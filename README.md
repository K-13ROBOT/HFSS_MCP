# HFSS MCP Server (native / 跨版本版)

放进 Claude Code(或任何 MCP 客户端)后,你用**自然语言**描述天线,模型照 `hfss-antenna-modeling` skill 的纪律调本 server 的工具,在 HFSS 里**真的建模、求解、出结果**。

> 本 server 是标准 **MCP stdio server**(官方 `mcp` SDK),协议层不绑任何客户端。下文以 Claude Code 为例;换别的 MCP 客户端见 [用别的 MCP 客户端](#用别的-mcp-客户端)。

**连接全走 win32com 裸调 AEDT 原生脚本 API**(oDesktop/oEditor/oModule),**不依赖 PyAEDT**,因此跨版本——**实测 2019.2 和 2025.2 都通**,适合驱动 PyAEDT/gRPC 够不到的**老版本 HFSS**(如 2019)。

**目录**:[为什么能跨版本](#为什么能跨版本) · [能做什么](#能做什么72-个工具) · [已验证](#已验证) · [安装](#安装) · [配置 & 用法](#配置--用法) · [用别的 MCP 客户端](#用别的-mcp-客户端) · [代码结构](#代码结构) · [当前短板](#当前短板) · [跨版本已知差异](#跨版本已知差异)

## 为什么能跨版本

- 连接 = `win32com.Dispatch("Ansoft.ElectronicsDesktop." + version)`(ProgID 每个装机版本都注册),不卡 PyAEDT 版本下限,也不依赖 gRPC(2022R2+ 才有)。
- 操作 = AEDT 原生脚本 API(宏录制那套),自 ~v15 稳定。

## 能做什么(72 个工具)

| 域 | 能力 |
|---|---|
| **会话** | open/attach/close、新建工程与设计、**从路径打开已有 .aedt**、切换/列举、保存工程、reset |
| **几何** | box/rectangle/cylinder/sphere/polyline、布尔(并/减/交)、变换(移动/旋转/镜像/线阵·环阵复制)、变量驱动、材料(含**自定义 εr/tanδ**)、delete |
| **自检 & 诊断** | `get_object_bbox`(看层叠/搭接)、`design_summary`、list_objects/variables;**`validate_design`**(HFSS 自带 Validation Check,analyze 前挡配置漏)、**`get_messages`**(读消息窗口——"跑通了但数不对"的第一手线索) |
| **边界** | Perfect E / Perfect H / 有限电导率 / 阻抗面 / 集总 RLC、开放辐射边界、远场球 |
| **馈电** | 集总端口、边馈/微带(一步)、同轴探针(一步)——均验证能产出**真匹配**;**端口幅度/相位**(双馈 CP 90°、差分 180°、相控阵扫描) |
| **周期单元** | 主从(Master/Slave)边界 + Floquet 端口(一步,晶格矢量自动推)——无限阵/FSS/超表面单元仿真,带扫描角 |
| **求解 & 结果** | setup + 扫频 + analyze;S11/谐振/-10dB 带宽、**VSWR + 输入阻抗 Zin**、**远场方向图**、**轴比 AR vs 频率 + 3dB 轴比带宽** |
| **参数扫描** | 一次解全部组合 + 6 指标提取:S11 / 增益 / 轴比 / 前后比 / HPBW / 交叉极化隔离 |
| **优化** | HFSS 内置优化器(自动迭代逼近目标) |
| **辅助设计** | `search_designs` / `list_design_cards` / `read_design_card`——按指标检索 `skill/.../design/` 设计卡片并**经 MCP 取回正文**拿起手尺寸;`check_design_targets`——实测 vs 目标逐项对标判定(指标驱动设计闭环的终止门) |

**可用性**:求解前 bbox 自检挡建歪、自动配色(导体金/铜、介质半透明、空气近透明)、阻塞操作弹确认框。

**skill 层(让"从论文复现"成为可能的纪律)**:读图解析(数字从参数表抽、图只判拓扑、歧义先确认)→ 经验库(`skill/.../knowledge/`,排错机理)+ 设计卡片库(`skill/.../design/`,正向设计起手)→ 显式规划 → 坐标/层叠约定 → 求解前自检 → 馈电/扫参/优化套路 → **指标驱动设计闭环**(检索卡片→缩放→建模→`check_design_targets` 对标→定向调,§10)。

## 已验证

- **跨版本**:连接 + 建模在 2019.2 + 2025.2 双版本通。
- **建模/求解/参扫的核心工具**在 2019.2 实测(含最难的参扫结果提取);辅助设计 3 个工具(`search_designs`/`list_design_cards`/`check_design_targets`)为纯本地逻辑、单测通过。
- **诊断工具**(`validate_design` / `get_messages`)在 2019.2 + 2025.2 双版本实测:坏 design(无激励 / 材料没设 solve inside)判 `passed=false`,好 design 判 `passed=true`;两版的返回码类型与消息延迟差异已在代码里兜住(见[跨版本已知差异](#跨版本已知差异))。
- **周期单元工具**(主从边界 + Floquet 端口)按 AEDT 脚本 API 实现、参数构造离线核对通过,但**COM 行为尚未逐版本真机回归**——首次用请盯结果。
- **整条管线产出过一个正确匹配的天线**(探针贴片:S11 −11.7dB / VSWR 1.7 / Zin~50Ω,自洽)——"建+求解"这半边已坐实。

## 前置要求

- **操作系统:Windows**。连接全走 win32com(pywin32),**仅 Windows**,Linux/macOS 不支持。
- **HFSS / Ansys Electronics Desktop**:本机装好目标版本(实测 2019.2、2025.2),license 可用、能正常手动启动。
- **Python 3.10+**(`mcp` 要求);建议用虚拟环境(理由见下)。
- **Claude Code** 已安装(`claude` CLI 在 PATH 里);或其它支持 MCP stdio 的客户端。

## 安装

### 1. 取代码 + 装依赖

```powershell
git clone https://github.com/K-13ROBOT/HFSS_MCP.git
cd HFSS_MCP

# 建议建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt    # 只装 mcp + pywin32,不要 pyaedt
```

> ⚠️ **关键**:`install.py` 会把"**当前正在跑它的那个 python 的绝对路径**"写进 MCP 配置当启动命令。所以**用哪个 python 装依赖、跑 install.py,server 以后就用哪个**。用了 venv,就在 venv 激活状态下跑后面所有 `python ...` 命令。

### 2. 自检(不启 HFSS)

```powershell
python smoke_mcp.py        # 看到 SMOKE OK = 依赖装好、工具能注册
```

### 3. 注册给 Claude Code

先**预览**将写入的配置(不动任何文件):

```powershell
python install.py
```

它会打印 ① 一段 `.mcp.json` ② 一条 `claude mcp add` 命令 ③ 推导出的 env。按使用范围二选一:

**方式 A — 只给某个项目(建议先用这个)**

```powershell
python install.py --project D:\path\to\your\project
```

一条命令写好三样(已存在则合并,不覆盖):
- `<项目>\.mcp.json` ← MCP server 注册(项目级)
- `<项目>\.claude\skills\hfss-antenna-modeling\` ← skill(含 knowledge/ 经验库 + design/ 设计卡片库)
- `<项目>\.claude\settings.json` ← 给 `analyze` 加"执行前确认"(防误触阻塞操作)

**方式 B — 全局(所有项目可用)**

```powershell
python install.py --skill-user      # ① 把 skill 装到 ~/.claude/skills/
```
然后**复制运行上一步打印的那条 `claude mcp add` 命令**注册 server,形如:
```powershell
claude mcp add hfss-agent-native --scope user -e HFSS_VERSION="2025.2" -- "C:\...\.venv\Scripts\python.exe" "C:\...\HFSS_MCP\hfss_mcp_server.py"
```

> 本脚本**绝不改全局 `~/.claude.json`**;全局 MCP 注册一律靠那条 `claude mcp add`(你能看清到底写了什么)。

### 4. 生效 + 验证

1. **重启 Claude Code**(改了 MCP 配置必须重启才加载)。
2. `/mcp` 应看到 **`hfss-agent-native`**。
3. 直接说一句"用 HFSS 建一个 2.45GHz 微带贴片并跑 S11",Claude 会自动走 `hfss-antenna-modeling` skill 调工具建模、求解、出结果。

## 配置 & 用法

**连哪个版本**:默认连 env 里的 `HFSS_VERSION`(`install.py` 从最高的 `ANSYSEM_ROOT###` 环境变量推导;推导不到则默认 `2025.2`)。**要连老版本(如 2019.2)**:对话里让 `open_desktop` 传 `version="2019.2"`,或改 `.mcp.json` env 里的 `HFSS_VERSION`。

**license**:`install.py` 会把本机的 `ANSYSLMD_LICENSE_FILE` / `ANSYSLIC_DIR`(若有)带进 server env;缺了就按你平时启动 HFSS 的方式补进 env 块。

**工程文件 / 导出**:`.aedt` 默认存到 server 运行目录(cwd)下的 `projects/`,导出的 CSV/报表存 `exports/`(分别可用 `HFSS_PROJECTS_DIR` / `HFSS_EXPORTS_DIR` 覆盖)。**cwd 由 MCP 客户端决定**——落在不可写目录时自动退到 `~/.hfss-agent/`,再不行退临时目录,不会启动失败。

**阻塞操作的确认**:`analyze` / 参扫 / 优化耗时且阻塞。stdio 下进程内的 `[y/N]` 已关(stdin 被协议占用),改由**客户端权限系统**拦——Claude Code 靠 `settings.json` 里的 `ask` 规则(`install.py --project` 已写好 `mcp__hfss-agent-native__analyze`)。别的客户端要靠它自己的工具授权。

**设计卡片目录**(辅助设计检索):`search_designs` 按 `HFSS_DESIGN_DIR` → `~/.claude/skills/.../design/` → bundle 内 `skill/.../design/` 顺序找卡片,一般无需配置。

## 用别的 MCP 客户端

server 是标准 MCP stdio,**任何 MCP 客户端都能挂**(Claude Desktop、Cline、Continue、Cursor、或自写的 MCP agent)。`python install.py` 打印的配置里 `command` / `args` / `env` 三样是通用的,按目标客户端的配置格式填即可:

```jsonc
{
  "command": "<python 路径>",          // 装了依赖的那个 python(venv 则用 venv 的)
  "args": ["<bundle>/hfss_mcp_server.py"],
  "env": { "HFSS_VERSION": "2025.2", "ANSYSLMD_LICENSE_FILE": "..." }
}
```

**兼容性已实测**(用通用 MCP SDK 客户端,非 Claude Code):协议版本 2024-11-05 / 2025-03-26 / 2025-06-18 都能正确协商降级;72 个工具 schema 全合规;返回统一 `TextContent` + UTF-8 JSON;stdout 做了 fd 级隔离。**cwd 由客户端决定**——落在不可写目录(如系统目录)时,`projects/`、`exports/`、`traces/` 会自动退到 `~/.hfss-agent/`,不会像以前那样在 initialize 之前就崩。

**长任务不再阻塞协议**:所有 COM 调用跑在一个专用线程上,事件循环全程空闲——实测 `analyze` 求解期间 `tools/list` 连续 9 次全部 <0.01s 返回。客户端的 ping/keepalive 不会超时,不会误判 server 已死而杀进程。但注意**两点仍然成立**:① `analyze` 这个请求本身就是几分钟,设了硬性单请求超时的客户端仍会在这一个调用上超时;② 求解**无法中途中止**(阻塞 COM 调用没有中断点),客户端发的 cancel 会被应答但求解照跑,后续调用排在它后面。

换客户端会**丢两样 Claude Code 专属能力**,知道就行:

1. **skill 不会自动加载**——`hfss-antenna-modeling` 是 Claude 的 skill 机制,别的客户端不读。工具照样能调,但丢了"怎么正确用"的纪律(坐标/层叠约定、求解前自检、经验库、设计闭环)。
   - 变通:把本仓库 `skill/hfss-antenna-modeling/SKILL.md`(及 `knowledge/`、`design/`)的内容放进那个 agent 的 system prompt / 上下文当指南。
2. **确认门**——如上,stdio 下进程内确认已关。客户端若没有工具授权 UI,`analyze`/扫参/优化会**直接跑、不问你**。用支持 MCP 工具授权的客户端,或自己留意别误触。

## 代码结构

```
hfss_mcp_server.py   MCP stdio 入口:常驻 ctx 持有 COM 句柄(oDesktop/oProject/oDesign/oEditor)
tools/__init__.py    工具注册表(@tool 装饰器)+ dispatch:前置校验、确认门、trace 落盘
tools/*.py           按域分文件:session / geometry / booleans / transforms / variables /
                     boundaries / excitations / sources / analysis / axialratio / mesh /
                     parametrics / optimization / periodic / diagnostics / design
model_state.py       Agent 侧的模型状态镜像(对象/变量/边界/激励/setup),供 design_summary 等用
install.py           打印/写入 MCP 配置 + 安装 skill(不改全局 ~/.claude.json)
smoke_mcp.py         不启 HFSS 的 stdio 冒烟:工具能否注册、协议往返是否干净
skill/hfss-antenna-modeling/
    SKILL.md         建模纪律(坐标/层叠约定、求解前自检、馈电/扫参/优化套路、设计闭环)
    knowledge/       排错经验库(按天线类型,随用变厚)
    design/          设计卡片库(λ 归一化尺寸/闭式公式,供 search_designs 检索)
```

## 当前短板

1. **最弱的是"读图/理解复杂结构"那半边,不是建模管线**。折叠/多层/定制馈电这类复杂拓扑,AI 从图反推容易错,仍要靠用户确认结构(skill §0 已尽量兜底)。
2. `analyze` 求解**无法中途中止**(阻塞 COM 调用无中断点)。协议层已不受影响(COM 走专用线程,事件循环空闲),但求解本身停不下来。
3. 经验库还年轻(随用随厚)。
4. 工具偏多,每轮 token 有成本(数量见[能做什么](#能做什么72-个工具)那张表)。

## 未来方向

- **近期(打磨)**:拿真论文端到端跑通"读图→建模";经验库随用沉淀。
- **中期(补能力)**:更多馈电/结构类型、场图/电流分布导出、工具按需收敛降 token。
- **远期愿景(设计顾问)**:从"照着建"进化到"参考文献辅助设计"——给指标/参考论文,它建议结构+尺寸并实现、仿真、迭代到达标;底层靠 λ 归一化设计卡片库 + 经验库。

## 跨版本已知差异

真机实测踩出来的坑,**都已在工具内兜底**,列在这里是为了别被"优化"回去:

| 项 | 2019.2 | 2025.2 | 兜底做法 |
|---|---|---|---|
| `CreateReport` 参数个数 | 8 参 | 7 参 | 多形式挨个试,谁不抛用谁 |
| 远场球方法名 | `InsertFarFieldSphereSetup` | `InsertInfiniteSphereSetup` | 两个都试 |
| `ValidateDesign()` 返回码 | `int`(坏 0 / 好 1) | `bool`(坏 False / 好 True) | `bool()` 统一,假=失败 |
| 消息窗口写入 | **滞后可达几十秒** | 即时 | 判定以返回码为主,消息只说明"错在哪" |
| `GetMessages` 的 severity 参数 | — | **0/1/2 结果相同,不起作用** | 级别自己从 `[error]`/`[warning]` 标记解析 |
| 扫频存远场 | — | **单设 `SaveRadFields` 不生效** | 取 AR/增益 vs 频率要 `Discrete` + `save_fields=True` |

另有两条与版本无关、但同样反直觉:

- **`CreateRectangle` 的 XZ 平面 Width/Height 轴向与直觉相反**(WhichAxis=Y 时 Width→Z、Height→X),已在 `create_rectangle` 内修正。
- **端口积分线不能直接放变量名**(老版本会崩),工具会自动解析成字面量(同轴端口除外,要求本来就传字面量)。

## 其它已知点

- server 名 **`hfss-agent-native`** 写死(settings 的 `mcp__hfss-agent-native__analyze` 确认规则 key 在它上)。
- 工程存 cwd 下 `projects/`、导出存 `exports/`(可用 `HFSS_PROJECTS_DIR` / `HFSS_EXPORTS_DIR` 覆盖);cwd 不可写时自动退到 `~/.hfss-agent/`。

## License

MIT,见 [LICENSE](LICENSE)。
