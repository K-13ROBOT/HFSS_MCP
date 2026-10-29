"""工具注册表 + 分发(native COM 版)。

跟 gRPC 版(hfss-mcp/)的区别:
- 连接走 win32com 裸调 AEDT 原生脚本 API(oDesktop/oEditor/oModule),不依赖 PyAEDT,
  (实测 2019.2 ~ 2025.2 均可用);
- ctx 持有的是 COM 句柄(oDesktop/oProject/oDesign/oEditor),不是 PyAEDT 的 Hfss 对象;
- 不需要 NO_PROXY / pyaedt 日志静默(那些是 gRPC/pyaedt 专属)。
"""

import os

TOOLS = {}

# 不需要 active design 即可调用(会话管理类 + 设计卡片只读检索)
NO_HFSS_REQUIRED = {
    "open_desktop", "attach_desktop", "close_desktop",
    "new_project", "open_project", "activate_project", "list_projects",
    "new_design", "activate_design", "list_designs",
    "search_designs", "read_design_card", "check_design_targets",
    "get_messages",   # 消息窗口:design 坏掉/没建起来时最需要读它,不能被 active design 挡住
}

# 完全不碰 COM 的工具(纯本地文件/计算)。这些不必排进 COM 单线程队列——
# 否则 analyze 跑 20 分钟期间,连查张设计卡片都要等 20 分钟。
NO_COM_REQUIRED = {
    "search_designs", "read_design_card", "check_design_targets",
}

# 调用前必须用户确认的工具(阻塞 / 耗资源)。环境变量 HFSS_AGENT_AUTOCONFIRM=1 跳过。
REQUIRES_CONFIRM = {
    "analyze",
    "run_parametric_sweep",
    "run_optimization",
    "run_sensitivity",
    "run_statistical",
}
_AUTOCONFIRM = os.environ.get("HFSS_AGENT_AUTOCONFIRM", "").lower() in ("1", "true", "yes")


def tool(schema):
    """装饰器:把函数 + schema 塞进 TOOLS。"""
    def deco(fn):
        TOOLS[schema["function"]["name"]] = {"fn": fn, "schema": schema}
        return fn
    return deco


def resolve_setup(ctx, setup=None):
    """要用的 setup 名。显式给的直接用;否则取 state 里第一个,state 为空(attach / 重开工程后)
    再问 HFSS。返回 (setup, None),找不到返回 (None, 错误 dict)。"""
    if setup:
        return setup, None
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        try:
            setups = [str(x) for x in (ctx["oDesign"].GetModule("AnalysisSetup").GetSetups() or [])]
        except Exception:
            setups = []
    if not setups:
        return None, {"ok": False, "error": "这个 design 里没有 setup,先 create_setup"}
    return setups[0], None


def setup_freqs(oDesign):
    """{setup: (Solution Freq Type, Solution Freq)},如 ('Multiple', '19.5GHz, 29.25GHz')、('Single', '5GHz')。
    多频 setup 会被 AEDT 静默冲成 Single 5GHz(见 skill _solving.md),analyze / run_* 求解前用它查。"""
    out = {}
    try:
        names = [str(x) for x in (oDesign.GetModule("AnalysisSetup").GetSetups() or [])]
    except Exception:
        return out
    for n in names:
        try:
            out[n] = tuple(str(oDesign.GetPropertyValue("HfssTab", "AnalysisSetup:" + n, k))
                           for k in ("Solution Freq Type", "Solution Freq"))
        except Exception:
            pass
    return out


def get_schemas():
    return [t["schema"] for t in TOOLS.values()]


def _ask_confirm(name, args):
    import json as _json
    args_str = _json.dumps(args, ensure_ascii=False, default=str)
    if len(args_str) > 200:
        args_str = args_str[:200] + "…"
    print(f"\n[Confirm] 即将执行 {name}({args_str})")
    print("  阻塞 / 耗资源操作,需要确认。继续? [y/N]: ", end="", flush=True)
    try:
        ans = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes")


def dispatch(name, args, ctx):
    """按名字找函数并调用。建模类工具先检查是否有 active design(native 看 oDesign)。"""
    import time
    import trace as _trace

    if name not in TOOLS:
        result = {"ok": False, "error": f"未知工具 '{name}'",
                  "available_tools": sorted(TOOLS.keys())}
        _trace.log({"type": "tool_call", "turn_id": _trace.current_turn(), "tool": name,
                    "args": _trace.truncate(args), "ok": False, "error": "unknown_tool",
                    "duration_ms": 0.0})
        return result

    if name not in NO_HFSS_REQUIRED and ctx.get("oDesign") is None:
        result = {"ok": False, "error": "无 active design",
                  "hint": "先 open_desktop 启动 HFSS,再 new_project + new_design;"
                          "或 attach_desktop + activate_project + activate_design"}
        _trace.log({"type": "tool_call", "turn_id": _trace.current_turn(), "tool": name,
                    "args": _trace.truncate(args), "ok": False, "error": "no_active_design",
                    "duration_ms": 0.0})
        return result

    # Optimetrics 批量求解(参扫/优化/灵敏度/统计)底下也是自适应:任何 setup 处在 Single 5GHz 回退态就先拦下,
    # 免得跑完一整批才发现网格是在 5 GHz 上自适应的。analyze 自己查(带 allow_5ghz 开关)。
    if name.startswith("run_") and ctx.get("oDesign") is not None:
        bad = [n for n, v in setup_freqs(ctx["oDesign"]).items() if v[0] == "Single" and v[1].replace(" ", "") == "5GHz"]
        if bad:
            return {"ok": False, "error": f"setup {bad} 是 Single 5GHz 自适应 —— 多半是多频 setup 被 AEDT 静默冲掉了,拒绝批量求解",
                    "hint": ("已实测的入口:端口删到零个后再建端口(2025.2)、2019 用了 2025 多频写法。"
                             "先把 setup 改回多频再跑;确实要 5 GHz,先单独 analyze(allow_5ghz=true)。")}

    if name in REQUIRES_CONFIRM and not _AUTOCONFIRM:
        if not _ask_confirm(name, args):
            result = {"ok": False, "error": "user_declined",
                      "hint": "用户拒绝了本次调用。先说明想跑什么/为什么/预估耗时,等回应再决定。"}
            _trace.log({"type": "tool_call", "turn_id": _trace.current_turn(), "tool": name,
                        "args": _trace.truncate(args), "ok": False, "error": "user_declined",
                        "duration_ms": 0.0})
            return result

    t0 = time.perf_counter()
    result = None
    exc_kind = None
    try:
        result = TOOLS[name]["fn"](ctx, **args)
        return result
    except Exception as e:
        exc_kind = f"{type(e).__name__}: {e}"
        raise
    finally:
        dt_ms = round((time.perf_counter() - t0) * 1000, 1)
        ok = isinstance(result, dict) and result.get("ok") is True
        err = exc_kind if exc_kind else (str(result.get("error", "")) if isinstance(result, dict) and result.get("ok") is False else None)
        _trace.log({"type": "tool_call", "turn_id": _trace.current_turn(), "tool": name,
                    "args": _trace.truncate(args), "ok": ok,
                    "error": _trace.truncate(err, 200) if err else None, "duration_ms": dt_ms})


from . import session, geometry, booleans, transforms, variables, boundaries, excitations, analysis, mesh, parametrics, optimization, design, periodic, axialratio, sources, diagnostics, fields, history
