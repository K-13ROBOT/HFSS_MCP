"""几何(native COM 版)—— 直接 oEditor 原生调用。Phase 1 先放 create_box + list_objects。"""

from . import tool

# 已知导体材料(SolveInside=False);其余(介质/真空)SolveInside=True
_CONDUCTORS = {"copper", "gold", "aluminum", "silver", "pec", "perfect conductor", "iron", "tungsten"}


def _all_object_names(oEditor):
    """所有对象名(实体 + 片)。GetObjectsInGroup 返回 tuple/list,统一成 list[str]。"""
    names = []
    for grp in ("Solids", "Sheets"):
        try:
            r = oEditor.GetObjectsInGroup(grp)
            if r:
                names.extend(str(n) for n in r if n)
        except Exception:
            pass
    return names


def _solve_inside(material):
    return (material or "").strip().lower().strip('"') not in _CONDUCTORS


# ── 配色:按材料/角色区分,介质半透明(能看穿,看见内部探针/馈电)──
_COL_METAL = "(184 115 51)"   # 金属材料(copper 等):铜色
_COL_PEC   = "(212 175 55)"   # PE 导体(贴片/地/馈片):金色,跟介质明显区分
_COL_VAC   = "(200 200 210)"  # 真空 sheet(端口面/未赋 PE 的片):中性灰
_COL_AIR   = "(200 225 255)"  # 开放空气盒:近透明蓝

# 介质调色板:多层板/多介质时要能一眼分开,所以**每种介质材料一个颜色**,
# 而不是所有介质共用一个绿。刻意避开铜色/金色(导体)和浅灰/浅蓝(真空/空气),彼此色相拉开。
_DIEL_PALETTE = [
    "(46 139 87)",    # 海绿
    "(65 105 225)",   # 宝蓝
    "(186 85 211)",   # 兰花紫
    "(0 139 139)",    # 深青
    "(205 92 92)",    # 印度红
    "(154 205 50)",   # 黄绿
    "(219 112 147)",  # 浅紫红
    "(72 209 204)",   # 绿松石
    "(128 128 0)",    # 橄榄
    "(123 104 238)",  # 板岩蓝
]
_COL_DIEL = _DIEL_PALETTE[0]  # 兼容旧引用;只有一种介质时外观与改动前一致

# 介质材料名 → 调色板下标。按**首次出现顺序**分配,同一材料在整个 server 进程里颜色固定
# (同一材料跨 design 也同色,便于对照);介质种类超过调色板长度后循环复用。
_diel_seen = {}


def _diel_color(m):
    idx = _diel_seen.setdefault(m, len(_diel_seen))
    return _DIEL_PALETTE[idx % len(_DIEL_PALETTE)]


def _color_for(material):
    """材料 → (颜色 '(r g b)', 透明度 0..1)。金属不透明、介质半透明且逐材料换色、真空中性。"""
    m = (material or "").strip().lower().strip('"')
    if m in _CONDUCTORS:
        return _COL_METAL, 0.0
    if m in ("vacuum", "air", ""):
        return _COL_VAC, 0.0
    return _diel_color(m), 0.6


def _recolor(oEditor, names, rgb, transp):
    """改对象颜色/透明度(纯外观,best-effort,失败不影响功能)。rgb='(r g b)'。"""
    try:
        r, g, b = (int(x) for x in str(rgb).strip("()").split())
        oEditor.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:Geometry3DAttributeTab",
              ["NAME:PropServers"] + [str(n) for n in names],
              ["NAME:ChangedProps",
               ["NAME:Color", "R:=", r, "G:=", g, "B:=", b],
               ["NAME:Transparent", "Value:=", float(transp)]]]])
    except Exception:
        pass


