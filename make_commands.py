#!/usr/bin/env python
"""生成 commands/hfss-*.md —— 斜杠命令。

**只给两个**(建模 / 优化)。曾按 flow/ 的 11 张卡一一对应生成 11 个命令,那是把内部
文件结构当成了用户界面——用户脑子里只有"建模"和"优化",不会去想"我需要 feeding 那张卡"。
细分交给 SKILL.md 的路由表,命令只负责把人送进大门。

**命令体是指针,不许抄内容。** 这条自己破过一次:hfss-model 里的分支列表是手抄路由表、
hfss-tune 里把退出条件又写了一遍——改了 SKILL.md 命令不会跟着变,就是两份要同步。
现在:
  - 建模命令的分支列表 **从 SKILL.md 的路由表解析生成**,单一事实来源
  - 优化命令**不复述退出条件**,只指向 SKILL.md 的「卡住了怎么办」
`lint_skill.py` 会重新生成一遍跟磁盘上的比,不一致就报——改了路由表忘了重跑会被抓到。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "commands")
CORE_MD = os.path.join(ROOT, "skill", "hfss-design", "SKILL.md")
CORE = "用 Skill 工具加载 `hfss-design`(它的 `SKILL.md`)"

# 路由表里不属于"建模"的行,按关键词排除(调参/诊断归 /hfss-tune)
_TUNE_ROWS = ("不达标", "不知道为什么")


def routing_rows():
    """解析 SKILL.md 路由表 → [(任务, 去向, 铁律)]。表头/分隔行跳过。
    第三列是"就算不读卡也要记住的那一条"——命令里同样带上:卡不一定在上下文里,
    命令体和路由表一定在。"""
    txt = io.open(CORE_MD, encoding="utf-8").read()
    m = re.search(r"\|\s*任务\s*\|\s*必须先读\s*\|.*\n\|[-\s|]+\|\n((?:\|.*\n)+)", txt)
    if not m:
        sys.exit("!! 解析不到 SKILL.md 的路由表 —— 表头是不是改了?"
                 "(期望 | 任务 | 必须先读 | ... |)")
    rows = []
    for line in m.group(1).strip().split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0]:
            rows.append((cells[0], cells[1], cells[2] if len(cells) > 2 else ""))
    return rows


def model_branches():
    """建模命令的分支列表,从路由表生成(排除调参/诊断那两行)"""
    out = []
    for task, dest, rule in routing_rows():
        if any(k in task for k in _TUNE_ROWS):
            continue
        # 路由表里是 [`flow/x.md`](flow/x.md) — 命令里只要反引号形式
        dest = re.sub(r"\[`([^`]+)`\]\([^)]+\)", r"`\1`", dest)
        out.append(f"- {task} → {dest}" + (f"\n  ⚠️ {rule}" if rule else ""))
    return "\n".join(out)


MODEL = """# HFSS 建模:把天线建出来并求解

先{core} —— 常驻约定(坐标层叠、sheet 规则、故障判定、卡住了怎么办),
**再按它的路由表判断这次属于哪种,去读对应的流程卡**(路径相对 skill 目录):

{branches}

一个任务读 3~4 份是正常的。任务性质中途变了就回路由表重查;建完发现指标差得远 → 转 `/hfss-tune`。

> 上面这份分支列表由 `make_commands.py` 从 `SKILL.md` 的路由表生成,别手改 ——
> 改路由表后重跑脚本即可。

---

用户的要求:

$ARGUMENTS
"""

TUNE = """# HFSS 优化:指标不达标,去调

1. {core} —— 其中「卡住了怎么办」定义了什么时候必须停手、"一轮"怎么数、未达标项怎么列。
2. 读 skill 目录下的 `flow/tuning.md` —— 调参流程卡,严格按它执行。

⚠️ {tune_rule}

调不动、或不知道为什么不工作 → 按退出条件转 `flow/diagnose-current.md` 看机理。

---

用户的要求:

$ARGUMENTS
"""


def tune_rule():
    """调参命令里那条"就算不读卡也要记住"的铁律,取自路由表调参那行的第三列。
    曾在命令里手写"顺序别搞反:先灵敏度再扫参……",卡里加了第零步网格校准之后
    它立刻就对不上了——所以改成和建模命令一样从路由表生成。"""
    for task, dest, rule in routing_rows():
        if "不达标" in task and rule:
            return rule
    sys.exit("!! 路由表里找不到调参那行(任务列含「不达标」)的铁律")


def build():
    return {
        "hfss-model.md": MODEL.format(core=CORE, branches=model_branches()),
        "hfss-tune.md": TUNE.format(core=CORE, tune_rule=tune_rule()),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    want = build()
    for f in sorted(os.listdir(OUT)):
        if f.startswith("hfss-") and f.endswith(".md") and f not in want:
            os.remove(os.path.join(OUT, f))
            print(f"  删旧命令 commands/{f}")
    for name, body in want.items():
        io.open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n").write(body)
        print(f"  生成 commands/{name}")
    print(f"\n共 {len(want)} 个命令;建模分支列表从 SKILL.md 路由表生成。")


if __name__ == "__main__":
    main()
