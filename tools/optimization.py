"""内置优化器(native COM 版,单目标)—— Optimetrics OptiOptimization。

变量边界走 ChangeProperty(LocalVariableTab 的 Optimization/Included/Min/Max);
setup 走 InsertSetup("OptiOptimization", arg) 带 Goal;求解走 Optimetrics.SolveSetup;
结果读 design 变量值(优化完成 UpdateDesignWhenDone 写回最优)。
"""

import time

from . import tool


def _opti(ctx):
    return ctx["oDesign"].GetModule("Optimetrics")


def _set_var_opt_bounds(oDesign, var, vmin, vmax):
    """给 local 变量设优化边界(Included + Min + Max)。"""
    oDesign.ChangeProperty(
        ["NAME:AllTabs",
         ["NAME:LocalVariableTab",
          ["NAME:PropServers", "LocalVariables"],
          ["NAME:ChangedProps",
           ["NAME:" + var,
            ["NAME:Optimization", "Included:=", True, "Min:=", str(vmin), "Max:=", str(vmax)]]]]])


@tool({
    "type": "function",
    "function": {
        "name": "create_optimization",
        "description": ("建内置优化(单目标):求解器自己迭代逼近目标。calculation=代价表达式(如 'dB(S(1,1))'); "
                        "condition+goal_value=目标(如 <= -15);variables=[{name,min,max}](数值,单位同变量)。"
                        "建完 run_optimization 跑、get_optimization_result 取最优。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "calculation": {"type": "string", "description": "代价表达式,如 'dB(S(1,1))'"},
                "variables": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "min": {"type": "string"}, "max": {"type": "string"}},
                    "required": ["name", "min", "max"]}, "minItems": 1,
                    "description": "优化变量及范围,如 [{'name':'PL','min':'26mm','max':'32mm'}]"},
                "condition": {"type": "string", "enum": ["<=", ">=", "=="], "default": "<="},
                "goal_value": {"type": "number", "default": 0},
                "goal_weight": {"type": "number", "default": 1},
                "freq": {"type": "string", "description": "代价评估频点,不传用 setup 频率"},
                "optimizer": {"type": "string", "enum": ["Quasi Newton", "Pattern Search", "Genetic Algorithm"],
                              "default": "Quasi Newton"},
                "max_iterations": {"type": "integer", "default": 20},
                "setup": {"type": "string"}, "sweep": {"type": "string", "default": "LastAdaptive"},
            },
            "required": ["name", "calculation", "variables"],
        },
    },
})
def create_optimization(ctx, name, calculation, variables, condition="<=", goal_value=0, goal_weight=1,
                        freq=None, optimizer="Quasi Newton", max_iterations=20, setup=None, sweep="LastAdaptive"):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if not setups:
        return {"ok": False, "error": "无 setup"}
    setup = setup or setups[0]
    freq = freq or (state.setups.get(setup, {}).get("frequency") if state else None)
    if not freq:
        return {"ok": False, "error": "缺 freq 且无法从 setup 推断", "hint": "传 freq='2.4GHz'"}

    # 1. 变量边界
    try:
        for v in variables:
            _set_var_opt_bounds(oDesign, v["name"], v["min"], v["max"])
    except Exception as e:
        return {"ok": False, "error": f"设变量优化边界失败: {type(e).__name__}: {e}"}

    soln = f"{setup} : {sweep}"
    mxi = int(max_iterations)
    goal = ["NAME:Goal",
            "ReportType:=", "Modal Solution Data", "Solution:=", soln,
            ["NAME:SimValueContext", "Domain:=", "Sweep"],
            "Calculation:=", calculation, "Name:=", calculation,
            ["NAME:Ranges", ["NAME:Range", "Var:=", "Freq", "Type:=", "d", "DiscreteValues:=", str(freq)]],
            "Condition:=", condition,
            ["NAME:GoalValue", "GoalValueType:=", "Independent", "Format:=", "Real/Imag",
             "bG:=", ["v:=", f"[{goal_value};]"]],
            "Weight:=", f"[{goal_weight};]"]
    arg = ["NAME:" + name, "IsEnabled:=", True,
           ["NAME:ProdOptiSetupDataV2", "SaveFields:=", False, "CopyMesh:=", False, "SolveWithCopiedMeshOnly:=", True],
           ["NAME:StartingPoint"],
           "Optimizer:=", optimizer,
           ["NAME:AnalysisStopOptions", "StopForNumIteration:=", True, "StopForElapsTime:=", False,
            "StopForSlowImprovement:=", False, "StopForGrdTolerance:=", False,
            "MaxNumIteration:=", mxi, "MaxSolTimeInSec:=", 3600, "RelGradientTolerance:=", 0,
            "MinNumIteration:=", min(10, mxi)],
           "CostFuncNormType:=", "L2", "PriorPSetup:=", "", "PreSolvePSetup:=", True,
           ["NAME:Variables"] + [x for v in variables for x in (v["name"] + ":=", "")],
           ["NAME:LCS"],
           ["NAME:Goals", goal],
           "Acceptable_Cost:=", 0, "Noise:=", 0.0001, "UpdateDesign:=", False,
           "UpdateIteration:=", 5, "KeepReportAxis:=", True, "UpdateDesignWhenDone:=", True]
    try:
        _opti(ctx).InsertSetup("OptiOptimization", arg)
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup(OptiOptimization) 失败: {type(e).__name__}: {e}"}

    if state is not None:
        if not hasattr(state, "optimizations"):
            state.optimizations = {}
        state.optimizations[name] = {"calculation": calculation, "variables": [v["name"] for v in variables]}
    return {"ok": True, "name": name, "calculation": calculation,
            "goal": f"{calculation} {condition} {goal_value}", "variables": [v["name"] for v in variables],
            "optimizer": optimizer, "max_iterations": mxi}


