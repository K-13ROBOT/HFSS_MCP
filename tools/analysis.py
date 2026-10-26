"""求解 + 取结果(native COM 版)。

create_setup → InsertSetup("HfssDriven");create_sweep → InsertFrequencySweep;
analyze → oDesign.Analyze(阻塞,不开子线程,避开 COM 公寓问题);
get_s_parameters → ReportSetup.CreateReport + ExportToFile CSV 再解析。
"""

import io
import os
import re

from . import tool, resolve_setup


def _drop_stale(csv_path):
    """导出前删掉同名旧 CSV。没有解时 CreateReport/ExportToFile 不报错、只是不写文件,
    不删的话后面会把上一次的旧数据当成这次的结果读回来。"""
    try:
        os.remove(csv_path)
    except OSError:
        pass


_NO_DATA = "报告建出来了但没导出数据 —— 这个变量组合/扫频多半没有解(改了变量或几何后需要重新 analyze)"


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
                "min_converged_passes": {"type": "integer", "default": 1,
                                         "description": "要求**连续几遍**满足 max_delta_s 才判收敛,默认 1。"
                                                        "只要求 1 遍时,网格还粗、恰好两遍都没解对也会判收敛"
                                                        "(实测:ΔS 0.03 + 1 遍,第 5 遍 39k 网格就判了收敛,是假的)。"
                                                        "**做网格校准时用 2**;日常调参为了快可以留 1"},
                "frequencies": {"type": "array", "items": {"type": "string"},
                                "description": "可选:多频点自适应(如 ['1.52GHz','1.672GHz']),每点都用 max_delta_s 判收敛,"
                                               "此时 frequency 被忽略。双频/多频天线、尤其含窄带高Q 模时用它——"
                                               "单频自适应只保证该频点收敛,离它远的窄谐振位置可能随网格漂移。"},
            },
            "required": ["name", "frequency"],
        },
    },
})
def create_setup(ctx, name, frequency, max_passes=10, max_delta_s=0.02, frequencies=None,
                 min_converged_passes=1):
    oDesign = ctx["oDesign"]
    if frequencies:
        # 键名照 AEDT 2025.2 录制脚本(Nuhertz Dual8Ports.py):频点表是 NAME: 嵌套数组,
        # 写成 "MultipleAdaptiveFreqsSetup:=" 键值对会被静默忽略,退化成 Broadband 2–20GHz
        freq_args = ["SolveType:=", "MultiFrequency",
                     ["NAME:MultipleAdaptiveFreqsSetup"] +
                     [["NAME:AdaptAt", "Frequency:=", _to_unit_str(f), "Delta:=", float(max_delta_s)]
                      for f in frequencies]]
    else:
        freq_args = ["SolveType:=", "Single",
                     "Frequency:=", _to_unit_str(frequency),
                     "MaxDeltaS:=", float(max_delta_s)]
    try:
        oModule = oDesign.GetModule("AnalysisSetup")
        oModule.InsertSetup("HfssDriven",
            ["NAME:" + name] + freq_args + [
             "MaximumPasses:=", int(max_passes),
             "MinimumPasses:=", 1,
             "MinimumConvergedPasses:=", int(min_converged_passes),
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
    out = {"ok": True, "name": name, "frequency": frequency, "max_passes": max_passes}
    if frequencies:
        out["frequencies"] = list(frequencies)
    return out


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
                "save_rad_fields": {"type": "boolean", "default": False,
                                    "description": "保存辐射场(理论上比 save_fields 省盘)。**实测 2025.2 上单独设它不生效**"
                                                   "——S 参数有解但远场报告报 com_error。要在扫频上取远场量"
                                                   "(增益/轴比 vs 频率,如 get_axial_ratio)请改传 save_fields=True。"},
                "save_fields": {"type": "boolean", "default": False,
                                "description": "保存完整场(很占盘)。只看 S 参数/远场时不需要。"},
            },
            "required": ["setup", "name", "start_frequency", "stop_frequency"],
        },
    },
})
def create_sweep(ctx, setup, name, start_frequency, stop_frequency, num_points=401,
                 sweep_type="Interpolating", save_rad_fields=False, save_fields=False):
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
             "SaveFields:=", bool(save_fields),
             "SaveRadFields:=", bool(save_rad_fields or save_fields),
             "InterpTolerance:=", 0.5,
             "InterpMaxSolns:=", 250,
             "InterpMinSolns:=", 0,
             "InterpMinSubranges:=", 1,
             "ExtrapToDC:=", False])
    except Exception as e:
        return {"ok": False, "error": f"InsertFrequencySweep 失败: {type(e).__name__}: {e}",
                "hint": ("设计里还没有端口时插值扫频必失败(2019.2 实测):先建端口再建扫频,"
                         "纯叠层这类无端口设计用 sweep_type='Discrete' + save_fields=True。同名扫频也会失败")}
    if "state" in ctx:
        ctx["state"].setups.setdefault(setup, {}).setdefault("sweeps", []).append(
            # save_fields / sweep_type 必须记进 state:下游取场的工具(get_current_along_path、
            # get_axial_ratio)要靠它在发 COM 调用之前就判断"这条扫频有没有场可取"
            {"name": name, "start": start_frequency, "stop": stop_frequency,
             "sweep_type": sweep_type,
             "save_fields": bool(save_fields),
             "save_rad_fields": bool(save_rad_fields or save_fields)})
    return {"ok": True, "name": name, "setup": setup,
            "range": [start_frequency, stop_frequency], "points": num_points,
            "sweep_type": sweep_type,
            "save_rad_fields": bool(save_rad_fields or save_fields),
            "save_fields": bool(save_fields)}


