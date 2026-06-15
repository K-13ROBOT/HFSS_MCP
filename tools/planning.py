"""显式规划工具 —— LLM 处理多步任务前先 set_plan 立目标,执行中 update_plan_step 改状态。

Plan 不依赖 HFSS 桌面,任何时候都能调(包括 HFSS 还没打开时就想列计划)。
渲染出的 plan 会自动通过 state.summary() 注入 LLM 的 context,
所以 LLM 每轮都看得到最新进度,不会"忘了大目标"。
"""

from . import tool, NO_HFSS_REQUIRED


# 这几个工具不操 HFSS,不需要 active design
NO_HFSS_REQUIRED.update({"set_plan", "update_plan_step"})


_VALID_STATUSES = {"pending", "in_progress", "done", "skipped", "blocked"}
_MARKS = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]",
          "skipped": "[-]", "blocked": "[!]"}


@tool({
    "type": "function",
    "function": {
        "name": "set_plan",
        "description": (
            "面对多步任务(≥3 步,如完整建模+仿真+扫参+优化、阵列设计、多目标调优)时,"
            "**先调本工具列出整体规划**,再开始执行。立此一次即可,后续用 update_plan_step 改单步状态。"
            "单工具就能搞定的简单任务**不要调**,免得啰嗦。重新立 plan 会覆盖旧的。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "总体目标一句话,如 '2.4GHz 缝隙耦合贴片,S11<-15dB,然后扩成 4 元线阵增益>10dBi'",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": "有序步骤列表,每项一句话描述要做什么。系统会自动按 1..N 编号",
                },
            },
            "required": ["goal", "steps"],
        },
    },
})
def set_plan(ctx, goal, steps):
    plan = ctx["state"].plan
    plan.goal = goal
    plan.steps = [
        {"id": i + 1, "title": s, "status": "pending", "note": ""}
        for i, s in enumerate(steps)
    ]
    print(f"\n[Plan] 目标:{goal}")
    for s in plan.steps:
        print(f"  [ ] {s['id']}. {s['title']}")
    return {"ok": True, "goal": goal, "n_steps": len(plan.steps)}


@tool({
    "type": "function",
    "function": {
        "name": "update_plan_step",
        "description": (
            "更新某个 plan 步骤的状态。"
            "开始做某步前置 'in_progress',完成置 'done',"
            "决定不做置 'skipped'(note 写原因),卡住置 'blocked'(note 写卡哪了)。"
            "一次只改一步;有多步同时变化分多次调。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "minimum": 1,
                       "description": "步骤编号(从 1 开始,跟 set_plan 时的顺序对应)"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "skipped", "blocked"],
                    "description": "新状态",
                },
                "note": {
                    "type": "string",
                    "description": "(可选)补充说明,如实际取的参数值、跳过原因、卡住的错误",
                },
            },
            "required": ["id", "status"],
        },
    },
})
def update_plan_step(ctx, id, status, note=""):
    plan = ctx["state"].plan
    if status not in _VALID_STATUSES:
        return {"ok": False, "error": f"status 必须是 {sorted(_VALID_STATUSES)} 之一"}
    if not plan.steps:
        return {"ok": False, "error": "还没立 plan,先调 set_plan"}

    target = next((s for s in plan.steps if s["id"] == id), None)
    if target is None:
        return {"ok": False,
                "error": f"步骤 {id} 不存在,当前 plan 只有 {len(plan.steps)} 步(1..{len(plan.steps)})"}

    target["status"] = status
    if note:
        target["note"] = note

    mark = _MARKS.get(status, "[?]")
    note_str = f" — {note}" if note else ""
    print(f"\n[Plan] {mark} {id}. {target['title']}{note_str}")

    done_n = sum(1 for s in plan.steps if s["status"] == "done")
    return {"ok": True, "id": id, "status": status,
            "progress": f"{done_n}/{len(plan.steps)} done"}
