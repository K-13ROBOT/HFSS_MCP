"""几何变换 —— 全部走 HFSS oEditor COM API 直通,不依赖 PyAEDT modeler cache。

5 个工具:
  - duplicate_along_line:沿向量复制 N 份(线阵列)
  - duplicate_around_axis:绕轴旋转复制 N 份(圆阵列)
  - move:就地平移
  - rotate:就地旋转
  - mirror:就地镜像
"""

from . import tool


# ─────────────────────────────────────────────────────────
# 共享 helper:COM 参数构造 & 返回值解析
# ─────────────────────────────────────────────────────────

def _selections_arg(objects):
    """HFSS COM 要求多个对象用逗号分隔成一个字符串。"""
    if isinstance(objects, str):
        return objects
    return ",".join(objects)


def _parse_new_names(result):
    """COM 返回的新对象名可能是 tuple / list / 单字符串,统一返回 list[str]。"""
    if result is None:
        return []
    if isinstance(result, str):
        return [result] if result else []
    try:
        return [str(x) for x in result if x]
    except TypeError:
        return [str(result)]


def _register_duplicates(state, source_list, new_names):
    """把复制出的新对象登记到 state.objects,继承源对象的元信息。"""
    if not source_list:
        return
    template = state.objects.get(source_list[0], {})
    for n in new_names:
        state.objects[n] = {**template, "duplicated_from": source_list[0]}


# ─────────────────────────────────────────────────────────
# 1. duplicate_along_line —— 沿向量复制(线阵列)
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "duplicate_along_line",
        "description": (
            "沿向量复制对象 N 份,做线阵列。n_clones=4 表示原 1 个 + 复制 3 个,**共 4 个**。"
            "新对象自动继承源对象的材料和边界(PE 等),不需要重新赋。"
            "走 HFSS COM 直通,不依赖 PyAEDT cache,稳定。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "要复制的对象名列表",
                },
                "vector": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3, "maxItems": 3,
                    "description": "相邻两份之间的位移 [dx, dy, dz],带单位",
                },
                "n_clones": {
                    "type": "integer",
                    "minimum": 2,
                    "default": 2,
                    "description": "总份数(含原对象),n_clones=4 表示原 1 + 复制 3",
                },
            },
            "required": ["objects", "vector"],
        },
    },
})
def duplicate_along_line(ctx, objects, vector, n_clones=2):
    oEditor = ctx["oEditor"]
    state = ctx["state"]
    if n_clones < 2:
        return {"ok": False, "error": "n_clones 必须 >= 2"}

    try:
        result = oEditor.DuplicateAlongLine(
            ["NAME:Selections",
             "Selections:=", _selections_arg(objects),
             "NewPartsModelFlag:=", "Model"],
            ["NAME:DuplicateToAlongLineParameters",
             "CreateNewObjects:=", True,
             "XComponent:=", str(vector[0]),
             "YComponent:=", str(vector[1]),
             "ZComponent:=", str(vector[2]),
             "NumClones:=", str(n_clones)],
            ["NAME:Options", "DuplicateAssignments:=", True],
            ["CreateGroupsForNewObjects:=", False],
        )
    except Exception as e:
        return {"ok": False, "error": f"DuplicateAlongLine COM 调用失败: {type(e).__name__}: {e}"}

    new_names = _parse_new_names(result)
    _register_duplicates(state, objects, new_names)
    return {"ok": True, "source": objects, "vector": vector,
            "n_clones": n_clones, "new_objects": new_names}


# ─────────────────────────────────────────────────────────
# 2. duplicate_around_axis —— 绕轴旋转复制(圆阵列)
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "duplicate_around_axis",
        "description": (
            "绕过原点的轴旋转复制 N 份,做圆阵列或螺旋臂。"
            "n_clones=8 + angle=45deg 表示 8 元均匀圆阵(360°/8=45°)。"
            "新对象自动继承源对象的材料和边界。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "要复制的对象名列表",
                },
                "axis": {
                    "type": "string",
                    "enum": ["X", "Y", "Z"],
                    "description": "旋转轴(过原点),圆阵列常用 'Z'",
                },
                "angle": {
                    "type": "string",
                    "description": "相邻两份之间的旋转角度,带 deg,如 '45deg'",
                },
                "n_clones": {
                    "type": "integer",
                    "minimum": 2,
                    "description": "总份数(含原对象)",
                },
            },
            "required": ["objects", "axis", "angle", "n_clones"],
        },
    },
})
def duplicate_around_axis(ctx, objects, axis, angle, n_clones):
    oEditor = ctx["oEditor"]
    state = ctx["state"]
    if n_clones < 2:
        return {"ok": False, "error": "n_clones 必须 >= 2"}

    try:
        result = oEditor.DuplicateAroundAxis(
            ["NAME:Selections",
             "Selections:=", _selections_arg(objects),
             "NewPartsModelFlag:=", "Model"],
            ["NAME:DuplicateAroundAxisParameters",
             "CreateNewObjects:=", True,
             "WhichAxis:=", axis,
             "AngleStr:=", str(angle),
             "NumClones:=", str(n_clones)],
            ["NAME:Options", "DuplicateAssignments:=", True],
            ["CreateGroupsForNewObjects:=", False],
        )
    except Exception as e:
        return {"ok": False, "error": f"DuplicateAroundAxis COM 调用失败: {type(e).__name__}: {e}"}

    new_names = _parse_new_names(result)
    _register_duplicates(state, objects, new_names)
    return {"ok": True, "source": objects, "axis": axis, "angle": angle,
            "n_clones": n_clones, "new_objects": new_names}


