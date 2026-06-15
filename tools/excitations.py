"""激励/端口(native COM 版)—— AssignLumpedPort 直通 + 边缘/同轴馈电一步编排。

Driven Modal lumped port 用显式积分线。积分线坐标可传变量名(如 'subH')或字面量,
工具内部会把变量解析成字面量(老版本积分线直接放变量名会崩);复杂表达式解析不了拿不准就写字面量数值。
"""

from . import tool
from .geometry import _attributes, _all_object_names


def _assign_lumped(oDesign, name, sheet, int_start, int_end, impedance):
    """实际调 AssignLumpedPort(Driven Modal,显式积分线)。返回 (ok, err)。
    积分线坐标先解析变量→字面量(老版本积分线放变量名会崩),让上层能放心传 'subH'。"""
    zstr = f"{impedance}ohm"
    int_start = _resolve_pt(oDesign, int_start)
    int_end = _resolve_pt(oDesign, int_end)
    try:
        oDesign.GetModule("BoundarySetup").AssignLumpedPort(
            ["NAME:" + name, "Objects:=", [sheet], "DoDeembed:=", False, "RenormalizeAllTerminals:=", True,
             ["NAME:Modes",
              ["NAME:Mode1", "ModeNum:=", 1, "UseIntLine:=", True,
               ["NAME:IntLine", "Start:=", list(int_start), "End:=", list(int_end)],
               "AlignmentGroup:=", 0, "CharImp:=", "Zpi", "RenormImp:=", zstr]],
             "ShowReporterFilter:=", False, "ReporterFilter:=", [True], "Impedance:=", zstr])
        return True, None
    except Exception as e:
        return False, f"AssignLumpedPort 失败: {type(e).__name__}: {e}"


@tool({
    "type": "function",
    "function": {
        "name": "create_lumped_port",
        "description": ("在已建好的 sheet 上建集中端口(Lumped Port,Driven Modal)。"
                        "需显式给积分线两端 int_start→int_end(从参考导体指向激励侧,落在 sheet 两条对边上)。"
                        "**端口 sheet 不要赋 PE**。自定义形状端口用这个;矩形侧馈用 create_edge_feed_port,同轴探针用 create_coax_feed_port。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "端口名,如 'P1'"},
                "sheet": {"type": "string", "description": "端口 sheet 对象名"},
                "int_start": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                              "description": "积分线起点 [x,y,z]。可用变量名(如 'subH')或字面量带单位;工具自动解析变量。复杂表达式拿不准就写字面量"},
                "int_end": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
                            "description": "积分线终点 [x,y,z],同样可用变量名或字面量"},
                "impedance": {"type": "number", "default": 50, "description": "归一化阻抗(欧姆),默认 50"},
            },
            "required": ["name", "sheet", "int_start", "int_end"],
        },
    },
})
def create_lumped_port(ctx, name, sheet, int_start, int_end, impedance=50):
    ok, err = _assign_lumped(ctx["oDesign"], name, sheet, int_start, int_end, impedance)
    if not ok:
        return {"ok": False, "error": err}
    if "state" in ctx:
        ctx["state"].excitations[name] = {"type": "LumpedPort", "sheet": sheet, "impedance": impedance,
                                          "int_line": [list(int_start), list(int_end)]}
    return {"ok": True, "name": name, "sheet": sheet, "impedance": impedance}