@tool({
    "type": "function",
    "function": {
        "name": "create_box",
        "description": ("创建长方体(轴对齐)。一角在 position,沿 +X/+Y/+Z 延伸 size。"
                        "坐标/尺寸为字符串,带单位或变量表达式(如 '10mm'、'L1+1mm')。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "对象名,唯一,英文数字下划线"},
                "position": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                             "description": "角点 [x,y,z],带单位"},
                "size": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                         "description": "沿 X/Y/Z 尺寸 [dx,dy,dz],带单位,可负"},
                "material": {"type": "string", "default": "vacuum", "description": "材料,如 'copper'、'FR4_epoxy'、'vacuum'"},
            },
            "required": ["name", "position", "size"],
        },
    },
})
def create_box(ctx, name, position, size, material="vacuum"):
    oEditor = ctx["oEditor"]
    px, py, pz = position
    sx, sy, sz = size
    try:
        oEditor.CreateBox(
            ["NAME:BoxParameters",
             "XPosition:=", px, "YPosition:=", py, "ZPosition:=", pz,
             "XSize:=", sx, "YSize:=", sy, "ZSize:=", sz],
            _attributes(name, material),
        )
    except Exception as e:
        return {"ok": False, "error": f"CreateBox 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "box", "material": material,
                                      "position": list(position), "size": list(size)}
    return {"ok": True, "name": name, "material": material}


@tool({
    "type": "function",
    "function": {
        "name": "list_objects",
        "description": "列出当前 design 里所有几何对象(实体 + 片)及其类别。",
        "parameters": {"type": "object", "properties": {}},
    },
})
def list_objects(ctx):
    oEditor = ctx["oEditor"]
    try:
        solids = [str(n) for n in (oEditor.GetObjectsInGroup("Solids") or []) if n]
        sheets = [str(n) for n in (oEditor.GetObjectsInGroup("Sheets") or []) if n]
    except Exception as e:
        return {"ok": False, "error": f"GetObjectsInGroup 失败: {type(e).__name__}: {e}"}
    objs = [{"name": n, "kind": "solid"} for n in solids] + [{"name": n, "kind": "sheet"} for n in sheets]
    return {"ok": True, "count": len(objs), "solids": solids, "sheets": sheets, "objects": objs}


def _bbox_of(oEditor, name):
    """单对象包围盒 {xmin,ymin,zmin,xmax,ymax,zmax}(模型单位,默认 mm)。
    优先 GetObjectBoundingBox(新版),老版(2019)用顶点兜底。取不到返回 None。"""
    try:
        bb = [float(x) for x in oEditor.GetObjectBoundingBox(name)]
        if len(bb) >= 6:
            return {"xmin": bb[0], "ymin": bb[1], "zmin": bb[2],
                    "xmax": bb[3], "ymax": bb[4], "zmax": bb[5]}
    except Exception:
        pass
    try:
        vids = oEditor.GetVertexIDsFromObject(name)
        pts = [[float(c) for c in oEditor.GetVertexPosition(v)] for v in (vids or [])]
        if not pts:
            return None
        xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
        return {"xmin": min(xs), "ymin": min(ys), "zmin": min(zs),
                "xmax": max(xs), "ymax": max(ys), "zmax": max(zs)}
    except Exception:
        return None


@tool({
    "type": "function",
    "function": {
        "name": "get_object_bbox",
        "description": ("取对象的轴向包围盒(xyz 最小/最大,模型单位默认 mm)——**求解前自检层叠/搭接的关键工具**。"
                        "不传 name 则返回所有对象的盒。用来核对:贴片底面 z == 基板顶面 z(不悬空)、"
                        "馈电面 z 跨满基板高度且 xy 落在导体之间(搭接)、地板/空气盒包住辐射体。"
                        "曲面体(球/圆柱)可能取不到顶点而返回 null,长方体/矩形片/多边形片都准。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "对象名;省略则返回全部对象的包围盒"},
            },
        },
    },
})
def get_object_bbox(ctx, name=None):
    oEditor = ctx["oEditor"]
    if name:
        bb = _bbox_of(oEditor, name)
        if bb is None:
            return {"ok": False, "error": f"取不到 '{name}' 的包围盒(对象不存在或为无顶点曲面体)"}
        return {"ok": True, "unit": "mm", "name": name, "bbox": bb}
    out = {}
    for n in _all_object_names(oEditor):
        out[n] = _bbox_of(oEditor, n)
    return {"ok": True, "unit": "mm", "count": len(out), "bboxes": out}


def _attributes(name, material):
    color, transp = _color_for(material)
    return ["NAME:Attributes", "Name:=", name, "Flags:=", "", "Color:=", color,
            "Transparency:=", float(transp), "PartCoordinateSystem:=", "Global",
            "MaterialValue:=", f'"{material}"', "SolveInside:=", _solve_inside(material)]