def _setups_of(oDesign):
    """当前 design 的 setup 名列表。取不到返回 None。"""
    try:
        r = oDesign.GetModule("AnalysisSetup").GetSetups()
        return [str(s) for s in (r or [])]
    except Exception:
        return None


def _sweeps_of(oDesign, setup):
    """某 setup 下现有的扫频名列表。取不到返回 None(区别于"存在但没有扫频"的空列表)。"""
    try:
        r = oDesign.GetModule("AnalysisSetup").GetSweeps(setup)
        return [str(s) for s in (r or [])]
    except Exception:
        return None


@tool({
    "type": "function",
    "function": {
        "name": "delete_sweep",
        "description": ("删除 setup 上的扫频。`create_sweep` 不能同名覆盖,建错了只能先删再重建。"
            "**必须显式 confirm=true 才真删**(不带只回显该 setup 现有扫频清单);名字写错则整批不动。"
            "⚠️ 删扫频会同时丢掉它已求解的结果数据。调参阶段为什么要主动清存场扫频,见 `flow/s-parameters.md`。"),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "扫频所属的 setup 名"},
                "names": {"type": "array", "items": {"type": "string"},
                          "description": "要删的扫频名列表;省略则只回显清单"},
                "confirm": {"type": "boolean", "default": False,
                            "description": "必须显式传 true 才真正删除"},
            },
            "required": ["setup"],
        },
    },
})
def delete_sweep(ctx, setup, names=None, confirm=False):
    oDesign = ctx["oDesign"]
    existing = _sweeps_of(oDesign, setup)
    if existing is None:
        return {"ok": False, "error": f"取不到 setup '{setup}' 的扫频清单(setup 名是否写错?)"}

    if not names:
        return {"ok": True, "setup": setup, "sweeps": existing,
                "deleted": [], "hint": "传 names + confirm=true 才会删除"}

    names = [str(n) for n in names]
    missing = [n for n in names if n not in existing]
    if missing:
        return {"ok": False, "error": f"这些扫频在 setup '{setup}' 下不存在: {missing}",
                "sweeps": existing, "hint": "名字写错则整批不动,核对后重试"}

    if not confirm:
        return {"ok": True, "setup": setup, "sweeps": existing, "would_delete": names,
                "deleted": [], "hint": "确认无误后带 confirm=true 再调一次才会真删"}

    oModule = oDesign.GetModule("AnalysisSetup")
    deleted, failed = [], {}
    for n in names:
        try:
            oModule.DeleteSweep(setup, n)
            deleted.append(n)
        except Exception as e:
            failed[n] = f"{type(e).__name__}: {e}"

    if "state" in ctx:
        st = ctx["state"].setups.get(setup)
        if isinstance(st, dict) and isinstance(st.get("sweeps"), list):
            st["sweeps"] = [s for s in st["sweeps"]
                            if not (isinstance(s, dict) and s.get("name") in deleted)]

    out = {"ok": not failed, "setup": setup, "deleted": deleted,
           "remaining": _sweeps_of(oDesign, setup) or []}
    if failed:
        out["failed"] = failed
        out["error"] = f"部分扫频删除失败: {list(failed)}"
    else:
        out["hint"] = "删完记得 save_project 才写进 .aedt"
    return out


