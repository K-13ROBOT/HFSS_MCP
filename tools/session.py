"""会话/连接(native COM 版)—— win32com 裸调 AEDT,跨版本。

连接路径(对照 PyAEDT 非 gRPC 后端,实测 2019.2 / 2025.2 均通):
    app = win32com.client.Dispatch("Ansoft.ElectronicsDesktop." + version)
    oDesktop = app.GetAppDesktop()
之后 oDesktop.NewProject / oProject.InsertDesign / oDesign.SetActiveEditor("3D Modeler")。
"""

import os

import win32com.client as _wc

from . import tool

# 版本:优先 HFSS_VERSION 环境变量(install 注入),否则 2025.2。ProgID 用 version[:6]。
_DEFAULT_VERSION = os.environ.get("HFSS_VERSION") or "2025.2"

# .aedt 存到运行目录(cwd)下的 projects/,可用 HFSS_PROJECTS_DIR 覆盖
_env_projects = os.environ.get("HFSS_PROJECTS_DIR")
PROJECTS_DIR = os.path.abspath(_env_projects) if _env_projects else os.path.abspath(os.path.join(os.getcwd(), "projects"))
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Modal/Terminal... → AEDT 原生 InsertDesign 的求解类型字符串
_SOLUTION_MAP = {
    "Modal": "DrivenModal",
    "Terminal": "DrivenTerminal",
    "Eigenmode": "Eigenmode",
    "Transient": "Transient Network",
}


def _progid(version):
    return "Ansoft.ElectronicsDesktop." + str(version)[0:6]


def _clear(ctx):
    for k in ("app", "oDesktop", "oProject", "oDesign", "oEditor"):
        ctx[k] = None
    ctx["project_name"] = None
    ctx["design_name"] = None


def _alive(ctx):
    od = ctx.get("oDesktop")
    if od is None:
        return False
    try:
        _ = od.GetVersion()
        return True
    except Exception:
        return False


@tool({
    "type": "function",
    "function": {
        "name": "open_desktop",
        "description": ("启动 HFSS 桌面(win32com 连接,跨版本)。用户说'打开/启动 HFSS'时调用。"
                        "调用后再 new_project / new_design 才能建模。version 默认取 HFSS_VERSION 环境变量。"),
        "parameters": {
            "type": "object",
            "properties": {
                "version": {"type": "string", "description": f"HFSS 版本,如 '2019.2'、'2025.2',默认 {_DEFAULT_VERSION}"},
            },
        },
    },
})
def open_desktop(ctx, version=None):
    if _alive(ctx):
        return {"ok": False, "error": "desktop 已打开且存活,如需重启先 close_desktop"}
    version = version or _DEFAULT_VERSION
    try:
        app = _wc.Dispatch(_progid(version))
        oDesktop = app.GetAppDesktop()
    except Exception as e:
        return {"ok": False, "error": f"连接 AEDT {version} 失败: {type(e).__name__}: {e}",
                "hint": f"确认已装 {version} 且 COM ProgID '{_progid(version)}' 已注册"}
    _clear(ctx)
    ctx["app"] = app
    ctx["oDesktop"] = oDesktop
    ctx["version"] = version
    try:
        real_ver = oDesktop.GetVersion()
    except Exception:
        real_ver = version
    return {"ok": True, "version": version, "aedt_version": real_ver}


@tool({
    "type": "function",
    "function": {
        "name": "attach_desktop",
        "description": "连接正在运行的 HFSS 桌面(不新启动)。用户说'连接已有 HFSS'时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "version": {"type": "string", "description": f"HFSS 版本,默认 {_DEFAULT_VERSION}"},
            },
        },
    },
})
def attach_desktop(ctx, version=None):
    if _alive(ctx):
        return {"ok": False, "error": "desktop 已连接且存活"}
    version = version or _DEFAULT_VERSION
    try:
        app = _wc.GetActiveObject(_progid(version))
        oDesktop = app.GetAppDesktop()
    except Exception as e:
        return {"ok": False, "error": f"连接运行中的 AEDT {version} 失败: {type(e).__name__}: {e}",
                "hint": "确认 HFSS 已在运行;否则用 open_desktop 新启动"}
    _clear(ctx)
    ctx["app"] = app
    ctx["oDesktop"] = oDesktop
    ctx["version"] = version
    projs = []
    try:
        projs = list(oDesktop.GetProjectList() or [])
    except Exception:
        pass
    return {"ok": True, "version": version, "projects_open": projs}