# 平面 → (法线轴, Width 取 size_u 还是 size_v, Height 取哪个)
# 实测 HFSS CreateRectangle WhichAxis 约定(Width/Height 各落哪条轴):
#   WhichAxis=Z(XY面): Width→X, Height→Y   → size_u(X)=Width, size_v(Y)=Height
#   WhichAxis=X(YZ面): Width→Y, Height→Z   → size_u(Y)=Width, size_v(Z)=Height
#   WhichAxis=Y(XZ面): Width→Z, Height→X   → size_u(X)=Height, size_v(Z)=Width  ←与直觉相反,要交换
_PLANE_AXIS = {"XY": "Z", "XZ": "Y", "YZ": "X"}
_PLANE_RECT = {  # (法线轴, Width 源, Height 源):让 size_u 始终落平面第一轴、size_v 落第二轴
    "XY": ("Z", "u", "v"),
    "YZ": ("X", "u", "v"),
    "XZ": ("Y", "v", "u"),  # XZ:Width 沿 Z 取 size_v,Height 沿 X 取 size_u
}


@tool({
    "type": "function",
    "function": {
        "name": "create_rectangle",
        "description": ("创建 2D 矩形片(sheet)。本身不是导体——要当导体调 assign_perfect_e;要当端口面给 create_lumped_port。"
                        "坐标/尺寸为字符串带单位。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "对象名"},
                "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"], "description": "所在平面"},
                "origin": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                           "description": "一角坐标 [x,y,z]"},
                "size_u": {"type": "string", "description": "沿平面第一轴长度(XY→X, XZ→X, YZ→Y)"},
                "size_v": {"type": "string", "description": "沿平面第二轴长度(XY→Y, XZ→Z, YZ→Z)"},
                "material": {"type": "string", "default": "vacuum", "description": "材料,默认 vacuum"},
            },
            "required": ["name", "plane", "origin", "size_u", "size_v"],
        },
    },
})
def create_rectangle(ctx, name, plane, origin, size_u, size_v, material="vacuum"):
    oEditor = ctx["oEditor"]
    spec = _PLANE_RECT.get(plane)
    if spec is None:
        return {"ok": False, "error": f"plane 必须是 XY/XZ/YZ,收到 {plane!r}"}
    axis, w_src, h_src = spec
    width = size_u if w_src == "u" else size_v   # 按实测 WhichAxis 约定把 size_u/size_v 落到正确轴
    height = size_u if h_src == "u" else size_v
    x, y, z = origin
    try:
        oEditor.CreateRectangle(
            ["NAME:RectangleParameters", "IsCovered:=", True,
             "XStart:=", x, "YStart:=", y, "ZStart:=", z,
             "Width:=", width, "Height:=", height, "WhichAxis:=", axis],
            _attributes(name, material),
        )
    except Exception as e:
        return {"ok": False, "error": f"CreateRectangle 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "rectangle", "plane": plane, "material": material}
    return {"ok": True, "name": name, "plane": plane}


@tool({
    "type": "function",
    "function": {
        "name": "create_cylinder",
        "description": "创建圆柱。沿 orientation 轴,底面圆心在 origin,半径 radius,高 height。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "对象名"},
                "orientation": {"type": "string", "enum": ["X", "Y", "Z"], "description": "轴向"},
                "origin": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                           "description": "底面圆心 [x,y,z]"},
                "radius": {"type": "string", "description": "半径,带单位"},
                "height": {"type": "string", "description": "高,带单位"},
                "material": {"type": "string", "default": "vacuum", "description": "材料,默认 vacuum"},
            },
            "required": ["name", "orientation", "origin", "radius", "height"],
        },
    },
})
def create_cylinder(ctx, name, orientation, origin, radius, height, material="vacuum"):
    oEditor = ctx["oEditor"]
    x, y, z = origin
    try:
        oEditor.CreateCylinder(
            ["NAME:CylinderParameters",
             "XCenter:=", x, "YCenter:=", y, "ZCenter:=", z,
             "Radius:=", radius, "Height:=", height,
             "WhichAxis:=", orientation, "NumSides:=", "0"],
            _attributes(name, material),
        )
    except Exception as e:
        return {"ok": False, "error": f"CreateCylinder 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "cylinder", "material": material}
    return {"ok": True, "name": name}


@tool({
    "type": "function",
    "function": {
        "name": "create_sphere",
        "description": "创建球。圆心 center,半径 radius。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "center": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                           "description": "球心 [x,y,z]"},
                "radius": {"type": "string", "description": "半径,带单位"},
                "material": {"type": "string", "default": "vacuum"},
            },
            "required": ["name", "center", "radius"],
        },
    },
})
def create_sphere(ctx, name, center, radius, material="vacuum"):
    oEditor = ctx["oEditor"]
    cx, cy, cz = center
    try:
        oEditor.CreateSphere(
            ["NAME:SphereParameters", "XCenter:=", cx, "YCenter:=", cy, "ZCenter:=", cz, "Radius:=", radius],
            _attributes(name, material))
    except Exception as e:
        return {"ok": False, "error": f"CreateSphere 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "sphere", "material": material}
    return {"ok": True, "name": name}


@tool({
    "type": "function",
    "function": {
        "name": "create_polyline",
        "description": ("创建折线/多边形。points 是顶点列表 [[x,y,z],...](带单位)。"
                        "close_surface=True 闭合,cover_surface=True 覆面成 sheet(用于不规则贴片/缝隙等)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "points": {"type": "array",
                           "items": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                           "minItems": 2, "description": "顶点列表,每点 [x,y,z] 带单位"},
                "close_surface": {"type": "boolean", "default": True, "description": "是否闭合"},
                "cover_surface": {"type": "boolean", "default": True, "description": "是否覆面成 sheet"},
                "material": {"type": "string", "default": "vacuum"},
            },
            "required": ["name", "points"],
        },
    },
})
def create_polyline(ctx, name, points, close_surface=True, cover_surface=True, material="vacuum"):
    oEditor = ctx["oEditor"]
    n = len(points)
    pts_arg = ["NAME:PolylinePoints"]
    for p in points:
        pts_arg.append(["NAME:PLPoint", "X:=", p[0], "Y:=", p[1], "Z:=", p[2]])
    # 闭合时补一个回到起点的点(HFSS 习惯:闭合 polyline 末点=首点)
    if close_surface:
        p0 = points[0]
        pts_arg.append(["NAME:PLPoint", "X:=", p0[0], "Y:=", p0[1], "Z:=", p0[2]])
    seg_count = (n if close_surface else n - 1)
    segs_arg = ["NAME:PolylineSegments"]
    for i in range(seg_count):
        segs_arg.append(["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2])
    try:
        oEditor.CreatePolyline(
            ["NAME:PolylineParameters",
             "IsPolylineCovered:=", bool(cover_surface),
             "IsPolylineClosed:=", bool(close_surface),
             pts_arg, segs_arg,
             ["NAME:PolylineXSection", "XSectionType:=", "None", "XSectionOrient:=", "Auto",
              "XSectionWidth:=", "0mm", "XSectionTopWidth:=", "0mm", "XSectionHeight:=", "0mm",
              "XSectionNumSegments:=", "0", "XSectionBendType:=", "Corner"]],
            _attributes(name, material))
    except Exception as e:
        return {"ok": False, "error": f"CreatePolyline 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "polyline", "material": material, "covered": bool(cover_surface)}
    return {"ok": True, "name": name}


@tool({
    "type": "function",
    "function": {
        "name": "delete_object",
        "description": "删除一个或多个几何对象。",
        "parameters": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "要删的对象名列表"},
            },
            "required": ["names"],
        },
    },
})
def delete_object(ctx, names):
    oEditor = ctx["oEditor"]
    existing = set(_all_object_names(oEditor))
    present = [n for n in names if n in existing]
    missing = [n for n in names if n not in existing]
    if present:
        try:
            oEditor.Delete(["NAME:Selections", "Selections:=", ",".join(present)])
        except Exception as e:
            return {"ok": False, "error": f"Delete 失败: {type(e).__name__}: {e}"}
        if "state" in ctx:
            for n in present:
                ctx["state"].objects.pop(n, None)
    return {"ok": True, "deleted": present, "missing": missing}


