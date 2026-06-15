"""求解 + 取结果(native COM 版)。

create_setup → InsertSetup("HfssDriven");create_sweep → InsertFrequencySweep;
analyze → oDesign.Analyze(阻塞,不开子线程,避开 COM 公寓问题);
get_s_parameters → ReportSetup.CreateReport + ExportToFile CSV 再解析。
"""

import os

from . import tool


def _to_unit_str(freq):
    """'2.4GHz' 原样;裸数字当 GHz。"""
    s = str(freq).strip()
    if s and s[-1].isalpha():
        return s
    return s + "GHz"


@tool({
    "type": "function",
    "function": {
        "name": "create_setup",
        "description": "创建求解设置(单频自适应)。扫频前必须先建。frequency 取工作频率。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Setup 名,如 'Setup1'"},
                "frequency": {"type": "string", "description": "自适应频率,带单位(如 '2.4GHz')"},
                "max_passes": {"type": "integer", "default": 10, "description": "最大自适应迭代,默认 10"},
                "max_delta_s": {"type": "number", "default": 0.02, "description": "S 收敛阈值,默认 0.02"},
            },
            "required": ["name", "frequency"],
        },
    },
})
def create_setup(ctx, name, frequency, max_passes=10, max_delta_s=0.02):
    oDesign = ctx["oDesign"]
    try:
        oModule = oDesign.GetModule("AnalysisSetup")
        oModule.InsertSetup("HfssDriven",
            ["NAME:" + name,
             "SolveType:=", "Single",
             "Frequency:=", _to_unit_str(frequency),
             "MaxDeltaS:=", float(max_delta_s),
             "MaximumPasses:=", int(max_passes),
             "MinimumPasses:=", 1,
             "MinimumConvergedPasses:=", 1,
             "PercentRefinement:=", 30,
             "IsEnabled:=", True,
             "BasisOrder:=", 1,
             "DoLambdaRefine:=", True,
             "DoMaterialLambda:=", True,
             "SetLambdaTarget:=", False,
             "Target:=", 0.3333,
             "UseMaxTetIncrease:=", False,
             "PortAccuracy:=", 2,
             "UseABCOnPort:=", False,
             "SetPortMinMaxTri:=", False,
             "UseDomains:=", False,
             "UseIterativeSolver:=", False,
             "SaveRadFieldsOnly:=", False,
             "SaveAnyFields:=", True])
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].setups[name] = {"frequency": frequency, "max_passes": max_passes, "sweeps": []}
    return {"ok": True, "name": name, "frequency": frequency, "max_passes": max_passes}


@tool({
    "type": "function",
    "function": {
        "name": "create_sweep",
        "description": "在已有 setup 上加扫频。Interpolating 最常用(快+准),适合 S11/带宽。",
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "所属 setup 名"},
                "name": {"type": "string", "description": "扫频名,如 'Sweep1'"},
                "start_frequency": {"type": "string", "description": "起始频率,带单位"},
                "stop_frequency": {"type": "string", "description": "终止频率,带单位"},
                "num_points": {"type": "integer", "default": 401, "description": "点数,默认 401"},
                "sweep_type": {"type": "string", "enum": ["Interpolating", "Discrete", "Fast"],
                               "default": "Interpolating"},
            },
            "required": ["setup", "name", "start_frequency", "stop_frequency"],
        },
    },
})
def create_sweep(ctx, setup, name, start_frequency, stop_frequency, num_points=401, sweep_type="Interpolating"):
    oDesign = ctx["oDesign"]
    try:
        oModule = oDesign.GetModule("AnalysisSetup")
        oModule.InsertFrequencySweep(setup,
            ["NAME:" + name,
             "IsEnabled:=", True,
             "RangeType:=", "LinearCount",
             "RangeStart:=", _to_unit_str(start_frequency),
             "RangeEnd:=", _to_unit_str(stop_frequency),
             "RangeCount:=", int(num_points),
             "Type:=", sweep_type,
             "SaveFields:=", False,
             "SaveRadFields:=", False,
             "InterpTolerance:=", 0.5,
             "InterpMaxSolns:=", 250,
             "InterpMinSolns:=", 0,
             "InterpMinSubranges:=", 1,
             "ExtrapToDC:=", False])
    except Exception as e:
        return {"ok": False, "error": f"InsertFrequencySweep 失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].setups.setdefault(setup, {}).setdefault("sweeps", []).append(
            {"name": name, "start": start_frequency, "stop": stop_frequency})
    return {"ok": True, "name": name, "setup": setup,
            "range": [start_frequency, stop_frequency], "points": num_points}


