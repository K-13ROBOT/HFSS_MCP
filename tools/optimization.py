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
