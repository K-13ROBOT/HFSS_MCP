"""建模历史参数(native COM 版)—— 改**已有对象**的创建/操作参数,不新建对象。

走对象模型:oEditor.GetChildObject(对象).GetChildObject(操作)... .SetPropValue(属性, 值)。
历史树形如(2025.2 实测):
  Feed/CreatePolyline:1/Segment0        Point1/X、Point1/Y、Point2/X ...(相邻段共用的点改一处两边都变)
  Sheet/Subtract:1/OperandPart_HoleC/HoleC:CreateCircle:1   Center Position/X、Radius ...(布尔里被消耗的工具对象)
2019.2 没有这套对象模型(oEditor 上没有 GetChildObject/GetChildNames,实测):只能用老接口
   ChangeProperty(Geometry3DCmdTab, "HoleC:CreateCircle:1") 改单个操作的参数(复合参数要整体给 X/Y/Z),
   列不出历史树、也够不着多边形的点 —— get_object_history / replace_in_history 在 2019.2 上直接报不支持。
⚠️ 多边形的点用 ChangeProperty(Geometry3DCmdTab, "Feed:CreatePolyline:1:Segment0")会报"发生意外",
   SetPropValue 才行;复合属性(如 'Center Position')要按分量 '/X' '/Y' '/Z' 改,整体传列表返回 True 但不生效。
"""

import time

from . import tool

# 历史节点上不该当"参数"看/改的属性
_SKIP_PROPS = {"Command", "Coordinate System", "Suppress Command", "Number of points", "Number of curves"}


def _node(oEditor, path):
    parts = [p for p in str(path).split("/") if p]
    if not parts:
        raise ValueError("path 为空")
    o = oEditor.GetChildObject(parts[0])
    for p in parts[1:]:
        o = o.GetChildObject(p)
    return o


def _kids(o):
    try:
        return [str(k) for k in (o.GetChildNames() or [])]
    except Exception:
        return []


def _leaf_props(o):
    """可改的叶子属性 {名: 值}。复合点('Point1' = "('X:=', ...)")只保留它的 /X /Y /Z 分量。"""
    try:
        names = [str(n) for n in (o.GetPropNames() or [])]
    except Exception:
        return {}
    out = {}
    for n in names:
        if n in _SKIP_PROPS or n.endswith("/Choices"):
            continue
        try:
            v = str(o.GetPropValue(n))
        except Exception:
            continue
        if v.startswith("('X:="):     # 复合点,分量单独列着
            continue
        out[n] = v
    return out


def _walk(oEditor, root):
    """深度优先列出 root 对象下的全部历史操作节点:[(path, node), ...](不含对象节点本身)。"""
    out = []

    def rec(path, o):
        for k in _kids(o):
            p = f"{path}/{k}"
            try:
                c = o.GetChildObject(k)
            except Exception:
                continue
            out.append((p, c))
            rec(p, c)
    rec(root, oEditor.GetChildObject(root))
    return out


def _polyline_points(op):
    """CreatePolyline 节点 → 去重后的点列表 [[x,y,z],...](相邻段共用的点只列一次)。"""
    pts = []
    for s in _kids(op):
        if not s.startswith("Segment"):
            continue
        seg = op.GetChildObject(s)
        for p in (("Point1", "Point2") if not pts else ("Point2",)):
            try:
                pts.append([str(seg.GetPropValue(f"{p}/{a}")) for a in ("X", "Y", "Z")])
            except Exception:
                pass
    return pts


def _has_object_model(oEditor):
    try:
        oEditor.GetChildNames()
        return True
    except AttributeError:
        return False
    except Exception:
        return True


_NO_OM = {"ok": False,
          "error": "这个 AEDT 版本没有建模对象模型(oEditor.GetChildObject 不存在,2019.2 实测),列不出历史树、改不了多边形的点",
          "hint": ("单个操作的参数仍可用 set_history_props 改:path 写成 '对象:命令:序号'(如 'HoleC:CreateCircle:1'),"
                   "复合参数整体给 [x, y, z]")}


def _objects(oEditor):
    try:
        return [str(n) for n in (oEditor.GetChildNames() or [])]
    except Exception:
        return []


