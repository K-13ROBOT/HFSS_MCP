#!/usr/bin/env python
"""从一张表生成 commands/hfss-*.md —— 每个斜杠命令对应一张流程卡。

为什么要生成而不是手写 11 个文件:它们只差"读哪张卡"一行,手写必然逐渐跑偏。
为什么要落成真文件而不是安装时才拼:落在仓库里才能 review、才能被 lint 查引用。

命令体是**指针**,绝不复制流程卡内容 —— 复制了就是两份要同步。
"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "commands")

# (命令名, 一句话, 流程卡, 这个命令最典型的用户说法)
CARDS = [
    ("hfss-reproduce", "复现文献:先解析结构图再建模", "reproduce-paper.md",
     "按这篇论文建一个 / 复现这个天线"),
    ("hfss-spec", "正向设计:从指标推尺寸的闭环", "design-loop.md",
     "设计一个 2.4GHz、S11<-10dB、增益≥6dBi 的天线"),
    ("hfss-solve", "S 参数仿真完整流程(顺序敏感)", "s-parameters.md",
     "跑一下 S11 / 求解这个设计"),
    ("hfss-farfield", "远场:增益 / 轴比 / HPBW / 前后比 / 隔离度", "farfield.md",
     "看看方向图 / 算轴比"),
    ("hfss-feeding", "非标准馈电:缝隙 / 近耦合 / CPW / 差分 / 多层", "feeding.md",
     "这个是缝隙耦合馈电,怎么建"),
    ("hfss-tuning", "调参:灵敏度 → 扫参 → 公差 → 优化", "tuning.md",
     "S11 不够深,帮我调 / 扫一下参数"),
    ("hfss-diagnose", "看机理:电流分布诊断(指标不对但不知道为什么)", "diagnose-current.md",
     "调不动了,不知道哪儿出了问题"),
    ("hfss-eigenmode", "本征模:不要端口,直接解谐振频率与 Q", "eigenmode.md",
     "算这个腔体的谐振频率 / 这个 DRA 支持哪些模"),
    ("hfss-periodic", "周期单元:无限阵 / FSS / 超表面", "periodic.md",
     "做一个 FSS 单元 / 无限阵单元仿真"),
    ("hfss-geometry", "进阶几何:阵列复制 / 边界 / 网格 / 螺旋", "geometry-advanced.md",
     "排个 4×4 阵 / 这个螺旋怎么建"),
    ("hfss-capture", "收工沉淀:把经验记进 knowledge/、把设计录成 design/ 卡片", "capture-learning.md",
     "这次的经验记一下 / 把这个设计录成卡片"),
]

TPL = """# {title}

读下面两份,**严格按它们执行**,别凭印象做:

1. `~/.claude/skills/hfss-design/SKILL.md` —— 常驻约定(坐标层叠、sheet 规则、故障判定、
   卡住了怎么办)。**其中「卡住了怎么办」那几条退出条件是可数的,到了就停。**
2. `~/.claude/skills/hfss-design/flow/{card}` —— 本命令对应的流程卡。

卡里指到别的卡(或 `knowledge/` / `design/`)时照样去读 —— 一个任务读 3~4 份是正常的。

⚠️ **任务性质中途变了就回 `SKILL.md` 的路由表重查**,别抱着这张卡走到黑。
最常见的转变:调着调着发现其实不知道为什么不工作 → 该转 `/hfss-diagnose`。

---

{args}
"""

os.makedirs(OUT, exist_ok=True)
for name, title, card, example in CARDS:
    body = TPL.format(title=f"{title}", card=card,
                      args="$ARGUMENTS" if True else "")
    body = body.replace("---\n\n$ARGUMENTS\n",
                        f"用户的具体要求(例如「{example}」):\n\n$ARGUMENTS\n")
    io.open(os.path.join(OUT, name + ".md"), "w", encoding="utf-8", newline="\n").write(body)
    print(f"  生成 commands/{name}.md  -> flow/{card}")

print(f"\n共 {len(CARDS)} 个命令。install.py --skill-user 会把它们装到 ~/.claude/commands/")
