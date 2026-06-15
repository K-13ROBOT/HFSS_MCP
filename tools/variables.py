"""设计变量(native COM 版)—— oDesign.ChangeProperty 操作 LocalVariables。"""

from . import tool


def _existing_vars(oDesign):
    try:
        return set(oDesign.GetVariables() or [])
    except Exception:
        return set()


@tool({
    "type": "function",
    "function": {
        "name": "set_variable",
        "description": ("定义或修改设计变量。表达式带单位或引用其它变量(如 '20mm'、'L1/2'、'2*pi')。"
                        "复杂结构先 set_variable 再用变量名建几何。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "变量名,英文字母开头"},
                "expression": {"type": "string", "description": "值/表达式,如 '20mm'、'L1+1mm'"},
            },
            "required": ["name", "expression"],
        },
    },
})
def set_variable(ctx, name, expression):
    oDesign = ctx["oDesign"]
    exists = name in _existing_vars(oDesign)
    try:
        if exists:
            changed = ["NAME:ChangedProps", ["NAME:" + name, "Value:=", str(expression)]]
        else:
            changed = ["NAME:NewProps",
                       ["NAME:" + name, "PropType:=", "VariableProp", "UserDef:=", True,
                        "Value:=", str(expression)]]
        oDesign.ChangeProperty(
            ["NAME:AllTabs",
             ["NAME:LocalVariableTab",
              ["NAME:PropServers", "LocalVariables"],
              changed]])
    except Exception as e:
        return {"ok": False, "error": f"设变量失败: {type(e).__name__}: {e}"}
    if "state" in ctx:
        ctx["state"].variables[name] = str(expression)
    return {"ok": True, "name": name, "expression": str(expression), "updated": exists}


@tool({
    "type": "function",
    "function": {
        "name": "list_variables",
        "description": "列出当前 design 的所有变量及其值。",
        "parameters": {"type": "object", "properties": {}},
    },
})
def list_variables(ctx):
    oDesign = ctx["oDesign"]
    out = {}
    try:
        for v in (oDesign.GetVariables() or []):
            try:
                out[str(v)] = str(oDesign.GetVariableValue(v))
            except Exception:
                out[str(v)] = None
    except Exception as e:
        return {"ok": False, "error": f"取变量失败: {type(e).__name__}: {e}"}
    return {"ok": True, "count": len(out), "variables": out}