@tool({
    "type": "function",
    "function": {
        "name": "get_object_history",
        "description": (
            "看**已有对象**的建模历史:每一步操作(CreatePolyline / CreateCircle / Subtract …)的路径和可改参数。"
            "布尔操作里被消耗掉的工具对象(如 subtract 掉的圆)也在里面,路径形如 "
            "'Sheet/Subtract:1/OperandPart_HoleC/HoleC:CreateCircle:1'。"
            "多边形不逐段列,直接给去重后的点表(points)。拿到路径后用 set_history_props 改单项,"
            "或用 replace_in_history 把某个值(如 '-1.8mm')批量换成表达式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "对象名"},
                "max_points": {"type": "integer", "default": 50,
                               "description": "多边形点表最多列多少个(超出只给总数),默认 50"},
            },
            "required": ["name"],
        },
    },
})
def get_object_history(ctx, name, max_points=50):
    oEditor = ctx["oEditor"]
    if not _has_object_model(oEditor):
        return dict(_NO_OM)
    if name not in _objects(oEditor):
        return {"ok": False, "error": f"没有对象 '{name}'", "hint": "list_objects 核对实际名字"}
    ops = []
    for path, node in _walk(oEditor, name):
        leaf = path.rsplit("/", 1)[-1]
        if leaf.startswith("Segment"):          # 段并进它的 CreatePolyline
            continue
        try:
            cmd = str(node.GetPropValue("Command"))
        except Exception:
            cmd = None
        if cmd is None:                         # OperandPart_* 这种分组节点,没有自身参数
            continue
        entry = {"path": path, "command": cmd}
        if cmd == "CreatePolyline":
            pts = _polyline_points(node)
            entry["n_points"] = len(pts)
            entry["points"] = pts[:max_points]
            if len(pts) > max_points:
                entry["points_truncated"] = True
            props = {k: v for k, v in _leaf_props(node).items()}
        else:
            props = _leaf_props(node)
        if props:
            entry["props"] = props
        ops.append(entry)
    return {"ok": True, "name": name, "operations": ops}


def _set_props_legacy(oEditor, path, props):
    """老接口(2019.2):ChangeProperty 到 '对象:命令:序号' 这个 PropServer。不能按分量改。"""
    server = str(path).rsplit("/", 1)[-1]
    try:
        names = {str(n) for n in (oEditor.GetProperties("Geometry3DCmdTab", server) or [])}
    except Exception as e:
        return {"ok": False, "error": f"找不到历史操作 '{server}': {type(e).__name__}: {e}",
                "hint": "这个版本列不出历史树;path 写成 '对象:命令:序号',如 'HoleC:CreateCircle:1'、'Sheet:CreateRectangle:1'"}
    changed, failed = {}, {}
    for k, v in (props or {}).items():
        if "/" in k:
            failed[k] = "这个版本不能按分量改,请整体给 [x, y, z](如 'Center Position': ['0mm', '1mm', 'h'])"
            continue
        if k not in names:
            failed[k] = "没有这个属性"
            continue
        if isinstance(v, (list, tuple)):
            if len(v) != 3:
                failed[k] = "复合参数要给 [x, y, z]"
                continue
            prop = [f"NAME:{k}", "X:=", str(v[0]), "Y:=", str(v[1]), "Z:=", str(v[2])]
        else:
            prop = [f"NAME:{k}", "Value:=", str(v)]
        try:
            oEditor.ChangeProperty(["NAME:AllTabs", ["NAME:Geometry3DCmdTab",
                                    ["NAME:PropServers", server], ["NAME:ChangedProps", prop]]])
            changed[k] = str(oEditor.GetPropertyValue("Geometry3DCmdTab", server, k))
        except Exception as e:
            failed[k] = f"{type(e).__name__}: {e}"
    out = {"ok": not failed, "path": server, "changed": changed,
           "note": "老接口:复合参数读回来不带单位(如 '0.2 ,0.3 ,1'),以 get_object_bbox 核对几何为准"}
    if failed:
        out["failed"] = failed
        out["available_props"] = sorted(names)
    return out


@tool({
    "type": "function",
    "function": {
        "name": "set_history_props",
        "description": (
            "改**已有对象**某一步历史操作的参数(不新建对象)。path 用 get_object_history 返回的;"
            "props 是 {属性: 值},值可以是字面量或表达式/变量名(改成变量名之后会跟着变量联动)。"
            "复合属性按分量写:'Center Position/X'、'Position/Y';也可以整体给 'Center Position': [x, y, z],工具会拆开。"
            "多边形的点:path 写到段,如 'Feed/CreatePolyline:1/Segment3',属性 'Point1/X'"
            "(相邻段共用的点改一处,两段都变)。改完几何立即重建,已有的解会作废。"
            "老版本(2019.2)没有对象模型:path 写成 '对象:命令:序号'(如 'HoleC:CreateCircle:1'),"
            "只能改单个操作的参数、复合参数整体给,改不了多边形的点。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "历史节点路径,如 'Sheet/Subtract:1/OperandPart_HoleC/HoleC:CreateCircle:1'"},
                "props": {"type": "object", "description": "如 {'Radius': 'r_hole', 'Center Position': ['cx', '0mm', 'h']}"},
            },
            "required": ["path", "props"],
        },
    },
})
def set_history_props(ctx, path, props):
    oEditor = ctx["oEditor"]
    if not _has_object_model(oEditor):
        return _set_props_legacy(oEditor, path, props)
    try:
        node = _node(oEditor, path)
        names = {str(n) for n in (node.GetPropNames() or [])}
    except Exception as e:
        return {"ok": False, "error": f"找不到历史节点 '{path}': {type(e).__name__}: {e}",
                "hint": "路径用 get_object_history 返回的原样字符串"}
    flat = {}
    for k, v in (props or {}).items():
        if isinstance(v, (list, tuple)):
            if len(v) != 3:
                return {"ok": False, "error": f"'{k}' 给的是列表,但不是 [x, y, z]"}
            for a, x in zip(("X", "Y", "Z"), v):
                flat[f"{k}/{a}"] = str(x)
        else:
            flat[k] = str(v)
    changed, failed = {}, {}
    for k, v in flat.items():
        if k not in names:
            failed[k] = "没有这个属性"
            continue
        try:
            ok = node.SetPropValue(k, v)
            now = str(node.GetPropValue(k))
        except Exception as e:
            failed[k] = f"{type(e).__name__}: {e}"
            continue
        if ok is False or now != v:
            failed[k] = f"没生效(现值 {now})"
        else:
            changed[k] = now
    out = {"ok": not failed, "path": path, "changed": changed}
    if failed:
        out["failed"] = failed
        out["available_props"] = sorted(n for n in names if not n.endswith("/Choices"))
    return out


