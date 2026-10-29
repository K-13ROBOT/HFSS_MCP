"""诊断:读 HFSS 消息窗口 + 调 HFSS 自带 Validation Check(native COM 版)。

补的是这么一个盲区:COM 只把「调用本身失败」抛给我们,而 HFSS 真正的抱怨
(端口缺积分线、材料未定义、边界重叠、网格/收敛警告)只写进**消息窗口**。
求解跑完但结果不对时,答案通常在那儿。

- get_messages   : oDesktop.GetMessages(project, design, severity)
- validate_design: oDesign.ValidateDesign() 的返回码 + 「调用前后消息差集」的合取。

实测(2019.2 / 2025.2):
- 返回码:2025.2 给 Python bool、2019.2 给 int,bool() 之后语义一致(假=失败),两版都可信;
- 消息窗口:2025.2 校验完立刻可读;**2019.2 写入滞后可达几十秒** —— 所以判定以返回码为主,
  消息只用来说明"错在哪";
- GetMessages 的 severity 参数在 2025.2 上 0/1/2 结果完全相同(不起作用),级别只能自己从
  消息文本里的 [error]/[warning] 标记解析。
"""

import re
import time

from . import tool

# 2025.2 实测的真实消息格式(级别标记在**中间**,不是开头):
#   Project: P1, Design: d1, [error] Boundary Setup: An excitation must be defined... (时间戳),尾部带 CRLF
# 所以只能全串搜标记,不能 startswith。
_LEVEL_RE = re.compile(r"\[(error|fatal|warning|warn|info|verbose)\]", re.I)


def _classify(msg):
    """从消息文本判级别。取不到标记当 info(宁可漏报,不误报)。"""
    m = _LEVEL_RE.search(str(msg))
    if not m:
        return "info"
    lv = m.group(1).lower()
    if lv in ("error", "fatal"):
        return "error"
    if lv in ("warning", "warn"):
        return "warning"
    return "info"


def _clean(msg):
    """压掉尾部换行和多余空白(HFSS 每条消息都带 CRLF)。"""
    return " ".join(str(msg).split())


def _raw_messages(oDesktop, project, design, severity):
    """调 GetMessages,多形式 fallback(各版本签名不一)。返回 (list[str], err)。"""
    forms = [
        (project, design, int(severity)),
        (project, design),
        (),
    ]
    last = None
    for args in forms:
        try:
            raw = oDesktop.GetMessages(*args)
            return [str(m) for m in (raw or []) if str(m).strip()], None
        except Exception as e:
            last = "{0}: {1}".format(type(e).__name__, e)
    return [], last


def _summarize(msgs):
    """按级别分桶。"""
    out = {"error": [], "warning": [], "info": []}
    for m in msgs:
        out[_classify(m)].append(_clean(m))
    return out


@tool({
    "type": "function",
    "function": {
        "name": "get_messages",
        "description": ("读 HFSS **消息窗口**(Message Manager)。COM 异常只反映「调用失败」,而端口缺积分线、"
            "材料未定义、边界重叠、自适应不收敛、解被作废这类抱怨**只出现在消息窗口里**。"
            "返回按 error/warning/info 分桶 + 最近 limit 条原文。什么时候必读,见 `flow/s-parameters.md`。"),
        "parameters": {
            "type": "object",
            "properties": {
                "project": {"type": "string",
                            "description": "工程名;省略用当前 active project,传空字符串 '' 取全部工程"},
                "design": {"type": "string",
                           "description": "design 名;省略用当前 active design,传 '' 取该工程全部 design"},
                "severity": {"type": "integer", "default": 0,
                             "description": "HFSS 侧过滤级别(实测不起作用,一般不用传);分桶以返回的 error/warning 计数为准"},
                "limit": {"type": "integer", "default": 50,
                          "description": "返回最近多少条原文,默认 50(分桶计数不受限)"},
                "errors_only": {"type": "boolean", "default": False,
                                "description": "只回 error+warning 原文,省 context"},
            },
        },
    },
})
def get_messages(ctx, project=None, design=None, severity=0, limit=50, errors_only=False):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "未连接 desktop,先 open_desktop 或 attach_desktop"}
    proj = ctx.get("project_name") or "" if project is None else project
    dsn = ctx.get("design_name") or "" if design is None else design

    msgs, err = _raw_messages(oDesktop, proj, dsn, severity)
    if err and not msgs:
        return {"ok": False, "error": "GetMessages 失败: {0}".format(err)}

    buckets = _summarize(msgs)
    tail = buckets["error"] + buckets["warning"] if errors_only else msgs[-int(limit):]
    out = {"ok": True, "project": proj or "(全部)", "design": dsn or "(全部)",
           "total": len(msgs),
           "counts": {k: len(v) for k, v in buckets.items()},
           "errors": buckets["error"], "warnings": buckets["warning"],
           "messages": [_clean(m) for m in tail]}
    if buckets["error"]:
        out["hint"] = "有 error 级消息,先解决它们再谈结果对不对"
    return out


