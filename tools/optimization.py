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
    if setup is None:   # 只有没显式给 setup 才需要 state;重开工程后 state.setups 为空,显式给的不该被挡
        if not setups:
            return {"ok": False, "error": "无 setup(重开工程后请显式传 setup)"}
        setup = setups[0]
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
        "description": ("建灵敏度分析:在当前工作点附近算**每个变量对指标的偏导**,回答\"该动哪个变量\"。"
            "与参扫的分工:参扫是笛卡尔积铺开看全貌,灵敏度是工作点附近取少量点求梯度,便宜得多。"
            "**要求该 setup 已有解**(梯度在工作点附近算)。建完用 run_sensitivity 跑。"
            "什么时候该先做这一步,见 `flow/tuning.md`。"),
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
        "description": ("取灵敏度结果:每个变量对指标的一阶/二阶偏导,按影响力排序。"
            "`dominant` 是最灵的变量,`relative` 是各变量相对它的权重(0~1),"
            "`nonlinearity` = |二阶导/一阶导|。⚠️ 一阶导带 SI 单位(每米),绝对值不直观,"
            "**判断用 relative 比值**。怎么据此定扫参策略,见 `flow/tuning.md`。"),
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


# ─────────────────────────────────────────────────────────
# 统计分析(蒙特卡洛)—— Optimetrics OptiStatistical
# 回答"按这个公差投产,良率是多少":给变量加分布,HFSS 随机采样跑 N 次,
# 统计指标的分布。公差/良率不用自己造轮子,HFSS 本来就有。
# 参数结构照 Tools→Record Script 录出来的官方调用(2025.2)。
# ⚠️ 三个不同于灵敏度的地方:
#   ① 变量启用属性组是 "Statistical" —— 这是第三个组(另两个是 Optimization / Sensitivity),
#      每种分析各用各的,用错了变量不出现在表里且没有任何报错。
#   ② MaxIterations 就是试验次数(GUI 对话框里压根没这个字段,默认 50)。
#   ③ 高斯分布的 Min/Max 是 **σ 单位的截断**(默认 ±3σ),不是变量的量纲;
#      变量本身的边界另有 VarMin/VarMax。LatinHypercube 是**字符串** "true"。
# ─────────────────────────────────────────────────────────

_DISTS = ("Gaussian", "Uniform", "Lognormal")


def _enable_statistical(oDesign, names):
    """把变量标成"参与统计分析"。属性组名是 Statistical。"""
    changed = [["NAME:" + n, ["NAME:Statistical", "Included:=", True]] for n in names]
    oDesign.ChangeProperty(
        ["NAME:AllTabs",
         ["NAME:LocalVariableTab",
          ["NAME:PropServers", "LocalVariables"],
          ["NAME:ChangedProps"] + changed]])


