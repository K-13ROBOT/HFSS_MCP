"""参数扫描(native COM 版)—— oDesign.GetModule("Optimetrics")。

create/run + 结果提取(S11 + 远场指标,报告导出带 variation 列再按 variation 分组)。
关键:Optimetrics setup 求解走 Optimetrics.SolveSetup(name),不是 oDesign.Analyze。
"""

import os as _os
import time

from . import tool

_POL = {"total": "Total", "lhcp": "LHCP", "rhcp": "RHCP", "theta": "Theta", "phi": "Phi"}
_CROSS = {"lhcp": "rhcp", "rhcp": "lhcp", "theta": "phi", "phi": "theta"}


def _opti(ctx):
    return ctx["oDesign"].GetModule("Optimetrics")


@tool({
    "type": "function",
    "function": {
        "name": "create_parametric_sweep",
        "description": ("建参数扫描(Optimetrics Parametric):若干变量离散取值做笛卡尔组合,一次求解全部。"
                        "variables=[{name, values:[...]}](值带单位)。组合数=各取值数乘积,别贪大。"
                        "要远场指标(gain/AR/HPBW/F-B/隔离)必须 save_fields=True。建完用 run_parametric_sweep。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "参扫名,如 'PS1'"},
                "variables": {
                    "type": "array",
                    "items": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "values": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    }, "required": ["name", "values"]},
                    "minItems": 1,
                    "description": "扫描变量及离散取值,如 [{'name':'PL','values':['28mm','30mm','32mm']}]",
                },
                "setup": {"type": "string", "description": "求解 setup 名,不传用第一个"},
                "save_fields": {"type": "boolean", "default": False,
                                "description": "是否给每组合存场(要远场指标必须 True)"},
            },
            "required": ["name", "variables"],
        },
    },
})
def create_parametric_sweep(ctx, name, variables, setup=None, save_fields=False):
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup,先 create_setup"}
    setup = setup or setups[0]

    # 表达式型变量(如 '0.1*109.1mm'、'MH1-1mm')直接进 OptiParametric 会 InsertSetup com_error。
    # 建参扫前先把每个被扫变量钉成它求值后的纯数值(单位保留),避免崩;只读单值不影响下游引用。
    oDesign = ctx["oDesign"]
    pinned = []
    for v in variables:
        defn = ctx["state"].variables.get(v["name"]) if (state and v["name"] in getattr(state, "variables", {})) else None
        try:
            evaluated = str(oDesign.GetVariableValue(v["name"]))
        except Exception:
            evaluated = None
        # defn 缺失时退而看求值结果;只要"定义"不是纯数值字面量,就钉成求值后的纯数值
        ref = defn if defn is not None else evaluated
        if ref is not None and not _NUM_LIT.match(ref.strip()) and evaluated and _NUM_LIT.match(evaluated.strip()):
            try:
                oDesign.ChangeProperty(
                    ["NAME:AllTabs",
                     ["NAME:LocalVariableTab",
                      ["NAME:PropServers", "LocalVariables"],
                      ["NAME:ChangedProps", ["NAME:" + v["name"], "Value:=", evaluated]]]])
                if state is not None:
                    state.variables[v["name"]] = evaluated
                pinned.append({v["name"]: f"{ref} → {evaluated}"})
            except Exception:
                pass  # 钉不动就交给 InsertSetup,真崩了会在下面报出来

    sweeps_arg = ["NAME:Sweeps"]
    for v in variables:
        data = " ".join(str(x) for x in v["values"])
        sweeps_arg.append(["NAME:SweepDefinition", "Variable:=", v["name"], "Data:=", data,
                           "OffsetF1:=", False, "Synchronize:=", 0])
    arg = ["NAME:" + name, "IsEnabled:=", True,
           ["NAME:ProdOptiSetupDataV2", "SaveFields:=", bool(save_fields), "CopyMesh:=", False,
            "SolveWithCopiedMeshOnly:=", True],
           ["NAME:StartingPoint"], "Sim. Setups:=", [setup], sweeps_arg,
           ["NAME:Sweep Operations"], ["NAME:Goals"]]
    try:
        _opti(ctx).InsertSetup("OptiParametric", arg)
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup(OptiParametric) 失败: {type(e).__name__}: {e}"}

    n = 1
    for v in variables:
        n *= len(v["values"])
    if state is not None:
        if not hasattr(state, "parametrics"):
            state.parametrics = {}
        state.parametrics[name] = {"variables": variables, "setup": setup, "save_fields": bool(save_fields)}
    out = {"ok": True, "name": name, "setup": setup, "n_combinations": n,
           "variables": [v["name"] for v in variables], "save_fields": bool(save_fields)}
    if pinned:
        out["pinned_to_numeric"] = pinned
        out["note_pinned"] = "被扫变量原为表达式,已钉成求值后的纯数值(否则 OptiParametric 会 InsertSetup 失败)。"
    return out


