"""场诊断:看结构上实际流了什么(native COM 版)。

补的是这么一个盲区:其余 get_* 工具只能测"进去多少"(S 参数/Zin)和"出来多少"
(远场/增益/轴比),**看不见中间的机理**。失配了不知道是没激励起来还是模次不对,
方向图歪了不知道是哪部分在辐射 —— 只能靠扫参试。表面电流是这一环的直接读数。

走的是 ReportSetup 的 "Fields" 报告(context = 一条 polyline,PointCount 控采样密度),
跟 analysis.py 里取 S 参数/远场是同一个路子:CreateReport → ExportToFile → 解析 CSV。
不走 FieldsReporter 场计算器 —— 那个是有状态的压栈式 API,行为更不稳。

**前提:必须有存场的解**(create_sweep 的 save_fields=True,或用 LastAdaptive 的自适应解)。
场数据贵(实测 ~90-100 秒/点、几百 MB/点),所以场诊断只在**单频点**用,不跟扫频做,
用完 delete_sweep 清掉 —— 见 SKILL.md §6.9 与 knowledge/_solving.md。
"""

import os
import math

from . import tool


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
                    "最可能是解已失效 —— 求解后动过几何(**新画采样线也算**)。"
                    "处理:先确保采样 polyline 已存在,再 analyze,然后才取场;"
                    "调 get_messages 能看到 'Solutions have been invalidated' 确认")
        except Exception as e:
            last = f"form#{i}(arity={len(args) + 3}): {type(e).__name__}: {e}"
        finally:
            try:
                oModule.DeleteReports([rname])   # 失败也可能留了个空报告,清掉再试下一种
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
            "两条硬前提,违反了会拿到空数据或假读数(详见 SKILL.md §6.9):"
            "**采样线必须在 analyze 之前画好**(求解后建 polyline 会让解作废,且 COM 无任何提示);"
            "**线要略短于导体、避开馈电点**。什么时候该调见 §6.9,别每次取结果都调。"),
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

    if setup is None:
        setups = list(state.setups.keys()) if state else []
        if not setups:
            return {"ok": False, "error": "无 setup(重开工程后请显式传 setup)"}
        setup = setups[0]

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