@tool({
    "type": "function",
    "function": {
        "name": "analyze",
        "description": ("运行求解(阻塞,几秒到几分钟)。调用前必须已建 setup + sweep + 至少一个端口。"
                        "完成后用 get_s_parameters 取 S 参数。"),
        "parameters": {
            "type": "object",
            "properties": {"setup": {"type": "string", "description": "要跑的 setup 名;不传则用第一个"}},
        },
    },
})
def analyze(ctx, setup=None):
    import time
    oDesign = ctx["oDesign"]
    setups = list(ctx["state"].setups.keys()) if "state" in ctx else []
    if setup is None:
        if not setups:
            return {"ok": False, "error": "无 setup,先 create_setup + create_sweep"}
        setup = setups[0]
    print(f"  [Solving] {setup} ...")
    t0 = time.time()
    try:
        oDesign.Analyze(setup)   # 阻塞;COM 自动化同步返回
    except Exception as e:
        return {"ok": False, "error": f"Analyze 失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    if "state" in ctx:
        ctx["state"].setups.setdefault(setup, {})["solved"] = True
    return {"ok": True, "setup": setup, "elapsed_sec": round(time.time() - t0, 1)}


@tool({
    "type": "function",
    "function": {
        "name": "get_s_parameters",
        "description": ("取已求解的 S(port,port):谐振频率、最低 S 值、-10dB 带宽。"
                        "导出报告 CSV 再解析。调用前必须已 analyze。"),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "setup 名,不传用第一个"},
                "sweep": {"type": "string", "description": "sweep 名,不传用该 setup 第一个"},
                "port": {"type": "string", "description": "端口名(如 'P1'),不传用第一个"},
                "summary_only": {"type": "boolean", "default": True, "description": "false 附完整频率/S 数组"},
            },
        },
    },
})
def get_s_parameters(ctx, setup=None, sweep=None, port=None, summary_only=True):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")

    # 解析 setup / sweep / port(从 state)
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup"}
    setup = setup or setups[0]
    sw_list = state.setups.get(setup, {}).get("sweeps", []) if state else []
    if sweep is None:
        if not sw_list:
            return {"ok": False, "error": f"setup '{setup}' 下无 sweep"}
        sweep = sw_list[0]["name"]
    ports = list(state.excitations.keys()) if state else []
    if port is None:
        if not ports:
            return {"ok": False, "error": "无端口"}
        port = ports[0]

    soln = f"{setup} : {sweep}"
    expr = f"dB(S({port},{port}))"
    report_name = "S_export_tmp"
    from .session import PROJECTS_DIR
    csv_path = os.path.join(PROJECTS_DIR, f"_{setup}_{sweep}_S.csv")

    # HFSS Modal:context 为空 [](对照 pyaedt standard report);families = ["Freq:=",["All"]];
    # CreateReport 参数个数跨版本有差异,7 参(新)/6 参(老)都试,谁不抛就用谁。
    oModule = oDesign.GetModule("ReportSetup")
    trace = ["X Component:=", "Freq", "Y Component:=", [expr]]
    forms = [
        # 8 参(2019 等老版本要这个,末尾多一个空属性数组)
        (report_name, "Modal Solution Data", "Data Table", soln, [], ["Freq:=", ["All"]], trace, []),
        (report_name, "Modal Solution Data", "Data Table", soln, ["Domain:=", "Sweep"], ["Freq:=", ["All"]], trace, []),
        # 7 参(新版本)
        (report_name, "Modal Solution Data", "Data Table", soln, [], ["Freq:=", ["All"]], trace),
        (report_name, "Modal Solution Data", "Rectangular Plot", soln, [], ["Freq:=", ["All"]], trace),
        (report_name, "Modal Solution Data", "Data Table", soln, [], trace),
    ]
    last_err = None
    created = False
    for args in forms:
        try:
            oModule.CreateReport(*args)
            created = True
            break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    if not created:
        return {"ok": False, "error": f"CreateReport 各形式都失败: {last_err}",
                "hint": f"表达式 {expr} 或端口名可能不匹配;检查端口实际名"}
    try:
        oModule.ExportToFile(report_name, csv_path)
        try:
            oModule.DeleteReports([report_name])
        except Exception:
            pass
    except Exception as e:
        return {"ok": False, "error": f"ExportToFile 失败: {type(e).__name__}: {e}"}

    # 解析 CSV
    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            rows = [ln.rstrip("\n").split(",") for ln in f if ln.strip()]
    except Exception as e:
        return {"ok": False, "error": f"读 CSV 失败: {e}"}
    if len(rows) < 2:
        return {"ok": False, "error": "S 数据为空"}

    header = rows[0]
    data = rows[1:]
    # 第 0 列是频率(含单位标注),第 1 列是 dB(S)
    def _num(x):
        x = x.strip().strip('"')
        try:
            return float(x.split()[0]) if x else None
        except Exception:
            try:
                return float(x)
            except Exception:
                return None
    freqs, s_db = [], []
    for r in data:
        if len(r) < 2:
            continue
        fv, sv = _num(r[0]), _num(r[1])
        if fv is not None and sv is not None:
            freqs.append(fv); s_db.append(sv)
    if not freqs:
        return {"ok": False, "error": "CSV 解析不出数值", "csv_header": header}

    # 按 -10dB 连续频段分组(多谐振:每段是一个独立谐振,带宽按各自频段算,不跨段)
    bands = []   # 每段 [low, high, dip_freq, dip_dB]
    cur = None
    for f, s in zip(freqs, s_db):
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

    summary = {"port": port, "metric": expr, "freq_unit": header[0] if header else "?"}
    if bands:
        bands.sort(key=lambda b: b[2])           # 按谐振频率排序;基模 = 最低频段
        prim = bands[0]                          # 主谐振取基模(论文目标通常是它)
        summary.update({
            "resonant_freq": round(prim[2], 4), "min_value_dB": round(prim[3], 2),
            "bw_-10dB_low": round(prim[0], 4), "bw_-10dB_high": round(prim[1], 4),
            "matched_-10dB": True, "n_resonances": len(bands),
        })
        if len(bands) > 1:                       # 多谐振:全列出,避免把不同模误当超宽带
            summary["resonances"] = [
                {"freq": round(b[2], 4), "min_dB": round(b[3], 2),
                 "bw_low": round(b[0], 4), "bw_high": round(b[1], 4), "bw_span": round(b[1] - b[0], 4)}
                for b in bands]
            summary["note"] = "多个独立 -10dB 谐振,resonant_freq 取基模(最低频);各模带宽见 resonances,勿把模间当超宽带"
    else:
        min_i = min(range(len(s_db)), key=lambda i: s_db[i])   # 没到 -10:报最接近点
        summary.update({
            "resonant_freq": round(freqs[min_i], 4), "min_value_dB": round(s_db[min_i], 2),
            "bw_-10dB_low": None, "bw_-10dB_high": None, "matched_-10dB": False,
            "n_resonances": 0,
        })
    result = {"ok": True, "setup": setup, "sweep": sweep, "summary": summary, "n_points": len(freqs)}
    if not summary_only:
        result["full_data"] = {"freq": [round(f, 6) for f in freqs], "s_dB": [round(s, 4) for s in s_db]}
    return result