@tool({
    "type": "function",
    "function": {
        "name": "run_parametric_sweep",
        "description": ("运行参数扫描。**阻塞**,组合多很久。调用前须 create_parametric_sweep。"
                        "跑完用 get_parametric_results / get_parametric_gain 等取各组合指标。"),
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
})
def run_parametric_sweep(ctx, name):
    print(f"  [Parametric solving] {name} ...")
    t0 = time.time()
    try:
        _opti(ctx).SolveSetup(name)   # Optimetrics 走 SolveSetup,不是 oDesign.Analyze
    except Exception as e:
        return {"ok": False, "error": f"参扫求解失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    state = ctx.get("state")
    if state is not None and hasattr(state, "parametrics") and name in state.parametrics:
        state.parametrics[name]["solved"] = True
    return {"ok": True, "name": name, "elapsed_sec": round(time.time() - t0, 1)}


# ────────────────────────── 结果提取 ──────────────────────────

def _csv_dir():
    from .session import EXPORTS_DIR
    return EXPORTS_DIR


def _num(x):
    try:
        return float(str(x).strip().strip('"').split()[0])
    except Exception:
        return None


def _variations(ctx, name):
    """返回 (变量名列表, [variation_dict,...] 笛卡尔积)。未知参扫返回 (None, None)。"""
    import itertools
    st = ctx.get("state")
    if not (st and hasattr(st, "parametrics") and name in st.parametrics):
        return None, None
    vs = st.parametrics[name]["variables"]
    names = [v["name"] for v in vs]
    combos = [dict(zip(names, c)) for c in itertools.product(*[v["values"] for v in vs])]
    return names, combos


def _pin_fam(pin):
    """把每个 swept 变量钉到单值的 family 片段(报告里只留该 variation 一行)。"""
    fam = []
    for k, v in pin.items():
        fam += [f"{k}:=", [str(v)]]
    return fam


import re as _re_mod
_NUMRE = _re_mod.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _fnum(s):
    """从带单位字符串抽前导数值,如 '2.04GHz'→2.04、'180deg'→180。"""
    m = _NUMRE.search(str(s))
    return float(m.group()) if m else None


# 纯数值字面量(带可选单位),如 '14.73mm'、'-3'、'2.4GHz';表达式(含 *、+、变量名等)不匹配。
_NUM_LIT = _re_mod.compile(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*[a-zA-Z]*$")


def _bands(pts):
    """pts=[(freq, s_dB), ...] 已按 freq 升序;返回连续 -10dB 段 [[low, high, dip_f, dip_dB], ...]。
    与 analysis.get_s_parameters 同一套分段逻辑,用来暴露双谐振中间的 -10dB 洞(别当连续超宽带)。"""
    bands, cur = [], None
    for f, s in pts:
        if s <= -10.0:
            if cur is None:
                cur = [f, f, f, s]
            else:
                cur[1] = f
                if s < cur[3]:
                    cur[2], cur[3] = f, s
        elif cur is not None:
            bands.append(cur); cur = None
    if cur is not None:
        bands.append(cur)
    return bands


def _with_fails(resp, fails):
    """把逐组失败信息挂到返回里(部分组合出报告失败时,仍返回成功组,不让一组炸毁全盘)。"""
    if fails:
        resp["n_failed"] = len(fails)
        resp["failed_variations"] = fails
        resp["note_failed"] = "部分组合出报告失败,已跳过,仅返回成功组(失败组见 failed_variations)。"
    return resp


def _param_report(oDesign, category, soln, context, families, trace, csv_path):
    """参扫报告 CreateReport(+context 远场)→ ExportToFile。返回 (ok, err)。
    跨版本 8 参(老)/7 参(新)都试;真生成文件才算成功。"""
    oM = oDesign.GetModule("ReportSetup")
    rn = "param_tmp"
    ctx_arg = ["Context:=", context] if context else []
    if _os.path.exists(csv_path):
        try:
            _os.remove(csv_path)
        except Exception:
            pass
    forms = [
        (rn, category, "Data Table", soln, ctx_arg, families, trace, []),
        (rn, category, "Data Table", soln, ctx_arg, families, trace),
    ]
    last = None
    for a in forms:
        try:
            oM.CreateReport(*a)
            oM.ExportToFile(rn, csv_path)
            try:
                oM.DeleteReports([rn])
            except Exception:
                pass
            if _os.path.exists(csv_path):   # 真生成了才算成功
                return True, None
            last = "CreateReport/ExportToFile 没报错但没生成文件(报告可能空)"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return False, last


def _parse_wide(csv_path, x_key, var_vals=None):
    """解析钉单值后的宽表:intrinsic(Freq/Theta)沿列铺开。
    每个 Y 列表头形如 "dB(S(P1,P1)) [] - Freq='2.04GHz'" —— X 值从表头 `x_key='...'` 取,
    Y 值从数据行对应单元取。var_vals 给定时按前导变量列匹配该 variation 行,否则取第一行。
    返回 [(x, y), ...](按 x 升序)。
    注意:表头里的表达式含逗号(如 S(P1,P1)),必须用 csv 模块按引号切分,
    否则该字段被拆成两列、表头与数据行错位 → freq 标签与 S 值对不上。"""
    import csv as _csv
    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        rows = [r for r in _csv.reader(f) if r]
    if len(rows) < 2:
        return []
    header = rows[0]
    datarow = None
    if var_vals:
        n = len(var_vals)
        want = [_fnum(v) for v in var_vals]
        for r in rows[1:]:
            if len(r) >= n and all(_num(r[k]) == want[k] for k in range(n)):
                datarow = r
                break
    if datarow is None:
        datarow = rows[1]
    pat = _re_mod.compile(_re_mod.escape(x_key) + r"='([^']*)'")
    out = []
    for j, h in enumerate(header):
        m = pat.search(h)
        if not m or j >= len(datarow):
            continue
        xv, yv = _fnum(m.group(1)), _num(datarow[j])
        if xv is not None and yv is not None:
            out.append((xv, yv))
    out.sort(key=lambda t: t[0])
    return out


def _resolve_sweep(ctx, setup, sweep):
    """sweep 为 'LastAdaptive' 时,若 setup 下有频率扫频则改用第一个(S11 谐振要扫频)。"""
    if sweep and sweep != "LastAdaptive":
        return sweep
    st = ctx.get("state")
    sws = st.setups.get(setup, {}).get("sweeps", []) if st else []
    return sws[0]["name"] if sws else (sweep or "LastAdaptive")


def _gain_expr(gain_type, pol):
    return f"dB({'Realized' if gain_type == 'realized' else ''}Gain{_POL.get(pol, 'Total')})"


@tool({"type": "function", "function": {
    "name": "get_parametric_results",
    "description": "取参扫各组合 S11 指标(谐振频率、最低 S 值)。须先 run_parametric_sweep。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "setup": {"type": "string"},
        "sweep": {"type": "string", "default": "LastAdaptive"}, "port": {"type": "string"}},
        "required": ["parametric"]}}})
def get_parametric_results(ctx, parametric, setup=None, sweep="LastAdaptive", port=None):
    st = ctx.get("state")
    names, variations = _variations(ctx, parametric)
    if not names:
        return {"ok": False, "error": f"参扫 '{parametric}' 未知或无变量"}
    setup = setup or (list(st.setups.keys())[0] if st and st.setups else None)
    port = port or (list(st.excitations.keys())[0] if st and st.excitations else None)
    if not setup or not port:
        return {"ok": False, "error": "缺 setup 或 port"}
    sweep = _resolve_sweep(ctx, setup, sweep)
    soln = f"{setup} : {sweep}"
    expr = f"dB(S({port},{port}))"
    trace = ["X Component:=", "Freq", "Y Component:=", [expr]]
    oDesign = ctx["oDesign"]
    # 逐 variation 钉单值(稳定,不改 nominal),宽表里按表头 Freq='..' 抽频率 + 数据行抽 S。
    # 单组失败不再让整份报告作废:跳过该组、继续读成功组,失败组单列 error。
    res, fails = [], []
    for i, vd in enumerate(variations):
        csv = _os.path.join(_csv_dir(), f"_par_{parametric}_S_{i}.csv")
        fam = _pin_fam(vd) + ["Freq:=", ["All"]]
        ok, err = _param_report(oDesign, "Modal Solution Data", soln, None, fam, trace, csv)
        if not ok:
            fails.append({"variation": vd, "error": err})
            res.append({"variation": vd, "resonant_freq": None, "min_S_dB": None, "error": err})
            continue
        pts = _parse_wide(csv, "Freq", list(vd.values()))
        if not pts:
            res.append({"variation": vd, "resonant_freq": None, "min_S_dB": None})
            continue
        fmin, smin = min(pts, key=lambda t: t[1])
        bands = _bands(pts)                          # 连续 -10dB 段,暴露双谐振中间的洞
        entry = {"variation": vd, "resonant_freq": round(fmin, 4), "min_S_dB": round(smin, 2),
                 "matched_-10dB": bool(bands), "n_resonances": len(bands)}
        if bands:
            bands.sort(key=lambda b: b[2])           # 基模 = 最低频段
            prim = bands[0]
            entry["bw_-10dB_low"] = round(prim[0], 4)
            entry["bw_-10dB_high"] = round(prim[1], 4)
            if len(bands) > 1:                       # 多段:别当连续超宽带,各段都列出
                entry["resonances"] = [
                    {"freq": round(b[2], 4), "min_dB": round(b[3], 2),
                     "bw_low": round(b[0], 4), "bw_high": round(b[1], 4)} for b in bands]
                entry["note"] = "多个独立 -10dB 段(中间有洞),bw 为基模段,勿当连续超宽带。"
        else:
            entry["bw_-10dB_low"] = None
            entry["bw_-10dB_high"] = None
        res.append(entry)
    return _with_fails({"ok": True, "parametric": parametric, "setup": setup, "sweep": sweep,
                        "n_variations": len(res), "results": res}, fails)


def _ff_metric(ctx, parametric, expr, sphere, setup, sweep, phi=None, reduce_fn=max):
    """逐 variation 钉单值取远场 Theta 切面长表。
    返回 (out, fails):out=[(variation_dict, [((theta,), val), ...], reduced_val), ...](含所有组合,
    失败组 pts=[]、reduced=None);fails=[{variation, error}, ...]。
    硬错(参扫未知)返回 (None, err_str)。单组失败不再让整份报告作废。"""
    st = ctx.get("state")
    names, variations = _variations(ctx, parametric)
    if not names:
        return None, f"参扫 '{parametric}' 未知或无变量"
    setup = setup or (list(st.setups.keys())[0] if st and st.setups else None)
    soln = f"{setup} : {sweep}"
    trace = ["X Component:=", "Theta", "Y Component:=", [expr]]
    oDesign = ctx["oDesign"]
    # 逐 variation 钉单值(稳定);宽表表头 Theta='5deg' 抽角度 + 数据行抽增益。
    out, fails = [], []
    for i, vd in enumerate(variations):
        csv = _os.path.join(_csv_dir(), f"_par_{parametric}_ff_{i}.csv")
        fam = _pin_fam(vd) + ["Theta:=", ["All"], "Phi:=", [str(phi)] if phi else ["All"], "Freq:=", ["All"]]
        ok, err = _param_report(oDesign, "Far Fields", soln, sphere, fam, trace, csv)
        if not ok:
            out.append((vd, [], None))
            fails.append({"variation": vd, "error": err})
            continue
        pts = [((t,), v) for t, v in _parse_wide(csv, "Theta", list(vd.values()))]
        vals = [v for _, v in pts]
        out.append((vd, pts, reduce_fn(vals) if vals else None))
    return out, fails


@tool({"type": "function", "function": {
    "name": "get_parametric_gain",
    "description": "取参扫各组合远场峰值增益(dB)。须 save_fields=True 跑参扫 + Infinite Sphere。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "sphere": {"type": "string", "default": "Sphere1"},
        "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
        "gain_type": {"type": "string", "enum": ["realized", "total"], "default": "realized"},
        "polarization": {"type": "string", "enum": ["total", "lhcp", "rhcp", "theta", "phi"], "default": "total"}},
        "required": ["parametric"]}}})
