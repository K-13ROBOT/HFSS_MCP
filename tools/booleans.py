"""布尔运算(native COM 版)—— oEditor.Subtract/Unite/Intersect 直通。"""

from . import tool


def _csv(names):
    if isinstance(names, str):
        return names
    return ",".join(names)


@tool({
    "type": "function",
    "function": {
        "name": "subtract",
        "description": "布尔减:从 blank 减去 tools 列表里的对象。blank 保留,tools 被消耗。",
        "parameters": {
            "type": "object",
            "properties": {
                "blank": {"type": "string", "description": "被减对象(保留)"},
                "tools": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "减去的对象名列表"},
                "keep_originals": {"type": "boolean", "default": False, "description": "是否保留 tools 对象"},
            },
            "required": ["blank", "tools"],
        },
    },
})
def subtract(ctx, blank, tools, keep_originals=False):
    oEditor = ctx["oEditor"]
    try:
        oEditor.Subtract(
            ["NAME:Selections", "Blank Parts:=", blank, "Tool Parts:=", _csv(tools)],
            ["NAME:SubtractParameters", "KeepOriginals:=", bool(keep_originals)],
        )
    except Exception as e:
        return {"ok": False, "error": f"Subtract 失败: {type(e).__name__}: {e}"}
    if "state" in ctx and not keep_originals:
        for t in (tools if isinstance(tools, list) else [tools]):
            ctx["state"].objects.pop(t, None)
    return {"ok": True, "blank": blank, "subtracted": list(tools)}


@tool({
    "type": "function",
    "function": {
        "name": "unite",
        "description": "布尔并:把 objects 合并成一个,结果保留在第一个名字下。",
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "要合并的对象名,第一个是保留名"},
                "keep_originals": {"type": "boolean", "default": False},
            },
            "required": ["objects"],
        },
    },
})
def unite(ctx, objects, keep_originals=False):
    oEditor = ctx["oEditor"]
    try:
        oEditor.Unite(
            ["NAME:Selections", "Selections:=", _csv(objects)],
            ["NAME:UniteParameters", "KeepOriginals:=", bool(keep_originals)],
        )
    except Exception as e:
        return {"ok": False, "error": f"Unite 失败: {type(e).__name__}: {e}"}
    if "state" in ctx and not keep_originals:
        for t in objects[1:]:
            ctx["state"].objects.pop(t, None)
    return {"ok": True, "result": objects[0], "merged": list(objects)}


@tool({
    "type": "function",
    "function": {
        "name": "intersect",
        "description": "布尔交:保留 objects 的公共部分,结果在第一个名字下。",
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                "keep_originals": {"type": "boolean", "default": False},
            },
            "required": ["objects"],
        },
    },
})
def intersect(ctx, objects, keep_originals=False):
    oEditor = ctx["oEditor"]
    try:
        oEditor.Intersect(
            ["NAME:Selections", "Selections:=", _csv(objects)],
            ["NAME:IntersectParameters", "KeepOriginals:=", bool(keep_originals)],
        )
    except Exception as e:
        return {"ok": False, "error": f"Intersect 失败: {type(e).__name__}: {e}"}
    return {"ok": True, "result": objects[0], "intersected": list(objects)}


# ─────────────────────────────────────────────────────────
# split —— 按坐标平面切割(oEditor.Split 直通)
# 参数格式对照 PyAEDT modeler.split(primitives.py)核实。
# AEDT 的切割平面只能过当前坐标系原点,所以非零 offset 用"平移→切→移回"实现。
# ─────────────────────────────────────────────────────────

_SPLIT_SIDE = {"positive": "PositiveOnly", "negative": "NegativeOnly", "both": "Both"}
_PLANE_AXIS = {"XY": 2, "YZ": 0, "ZX": 1}


def _all_names(oEditor):
    try:
        return set(oEditor.GetMatchedObjectName("*"))
    except Exception:
        return None


