#!/usr/bin/env python
"""把 native bundle 注册给 Claude Code —— 就地生成绝对路径配置。

native 版用 win32com 连接(不依赖 pyaedt),所以 env 块比 gRPC 版更精简:
只需 HFSS_VERSION(决定默认连哪个版本,可被 open_desktop 的 version 参数覆盖)+ license 变量。
ProgID 由注册表解析,不需要 ANSYSEM_ROOT 路径。

用法:
  python install.py                  # 只打印 .mcp.json 块 + claude mcp add 命令,不动文件
  python install.py --project DIR     # 把 .mcp.json / skill / settings 写进项目目录 DIR
  python install.py --skill-user      # 把全部 skill 复制到 ~/.claude/skills/(全局)

绝不改全局 ~/.claude.json;用户级 MCP 注册用打印出来的 `claude mcp add` 命令。
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
SERVER = BUNDLE / "hfss_mcp_server.py"
SKILLS_SRC = BUNDLE / "skill"      # 下面每个含 SKILL.md 的子目录 = 一个 skill,全部安装
SETTINGS_SNIPPET = BUNDLE / "settings.snippet.json"

SERVER_NAME = "hfss-agent-native"   # 固定:settings 的 ask 规则 key 在它上(mcp__hfss-agent-native__analyze)


def _derive_version(root_keys):
    """ANSYSEM_ROOT252 → '2025.2';多个取最高。无法解析返回 None。"""
    suffixes = [k[len("ANSYSEM_ROOT"):] for k in root_keys]
    suffixes = [s for s in suffixes if len(s) == 3 and s.isdigit()]
    if not suffixes:
        return None
    s = max(suffixes)
    return f"20{s[:2]}.{s[2]}"


def server_env() -> dict:
    """native 只需 HFSS_VERSION(默认版本)+ license(HFSS 进程要)。
    HFSS_VERSION 从最高的 ANSYSEM_ROOT### 推导;不带 ANSYSEM_ROOT 路径(win32com 用注册表 ProgID)。
    """
    env = {}
    root_keys = sorted(k for k in os.environ if k.startswith("ANSYSEM_ROOT"))
    ver = _derive_version(root_keys)
    if ver:
        env["HFSS_VERSION"] = ver
    for k in ("ANSYSLMD_LICENSE_FILE", "ANSYSLIC_DIR"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def mcp_entry() -> dict:
    return {"command": str(Path(sys.executable)), "args": [str(SERVER)], "env": server_env()}


def print_instructions():
    entry = mcp_entry()
    block = {"mcpServers": {SERVER_NAME: entry}}
    print("\n=== 方式 A:粘贴到项目的 .mcp.json ===\n")
    print(json.dumps(block, indent=2, ensure_ascii=False))
    print("\n=== 方式 B:claude mcp add 注册到用户级(全局)===\n")
    e_flags = " ".join(f'-e {k}="{v}"' for k, v in entry["env"].items())
    print(f'claude mcp add {SERVER_NAME} --scope user {e_flags} -- '
          f'"{entry["command"]}" "{entry["args"][0]}"')
    print("\n=== skill 安装 ===")
    print("  全局:  python install.py --skill-user")
    print("  单项目:python install.py --project <你的项目目录>")
    print(f"\n  提示:env 当前 = {dict(entry['env'])}")
    print("  跨版本:默认连 HFSS_VERSION 那个版本;要连别的(如 2019.2)在对话里让 open_desktop 传 version='2019.2',")
    print("         或把 env 里的 HFSS_VERSION 改掉。")


def _merge_json_file(path: Path, patch: dict, top_key: str, sub_key: str):
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            print(f"  [warn] {path} 解析失败,跳过合并")
            return
    data.setdefault(top_key, {})[sub_key] = patch[top_key][sub_key]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  [写] {path}")


# 种子卡:教科书参考(非个人经验),作为 starter 随安装发(目录专属)。
_SKILL_STARTERS = {"design": {"microstrip-patch.md"}}


def _skill_ignore(dirpath, names):
    """copytree 过滤:knowledge/ 和 design/ 里**按天线类型命名**的 .md 不复制——
    那是运行时积累的个人经验(如 magneto-electric-dipole.md),不随分发走,也不覆盖
    用户安装副本里已攒的。只带通用框架:SKILL.md、`_*.md`(_general/_optimization/_TEMPLATE)、INDEX.md。
    例外 = _SKILL_STARTERS 里的种子卡(教科书参考,作为 starter 发)。"""
    base = os.path.basename(dirpath).lower()
    if base == "papers":
        # papers/ 只发通用读法 _HOWTO.md;INDEX.md 是个人的原文索引、PDF 有版权,都不随分发走
        return [n for n in names if n != "_HOWTO.md"]
    if base not in ("knowledge", "design"):
        return []
    keep = _SKILL_STARTERS.get(base, set())
    return [n for n in names
            if n.lower().endswith(".md") and not n.startswith("_")
            and n.lower() != "index.md" and n.lower() not in keep]


def _copy_skill(src: Path, dest: Path):
    """复制一个 skill,遵守 _skill_ignore。**已存在的 INDEX.md 一律不覆盖**——
    它是用户随使用追加条目的活文档(卡片指针都在里面),覆盖会把攒的条目抹掉。
    返回因此被跳过、且内容与 bundle 不同的文件列表,供调用方提示用户手工合并。"""
    kept = []
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        ignored = set(_skill_ignore(root, files + dirs))
        dirs[:] = [d for d in dirs if d not in ignored]
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for fn in files:
            if fn in ignored:
                continue
            s_path, d_path = Path(root) / fn, dest / rel / fn
            if fn.lower() == "index.md" and d_path.exists():
                if d_path.read_bytes() != s_path.read_bytes():
                    kept.append(d_path)
                continue
            shutil.copy2(s_path, d_path)
    return kept


def install_skill(dest_skills_dir: Path):
    """安装 skill/ 下的**每一个** skill(判据:目录里有 SKILL.md)。"""
    srcs = sorted(d for d in SKILLS_SRC.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())
    if not srcs:
        print(f"  [警告] {SKILLS_SRC} 下没找到 skill(子目录需含 SKILL.md),跳过")
        return
    kept = []
    for src in srcs:
        dest = dest_skills_dir / src.name
        kept += _copy_skill(src, dest)
        print(f"  [写] {dest}")
    print("        (仅通用框架;knowledge/design 里按天线类型的卡片不复制,保留安装副本已有的)")
    for k in kept:
        print(f"  [跳过] {k} 已存在且与 bundle 不同——保留你的版本,如需 bundle 的改动请手工合并")


def install_project(project_dir: str):
    proj = Path(project_dir).resolve()
    if not proj.is_dir():
        sys.exit(f"项目目录不存在: {proj}")
    print(f"写入项目 {proj}:")
    _merge_json_file(proj / ".mcp.json", {"mcpServers": {SERVER_NAME: mcp_entry()}}, "mcpServers", SERVER_NAME)
    install_skill(proj / ".claude" / "skills")
    snippet = json.loads(SETTINGS_SNIPPET.read_text(encoding="utf-8"))
    _merge_json_file(proj / ".claude" / "settings.json", snippet, "permissions", "ask")
    print("\n完成。重启 Claude Code,/mcp 应看到 hfss-agent-native。")


def install_skill_user():
    home_skills = Path.home() / ".claude" / "skills"
    print(f"安装 skill 到用户级 {home_skills}:")
    install_skill(home_skills)
    print("\n完成。MCP server 仍需用下面的 `claude mcp add` 命令注册(本脚本不动全局配置)。\n")
    print_instructions()


def main():
    ap = argparse.ArgumentParser(description="注册 HFSS native MCP bundle 给 Claude Code")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--project", metavar="DIR", help="把 .mcp.json/skill/settings 写进项目目录")
    g.add_argument("--skill-user", action="store_true", help="把全部 skill 复制到 ~/.claude/skills/")
    args = ap.parse_args()
    if not SERVER.exists():
        sys.exit(f"找不到 {SERVER} —— install.py 必须和 hfss_mcp_server.py 同目录")
    if args.project:
        install_project(args.project)
    elif args.skill_user:
        install_skill_user()
    else:
        print_instructions()


if __name__ == "__main__":
    main()