def get_parametric_gain(ctx, parametric, sphere="Sphere1", setup=None, sweep="LastAdaptive",
                        gain_type="realized", polarization="total"):
    out, fails = _ff_metric(ctx, parametric, _gain_expr(gain_type, polarization), sphere, setup, sweep)
    if out is None:
        return {"ok": False, "error": f"远场增益报告失败: {fails}"}
    res = []
    for var, pts, pk in out:
        bs = [v for i, v in pts if i and abs(i[0]) < 1e-3]
        res.append({"variation": var, "peak_gain_dB": round(pk, 2) if pk is not None else None,
                    "broadside_gain_dB": round(max(bs), 2) if bs else None})
    return _with_fails({"ok": True, "parametric": parametric, "gain_type": gain_type,
                        "polarization": polarization, "n_variations": len(res), "results": res}, fails)


@tool({"type": "function", "function": {
    "name": "get_parametric_axial_ratio",
    "description": "取参扫各组合最小轴比 AR(dB),CP 天线核心。AR<3dB 为良好 CP。须 save_fields + Sphere。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "sphere": {"type": "string", "default": "Sphere1"},
        "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
        "threshold_dB": {"type": "number", "default": 3.0}}, "required": ["parametric"]}}})
def get_parametric_axial_ratio(ctx, parametric, sphere="Sphere1", setup=None, sweep="LastAdaptive", threshold_dB=3.0):
    out, fails = _ff_metric(ctx, parametric, "dB(AxialRatioValue)", sphere, setup, sweep, reduce_fn=min)
    if out is None:
        return {"ok": False, "error": f"轴比报告失败: {fails}"}
    res = []
    for var, pts, best in out:
        bs = [v for i, v in pts if i and abs(i[0]) < 1e-3]
        res.append({"variation": var, "best_AR_dB": round(best, 2) if best is not None else None,
                    "broadside_AR_dB": round(min(bs), 2) if bs else None,
                    "is_CP_at_broadside": bool(bs and min(bs) < threshold_dB)})
    return _with_fails({"ok": True, "parametric": parametric, "n_variations": len(res), "results": res}, fails)


