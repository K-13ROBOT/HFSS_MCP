"""场诊断:看结构上实际流了什么(native COM 版)。

补的是这么一个盲区:其余 get_* 工具只能测"进去多少"(S 参数/Zin)和"出来多少"
(远场/增益/轴比),**看不见中间的机理**。失配了不知道是没激励起来还是模次不对,
方向图歪了不知道是哪部分在辐射 —— 只能靠扫参试。表面电流是这一环的直接读数。

走的是 ReportSetup 的 "Fields" 报告(context = 一条 polyline,PointCount 控采样密度),
跟 analysis.py 里取 S 参数/远场是同一个路子:CreateReport → ExportToFile → 解析 CSV。
不走 FieldsReporter 场计算器 —— 那个是有状态的压栈式 API,行为更不稳。

**前提:必须有存场的解**(create_sweep 的 save_fields=True,或用 LastAdaptive 的自适应解)。
场数据贵(实测 ~90-100 秒/点、几百 MB/点),所以场诊断只在**单频点**用,不跟扫频做,
用完 delete_sweep 清掉 —— 见 `flow/diagnose-current.md` 与 knowledge/_solving.md。
"""

import os
import math

from . import tool, resolve_setup


# Fields 报告的 families **必须把该 design 的全部设计变量列全**(各取 ["Nominal"]),
# 外加 Freq / Phase。少列一个变量,CreateReport **不报错但什么都不建** ——
# GetAllReportNames() 是空的,随后 ExportToFile 也不报错、不产出文件。
# 这条是从 AEDT 的 Tools→Record Script 录出来的官方调用抄的(2025.2 实测),
# 猜是猜不出来的:S 参数/远场报告都不需要列设计变量,只有 Fields 报告要。
# 调用是 7 参(末尾不带空数组),PointCount 传 int。

def _design_var_families(oDesign):
    """该 design 的全部设计变量 → ["名:=", ["Nominal"], ...]。取不到就返回空(交给下面报错)。"""
    fam = []
    try:
        for v in (oDesign.GetVariables() or []):
            fam += [f"{v}:=", ["Nominal"]]
    except Exception:
        pass
    return fam


def _fields_report_to_csv(oDesign, soln, path, expr, point_count, freq, csv_path):
    """Fields 报告(沿 polyline 采样)→ ExportToFile CSV。返回 (ok, err)。
    CreateReport 的 arity 各版本不一致,照 analysis.py 的做法逐个试。"""
    oModule = oDesign.GetModule("ReportSetup")
    rname = "_field_path_tmp"
    ctxt = ["Context:=", str(path), "PointCount:=", int(point_count)]
    trace = ["X Component:=", "Distance", "Y Component:=", [str(expr)]]
    fams = ["Distance:=", ["All"]]
    if freq:
        fams += ["Freq:=", [str(freq)], "Phase:=", ["0deg"]]
    fams += _design_var_families(oDesign)      # ← 漏掉这段就静默建不出报告
    forms = [
        (rname, "Fields", "Rectangular Plot", soln, ctxt, fams, trace),      # 录制出来的官方形式
        (rname, "Fields", "Rectangular Plot", soln, ctxt, fams, trace, []),
    ]
    if os.path.exists(csv_path):
        os.remove(csv_path)          # 别让上一次的残留冒充本次结果
    last = None
    for i, args in enumerate(forms):
        try:
            oModule.CreateReport(*args)
            oModule.ExportToFile(rname, csv_path)
            # ⚠️ 实测:CreateReport + ExportToFile 都**不抛异常**,文件却没落地
            # (报告建出来是空的)。所以必须以"文件存在且非空"为判据,否则一个静默
            # 失败会被当成成功,到下游变成莫名的 FileNotFoundError。
            if os.path.exists(csv_path) and os.path.getsize(csv_path) > 20:
                return True, None
            # 报告建出来了却导不出数据,最常见的原因是**解已失效**:求解之后动过几何,
            # 而"画一条采样用的 polyline"也算动几何。HFSS 只在消息窗口写一句
            # "Solutions have been invalidated",COM 这边完全看不出来。
            last = (f"form#{i}: 报告建出来了,但没有数据可导。"
                    "最可能是解已失效 —— 求解后动过几何(**采样线没加 non_model=True 也算**)。"
                    "处理:重新 analyze 再取场;采样线以后用 create_polyline(non_model=True),"
                    "求解后补画不作废;"
                    "调 get_messages 能看到 'Solutions have been invalidated' 确认")
        except Exception as e:
            last = f"form#{i}(arity={len(args) + 3}): {type(e).__name__}: {e}"
        finally:
            # 失败也可能留了个空报告,清掉再试下一种。先查在不在:对不存在的报告 DeleteReports
            # 会在消息窗口记一条 [error] "Report not found"(2019.2 上 form#0 必失败,每次都留),
            # 让 get_messages 里平白多出一条要人去追的假错误
            try:
                if rname in [str(x) for x in oModule.GetAllReportNames()]:
                    oModule.DeleteReports([rname])
            except Exception:
                pass
    return False, f"取场报告失败。最后一次: {last}"