@tool({
    "type": "function",
    "function": {
        "name": "create_statistical",
        "description": (
            "建统计分析(蒙特卡洛):给变量加**公差分布**,随机采样跑 N 次,看指标的分布和良率。"
            "回答的是\"按这个加工公差投产,有多少比例的板子能达标\" —— 仿真漂亮但批量下来一半不合格,"
            "就是没做过这一步。与灵敏度的分工:灵敏度问\"动哪个变量\",统计分析问\"变量抖动时指标散多少\"。"
            "**代价是 trials 次完整求解**,调用前务必预告耗时。建完用 run_statistical 跑。"
            "什么时候该做、结果怎么用,见 `flow/tuning.md`。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "统计 setup 名,如 'Stat1'"},
                "variables": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "distribution": {"type": "string", "enum": ["Gaussian", "Uniform", "Lognormal"],
                                         "default": "Gaussian",
                                         "description": "加工公差一般用 Gaussian;最坏情况估计用 Uniform"},
                        "std_dev": {"type": "string",
                                    "description": "Gaussian 的标准差,带单位(如 '0.1mm')。"
                                                   "**板厂给的 ±公差通常是 3σ**,所以 ±0.3mm 的公差对应 std_dev='0.1mm'"},
                        "tolerance": {"type": "string",
                                      "description": "Uniform 用的容差,百分比(如 '1%')或带单位"},
                        "sigma_clip": {"type": "number", "default": 3,
                                       "description": "Gaussian 截断在几倍 σ,默认 3"},
                    }, "required": ["name"]},
                    "description": "加公差的变量。Gaussian 给 std_dev,Uniform 给 tolerance",
                },
                "calculation": {"type": "string", "description": "考察哪个指标,如 'dB(S(P1,P1))'"},
                "freq": {"type": "string", "description": "在哪个频点算,不传用 setup 的自适应频率"},
                "setup": {"type": "string", "description": "求解 setup 名,不传用第一个"},
                "sweep": {"type": "string", "default": "LastAdaptive"},
                "trials": {"type": "integer", "default": 50,
                           "description": "跑几次(= MaxIterations)。**每次都是一次完整求解**,"
                                          "先用 10~20 看趋势,要可信的良率数字才上 50+"},
                "latin_hypercube": {"type": "boolean", "default": True,
                                    "description": "拉丁超立方采样,少量试验下覆盖比纯随机均匀得多,建议开"},
                "seed": {"type": "integer", "default": 0, "description": "随机种子,0 = 每次不同"},
            },
            "required": ["name", "variables", "calculation"],
        },
    },
})
def create_statistical(ctx, name, variables, calculation, freq=None, setup=None,
                       sweep="LastAdaptive", trials=50, latin_hypercube=True, seed=0):
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
        _enable_statistical(oDesign, names)
    except Exception as e:
        return {"ok": False, "error": f"启用变量的 Statistical 属性失败: {type(e).__name__}: {e}",
                "hint": "变量名是否拼错?必须是已 set_variable 建过的设计变量"}

    start, var_block = ["NAME:StartingPoint"], ["NAME:Variables"]
    for v in variables:
        n = v["name"]
        dist = v.get("distribution", "Gaussian")
        if dist not in _DISTS:
            return {"ok": False, "error": f"不支持的分布 '{dist}'", "hint": f"可选: {_DISTS}"}
        try:
            cur = str(oDesign.GetVariableValue(n))
        except Exception as e:
            return {"ok": False, "error": f"取变量 '{n}' 当前值失败: {type(e).__name__}: {e}"}
        num, unit = _split_val(cur)
        if dist == "Gaussian" and not v.get("std_dev"):
            return {"ok": False, "error": f"变量 '{n}' 用 Gaussian 必须给 std_dev",
                    "hint": "板厂的 ±公差通常是 3σ,±0.3mm 对应 std_dev='0.1mm'"}
        if dist == "Uniform" and not v.get("tolerance"):
            return {"ok": False, "error": f"变量 '{n}' 用 Uniform 必须给 tolerance",
                    "hint": "如 '1%' 或 '0.3mm'"}
        clip = float(v.get("sigma_clip", 3))
        vmin = f"{num * 0.5:g}{unit}" if num is not None else cur
        vmax = f"{num * 1.5:g}{unit}" if num is not None else cur
        start += [f"{n}:=", cur]
        var_block += [f"{n}:=", [
            "i:=", True, "int:=", False,
            "Dist:=", dist,
            "Tol:=", str(v.get("tolerance", "10%")),
            "StdD:=", str(v.get("std_dev", "0")),
            # 高斯的 Min/Max 是 σ 倍数,不是变量量纲
            "Min:=", f"{-clip:g}", "Max:=", f"{clip:g}",
            "Shape:=", "1", "Scale:=", f"{num * 0.1:g}{unit}" if num is not None else "0",
            "Location:=", cur, "Dataset:=", "",
            "LatinHypercube:=", "true" if latin_hypercube else "false",
            "VarMin:=", vmin, "VarMax:=", vmax,
            "Prob:=", "0", "Mean:=", cur]]

    goal = ["NAME:Goal",
            "ReportType:=", "Modal Solution Data",
            "Solution:=", f"{setup} : {sweep}",
            ["NAME:SimValueContext"],
            "Calculation:=", calculation, "Name:=", calculation,
            ["NAME:Ranges",
             "Range:=", ["Var:=", "Freq", "Type:=", "d", "DiscreteValues:=", str(freq)]]]

    arg = ["NAME:" + name, "IsEnabled:=", True,
           ["NAME:ProdOptiSetupDataV2", "SaveFields:=", False, "CopyMesh:=", False,
            "SolveWithCopiedMeshOnly:=", True],
           start,
           "MaxIterations:=", int(trials),
           "SeedValue:=", int(seed),
           "PriorPSetup:=", "",
           var_block,
           ["NAME:Goals", goal]]
    try:
        _opti(ctx).InsertSetup("OptiStatistical", arg)
    except Exception as e:
        return {"ok": False, "error": f"InsertSetup(OptiStatistical) 失败: {type(e).__name__}: {e}",
                "hint": "同名 setup 已存在?变量是表达式型?"}

    if state is not None:
        if not hasattr(state, "statisticals"):
            state.statisticals = {}
        state.statisticals[name] = {"variables": names, "calculation": calculation,
                                    "setup": setup, "freq": freq, "trials": int(trials)}
    return {"ok": True, "name": name, "setup": setup, "variables": names,
            "calculation": calculation, "freq": freq, "trials": int(trials),
            "latin_hypercube": bool(latin_hypercube),
            "warn_cost": f"跑这个要 {int(trials)} 次完整求解 —— 先跟用户确认耗时再 run_statistical。"}