@tool({"type": "function", "function": {
    "name": "get_parametric_front_to_back",
    "description": "取参扫各组合前后比(broadside θ≈0 − 背向 θ≈180 增益,dB)。须 save_fields + Sphere。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "sphere": {"type": "string", "default": "Sphere1"},
        "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
        "gain_type": {"type": "string", "enum": ["realized", "total"], "default": "realized"},
        "polarization": {"type": "string", "enum": ["total", "lhcp", "rhcp", "theta", "phi"], "default": "total"}},
        "required": ["parametric"]}}})
def get_parametric_front_to_back(ctx, parametric, sphere="Sphere1", setup=None, sweep="LastAdaptive",
                                 gain_type="realized", polarization="total"):
    out, fails = _ff_metric(ctx, parametric, _gain_expr(gain_type, polarization), sphere, setup, sweep, phi="0deg")
    if out is None:
        return {"ok": False, "error": f"前后比报告失败: {fails}"}
    res = []
    for var, pts, _ in out:
        front = [v for i, v in pts if i and abs(i[0]) < 2]
        back = [v for i, v in pts if i and abs(i[0] - 180) < 2]
        res.append({"variation": var,
                    "front_to_back_dB": round(max(front) - max(back), 2) if front and back else None})
    return _with_fails({"ok": True, "parametric": parametric, "n_variations": len(res), "results": res}, fails)