@tool({
    "type": "function",
    "function": {
        "name": "delete_setup",
        "description": ("删除求解 setup。**必须显式 confirm=true 才真删**(不带只回显现有 setup 清单及各自的扫频);"
            "名字写错则整批不动。⚠️ **删 setup 会连带删掉其下所有扫频和已求解结果,不可撤销** —— "
            "删之前先确认要保留的曲线已经取过数。注意参扫是按 ID 引用 setup 的,删了再同名重建也接不上"
            "(见 `flow/tuning.md`,要用 delete_parametric 清孤儿参扫)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"},
                          "description": "要删的 setup 名列表;省略则只回显清单"},
                "confirm": {"type": "boolean", "default": False,
                            "description": "必须显式传 true 才真正删除"},
            },
        },
    },
})
def delete_setup(ctx, names=None, confirm=False):
    oDesign = ctx["oDesign"]
    existing = _setups_of(oDesign)
    if existing is None:
        return {"ok": False, "error": "取不到 setup 清单(是否没有 active design?)"}

    def _listing():
        return {s: (_sweeps_of(oDesign, s) or []) for s in existing}

    if not names:
        return {"ok": True, "setups": _listing(), "deleted": [],
                "hint": "传 names + confirm=true 才会删除;删 setup 会连带删掉其下扫频与结果"}

    names = [str(n) for n in names]
    missing = [n for n in names if n not in existing]
    if missing:
        return {"ok": False, "error": f"这些 setup 不存在: {missing}",
                "setups": existing, "hint": "名字写错则整批不动,核对后重试"}

    if not confirm:
        return {"ok": True, "setups": _listing(), "would_delete": names, "deleted": [],
                "hint": "确认无误后带 confirm=true 再调一次才会真删(连带删掉其下扫频与已求解结果)"}

    oModule = oDesign.GetModule("AnalysisSetup")
    deleted, failed = [], {}
    for n in names:
        try:
            oModule.DeleteSetups([n])
            deleted.append(n)
        except Exception as e:
            failed[n] = f"{type(e).__name__}: {e}"

    if "state" in ctx:
        for n in deleted:
            ctx["state"].setups.pop(n, None)

    out = {"ok": not failed, "deleted": deleted, "remaining": _setups_of(oDesign) or []}
    if failed:
        out["failed"] = failed
        out["error"] = f"部分 setup 删除失败: {list(failed)}"
    else:
        out["hint"] = "删完记得 save_project 才写进 .aedt"
    return out


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
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
    print(f"  [Solving] {setup} ...")
    # 求解前先导一份收敛表:求解后若与之一字不差,说明 HFSS 复用了缓存解、没重算。
    # (对没解过的 setup 导,只得到 Completed: N/A,不会在消息窗口留 error —— 2019.2 实测)
    before = _export_convergence(ctx, setup)
    t0 = time.time()
    try:
        oDesign.Analyze(setup)   # 阻塞;COM 自动化同步返回
    except Exception as e:
        return {"ok": False, "error": f"Analyze 失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    if "state" in ctx:
        ctx["state"].setups.setdefault(setup, {})["solved"] = True
    out = {"ok": True, "setup": setup, "elapsed_sec": round(time.time() - t0, 1)}
    # 收敛体检:文档里写着要查的事,直接放进返回值 —— 返回值 agent 一定会看到
    conv, warns = _convergence_check(ctx, setup, before)
    if conv:
        out["convergence"] = conv
    if warns:
        out["warnings"] = warns
    return out


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
                "expression": {"type": "string",
                               "description": ("可选:自定义 dB 量表达式,替代默认 dB(S(port,port))。"
                                               "多口同时馈电(如四臂螺旋 0/90/180/270°)要看实际匹配,先 set_port_excitation "
                                               "设好幅相,再传 'dB(ActiveS(P1:1))' 取有源反射系数。须是 dB 量(带宽按 -10dB 分段)。")},
            },
        },
    },
})
def get_s_parameters(ctx, setup=None, sweep=None, port=None, summary_only=True, expression=None):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")

    # 解析 setup / sweep / port(从 state)
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
    sw_list = state.setups.get(setup, {}).get("sweeps", []) if state else []
    if sweep is None:
        if sw_list:
            sweep = sw_list[0]["name"]
        else:
            # 重开工程/重启 server 后 state 为空,直接问 HFSS
            try:
                sweep = list(oDesign.GetModule("AnalysisSetup").GetSweeps(setup))[0]
            except Exception:
                sweep = None
            if not sweep:
                return {"ok": False, "error": f"setup '{setup}' 下无 sweep"}
    ports = list(state.excitations.keys()) if state else []
    if port is None:
        if not ports:
            # 显式给了 expression 时 port 只是没用到的默认值,不该因此挡住
            try:
                ports = [e for e in oDesign.GetModule("BoundarySetup").GetExcitations()[::2]]
            except Exception:
                ports = []
        if ports:
            port = ports[0]
        elif expression:
            port = "?"
        else:
            return {"ok": False, "error": "无端口(请显式传 port 或 expression)"}

    soln = f"{setup} : {sweep}"
    expr = expression or f"dB(S({port},{port}))"
    report_name = "S_export_tmp"
    from .session import EXPORTS_DIR
    csv_path = os.path.join(EXPORTS_DIR, f"_{setup}_{sweep}_S.csv")

    # HFSS Modal:context 为空 [](对照 pyaedt standard report);families = ["Freq:=",["All"]];
    # CreateReport 参数个数各版本不一致,7 参(新)/6 参(老)都试,谁不抛就用谁。
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
        _drop_stale(csv_path)
        oModule.ExportToFile(report_name, csv_path)
        try:
            oModule.DeleteReports([report_name])
        except Exception:
            pass
        if not os.path.exists(csv_path):
            return {"ok": False, "error": _NO_DATA, "solution": soln}
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
    2019=8 参,2025=7 参,都试。"""
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
            _drop_stale(csv_path)
            oModule.ExportToFile(rname, csv_path)
            try:
                oModule.DeleteReports([rname])
            except Exception:
                pass
            if not os.path.exists(csv_path):
                return False, _NO_DATA
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
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
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
    from .session import EXPORTS_DIR
    csv_path = os.path.join(EXPORTS_DIR, f"_{setup}_{sweep}_Zin.csv")
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
                        "返回每刀 theta/gain 数组+峰值。调用前必须已 analyze,且 design 有 create_open_region + create_infinite_sphere。"
                        "对多频点的存场扫频:不传 freq 则每刀按频点给 by_freq(每个频点一组 gain/峰值),"
                        "另附 boresight_gain_dB 汇总轴向增益 vs 频率;传 freq 只取该频点。"),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
                "freq": {"type": "string",
                         "description": "可选:只取这个频点,如 '38.5GHz'(须是该扫频里有的点);不传=全部频点"},
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
                          phi_cuts=None, gain_type="realized", polarization="total", freq=None):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
    if not phi_cuts:
        phi_cuts = ["0deg", "90deg"]
    suffix = _POL.get(polarization, "Total")
    expr = f"dB({'Realized' if gain_type == 'realized' else ''}Gain{suffix})"
    soln = f"{setup} : {sweep}"
    oModule = oDesign.GetModule("ReportSetup")
    from .session import EXPORTS_DIR

    cuts = []
    for phi in phi_cuts:
        rname = "ff_tmp"
        csv_path = os.path.join(EXPORTS_DIR, f"_ff_{phi}.csv")
        fam = ["Theta:=", ["All"], "Phi:=", [str(phi)], "Freq:=", [str(freq)] if freq else ["All"]]
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
                _drop_stale(csv_path)
                oModule.ExportToFile(rname, csv_path)
                try:
                    oModule.DeleteReports([rname])
                except Exception:
                    pass
                if not os.path.exists(csv_path):
                    return {"ok": False, "error": f"{_NO_DATA} (phi={phi})", "solution": soln}
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
        # 多频点扫频导出的是宽表:第 1 列 Theta,之后每个频点一列(表头带 Freq='...')
        header = rows[0] if rows else []
        col_freqs = []
        for h in header[1:]:
            m = re.search(r"Freq='([^']+)'", h)
            col_freqs.append(m.group(1) if m else (str(freq) if freq else None))
        thetas, cols = [], [[] for _ in col_freqs]
        for r in rows[1:]:
            if len(r) < 1 + len(col_freqs):
                continue
            try:
                t = float(r[0].strip().strip('"').split()[0])
                vals = [float(r[j + 1].strip().strip('"').split()[0]) for j in range(len(col_freqs))]
            except Exception:
                continue
            thetas.append(t)
            for j, v in enumerate(vals):
                cols[j].append(v)
        if not thetas or not col_freqs:
            return {"ok": False, "error": f"远场数据空 (phi={phi})", "csv_header": header or None}

        def _one(gains, f):
            pk = max(gains); pi = gains.index(pk)
            return {"freq": f, "gain_dB": [round(g, 3) for g in gains],
                    "peak_gain_dB": round(pk, 2), "peak_theta_deg": round(thetas[pi], 2)}
        cut = {"phi": str(phi), "theta_deg": [round(t, 2) for t in thetas], "n_points": len(thetas)}
        if len(col_freqs) == 1:
            cut.update(_one(cols[0], col_freqs[0]))
        else:
            # 多频点时不放顶层 gain_dB,免得被当成"那一个"频点的结果
            cut["by_freq"] = [_one(g, f) for g, f in zip(cols, col_freqs)]
        cuts.append(cut)

    out = {"ok": True, "setup": setup, "sphere": sphere, "gain_type": gain_type,
           "polarization": polarization, "metric": expr, "n_cuts": len(cuts), "cuts": cuts}
    # 轴向增益 vs 频率:取第一刀 theta=0(各刀在 theta=0 是同一个方向)
    c0 = cuts[0]
    if 0.0 in c0["theta_deg"]:
        i0 = c0["theta_deg"].index(0.0)
        per = c0["by_freq"] if "by_freq" in c0 else [c0]
        out["boresight_gain_dB"] = [{"freq": p["freq"], "gain_dB": p["gain_dB"][i0]} for p in per]
    return out


def _results_dir_size(ctx):
    """返回 (<design>.results 所在的 .aedtresults 目录, 字节数);取不到就 (None, None)。"""
    import os
    try:
        oProject = ctx["oProject"]
        d = _os_join(oProject.GetPath(), oProject.GetName() + ".aedtresults")
    except Exception:
        return None, None
    if not os.path.isdir(d):
        return d, None
    total = 0
    for root, _dirs, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return d, total


def _os_join(a, b):
    import os
    return os.path.join(str(a), str(b))


@tool({
    "type": "function",
    "function": {
        "name": "cleanup_solutions",
        "description": ("清理已求解的解数据(对应 GUI 的 Clean Up Solutions),回收磁盘。"
                        "**必须显式 confirm=true 才真删**(不带只回显结果目录占用)。"
                        "scope: fields(默认)只删场留 S 参数 / all 连 S 参数一起删(要重跑)/ linked 只删外部链接。"
                        "什么时候清、清完有什么取不到,见 SKILL.md §3。"),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["fields", "all", "linked"], "default": "fields",
                          "description": "fields=只删场保留S参数(推荐);all=整份解都删;linked=只删链接数据"},
                "variations": {"type": "array", "items": {"type": "string"},
                               "description": "要清的变量组合;省略=All(全部)"},
                "keep_mesh": {"type": "boolean", "default": False,
                              "description": "scope='fields' 时保留网格(下次同几何求解可复用,省自适应时间;但网格本身也占盘)"},
                "confirm": {"type": "boolean", "default": False,
                            "description": "必须显式传 true 才真正删除"},
            },
        },
    },
})
def cleanup_solutions(ctx, scope="fields", variations=None, keep_mesh=False, confirm=False):
    oDesign = ctx.get("oDesign")
    if oDesign is None:
        return {"ok": False, "error": "无 active design"}

    d, before = _results_dir_size(ctx)
    human = (lambda n: None if n is None else f"{n/1024/1024:.1f} MB")
    vars_ = [str(v) for v in variations] if variations else ["All"]

    if not confirm:
        return {"ok": True, "results_dir": d, "size": human(before), "deleted": False,
                "would_clean": {"scope": scope, "variations": vars_, "keep_mesh": keep_mesh},
                "hint": ("带 confirm=true 再调一次才会真删。scope='fields' 保留 S 参数、只回收场数据;"
                         "**删场后远场量取不到了**,先确认远场已取数/导出")}

    try:
        if scope == "all":
            oDesign.DeleteFullVariation(vars_, True)
        elif scope == "linked":
            oDesign.DeleteLinkedDataVariation(vars_)
        else:
            oDesign.DeleteFieldVariation(vars_, not keep_mesh, True)
    except Exception as e:
        return {"ok": False, "error": f"清理解数据失败: {type(e).__name__}: {e}",
                "results_dir": d, "size": human(before)}

    _d2, after = _results_dir_size(ctx)
    out = {"ok": True, "scope": scope, "variations": vars_, "results_dir": d,
           "size_before": human(before), "size_after": human(after)}
    if before and after is not None:
        out["freed"] = human(max(before - after, 0))
    out["hint"] = "磁盘回收可能要等 HFSS 落盘;删完记得 save_project"
    return out


# ─────────────────────────────────────────────────────────
# 本征模求解 —— InsertSetup("HfssEigen") + Solutions.ExportEigenmodes
# 与驱动求解(HfssDriven)的根本区别:**不需要端口、不需要激励**,直接解出结构
# 自身的谐振频率和 Q。腔体、介质谐振器(DRA)、周期结构的模式分析用它。
# 参数结构照 AEDT 的 Tools→Record Script 录出来的官方调用(2025.2),不是猜的。
# ⚠️ HfssEigen 的参数块与 HfssDriven 不同:没有 Frequency/MaxDeltaS/SaveAnyFields,
#    换成 MinimumFrequency/NumModes/MaxDeltaFreq/ConvergeOnRealFreq,且多一个 MeshLink 块。
# ─────────────────────────────────────────────────────────


@tool({
    "type": "function",
    "function": {
        "name": "create_eigenmode_setup",
        "description": ("建**本征模**求解设置(HfssEigen):不要端口、不要激励,直接解结构自身的谐振频率与 Q。"
            "**design 必须是 Eigenmode 类型**(new_design 时传 solution_type='Eigenmode'),"
            "驱动类型的 design 建不了。min_frequency 取略低于预期最低模(给高了会漏掉低阶模)。"
            "建完用 analyze 跑(与驱动求解同一个工具),再 get_eigenmodes 取结果。用法见 `flow/eigenmode.md`。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Setup 名,如 'Setup1'"},
                "min_frequency": {"type": "string",
                                  "description": "从这个频率往上找模,带单位(如 '4GHz')。"
                                                 "取略低于你预期的最低模;给太高会漏掉低阶模"},
                "num_modes": {"type": "integer", "default": 1,
                              "description": "求几个模,默认 1。简并模会各占一个名额"},
                "max_passes": {"type": "integer", "default": 6, "description": "最大自适应迭代,默认 6"},
                "max_delta_freq_pct": {"type": "number", "default": 10,
                                       "description": "频率收敛判据(百分比),默认 10"},
                "min_converged_passes": {"type": "integer", "default": 1,
                                         "description": "要求连续几遍满足判据才判收敛,默认 1。校准/高 Q 结构用 2"},
                "converge_on_real_freq": {"type": "boolean", "default": False,
                                          "description": "只按实部收敛(高 Q 结构用),默认 False"},
            },
            "required": ["name", "min_frequency"],
        },
    },
})
def create_eigenmode_setup(ctx, name, min_frequency, num_modes=1, max_passes=6,
                           max_delta_freq_pct=10, converge_on_real_freq=False,
                           min_converged_passes=1):
    oDesign = ctx["oDesign"]
    try:
        oDesign.GetModule("AnalysisSetup").InsertSetup("HfssEigen",
            ["NAME:" + name,
             "MinimumFrequency:=", _to_unit_str(min_frequency),
             "NumModes:=", int(num_modes),
             "MaxDeltaFreq:=", float(max_delta_freq_pct),
             "ConvergeOnRealFreq:=", bool(converge_on_real_freq),
             "MaximumPasses:=", int(max_passes),
             "MinimumPasses:=", 1,
             "MinimumConvergedPasses:=", int(min_converged_passes),
             "PercentRefinement:=", 30,
             "IsEnabled:=", True,
             # 不带 MeshLink 块:2025.2 录制里有(ImportMesh:=False 等于没用),但 **2019.2 上
             # 只要出现这个块就要求 partner project 名**,否则报
             # "The partner project name cannot be empty"。我们从不跨工程链接网格,直接不发。
             "BasisOrder:=", 1,
             "DoLambdaRefine:=", True,
             "DoMaterialLambda:=", True,
             "SetLambdaTarget:=", False,
             "Target:=", 0.2,
             "UseMaxTetIncrease:=", False])
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup(HfssEigen) 失败: {type(e).__name__}: {e}",
                "hint": "这个 design 是 Eigenmode 类型吗?驱动类型的 design 建不了本征模 setup "
                        "(new_design 时要传 solution_type='Eigenmode');另外同名 setup 不能覆盖"}
    if "state" in ctx:
        ctx["state"].setups[name] = {"frequency": min_frequency, "max_passes": max_passes,
                                     "sweeps": [], "kind": "eigenmode", "num_modes": int(num_modes)}
    return {"ok": True, "name": name, "min_frequency": min_frequency, "num_modes": int(num_modes),
            "max_passes": max_passes,
            "hint": "用 analyze 跑(和驱动求解同一个工具),再 get_eigenmodes 取结果"}


@tool({
    "type": "function",
    "function": {
        "name": "get_eigenmodes",
        "description": ("取本征模结果:各模的**谐振频率**和 **Q**,外加相邻模间隔 spacing_pct。调用前必须已 analyze。"
            "**Q=0 表示无耗**(真空+PEC 的理想腔体),不是出错。结果怎么读见 `flow/eigenmode.md`。"),
        "parameters": {"type": "object", "properties": {
            "setup": {"type": "string", "description": "setup 名,不传用第一个"},
            "sweep": {"type": "string", "default": "LastAdaptive"},
            "path": {"type": "string", "description": "可选:.eig 文件落地路径,不传放 exports/"},
        }},
    },
})
def get_eigenmodes(ctx, setup=None, sweep="LastAdaptive", path=None):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err

    from .session import EXPORTS_DIR
    path = path or os.path.join(EXPORTS_DIR, f"_eig_{setup}.eig")
    if os.path.exists(path):
        os.remove(path)
    try:
        # 实测可用(2025.2):Solutions.ExportEigenmodes(soln, variation, file)。
        # 本征模结果不走 ReportSetup,只有这个专用导出。
        oDesign.GetModule("Solutions").ExportEigenmodes(f"{setup} : {sweep}", "", path)
    except Exception as e:
        return {"ok": False, "error": f"ExportEigenmodes 失败: {type(e).__name__}: {e}",
                "hint": "这个 setup 跑过了吗(先 analyze)?是本征模 setup 吗(驱动求解没有本征模结果)?"}
    if not os.path.exists(path) or os.path.getsize(path) < 20:
        return {"ok": False, "error": "导出没产出内容,多半是还没有解", "hint": "先 analyze 再取"}

    modes = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) < 3:
            continue
        try:
            modes.append({"mode": int(parts[0]), "freq_ghz": round(float(parts[1]), 6),
                          "q": float(parts[2])})
        except ValueError:
            continue
    if not modes:
        return {"ok": False, "error": "解析不出本征模数据", "file": path}

    for i in range(1, len(modes)):
        lo = modes[i - 1]["freq_ghz"]
        if lo:
            modes[i]["spacing_pct"] = round((modes[i]["freq_ghz"] - lo) / lo * 100, 3)

    out = {"ok": True, "setup": setup, "n_modes": len(modes), "modes": modes, "file": path}
    if all(m["q"] == 0 for m in modes):
        out["note_q"] = "所有 Q 都是 0 = 结构无耗(真空 + PEC)。要算真实 Q,给材料加 tanδ 或壁赋有限电导率。"
    near = [m for m in modes if m.get("spacing_pct") is not None and abs(m["spacing_pct"]) < 1]
    if near:
        out["note_degenerate"] = (f"有 {len(near)} 处相邻模间隔 <1%,基本是简并模 —— "
                                  "做单模器件要确认馈电不会把另一个一起激发。")
    return out


# ─────────────────────────────────────────────────────────
# 收敛体检 —— 把"文档里写着要查"的事做进 analyze 的返回值
# 文档是可选读物,工具返回是强制读物:agent 一定会看到 analyze 返回了什么。
#
# 数据源:oDesign.ExportConvergence(setup, "", path, True) —— "" = **当前这组设计变量**。
# 它挂在 **design 对象**上,不在 AnalysisSetup 模块上。(更正:旧注释写过"试过
# ExportConvergence 等 5 个方法名,2025.2 上都不存在"——那次是试在了 AnalysisSetup 模块上,
# 对象找错了。用户指出后在 2019.2 + 2025.2 都实测可用。)
#
# 为什么不再扫结果目录里的 *.EMConvData:那些文件是**按设计变量组合**存的,同一 setup
# 的各组合设置完全相同,按设置做指纹分不开;取最新的那个只是"最后解过的那组",不一定
# 是当前这组。实测:改回 zM3=1.49mm 求解,HFSS 复用旧解没写新文件,目录里最新的却是
# zM3=1.59mm 那组 —— 会把别的组合的收敛信息当成当前的报出来。
#
# **只对确定的事下结论,其余只报数。** 曾按"轮数≤3 / 单元<2万"判"可能假收敛",
# 两个与解析解偏差 <0.02% 的腔体全被误报 —— 会喊狼来了的检查比没有更坏,agent 被假警报
# 烫几次就学会忽略整条返回,真出事时也一起忽略。网格够不够交给 flow/tuning.md 的网格校准。
# ─────────────────────────────────────────────────────────


def _setup_props(ctx, setup):
    """setup 的**活**属性(内存里的,不是盘上 .aedt —— 复制 design 被重置成 5 GHz 这种事
    在存盘前只存在于内存)。取不到返回 {}。"""
    oD = ctx["oDesign"]
    srv = f"AnalysisSetup:{setup}"
    out = {}
    try:
        for p in oD.GetProperties("HfssTab", srv) or []:
            try:
                out[str(p)] = str(oD.GetPropertyValue("HfssTab", srv, str(p)))
            except Exception:
                pass
    except Exception:
        pass
    return out


def _nums(x):
    """'0.02' → [0.02];'0.02, 0.02'(多频自适应,每个频点一个)→ [0.02, 0.02];'N/A' → []。
    多频 setup 的判据活值是逗号列表——只当单个数解析会失败,曾因此整个退化掉。"""
    out = []
    for part in str(x or "").replace("%", "").split(","):
        try:
            out.append(float(part.strip()))
        except ValueError:
            pass
    return out


def _export_convergence(ctx, setup, variation=""):
    """某组设计变量的收敛表 → dict。导不出返回 None。
    variation 为空 = 当前这组;也可以只写被扫的变量(如 "L='22mm'"),其余按 nominal 补齐。"""
    import tempfile
    oD = ctx["oDesign"]
    path = os.path.join(tempfile.gettempdir(), f"_hfss_conv_{os.getpid()}_{setup}.txt")
    try:
        if os.path.exists(path):
            os.remove(path)
        oD.ExportConvergence(setup, variation, path, True)
        txt = io.open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    kv, rows, header = {}, [], None
    for line in txt.splitlines():
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                header = cells
            elif cells and cells[0].isdigit():
                rows.append(cells)
        elif ":" in line:
            k, _, v = line.partition(":")
            kv[k.strip()] = v.strip()

    def num(k):
        v = [int(x) if float(x).is_integer() else x for x in _nums(kv.get(k))]
        return v[0] if len(v) == 1 else (v or None)     # 多频 setup 是列表,每个频点一个

    # 不报 DesignVariation:它把所有变量(含派生量)全列一遍,动辄上百个;导的本来就是当前这组
    out = {"criterion": kv.get("Criterion"),
           "target": num("Target"),
           "final_value": num("Current"),
           "passes_completed": num("Completed"),
           "passes_max": num("Maximum"),
           "consec_passes_required": num("Target Consecutive Passes"),
           "consec_passes_achieved": num("Current Consecutive Passes")}
    conv = kv.get("Converged")
    out["converged"] = None if conv is None else conv.strip().lower().startswith("y")
    out["has_solution"] = str(kv.get("Completed", "")).strip().upper() not in ("", "N/A")
    # 网格单元数列:某些求解类型/版本里不是纯整数(N/A、千分位逗号)—— 解析不了就跳过,
    # 不能让一个格子把整次求解报成失败
    elems = []
    for r in rows:
        v = _nums(r[1].replace(",", "")) if len(r) > 1 else []
        if v:
            elems.append(int(v[0]))
    if elems:
        out["elements"] = elems[-1]
        out["elements_by_pass"] = elems
    out = {k: v for k, v in out.items() if v is not None}
    out["_raw"] = txt               # 给 analyze 比对"前后是否完全一样"(判缓存)用,返回前删掉
    return out


def _convergence_check(ctx, setup, before=None):
    """返回 (摘要 dict, 警告 list)。before = analyze 之前导出的那份(判是否复用了缓存解)。"""
    # 不用 GetValidISolutionList 判"有没有解":2019.2 上没解过的 setup 它也列着,
    # 解被作废后它也照样列着。收敛表的 has_solution 才可靠。
    warns = []
    props = _setup_props(ctx, setup)
    summary = {"setup": setup}
    # setup 的活值 —— 只报事实。看一眼就知道频点对不对、是不是被重置成了单频
    # 驱动求解:Solution Freq / Solution Freq Type / Delta S;本征模:Min Freq / Modes / Delta F
    for k_out, k_in in (("solution_freq", "Solution Freq"),
                        ("solution_freq_type", "Solution Freq Type"),
                        ("min_freq", "Min Freq"), ("num_modes", "Modes"),
                        ("max_passes_set", "Passes"),
                        ("delta_s_set", "Delta S"), ("delta_f_pct_set", "Delta F")):
        if k_in in props:
            summary[k_out] = props[k_in]

    c = _export_convergence(ctx, setup)
    if c is None:
        summary["convergence"] = "导不出收敛表"
        return summary, warns
    raw = c.pop("_raw", "")
    if isinstance(before, dict):
        # analyze 之前就已经有解、且前后收敛表一字不差 = HFSS 复用了缓存解,没重算。
        # 之前没解(从没解过 / 解被作废)→ 这次一定是新解。
        c["reused_cached_solution"] = bool(before.get("has_solution")) and before.get("_raw") == raw
    summary.update(c)

    # 只对确定的事下结论
    if not c.get("has_solution"):
        warns.append("**当前这组设计变量没有可用的解**(收敛表是空的)—— 典型是求解后又改过几何"
                     "(**画采样线没加 non_model=True 也算**),解被作废了;或者这组变量还没解过。"
                     "不要拿任何取数结果当真。刚 analyze 完就是这样的话,读 get_messages 查原因"
                     "(典型:求解器子进程起不来);否则重新 analyze。")
    elif c.get("converged") is False:
        warns.append(f"**没有收敛**:跑了 {c.get('passes_completed')}/{c.get('passes_max')} 轮,"
                     f"判据 {c.get('criterion')} 目标 {c.get('target')}、末轮 {c.get('final_value')}。"
                     "**结果不可信,别拿它对标、别拿它调参** —— 加大 max_passes 重解。")
    return summary, warns


@tool({
    "type": "function",
    "function": {
        "name": "get_convergence",
        "description": (
            "查某个 setup 在**当前这组设计变量**下的收敛事实:是否收敛、跑了几轮/上限、"
            "判据与末轮值、**要求连续几遍满足 / 实际连续几遍**、各轮网格单元数,"
            "以及 setup 当前的**自适应频率与类型**(单频/多频)。"
            "analyze 的返回值里已经带着同样的东西;**这个工具是给\"不是用 analyze 解的\"情况用的** "
            "—— 自己写脚本求解、或接手别人已经解好的工程,事后照样能查。"
            "只对确定的事报警(没收敛 / 根本没解 / 当前变量组合没有可用的解),其余只报数。"
        ),
        "parameters": {"type": "object", "properties": {
            "setup": {"type": "string", "description": "setup 名,不传用第一个"}}},
    },
})
def get_convergence(ctx, setup=None):
    setup, err = resolve_setup(ctx, setup)
    if err:
        return err
    summary, warns = _convergence_check(ctx, setup)
    out = {"ok": True, "setup": setup}
    if summary:
        out["convergence"] = summary
    if warns:
        out["warnings"] = warns
    return out
