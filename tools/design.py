"""设计卡片检索(辅助设计 Layer 2)—— 只读扫 skill 的 design/*.md,按条件过滤。

纯查表:不碰 COM/HFSS,不含设计推理(缩放/建模/对标留给 skill+Claude)。
卡片单一真相 = design/<type>.md 的 YAML-ish frontmatter;本工具只解析+过滤,不另存库。
卡片位置解析顺序:HFSS_DESIGN_DIR 环境变量 → 安装副本(~/.claude/...) → bundle 副本。
"""

import os

from . import tool

_SKIP = {"_template.md", "index.md"}


def _design_dir():
    """返回第一个存在的卡片目录(优先 env,其次安装副本,最后 bundle 内)。"""
    cands = []
    env = os.environ.get("HFSS_DESIGN_DIR")
    if env:
        cands.append(os.path.abspath(env))
    cands.append(os.path.expanduser("~/.claude/skills/hfss-antenna-modeling/design"))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(os.path.dirname(here), "skill", "hfss-antenna-modeling", "design"))
    for d in cands:
        if d and os.path.isdir(d):
            return d, cands
    return None, cands


def _scalar(s):
    """'2.4'→2.4、'-11.7'→-11.7、'any'→'any'(保留字符串)。"""
    s = s.strip()
    try:
        f = float(s)
        return int(f) if f == int(f) and "." not in s and "e" not in s.lower() else f
    except ValueError:
        return s


def _parse_frontmatter(text):
    """解析卡片顶部 ---...--- 之间的扁平 frontmatter(scalar 或 [a, b])。无 dep。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ":" not in ln:
            continue
        k, _, v = ln.partition(":")
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if v.startswith("[") and v.endswith("]"):
            items = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            fm[k] = [_scalar(x) for x in items]
        else:
            fm[k] = _scalar(v)
    return fm


def _load_cards(d):
    cards = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md") or fn.lower() in _SKIP:
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        fm = _parse_frontmatter(text)
        cards.append({"card": fn[:-3], "file": fn, "path": path, "fm": fm})
    return cards


def _as_list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


@tool({"type": "function", "function": {
    "name": "list_design_cards",
    "description": "列出设计卡片库里所有卡(辅助设计用)。返回每张卡的拓扑/频段/基板/馈电/极化/报告性能摘要 + 文件路径(用 Read 看公式细节)。",
    "parameters": {"type": "object", "properties": {}}}})
def list_design_cards(ctx):
    d, cands = _design_dir()
    if not d:
        return {"ok": False, "error": "找不到设计卡片目录", "searched": cands}
    cards = _load_cards(d)
    return {"ok": True, "dir": d, "n_cards": len(cards),
            "cards": [{"card": c["card"], "path": c["path"],
                       "topology": c["fm"].get("topology", c["card"]),
                       "freq_ghz": [c["fm"].get("freq_ghz_min"), c["fm"].get("freq_ghz_max")],
                       "eps_r": c["fm"].get("eps_r"), "polarization": c["fm"].get("polarization"),
                       "feed": _as_list(c["fm"].get("feed")), "source": c["fm"].get("source")}
                      for c in cards]}


@tool({"type": "function", "function": {
    "name": "search_designs",
    "description": ("按需求检索设计卡片(辅助设计起手)。给频率/极化/拓扑/增益等条件,返回匹配的卡及其报告性能、"
                    "λ归一化尺寸/公式所在文件路径(用 Read 看细节,再按目标频率缩放起手建模)。"
                    "不传任何条件=返回全部。缺对应元数据的卡不因该条件被排除(从宽,标注 unknown)。"),
    "parameters": {"type": "object", "properties": {
        "frequency_ghz": {"type": "number", "description": "目标工作频率(GHz),匹配频段覆盖它的卡"},
        "polarization": {"type": "string", "description": "极化,如 'linear'/'cp'(不区分大小写,子串匹配)"},
        "topology": {"type": "string", "description": "拓扑关键词,如 'patch'/'贴片'/'dipole'(匹配拓扑名/别名/文件名)"},
        "min_gain_dbi": {"type": "number", "description": "最低峰值增益要求(dBi),卡能达到的上限须 ≥ 它"},
        "eps_r": {"type": "number", "description": "基板介电常数(可选,'any' 的卡始终匹配)"}}}}})
def search_designs(ctx, frequency_ghz=None, polarization=None, topology=None, min_gain_dbi=None, eps_r=None):
    d, cands = _design_dir()
    if not d:
        return {"ok": False, "error": "找不到设计卡片目录", "searched": cands}
    cards = _load_cards(d)
    out = []
    for c in cards:
        fm = c["fm"]
        why, ok = [], True

        if frequency_ghz is not None:
            lo, hi = fm.get("freq_ghz_min"), fm.get("freq_ghz_max")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                if lo <= frequency_ghz <= hi:
                    why.append(f"频率 {frequency_ghz}GHz 在 [{lo},{hi}] 内")
                else:
                    ok = False
            else:
                why.append("频段未标注(未排除)")

        if polarization is not None:
            cp = fm.get("polarization")
            if cp is not None:
                if polarization.lower() in str(cp).lower():
                    why.append(f"极化匹配 {cp}")
                else:
                    ok = False
            else:
                why.append("极化未标注(未排除)")

        if topology is not None:
            hay = " ".join(str(x) for x in [fm.get("topology", ""), c["card"]] + _as_list(fm.get("aliases"))).lower()
            if topology.lower() in hay:
                why.append(f"拓扑命中 '{topology}'")
            else:
                ok = False

        if min_gain_dbi is not None:
            gmax = fm.get("gain_dbi_max", fm.get("gain_dbi_min"))
            if isinstance(gmax, (int, float)):
                if gmax >= min_gain_dbi:
                    why.append(f"增益可达 {gmax}dBi ≥ {min_gain_dbi}")
                else:
                    ok = False
            else:
                why.append("增益未标注(未排除)")

        if eps_r is not None:
            er = fm.get("eps_r")
            if er == "any":
                why.append("εr 任意(闭式公式)")
            elif isinstance(er, (int, float)):
                why.append(f"εr={er}" + ("(匹配)" if abs(er - eps_r) < 0.3 else f"(参考,目标 {eps_r})"))

        if not ok:
            continue
        out.append({
            "card": c["card"], "path": c["path"],
            "topology": fm.get("topology", c["card"]),
            "freq_ghz": [fm.get("freq_ghz_min"), fm.get("freq_ghz_max")],
            "eps_r": fm.get("eps_r"), "feed": _as_list(fm.get("feed")),
            "polarization": fm.get("polarization"),
            "performance": {"s11_db": fm.get("s11_db"),
                            "bw_pct": [fm.get("bw_pct_min"), fm.get("bw_pct_max")],
                            "gain_dbi": [fm.get("gain_dbi_min"), fm.get("gain_dbi_max")]},
            "source": fm.get("source"), "matched": why})
    return {"ok": True, "dir": d, "n_matches": len(out), "matches": out,
            "hint": "用 Read 打开匹配卡的 path 看闭式公式/归一化尺寸,按 frequency_ghz 缩放算起手,再建模仿真对标 performance。"}