@tool({"type": "function", "function": {
    "name": "get_parametric_hpbw",
    "description": "取参扫各组合半功率波束宽度 HPBW(度,指定 phi 切面)。须 save_fields + Sphere。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "phi_cut": {"type": "string", "default": "0deg"},
        "sphere": {"type": "string", "default": "Sphere1"}, "setup": {"type": "string"},
        "sweep": {"type": "string", "default": "LastAdaptive"},
        "gain_type": {"type": "string", "enum": ["realized", "total"], "default": "realized"},
        "polarization": {"type": "string", "enum": ["total", "lhcp", "rhcp", "theta", "phi"], "default": "total"}},
        "required": ["parametric"]}}})
def get_parametric_hpbw(ctx, parametric, phi_cut="0deg", sphere="Sphere1", setup=None, sweep="LastAdaptive",
                        gain_type="realized", polarization="total"):
    out, fails = _ff_metric(ctx, parametric, _gain_expr(gain_type, polarization), sphere, setup, sweep, phi=phi_cut)
    if out is None:
        return {"ok": False, "error": f"HPBW 报告失败: {fails}"}
    res = []
    for var, pts, _ in out:
        tg = sorted([(i[0], v) for i, v in pts if i], key=lambda t: t[0])
        if not tg:
            res.append({"variation": var, "HPBW_deg": None}); continue
        pi = max(range(len(tg)), key=lambda k: tg[k][1]); pkt, pkg = tg[pi]; half = pkg - 3.0
        left = tg[0][0]
        for k in range(pi, 0, -1):
            if tg[k][1] >= half > tg[k - 1][1]:
                left = tg[k - 1][0] + (tg[k][0] - tg[k - 1][0]) * (half - tg[k - 1][1]) / (tg[k][1] - tg[k - 1][1]); break
        right = tg[-1][0]
        for k in range(pi, len(tg) - 1):
            if tg[k][1] >= half > tg[k + 1][1]:
                right = tg[k][0] + (tg[k + 1][0] - tg[k][0]) * (tg[k][1] - half) / (tg[k][1] - tg[k + 1][1]); break
        res.append({"variation": var, "peak_gain_dB": round(pkg, 2), "HPBW_deg": round(abs(right - left), 1)})
    return _with_fails({"ok": True, "parametric": parametric, "phi_cut": phi_cut,
                        "n_variations": len(res), "results": res}, fails)


