"""边界(native COM 版)—— oDesign.GetModule("BoundarySetup") 直通。"""

from . import tool
from .geometry import _attributes, _recolor, _COL_PEC, _COL_METAL, _COL_AIR


@tool({
    "type": "function",
    "function": {
        "name": "assign_perfect_e",
        "description": ("在 sheet 上赋 Perfect E(理想电导体)。贴片、地板、馈电片等导体面都要这步。"
                        "端口 sheet 不要赋 PE(会让端口失效)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "边界名,如 'PE_patch'"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "要赋 PE 的 sheet 名列表"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_perfect_e(ctx, name, objects):
    oDesign = ctx["oDesign"]
    try:
        oModule = oDesign.GetModule("BoundarySetup")
        oModule.AssignPerfectE(["NAME:" + name, "Objects:=", list(objects), "InfGroundPlane:=", False])
    except Exception as e:
        return {"ok": False, "error": f"AssignPerfectE 失败: {type(e).__name__}: {e}"}
    _recolor(ctx["oEditor"], objects, _COL_PEC, 0.0)   # 导体面上金色,跟介质/真空区分
    if "state" in ctx:
        ctx["state"].boundaries[name] = {"type": "PerfectE", "objects": list(objects)}
    return {"ok": True, "name": name, "objects": list(objects)}


def _freq_to_hz(s):
    s = str(s).strip().lower().replace(" ", "")
    mult = 1.0
    for suf, m in (("ghz", 1e9), ("mhz", 1e6), ("khz", 1e3), ("hz", 1.0)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * m
    return float(s) * 1e9  # 裸数字当 GHz


@tool({
    "type": "function",
    "function": {
        "name": "create_open_region",
        "description": ("为天线仿真建开放空间:在模型外约 quarter-wave 处建真空空气盒,并给其外表面赋辐射边界。"
                        "天线类仿真求解前必须调一次(否则没有辐射、远场)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "frequency": {"type": "string", "description": "工作频率,带单位(如 '2.4GHz'),决定空气盒留白"},
                "name": {"type": "string", "default": "airbox", "description": "空气盒对象名"},
            },
            "required": ["frequency"],
        },
    },
})
def create_open_region(ctx, frequency, name="airbox"):
    oEditor = ctx["oEditor"]
    oDesign = ctx["oDesign"]
    # quarter-wave 留白(mm),按模型单位 mm 处理
    pad_mm = (299792458.0 / _freq_to_hz(frequency)) / 4.0 * 1000.0
    try:
        bb = [float(v) for v in oEditor.GetModelBoundingBox()]
    except Exception as e:
        return {"ok": False, "error": f"取模型 bbox 失败: {type(e).__name__}: {e}"}
    xmin, ymin, zmin, xmax, ymax, zmax = bb[:6]
    pos = [f"{xmin - pad_mm}mm", f"{ymin - pad_mm}mm", f"{zmin - pad_mm}mm"]
    size = [f"{(xmax - xmin) + 2 * pad_mm}mm", f"{(ymax - ymin) + 2 * pad_mm}mm", f"{(zmax - zmin) + 2 * pad_mm}mm"]
    try:
        oEditor.CreateBox(
            ["NAME:BoxParameters", "XPosition:=", pos[0], "YPosition:=", pos[1], "ZPosition:=", pos[2],
             "XSize:=", size[0], "YSize:=", size[1], "ZSize:=", size[2]],
            _attributes(name, "vacuum"))
        face_ids = [int(f) for f in oEditor.GetFaceIDs(name)]
        oModule = oDesign.GetModule("BoundarySetup")
        oModule.AssignRadiation(
            ["NAME:Rad1", "Faces:=", face_ids,
             "IsFssReference:=", False, "IsForPML:=", False])
    except Exception as e:
        return {"ok": False, "error": f"建空气盒/赋辐射边界失败: {type(e).__name__}: {e}"}
    _recolor(oEditor, [name], _COL_AIR, 0.9)   # 空气盒近透明,不挡住内部结构
    if "state" in ctx:
        ctx["state"].objects[name] = {"type": "open_region", "material": "vacuum"}
        ctx["state"].boundaries["Rad1"] = {"type": "Radiation", "frequency": frequency}
    return {"ok": True, "airbox": name, "boundary": "Rad1", "pad_mm": round(pad_mm, 3)}


def _bnd(ctx):
    return ctx["oDesign"].GetModule("BoundarySetup")


@tool({
    "type": "function",
    "function": {
        "name": "assign_perfect_h",
        "description": "在 sheet 上赋 Perfect H(理想磁壁/PMC)。用于对称面磁壁、磁导体边界等。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "边界名"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "sheet 名列表"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_perfect_h(ctx, name, objects):
    try:
        _bnd(ctx).AssignPerfectH(["NAME:" + name, "Objects:=", list(objects), "InfGroundPlane:=", False])
    except Exception as e:
        return {"ok": False, "error": f"AssignPerfectH 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].boundaries[name] = {"type": "PerfectH", "objects": list(objects)}
    return {"ok": True, "name": name, "objects": list(objects)}


@tool({
    "type": "function",
    "function": {
        "name": "assign_finite_conductivity",
        "description": ("在 sheet 上赋有限电导率边界(真实金属损耗)。要算效率/Q/插损时用它替代 Perfect E。"
                        "传 material(如 'copper')或 conductivity(S/m)其一。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "material": {"type": "string", "description": "材料名,如 'copper'(取其电导率)"},
                "conductivity": {"type": "number", "description": "电导率 S/m(不传 material 时用)"},
                "roughness": {"type": "string", "default": "0um", "description": "表面粗糙度,默认 '0um'"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_finite_conductivity(ctx, name, objects, material=None, conductivity=None, roughness="0um"):
    if not material and conductivity is None:
        return {"ok": False, "error": "必须传 material 或 conductivity 之一"}
    args = ["NAME:" + name, "Objects:=", list(objects)]
    if material:
        args += ["UseMaterial:=", True, "Material:=", material]
    else:
        args += ["UseMaterial:=", False, "Conductivity:=", str(conductivity), "Permeability:=", "1"]
    args += ["UseThickness:=", False, "Roughness:=", roughness,
             "InfGroundPlane:=", False, "IsTwoSided:=", False, "IsInternal:=", True]
    try:
        _bnd(ctx).AssignFiniteCond(args)
    except Exception as e:
        return {"ok": False, "error": f"AssignFiniteCond 失败: {type(e).__name__}: {e}"}
    _recolor(ctx["oEditor"], objects, _COL_METAL, 0.0)   # 真实金属面上铜色
    if "state" in ctx:
        ctx["state"].boundaries[name] = {"type": "FiniteCond", "objects": list(objects),
                                         "material": material, "conductivity": conductivity}
    return {"ok": True, "name": name, "objects": list(objects), "material": material, "conductivity": conductivity}


@tool({
    "type": "function",
    "function": {
        "name": "assign_impedance",
        "description": "在 sheet 上赋各向同性阻抗边界(R+jX 欧姆)。用于薄电阻片、吸波等效表面阻抗。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "objects": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "resistance": {"type": "number", "default": 50, "description": "电阻 Ω,默认 50"},
                "reactance": {"type": "number", "default": 0, "description": "电抗 Ω,默认 0"},
            },
            "required": ["name", "objects"],
        },
    },
})
def assign_impedance(ctx, name, objects, resistance=50, reactance=0):
    try:
        _bnd(ctx).AssignImpedance(
            ["NAME:" + name, "Objects:=", list(objects),
             "Resistance:=", str(resistance), "Reactance:=", str(reactance), "InfGroundPlane:=", False])
    except Exception as e:
        return {"ok": False, "error": f"AssignImpedance 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].boundaries[name] = {"type": "Impedance", "objects": list(objects),
                                         "resistance": resistance, "reactance": reactance}
    return {"ok": True, "name": name, "objects": list(objects), "resistance": resistance, "reactance": reactance}


@tool({
    "type": "function",
    "function": {
        "name": "assign_lumped_rlc",
        "description": ("在 sheet 上赋集总 RLC 边界(并联/串联 R/L/C 负载)。R/L/C 至少给一个。"
                        "需显式电流方向线 current_start→current_end(沿 RLC 电流方向,落在 sheet 两条对边上)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sheet": {"type": "string", "description": "单个 sheet 对象名"},
                "current_start": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                                  "description": "电流线起点 [x,y,z]。**用字面量坐标带单位(如 '1.6mm'),不要用变量名/表达式**"},
                "current_end": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                                "description": "电流线终点 [x,y,z],同样字面量带单位"},
                "rlc_type": {"type": "string", "enum": ["Parallel", "Serial"], "default": "Parallel"},
                "resistance": {"type": "number", "description": "电阻 Ω,可选"},
                "inductance": {"type": "number", "description": "电感 H,可选(1e-9=1nH)"},
                "capacitance": {"type": "number", "description": "电容 F,可选(1e-12=1pF)"},
            },
            "required": ["name", "sheet", "current_start", "current_end"],
        },
    },
})
def assign_lumped_rlc(ctx, name, sheet, current_start, current_end, rlc_type="Parallel",
                      resistance=None, inductance=None, capacitance=None):
    if resistance is None and inductance is None and capacitance is None:
        return {"ok": False, "error": "R/L/C 至少给一个"}
    args = ["NAME:" + name, "Objects:=", [sheet],
            ["NAME:CurrentLine", "Start:=", list(current_start), "End:=", list(current_end)],
            "RLC Type:=", rlc_type,
            "UseResist:=", resistance is not None, "Resistance:=", f"{resistance}ohm" if resistance is not None else "0ohm",
            "UseInduct:=", inductance is not None, "Inductance:=", f"{inductance}H" if inductance is not None else "0H",
            "UseCap:=", capacitance is not None, "Capacitance:=", f"{capacitance}F" if capacitance is not None else "0F"]
    try:
        _bnd(ctx).AssignLumpedRLC(args)
    except Exception as e:
        return {"ok": False, "error": f"AssignLumpedRLC 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].boundaries[name] = {"type": "LumpedRLC", "sheet": sheet, "rlc_type": rlc_type,
                                         "R": resistance, "L": inductance, "C": capacitance}
    return {"ok": True, "name": name, "sheet": sheet, "rlc_type": rlc_type,
            "R": resistance, "L": inductance, "C": capacitance}


@tool({
    "type": "function",
    "function": {
        "name": "create_infinite_sphere",
        "description": ("建远场观察球(Infinite Sphere),求解后从它取增益/方向图/轴比。"
                        "和 create_open_region 配套;远场分析必须先建一个。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "Sphere1"},
                "theta_start": {"type": "string", "default": "0deg"}, "theta_stop": {"type": "string", "default": "180deg"},
                "theta_step": {"type": "string", "default": "2deg"},
                "phi_start": {"type": "string", "default": "0deg"}, "phi_stop": {"type": "string", "default": "360deg"},
                "phi_step": {"type": "string", "default": "5deg"},
            },
        },
    },
})
def create_infinite_sphere(ctx, name="Sphere1", theta_start="0deg", theta_stop="180deg", theta_step="2deg",
                           phi_start="0deg", phi_stop="360deg", phi_step="5deg"):
    oModule = ctx["oDesign"].GetModule("RadField")
    args = ["NAME:" + name, "UseCustomRadiationSurface:=", False,
            "CSDefinition:=", "Theta-Phi", "Polarization:=", "Linear",
            "ThetaStart:=", theta_start, "ThetaStop:=", theta_stop, "ThetaStep:=", theta_step,
            "PhiStart:=", phi_start, "PhiStop:=", phi_stop, "PhiStep:=", phi_step,
            "UseLocalCS:=", False]
    # 方法名跨版本不同:新版 InsertInfiniteSphereSetup,老版(2019)InsertFarFieldSphereSetup。都试。
    last = None
    for meth in ("InsertInfiniteSphereSetup", "InsertFarFieldSphereSetup"):
        try:
            getattr(oModule, meth)(args)
            last = None
            break
        except Exception as e:
            last = f"{meth}: {type(e).__name__}: {e}"
    if last:
        return {"ok": False, "error": f"插入远场球失败({last})"}
    if "state" in ctx:
        ctx["state"].boundaries[f"InfSphere_{name}"] = {"type": "InfiniteSphere", "name": name}
    return {"ok": True, "name": name,
            "theta": [theta_start, theta_stop, theta_step], "phi": [phi_start, phi_stop, phi_step]}