def _report_to_csv(oDesign, soln, exprs, csv_path):
    """多 arity CreateReport(re/im 等表达式)→ ExportToFile CSV。返回 (ok, err)。
    跨版本:2019=8 参,2025=7 参,都试。"""
    oModule = oDesign.GetModule("ReportSetup")
    rname = "metrics_tmp"
    trace = ["X Component:=", "Freq", "Y Component:=", list(exprs)]
    forms = [
        (rname, "Modal Solution Data", "Data Table", soln, [], ["Freq:=", ["All"]], trace, []),
        (rname, "Modal Solution Data", "Data Table", soln, [], ["Freq:=", ["All"]], trace),
        (rname, "Modal Solution Data", "Data Table", soln, [], trace),
    ]
    last = None
    for args in forms:
        try:
            oModule.CreateReport(*args)
            oModule.ExportToFile(rname, csv_path)
            try:
                oModule.DeleteReports([rname])
            except Exception:
                pass
            return True, None
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return False, last


@tool({
    "type": "function",
    "function": {
        "name": "get_input_metrics",
        "description": ("从复数 S(port,port) 取天线输入指标:VSWR、输入阻抗 Zin(R+jX 欧姆)、"
                        "阻抗带宽(默认 VSWR<2)。比 get_s_parameters 多了 Zin/VSWR。调用前必须已 analyze。"),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string"}, "sweep": {"type": "string"}, "port": {"type": "string"},
                "z0": {"type": "number", "default": 50, "description": "参考阻抗 Ω,默认 50"},
                "vswr_max": {"type": "number", "default": 2.0, "description": "带宽判据 VSWR<此值,默认 2"},
            },
        },
    },
})
def get_input_metrics(ctx, setup=None, sweep=None, port=None, z0=50, vswr_max=2.0):
    import math
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup"}
    setup = setup or setups[0]
    sws = state.setups.get(setup, {}).get("sweeps", []) if state else []
    if sweep is None:
        if not sws:
            return {"ok": False, "error": f"setup '{setup}' 下无 sweep"}
        sweep = sws[0]["name"]
    ports = list(state.excitations.keys()) if state else []
    if port is None:
        if not ports:
            return {"ok": False, "error": "无端口"}
        port = ports[0]

    soln = f"{setup} : {sweep}"
    from .session import PROJECTS_DIR
    csv_path = os.path.join(PROJECTS_DIR, f"_{setup}_{sweep}_Zin.csv")
    ok, err = _report_to_csv(oDesign, soln, [f"re(S({port},{port}))", f"im(S({port},{port}))"], csv_path)
    if not ok:
        return {"ok": False, "error": f"导出 re/im(S) 报告失败: {err}"}
    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            rows = [ln.rstrip("\n").split(",") for ln in f if ln.strip()]
    except Exception as e:
        return {"ok": False, "error": f"读 CSV 失败: {e}"}
    if len(rows) < 2:
        return {"ok": False, "error": "数据为空"}

    def num(x):
        x = x.strip().strip('"')
        try:
            return float(x.split()[0]) if x else None
        except Exception:
            try:
                return float(x)
            except Exception:
                return None
    freqs, re, im = [], [], []
    for r in rows[1:]:
        if len(r) < 3:
            continue
        f0, rr, ii = num(r[0]), num(r[1]), num(r[2])
        if None not in (f0, rr, ii):
            freqs.append(f0); re.append(rr); im.append(ii)
    if not freqs:
        return {"ok": False, "error": "CSV 解析不出数值", "csv_header": rows[0]}

    mags = [math.hypot(a, b) for a, b in zip(re, im)]
    vswr = [((1 + g) / (1 - g)) if g < 1 else float("inf") for g in mags]
    i0 = min(range(len(mags)), key=lambda i: mags[i])
    num_c = complex(1 + re[i0], im[i0]); den_c = complex(1 - re[i0], -im[i0])
    zin = z0 * num_c / den_c if abs(den_c) > 1e-12 else complex(0, 0)
    inb = [f for f, v in zip(freqs, vswr) if v < vswr_max]
    bw_low, bw_high = (inb[0], inb[-1]) if inb else (None, None)
    center = (bw_low + bw_high) / 2 if inb else None
    span = (bw_high - bw_low) if inb else None
    return {"ok": True, "setup": setup, "sweep": sweep, "summary": {
        "port": port, "z0_ohm": z0,
        "resonant_freq": round(freqs[i0], 4),
        "at_resonance": {
            "VSWR": round(vswr[i0], 3) if vswr[i0] != float("inf") else None,
            "Zin_real_ohm": round(zin.real, 2), "Zin_imag_ohm": round(zin.imag, 2),
        },
        "bandwidth": {"criterion": f"VSWR<{vswr_max}",
                      "low": round(bw_low, 4) if bw_low is not None else None,
                      "high": round(bw_high, 4) if bw_high is not None else None,
                      "center": round(center, 4) if center is not None else None,
                      "span": round(span, 4) if span is not None else None,
                      "fractional_pct": round(span / center * 100, 2) if center else None,
                      "matched": bw_low is not None},
    }}