def _parse_two_col(csv_path):
    """Fields 报告 CSV → ([distance], [value])。取每行前两个能转成浮点的列。"""
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        rows = [ln.strip() for ln in f if ln.strip()]
    if not rows:
        return None, None, "CSV 为空"
    header = rows[0]
    xs, ys = [], []
    for ln in rows[1:]:
        parts = [p.strip().strip('"') for p in ln.split(",")]
        nums = []
        for p in parts:
            try:
                nums.append(float(p))
            except ValueError:
                pass
            if len(nums) == 2:
                break
        if len(nums) == 2:
            xs.append(nums[0])
            ys.append(nums[1])
    if not xs:
        return None, None, f"CSV 解析不出数值,表头: {header[:160]}"
    return xs, ys, None


def _features(xs, ys, null_frac):
    """从采样曲线提炼判据 —— agent 能直接推理的东西,而不是一堆原始数。"""
    peak = max(ys)
    i_pk = ys.index(peak)
    out = {
        "peak": round(peak, 6),
        "peak_at": round(xs[i_pk], 4),
        "peak_at_fraction": round((xs[i_pk] - xs[0]) / (xs[-1] - xs[0]), 3) if xs[-1] != xs[0] else 0.0,
        "start": round(ys[0], 6),
        "end": round(ys[-1], 6),
    }
    # 首尾衰减(dB):行波天线"辐射完了没"的判据 —— 末端残留越小越说明能量已辐射掉
    if ys[0] > 0 and ys[-1] > 0:
        out["decay_db"] = round(20 * math.log10(ys[-1] / ys[0]), 2)
    # 电流零点:低于峰值 null_frac 的局部极小。**只数内部零点**(端点天然为零,不是模次信息),
    # 所以 n_nulls 就是模次读数:基模 0、全波 1、三次模 2 —— 模次 = n_nulls + 1。离线用合成
    # 正弦曲线验过(sin(πu)/sin(2πu)/sin(3πu) 分别给 0/1/2)。
    thr = peak * null_frac
    nulls = []
    for i in range(1, len(ys) - 1):
        if ys[i] < thr and ys[i] <= ys[i - 1] and ys[i] <= ys[i + 1]:
            if not nulls or xs[i] - nulls[-1] > (xs[-1] - xs[0]) * 0.05:   # 合并相邻点
                nulls.append(xs[i])
    out["n_nulls"] = len(nulls)
    out["nulls_at"] = [round(v, 4) for v in nulls]
    out["null_threshold"] = round(thr, 6)
    return out