@tool({
    "type": "function",
    "function": {
        "name": "create_edge_feed_port",
        "description": ("边缘/侧馈端口一步搞定:在 (feed_x,feed_y) 处建一个从 z_bottom 到 z_top 的竖直矩形 sheet,"
                        "再赋 lumped port(积分线沿 +Z)。你不用手动建 sheet。"
                        "feed_x/feed_y/z_bottom/z_top 可用变量名(如 'subH')或字面量带单位,工具自动把变量解析成字面量喂积分线;复杂表达式拿不准就写字面量数值。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "端口名,如 'P1'"},
                "feed_x": {"type": "string", "description": "端口中心 X(变量名或字面量)"},
                "feed_y": {"type": "string", "description": "端口中心 Y(变量名或字面量)"},
                "z_bottom": {"type": "string", "description": "底部 Z(gnd 平面,变量名或字面量,如 '0mm')"},
                "z_top": {"type": "string", "description": "顶部 Z(patch 平面,变量名或字面量,如 'subH'/'1.6mm')"},
                "feed_width": {"type": "string", "default": "1mm", "description": "端口 sheet 宽度"},
                "plane": {"type": "string", "enum": ["XZ", "YZ"], "default": "XZ",
                          "description": "sheet 平面:XZ=沿 X 馈电,YZ=沿 Y 馈电"},
                "impedance": {"type": "number", "default": 50},
            },
            "required": ["name", "feed_x", "feed_y", "z_bottom", "z_top"],
        },
    },
})
def create_edge_feed_port(ctx, name, feed_x, feed_y, z_bottom, z_top, feed_width="1mm", plane="XZ", impedance=50):
    oEditor = ctx["oEditor"]
    sheet = f"{name}_sheet"
    height = f"({z_top})-({z_bottom})"
    # 实测 WhichAxis 约定:Y(XZ面) Width→Z/Height→X;X(YZ面) Width→Y/Height→Z。
    if plane == "XZ":   # 法线 Y,沿 X 宽 feed_width,沿 Z 高 → Width=height(Z), Height=feed_width(X)
        origin = [f"({feed_x})-({feed_width})/2", feed_y, z_bottom]; axis = "Y"
        width_val, height_val = height, feed_width
    else:               # YZ:法线 X,沿 Y 宽 feed_width,沿 Z 高 → Width=feed_width(Y), Height=height(Z)
        origin = [feed_x, f"({feed_y})-({feed_width})/2", z_bottom]; axis = "X"
        width_val, height_val = feed_width, height
    try:
        oEditor.CreateRectangle(
            ["NAME:RectangleParameters", "IsCovered:=", True,
             "XStart:=", origin[0], "YStart:=", origin[1], "ZStart:=", origin[2],
             "Width:=", width_val, "Height:=", height_val, "WhichAxis:=", axis],
            _attributes(sheet, "vacuum"))
    except Exception as e:
        return {"ok": False, "error": f"建端口 sheet 失败: {type(e).__name__}: {e}"}
    ok, err = _assign_lumped(ctx["oDesign"], name, sheet,
                             [feed_x, feed_y, z_bottom], [feed_x, feed_y, z_top], impedance)
    if not ok:
        return {"ok": False, "error": err}
    if "state" in ctx:
        ctx["state"].objects[sheet] = {"type": "rectangle", "role": "edge_feed_port_sheet"}
        ctx["state"].excitations[name] = {"type": "LumpedPort", "kind": "edge_feed", "sheet": sheet,
                                          "feed_x": feed_x, "feed_y": feed_y, "impedance": impedance}
    return {"ok": True, "name": name, "sheet": sheet, "plane": plane, "impedance": impedance}