@tool({
    "type": "function",
    "function": {
        "name": "assign_material",
        "description": ("给已建的**实体**改/赋材料(走 ChangeProperty)。介质基板务必赋(否则真空)。"
                        "sheet 导体面用 assign_perfect_e,不要用这个。"),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "实体名列表"},
                "material": {"type": "string", "description": "材料名,如 'FR4_epoxy'、'copper'"},
                "solve_inside": {"type": "boolean", "description": "是否求解内部场;不传则按材料自动(导体 False,其余 True)"},
            },
            "required": ["objects", "material"],
        },
    },
})
def assign_material(ctx, objects, material, solve_inside=None):
    oEditor = ctx["oEditor"]
    si = _solve_inside(material) if solve_inside is None else bool(solve_inside)
    try:
        oEditor.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:Geometry3DAttributeTab",
              ["NAME:PropServers", *objects],
              ["NAME:ChangedProps",
               ["NAME:Material", "Value:=", f'"{material}"'],
               ["NAME:Solve Inside", "Value:=", si]]]])
    except Exception as e:
        return {"ok": False, "error": f"ChangeProperty(Material) 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        for n in objects:
            ctx["state"].objects.setdefault(n, {})["material"] = material
    return {"ok": True, "objects": list(objects), "material": material, "solve_inside": si}


@tool({
    "type": "function",
    "function": {
        "name": "create_material",
        "description": ("自定义材料(精确 εr / 损耗角正切等),用于精确复现论文基板——库里现成材料(如 FR4_epoxy εr≈4.4)"
                        "常和论文标的值(如 εr=4.2)对不上,会导致谐振频率偏。建完用对象的 material 参数引用此名,"
                        "或对已建实体 assign_material。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "材料名,如 'Sub_er4p2'"},
                "permittivity": {"type": "number", "description": "相对介电常数 εr,如 4.2"},
                "loss_tangent": {"type": "number", "default": 0, "description": "介质损耗角正切 tanδ,如 0.019"},
                "permeability": {"type": "number", "default": 1, "description": "相对磁导率 μr,默认 1"},
                "conductivity": {"type": "number", "default": 0, "description": "电导率 S/m,默认 0(理想介质)"},
            },
            "required": ["name", "permittivity"],
        },
    },
})
def create_material(ctx, name, permittivity, loss_tangent=0, permeability=1, conductivity=0):
    oProject = ctx.get("oProject")
    if oProject is None:
        return {"ok": False, "error": "无 active project"}
    mat = ["NAME:" + name,
           "CoordinateSystemType:=", "Cartesian", "BulkOrSurfaceType:=", 1,
           ["NAME:PhysicsTypes", "set:=", ["Electromagnetic"]],
           "permittivity:=", str(permittivity),
           "dielectric_loss_tangent:=", str(loss_tangent),
           "permeability:=", str(permeability)]
    if conductivity:
        mat += ["conductivity:=", str(conductivity)]
    try:
        oProject.GetDefinitionManager().AddMaterial(mat)
    except Exception as e:
        return {"ok": False, "error": f"AddMaterial 失败(同名材料已存在?): {type(e).__name__}: {e}"}
    if "state" in ctx:
        if not hasattr(ctx["state"], "materials"):
            ctx["state"].materials = {}
        ctx["state"].materials[name] = {"permittivity": permittivity, "loss_tangent": loss_tangent}
    return {"ok": True, "name": name, "permittivity": permittivity, "loss_tangent": loss_tangent,
            "hint": f"建几何时 material='{name}' 引用,或 assign_material 给已建实体"}


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