@tool({
    "type": "function",
    "function": {
        "name": "get_current_along_path",
        "description": ("沿一条 polyline 取**表面电流 |J| 的分布**(幅度 vs 沿线距离)+ 判据:"
            "峰值与位置、内部零点数、首尾衰减 dB。**模次 = n_nulls + 1**(端点天然为零不计)。"
            "其余 get_* 只测进去多少/出来多少,这个看结构上实际流了什么。"
            "**采样线用 create_polyline(non_model=True, close_surface=False, cover_surface=False) 画**"
            "(模型线求解后画会让解作废、COM 无提示;不关闭合/覆面会变成一去一回的路径),"
            "**线要略短于导体、避开馈电点**(否则读到的是馈电区电流)。"
            "什么时候该调见 `flow/diagnose-current.md`,别每次取结果都调。"),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "采样路径的 polyline 对象名(需贴着要看的导体表面)"},
                "setup": {"type": "string", "description": "setup 名,不传用第一个"},
                "sweep": {"type": "string", "default": "LastAdaptive",
                          "description": "解名。默认 'LastAdaptive'(自适应频点的解,不需要存场扫频);"
                                         "要看别的频点则传扫频名,且该扫频必须 save_fields=True"},
                "freq": {"type": "string",
                         "description": "取哪个频点(带单位,如 '2.4GHz')。用 LastAdaptive 时可不传"},
                "quantity": {"type": "string", "default": "Mag_Jsurf",
                             "description": "场量表达式。默认 'Mag_Jsurf'(表面电流幅度)。"
                                            "也可 'Mag_H' / 'Mag_E';要看相位沿线递进传分量的相位表达式"},
                "point_count": {"type": "integer", "default": 50,
                                "description": "沿线采样点数,默认 50(够判趋势且不炸 context)"},
                "null_fraction": {"type": "number", "default": 0.2,
                                  "description": "判零点的阈值:低于峰值这个比例的局部极小算一个零点,默认 0.2"},
                "include_samples": {"type": "boolean", "default": True,
                                    "description": "false 则只回判据不回采样数组,省 context"},
            },
            "required": ["path"],
        },
    },
})
def get_current_along_path(ctx, path, setup=None, sweep="LastAdaptive", freq=None,
                           quantity="Mag_Jsurf", point_count=50, null_fraction=0.2,
                           include_samples=True):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")

    setup, err = resolve_setup(ctx, setup)
    if err:
        return err

    # 先挡掉最常见的失败:取非自适应频点的场,却没存场。省一次几十秒的 COM 往返。
    if sweep != "LastAdaptive" and state:
        sw = state.setups.get(setup, {}).get("sweeps", [])
        rec = next((s for s in sw if isinstance(s, dict) and s.get("name") == sweep), None)
        if rec is not None and not rec.get("save_fields"):
            return {"ok": False,
                    "error": f"扫频 '{sweep}' 建的时候没有 save_fields=True,没有场可取",
                    "hint": "要么改用 sweep='LastAdaptive'(自适应频点的场总是在的),"
                            "要么 delete_sweep 删掉重建一个 save_fields=True 的单频点扫频"}

    from .session import EXPORTS_DIR
    soln = f"{setup} : {sweep}"
    csv_path = os.path.join(EXPORTS_DIR, f"_Jpath_{path}.csv")
    ok, err = _fields_report_to_csv(oDesign, soln, path, quantity, point_count, freq, csv_path)
    if not ok:
        return {"ok": False, "error": err,
                "hint": ("第一步先查这个解在不在场解列表里:"
                         "oDesign.GetModule('ReportSetup').GetAvailableSolutions('Fields') —— "
                         "不在就说明这条解没有可供后处理的场,再怎么调参数都没用。"
                         "其次:GetAllQuantities(...) 返回空也是同一个病因。"
                         "最后才查 path 是不是已存在的 polyline、quantity 名(表面电流是 'Mag_Jsurf')、freq 是否落在已解频点上。")}

    xs, ys, perr = _parse_two_col(csv_path)
    if perr:
        return {"ok": False, "error": perr, "csv": csv_path}

    out = {"ok": True, "path": path, "setup": setup, "sweep": sweep,
           "quantity": quantity, "n_points": len(xs)}
    if freq:
        out["freq"] = freq
    out.update(_features(xs, ys, null_fraction))
    if include_samples:
        out["distance"] = [round(v, 4) for v in xs]
        out["values"] = [round(v, 6) for v in ys]
    out["csv"] = csv_path
    return out


# ---------------------------------------------------------------------------
# 平面场分布:FieldsReporter 场计算器 → ExportOnGrid(点值 .fld)→ 叠几何轮廓出图
# ---------------------------------------------------------------------------
# 跟上面的 Fields 报告是两条路:沿线取样走 ReportSetup;整面取样只能走 FieldsReporter
# (Fields 报告不支持二维网格)。场计算器是压栈式 API,所以每次都先 CalcStack("clear"),
# 只用 CopyNamedExprToStack 取命名表达式(Mag_E = 各分量复幅值的模,峰值意义,不受相位影响)。
# 实测(2025.2):表达式名错、频点不在解里 —— ExportOnGrid / CopyNamedExprToStack 都会抛异常,
# 不会静默出空文件;5.2 mm 见方、0.1 mm 网格一面 ~2 s。
# 轮廓只画金属:赋了 PE / 有限电导率 / 阻抗边界的片,和 Solve Inside=False 的实体(过孔)。
# 端口面、未赋边界的真空片不算。多边形边精确;真圆(NumSegments=0)的边**没有顶点**,COM 读不出圆心半径 ——
# 单边圆片用 GetFaceCenter + 面积还原,平面上挖的圆孔(避让孔)画不出,只计数报告;
# 只有两个端点的曲线边(圆弧)画成直线弦。

import ast as _ast
import re as _re

_UNIT_MM = {"mm": 1.0, "um": 1e-3, "nm": 1e-6, "cm": 10.0, "m": 1000.0, "meter": 1000.0,
            "mil": 0.0254, "in": 25.4, "inch": 25.4}
_METAL_BOUNDARY_TYPES = ("Perfect E", "Finite Conductivity", "Impedance", "Layered Impedance")
_TOKEN = _re.compile(r"(\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)\s*([A-Za-z]+)?|([A-Za-z_]\w*)")
_SAFE_NODES = (_ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant,
               _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Pow, _ast.USub, _ast.UAdd)


