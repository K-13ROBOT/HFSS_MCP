"""周期单元分析(native COM 版)—— 主从边界 + Floquet 端口。

用于无限阵列 / 频率选择表面(FSS)/ 超表面的**单元(unit cell)**仿真:
- 主从(Master/Slave)边界配在单元盒的 ±X、±Y 四个侧面,使场沿晶格周期。
- Floquet 端口配在单元盒顶/底面,以平面波激励 + 取反射/透射(S 参数对应各 Floquet 模)。
- 扫描角 θ/φ 设定入射方向(相位推进),master/slave 与 floquet 的扫描角要一致。

周期单元**不要**用 create_open_region(那是孤立天线的开放边界);单元盒一般是
辐射体上方/上下的真空盒,侧面主从、上下 Floquet。晶格矢量、面坐标全部从单元盒
的包围盒自动推导(对象须是轴对齐长方体)。

跨版本:用长期稳定的 AssignMaster/AssignSlave/AssignFloquetPort(2019 起可用;
新版 GUI 改叫 Primary/Secondary 但脚本名仍兼容)。COM 行为未在真机逐版本回归,
首次用盯结果。
"""

from . import tool
from .geometry import _bbox_of


def _bnd(ctx):
    return ctx["oDesign"].GetModule("BoundarySetup")


def _mm(v):
    return f"{v}mm"


def _pt(lo, hi, axis_overrides):
    """从 lo/hi 角点构造一个点:axis_overrides={轴:'lo'/'hi'},其余取 lo。返回带 mm 的 [x,y,z]。"""
    p = list(lo)
    for ax, side in axis_overrides.items():
        p[ax] = hi[ax] if side == "hi" else lo[ax]
    return [_mm(p[0]), _mm(p[1]), _mm(p[2])]


def _pick_face(oEditor, obj, axis, sign):
    """obj 上沿 axis(0/1/2=x/y/z)最 sign(+1=max,-1=min)的那个面的 face id;取不到返回 None。"""
    try:
        fids = [int(f) for f in oEditor.GetFaceIDs(obj)]
    except Exception:
        return None
    best_v, best_id = None, None
    for fid in fids:
        try:
            c = [float(x) for x in oEditor.GetFaceCenter(fid)]
        except Exception:
            continue
        v = c[axis]
        if best_v is None or (sign > 0 and v > best_v) or (sign < 0 and v < best_v):
            best_v, best_id = v, fid
    return best_id


def _lohi(bb):
    return ([bb["xmin"], bb["ymin"], bb["zmin"]], [bb["xmax"], bb["ymax"], bb["zmax"]])


_AXIS = {"x": 0, "y": 1, "z": 2}


@tool({
    "type": "function",
    "function": {
        "name": "assign_periodic_boundaries",
        "description": ("给单元盒的 ±X、±Y 四个侧面自动配主从(Master/Slave)周期边界——无限阵/FSS/超表面"
                        "单元分析的必备项。晶格矢量从盒子包围盒推(轴对齐长方体)。扫描角 θ/φ 给入射方向,"
                        "须与 Floquet 端口一致。配完再 assign_floquet_port。**别和 create_open_region 混用**。"),
        "parameters": {
            "type": "object",
            "properties": {
                "unit_cell": {"type": "string", "description": "单元盒对象名(轴对齐长方体)"},
                "scan_theta": {"type": "string", "default": "0deg", "description": "扫描角 θ(入射俯仰),如 '30deg'"},
                "scan_phi": {"type": "string", "default": "0deg", "description": "扫描角 φ(入射方位)"},
            },
            "required": ["unit_cell"],
        },
    },
})
def assign_periodic_boundaries(ctx, unit_cell, scan_theta="0deg", scan_phi="0deg"):
    oEditor = ctx["oEditor"]
    bb = _bbox_of(oEditor, unit_cell)
    if not bb:
        return {"ok": False, "error": f"取不到 '{unit_cell}' 包围盒(对象不存在或非长方体)"}
    lo, hi = _lohi(bb)
    oM = _bnd(ctx)

    # X 对:master 在 x=min 面、slave 在 x=max 面,U 向 +Y;晶格沿 X。
    # Y 对:master 在 y=min 面、slave 在 y=max 面,U 向 +X;晶格沿 Y。
    pairs = [
        ("MasterX", "SlaveX", 0, 1),   # (master名, slave名, 法线轴, U 方向轴)
        ("MasterY", "SlaveY", 1, 0),
    ]
    done = []
    for mname, sname, naxis, uaxis in pairs:
        mfid = _pick_face(oEditor, unit_cell, naxis, -1)
        sfid = _pick_face(oEditor, unit_cell, naxis, +1)
        if mfid is None or sfid is None:
            return {"ok": False, "error": f"挑不到 {unit_cell} 沿 {'XYZ'[naxis]} 的对面(GetFaceCenter 失败?)"}
        m_origin = _pt(lo, hi, {naxis: "lo"})
        m_upos = _pt(lo, hi, {naxis: "lo", uaxis: "hi"})
        s_origin = _pt(lo, hi, {naxis: "hi"})
        s_upos = _pt(lo, hi, {naxis: "hi", uaxis: "hi"})
        try:
            oM.AssignMaster(["NAME:" + mname, "Faces:=", [mfid],
                             ["NAME:CoordSysVector", "Origin:=", m_origin, "UPos:=", m_upos],
                             "ReverseV:=", False])
            oM.AssignSlave(["NAME:" + sname, "Faces:=", [sfid],
                            ["NAME:CoordSysVector", "Origin:=", s_origin, "UPos:=", s_upos],
                            "ReverseU:=", False, "Master:=", mname,
                            "UseScanAngles:=", True, "Phi:=", scan_phi, "Theta:=", scan_theta])
        except Exception as e:
            return {"ok": False, "error": f"配主从({mname}/{sname})失败: {type(e).__name__}: {e}"}
        done += [mname, sname]
        if "state" in ctx:
            ctx["state"].boundaries[mname] = {"type": "Master", "object": unit_cell, "axis": "XYZ"[naxis]}
            ctx["state"].boundaries[sname] = {"type": "Slave", "master": mname,
                                              "scan_theta": scan_theta, "scan_phi": scan_phi}
    return {"ok": True, "unit_cell": unit_cell, "boundaries": done,
            "scan_theta": scan_theta, "scan_phi": scan_phi,
            "note": "已配 X、Y 两对主从。接着 assign_floquet_port 配顶/底面端口(扫描角保持一致)。"}