@tool({
    "type": "function",
    "function": {
        "name": "new_project",
        "description": "在当前 desktop 新建空白工程并保存到 projects 目录。调用前 desktop 必须已打开。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "工程名,如 'patch_2_4g'"}},
            "required": ["name"],
        },
    },
})
def new_project(ctx, name):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "未打开 desktop,先 open_desktop"}
    try:
        oProject = oDesktop.NewProject()
        path = os.path.join(PROJECTS_DIR, f"{name}.aedt")
        oProject.SaveAs(path, True)
    except Exception as e:
        return {"ok": False, "error": f"新建/保存工程失败: {type(e).__name__}: {e}"}
    ctx["oProject"] = oProject
    ctx["project_name"] = name
    ctx["oDesign"] = None
    ctx["oEditor"] = None
    ctx["design_name"] = None
    if "state" in ctx:
        ctx["state"].project = name
    return {"ok": True, "project": name, "path": path}


@tool({
    "type": "function",
    "function": {
        "name": "open_project",
        "description": ("从磁盘路径打开已有 .aedt 工程(desktop 须先 open_desktop/attach_desktop)。"
                        "打开后:只有一个 design 时自动激活它;多个则列出 designs 待 activate_design。"
                        "工程已在打开列表里则直接激活、不重复打开。"),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": r"完整 .aedt 路径,如 'D:\work\patch.aedt'"},
                "activate_design": {"type": "string",
                                    "description": "(可选)打开后要激活的 design 名;不传且工程内仅一个 design 时自动激活"},
            },
            "required": ["path"],
        },
    },
})
def open_project(ctx, path, activate_design=None):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "未打开 desktop,先 open_desktop 或 attach_desktop"}
    p = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isfile(p):
        return {"ok": False, "error": f"找不到文件: {p}"}
    if not p.lower().endswith(".aedt"):
        return {"ok": False, "error": "路径必须是 .aedt 文件(.aedtz 归档请先在 HFSS 里解包)"}
    base = os.path.splitext(os.path.basename(p))[0]
    try:
        open_list = list(oDesktop.GetProjectList() or [])
    except Exception:
        open_list = []
    already = base in open_list
    try:
        if already:
            try:
                oProject = oDesktop.SetActiveProject(base)
            except Exception:
                oProject = None
        else:
            oProject = oDesktop.OpenProject(p)   # 新版返回 oProject;老版可能返回 None
        if oProject is None:
            oProject = oDesktop.GetActiveProject()
        if oProject is None:
            return {"ok": False, "error": "打开后取不到 oProject(版本兼容问题?)"}
    except Exception as e:
        return {"ok": False, "error": f"打开工程失败: {type(e).__name__}: {e}"}
    try:
        pname = oProject.GetName()
    except Exception:
        pname = base
    ctx["oProject"] = oProject
    ctx["project_name"] = pname
    ctx["oDesign"] = None
    ctx["oEditor"] = None
    ctx["design_name"] = None
    if "state" in ctx:
        ctx["state"].project = pname
    try:
        designs = list(oProject.GetTopDesignList() or [])
    except Exception:
        designs = []
    target = activate_design or (designs[0] if len(designs) == 1 else None)
    activated, act_err = None, None
    if target:
        try:
            oDesign = oProject.SetActiveDesign(target)
            oEditor = oDesign.SetActiveEditor("3D Modeler")
            ctx["oDesign"] = oDesign
            ctx["oEditor"] = oEditor
            ctx["design_name"] = target
            if "state" in ctx:
                ctx["state"].design = target
            activated = target
        except Exception as e:
            act_err = f"{type(e).__name__}: {e}"
    out = {"ok": True, "project": pname, "path": p, "already_open": already,
           "designs": designs, "active_design": activated}
    if act_err:
        out["activate_warning"] = f"激活 design '{target}' 失败: {act_err},请手动 activate_design"
    elif not activated and designs:
        out["note"] = f"工程有 {len(designs)} 个 design,用 activate_design 选一个再建模/求解。"
    return out


@tool({
    "type": "function",
    "function": {
        "name": "new_design",
        "description": ("在 active project 新建 HFSS design 并激活。solution_type 默认 'Modal'(Driven Modal)。"),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "design 名,如 'd1'"},
                "solution_type": {"type": "string", "enum": ["Modal", "Terminal", "Transient", "Eigenmode"],
                                  "default": "Modal", "description": "求解类型,默认 Modal"},
            },
            "required": ["name"],
        },
    },
})
def new_design(ctx, name, solution_type="Modal"):
    oProject = ctx.get("oProject")
    if oProject is None:
        return {"ok": False, "error": "无 active project,先 new_project 或 activate_project"}
    soltype = _SOLUTION_MAP.get(solution_type, "DrivenModal")
    try:
        oProject.InsertDesign("HFSS", name, soltype, "")
        oDesign = oProject.SetActiveDesign(name)
        oEditor = oDesign.SetActiveEditor("3D Modeler")
    except Exception as e:
        return {"ok": False, "error": f"新建 design 失败: {type(e).__name__}: {e}"}
    ctx["oDesign"] = oDesign
    ctx["oEditor"] = oEditor
    ctx["design_name"] = name
    if "state" in ctx:
        ctx["state"].project = ctx.get("project_name") or ""
        ctx["state"].design = name
        ctx["state"].solution_type = solution_type
    return {"ok": True, "project": ctx.get("project_name"), "design": name, "solution_type": soltype}