_POL = {"total": "Total", "lhcp": "LHCP", "rhcp": "RHCP", "theta": "Theta", "phi": "Phi"}


@tool({
    "type": "function",
    "function": {
        "name": "get_radiation_pattern",
        "description": ("导出远场方向图:增益(dB) vs theta,按 phi 切面(默认 E面0°/H面90°)。"
                        "返回每刀 theta/gain 数组+峰值。调用前必须已 analyze,且 design 有 create_open_region + create_infinite_sphere。"),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
                "sphere": {"type": "string", "default": "Sphere1"},
                "phi_cuts": {"type": "array", "items": {"type": "string"},
                             "description": "phi 切面列表带 deg,默认 ['0deg','90deg']"},
                "gain_type": {"type": "string", "enum": ["realized", "total"], "default": "realized"},
                "polarization": {"type": "string", "enum": ["total", "lhcp", "rhcp", "theta", "phi"], "default": "total"},
            },
        },
    },
})
def get_radiation_pattern(ctx, setup=None, sweep="LastAdaptive", sphere="Sphere1",
                          phi_cuts=None, gain_type="realized", polarization="total"):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup"}
    setup = setup or setups[0]
    if not phi_cuts:
        phi_cuts = ["0deg", "90deg"]
    suffix = _POL.get(polarization, "Total")
    expr = f"dB({'Realized' if gain_type == 'realized' else ''}Gain{suffix})"
    soln = f"{setup} : {sweep}"
    oModule = oDesign.GetModule("ReportSetup")
    from .session import PROJECTS_DIR

    cuts = []
    for phi in phi_cuts:
        rname = "ff_tmp"
        csv_path = os.path.join(PROJECTS_DIR, f"_ff_{phi}.csv")
        fam = ["Theta:=", ["All"], "Phi:=", [str(phi)], "Freq:=", ["All"]]
        trace = ["X Component:=", "Theta", "Y Component:=", [expr]]
        forms = [
            (rname, "Far Fields", "Data Table", soln, ["Context:=", sphere], fam, trace, []),
            (rname, "Far Fields", "Data Table", soln, ["Context:=", sphere], fam, trace),
        ]
        last = None
        done = False
        for args in forms:
            try:
                oModule.CreateReport(*args)
                oModule.ExportToFile(rname, csv_path)
                try:
                    oModule.DeleteReports([rname])
                except Exception:
                    pass
                done = True
                break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
        if not done:
            return {"ok": False, "error": f"远场报告失败 (phi={phi}): {last}",
                    "hint": "确认已 analyze 且有 create_infinite_sphere + open_region"}
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                rows = [ln.rstrip("\n").split(",") for ln in f if ln.strip()]
        except Exception as e:
            return {"ok": False, "error": f"读 CSV 失败: {e}"}
        thetas, gains = [], []
        for r in rows[1:]:
            if len(r) < 2:
                continue
            try:
                thetas.append(float(r[0].strip().strip('"').split()[0]))
                gains.append(float(r[1].strip().strip('"').split()[0]))
            except Exception:
                continue
        if not thetas:
            return {"ok": False, "error": f"远场数据空 (phi={phi})", "csv_header": rows[0] if rows else None}
        pk = max(gains); pi = gains.index(pk)
        cuts.append({"phi": str(phi), "theta_deg": [round(t, 2) for t in thetas],
                     "gain_dB": [round(g, 3) for g in gains],
                     "peak_gain_dB": round(pk, 2), "peak_theta_deg": round(thetas[pi], 2),
                     "n_points": len(thetas)})
    return {"ok": True, "setup": setup, "sphere": sphere, "gain_type": gain_type,
            "polarization": polarization, "metric": expr, "n_cuts": len(cuts), "cuts": cuts}
