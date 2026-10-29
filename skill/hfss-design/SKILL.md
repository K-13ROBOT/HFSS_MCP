---
name: hfss-design
description: >-
  在 Ansys HFSS 里用自然语言做天线/微波结构建模与仿真。当用户要建几何(贴片、偶极、阵列、
  缝隙耦合等)、加端口/边界、跑 S 参数或远场(增益/轴比/HPBW)、做参数扫描或优化时使用。
  依赖已注册的 hfss-agent MCP server 提供的工具(open_desktop / create_box / analyze 等)。
---

# HFSS 天线建模

用户用自然语言描述结构,你调 `hfss-agent` MCP 工具在 HFSS 里**实际建模**,不要只用文字回答。
工具怎么用以工具描述为准;本文件和流程卡只讲流程和判断。

## ★ 路由:什么任务读哪张流程卡

本文件只放每个任务都要守的约定,具体流程在 `flow/` 里。**按任务读了卡再开工。**

| 任务 | 必须先读 | 最常被违反的一条 |
|---|---|---|
| **开工第一件事**(任何天线任务) | [`flow/capture-learning.md`](flow/capture-learning.md) | 先读经验库,坑只踩一次 |
| 照论文尺寸复现 | [`flow/reproduce-paper.md`](flow/reproduce-paper.md) | **尺寸只从参数表/正文抽,绝不在图上量**;拓扑有歧义先让用户确认 |
| 给的是**目标/规格**不是现成尺寸 | [`flow/design-loop.md`](flow/design-loop.md) | 先对标再调、调完再对标,别靠眼估说"差不多达标" |
| 跑 S 参数 / 完整求解一个设计 | [`flow/s-parameters.md`](flow/s-parameters.md) | 求解前 bbox + validate 两道自检不许跳 |
| 取远场(增益/轴比/HPBW/前后比) | [`flow/farfield.md`](flow/farfield.md) | **多端口先 `set_port_excitation` 设幅相**,否则算的是同相馈电 |
| 非标准馈电(缝隙/近耦合/CPW/差分/多层) | [`flow/feeding.md`](flow/feeding.md) | **端口 sheet 绝不赋 PE** |
| 指标不达标要调(扫参/灵敏度/扰动法/公差/优化) | [`flow/tuning.md`](flow/tuning.md) | **收敛了就信默认网格,先查模型和设置**;多谐振结构第一次不达标就先看电流 |
| 指标不对但**不知道为什么** | [`flow/diagnose-current.md`](flow/diagnose-current.md) | 采样线按 `get_current_along_path` 描述的要求画(非模型、开口、避开馈电点) |
| 腔体/滤波器/DRA,要谐振频率与 Q | [`flow/eigenmode.md`](flow/eigenmode.md) | **design 必须建成 Eigenmode 类型**,不要端口 |
| 无限阵 / FSS / 超表面单元 | [`flow/periodic.md`](flow/periodic.md) | **不要 `create_open_region`** |
| 阵列复制、改网格、建螺旋 | [`flow/geometry-advanced.md`](flow/geometry-advanced.md) | 复制出来的副本**不带 PE**,复制完重新赋 |
| 板厂叠层表还原多层板 | 转 `hfss-stackup` skill | 读错一条行业约定,整板厚度就错 |
| 要找文献 / 卡片库没有匹配拓扑 | 转 `hfss-search` skill | 先查本地库,别一上来就联网 |

- **任务性质中途会变,变了就回来重查这张表。** 最常见:正向设计调了几轮调不动 → 其实已经是"不知道为什么"。
- **收工回 `flow/capture-learning.md`**,把坑记进 `knowledge/`、把验证过的设计录成 `design/` 卡片。
- **上下文被压缩后**,看不到这张路由表就重新用 Skill 工具加载 `hfss-design`,再重读当前任务的流程卡
  (用 Read 读过的卡不会被自动重新注入)。求解、删除、提交结论之前尤其要先补。

**三条自检**(细节在 `flow/s-parameters.md`):
1. 求解前 `get_object_bbox` 核对层叠搭接 —— 治"建歪"
2. analyze 前 `validate_design` —— 治"配置漏"(端口缺积分线、setup 没绑激励)
3. 跑通了但数不对,先 `get_messages` 读消息窗口 —— 解被作废、端口阻抗偏离、不收敛只写在那里

**数不对时按这个顺序查,网格排最后**:几何与搭接(bbox)→ 端口位置/积分线/激励幅相 → 材料、单位、变量实际值
→ 边界与辐射区 → setup 频率(Single 5GHz 回退)、扫频范围、取数取错 setup/sweep → 最后才是网格。
HFSS 默认自适应网格一般可靠:`analyze` 报 `converged: true` 且没有 `warnings` 就别怀疑它。
只有出现具体证据才查网格:没收敛;镜像/对称的口对不上;同参数重跑差很多;变量变一点结果非单调乱跳。

## ★ 卡住了怎么办(退出条件,到了就停)