def _to_model(oDesign, val, model_units, _depth=0):
    """长度 → 模型单位下的浮点数。接受 0.76 / '0.76mm' / 'subH' / 'subH/2+0.1mm';裸数按模型单位。"""
    if isinstance(val, (int, float)):
        return float(val)
    mu = model_units.lower()
    if mu not in _UNIT_MM:
        raise ValueError(f"不认识的模型单位 '{model_units}'")
    s = str(val).strip()
    if _depth > 8:
        raise ValueError(f"变量嵌套太深:'{s}'")

    def sub(m):
        num, unit, name = m.group(1), m.group(2), m.group(3)
        if name:                                  # 设计变量 → 递归求值
            try:
                v = oDesign.GetVariableValue(name) if oDesign is not None else None
            except Exception:
                v = None
            if v is None or not str(v).strip():
                raise ValueError(f"'{s}' 里的 '{name}' 不是设计变量")
            return repr(_to_model(oDesign, str(v), model_units, _depth + 1))
        if not unit:
            return num
        if unit.lower() not in _UNIT_MM:
            raise ValueError(f"'{s}' 里不认识的单位 '{unit}'")
        return repr(float(num) * _UNIT_MM[unit.lower()] / _UNIT_MM[mu])

    expr = _TOKEN.sub(sub, s)
    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError(f"看不懂的长度 '{s}'")
    if not all(isinstance(n, _SAFE_NODES) for n in _ast.walk(tree)):
        raise ValueError(f"看不懂的长度 '{s}'(只支持 + - * / 和括号)")
    return float(eval(compile(tree, "<len>", "eval"), {"__builtins__": {}}))


def _set_sources(oDesign, excite):
    """excite: {"PH": "1W"} 或 {"PH:1": ["1W", "90deg"]};没列的激励全部置 0W。返回 (实际设置, err)。"""
    from .sources import _list_excitations, _match, _edit_sources
    names = _list_excitations(oDesign)
    want = {}
    for k, v in excite.items():
        hit = _match(k, names)                      # 只给端口名时取它的 1 号模
        if hit is None:
            return None, f"没有叫 '{k}' 的激励;可用: {names}"
        if isinstance(v, (int, float)):
            want[hit] = (f"{v}W", "0deg")
        elif isinstance(v, str):
            want[hit] = (v, "0deg")
        else:
            want[hit] = (str(v[0]), str(v[1]) if len(v) > 1 else "0deg")
    get = lambda n: want.get(n, ("0W", "0deg"))
    rows = [["Name:=", n, "Magnitude:=", get(n)[0], "Phase:=", get(n)[1]] for n in names]
    _, err = _edit_sources(oDesign.GetModule("Solutions"), rows)
    if err:
        return None, err
    return {n: get(n)[0] + "@" + get(n)[1] for n in names}, None


def _metal_sheet_names(oDesign, oEditor):
    """赋了金属类边界的对象名集合;查不了返回 None(调用方退回"所有片都算")。
    GetBoundaryAssignment 返回的是**面 ID**(2025.2 实测 PE1 → ['44','56']),要换回对象名。"""
    try:
        bs = oDesign.GetModule("BoundarySetup")
        raw = [str(x) for x in (bs.GetBoundaries() or [])]          # [名, 类型, 名, 类型, ...]
        out = set()
        for name, typ in zip(raw[0::2], raw[1::2]):
            if typ in _METAL_BOUNDARY_TYPES:
                for x in (bs.GetBoundaryAssignment(name) or []):
                    x = str(x)
                    out.add(str(oEditor.GetObjectNameByFaceID(int(x))) if x.isdigit() else x)
        return out
    except Exception:
        return None