# ─────────────────────────────────────────────────────────
# create_helix —— 轮廓绕轴扫成螺旋(oEditor.CreateHelix 直通)
# 参数格式对照 PyAEDT modeler.create_helix(primitives_3d.py)核实
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "create_helix",
        "description": (
            "把一个轮廓对象绕轴扫成螺旋:1D 线 → 螺旋面(sheet),2D 面 → 螺旋实体。"
            "轮廓对象被原地替换,结果保留原名(材料/后续赋 PE 照常)。"
            "轴 = center(轴上一点)+ axis_dir(方向向量);pitch = 每圈沿轴前进的距离;turns = 圈数(可小数)。"
            "所有长度与圈数都可用设计变量表达式 → 螺旋结构可直接参扫/优化。"
            "四臂螺旋/螺旋带:在圆柱面上(如 x=r0 处)画一条竖直短线作轮廓(create_polyline,"
            "close_surface=False, cover_surface=False),扫一次得到恒定带宽的真螺旋面,"
            "再 duplicate_around_axis 出多臂。端头需要水平时用 split 按 XY 平面切。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "profile": {"type": "string",
                            "description": "被扫的轮廓对象名(线或面),会被原地变成螺旋"},
                "center": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                           "default": ["0mm", "0mm", "0mm"],
                           "description": "螺旋轴上一点 [x,y,z],带单位或变量"},
                "axis_dir": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                             "default": ["0mm", "0mm", "1mm"],
                             "description": "螺旋轴方向向量 [dx,dy,dz],带单位,如 +Z 轴 ['0mm','0mm','1mm']"},
                "pitch": {"type": "string",
                          "description": "螺距:每圈沿轴前进的距离,带单位或表达式,如 'H/N'"},
                "turns": {"type": "string",
                          "description": "圈数,可小数或变量,如 '0.6034' 或 'N'"},
                "right_hand": {"type": "boolean", "default": True,
                               "description": "右手螺旋(沿 axis_dir 看逆时针上升)。左旋圆极化常需 False,以实测轴比/极化为准"},
                "radius_increment": {"type": "string", "default": "0mm",
                                     "description": "每圈半径增量,圆柱螺旋填 '0mm',锥形螺旋填正/负值"},
            },
            "required": ["profile", "pitch", "turns"],
        },
    },
})
def create_helix(ctx, profile, pitch, turns, center=None, axis_dir=None,
                 right_hand=True, radius_increment="0mm"):
    oEditor = ctx["oEditor"]
    cx, cy, cz = center or ["0mm", "0mm", "0mm"]
    dx, dy, dz = axis_dir or ["0mm", "0mm", "1mm"]
    try:
        oEditor.CreateHelix(
            ["NAME:Selections", "Selections:=", profile, "NewPartsModelFlag:=", "Model"],
            ["NAME:HelixParameters",
             "XCenter:=", str(cx), "YCenter:=", str(cy), "ZCenter:=", str(cz),
             "XStartDir:=", str(dx), "YStartDir:=", str(dy), "ZStartDir:=", str(dz),
             "NumThread:=", str(turns),
             "RightHand:=", bool(right_hand),
             "RadiusIncrement:=", str(radius_increment),
             "Thread:=", str(pitch)],
        )
    except Exception as e:
        return {"ok": False, "error": f"CreateHelix 失败: {type(e).__name__}: {e}",
                "hint": "轮廓须是已存在的线/面对象;轮廓不能与螺旋轴相交(扫出来自交会失败)"}
    if "state" in ctx:
        ctx["state"].objects.setdefault(profile, {})["type"] = "helix"
    return {"ok": True, "name": profile, "pitch": pitch, "turns": turns,
            "right_hand": bool(right_hand)}