@tool({
    "type": "function",
    "function": {
        "name": "activate_project",
        "description": "切换 active project。切换后 active design 清空,需再 activate_design。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "工程名,必须已打开"}},
            "required": ["name"],
        },
    },
})
def activate_project(ctx, name):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "未打开 desktop"}
    try:
        open_projects = list(oDesktop.GetProjectList() or [])
        if name not in open_projects:
            return {"ok": False, "error": f"工程 '{name}' 未打开", "available": open_projects}
        # SetActiveProject 在部分老版本会抛(返回值/状态怪),容错:抛了也试 GetActiveProject 兜底
        try:
            oProject = oDesktop.SetActiveProject(name)
        except Exception:
            oProject = None
        if oProject is None:
            oProject = oDesktop.GetActiveProject()
        if oProject is None:
            return {"ok": False, "error": f"激活工程 '{name}' 后取不到 oProject"}
    except Exception as e:
        return {"ok": False, "error": f"激活工程失败: {type(e).__name__}: {e}"}
    ctx["oProject"] = oProject
    ctx["project_name"] = name
    ctx["oDesign"] = None
    ctx["oEditor"] = None
    ctx["design_name"] = None
    if "state" in ctx:
        ctx["state"].project = name
    return {"ok": True, "project": name}


@tool({
    "type": "function",
    "function": {
        "name": "activate_design",
        "description": "切换 active design,把后续建模目标指向它。调用前必须已有 active project。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "design 名,当前 project 中已存在"}},
            "required": ["name"],
        },
    },
})
def activate_design(ctx, name):
    oProject = ctx.get("oProject")
    if oProject is None:
        return {"ok": False, "error": "无 active project,先 activate_project"}
    try:
        oDesign = oProject.SetActiveDesign(name)
        oEditor = oDesign.SetActiveEditor("3D Modeler")
    except Exception as e:
        return {"ok": False, "error": f"激活 design 失败: {type(e).__name__}: {e}"}
    ctx["oDesign"] = oDesign
    ctx["oEditor"] = oEditor
    ctx["design_name"] = name
    if "state" in ctx:
        ctx["state"].design = name
    return {"ok": True, "project": ctx.get("project_name"), "design": name}


@tool({
    "type": "function",
    "function": {
        "name": "list_projects",
        "description": "列出当前 desktop 下打开的工程,以及当前 active 的。",
        "parameters": {"type": "object", "properties": {}},
    },
})
def list_projects(ctx):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "未打开 desktop"}
    try:
        projs = list(oDesktop.GetProjectList() or [])
    except Exception as e:
        return {"ok": False, "error": f"取工程列表失败: {e}"}
    return {"ok": True, "projects": projs, "active": ctx.get("project_name")}


@tool({
    "type": "function",
    "function": {
        "name": "list_designs",
        "description": "列出 active project 下所有 design,以及当前 active 的。",
        "parameters": {"type": "object", "properties": {}},
    },
})
def list_designs(ctx):
    oProject = ctx.get("oProject")
    if oProject is None:
        return {"ok": False, "error": "无 active project"}
    try:
        designs = list(oProject.GetTopDesignList() or [])
    except Exception as e:
        return {"ok": False, "error": f"取 design 列表失败: {e}"}
    return {"ok": True, "designs": designs, "active": ctx.get("design_name")}


@tool({
    "type": "function",
    "function": {
        "name": "reset_session",
        "description": "强制清空 Agent 内部会话状态(desktop/project/design 全置空)。COM 句柄失效时调用。",
        "parameters": {"type": "object", "properties": {}},
    },
})
def reset_session(ctx):
    _clear(ctx)
    if "state" in ctx:
        st = ctx["state"]
        st.project = ""; st.design = ""
        for d in (st.variables, st.objects, st.boundaries, st.excitations, st.setups):
            d.clear()
    return {"ok": True, "msg": "会话已重置,可重新 open_desktop / attach_desktop"}


@tool({
    "type": "function",
    "function": {
        "name": "close_desktop",
        "description": "关闭当前 HFSS 桌面进程。用户说'关闭/退出 HFSS'时调用。",
        "parameters": {
            "type": "object",
            "properties": {"save": {"type": "boolean", "default": False, "description": "关闭前是否保存当前工程"}},
        },
    },
})
def close_desktop(ctx, save=False):
    oDesktop = ctx.get("oDesktop")
    if oDesktop is None:
        return {"ok": False, "error": "当前没有 desktop"}
    try:
        if save and ctx.get("oProject") is not None:
            try:
                ctx["oProject"].Save()
            except Exception:
                pass
        oDesktop.QuitApplication()
    except Exception as e:
        _clear(ctx)
        return {"ok": False, "error": f"关闭 desktop 出错: {e},但状态已清空"}
    _clear(ctx)
    return {"ok": True}