@tool({
    "type": "function",
    "function": {
        "name": "run_optimization",
        "description": "运行优化。**阻塞**,多轮求解迭代很久。须先 create_optimization。跑完 get_optimization_result。",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
})
def run_optimization(ctx, name):
    print(f"  [Optimizing] {name} ...")
    t0 = time.time()
    try:
        _opti(ctx).SolveSetup(name)
    except Exception as e:
        return {"ok": False, "error": f"优化求解失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    return {"ok": True, "name": name, "elapsed_sec": round(time.time() - t0, 1)}


@tool({
    "type": "function",
    "function": {
        "name": "get_optimization_result",
        "description": "取优化后 design 里各优化变量的值(最优解,HFSS 优化完成默认写回)。须先 run_optimization。",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
})
def get_optimization_result(ctx, name):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    opt_vars = []
    if state and hasattr(state, "optimizations") and name in state.optimizations:
        opt_vars = state.optimizations[name]["variables"]
    current = {}
    for v in opt_vars:
        try:
            current[v] = str(oDesign.GetVariableValue(v))
        except Exception:
            pass
    return {"ok": True, "name": name, "optimization_variables": opt_vars,
            "optimized_design_values": current,
            "note": "optimized_design_values 是优化完成后 design 中的变量值(最优解)。"}


# ─────────────────────────────────────────────────────────
# 灵敏度分析 —— Optimetrics OptiSensitivity
# 回答"该动哪个变量":在工作点附近算 ∂指标/∂变量,比粗扫便宜得多,
# 而且给的是**当前这个结构**的实测偏导(耦合关系自然体现),不是预先写死的经验映射。
# 参数结构照 AEDT 的 Tools→Record Script 录出来的官方调用(2025.2),不是猜的。
# ⚠️ 两个与 OptiOptimization 不同的坑:
#   ① 变量启用属性组是 "Sensitivity" 不是 "Optimization" —— 用错了变量不会出现在
#      Optimetrics 的变量表里(GUI 上表现为 Variables 标签页完全是空的)。
#   ② Goals 里 Ranges 的写法是 "Range:=", [...],而 OptiOptimization 是 ["NAME:Range", ...]。
# ─────────────────────────────────────────────────────────

import re as _re_sens

_NUM = _re_sens.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*$")


def _split_val(s):
    """'29mm' -> (29.0, 'mm');解析不了返回 (None, '')。"""
    m = _NUM.match(str(s))
    if not m:
        return None, ""
    return float(m.group(1)), m.group(2)


def _enable_sensitivity(oDesign, names):
    """把变量标成"参与灵敏度分析"。属性组名是 Sensitivity,**不是** Optimization。"""
    changed = [["NAME:" + n, ["NAME:Sensitivity", "Included:=", True]] for n in names]
    oDesign.ChangeProperty(
        ["NAME:AllTabs",
         ["NAME:LocalVariableTab",
          ["NAME:PropServers", "LocalVariables"],
          ["NAME:ChangedProps"] + changed]])


@tool({
    "type": "function",
    "function": {
        "name": "create_sensitivity",
        "description": (
            "建灵敏度分析:在当前工作点附近算**每个变量对指标的偏导**,回答\"该动哪个变量\"。"
            "典型用途:扫参之前先问一次 —— 三五个候选变量里哪个对频率最灵、哪个基本不影响,"
            "然后只扫真正有用的那个,省掉大半机时。"
            "与参扫的分工:参扫是**笛卡尔积铺开看全貌**,灵敏度是**工作点附近取少量点求梯度**,便宜得多。"
            "给的是当前这个结构的实测偏导,所以一个尺寸同时影响多个指标时,耦合关系直接看得见。"
            "建完用 run_sensitivity 跑。**要求该 setup 已有解**(梯度在工作点附近算)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "灵敏度 setup 名,如 'Sens1'"},
                "variables": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "min": {"type": "string", "description": "可选,默认当前值的 0.5 倍"},
                        "max": {"type": "string", "description": "可选,默认当前值的 1.5 倍"},
                        "initial_disp": {"type": "string",
                                         "description": "可选:初始扰动量,默认当前值的 10%。太小会被数值噪声淹没"},
                    }, "required": ["name"]},
                    "description": "要考察的变量,如 [{'name':'PL'},{'name':'PW'}]。只给 name 则范围用默认",
                },
                "calculation": {"type": "string",
                                "description": "考察哪个指标,如 'dB(S(P1,P1))'。表达式写法同 get_s_parameters"},
                "freq": {"type": "string", "description": "在哪个频点算,如 '2.4GHz';不传用 setup 的自适应频率"},
                "setup": {"type": "string", "description": "求解 setup 名,不传用第一个"},
                "sweep": {"type": "string", "default": "LastAdaptive"},
                "max_iterations": {"type": "integer", "default": 10, "description": "最大迭代次数,默认 10"},
            },
            "required": ["name", "variables", "calculation"],
        },
    },
})
def create_sensitivity(ctx, name, variables, calculation, freq=None, setup=None,
                       sweep="LastAdaptive", max_iterations=10):
    oDesign = ctx["oDesign"]
    state = ctx.get("state")
    setups = list(state.setups.keys()) if state else []
    if setup is None:
        if not setups:
            return {"ok": False, "error": "无 setup(重开工程后请显式传 setup)"}
        setup = setups[0]
    freq = freq or (state.setups.get(setup, {}).get("frequency") if state else None)
    if not freq:
        return {"ok": False, "error": "缺 freq 且无法从 setup 推断", "hint": "传 freq='2.4GHz'"}

    names = [v["name"] for v in variables]
    try:
        _enable_sensitivity(oDesign, names)
    except Exception as e:
        return {"ok": False, "error": f"启用变量的 Sensitivity 属性失败: {type(e).__name__}: {e}",
                "hint": "变量名是否拼错?必须是已 set_variable 建过的设计变量"}

    # 起点 = 变量当前值;未给范围时照 GUI 的默认:0.5x ~ 1.5x,初始扰动 10%
    start, var_block, defaulted = ["NAME:StartingPoint"], ["NAME:Variables"], []
    for v in variables:
        n = v["name"]
        try:
            cur = str(oDesign.GetVariableValue(n))
        except Exception as e:
            return {"ok": False, "error": f"取变量 '{n}' 当前值失败: {type(e).__name__}: {e}"}
        num, unit = _split_val(cur)
        if num is None and not all(k in v for k in ("min", "max", "initial_disp")):
            return {"ok": False, "error": f"变量 '{n}' 的值 '{cur}' 不是纯数值,无法推默认范围",
                    "hint": "表达式型变量请显式给 min/max/initial_disp,或先 set_variable 成纯数值"}
        vmin = v.get("min") or f"{num * 0.5:g}{unit}"
        vmax = v.get("max") or f"{num * 1.5:g}{unit}"
        idisp = v.get("initial_disp") or f"{num * 0.1:g}{unit}"
        if not (v.get("min") and v.get("max") and v.get("initial_disp")):
            defaulted.append({n: {"min": vmin, "max": vmax, "initial_disp": idisp}})
        start += [f"{n}:=", cur]
        var_block += [f"{n}:=", ["i:=", True, "int:=", False,
                                 "Min:=", vmin, "Max:=", vmax, "IDisp:=", idisp]]

    goal = ["NAME:Goal",
            "ReportType:=", "Modal Solution Data",
            "Solution:=", f"{setup} : {sweep}",
            ["NAME:SimValueContext"],                       # 灵敏度这里是空的,不带 Domain
            "Calculation:=", calculation, "Name:=", calculation,
            # 这里是 "Range:=", [...];OptiOptimization 那边是 ["NAME:Range", ...],别混
            ["NAME:Ranges",
             "Range:=", ["Var:=", "Freq", "Type:=", "d", "DiscreteValues:=", str(freq)]]]

    arg = ["NAME:" + name, "IsEnabled:=", True,
           ["NAME:ProdOptiSetupDataV2", "SaveFields:=", False, "CopyMesh:=", False,
            "SolveWithCopiedMeshOnly:=", True],
           start,
           "MaxIterations:=", int(max_iterations),
           "PriorPSetup:=", "", "PreSolvePSetup:=", True,
           var_block,
           ["NAME:LCS"],
           ["NAME:Goals", goal],
           "Primary Goal:=", -1, "PrimaryError:=", 0.0001,
           "Perform Worst Case Analysis:=", False]
    try:
        _opti(ctx).InsertSetup("OptiSensitivity", arg)
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup(OptiSensitivity) 失败: {type(e).__name__}: {e}",
                "hint": "同名 setup 已存在?被考察变量是表达式型?(参扫那边会自动钉成纯数值,这里不会)"}

    if state is not None:
        if not hasattr(state, "sensitivities"):
            state.sensitivities = {}
        state.sensitivities[name] = {"variables": names, "calculation": calculation,
                                     "setup": setup, "freq": freq}
    out = {"ok": True, "name": name, "setup": setup, "variables": names,
           "calculation": calculation, "freq": freq}
    if defaulted:
        out["defaulted_ranges"] = defaulted
        out["note_defaults"] = "未显式给范围的变量用了 GUI 默认:0.5x~1.5x,初始扰动 10%。"
    return out


