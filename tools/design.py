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
    "description": "列出设计卡片库里所有卡(辅助设计用)。返回每张卡的拓扑/频段/基板/馈电/极化/报告性能摘要 + 卡片名(用 read_design_card 看公式细节)。",
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
    "name": "read_design_card",
    "description": ("读一张设计卡片的完整正文(闭式公式 / λ 归一化尺寸 / 设计自由度 / 出处)。"
                    "search_designs / list_design_cards 命中后用它拿细节,再按目标频率缩放算起手尺寸。"
                    "**卡片内容通过本工具返回,不需要客户端自带文件读取能力。**"),
    "parameters": {"type": "object", "properties": {
        "card": {"type": "string", "description": "卡片名(不含 .md),取自 search_designs/list_design_cards 返回的 card 字段"},
        "max_chars": {"type": "integer", "default": 20000,
                      "description": "最多返回多少字符,默认 20000;超长会截断并标注 truncated"}},
        "required": ["card"]}}})
def read_design_card(ctx, card, max_chars=20000):
    d, cands = _design_dir()
    if not d:
        return {"ok": False, "error": "找不到设计卡片目录", "searched": cands}
    # 只认卡片库里已登记的卡名,不接受路径——避免把任意文件读出去
    cards = {c["card"]: c for c in _load_cards(d)}
    hit = cards.get(str(card).strip()) or cards.get(str(card).strip().removesuffix(".md"))
    if hit is None:
        return {"ok": False, "error": f"没有名为 '{card}' 的设计卡",
                "available": sorted(cards.keys())}
    try:
        with open(hit["path"], "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return {"ok": False, "error": f"读卡片失败: {type(e).__name__}: {e}"}
    n = int(max_chars)
    truncated = len(text) > n
    return {"ok": True, "card": hit["card"], "path": hit["path"], "fm": hit["fm"],
            "n_chars": len(text), "truncated": truncated,
            "content": text[:n] + ("  …(已截断,调大 max_chars 看全文)" if truncated else "")}


@tool({"type": "function", "function": {
    "name": "search_designs",
    "description": ("按需求检索设计卡片(辅助设计起手)。给频率/极化/拓扑/增益等条件,返回匹配的卡及其报告性能、"
                    "λ归一化尺寸/公式所在卡片名(用 read_design_card 取正文,再按目标频率缩放起手建模)。"
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
            "hint": "用 read_design_card(card=...) 取闭式公式/归一化尺寸,按 frequency_ghz 缩放算起手,再建模仿真对标 performance。"}


# ────────────────────────── 对标门(Layer 3 闭环的终止判定)──────────────────────────

# 每个指标的默认比较方向 + 单位提示(目标只给数值时用)。
_TARGET_OP = {
    "resonant_freq_ghz": "~=", "center_freq_ghz": "~=", "freq_ghz": "~=",
    "s11_db": "<=", "vswr": "<=", "axial_ratio_db": "<=", "cross_pol_db": "<=",
    "peak_gain_dbi": ">=", "broadside_gain_dbi": ">=", "bw_pct": ">=", "bw_mhz": ">=",
    "bw_ghz": ">=", "front_to_back_db": ">=", "hpbw_deg": ">=", "isolation_db": ">=",
}
_DEFAULT_TOL_PCT = 2.0   # "~=" 默认容差(目标的百分比)


def _check_one(metric, meas, spec):
    """spec 是标量(用默认 op)或 {op, value, tol/tol_pct}。返回判定 dict。"""
    if isinstance(spec, dict):
        op = spec.get("op") or _TARGET_OP.get(metric, "<=")
        val = spec.get("value")
        tol_abs = spec.get("tol")
        tol_pct = spec.get("tol_pct")
    else:
        op, val, tol_abs, tol_pct = _TARGET_OP.get(metric, "<="), spec, None, None
    r = {"metric": metric, "measured": meas, "op": op, "target": val}
    if meas is None or val is None:
        r["pass"] = None
        r["note"] = "缺测量值或目标值,未判定"
        return r
    if op in ("~=", "within"):
        tol = tol_abs if tol_abs is not None else abs(val) * (tol_pct if tol_pct is not None else _DEFAULT_TOL_PCT) / 100.0
        dev = meas - val
        r.update({"deviation": round(dev, 4), "tol": round(tol, 4), "pass": abs(dev) <= tol})
        if val:
            r["deviation_pct"] = round(dev / val * 100, 2)
    else:
        dev = meas - val
        r["deviation"] = round(dev, 4)
        r["pass"] = {"<=": meas <= val, "<": meas < val, ">=": meas >= val,
                     ">": meas > val, "==": meas == val}.get(op, None)
    return r


@tool({"type": "function", "function": {
    "name": "check_design_targets",
    "description": ("对标门:把实测指标和目标规格逐项比,给结构化通过/偏差判定(辅助设计闭环的终止条件,也是不达标"
                    "时该调哪项的依据)。measured/targets 都是 {指标名: 值} —— 自己从 get_s_parameters / "
                    "get_radiation_pattern 取数填 measured。目标给标量用默认方向(频率~=、s11/vswr/AR<=、"
                    "增益/带宽/前后比>=);要自定义方向/容差就给 {op, value, tol 或 tol_pct}。"
                    "常用指标名:resonant_freq_ghz, s11_db, vswr, bw_pct, bw_mhz, peak_gain_dbi, "
                    "axial_ratio_db, front_to_back_db, hpbw_deg, isolation_db。"),
    "parameters": {"type": "object", "properties": {
        "measured": {"type": "object", "description": "实测指标 {名: 数值},如 {'resonant_freq_ghz':2.46,'s11_db':-11.7,'bw_pct':3.5}"},
        "targets": {"type": "object", "description": "目标规格 {名: 数值 或 {op,value,tol/tol_pct}},如 {'resonant_freq_ghz':2.45,'s11_db':-10,'bw_pct':3}"}},
        "required": ["measured", "targets"]}}})
def check_design_targets(ctx, measured, targets):
    checks = [_check_one(m, measured.get(m), spec) for m, spec in targets.items()]
    decided = [c for c in checks if c["pass"] is not None]
    failed = [c["metric"] for c in checks if c["pass"] is False]
    undecided = [c["metric"] for c in checks if c["pass"] is None]
    all_pass = bool(decided) and not failed
    return {"ok": True, "all_pass": all_pass,
            "n_pass": sum(1 for c in decided if c["pass"]), "n_fail": len(failed),
            "failed_metrics": failed, "undecided_metrics": undecided, "checks": checks,
            "hint": ("全部达标。" if all_pass else
                     f"未达标:{failed}。查设计卡'起手→调匹配'看哪个自由度控这些指标,"
                     "用 create_parametric_sweep 扫它再 check 一遍。")}

