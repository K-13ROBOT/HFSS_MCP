# HFSS MCP Server (native / 跨版本版)

放进 Claude Code 后,你用**自然语言**描述天线,Claude 照 `hfss-antenna-modeling` skill 的纪律调本 server 的工具,在 HFSS 里**真的建模、求解、出结果**。

**连接全走 win32com 裸调 AEDT 原生脚本 API**(oDesktop/oEditor/oModule),**不依赖 PyAEDT**,因此跨版本——**实测 2019.2 和 2025.2 都通**,适合驱动 PyAEDT/gRPC 够不到的**老版本 HFSS**(如 2019)。

## 为什么能跨版本

- 连接 = `win32com.Dispatch("Ansoft.ElectronicsDesktop." + version)`(ProgID 每个装机版本都注册),不卡 PyAEDT 版本下限,也不依赖 gRPC(2022R2+ 才有)。
- 操作 = AEDT 原生脚本 API(宏录制那套),自 ~v15 稳定。

## 能做什么(65 个工具)

| 域 | 能力 |
|---|---|
| **会话** | open/attach/close、新建/切换 工程与设计、列举、reset |
| **几何** | box/rectangle/cylinder/sphere/polyline、布尔(并/减/交)、变换(移动/旋转/镜像/线阵·环阵复制)、变量驱动、材料(含**自定义 εr/tanδ**)、delete |
| **自检** | `get_object_bbox`(看层叠/搭接)、`design_summary`、list_objects/variables |
| **边界** | Perfect E / Perfect H / 有限电导率 / 阻抗面 / 集总 RLC、开放辐射边界、远场球 |
| **馈电** | 集总端口、边馈/微带(一步)、同轴探针(一步)——均验证能产出**真匹配** |
| **求解 & 结果** | setup + 扫频 + analyze;S11/谐振/-10dB 带宽、**VSWR + 输入阻抗 Zin**、**远场方向图** |
| **参数扫描** | 一次解全部组合 + 6 指标提取:S11 / 增益 / 轴比 / 前后比 / HPBW / 交叉极化隔离 |
| **优化** | HFSS 内置优化器(自动迭代逼近目标) |
| **辅助设计** | `search_designs` / `list_design_cards`——按指标检索 `skill/.../design/` 设计卡片拿起手尺寸;`check_design_targets`——实测 vs 目标逐项对标判定(指标驱动设计闭环的终止门) |

**可用性**:求解前 bbox 自检挡建歪、自动配色(导体金/铜、介质半透明、空气近透明)、阻塞操作弹确认框。

**skill 层(让"从论文复现"成为可能的纪律)**:读图解析(数字从参数表抽、图只判拓扑、歧义先确认)→ 经验库(`skill/.../knowledge/`,排错机理)+ 设计卡片库(`skill/.../design/`,正向设计起手)→ 显式规划 → 坐标/层叠约定 → 求解前自检 → 馈电/扫参/优化套路 → **指标驱动设计闭环**(检索卡片→缩放→建模→`check_design_targets` 对标→定向调,§10)。

## 已验证

- **跨版本**:连接 + 建模在 2019.2 + 2025.2 双版本通。
- **全 61 工具**在 2019.2 实测(含最难的参扫结果提取)。
- **整条管线产出过一个正确匹配的天线**(探针贴片:S11 −11.7dB / VSWR 1.7 / Zin~50Ω,自洽)——"建+求解"这半边已坐实。

## 前置 & 安装

- 本机装好目标版本 HFSS(2019.2 / 2025.2 …),license 可用。
- 装依赖(**很轻,不要 pyaedt**):
  ```powershell
  python -m pip install -r requirements.txt    # mcp + pywin32
  ```
- 注册:
  ```powershell
  python install.py              # 看配置
  python install.py --skill-user # skill 装到 ~/.claude/skills/,再按打印的 claude mcp add 注册
  python install.py --project D:\path\to\project   # 只给某项目
  ```
- 重启 Claude Code,`/mcp` 看到 `hfss-agent-native`。

## 用

默认连 `HFSS_VERSION`(install 推导的最高版本)。**要连老版本**:对话里让 `open_desktop` 传 `version="2019.2"`,或改 `.mcp.json` env 里的 `HFSS_VERSION`。

自检(不启 HFSS):`python smoke_mcp.py` → 看到 `SMOKE OK`。

## 当前短板

1. **最弱的是"读图/理解复杂结构"那半边,不是建模管线**。折叠/多层/定制馈电这类复杂拓扑,AI 从图反推容易错,仍要靠用户确认结构(skill §0 已尽量兜底)。
2. `analyze` 阻塞,**暂无 Ctrl+C 中止**。
3. 经验库还年轻(随用随厚)。
4. 工具偏多(62),每轮 token 有成本。

## 未来方向

- **近期(打磨)**:拿真论文端到端跑通"读图→建模";经验库随用沉淀。
- **中期(补能力)**:更多馈电/结构类型、场图/电流分布导出、工具按需收敛降 token。
- **远期愿景(设计顾问)**:从"照着建"进化到"参考文献辅助设计"——给指标/参考论文,它建议结构+尺寸并实现、仿真、迭代到达标;底层靠 λ 归一化设计卡片库 + 经验库。

## 已知点

- server 名 **`hfss-agent-native`** 写死(settings 的 `mcp__hfss-agent-native__analyze` 确认规则 key 在它上)。
- 工程存到运行目录 cwd 下 `projects/`(可 `HFSS_PROJECTS_DIR` 覆盖)。
- **CreateReport 跨版本 arity 不同**(2019=8 参,2025=7 参),结果提取已用多形式兜底。
- **CreateRectangle 的 XZ 平面 Width/Height 轴向**与直觉相反(已在工具内修正);**端口积分线**变量名会自动解析成字面量(同轴除外)。
