"""网格控制(native COM 版)—— oDesign.GetModule("MeshSetup") 直通。"""

from . import tool
from .geometry import _all_object_names


def _mesh(ctx):
    return ctx["oDesign"].GetModule("MeshSetup")


@tool({
    "type": "function",
    "function": {
        "name": "assign_mesh_length",
        "description": ("对指定对象做长度细化:限制其网格最大边长,在关键区域(缝隙/薄结构/强场区)提精度。"
                        "max_length 越小越细越慢。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "网格操作名"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "max_length": {"type": "string", "description": "最大边长,带单位或变量(如 '0.5mm')"},
                "refine_inside": {"type": "boolean", "default": False, "description": "是否细化内部体网格"},
            },
            "required": ["name", "objects", "max_length"],
        },
    },
})
def assign_mesh_length(ctx, name, objects, max_length, refine_inside=False):
    missing = [n for n in objects if n not in set(_all_object_names(ctx["oEditor"]))]
    if missing:
        return {"ok": False, "error": "objects not found", "missing": missing}
    try:
        _mesh(ctx).AssignLengthOp(
            ["NAME:" + name, "RefineInside:=", bool(refine_inside), "Enabled:=", True,
             "Objects:=", list(objects), "RestrictElem:=", False, "NumMaxElem:=", "1000",
             "RestrictLength:=", True, "MaxLength:=", str(max_length)])
    except Exception as e:
        return {"ok": False, "error": f"AssignLengthOp 失败: {type(e).__name__}: {e}"}
    return {"ok": True, "name": name, "objects": list(objects), "max_length": str(max_length)}


@tool({
    "type": "function",
    "function": {
        "name": "assign_mesh_surface",
        "description": ("对曲面对象做曲率细化(slider 1-3):圆柱/球/弯曲探针等默认逼近粗,影响精度。level 越大越细。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "level": {"type": "integer", "default": 2, "description": "1=粗 2=中 3=细,默认 2"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_mesh_surface(ctx, name, objects, level=2):
    missing = [n for n in objects if n not in set(_all_object_names(ctx["oEditor"]))]
    if missing:
        return {"ok": False, "error": "objects not found", "missing": missing}
    try:
        _mesh(ctx).AssignTrueSurfOp(
            ["NAME:" + name, "Type:=", "SurfApproxBased", "Objects:=", list(objects),
             "CurvedSurfaceApproxChoice:=", "UseSlider", "SliderMeshSettings:=", int(level)])
    except Exception as e:
        return {"ok": False, "error": f"AssignTrueSurfOp 失败: {type(e).__name__}: {e}"}
    return {"ok": True, "name": name, "objects": list(objects), "level": int(level)}