import re as _re
_UNIT_MM = {"": 1.0, "mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 0.001, "mil": 0.0254}


def _to_mm(s):
    """把 '5mm'/'0.635mm'/'5' 这种字面量长度解析成 mm 数值(用于算积分线 literal 坐标)。
    解析不了(含变量/表达式)返回 None。"""
    m = _re.match(r"^([+-]?\d*\.?\d+)\s*([a-zA-Z]*)$", str(s).strip())
    if not m:
        return None
    f = _UNIT_MM.get(m.group(2).lower())
    return float(m.group(1)) * f if f is not None else None


def _resolve_coord(oDesign, s):
    """坐标字符串 → 字面量(带单位)。已是字面量直接返回;裸变量名用 GetVariableValue 解析成
    '1.6mm' 这种;复杂表达式解析不了就原样返回(best-effort,老版本可能仍崩 → skill 提示拿不准写字面量)。"""
    s = str(s).strip()
    if _to_mm(s) is not None:                 # 已是 '1.6mm'/'-0.5mm'/'5' 字面量
        return s
    try:
        v = oDesign.GetVariableValue(s)        # 裸变量名(如 'subH')→ 其值字符串
        if v is not None and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    return s


def _resolve_pt(oDesign, pt):
    return [_resolve_coord(oDesign, c) for c in pt]


def _circle(oEditor, name, cx, cy, cz, radius, axis="Z"):
    oEditor.CreateCircle(
        ["NAME:CircleParameters", "XCenter:=", cx, "YCenter:=", cy, "ZCenter:=", cz,
         "Radius:=", radius, "WhichAxis:=", axis, "NumSegments:=", "0"],
        _attributes(name, "vacuum"))


@tool({
    "type": "function",
    "function": {
        "name": "create_coax_feed_port",
        "description": ("同轴探针馈电一步搞定:(1) 在 gnd 上 (feed_x,feed_y) 处钻孔(半径 outer_radius);"
                        "(2) 建内导体探针 z_bottom→z_top;(3) 在孔里建环形端口面(外圆-内圆);(4) 赋 lumped port(径向积分线)。"
                        "介质不需钻孔。**feed_x/feed_y/z 用字面量带单位**(积分线要字面量)。默认 SMA 50Ω(内 0.635mm/外 2.1mm)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "端口名"},
                "gnd": {"type": "string", "description": "地板 sheet 对象名(会被钻孔)"},
                "feed_x": {"type": "string", "description": "探针 X(字面量)"},
                "feed_y": {"type": "string", "description": "探针 Y(字面量)"},
                "z_bottom": {"type": "string", "description": "gnd 平面 Z(字面量,如 '0mm')"},
                "z_top": {"type": "string", "description": "顶部导体平面 Z(字面量)"},
                "inner_radius": {"type": "string", "default": "0.635mm", "description": "内导体半径(字面量)"},
                "outer_radius": {"type": "string", "default": "2.1mm", "description": "外导体/钻孔半径(字面量)"},
                "impedance": {"type": "number", "default": 50},
            },
            "required": ["name", "gnd", "feed_x", "feed_y", "z_bottom", "z_top"],
        },
    },
})
def create_coax_feed_port(ctx, name, gnd, feed_x, feed_y, z_bottom, z_top,
                          inner_radius="0.635mm", outer_radius="2.1mm", impedance=50):
    oEditor = ctx["oEditor"]
    pin = f"{name}_pin"
    hole = f"{name}_hole_tmp"
    outer = f"{name}_port"
    inner_tmp = f"{name}_inner_tmp"
    pin_h = f"({z_top})-({z_bottom})"
    try:
        # 1. gnd 钻孔
        _circle(oEditor, hole, feed_x, feed_y, z_bottom, outer_radius)
        oEditor.Subtract(["NAME:Selections", "Blank Parts:=", gnd, "Tool Parts:=", hole],
                         ["NAME:SubtractParameters", "KeepOriginals:=", False])
        # 2. 内导体探针
        oEditor.CreateCylinder(
            ["NAME:CylinderParameters", "XCenter:=", feed_x, "YCenter:=", feed_y, "ZCenter:=", z_bottom,
             "Radius:=", inner_radius, "Height:=", pin_h, "WhichAxis:=", "Z", "NumSides:=", "0"],
            _attributes(pin, "copper"))
        # 3. 环形端口面 = 外圆 - 内圆(在 z_bottom)
        _circle(oEditor, outer, feed_x, feed_y, z_bottom, outer_radius)
        _circle(oEditor, inner_tmp, feed_x, feed_y, z_bottom, inner_radius)
        oEditor.Subtract(["NAME:Selections", "Blank Parts:=", outer, "Tool Parts:=", inner_tmp],
                         ["NAME:SubtractParameters", "KeepOriginals:=", False])
    except Exception as e:
        return {"ok": False, "error": f"同轴几何构建失败: {type(e).__name__}: {e}"}
    # 4. 径向积分线:外缘 → 内缘(沿 +X)。积分线坐标必须 literal,所以把 feed_x±radius 算成字面量 mm。
    fx, ro, ri = _to_mm(feed_x), _to_mm(outer_radius), _to_mm(inner_radius)
    if None in (fx, ro, ri):
        return {"ok": False, "error": "feed_x/outer_radius/inner_radius 必须是字面量长度(如 '5mm'),不能含变量",
                "hint": "同轴积分线要 literal 坐标"}
    start = [f"{round(fx + ro, 6)}mm", feed_y, z_bottom]
    stop = [f"{round(fx + ri, 6)}mm", feed_y, z_bottom]
    ok, err = _assign_lumped(ctx["oDesign"], name, outer, start, stop, impedance)
    if not ok:
        return {"ok": False, "error": err}
    if "state" in ctx:
        ctx["state"].objects[pin] = {"type": "cylinder", "role": "coax_pin", "material": "copper"}
        ctx["state"].objects[outer] = {"type": "annulus", "role": "coax_port_sheet"}
        ctx["state"].excitations[name] = {"type": "LumpedPort", "kind": "coax_probe", "gnd": gnd,
                                          "pin": pin, "sheet": outer, "impedance": impedance}
    return {"ok": True, "name": name, "pin": pin, "port_sheet": outer, "impedance": impedance}
