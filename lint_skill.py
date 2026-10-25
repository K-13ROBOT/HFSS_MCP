#!/usr/bin/env python
"""skill 引用体检:拆成多张流程卡之后,跨文件引用没法靠人盯,交给脚本。

查四类问题 —— 都是真踩过的:
  1. 指向不存在的 .md(相对链接、以及正文里写成 `flow/xxx.md` 的裸引用)
  2. 指向本文件不存在的 §节号(搬节之后最容易留下的残留)
  3. **跨文件的"第 N 步"悬空指代** —— "上面第 11 步"这种,搬走之后单独读这张卡就找不到
  4. 工具描述里引用的 skill 位置失效(SKILL.md §x 已经被搬走)

install.py 分发前会自动跑一次;也可以单独 `python lint_skill.py`。
退出码非 0 表示有问题。
"""
import io
import os
import re
import sys
import glob

ROOT = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(ROOT, "skill")


def _read(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


def _own_sections(txt):
    """本文件自己定义的节号(含三四级标题)"""
    return {h.rstrip(".") for h in re.findall(r"(?m)^#{2,4} ([\d.]+)", txt)}


def check(verbose=True):
    problems = []
    md_files = glob.glob(os.path.join(SKILLS, "**", "*.md"), recursive=True)

    # 每个 skill 的 SKILL.md 节号,供同 skill 内的 §引用核对
    core_sections = {}
    for p in md_files:
        if os.path.basename(p) == "SKILL.md":
            core_sections[os.path.dirname(p)] = _own_sections(_read(p))

    for p in md_files:
        txt = _read(p)
        rel = os.path.relpath(p, ROOT)
        d = os.path.dirname(p)
        # 该文件属于哪个 skill(flow/ knowledge/ 等子目录往上找)
        skill_dir = d
        while skill_dir != SKILLS and not os.path.exists(os.path.join(skill_dir, "SKILL.md")):
            skill_dir = os.path.dirname(skill_dir)
        allowed = _own_sections(txt) | core_sections.get(skill_dir, set())

        # ① 相对链接
        for link in re.findall(r"\]\(([^)#]+\.md)\)", txt):
            if link.endswith("papers/INDEX.md"):
                continue        # 个人原文索引,只在本机、不随分发,缺了是正常的
            if not os.path.exists(os.path.join(d, link)):
                problems.append(f"[死链] {rel} -> {link}")

        # ② 正文里的裸文件引用 `flow/xxx.md` / `xxx.md`。
        #    跨 skill 引用写成 `hfss-design` 的 `flow/xxx.md`,去对方目录下找。
        others = [os.path.join(SKILLS, m) for m in set(re.findall(r"`(hfss-[a-z]+)`", txt))]
        for fn in set(re.findall(r"`((?:flow/)?[a-z][a-z0-9-]*\.md)`", txt)):
            cand = [os.path.join(d, fn), os.path.join(skill_dir, fn)]
            cand += [os.path.join(o, fn) for o in others]
            if not any(os.path.exists(c) for c in cand):
                problems.append(f"[引用的文件不存在] {rel} -> {fn}")

        # ③ §节号。跨 skill 引用必须写明归属(`hfss-xxx` 的 ... §N),
        #    那种形式去对方 skill 的 SKILL.md 里核;没写归属的只认本 skill。
        for m in re.finditer(r"(?:`(hfss-[a-z]+)`[^§]{0,24})?§([\d.]+)", txt):
            other, sec = m.group(1), m.group(2).rstrip(".")
            if other:
                tgt = core_sections.get(os.path.join(SKILLS, other))
                if tgt is None:
                    problems.append(f"[跨 skill 引用:skill 不存在] {rel} -> {other}")
                elif sec not in tgt:
                    problems.append(f"[跨 skill 死节号] {rel} -> {other} §{sec}")
            elif sec not in allowed:
                problems.append(f"[死节号] {rel} -> §{sec}")

        # ④ 跨文件的"第 N 步"悬空指代:这张卡里没有编号步骤,却提到"第 N 步"
        has_steps = bool(re.search(r"(?m)^\s*\d+\. ", txt))
        for m in re.findall(r"(上面|前面)?第\s*\d+\s*步", txt):
            if not has_steps:
                problems.append(f"[悬空指代] {rel} -> 提到「第 N 步」但本文件没有编号步骤")
                break

    # ⑤ 工具描述里引用的 skill 位置
    try:
        sys.path.insert(0, ROOT)
        os.environ.setdefault("HFSS_AGENT_AUTOCONFIRM", "1")
        from tools import TOOLS
        design = os.path.join(SKILLS, "hfss-design")
        core = core_sections.get(design, set())
        for name, t in TOOLS.items():
            desc = t["schema"]["function"].get("description", "")
            for sec in set(re.findall(r"§([\d.]+)", desc)):
                if sec.rstrip(".") not in core:
                    problems.append(f"[工具描述死节号] {name} -> §{sec}")
            for fn in set(re.findall(r"`((?:flow/)?[a-z][a-z0-9-]*\.md)`", desc)):
                if not os.path.exists(os.path.join(design, fn)):
                    problems.append(f"[工具描述引用不存在] {name} -> {fn}")
    except Exception as e:
        problems.append(f"[跳过工具检查] {type(e).__name__}: {e}")

    # ⑥ 斜杠命令指向的流程卡是否存在(命令在仓库 commands/,卡在 skill/hfss-design/flow/)
    cmd_dir = os.path.join(ROOT, "commands")
    design = os.path.join(SKILLS, "hfss-design")
    if os.path.isdir(cmd_dir):
        cards = set()
        for c in glob.glob(os.path.join(cmd_dir, "hfss-*.md")):
            txt = _read(c)
            found = re.findall(r"flow/([a-z][a-z0-9-]*\.md)", txt)
            if not found:
                problems.append(f"[命令没指向流程卡] {os.path.relpath(c, ROOT)}")
            for fn in found:
                cards.add(fn)
                if not os.path.exists(os.path.join(design, "flow", fn)):
                    problems.append(f"[命令指向的卡不存在] {os.path.relpath(c, ROOT)} -> flow/{fn}")
        # 反向检查:命令集是粗粒度的(只有 建模/优化 两个),一张卡没被命令直接点名很正常
        # ——细分由 SKILL.md 的路由表负责。所以这里改查**路由表有没有覆盖全部卡**。
        core_txt = _read(os.path.join(design, "SKILL.md"))
        for f in sorted(glob.glob(os.path.join(design, "flow", "*.md"))):
            fn = os.path.basename(f)
            if f"flow/{fn}" not in core_txt and fn not in "".join(
                    _read(c) for c in glob.glob(os.path.join(cmd_dir, "hfss-*.md"))):
                problems.append(f"[流程卡既不在路由表也不在命令里,没人会读到它] flow/{fn}")

    # ⑦ 命令是不是生成物的最新版 —— 命令里的分支列表来自 SKILL.md 的路由表,
    #    改了路由表却没重跑 make_commands.py,两份就对不上了。重新生成一遍比对。
    try:
        sys.path.insert(0, ROOT)
        import make_commands
        for name, want in make_commands.build().items():
            f = os.path.join(ROOT, "commands", name)
            if not os.path.exists(f):
                problems.append(f"[命令缺失] commands/{name} —— 跑 python make_commands.py")
            elif _read(f).replace("\r\n", "\n") != want.replace("\r\n", "\n"):
                problems.append(f"[命令与 SKILL.md 路由表不同步] commands/{name}"
                                f" —— 跑 python make_commands.py 重新生成")
    except SystemExit as e:
        problems.append(f"[命令生成器跑不动] {e}")
    except Exception as e:
        problems.append(f"[跳过命令同步检查] {type(e).__name__}: {e}")

    if verbose:
        if problems:
            print(f"skill 引用体检:{len(problems)} 处问题")
            for x in sorted(set(problems)):
                print("  " + x)
        else:
            print(f"skill 引用体检:通过({len(md_files)} 个 .md)")
    return sorted(set(problems))


if __name__ == "__main__":
    sys.exit(1 if check() else 0)
