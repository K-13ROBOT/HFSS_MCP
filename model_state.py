import time
from dataclasses import dataclass, field


# 已知的"瞬时 gRPC 抽风"错误关键词,出现就重试
_RETRY_KEYWORDS = (
    "GetObjectsInGroup",
    "GetBoundaries",
    "GetProperties",
    "GetSolutionType",
    "GetMatchedObjectName",
)


def _retry_modeler(call, retries=2, delay=1.0):
    """对 HFSS 查询类调用做透明重试。遇到瞬时 gRPC 抽风等 1 秒再试一次。
    彻底失败(真错或重试用完)就把最后一次异常抛出去。
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return call()
        except Exception as e:
            last_exc = e
            msg = str(e)
            if any(kw in msg for kw in _RETRY_KEYWORDS) and attempt < retries:
                time.sleep(delay)
                continue
            raise
    raise last_exc  # 不该到这里


@dataclass
class Plan:
    """LLM 自管理的显式规划:目标 + 有序步骤 + 每步状态。
    通过 set_plan / update_plan_step 工具更新,在 state.summary() 里渲染给 LLM 看。
    """
    goal: str = ""
    steps: list = field(default_factory=list)  # [{"id":int, "title":str, "status":str, "note":str}]

    def render(self) -> str:
        if not self.steps:
            return ""
        marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]",
                 "skipped": "[-]", "blocked": "[!]"}
        lines = []
        if self.goal:
            lines.append(f"Goal: {self.goal}")
        for s in self.steps:
            mark = marks.get(s["status"], "[?]")
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"  {mark} {s['id']}. {s['title']}{note}")
        return "\n".join(lines)


@dataclass
class ModelState:
    project: str = ""
    design: str = ""
    solution_type: str = "Modal"

    variables: dict[str, str] = field(default_factory=dict)      # {"L1": "10mm"}
    materials: dict[str, dict] = field(default_factory=dict)     # 自定义材料
    objects: dict[str, dict] = field(default_factory=dict)       # {name: {type, material, ...}}
    boundaries: dict[str, dict] = field(default_factory=dict)    # {name: {type, faces, ...}}
    excitations: dict[str, dict] = field(default_factory=dict)   # ports / lumped
    setups: dict[str, dict] = field(default_factory=dict)        # {setup_name: {freq, sweeps,...}}

    plan: Plan = field(default_factory=Plan)                     # 显式规划

    last_action: str = ""
    last_error: str = ""

    def refresh_objects(self, hfss):
        """走 oEditor COM 直通,不走 PyAEDT objects_by_name cache。
        理由见 CLAUDE.md "PyAEDT 包装层 cache 不可靠" 一节。
        """
        from tools.primitives import _all_object_names, _object_material
        names = _all_object_names(hfss)
        self.objects = {n: {"material": _object_material(hfss, n)} for n in names}

    def refresh_variables(self, hfss):
        def _do():
            return {k: str(v) for k, v in hfss.variable_manager.variables.items()}
        self.variables = _retry_modeler(_do)

    def refresh_from_hfss(self, hfss):
        self.refresh_objects(hfss)
        self.refresh_variables(hfss)

    def summary(self) -> str:
        plan_rendered = self.plan.render()
        plan_block = f"Plan:\n{plan_rendered}\n" if plan_rendered else ""
        return (
            plan_block +
            f"Project={self.project} Design={self.design} ({self.solution_type})\n"
            f"Vars({len(self.variables)}): {self.variables}\n"
            f"Objects({len(self.objects)}): {list(self.objects)}\n"
            f"Boundaries({len(self.boundaries)}): {list(self.boundaries)}\n"
            f"Excitations({len(self.excitations)}): {list(self.excitations)}\n"
            f"Setups({len(self.setups)}): {list(self.setups)}\n"
            f"LastAction: {self.last_action}\n"
            f"LastError: {self.last_error}"
        )