@tool({
    "type": "function",
    "function": {
        "name": "replace_in_history",
        "description": (
            "在已有对象的历史参数里**批量替换值**(不新建对象):把所有等于 find 的参数换成 replace。"
            "典型:馈线多边形里约 200 个点的锚点 '-1.8mm' → 'x_anchor';或把多个对象里写死的同一个尺寸换成变量。"
            "覆盖多边形的每个点分量、布尔里被消耗的工具对象的参数。"
            "默认整值精确匹配('-1.8mm' 不会命中 '-1.8mm+w');match='substring' 做子串替换(当心误伤)。"
            "先 dry_run=true 看会改哪些。每改一个点几何重建一次,200 个点约 20 秒;已有的解会作废。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "find": {"type": "string", "description": "要找的值,原样写,如 '-1.8mm'"},
                "replace": {"type": "string", "description": "换成的值/表达式,如 'x_anchor' 或 '-(Lf+0.2mm)'"},
                "objects": {"type": "array", "items": {"type": "string"},
                            "description": "只在这些对象的历史里找;不传 = 全部对象"},
                "prop_filter": {"type": "string",
                                "description": "只改属性名里含这个子串的,如 '/X' 只改 X 分量、'Radius' 只改半径"},
                "match": {"type": "string", "enum": ["exact", "substring"], "default": "exact"},
                "dry_run": {"type": "boolean", "default": False, "description": "true = 只列出会改哪些,不动"},
            },
            "required": ["find", "replace"],
        },
    },
})
def replace_in_history(ctx, find, replace, objects=None, prop_filter=None, match="exact", dry_run=False):
    oEditor = ctx["oEditor"]
    if not _has_object_model(oEditor):
        return dict(_NO_OM)
    allobj = _objects(oEditor)
    if objects:
        missing = [o for o in objects if o not in allobj]
        if missing:
            return {"ok": False, "error": f"没有这些对象: {missing}", "hint": "list_objects 核对实际名字"}
    targets = objects or allobj
    find, replace = str(find), str(replace)

    def hit(v):
        return v == find if match == "exact" else (find in v)

    def new_value(v):
        return replace if match == "exact" else v.replace(find, replace)

    t0 = time.time()
    plan = []          # [(path, node, prop)]
    for obj in targets:
        for path, node in _walk(oEditor, obj):
            for k, v in _leaf_props(node).items():
                if prop_filter and prop_filter not in k:
                    continue
                if hit(v):
                    plan.append((path, node, k))
    if dry_run:
        return {"ok": True, "dry_run": True, "matches": len(plan),
                "sample": [f"{p} :: {k}" for p, _, k in plan[:30]],
                "note": "多边形相邻段共用的点会出现两次,实际只改一次" if plan else "没有匹配"}
    changed, skipped, failed = [], 0, []
    for path, node, k in plan:
        try:
            cur = str(node.GetPropValue(k))
            if not hit(cur):          # 共用点已经随另一段改掉了
                skipped += 1
                continue
            target = new_value(cur)
            node.SetPropValue(k, target)
            now = str(node.GetPropValue(k))
            if now == target:
                changed.append(f"{path} :: {k}")
            else:
                failed.append(f"{path} :: {k}(现值 {now})")
        except Exception as e:
            failed.append(f"{path} :: {k}({type(e).__name__}: {e})")
    out = {"ok": not failed, "find": find, "replace": replace, "changed": len(changed),
           "elapsed_sec": round(time.time() - t0, 1), "sample": changed[:20]}
    if skipped:
        out["shared_points_followed"] = skipped
    if failed:
        out["failed"] = failed[:30]
        out["n_failed"] = len(failed)
    if not plan:
        out["note"] = "没有匹配。值要和 get_object_history 里显示的原样一致(含单位)"
    return out