@tool({
    "type": "function",
    "function": {
        "name": "validate_design",
        "description": ("跑 HFSS 自带的 Validation Check:端口没积分线 / setup 没绑激励 / 边界重叠 / 材料缺失。"
            "与 get_object_bbox 的分工:bbox 查几何层叠搭接(我们自己的自检),"
            "本工具查 **HFSS 认不认**这个 design。analyze 之前必调,见 `flow/s-parameters.md`。"),
        "parameters": {"type": "object", "properties": {}},
    },
})
def validate_design(ctx):
    oDesign = ctx["oDesign"]
    oDesktop = ctx.get("oDesktop")
    proj = ctx.get("project_name") or ""
    dsn = ctx.get("design_name") or ""

    # 校验结果写进消息窗口 → 用「调用前后差集」拿这次校验产生的那几条
    before = []
    if oDesktop is not None:
        before, _ = _raw_messages(oDesktop, proj, dsn, 0)

    code, err = None, None
    for meth in ("ValidateDesign", "ValidateCircuit"):   # 名字按版本/产品线有别,都试
        try:
            code = getattr(oDesign, meth)()
            err = None
            break
        except Exception as e:
            err = "{0}: {1}".format(meth, e)
    if err is not None:
        return {"ok": False, "error": "ValidateDesign 失败: {0}".format(err),
                "hint": "该版本可能没暴露此方法;可先用 design_summary + get_object_bbox 自检"}

    # 消息窗口不是同步写的:2019.2 实测校验完立刻读是空的,几十秒后才浮出来。
    # 这里给几百毫秒沉降时间兜住"稍慢一点"的情况;真延迟很久的靠返回码判,并在 hint 里叫人复核。
    new_msgs = []
    if oDesktop is not None:
        for _ in range(3):
            after, _e = _raw_messages(oDesktop, proj, dsn, 0)
            new_msgs = after[len(before):] if len(after) >= len(before) else after
            if new_msgs:
                break
            time.sleep(0.3)

    buckets = _summarize(new_msgs)
    # 判据取「返回码 AND 无 error 消息」的合取,两条腿互相兜底。返回码实测:
    #   2025.2 → Python bool(坏 design=False / 好 design=True)
    #   2019.2 → int   (坏 design=0     / 好 design=1)
    # 两者 bool() 之后语义一致,所以 bool/int 都认;其它类型(None/字符串)才退回只看消息。
    rc = bool(code) if isinstance(code, (bool, int)) else None
    passed = (not buckets["error"]) if rc is None else (rc and not buckets["error"])
    out = {"ok": True, "passed": passed, "return_code": code,
           "design": dsn or None,
           "counts": {k: len(v) for k, v in buckets.items()},
           "errors": buckets["error"], "warnings": buckets["warning"]}
    if not passed:
        out["hint"] = "校验未通过:先修 errors 再 analyze,否则大概率白跑"
        if not buckets["error"]:
            out["hint"] += ("。返回码判失败但没抓到 error 原文——消息窗口写入有延迟"
                            "(2019.2 实测滞后可达几十秒),过一会儿调 get_messages 看具体是什么")
    elif rc is None and not new_msgs:
        out["note"] = "返回码类型未知且校验没产生新消息 —— 通常表示通过;拿不准用 get_messages 复核"
    return out


# ─────────────────────────────────────────────────────────
# design_summary —— 当前 design 全景(从 geometry.py 搬来:看全景、不改模型,
# 跟 get_messages / validate_design 同属诊断,不属于几何)
# 逐项 try:modeler 瞬时抽风时只让该字段带 _error,其余照常返回,别整份作废
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "design_summary",
        "description": ("当前 design 全景:对象(实体/片)、变量、边界、激励(端口)、setup。"
                        "新任务/仿真/取数前先调,确认现状,别重复创建已有的。"),
        "parameters": {"type": "object", "properties": {}},
    },
})
def design_summary(ctx):
    oEditor = ctx["oEditor"]
    oDesign = ctx["oDesign"]
    out = {"ok": True, "project": ctx.get("project_name"), "design": ctx.get("design_name")}

    try:
        out["solids"] = [str(n) for n in (oEditor.GetObjectsInGroup("Solids") or []) if n]
        out["sheets"] = [str(n) for n in (oEditor.GetObjectsInGroup("Sheets") or []) if n]
    except Exception as e:
        out["objects_error"] = str(e)[:80]
    try:
        out["variables"] = {str(v): str(oDesign.GetVariableValue(v)) for v in (oDesign.GetVariables() or [])}
    except Exception as e:
        out["variables_error"] = str(e)[:80]
    try:
        b = list(oDesign.GetModule("BoundarySetup").GetBoundaries() or [])  # [name,type,name,type,...]
        out["boundaries"] = [{"name": b[i], "type": b[i + 1]} for i in range(0, len(b) - 1, 2)]
    except Exception as e:
        out["boundaries_error"] = str(e)[:80]
    try:
        e2 = list(oDesign.GetModule("BoundarySetup").GetExcitations() or [])
        out["excitations"] = [{"name": e2[i], "type": e2[i + 1]} for i in range(0, len(e2) - 1, 2)]
    except Exception as e:
        out["excitations_error"] = str(e)[:80]
    try:
        out["setups"] = [str(s) for s in (oDesign.GetModule("AnalysisSetup").GetSetups() or [])]
    except Exception as e:
        out["setups_error"] = str(e)[:80]
    return out