@tool({
    "type": "function",
    "function": {
        "name": "run_sensitivity",
        "description": ("跑灵敏度分析(阻塞)。比参扫便宜但仍要多次求解,时间约 = 变量数 × 单点求解时间 × 迭代轮数,"
                        "调用前先预告耗时。跑完用 get_sensitivity_result 取偏导。"),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "灵敏度 setup 名"}}, "required": ["name"]},
    },
})
def run_sensitivity(ctx, name):
    print(f"  [Sensitivity] {name} ...")
    t0 = time.time()
    try:
        _opti(ctx).SolveSetup(name)
    except Exception as e:
        return {"ok": False, "error": f"灵敏度求解失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    return {"ok": True, "name": name, "elapsed_sec": round(time.time() - t0, 1),
            "hint": "用 get_sensitivity_result 取各变量的偏导"}


@tool({
    "type": "function",
    "function": {
        "name": "get_sensitivity_result",
        "description": (
            "取灵敏度分析结果:每个变量对指标的**一阶/二阶偏导**,并按影响力排好序。"
            "`dominant` 给出最灵的那个变量,`relative` 是各变量相对它的权重(0~1)—— "
            "**决定扫参该动谁就看这个**:权重远小于 1 的变量扫了也是白扫。"
            "二阶导大说明响应非线性强,线性外推估步长会不准,该缩小扫描范围。"
            "⚠️ 一阶导的单位是「指标单位 / 变量的 SI 单位(米)」,绝对值不直观;"
            "**用 relative 比值判断,别直接读绝对值**。"
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "灵敏度 setup 名"},
            "csv_path": {"type": "string", "description": "可选:导出 CSV 的落地路径,不传放 exports/"},
        }, "required": ["name"]},
    },
})
def get_sensitivity_result(ctx, name, csv_path=None):
    import os
    oDesign = ctx["oDesign"]
    from .session import EXPORTS_DIR
    csv_path = csv_path or os.path.join(EXPORTS_DIR, f"_sens_{name}.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)
    try:
        # 实测可用(2025.2):Optimetrics.ExportOptimetricsResult(setup, file)。
        # 灵敏度结果不是标准报告类型(GetAvailableReportTypes 里没有 Optimetrics),
        # 走不了 CreateReport→ExportToFile 那条路,只能用这个专用导出。
        oDesign.GetModule("Optimetrics").ExportOptimetricsResult(name, csv_path)
    except Exception as e:
        return {"ok": False, "error": f"ExportOptimetricsResult 失败: {type(e).__name__}: {e}",
                "hint": "该灵敏度 setup 跑过了吗(先 run_sensitivity)?名字是否拼对?"}
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) < 20:
        return {"ok": False, "error": "导出没产出内容,多半是这个 setup 还没有结果",
                "hint": "先 run_sensitivity 跑完再取"}

    rows = [ln.strip() for ln in open(csv_path, encoding="utf-8", errors="replace") if ln.strip()]
    # 表头: Input,Output,Func. Value,1st D,2nd D
    items, goal = [], None
    for ln in rows[1:]:
        # ⚠️ 不能简单按逗号切:指标表达式自己带逗号(dB(S(P1,P1)) 会被劈成两段)。
        # 结构是固定的「变量, 指标表达式..., 函数值, 一阶导, 二阶导」——
        # 第一段是变量名、最后三段是数,中间全是表达式,所以从两端往里切。
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 5:
            continue
        var = parts[0]
        try:
            fv, d1, d2 = float(parts[-3]), float(parts[-2]), float(parts[-1])
        except ValueError:
            continue
        goal = goal or ",".join(parts[1:-3]).strip()
        items.append({"variable": var, "value_at_point": fv,
                      "d1": d1, "d2": d2, "abs_d1": abs(d1)})
    if not items:
        return {"ok": False, "error": "解析不出灵敏度数据", "csv": csv_path,
                "header": rows[0][:160]}

    items.sort(key=lambda x: x["abs_d1"], reverse=True)
    top = items[0]["abs_d1"]
    for it in items:
        it["relative"] = round(it["abs_d1"] / top, 4) if top else 0.0
        # 二阶/一阶 的量级比:远大于 1 说明工作点附近非线性强
        it["nonlinearity"] = round(abs(it["d2"]) / it["abs_d1"], 1) if it["abs_d1"] else None
        it.pop("abs_d1")

    out = {"ok": True, "name": name, "goal": goal,
           "dominant": items[0]["variable"],
           "sensitivities": items,
           "csv": csv_path,
           "how_to_read": ("relative 是各变量相对最灵那个的权重;权重远小于 1 的扫了也是白扫。"
                           "nonlinearity = |2阶导/1阶导|,很大说明响应非线性强,线性外推估步长不准。"
                           "一阶导的绝对值带 SI 单位不直观,判断用 relative 比值。")}
    if len(items) > 1:
        r2 = items[1]["relative"]
        if r2 < 0.2:
            out["verdict"] = (f"'{items[0]['variable']}' 一家独大(次者只有 {r2:.0%}),"
                              "扫参只动它就行,其余固定。")
        elif r2 > 0.6:
            out["verdict"] = (f"'{items[0]['variable']}' 和 '{items[1]['variable']}' 量级相当,"
                              "单独扫任一个都会被另一个带偏,需要二维扫或先固定其一。")
    return out
