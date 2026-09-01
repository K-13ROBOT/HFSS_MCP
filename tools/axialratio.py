"""轴比 vs 频率(CP 天线对标门,native COM 版)。

与 parametrics.get_parametric_axial_ratio 的分工:
- 那个:参扫**各组合**在单个频点的最小 AR —— 用来在设计空间里找最优组合;
- 本篇:**一个设计**在整条扫频上的 AR 曲线 —— 用来判 AR<=3dB 的**连续带宽**是否覆盖工作频段。

前提:扫频必须带场建。**实测 2025.2:SaveRadFields 单独设不生效**(S 参数有解、远场报告仍报 com_error),
必须 create_sweep(..., sweep_type='Discrete', save_fields=True)。否则扫频上没有辐射场。
"""

import os

from . import tool


def _contiguous_bands(freqs, vals, threshold):
    """vals<=threshold 的所有连续频段 [(lo, hi), ...],边界线性插值。"""
    bands = []
    inside = False
    lo = None
    for i in range(len(freqs)):
        ok = vals[i] <= threshold
        if ok and not inside:
            if i == 0:
                lo = freqs[0]
            else:
                f0, f1, v0, v1 = freqs[i - 1], freqs[i], vals[i - 1], vals[i]
                lo = f0 + (threshold - v0) * (f1 - f0) / (v1 - v0) if v1 != v0 else f1
            inside = True
        elif not ok and inside:
            f0, f1, v0, v1 = freqs[i - 1], freqs[i], vals[i - 1], vals[i]
            hi = f0 + (threshold - v0) * (f1 - f0) / (v1 - v0) if v1 != v0 else f0
            bands.append((lo, hi))
            inside = False
    if inside:
        bands.append((lo, freqs[-1]))
    return bands


def _ghz(v):
    s = str(v).strip().lower()
    for u, k in (("ghz", 1.0), ("mhz", 1e-3), ("khz", 1e-6), ("hz", 1e-9)):
        if s.endswith(u):
            return float(s[: -len(u)]) * k
    return float(s)