@tool({
    "type": "function",
    "function": {
        "name": "assign_floquet_port",
        "description": ("在单元盒的一个面赋 Floquet 端口(周期单元的平面波激励/取反射透射)。默认顶面 +z;"
                        "做透射(FSS/超表面)需在 +z 和 -z 各配一个。num_modes=2 含 TE00+TM00 两主模。"
                        "晶格矢量从盒子几何推。扫描角须与 assign_periodic_boundaries 一致。配前先配好主从边界。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "端口名,如 'FloquetTop'"},
                "unit_cell": {"type": "string", "description": "单元盒对象名(轴对齐长方体)"},
                "side": {"type": "string", "enum": ["+z", "-z", "+x", "-x", "+y", "-y"], "default": "+z",
                         "description": "端口所在面,默认顶面 +z"},
                "num_modes": {"type": "integer", "default": 2, "description": "Floquet 模数,默认 2(TE00+TM00)"},
                "scan_theta": {"type": "string", "default": "0deg"},
                "scan_phi": {"type": "string", "default": "0deg"},
                "deembed_mm": {"type": "number", "default": 0, "description": "去嵌入距离(mm),>0 才去嵌"},
            },
            "required": ["name", "unit_cell"],
        },
    },
})
def assign_floquet_port(ctx, name, unit_cell, side="+z", num_modes=2,
                        scan_theta="0deg", scan_phi="0deg", deembed_mm=0):
    oEditor = ctx["oEditor"]
    bb = _bbox_of(oEditor, unit_cell)
    if not bb:
        return {"ok": False, "error": f"取不到 '{unit_cell}' 包围盒(对象不存在或非长方体)"}
    sign = -1 if side[0] == "-" else 1
    axis = _AXIS.get(side[-1].lower())
    if axis is None:
        return {"ok": False, "error": f"side 不合法: {side}"}
    fid = _pick_face(oEditor, unit_cell, axis, sign)
    if fid is None:
        return {"ok": False, "error": f"挑不到 {unit_cell} 的 {side} 面(GetFaceCenter 失败?)"}
    lo, hi = _lohi(bb)
    inplane = [i for i in (0, 1, 2) if i != axis]
    face_side = "hi" if sign > 0 else "lo"
    a_start = _pt(lo, hi, {axis: face_side})
    a_end = _pt(lo, hi, {axis: face_side, inplane[0]: "hi"})
    b_start = _pt(lo, hi, {axis: face_side})
    b_end = _pt(lo, hi, {axis: face_side, inplane[1]: "hi"})

    n = max(1, int(num_modes))
    modes = ["NAME:Modes"] + [["NAME:Mode" + str(i + 1), "ModeNum:=", i + 1, "UseIntLine:=", False]
                              for i in range(n)]
    arg = ["NAME:" + name, "Faces:=", [fid], "NumModes:=", n,
           "RenormalizeAllTerminals:=", True,
           "DoDeembed:=", bool(deembed_mm), "DeembedDist:=", _mm(deembed_mm),
           modes,
           "ShowReporterFilter:=", False, "ReporterFilter:=", [True] * n,
           "UseScanAngles:=", True, "Phi:=", scan_phi, "Theta:=", scan_theta,
           ["NAME:LatticeAVector", "LatticeStartPoint:=", a_start, "LatticeEndPoint:=", a_end],
           ["NAME:LatticeBVector", "LatticeStartPoint:=", b_start, "LatticeEndPoint:=", b_end]]
    try:
        _bnd(ctx).AssignFloquetPort(arg)
    except Exception as e:
        return {"ok": False, "error": f"AssignFloquetPort 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].excitations[name] = {"type": "FloquetPort", "object": unit_cell, "side": side,
                                          "num_modes": n, "scan_theta": scan_theta, "scan_phi": scan_phi}
    return {"ok": True, "name": name, "unit_cell": unit_cell, "side": side, "num_modes": n,
            "scan_theta": scan_theta, "scan_phi": scan_phi,
            "note": "Floquet 端口已配。透射类(FSS)记得 -z 面也配一个;扫描角要和主从一致。"}
