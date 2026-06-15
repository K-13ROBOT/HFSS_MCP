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