def _plane_outlines(oDesign, oEditor, a, pos, window):
    """切面附近的金属轮廓。a = 法向轴 0/1/2。返回 dict:
    levels(选中的金属层坐标)、segs{level: [(u1,v1,u2,v2)]}、circles{level: [(u,v,r)]}、
    cross(竖直片与切面的交线)、cuts(穿过切面的金属实体截面框)、n_hidden_circles、extent。
    两遍:先只用包围盒分类、选层,再只对选中层的片读面/边/顶点(那一步 COM 调用最多)。"""
    from .geometry import _all_object_names, _bbox_of
    ua, va = [i for i in (0, 1, 2) if i != a]
    sheets = set(str(x) for x in (oEditor.GetObjectsInGroup("Sheets") or []))
    metal = _metal_sheet_names(oDesign, oEditor)
    flat, cross, cuts, ext = [], [], [], [None] * 4

    def grow(u0, u1, v0, v1):
        for i, val, f in ((0, u0, min), (1, u1, max), (2, v0, min), (3, v1, max)):
            ext[i] = val if ext[i] is None else f(ext[i], val)

    for n in _all_object_names(oEditor):
        is_sheet = n in sheets
        if is_sheet:
            if metal is not None and n not in metal:
                continue                # 端口面、没赋边界的真空片
        else:
            try:
                if str(oEditor.GetPropertyValue("Geometry3DAttributeTab", n, "Solve Inside")).lower() not in ("false", "0"):
                    continue            # 介质/空气不画
            except Exception:
                continue
        bb = _bbox_of(oEditor, n)
        if bb is None:
            continue
        lo = [bb["xmin"], bb["ymin"], bb["zmin"]]
        hi = [bb["xmax"], bb["ymax"], bb["zmax"]]
        size = max(hi[i] - lo[i] for i in range(3)) or 1.0
        if not is_sheet:
            # 穿过切面的金属实体:画截面包围框(过孔近似为圆)
            if lo[a] < pos < hi[a]:
                du, dv = hi[ua] - lo[ua], hi[va] - lo[va]
                kind = "circle" if abs(du - dv) < 0.15 * max(du, dv, 1e-12) else "rect"
                cuts.append((kind, (lo[ua] + hi[ua]) / 2, (lo[va] + hi[va]) / 2, du, dv, n))
            continue
        grow(lo[ua], hi[ua], lo[va], hi[va])
        if hi[a] - lo[a] >= 1e-6 * size:
            # 片不垂直于法向轴(比如 z 片被 x 切面切):被切面穿过时画交线(按包围盒,开槽处会连上)
            for k in (ua, va):
                if hi[k] - lo[k] < 1e-6 * size and lo[a] < pos < hi[a]:
                    o = va if k == ua else ua
                    p1 = {k: lo[k], o: lo[o]}
                    p2 = {k: lo[k], o: hi[o]}
                    cross.append((p1[ua], p1[va], p2[ua], p2[va]))
            continue
        flat.append((round(lo[a], 9), n))

    levels = sorted({lv for lv, _ in flat})
    span = max(ext[1] - ext[0], ext[3] - ext[2]) if ext[0] is not None else None
    if window is not None:
        pick = [lv for lv in levels if abs(lv - pos) <= window]
    else:
        # 上下最近各一层,但离切面超过视场 10% 的不算"附近"(竖切时远处的平行片不该画进来)
        lim = 0.1 * span if span else float("inf")
        below = [lv for lv in levels if pos - lim <= lv <= pos]
        above = [lv for lv in levels if pos <= lv <= pos + lim]
        pick = sorted({x for x in ((below[-1] if below else None), (above[0] if above else None)) if x is not None})
    # 截面框只对细实体(过孔/柱)有意义;大实体(合并成一个对象的整圈围栏等)的包围盒画出来是误导,只计数
    big = [c for c in cuts if span and max(c[3], c[4]) > 0.15 * span]
    cuts = [c for c in cuts if c not in big]
    out = {"levels": pick, "segs": {}, "circles": {}, "cross": cross, "cuts": cuts, "n_hidden_circles": 0,
           "big_solids_skipped": [c[5] for c in big], "metal_from_boundaries": metal is not None,
           "extent": tuple(ext) if ext[0] is not None else None}

    vcache = {}

    def vpos(vid):
        if vid not in vcache:
            vcache[vid] = [float(c) for c in oEditor.GetVertexPosition(vid)]
        return vcache[vid]

    for level, n in flat:
        if level not in pick:
            continue
        for f in oEditor.GetFaceIDs(n):
            edges = list(oEditor.GetEdgeIDsFromFace(f))
            for e in edges:
                vs = list(oEditor.GetVertexIDsFromEdge(e))
                if len(vs) == 2:
                    p, q = vpos(vs[0]), vpos(vs[1])
                    out["segs"].setdefault(level, []).append((p[ua], p[va], q[ua], q[va]))
                elif len(edges) == 1:       # 单边圆片:圆心=面心,半径由面积还原
                    c = [float(x) for x in oEditor.GetFaceCenter(f)]
                    r = (float(oEditor.GetFaceArea(f)) / math.pi) ** 0.5
                    out["circles"].setdefault(level, []).append((c[ua], c[va], r))
                else:
                    out["n_hidden_circles"] += 1   # 面上挖的真圆孔:读不出圆心半径
    return out


def _read_fld(path, ua, va, model_units):
    """ExportOnGrid 的 .fld(坐标 SI 米)→ (us, vs, grid[v][u])。坐标换回模型单位。"""
    k = 1000.0 / _UNIT_MM[model_units.lower()]
    pts = []
    with open(path, "r", errors="replace") as f:
        for ln in f:
            p = ln.split()
            if len(p) < 4:
                continue
            try:
                xyz = [float(p[0]) * k, float(p[1]) * k, float(p[2]) * k]
                val = float(p[3])
            except ValueError:
                continue
            if val != val:          # NaN
                continue
            pts.append((round(xyz[ua], 9), round(xyz[va], 9), val))
    us = sorted({p[0] for p in pts})
    vs = sorted({p[1] for p in pts})
    iu = {u: i for i, u in enumerate(us)}
    iv = {v: i for i, v in enumerate(vs)}
    grid = [[None] * len(us) for _ in vs]
    for u, v, val in pts:
        grid[iv[v]][iu[u]] = val
    return us, vs, grid