# 常用色名 → RGB,省得记数值。自动配色够用时不必调本工具。
_NAMED_COLORS = {
    "red": "(220 20 60)", "green": "(46 139 87)", "blue": "(65 105 225)",
    "purple": "(186 85 211)", "teal": "(0 139 139)", "cyan": "(72 209 204)",
    "yellow": "(218 190 60)", "orange": "(230 140 40)", "pink": "(219 112 147)",
    "olive": "(128 128 0)", "gray": "(160 160 170)", "grey": "(160 160 170)",
    "white": "(240 240 245)", "black": "(40 40 45)",
    "copper": _COL_METAL, "gold": _COL_PEC,
}


def _parse_color(c):
    """接受 '(r g b)' / 'r,g,b' / 'r g b' / 色名 → '(r g b)';认不出返回 None。"""
    s = str(c).strip()
    named = _NAMED_COLORS.get(s.lower())
    if named:
        return named
    parts = [p for p in s.strip("()").replace(",", " ").split() if p]
    if len(parts) != 3:
        return None
    try:
        rgb = [max(0, min(255, int(float(p)))) for p in parts]
    except ValueError:
        return None
    return "({} {} {})".format(*rgb)


@tool({
    "type": "function",
    "function": {
        "name": "set_object_color",
        "description": ("手动改对象的颜色/透明度(纯外观,不影响求解)。建模时已按材料自动配色"
                        "(导体铜/金色、每种介质一个颜色、空气近透明),**一般不需要调本工具**;"
                        "用在:自动色不合心意、或想把某个件临时高亮出来看清层叠关系。"
                        "不传 names 则返回当前介质材料→颜色的分配表,不改任何东西。"),
        "parameters": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"},
                          "description": "对象名列表;省略则只回查分配表"},
                "color": {"type": "string",
                          "description": "'(r g b)' / 'r,g,b' / 色名(red/green/blue/purple/teal/cyan/"
                                         "yellow/orange/pink/olive/gray/white/black/copper/gold)"},
                "transparency": {"type": "number",
                                 "description": "0=不透明,1=全透明;介质建议 0.6,空气盒 0.9。省略则不改透明度"},
            },
        },
    },
})
def set_object_color(ctx, names=None, color=None, transparency=None):
    palette = {m: _DIEL_PALETTE[i % len(_DIEL_PALETTE)] for m, i in _diel_seen.items()}
    if not names:
        return {"ok": True, "dielectric_palette": palette,
                "named_colors": sorted(_NAMED_COLORS),
                "hint": "传 names + color 才会改色"}
    if color is None and transparency is None:
        return {"ok": False, "error": "color 和 transparency 至少给一个"}
    oEditor = ctx["oEditor"]
    existing = set(_all_object_names(oEditor))
    missing = [n for n in names if n not in existing]
    if missing:
        return {"ok": False, "error": f"对象不存在: {missing}"}

    props = []
    rgb = None
    if color is not None:
        rgb = _parse_color(color)
        if rgb is None:
            return {"ok": False, "error": f"认不出颜色 '{color}'",
                    "hint": "用 '(r g b)'、'r,g,b' 或色名"}
        r, g, b = (int(x) for x in rgb.strip("()").split())
        props.append(["NAME:Color", "R:=", r, "G:=", g, "B:=", b])
    if transparency is not None:
        props.append(["NAME:Transparent", "Value:=", float(transparency)])

    try:
        oEditor.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:Geometry3DAttributeTab",
              ["NAME:PropServers"] + [str(n) for n in names],
              ["NAME:ChangedProps"] + props]])
    except Exception as e:
        return {"ok": False, "error": f"ChangeProperty 失败: {type(e).__name__}: {e}"}
    return {"ok": True, "names": list(names), "color": rgb,
            "transparency": transparency, "dielectric_palette": palette}