def _translate(oEditor, names, axis_idx, expr):
    v = ["0mm", "0mm", "0mm"]
    v[axis_idx] = expr
    oEditor.Move(
        ["NAME:Selections", "Selections:=", _csv(names), "NewPartsModelFlag:=", "Model"],
        ["NAME:TranslateParameters",
         "TranslateVectorX:=", v[0], "TranslateVectorY:=", v[1], "TranslateVectorZ:=", v[2]],
    )


@tool({
    "type": "function",
    "function": {
        "name": "split",
        "description": ("按坐标平面切割对象(实体或 sheet 都行),保留一侧或两侧。"
            "plane=XY 表示平面 z=offset(法向 +Z),YZ → x=offset,ZX → y=offset;"
            "keep='positive' 留法向正侧,'negative' 留负侧,'both' 两侧都留(新增部件名见返回)。"
            "offset 可用变量表达式。**切 sheet 只能用本工具** —— solid 去 subtract 一张 sheet "
            "会类型不匹配而失败,并把 blank 一起删掉。"),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                            "description": "要切的对象名列表"},
                "plane": {"type": "string", "enum": ["XY", "YZ", "ZX"], "description": "切割平面方向"},
                "offset": {"type": "string", "default": "0mm",
                           "description": "平面沿其法向的位置,带单位或变量,如 '67mm'"},
                "keep": {"type": "string", "enum": ["positive", "negative", "both"], "default": "negative",
                         "description": "保留哪一侧"},
            },
            "required": ["objects", "plane"],
        },
    },
})
def split(ctx, objects, plane, offset="0mm", keep="negative"):
    oEditor = ctx["oEditor"]
    objects = [objects] if isinstance(objects, str) else list(objects)
    if plane not in _PLANE_AXIS or keep not in _SPLIT_SIDE:
        return {"ok": False, "error": f"plane 须为 XY/YZ/ZX,keep 须为 positive/negative/both(收到 {plane}/{keep})"}
    axis_idx = _PLANE_AXIS[plane]
    off = str(offset).strip()
    shifted = off not in ("", "0", "0mm", "0.0mm", "0.0")
    before = _all_names(oEditor)
    moved = False
    try:
        if shifted:
            _translate(oEditor, objects, axis_idx, f"-({off})")
            moved = True
        oEditor.Split(
            ["NAME:Selections", "Selections:=", _csv(objects), "NewPartsModelFlag:=", "Model"],
            ["NAME:SplitToParameters",
             "SplitPlane:=", plane,
             "WhichSide:=", _SPLIT_SIDE[keep],
             "ToolType:=", "PlaneTool",
             "ToolEntityID:=", -1,
             "SplitCrossingObjectsOnly:=", False,
             "DeleteInvalidObjects:=", True],
        )
    except Exception as e:
        if moved:  # 切失败也要把对象移回原位,别留下错位几何
            try:
                _translate(oEditor, objects, axis_idx, f"({off})")
            except Exception:
                pass
        return {"ok": False, "error": f"Split 失败: {type(e).__name__}: {e}"}

    after = _all_names(oEditor)
    if before is not None and after is not None:
        new_parts = sorted(after - before)
        survivors = [o for o in objects if o in after] + new_parts
        removed = [o for o in objects if o not in after]
    else:
        new_parts, removed, survivors = [], [], list(objects)
    if shifted and survivors:
        try:
            _translate(oEditor, survivors, axis_idx, f"({off})")
        except Exception as e:
            return {"ok": False, "error": f"Split 成功但移回原位失败: {type(e).__name__}: {e}",
                    "hint": f"对象仍在 {plane} 法向上偏移了 -({off}),用 move 手动移回", "parts": survivors}
    if "state" in ctx:
        for o in removed:
            ctx["state"].objects.pop(o, None)
        for n in new_parts:
            ctx["state"].objects.setdefault(n, {"type": "split_part"})
    return {"ok": True, "plane": plane, "offset": off, "keep": keep,
            "parts": survivors, "new_parts": new_parts, "removed": removed}
