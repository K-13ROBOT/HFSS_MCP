# HFSS MCP Server (native)

放进 Claude Code(或任何 MCP 客户端)后,你用**自然语言**描述天线,模型照 `hfss-design` skill 的纪律调本 server 的工具,在 HFSS 里**真的建模、求解、出结果**。

> 本 server 是标准 **MCP stdio server**(官方 `mcp` SDK),协议层不绑任何客户端。下文以 Claude Code 为例;换别的 MCP 客户端见 [用别的 MCP 客户端](#用别的-mcp-客户端)。

**连接全走 win32com 裸调 AEDT 原生脚本 API**(oDesktop/oEditor/oModule),**不依赖 PyAEDT**。实测 2019.2 和 2025.2 都通,PyAEDT/gRPC 够不到的老版本 HFSS(如 2019)也能驱动。

**目录**:[为什么不依赖 PyAEDT](#为什么不依赖-pyaedt) · [能做什么](#能做什么93-个工具) · [skill 层](#skill-层三个) · [已验证](#已验证) · [安装](#安装) · [配置 & 用法](#配置--用法) · [用别的 MCP 客户端](#用别的-mcp-客户端) · [代码结构](#代码结构) · [已知的版本差异](#已知的版本差异)

## 为什么不依赖 PyAEDT

- 连接 = `win32com.Dispatch("Ansoft.ElectronicsDesktop." + version)`(ProgID 每个装机版本都注册),不卡 PyAEDT 版本下限,也不依赖 gRPC(2022R2+ 才有)。
- 操作 = AEDT 原生脚本 API(宏录制那套),自 ~v15 稳定。

## 能做什么(93 个工具)

| 域 | 能力 |
|---|---|
| **会话** | open/attach/close、新建工程与设计、**从路径打开已有 .aedt**、切换/列举、保存工程、reset |
| **几何** | box/rectangle/circle/cylinder/sphere/polyline/helix、布尔(并/减/交)、`split`、`thicken`(sheet→实体)、变换(移动/旋转/镜像/线阵·环阵复制)、变量驱动、材料(含**自定义 εr/tanδ**)、delete |
| **自检 & 诊断** | `get_object_bbox`(看层叠/搭接)、`design_summary`、list_objects/variables;**`validate_design`**(HFSS 自带 Validation Check,analyze 前挡配置漏)、**`get_messages`**(读消息窗口——"跑通了但数不对"的第一手线索) |
| **边界** | Perfect E / Perfect H / 有限电导率 / 阻抗面 / 集总 RLC、开放辐射边界、远场球 |
| **馈电** | 集总端口、**波导端口**(多模/de-embed)、边馈/微带(一步)、同轴探针(一步)——均验证能产出**真匹配**;**端口幅度/相位**(双馈 CP 90°、差分 180°、相控阵扫描) |
| **周期单元** | 主从(Master/Slave)边界 + Floquet 端口(一步,晶格矢量自动推)——无限阵/FSS/超表面单元仿真,带扫描角 |
| **本征模** | `create_eigenmode_setup` + `get_eigenmodes`——不要端口、不要激励,直接解结构自身的谐振频率与 Q。腔体/滤波器/介质谐振器(DRA)/周期结构的模式分析;驱动求解要先猜馈电位置,猜错了模激发不出来,本征模没这问题。50×25×40mm 腔实测与解析解偏差 <0.02% |
| **求解 & 结果** | setup + 扫频 + analyze(驱动求解);S11/谐振/-10dB 带宽、**VSWR + 输入阻抗 Zin**、**远场方向图**、**轴比 AR vs 频率 + 3dB 轴比带宽** |
| **场诊断** | `get_current_along_path`——沿 polyline 取表面电流分布 + 判据(模次 = 内部零点数+1、峰值位置、首尾衰减 dB)。补的是"只能测进去多少/出来多少、看不见结构上实际流了什么"这个盲区:失配不知往哪调、谐振对而方向图不对、寄生臂有没有被激励、行波辐射完没、弱接触,都靠它。**条件触发不是每次都看**,见 SKILL.md §6.9 |
| **参数扫描** | 一次解全部组合 + 6 指标提取:S11 / 增益 / 轴比 / 前后比 / HPBW / 交叉极化隔离 |
| **优化** | HFSS 内置优化器:给代价表达式和目标值,求解器自己梯度/遗传迭代,写回最优变量 |
| **设计分析** | **灵敏度**——在工作点算各变量对指标的偏导,扫参前先问"该动哪个";权重远小于 1 的变量直接固定,省掉大半机时。**公差/良率**——加工公差分布跑蒙特卡洛,出指标分布与良率,回答"按这个公差投产能做出来吗"。两者是同一个偏导的两面:前者问动哪个旋钮,后者问旋钮抖动时结果散多少 |
| **工程卫生** | `cleanup_solutions` 回收解/场数据(对应 GUI 的 Clean Up Solutions)、`delete_setup` / `delete_sweep` / `delete_parametric` 清掉建错的和孤儿的——三个删除工具都是 `confirm=true` 才真删,不传 names 时只回显清单。**调参期工程里只留一个 setup**,存场扫频堆着会让每轮求解从十几分钟涨到一两小时 |
| **辅助设计** | `search_designs` / `list_design_cards` / `read_design_card`——按指标检索 `skill/.../design/` 设计卡片并**经 MCP 取回正文**拿起手尺寸;`check_design_targets`——实测 vs 目标逐项对标判定(指标驱动设计闭环的终止门) |

**可用性**:求解前 bbox 自检挡建歪、自动配色(导体金/铜、介质半透明、空气近透明)、阻塞操作弹确认框。

## skill 层(三个)

MCP 工具是"手",skill 是"怎么正确用手"的纪律 —— 复现文献总建歪、设计不收敛,绝大多数不是工具不行,
是缺纪律。三个 skill 各管一段,**既能 `/名字` 直接点,也会按 description 自动匹配**。

| 斜杠命令 | 什么时候用 | 它管什么 |
|---|---|---|
| **`/hfss-design`** | 建几何、加端口边界、跑 S 参数/远场、扫参优化 —— **天线活儿的默认入口** | 读图解析 → 显式规划 → 坐标/层叠约定 → 求解前双自检 → 馈电/扫参/优化套路 → 指标驱动设计闭环 |
| **`/hfss-search`** | 要找文献、问"有没有参考论文""这类天线别人怎么设计的"、给了 PDF 要提炼 | 指标 → 英文检索式 → 五道筛选门 → 交回原文库精读 → 结构理解表交用户确认 |
| **`/hfss-stackup`** | 丢来板厂叠层表(StackUp Report)、"按这个叠层建板子" | dump 表格 → 解析行业约定 → 总厚自校验 → 出层表确认 → 全参数化建模 |

### 斜杠命令:两个入口

skill 的路由靠 agent 自己判断任务性质,**命令给一个不靠判断的入口**。
`install.py --project` 把 `commands/hfss-*.md` 装到 `<项目>/.claude/commands/`(`--skill-user` 则装到 `~/.claude/commands/`):

| 命令 | 用在什么时候 |
|---|---|
| **`/hfss-model`** | 要把天线**建出来并求解** —— 复现文献、正向设计、加馈电、取远场、本征模、周期单元,都走它 |
| **`/hfss-tune`** | 已经有设计了,**指标不达标要调** —— 灵敏度、扫参、公差、诊断 |

**只有两个是刻意的。** 曾按 `flow/` 的 11 张卡一一对应生成 11 个命令,那是把内部
文件结构当成了用户界面——用户脑子里只有"建模"和"优化",不会去想"我需要 feeding
那张卡"。**细分交给 `SKILL.md` 的路由表**(agent 读了自己判断),命令只负责把人送进大门。

命令体只是**指针**(读哪些文件 + 接 `$ARGUMENTS`),内容一律在流程卡里 —— 复制一份
就是两份要同步。由 `make_commands.py` 生成。安装时**只写 `hfss-*.md`**,并清掉本 bundle
不再提供的旧 `hfss-*` 命令;`~/.claude/commands/` 里别的命令不碰不删。

### 三者怎么衔接

```
给指标做设计  ──→ /hfss-design §10 闭环第 1 步:search_designs 查卡片库
                      │
        命中 ─────────┤──── 未命中 ──→ /hfss-search 检索文献 → 筛选 → 精读
                      │                      │
                      └──←── 起手尺寸 ←──────┘(结构理解表,用户确认后才建)
                      ↓
                 建模 → analyze → check_design_targets 对标 → 不达标定向调
                      ↓
                 达标 + 用户点头 → 录卡沉淀(公式,不是绝对尺寸)

给真实叠层建板 ──→ /hfss-stackup 还原多层板 ──→ 板子上要放天线则接 /hfss-design
```

### 三个库(在 `hfss-design` 里,随用变厚)

| 目录 | 装什么 | 判据 |
|---|---|---|
| `design/` | **可缩放的设计数据**:闭式公式 > λ₀ 归一化常数 > 报告性能与出处 | 换个频率/εr 还用得上 |
| `knowledge/` | **建模排错经验**:机理、HFSS 操作陷阱、哪个自由度控哪个指标 | 换一篇同类但结构不同的论文还用得上 |
| `papers/` | **文献原文**:`_HOWTO.md`(通用读法,随分发)+ 每篇的「章节/图表→页」索引 + PDF(个人资料,不分发) | 卡片只够选型,要建就得回原图 |

`design/` 由 `search_designs` / `list_design_cards` / `read_design_card` 三个 MCP 工具检索,所以**换任何 MCP
客户端都取得到**;`knowledge/` 和 `papers/` 靠模型读文件。

> **一条纪律贯穿三个 skill**:卡片只录**自己仿真达标、且用户确认**过的东西,录的是**公式和归一化常数,
> 不是论文那一款的绝对毫米尺寸**(换个频率就作废,留着只会误导下次检索)。照抄论文数字入库,
> 库就废了 —— 它的全部价值在于"里面的数字都验证过"。

## 已验证

- **版本**:连接 + 建模在 2019.2 和 2025.2 都实测通过。
- **建模/求解/参扫的核心工具**在 2019.2 实测(含最难的参扫结果提取);辅助设计 3 个工具(`search_designs`/`list_design_cards`/`check_design_targets`)为纯本地逻辑、单测通过。
- **诊断工具**(`validate_design` / `get_messages`)在 2019.2 + 2025.2 双版本实测:坏 design(无激励 / 材料没设 solve inside)判 `passed=false`,好 design 判 `passed=true`;两版的返回码类型与消息延迟差异已在代码里兜住(见[已知的版本差异](#已知的版本差异))。
- **周期单元工具**(主从边界 + Floquet 端口)按 AEDT 脚本 API 实现、参数构造离线核对通过,但**COM 行为尚未逐版本真机回归**——首次用请盯结果。
- **最近新增的工具在 2019.2 + 2025.2 双版本回归通过**(15/15):场诊断(沿路径取表面电流)、灵敏度三件套、统计/公差三件套、本征模求解,以及 `thicken` / `create_circle` / `split` / `create_wave_port` / `delete_sweep` / `cleanup_solutions`。
  **本征模与解析解对过**:50×25×40mm 真空腔前三个模,2019.2 偏差 0.004~0.019%、2025.2 偏差 0.005~0.021%。
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

一条命令写好四样(已存在则合并,不覆盖):
- `<项目>\.mcp.json` ← MCP server 注册(项目级;已有条目里自己加的 env 键、timeout 保留)
- `<项目>\.claude\skills\` ← 三个 skill(含 knowledge/ 经验库 + design/ 设计卡片库)
- `<项目>\.claude\commands\` ← `/hfss-*` 斜杠命令(只动 `hfss-*.md`)
- `<项目>\.claude\settings.json` ← 给 `analyze` 加"执行前确认"(防误触阻塞操作)

**方式 B — 全局(所有项目可用)**

skill 和命令装到全局、MCP 却只在某个项目注册的话,别的项目里也能敲 `/hfss-*`,但调不到任何工具。
两者要么都全局,要么都项目级。

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
3. 直接说一句"用 HFSS 建一个 2.45GHz 微带贴片并跑 S11",Claude 会自动走 `hfss-design` skill 调工具建模、求解、出结果。

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

**兼容性已实测**(用通用 MCP SDK 客户端,非 Claude Code):协议版本 2024-11-05 / 2025-03-26 / 2025-06-18 都能正确协商降级;93 个工具 schema 全合规;返回统一 `TextContent` + UTF-8 JSON;stdout 做了 fd 级隔离。**cwd 由客户端决定**——落在不可写目录(如系统目录)时,`projects/`、`exports/`、`traces/` 会自动退到 `~/.hfss-agent/`,不会像以前那样在 initialize 之前就崩。

**长任务不再阻塞协议**:所有 COM 调用跑在一个专用线程上,事件循环全程空闲——实测 `analyze` 求解期间 `tools/list` 连续 9 次全部 <0.01s 返回。客户端的 ping/keepalive 不会超时,不会误判 server 已死而杀进程。但注意**两点仍然成立**:① `analyze` 这个请求本身就是几分钟,设了硬性单请求超时的客户端仍会在这一个调用上超时;② 求解**无法中途中止**(阻塞 COM 调用没有中断点),客户端发的 cancel 会被应答但求解照跑,后续调用排在它后面。

换客户端会**丢两样 Claude Code 专属能力**,知道就行:

1. **三个 skill 都不会自动加载**——那是 Claude 的 skill 机制,别的客户端不读。93 个工具照样能调,但丢了"怎么正确用"的纪律([skill 层](#skill-层三个)那一节的全部内容)。
   - 变通:把 `skill/hfss-design/SKILL.md` 放进那个 agent 的 system prompt 当指南;要查文献或还原叠层再补 `skill/hfss-search/` 或 `skill/hfss-stackup/` 的 SKILL.md。
   - `design/` 卡片库不受影响——它由 `search_designs` / `read_design_card` 经 MCP 提供,任何客户端都取得到;`knowledge/` 和 `papers/` 则要靠那个 agent 自己有文件读取能力。
2. **确认门**——如上,stdio 下进程内确认已关。客户端若没有工具授权 UI,`analyze`/扫参/优化会**直接跑、不问你**。用支持 MCP 工具授权的客户端,或自己留意别误触。

## 代码结构

```
hfss_mcp_server.py   MCP stdio 入口:常驻 ctx 持有 COM 句柄(oDesktop/oProject/oDesign/oEditor)
tools/__init__.py    工具注册表(@tool 装饰器)+ dispatch:前置校验、确认门、trace 落盘
tools/*.py           按域分文件:session / geometry / booleans / transforms / variables /
                     boundaries / excitations / sources / analysis / axialratio / fields /
                     mesh / parametrics / optimization / periodic / diagnostics / design
model_state.py       Agent 侧的模型状态镜像(对象/变量/边界/激励/setup),供 design_summary 等用
install.py           打印/写入 MCP 配置 + 安装 skill(不改全局 ~/.claude.json)
smoke_mcp.py         不启 HFSS 的 stdio 冒烟:工具能否注册、协议往返是否干净
skill/hfss-design/      建模纪律 skill
    SKILL.md         坐标/层叠约定、求解前自检、馈电/扫参/优化套路、指标驱动设计闭环
    knowledge/       排错经验库(按天线类型,随用变厚)
    design/          设计卡片库(λ 归一化尺寸/闭式公式,供 search_designs 检索)
    papers/          原文库:_HOWTO.md(通用读法,随分发)+ INDEX.md/PDF(个人资料,不分发)
skill/hfss-search/                文献检索 skill
    SKILL.md         指标→检索式→候选筛选→交回原文库精读→出确认表→回建模闭环
skill/hfss-stackup/               PCB 叠层还原 skill
    SKILL.md         dump 表格→解析行业约定→总厚自校验→出层表确认→参数化建模
                     (install.py 遍历 skill/ 下每个含 SKILL.md 的目录,三个一起装)
```

## 已知的版本差异

真机实测踩出来的坑,**都已在工具内兜底**,列在这里是为了别被"优化"回去:

| 项 | 2019.2 | 2025.2 | 兜底做法 |
|---|---|---|---|
| `CreateReport` 参数个数 | 8 参 | 7 参 | 多形式挨个试,谁不抛用谁 |
| 远场球方法名 | `InsertFarFieldSphereSetup` | `InsertInfiniteSphereSetup` | 两个都试 |
| `ValidateDesign()` 返回码 | `int`(坏 0 / 好 1) | `bool`(坏 False / 好 True) | `bool()` 统一,假=失败 |
| 消息窗口写入 | **滞后可达几十秒** | 即时 | 判定以返回码为主,消息只说明"错在哪" |
| `GetMessages` 的 severity 参数 | — | **0/1/2 结果相同,不起作用** | 级别自己从 `[error]`/`[warning]` 标记解析 |
| 扫频存远场 | — | **单设 `SaveRadFields` 不生效** | 取 AR/增益 vs 频率要 `Discrete` + `save_fields=True` |
| 本征模 setup 的 `MeshLink` 块 | **出现就要求 partner project 名**,否则报"The partner project name cannot be empty" | 可带可不带(`ImportMesh:=False` 时无作用)| 一律不发这个块 |

另有几条与版本无关、但同样反直觉:

- **`CreateRectangle` 的 XZ 平面 Width/Height 轴向与直觉相反**(WhichAxis=Y 时 Width→Z、Height→X),已在 `create_rectangle` 内修正。
- **端口积分线不能直接放变量名**(老版本会崩),工具会自动解析成字面量(同轴端口除外,要求本来就传字面量)。
- **AEDT 对不认识的参数键静默忽略**:键名写错不报"未知参数",而是按缺省处理,报错指向别处
  (如 `Mirror` 把 `MirrorNormalX` 写成 `MirrorNormalVecX` → 报"向量非法"),甚至返回成功、存进去的全是默认值
  (多频自适应用键值对而不是 `NAME:` 嵌套写法)。新写 COM 调用后 `save_project`,grep `.aedt` 里对应的块核对;
  要抄脚本写法,去 AEDT 安装目录搜录制脚本(`.aedt` 的存盘格式和脚本格式不一样,只能用来核对)。
- **`GetValidISolutionList` 不能用来判"有没有解"**:没解过的 setup 它也列着(2019.2 实测),
  解被作废后也照样列着。工具一律用 `ExportConvergence` 的收敛表判断。

## 其它已知点

- server 名 **`hfss-agent-native`** 写死(settings 的 `mcp__hfss-agent-native__analyze` 确认规则 key 在它上)。
- 工程存 cwd 下 `projects/`、导出存 `exports/`(可用 `HFSS_PROJECTS_DIR` / `HFSS_EXPORTS_DIR` 覆盖);cwd 不可写时自动退到 `~/.hfss-agent/`。

## License

MIT,见 [LICENSE](LICENSE)。
