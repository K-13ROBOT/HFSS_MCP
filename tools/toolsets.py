"""按需加载的扩展工具:不常用的分组不进 tools/list(省每轮上下文),经 extra_tools 一个入口查参数、调用。

不用 MCP 的 tools/list_changed 动态增删:Claude Code 同一轮里新出现的工具调不到,别的客户端也未必支持;
一个固定入口在任何客户端上都稳。扩展工具仍注册在 TOOLS 里,dispatch 照常能调(测试脚本不受影响)。
"""

from . import tool, TOOLS

EXTRA_GROUPS = {
    "periodic": (["assign_periodic_boundaries", "assign_floquet_port"],
                 "无限阵 / FSS / 超表面单元:主从边界 + Floquet 端口"),
    "eigenmode": (["create_eigenmode_setup", "get_eigenmodes"],
                  "本征模:腔体/滤波器/DRA 的谐振频率与 Q(design 须建成 Eigenmode 类型)"),
    "statistical": (["create_statistical", "run_statistical", "get_statistical_result"],
                    "公差/良率蒙特卡洛(设计达标之后、投板之前)"),
    "boundary": (["assign_perfect_h", "assign_impedance", "assign_finite_conductivity", "assign_lumped_rlc"],
                 "进阶边界:Perfect H、阻抗面、有限电导率、集总 RLC"),
    "mesh": (["assign_mesh_length", "assign_mesh_surface"],
             "手动网格加密(默认自适应网格够用,有证据才加)"),
    "history": (["get_object_history", "set_history_props", "replace_in_history"],
                "改已有对象的建模历史参数(多边形锚点换表达式、布尔里工具圆的半径/位置),不新建对象"),
}
EXTRA_TOOLS = {n: g for g, (names, _) in EXTRA_GROUPS.items() for n in names}


def _schema(name):
    fn = TOOLS[name]["schema"]["function"]
    return {"name": name, "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}})}


def _catalog():
    return "; ".join(f"{g}: {'/'.join(names)} —— {what}" for g, (names, what) in EXTRA_GROUPS.items())


@tool({"type": "function", "function": {
    "name": "extra_tools",
    "description": ("不常用工具的入口(不在工具列表里,按需加载)。"
                    "先 extra_tools(group=...) 取该组各工具的参数说明,再 extra_tools(tool=..., arguments={...}) 调用。"
                    "分组 —— " + _catalog()),
    "parameters": {"type": "object", "properties": {
        "group": {"type": "string", "enum": list(EXTRA_GROUPS),
                  "description": "要看参数说明的分组"},
        "tool": {"type": "string", "description": "要调用的扩展工具名"},
        "arguments": {"type": "object", "description": "传给该工具的参数,按 group 返回的 parameters 填"}}}}})
def extra_tools(ctx, group=None, tool=None, arguments=None):
    if not tool:
        if group not in EXTRA_GROUPS:
            return {"ok": False, "error": "给 group 看参数说明,或给 tool + arguments 调用",
                    "groups": {g: {"tools": n, "what": w} for g, (n, w) in EXTRA_GROUPS.items()}}
        names, what = EXTRA_GROUPS[group]
        return {"ok": True, "group": group, "what": what, "tools": [_schema(n) for n in names],
                "hint": "调用:extra_tools(tool='<name>', arguments={...})"}
    if tool not in EXTRA_TOOLS:
        hint = "它在常规工具列表里,直接调" if tool in TOOLS else "看 groups 里的工具名"
        return {"ok": False, "error": f"'{tool}' 不是扩展工具", "hint": hint,
                "groups": {g: n for g, (n, _) in EXTRA_GROUPS.items()}}
    args = arguments or {}
    params = TOOLS[tool]["schema"]["function"].get("parameters", {})
    props = params.get("properties", {})
    missing = [k for k in params.get("required", []) if k not in args]
    unknown = [k for k in args if k not in props]
    if missing or unknown:
        return {"ok": False, "error": f"{tool} 参数不对:缺 {missing},不认识 {unknown}",
                "schema": _schema(tool)}
    from . import dispatch
    return dispatch(tool, args, ctx)