def _hotspots(us, vs, grid, within_db=6.0, n_max=5):
    """峰值附近(距峰 within_db dB 内)的亮区代表点,相互间隔 ≥ 8% 视场。"""
    vals = [(grid[j][i], us[i], vs[j]) for j in range(len(vs)) for i in range(len(us)) if grid[j][i]]
    if not vals:
        return None, []
    vals.sort(reverse=True)
    peak = vals[0][0]
    sep = 0.08 * max(us[-1] - us[0], vs[-1] - vs[0], 1e-12)
    spots = []
    for val, u, v in vals:
        if 20 * math.log10(val / peak) < -within_db or len(spots) >= n_max:
            break
        if all(math.hypot(u - s[1], v - s[2]) >= sep for s in spots):
            spots.append((val, u, v))
    return peak, [{"at": [round(u, 4), round(v, 4)], "rel_db": round(20 * math.log10(val / peak), 2)}
                  for val, u, v in spots]


def _plot_planes(maps, outl, axes_names, title_extra, dyn_db, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Circle, Rectangle
    gmax = max(max(v for row in g for v in row if v is not None) for _, _, _, g in maps)
    n = len(maps)
    du = maps[0][1][-1] - maps[0][1][0]
    dv = maps[0][2][-1] - maps[0][2][0]
    flat_view = dv > 0 and du > 0 and max(du / dv, dv / du) > 4     # 竖切穿薄板:等比例会压成一条线
    fig, axs = plt.subplots(1, n, figsize=(6.2 * n, 5.8), squeeze=False)
    lv = outl["levels"]
    if len(lv) == 2:
        styles = {lv[0]: ("c", "--"), lv[1]: ("w", "-")}
    else:
        styles = {l: (plt.cm.cool(i / max(1, len(lv) - 1)) if len(lv) > 1 else "w", "-") for i, l in enumerate(lv)}
    for ax, (label, us, vs, g) in zip(axs[0], maps):
        G = np.array([[np.nan if v is None or v <= 0 else 20 * np.log10(v) for v in row] for row in g])
        im = ax.pcolormesh(us, vs, G, cmap="inferno", vmin=20 * np.log10(gmax) - dyn_db,
                           vmax=20 * np.log10(gmax), shading="auto")
        for l in lv:
            col, ls = styles[l]
            for (u1, v1, u2, v2) in outl["segs"].get(l, []):
                ax.plot([u1, u2], [v1, v2], color=col, ls=ls, lw=0.7)
            for (u, v, r) in outl["circles"].get(l, []):
                ax.add_patch(Circle((u, v), r, fill=False, ec=col, ls=ls, lw=0.7))
        for (u1, v1, u2, v2) in outl["cross"]:
            ax.plot([u1, u2], [v1, v2], color="w", lw=0.9)
        for kind, u, v, du_, dv_, _ in outl["cuts"]:
            if kind == "circle" and not flat_view:
                ax.add_patch(Circle((u, v), max(du_, dv_) / 2, fill=False, ec="lime", lw=0.8))
            else:
                ax.add_patch(Rectangle((u - du_ / 2, v - dv_ / 2), du_, dv_, fill=False, ec="lime", lw=0.8))
        ax.set_xlim(us[0], us[-1])
        ax.set_ylim(vs[0], vs[-1])
        ax.set_aspect("auto" if flat_view else "equal")
        ax.set_xlabel(axes_names[0])
        ax.set_ylabel(axes_names[1] + ("  (stretched)" if flat_view else ""))
        ax.set_title(f"{label}  {title_extra}", fontsize=9)
        fig.colorbar(im, ax=ax, label="dB (shared scale)")
    leg = []
    if len(lv) == 2:
        leg = [f"white solid = metal @ {lv[1]:g}", f"cyan dashed = metal @ {lv[0]:g}"]
    elif len(lv) == 1:
        leg = [f"white = metal @ {lv[0]:g}"]
    elif lv:
        leg = [f"metal levels {', '.join(f'{x:g}' for x in lv)} (cool colormap, low→high)"]
    leg.append("lime = metal solids crossing the plane")
    fig.suptitle(" | ".join(leg), fontsize=8)
    plt.tight_layout()
    plt.savefig(png, dpi=90)
    plt.close(fig)


@tool({
    "type": "function",
    "function": {
        "name": "export_field_plane",
        "description": ("导出一个**切面上的场幅度分布**(默认 Mag_E)并出图(叠加切面附近的金属轮廓 + 穿过切面的过孔),"
            "回峰值位置与热点列表。用来回答'能量在哪 / 哪个结构在谐振 / 端口之间从哪里耦合':"
            "只激励一个口(excite={'P1': '1W'},其余自动置 0)看另一口附近亮不亮;"
            "传多个频点(如谐振点与正常点)同色标并排,强弱差一眼可见。"
            "**前提:解里有场** —— 扫频须 save_fields=True(单频点离散扫频即可),或用 LastAdaptive 的自适应频点。"
            "图是 PNG(用 Read 看),数据是 .fld 点值文本(x y z 值,坐标 SI 米)。"
            "注意:传 excite 会改 Edit Sources,之后的远场/场图沿用这个激励;"
            "平面里挖的真圆孔(避让孔)画不出,只报数量;圆弧边画成直线弦。"),
        "parameters": {
            "type": "object",
            "properties": {
                "position": {"type": ["string", "number"],
                             "description": "切面位置,如 '0.76mm' 或 'subH/2';裸数按模型单位"},
                "axis": {"type": "string", "enum": ["x", "y", "z"], "default": "z",
                         "description": "切面法向。默认 z(水平面)"},
                "freq": {"type": ["string", "array"], "items": {"type": "string"},
                         "description": "频点,如 '21.1GHz' 或 ['19GHz','21.1GHz'](多个频点同色标并排)。"
                                        "用 LastAdaptive 时可省(取 setup 的第一个自适应频点)"},
                "setup": {"type": "string", "description": "setup 名,不传用第一个"},
                "sweep": {"type": "string", "default": "LastAdaptive",
                          "description": "解名:'LastAdaptive' 或一个 save_fields=True 的扫频名"},
                "quantity": {"type": "string", "default": "Mag_E",
                             "description": "场计算器命名表达式:Mag_E / Mag_H / Mag_Jvol 等"},
                "excite": {"type": "object",
                           "description": "激励 {端口名: '1W'} 或 {'端口:模号': ['1W','90deg']};没列的全置 0。"
                                          "不传则沿用当前 Edit Sources"},
                "range": {"type": "array", "items": {"type": ["string", "number"]},
                          "description": "视场 [u_min, u_max, v_min, v_max](切面内两轴,z 切面即 x,y)。"
                                         "不传取所有金属片的包围范围"},
                "step": {"type": ["string", "number"],
                         "description": "网格步长,不传时长边 130 点、短边至少 40 点"},
                "outline_window": {"type": ["string", "number"],
                                   "description": "画切面 ±这个距离内所有金属层的轮廓;不传只画上下最近的各一层"},
                "dynamic_range_db": {"type": "number", "default": 40,
                                     "description": "色标动态范围(从所有图的共同最大值往下),默认 40 dB"},
                "tag": {"type": "string", "description": "输出文件名标签,不传自动生成"},
            },
            "required": ["position"],
        },
    },
})
def export_field_plane(ctx, position, axis="z", freq=None, setup=None, sweep="LastAdaptive",
                       quantity="Mag_E", excite=None, range=None, step=None, outline_window=None,
                       dynamic_range_db=40, tag=None):
    view = range          # 参数名沿用 schema 的 range;函数体里只用 view,别遮住内置 range
    oDesign, oEditor = ctx["oDesign"], ctx["oEditor"]
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
    soln = f"{setup} : {sweep}"
    try:
        avail = [str(x) for x in oDesign.GetModule("ReportSetup").GetAvailableSolutions("Fields")]
    except Exception:
        avail = None
    if avail is not None and soln not in avail:
        return {"ok": False, "error": f"'{soln}' 没有可后处理的场", "fields_solutions": avail,
                "hint": "建一个 save_fields=True 的单频点离散扫频并求解,或改用 LastAdaptive"}

    try:
        mu = str(oEditor.GetModelUnits())
    except Exception:
        mu = "mm"
    a = "xyz".index(axis)
    ua, va = [i for i in (0, 1, 2) if i != a]
    try:
        pos = _to_model(oDesign, position, mu)
        win = _to_model(oDesign, outline_window, mu) if outline_window is not None else None
        stp_user = _to_model(oDesign, step, mu) if step is not None else None
        rg = [_to_model(oDesign, x, mu) for x in view] if view else None
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if rg is not None and len(rg) != 4:
        return {"ok": False, "error": "range 要 4 个数 [u_min, u_max, v_min, v_max]"}

    freqs = [freq] if isinstance(freq, str) else list(freq or [])
    if not freqs:
        if sweep != "LastAdaptive":
            return {"ok": False, "error": "扫频解必须给 freq"}
        from . import setup_freqs
        sf = setup_freqs(oDesign).get(setup)
        if not sf:
            return {"ok": False, "error": f"读不到 {setup} 的自适应频点,请显式给 freq"}
        freqs = [sf[1].split(",")[0].strip()]

    outl = _plane_outlines(oDesign, oEditor, a, pos, win)
    if rg is None:
        if outl["extent"]:
            rg = list(outl["extent"])
        else:
            bb = [float(x) for x in oEditor.GetModelBoundingBox()]
            rg = [bb[ua], bb[ua + 3], bb[va], bb[va + 3]]
    du, dv = rg[1] - rg[0], rg[3] - rg[2]
    if stp_user:
        su = sv = stp_user
    else:
        # 长边 130 点;短边至少 40 点(竖切穿薄板时厚度方向不然只剩几个点)
        s_long = max(du, dv) / 130.0
        su = min(s_long, du / 40.0) if du > 0 else s_long
        sv = min(s_long, dv / 40.0) if dv > 0 else s_long

    sources = None
    if excite:
        try:
            sources, err = _set_sources(oDesign, excite)
        except Exception as e:
            return {"ok": False, "error": f"EditSources 失败: {type(e).__name__}: {e}"}
        if err:
            return {"ok": False, "error": err}

    def fail(d):
        if sources:     # 激励已经改了,出错也要让调用方知道
            d["sources_set"] = sources
            d["sources_note"] = "Edit Sources 已改成上面的设置(本次出错前就改了),后续远场/场图沿用它"
        return d

    from .session import EXPORTS_DIR
    fr = oDesign.GetModule("FieldsReporter")
    dname = str(oDesign.GetName()).split(";")[-1]
    base = _re.sub(r"[^\w.\-]+", "_", tag or f"{dname}_{quantity}_{axis}{position}")
    lo, hi, st = [0.0] * 3, [0.0] * 3, [su] * 3
    lo[a] = hi[a] = pos
    lo[ua], hi[ua], lo[va], hi[va] = rg[0], rg[1], rg[2], rg[3]
    st[ua], st[va] = su, sv
    fmt = lambda v: f"{v:.9g}{mu}"
    maps, per_freq = [], []
    for f in freqs:
        fld = os.path.join(EXPORTS_DIR, f"field_{base}_{_re.sub(r'[^\w.]+', '_', f)}.fld")
        if os.path.exists(fld):
            os.remove(fld)
        try:
            fr.CalcStack("clear")
            fr.CopyNamedExprToStack(quantity)
        except Exception as e:
            return fail({"ok": False, "error": f"场计算器取不到命名表达式 '{quantity}': {e}",
                         "hint": "常用:Mag_E / Mag_H / Mag_Jvol / Mag_Jsurf(Jsurf 只在导体表面有值)"})
        try:
            fr.ExportOnGrid(fld, [fmt(v) for v in lo], [fmt(v) for v in hi], [fmt(v) for v in st],
                            soln, ["Freq:=", f, "Phase:=", "0deg"], True, "Cartesian",
                            ["0" + mu, "0" + mu, "0" + mu], False)
        except Exception as e:
            return fail({"ok": False, "error": f"ExportOnGrid 失败({f}): {e}",
                         "hint": "最常见:freq 不在这个解的存场频点上(离散扫频只有建的那几个点);其次是解已失效"})
        if not os.path.exists(fld) or os.path.getsize(fld) < 50:
            return fail({"ok": False, "error": f"ExportOnGrid 没产出数据({f})", "file": fld})
        us, vs, g = _read_fld(fld, ua, va, mu)
        peak, spots = _hotspots(us, vs, g)
        maps.append((f, us, vs, g))
        per_freq.append({"freq": f, "file": fld, "peak": peak, "hotspots": spots})

    gmax = max((p["peak"] for p in per_freq if p["peak"]), default=None)
    for p in per_freq:
        p["peak_rel_db"] = round(20 * math.log10(p["peak"] / gmax), 2) if p["peak"] and gmax else None
        p["peak"] = round(p["peak"], 4) if p["peak"] else None

    png, perr = os.path.join(EXPORTS_DIR, f"field_{base}.png"), None
    try:
        an = ["XYZ"[ua] + f" ({mu})", "XYZ"[va] + f" ({mu})"]
        src = ""
        if sources:
            src = "  src: " + ", ".join(k for k, v in sources.items() if not v.startswith("0W"))
        _plot_planes(maps, outl, an, f"{quantity} @ {axis}={position}{src}", float(dynamic_range_db), png)
    except ImportError:
        png, perr = None, "没装 matplotlib/numpy,只出数据不出图(pip install matplotlib)"
    except Exception as e:
        png, perr = None, f"出图失败: {type(e).__name__}: {e}"

    out = {"ok": True, "solution": soln, "quantity": quantity, "plane": f"{axis}={pos:g}{mu}",
           "range": [round(x, 4) for x in rg], "step": [round(su, 5), round(sv, 5)], "unit": mu,
           "frequencies": per_freq, "png": png,
           "outline": {"metal_levels": outl["levels"], "metal_solid_cuts": len(outl["cuts"]),
                       "hidden_round_holes": outl["n_hidden_circles"],
                       "big_solids_not_drawn": outl["big_solids_skipped"]},
           "note": "hotspots.rel_db 相对该频点自身峰值;peak_rel_db 是各频点峰值相对所有频点最大值"}
    if not outl["metal_from_boundaries"]:
        out["outline"]["note"] = "查不到边界分配,所有片都当金属画了(端口面也会画进去)"
    if sources:
        out["sources_set"] = sources
        out["sources_note"] = "Edit Sources 已改成上面的设置,后续远场/场图都沿用它"
    if perr:
        out["plot_error"] = perr
    return out