@tool({"type": "function", "function": {
    "name": "get_parametric_cross_pol_isolation",
    "description": "取参扫各组合共/交叉极化隔离(broadside co 增益 − cross 增益,dB)。须 save_fields + Sphere。",
    "parameters": {"type": "object", "properties": {
        "parametric": {"type": "string"}, "co_pol": {"type": "string", "enum": ["lhcp", "rhcp", "theta", "phi"]},
        "sphere": {"type": "string", "default": "Sphere1"}, "setup": {"type": "string"},
        "sweep": {"type": "string", "default": "LastAdaptive"},
        "gain_type": {"type": "string", "enum": ["realized", "total"], "default": "realized"}},
        "required": ["parametric", "co_pol"]}}})
def get_parametric_cross_pol_isolation(ctx, parametric, co_pol, sphere="Sphere1", setup=None,
                                       sweep="LastAdaptive", gain_type="realized"):
    cx = _CROSS.get(co_pol)
    if not cx:
        return {"ok": False, "error": f"co_pol 不合法: {co_pol}"}
    co_out, f1 = _ff_metric(ctx, parametric, _gain_expr(gain_type, co_pol), sphere, setup, sweep, phi="0deg")
    if co_out is None:
        return {"ok": False, "error": f"co 报告失败: {f1}"}
    cx_out, f2 = _ff_metric(ctx, parametric, _gain_expr(gain_type, cx), sphere, setup, sweep, phi="0deg")
    if cx_out is None:
        return {"ok": False, "error": f"cross 报告失败: {f2}"}
    cx_map = {tuple(sorted(v.items())): pts for v, pts, _ in cx_out}
    res = []
    for var, co_pts, _ in co_out:
        co_bs = [v for i, v in co_pts if i and abs(i[0]) < 2]
        cx_bs = [v for i, v in cx_map.get(tuple(sorted(var.items())), []) if i and abs(i[0]) < 2]
        res.append({"variation": var, "co_pol": co_pol, "cross_pol": cx,
                    "isolation_dB": round(max(co_bs) - max(cx_bs), 2) if co_bs and cx_bs else None})
    return _with_fails({"ok": True, "parametric": parametric, "n_variations": len(res), "results": res},
                       (f1 or []) + (f2 or []))
