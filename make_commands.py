#!/usr/bin/env python
"""生成 commands/hfss-*.md —— 斜杠命令。

**只给两个。** 曾经按 flow/ 的 11 张卡一一对应生成 11 个命令,那是把内部文件结构
当成了用户界面——用户脑子里只有"建模"和"优化"两件事,不会去想"我需要 feeding 那张卡"。
细分交给 SKILL.md 的路由表(agent 读了自己判断),命令只负责把人送进大门。

命令体是**指针**,绝不复制流程卡内容 —— 复制了就是两份要同步。
"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "commands")

CORE = "`~/.claude/skills/hfss-design/SKILL.md`"

MODEL = """# HFSS 建模:把天线建出来并求解

读 {core} —— 常驻约定(坐标层叠、sheet 规则、故障判定、卡住了怎么办),
**然后按它的路由表判断这次属于哪种,去读对应的流程卡**:

- 照论文尺寸复现 → `flow/reproduce-paper.md`(先解析结构图,治"建歪")
- 给的是指标不是尺寸 → `flow/design-loop.md`(正向设计闭环)
- 要跑 S 参数 / 完整求解 → `flow/s-parameters.md`(**顺序敏感,跳步会白跑**)
- 非标准馈电(缝隙/近耦合/CPW/差分/多层)→ `flow/feeding.md`
- 要远场(增益/轴比/HPBW)→ `flow/farfield.md`
- 腔体/滤波器/DRA 要谐振频率与 Q → `flow/eigenmode.md`(不要端口)
- 无限阵 / FSS / 超表面单元 → `flow/periodic.md`
- 阵列复制、改网格、建螺旋 → `flow/geometry-advanced.md`
- 板厂叠层表还原多层板 → 转 `hfss-stackup` skill

**开工先读 `flow/capture-learning.md`**(经验库 + 卡片库),站在过往经验上;
**收工回去记**——这是整套东西复利增长的机制,跳过它每次都从零踩坑。

一个任务读 3~4 份是正常的。拿不准读哪张就先读路由表。

---

用户的要求:

$ARGUMENTS
"""

TUNE = """# HFSS 优化:指标不达标,去调

读 {core} —— 常驻约定,**尤其是「卡住了怎么办」那几条可数的退出条件**。
然后读 `~/.claude/skills/hfss-design/flow/tuning.md`:灵敏度 → 扫参 → 公差 → 优化。

**顺序别搞反:**
1. 先用**灵敏度**问"该动哪个变量" —— 权重远小于 1 的扫了也是白扫
2. 再**扫参**。多变量先看敏感性,别直接上笛卡尔积
3. 达标之后、投板之前才做**公差与良率**(调参过程中做是白做,设计还在变)

⚠️ **退出条件是可数的,不是靠判断**:连续两轮扫参后 `check_design_targets` 的
`failed_metrics` 没少一项,就停 —— 转去 `flow/diagnose-current.md` 看电流分布,
搞清楚为什么不工作。

**「方向是对的、只是力度不够」是最贵的自我说服,每信一次就是一整轮机时。**
把每轮的 `failed_metrics` 记在回复里,这样"有没有少一项"是能数的。

---

用户的要求:

$ARGUMENTS
"""

CMDS = [("hfss-model", MODEL), ("hfss-tune", TUNE)]

os.makedirs(OUT, exist_ok=True)
# 先清掉本脚本不再生成的旧命令(曾经有 11 个)
keep = {n + ".md" for n, _ in CMDS}
for f in sorted(os.listdir(OUT)):
    if f.startswith("hfss-") and f.endswith(".md") and f not in keep:
        os.remove(os.path.join(OUT, f))
        print(f"  删旧命令 commands/{f}")

for name, tpl in CMDS:
    io.open(os.path.join(OUT, name + ".md"), "w", encoding="utf-8", newline="\n").write(
        tpl.format(core=CORE))
    print(f"  生成 commands/{name}.md")

print(f"\n共 {len(CMDS)} 个命令。细分由 SKILL.md 的路由表负责。")
