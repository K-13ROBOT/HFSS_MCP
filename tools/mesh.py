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
        "description": ("对曲面对象设曲面逼近(faceting):圆柱/螺旋/球的初始网格是多边形逼近,窄缝、高Q 模对它敏感。"
                        "**推荐传 normal_dev**(如 '5deg',法向偏差,半径 R 的弦高≈R(1-cos(dev/2))),含义明确;"
                        "slider 的 **全局默认是 5,数字越大越细**——传小于 5 的 level 是在**变粗**。同名算子会先删再建。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "level": {"type": "integer", "default": 7,
                          "description": "slider 档位;全局默认 5,越大越细(实测 4 比默认粗)。传了 normal_dev 时忽略"},
                "normal_dev": {"type": "string",
                               "description": "可选:法向偏差,如 '5deg'。给了就用 ManualSettings,不用 slider"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_mesh_surface(ctx, name, objects, level=7, normal_dev=None):
    missing = [n for n in objects if n not in set(_all_object_names(ctx["oEditor"]))]
    if missing:
        return {"ok": False, "error": "objects not found", "missing": missing}
    if normal_dev:
        # 键名照 AEDT 自带示例工程里录制的 SurfApproxBased 块
        approx = ["CurvedSurfaceApproxChoice:=", "ManualSettings", "SurfDevChoice:=", 0,
                  "NormalDevChoice:=", 2, "NormalDev:=", str(normal_dev), "AspectRatioChoice:=", 1]
    else:
        approx = ["CurvedSurfaceApproxChoice:=", "UseSlider", "SliderMeshSettings:=", int(level)]
    m = _mesh(ctx)
    replaced = False
    # GetOperationNames("SurfApproxBased") 实测查不到已有算子,直接尝试删,不存在时 DeleteOp 抛错即忽略
    try:
        m.DeleteOp([name])
        replaced = True
    except Exception:
        pass
    try:
        m.AssignTrueSurfOp(["NAME:" + name, "Type:=", "SurfApproxBased", "Objects:=", list(objects)] + approx)
    except Exception as e:
        out = {"ok": False, "error": f"AssignTrueSurfOp 失败: {type(e).__name__}: {e}"}
        if replaced:
            # 上面已经把同名算子删掉了,这里再失败就等于净删了一个 —— 必须说出来,
            # 否则调用方会以为"失败=什么都没变",实际旧的细化已经没了。
            out["warning"] = (f"同名算子 '{name}' 已被删除且新算子创建失败,该细化现在**不存在**。"
                              "注意 DeleteOp 不分算子类型,被删的可能是 assign_mesh_length 建的。重新赋一次。")
        return out
    out = {"ok": True, "name": name, "objects": list(objects), "replaced": replaced}
    out.update({"normal_dev": str(normal_dev)} if normal_dev else {"level": int(level)})
    return out