# ─────────────────────────────────────────────────────────
# 3. move —— 就地平移
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "move",
        "description": (
            "把对象沿向量平移。原对象被移动,不复制。"
            "如需保留原位再复制一份,用 duplicate_along_line 而不是 move。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "要平移的对象名列表",
                },
                "vector": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3, "maxItems": 3,
                    "description": "位移向量 [dx, dy, dz],带单位",
                },
            },
            "required": ["objects", "vector"],
        },
    },
})
def move(ctx, objects, vector):
    oEditor = ctx["oEditor"]

    try:
        oEditor.Move(
            ["NAME:Selections",
             "Selections:=", _selections_arg(objects),
             "NewPartsModelFlag:=", "Model"],
            ["NAME:TranslateParameters",
             "TranslateVectorX:=", str(vector[0]),
             "TranslateVectorY:=", str(vector[1]),
             "TranslateVectorZ:=", str(vector[2])],
        )
    except Exception as e:
        return {"ok": False, "error": f"Move COM 调用失败: {type(e).__name__}: {e}"}

    return {"ok": True, "moved": objects, "vector": vector}


# ─────────────────────────────────────────────────────────
# 4. rotate —— 就地旋转(绕过原点的轴)
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "rotate",
        "description": (
            "把对象绕过原点的轴旋转 angle 度。就地变换,不复制。正向角度按右手定则。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "要旋转的对象名列表",
                },
                "axis": {
                    "type": "string",
                    "enum": ["X", "Y", "Z"],
                    "description": "旋转轴(过原点)",
                },
                "angle": {
                    "type": "string",
                    "description": "角度,带 deg,如 '45deg'、'-30deg'",
                },
            },
            "required": ["objects", "axis", "angle"],
        },
    },
})
def rotate(ctx, objects, axis, angle):
    oEditor = ctx["oEditor"]

    try:
        oEditor.Rotate(
            ["NAME:Selections",
             "Selections:=", _selections_arg(objects),
             "NewPartsModelFlag:=", "Model"],
            ["NAME:RotateParameters",
             "RotateAxis:=", axis,
             "RotateAngle:=", str(angle)],
        )
    except Exception as e:
        return {"ok": False, "error": f"Rotate COM 调用失败: {type(e).__name__}: {e}"}

    return {"ok": True, "rotated": objects, "axis": axis, "angle": angle}


# ─────────────────────────────────────────────────────────
# 5. mirror —— 关于平面镜像(就地)
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "mirror",
        "description": (
            "把对象关于一个平面镜像。平面由 base(平面上一点)和 normal(法向量)定义。"
            "就地变换,不复制。要保留原对象再镜像,先 duplicate 再对新对象 mirror。"
            "典型用法:左半臂建好后镜像出右半臂(差分馈电)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "要镜像的对象名列表",
                },
                "base": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3, "maxItems": 3,
                    "description": "镜像平面上一点 [x, y, z],带单位。常用 ['0mm','0mm','0mm']",
                },
                "normal": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3, "maxItems": 3,
                    "description": "镜像平面法向量 [nx, ny, nz],无单位。例 ['1','0','0'] 表示关于 YZ 平面镜像",
                },
            },
            "required": ["objects", "base", "normal"],
        },
    },
})
def mirror(ctx, objects, base, normal):
    oEditor = ctx["oEditor"]

    try:
        oEditor.Mirror(
            ["NAME:Selections",
             "Selections:=", _selections_arg(objects),
             "NewPartsModelFlag:=", "Model"],
            ["NAME:MirrorParameters",
             "MirrorBaseX:=", str(base[0]),
             "MirrorBaseY:=", str(base[1]),
             "MirrorBaseZ:=", str(base[2]),
             "MirrorNormalVecX:=", str(normal[0]),
             "MirrorNormalVecY:=", str(normal[1]),
             "MirrorNormalVecZ:=", str(normal[2])],
        )
    except Exception as e:
        return {"ok": False, "error": f"Mirror COM 调用失败: {type(e).__name__}: {e}"}

    return {"ok": True, "mirrored": objects, "base": base, "normal": normal}