@tool({
    "type": "function",
    "function": {
        "name": "run_statistical",
        "description": ("跑统计分析(阻塞,**trials 次完整求解**)。时间 = trials × 单点求解时间,"
                        "动辄几十分钟到几小时,调用前必须预告耗时并等用户确认。"
                        "跑完用 get_statistical_result 取分布与良率。"),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "统计 setup 名"}}, "required": ["name"]},
    },
})
def run_statistical(ctx, name):
    print(f"  [Statistical] {name} ...")
    t0 = time.time()
    try:
        _opti(ctx).SolveSetup(name)
    except Exception as e:
        return {"ok": False, "error": f"统计分析求解失败: {type(e).__name__}: {e}",
                "elapsed_sec": round(time.time() - t0, 1)}
    return {"ok": True, "name": name, "elapsed_sec": round(time.time() - t0, 1),
            "hint": "用 get_statistical_result 取分布与良率"}


@tool({
    "type": "function",
    "function": {
        "name": "get_statistical_result",
        "description": (
            "取统计分析结果:指标在公差抖动下的**分布**(均值/标准差/最值/分位数),"
            "给了 spec 还会算**良率**(满足规格的试验占比)。"
            "良率低说明设计对公差敏感 —— 配合灵敏度分析能定位是哪个变量在拖后腿,"
            "进而决定该找板厂把哪一项卡紧。结果怎么用见 `flow/tuning.md`。"
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "统计 setup 名"},
            "spec_op": {"type": "string", "enum": ["<=", ">=", "<", ">"], "default": "<=",
                        "description": "规格方向。S11/VSWR/AR 用 <=,增益/带宽用 >="},
            "spec_value": {"type": "number", "description": "规格门限,如 -10(dB)。不传则只给分布不算良率"},
            "csv_path": {"type": "string", "description": "可选:导出 CSV 落地路径"},
        }, "required": ["name"]},
    },
})
def get_statistical_result(ctx, name, spec_op="<=", spec_value=None, csv_path=None):
    import os
    oDesign = ctx["oDesign"]
    from .session import EXPORTS_DIR
    csv_path = csv_path or os.path.join(EXPORTS_DIR, f"_stat_{name}.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)
    try:
        oDesign.GetModule("Optimetrics").ExportOptimetricsResult(name, csv_path)
    except Exception as e:
        return {"ok": False, "error": f"ExportOptimetricsResult 失败: {type(e).__name__}: {e}",
                "hint": "这个统计 setup 跑过了吗(先 run_statistical)?"}
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) < 20:
        return {"ok": False, "error": "导出没产出内容,多半是还没有结果", "hint": "先 run_statistical"}

    rows = [ln.strip() for ln in open(csv_path, encoding="utf-8", errors="replace") if ln.strip()]
    if len(rows) < 2:
        return {"ok": False, "error": "结果为空", "csv": csv_path}
    # 同灵敏度:指标表达式自己带逗号,不能简单按逗号切。数值列在最右端。
    header = rows[0]
    vals = []
    for ln in rows[1:]:
        parts = [p.strip() for p in ln.split(",")]
        got = None
        for p in reversed(parts):          # 从右往左找第一个能转成浮点的
            try:
                got = float(p); break
            except ValueError:
                continue
        if got is not None:
            vals.append(got)
    if not vals:
        return {"ok": False, "error": "解析不出数值", "csv": csv_path, "header": header[:160]}

    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n
    sd = var ** 0.5
    sv = sorted(vals)

    def pct(q):
        i = max(0, min(n - 1, int(round(q * (n - 1)))))
        return round(sv[i], 4)

    out = {"ok": True, "name": name, "n_trials": n,
           "mean": round(mean, 4), "std_dev": round(sd, 4),
           "min": round(sv[0], 4), "max": round(sv[-1], 4),
           "p05": pct(0.05), "median": pct(0.5), "p95": pct(0.95),
           "spread": round(sv[-1] - sv[0], 4), "csv": csv_path}
    if spec_value is not None:
        ops = {"<=": lambda x: x <= spec_value, ">=": lambda x: x >= spec_value,
               "<": lambda x: x < spec_value, ">": lambda x: x > spec_value}
        passed = sum(1 for x in vals if ops[spec_op](x))
        out["spec"] = f"{spec_op} {spec_value}"
        out["pass_count"] = passed
        out["yield_pct"] = round(passed / n * 100, 1)
        if n < 20:
            out["note_n"] = (f"只有 {n} 次试验,良率数字的置信区间很宽(±{100/n**0.5:.0f}% 量级),"
                             "只能看趋势。要可信的良率跑 50+ 次。")
        if out["yield_pct"] < 90:
            out["verdict"] = ("良率偏低,设计对公差敏感。配合 get_sensitivity_result 看是哪个变量主导,"
                              "再决定收紧公差还是改设计让它对该变量不敏感。")
    return out