- **COM 参数试 2 次不通 → 停**,让用户在 AEDT 里 `Tools → Record Script To File` 手工做一次,把官方调用录出来。别继续猜参数名。
- **同一个报错改 3 次还在 → 停**,报告现状 + 已排除的假设,让用户定方向。
- **调不动时按"轮数 + 未达标项有没有少"数,不按"方向对不对"判**("方向对、力度不够"是最贵的自我说服):
  - **一轮** = 改了设计变量之后的任何一次求解(单次 analyze、参扫、优化器、自己写脚本跑的都算)。
  - **每轮在回复里列出未达标项和当前数值**(`check_design_targets` 或任何等价的逐项对表都行)。
    匹配类指标(S11/VSWR 带内 ≤ 某值)不许只报最差点,每个频段还要报**反射环半径和环心阻抗**
    (`get_input_metrics(bands=...)` 的 `loop_check`):最差点会把"整段偏了"误读成"边频掉了"。
  - **连续两轮未达标项没少一项 → 停**,转 `flow/diagnose-current.md` 看机理,或用灵敏度(`flow/tuning.md`)查该动哪个变量。
- **诊断完按机理改过,再两轮仍没少项 → 停下来交给用户**:报各项现状、已排除的假设、可选方向(换拓扑/松指标/继续投机时由用户定)。
- **拿不准论文结构/标注 → 问用户**,别猜着建。

用户授权"自己调到达标、别打扰我"时,上面的退出条件**仍然优先**:授权免的是中途的小决定和逐轮汇报,
不是"方向走不通也别说"。

## 1. 会话与规划
- 启动时 HFSS 是关的,建模工具都会报"无 active design"。打开/启动 → `open_desktop`;连已开的 → `attach_desktop`;
  然后 `new_project` + `new_design`,或 `open_project(路径)`;切换用 `activate_project` / `activate_design`。
- **新任务先 `design_summary` 看全景**,确认 setup/端口/边界是否已存在,别重复创建。
- ≥3 步的复合任务动手前用宿主的待办机制(如 TodoWrite)列规划,写清最终交付和可量化指标;简单请求不用。
- `analyze` / `run_parametric_sweep` 等阻塞操作会弹权限确认:调用前先说清跑什么、为什么、预估耗时;用户拒绝就先说明再等回应。

## 2. 故障判定(别动核武器)
- 工具单次失败通常是参数错 → 报告错误、按提示改,**不要 reset、不要重建 design**。
- 只有 AEDT 本身没了(连续多个不同工具报 COM 断连/RPC 不可用,`list_projects` 也失败)才重新
  `open_desktop` / `attach_desktop`(会顺带清掉旧会话的缓存)。
- `new_design` / `delete_design` 除非用户明确要求,**永远别主动调**。

## 3. 通用约定
- 坐标/尺寸传**字符串**,带单位(`'10mm'`)或变量表达式(`'L1+1mm'`);对象名只用英文字母数字下划线。
- 复杂结构先 `set_variable` 再用变量名建几何;建错用 `delete_object` 删掉重建,不要堆叠。
- 材料用 HFSS 内置库(`'copper'`/`'FR4_epoxy'`/`'Vacuum'`);论文 εr/tanδ 和库里对不上就 `create_material` 按原值建。
- setup / 扫频 / 参扫都**不能同名覆盖**,建错先删再建;删除类工具都要 `confirm=true` 才真删,删 setup/扫频会连带删掉结果,删前先把要留的数取完。
- 磁盘吃紧用 `cleanup_solutions`(默认只删场、保留 S 参数)。**删场之后远场就取不到了**,先把远场取完再清。

## 4. 几何坐标 / 层叠约定(复现文献"建歪"的根因)
> 用户给的是板厂叠层表(xlsx/csv)→ 转 `hfss-stackup` skill。本节是自己编层叠时的约定。

文献只给尺寸,几乎从不给坐标。按固定约定建:
- **层叠先用变量定死**:`subH`(基板厚)、`PL`/`PW`(辐射体)、`gndL`/`gndW`(地板),几何全引用变量。
- **z 轴是层叠方向**:地板 sheet 在 **z=0**;基板 box 从 0 到 `subH`;辐射贴片 sheet 在 **z=subH**(不是 0);
  竖直馈电面 z 跨满 0→subH,同时搭到地和贴片。
- **xy**:辐射体居中,地板/基板盖住辐射体,三者共中心。
- 空气盒用 `create_open_region`(频率传工作频率),别手搭过小的空气盒。单位统一 mm。
- 复现前**先列一张层叠表**(对象/材料/z 范围/xy 范围)让用户确认,再动手。

## 5. 2D sheet → 导体
- `create_rectangle` / `create_polyline` / `create_circle` 建的是 sheet,本身不是导体;当导体用要 `assign_perfect_e`。
  **端口 sheet 不要赋 PE**。
- sheet 变实体用 `thicken`;规则长方体直接 `create_box`。
- 圆形件用 `create_circle` 画真圆,别用多边形逼近(会破坏旋转对称,CP/多臂结构轴比直接变差)。
- **切 sheet 用 `split`,不能用 solid 去 `subtract`**(会报错并把 sheet 一起删掉)。