@tool({
    "type": "function",
    "function": {
        "name": "get_axial_ratio",
        "description": (
            "取单个已求解设计的**轴比 AR(dB) vs 频率**曲线 + 3dB 轴比带宽 —— CP 天线的对标门。"
            "默认取 boresight(theta=0,phi=0)。"
            "与 get_parametric_axial_ratio 区别:那个是参扫各组合在单频点的最小 AR;这个是一个设计整条扫频的 AR 曲线,"
            "能直接给出 AR<=3dB 的连续带宽,判定是否覆盖工作频段。"
            "**前提:扫频必须用 create_sweep(..., sweep_type='Discrete', save_fields=True) 建**"
            "——实测 2025.2 上只设 save_rad_fields 不生效(远场报告报 com_error)。"
            "另需 create_open_region + create_infinite_sphere。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "setup": {"type": "string", "description": "setup 名,不传用第一个"},
                "sweep": {"type": "string", "default": "Sweep1",
                          "description": "扫频名,必须是建了 save_fields=True 的那条。"
                                         "传 'LastAdaptive' 只会得到单个频点(拿不到带宽)"},
                "sphere": {"type": "string", "default": "Sphere1"},
                "theta": {"type": "string", "default": "0deg", "description": "观察角 theta,默认 0deg(法向)"},
                "phi": {"type": "string", "default": "0deg", "description": "观察角 phi,默认 0deg"},
                "threshold_dB": {"type": "number", "default": 3, "description": "轴比带宽判据,默认 3dB"},
                "freq_range": {"type": "array", "items": {"type": "string"},
                               "description": "可选,只统计该区间并判定是否全带达标,如 ['14.5GHz','16.5GHz']"},
                "max_curve_points": {"type": "integer", "default": 60,
                                     "description": "回传曲线最大点数(等间隔抽稀,省上下文)。0=不回传曲线"},
            },
        },
    },
})
def get_axial_ratio(ctx, setup=None, sweep="Sweep1", sphere="Sphere1", theta="0deg", phi="0deg",
                    threshold_dB=3, freq_range=None, max_curve_points=60):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup"}
    setup = setup or setups[0]

    expr = "dB(AxialRatioValue)"
    soln = "%s : %s" % (setup, sweep)
    oModule = oDesign.GetModule("ReportSetup")
    from .session import EXPORTS_DIR

    rname = "ar_tmp"
    csv_path = os.path.join(EXPORTS_DIR, "_ar.csv")
    fam = ["Theta:=", [str(theta)], "Phi:=", [str(phi)], "Freq:=", ["All"]]
    tr = ["X Component:=", "Freq", "Y Component:=", [expr]]
    forms = [
        (rname, "Far Fields", "Data Table", soln, ["Context:=", sphere], fam, tr, []),
        (rname, "Far Fields", "Data Table", soln, ["Context:=", sphere], fam, tr),
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
            last = "%s: %s" % (type(e).__name__, e)
    if not done:
        return {"ok": False, "error": "轴比报告失败: %s" % last,
                "hint": "确认已 analyze;扫频须 create_sweep(..., sweep_type='Discrete', save_fields=True) 建;"
                        "并已 create_open_region + create_infinite_sphere"}

    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            rows = [ln.rstrip("\n").split(",") for ln in f if ln.strip()]
    except Exception as e:
        return {"ok": False, "error": "读 CSV 失败: %s" % e}

    header = [h.strip().strip('"') for h in (rows[0] if rows else [])]

    # HFSS 的 Data Table 导出有两种布局,都要认:
    #   窄表: "Freq [GHz]","dB(AxialRatioValue)"            —— 每行一个频点
    #   宽表: "Theta [deg]","Freq [GHz]",AR,"Freq [GHz]",AR… —— 每个频点一对列,只有一行
    # 统一做法:按表头找出所有 Freq 列,其右邻即对应的 AR 列,再扫全部数据行收集 (f, ar) 对。
    freq_cols = [i for i, h in enumerate(header) if h.lower().startswith("freq")]

    def _scale_of(h):
        hl = h.lower()
        if "[mhz]" in hl:
            return 1e-3
        if "[khz]" in hl:
            return 1e-6
        if "[hz]" in hl and "[ghz]" not in hl and "[mhz]" not in hl and "[khz]" not in hl:
            return 1e-9
        return 1.0

    def _num(cell):
        return float(cell.strip().strip('"').split()[0])

    seen = {}
    if freq_cols:
        for r in rows[1:]:
            for ci in freq_cols:
                if ci + 1 >= len(r):
                    continue
                try:
                    f = _num(r[ci]) * _scale_of(header[ci])
                    a = _num(r[ci + 1])
                except Exception:
                    continue
                seen.setdefault(round(f, 9), a)
    else:
        # 兜底:没有可识别的表头,按 col0=freq / col1=value
        us = _scale_of(header[0] if header else "")
        for r in rows[1:]:
            if len(r) < 2:
                continue
            try:
                seen.setdefault(round(_num(r[0]) * us, 9), _num(r[1]))
            except Exception:
                continue

    freqs = sorted(seen.keys())
    ars = [seen[f] for f in freqs]

    if not freqs:
        return {"ok": False, "error": "轴比数据空", "csv_header": header,
                "hint": "多半是扫频没存场:改用 "
                        "create_sweep(..., sweep_type='Discrete', save_fields=True) 重建扫频再 analyze"}
    if len(freqs) < 2:
        return {"ok": False, "error": "扫频上只有 %d 个频点,给不出带宽" % len(freqs),
                "at": {"freq_ghz": round(freqs[0], 4), "axial_ratio_db": round(ars[0], 3)},
                "hint": "sweep 传成 LastAdaptive 了?改传带 save_rad_fields 的扫频名"}

    rng = None
    if freq_range and len(freq_range) == 2:
        lo_r, hi_r = _ghz(freq_range[0]), _ghz(freq_range[1])
        rng = [lo_r, hi_r]
        sel = [(f, a) for f, a in zip(freqs, ars) if lo_r - 1e-9 <= f <= hi_r + 1e-9]
        if not sel:
            return {"ok": False, "error": "指定区间 %s 内没有扫频点" % freq_range,
                    "sweep_span_ghz": [round(freqs[0], 4), round(freqs[-1], 4)]}
        freqs = [p[0] for p in sel]
        ars = [p[1] for p in sel]

    mn = min(ars)
    mi = ars.index(mn)
    bands = _contiguous_bands(freqs, ars, float(threshold_dB))
    main = None
    for lo, hi in bands:
        if lo - 1e-9 <= freqs[mi] <= hi + 1e-9:
            main = (lo, hi)
            break
    if main is None and bands:
        main = max(bands, key=lambda b: b[1] - b[0])

    out = {
        "ok": True, "setup": setup, "sweep": sweep, "sphere": sphere,
        "at_angle": {"theta": str(theta), "phi": str(phi)},
        "metric": expr, "threshold_dB": float(threshold_dB),
        "n_points": len(freqs),
        "freq_span_ghz": [round(freqs[0], 4), round(freqs[-1], 4)],
        "min_ar_db": round(mn, 3),
        "min_ar_freq_ghz": round(freqs[mi], 4),
        "n_bands": len(bands),
    }
    if rng:
        out["freq_range_applied_ghz"] = [round(rng[0], 4), round(rng[1], 4)]
        out["max_ar_in_range_db"] = round(max(ars), 3)
        out["all_pass_in_range"] = bool(max(ars) <= float(threshold_dB))
    if main:
        lo, hi = main
        ctr = 0.5 * (lo + hi)
        out["ar_band"] = {
            "low_ghz": round(lo, 4), "high_ghz": round(hi, 4),
            "center_ghz": round(ctr, 4), "span_mhz": round((hi - lo) * 1000, 1),
            "fractional_pct": round((hi - lo) / ctr * 100, 2) if ctr else None,
        }
    else:
        out["ar_band"] = None
        out["hint"] = "整条曲线都没到 %sdB 以下,最小 %sdB @ %sGHz" % (
            threshold_dB, round(mn, 2), round(freqs[mi], 3))
    if len(bands) > 1:
        out["bands"] = [{"low_ghz": round(a, 4), "high_ghz": round(b, 4)} for a, b in bands]

    if max_curve_points and max_curve_points > 0:
        n = len(freqs)
        if n <= max_curve_points:
            idx = list(range(n))
        else:
            step = (n - 1) / float(max_curve_points - 1)
            idx = sorted({int(round(i * step)) for i in range(max_curve_points)})
        out["curve"] = {"freq_ghz": [round(freqs[i], 4) for i in idx],
                        "ar_db": [round(ars[i], 3) for i in idx]}
    return out
