"""结构化追踪日志 —— LLM 调用 / 工具调用 / 用户轮 各打一条 JSON line。

文件名 ./traces/session-{YYYYMMDD-HHMMSS}.jsonl,append-only,跑完用 jq / pandas / grep 直接吃。

每条记录字段:
  ts:          时间戳 ISO 8601
  type:        session_start / turn / llm_call / tool_call / turn_end / note
  turn_id:     当前用户轮编号(从 1 开始)
  duration_ms: 耗时,float
  + 各 type 特有字段(见 init_session / next_turn / log 例子)

故意把所有失败兜底掉:trace 不能反过来拖垮主流程。
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

_TRACE_DIR = Path("./traces")
_session_path: Path | None = None
_turn_id = 0
# COM 工具跑在专用线程、NO_COM_REQUIRED 工具跑在事件循环上,两边都会 log ——
# 串行时代不需要锁,现在需要,否则两条 JSON line 可能交错成一行坏数据。
_write_lock = threading.Lock()


def init_session(model: str) -> Path | None:
    """REPL 启动时调一次,创建当次 session 的 jsonl 文件。"""
    global _session_path
    # cwd 由 MCP 客户端决定,可能不可写(见 tools/session.py 同款兜底)——依次退到用户目录/临时目录,
    # 都不行才放弃追踪。追踪没了不影响主流程,但能保留就保留。
    import tempfile
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    cands = [_TRACE_DIR,
             Path(os.path.expanduser("~")) / ".hfss-agent" / "traces",
             Path(tempfile.gettempdir()) / "hfss-agent" / "traces"]
    for d in cands:
        try:
            d.mkdir(parents=True, exist_ok=True)
            _session_path = d / f"session-{ts}.jsonl"
            log({"type": "session_start", "model": model, "pid": os.getpid()})
            return _session_path
        except Exception:
            _session_path = None
    print("[trace] 所有候选目录都不可写,本次会话无追踪日志")
    return None


def log(record: dict) -> None:
    """写一条 JSON line。任何错误都吞掉。"""
    if _session_path is None:
        return
    record.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _write_lock:
            with open(_session_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def next_turn(user_input: str) -> int:
    """每条用户输入开始时调,递增 turn_id 并落一条 turn 记录。"""
    global _turn_id
    _turn_id += 1
    log({"type": "turn", "turn_id": _turn_id, "user": _truncate_str(user_input, 200)})
    return _turn_id


def current_turn() -> int:
    return _turn_id


def truncate(val, max_len: int = 200):
    """嵌套结构瘦身,用于 args / 错误信息。和上下文压缩同样思路。"""
    if isinstance(val, str):
        return _truncate_str(val, max_len)
    if isinstance(val, (list, tuple)):
        items = list(val)
        if len(items) > 5:
            return [truncate(v, max_len) for v in items[:5]] + [f"…+{len(items)-5}"]
        return [truncate(v, max_len) for v in items]
    if isinstance(val, dict):
        out = {}
        for i, (k, v) in enumerate(val.items()):
            if i >= 20:
                out["…"] = f"+{len(val)-20} more keys"
                break
            out[k] = truncate(v, max_len)
        return out
    return val


def _truncate_str(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[:max_len] + "…"


def session_path() -> Path | None:
    return _session_path
