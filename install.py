#!/usr/bin/env python
"""把 native bundle 注册给 Claude Code —— 就地生成绝对路径配置。

native 版用 win32com 连接(不依赖 pyaedt),所以 env 块比 gRPC 版更精简:
只需 HFSS_VERSION(决定默认连哪个版本,可被 open_desktop 的 version 参数覆盖)+ license 变量。
ProgID 由注册表解析,不需要 ANSYSEM_ROOT 路径。

用法:
  python install.py                  # 只打印 .mcp.json 块 + claude mcp add 命令,不动文件
  python install.py --project DIR     # 把 .mcp.json / skill / settings 写进项目目录 DIR
  python install.py --skill-user      # 把 skill 复制到 ~/.claude/skills/(全局)

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
SKILL_SRC = BUNDLE / "skill" / "hfss-antenna-modeling"
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


def _skill_ignore(dirpath, names):
    """copytree 过滤:knowledge/ 和 design/ 里**按天线类型命名**的 .md 不复制——
    那是运行时积累的个人经验(如 magneto-electric-dipole.md),不随分发走,也不覆盖
    用户安装副本里已攒的。只带通用框架:SKILL.md、`_*.md`(_general/_optimization/_TEMPLATE)、INDEX.md。"""
    if os.path.basename(dirpath).lower() not in ("knowledge", "design"):
        return []
    return [n for n in names
            if n.lower().endswith(".md") and not n.startswith("_") and n.lower() != "index.md"]


def install_skill(dest_skills_dir: Path):
    dest = dest_skills_dir / SKILL_SRC.name
    shutil.copytree(SKILL_SRC, dest, dirs_exist_ok=True, ignore=_skill_ignore)
    print(f"  [写] {dest}(仅通用框架;按天线类型的 knowledge/design 卡片不复制,保留安装副本已有的)")


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
    g.add_argument("--skill-user", action="store_true", help="把 skill 复制到 ~/.claude/skills/")
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
