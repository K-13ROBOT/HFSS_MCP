"""端口激励的幅度/相位设置(native COM 版)。

HFSS 默认所有端口 1W / 0deg 同幅同相。做**双馈圆极化**(正交双探针 + 90° 电桥)、
差分馈电、相控阵扫描时,必须能把某个端口的相位设成 90°/180°,否则远场算出来的
轴比/方向图不是实际馈电网络下的结果。

EditSources 的参数块跨版本有差异,这里按本仓库惯例做多形式 fallback。
注意:EditSources 是**全量替换**——没在 sources 里指定的端口会被补成 1W/0deg 默认值。
"""

from . import tool


def _list_excitations(oDesign):
    """返回激励名列表(如 ['P1:1','P2:1'])。GetExcitations 返回 name/type 交替的扁平表。"""
    try:
        raw = list(oDesign.GetModule("BoundarySetup").GetExcitations() or [])
    except Exception:
        return []
    return [raw[i] for i in range(0, len(raw), 2)]


def _match(name, available):
    """把用户给的 'P1' 或 'P1:1' 对到实际激励名上。"""
    if name in available:
        return name
    for a in available:
        if a.split(":")[0] == str(name).split(":")[0]:
            return a
    return None


@tool({
    "type": "function",
    "function": {
        "name": "set_port_excitation",
        "description": (
            "设置各端口激励的**幅度与相位**(默认全部 1W/0deg)。"
            "做**双馈 CP**(正交双探针 + 90° 电桥)必须用它把一个口设成 90deg,否则远场轴比算的是同相馈电、不是实际结果;"
            "差分馈电(180deg)、相控阵扫描同理。"
            "**全量替换语义**:没在 sources 里列出的端口会被补成 1W/0deg。"
            "设完直接取远场(get_axial_ratio / get_radiation_pattern)即可,不需要重新 analyze"
            "(改的是后处理叠加权重,不是求解本身)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "description": "各端口的激励设置。端口名写 'P1' 或 'P1:1' 都可以。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "port": {"type": "string", "description": "端口名,如 'P1'"},
                            "magnitude": {"type": "string", "default": "1W",
                                          "description": "幅度带单位,如 '1W';等幅馈电就都填 '1W'"},
                            "phase": {"type": "string", "default": "0deg",
                                      "description": "相位带 deg,如 '0deg'/'90deg'。双馈 CP 用 0/90"},
                        },
                        "required": ["port"],
                    },
                },
            },
            "required": ["sources"],
        },
    },
})
def set_port_excitation(ctx, sources):
    oDesign = ctx["oDesign"]
    available = _list_excitations(oDesign)
    if not available:
        return {"ok": False, "error": "当前 design 没有激励(端口)"}

    wanted = {}
    unknown = []
    for s in sources or []:
        pname = s.get("port")
        hit = _match(pname, available)
        if hit is None:
            unknown.append(pname)
            continue
        wanted[hit] = (str(s.get("magnitude", "1W")), str(s.get("phase", "0deg")))
    if unknown:
        return {"ok": False, "error": "找不到端口: %s" % unknown, "available": available}
    if not wanted:
        return {"ok": False, "error": "sources 为空"}

    # 全量替换:没指定的补默认值,并在返回里说明
    filled = []
    rows = []
    for exc in available:
        mag, ph = wanted.get(exc, ("1W", "0deg"))
        if exc not in wanted:
            filled.append(exc)
        rows.append(["Name:=", exc, "Magnitude:=", mag, "Phase:=", ph])

    try:
        oModule = oDesign.GetModule("Solutions")
    except Exception as e:
        return {"ok": False, "error": "取 Solutions 模块失败: %s: %s" % (type(e).__name__, e)}

    head_variants = [
        ["IncludePortPostProcessing:=", False, "SpecifySystemPower:=", False],
        ["FieldType:=", "TotalFields", "IncludePortPostProcessing:=", False,
         "SpecifySystemPower:=", False],
        ["FieldType:=", "TotalFields"],
    ]
    last = None
    for head in head_variants:
        try:
            oModule.EditSources([head] + rows)
            applied = {r[1]: {"magnitude": r[3], "phase": r[5]} for r in rows}
            out = {"ok": True, "sources": applied, "n_ports": len(rows),
                   "head_form": head[0]}
            if filled:
                out["defaulted_to_1W_0deg"] = filled
                out["note"] = ("EditSources 是全量替换,以上端口未在 sources 中指定,"
                               "已按 1W/0deg 填入")
            out["hint"] = "后处理权重已改,直接取远场即可,不必重新 analyze"
            return out
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
    return {"ok": False, "error": "EditSources 失败(已试 %d 种参数块形式): %s" % (len(head_variants), last),
            "tried_rows": rows}