# ─────────────────────────────────────────────────────────
# thicken —— sheet 原地加厚成实体(oEditor.ThickenSheet 直通)
# 不规则截面(多边形基板、异形结构)才用;规则长方体直接 create_box 更省事
# ─────────────────────────────────────────────────────────

@tool({
    "type": "function",
    "function": {
        "name": "thicken",
        "description": (
            "把 sheet **原地**加厚成 3D 实体(介质基板、金属块、墙体等),结果保留原对象名。"
            "加厚方向 = sheet 法线;`both_sides=True` 则以 sheet 为中面向两侧各加厚 thickness。"
            "厚度可用设计变量表达式(如 'subH')→ 加厚后的实体能直接参扫。"
            "**规则长方体基板直接 create_box 更省事**,只有不规则截面(多边形、异形轮廓)才走"
            "「create_polyline 画 sheet → thicken」。"
            "**零厚度辐射金属面(贴片/振子/地板)不要 thicken**——用 assign_perfect_e,网格轻得多。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                            "description": "要加厚的 sheet 对象名(可多个,一次同厚度加厚)"},
                "thickness": {"type": "string",
                              "description": "加厚量,带单位或变量表达式(如 '1.6mm'/'subH');负值沿法线反向"},
                "both_sides": {"type": "boolean", "default": False,
                               "description": "True=以 sheet 为中面双向各加厚 thickness(总厚 2×)"},
                "material": {"type": "string",
                             "description": "可选:加厚后顺手赋材料(如 'FR4_epoxy'),不传保持原材料"},
            },
            "required": ["objects", "thickness"],
        },
    },
})
def thicken(ctx, objects, thickness, both_sides=False, material=None):
    oEditor = ctx["oEditor"]
    try:
        oEditor.ThickenSheet(
            ["NAME:Selections", "Selections:=", ",".join(objects), "NewPartsModelFlag:=", "Model"],
            ["NAME:SheetThickenParameters", "Thickness:=", str(thickness),
             "BothSides:=", bool(both_sides)])
    except Exception as e:
        return {"ok": False, "error": f"ThickenSheet 失败: {type(e).__name__}: {e}",
                "hint": "对象必须是 sheet(已是实体会失败);法线方向自交/穿模也会失败"}
    if "state" in ctx:
        for n in objects:
            ctx["state"].objects.setdefault(n, {})["type"] = "solid"
    out = {"ok": True, "objects": list(objects), "thickness": thickness,
           "both_sides": bool(both_sides)}
    if material:
        r = assign_material(ctx, objects, material)
        out["material"] = material
        if not r.get("ok"):
            out["material_warning"] = r.get("error")
    return out
