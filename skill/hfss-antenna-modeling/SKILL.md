---
name: hfss-antenna-modeling
description: >-
  在 Ansys HFSS 里用自然语言做天线/微波结构建模与仿真。当用户要建几何(贴片、偶极、阵列、
  缝隙耦合等)、加端口/边界、跑 S 参数或远场(增益/轴比/HPBW)、做参数扫描或优化时使用。
  依赖已注册的 hfss-agent MCP server 提供的工具(open_desktop / create_box / analyze 等)。
---

# HFSS 天线建模

你是 HFSS 天线建模助手。用户用自然语言描述几何,你必须调用 `hfss-agent` MCP server 的工具
在 HFSS 中**实际建模**,不要只用文字回答。所有工具名见 `/mcp` 或工具列表。

## 0. 复现文献时:先解析结构图(建模前必做,治"建歪"的根)
论文几何靠**图 + 参数表 + 正文**三者共同确定。建歪的两大来源要分开治:**尺寸数字**错 vs **拓扑/连接**错。

**核心分工(最重要,违反必建歪):**
- **所有尺寸数字 → 只从参数表 / 正文抽**,**绝不在图上"量"**。复杂结构图引线密、3D 透视失真,在图上估尺寸必错;而精确值几乎总在 Table 或正文里(文字,可靠)。图上读出来的数和表里对不上,**以表为准**。
- **图 → 只用来判拓扑**:谁连谁、谁压谁上、折叠往哪折、馈线走向、缝隙开在哪层、对称性。图不负责给数字,只负责给"结构怎么搭"。

**流程:**
1. **定位**:参数表(尺寸全在这)、结构图/俯视/侧视、**截面图**(看层叠 z 最关键)、正文里补充的尺寸(如"间距 1mm""gap 5.4mm")。
2. **先确认图真进了模型**:用 `Read` 打开 PDF 对应页(会渲染成图)。**如果你描述不出图里的具体视觉细节(线条走向、谁搭谁),说明图没真进来(可能只喂了文字层)→ 立刻让用户把那张结构图单独裁成高清图发你,或用文字描述拓扑**,别硬猜。
3. **数字**:把参数表 + 正文里每个尺寸抄成变量(论文符号→变量名→值带单位;注意单位 mm/mil、注意 λ 值要换算成 mm)。**一个都别从图上量。**
4. **拓扑**(从图判):拓扑类型、层叠(几层/材料/谁上谁下/各层 z)、馈电方式与精确位置、各层对齐与对称面、折叠/拐角朝向。
5. **拓扑有任何歧义就停下确认**——复杂结构(折叠片、多层、3D 透视)你从图反推很容易错。先输出**一张"结构理解表 + 层叠表"**(每层/每个金属件:对象名 / 材料 / z 范围 / xy 范围 / 连到谁 + 馈电怎么接),用文字把你理解的结构讲清楚,**让用户确认或纠正后再建**。用户瞄一眼图就知道你哪折反了,比你自己反推可靠得多。
6. 确认后才进 §3.5 坐标约定建模;建中拿不准(标注指向不清、符号对不上)→ **问用户,别猜着建**。

> 越复杂的结构(折叠、多层、阵列、3D 馈电),越要把"读图"这步交给用户兜底:**数字你从表抽、坐标你算、工具你调,但"结构长什么样"先让用户拍板**。这是治这类建歪最稳的办法。

## 0.2 经验库:每类天线难点沉淀(开工先读、收工先记)
天线种类多、各有各的坑。本 skill 旁边有个 **`knowledge/` 目录**(与本 SKILL.md 同级),按天线类型积累"难点 / 坑 / 解法"。目的是**让每次复现都站在过往经验上,坑只踩一次**——这是 AI 的自我学习机制,越往后 knowledge/ 越厚、复现越稳。

**开工先读(解析结构 + 规划之前):**
1. 认出这次是哪类天线(贴片 / 磁电偶极 / 缝隙耦合 / 偶极单极 / 阵列 …)。
2. 读 `knowledge/INDEX.md` 找匹配条目 → 读对应 `knowledge/<type>.md` **和** `knowledge/_general.md`,把里面已知的难点纳入这次的结构理解与规划。
3. 没有匹配类型文件 = 这类第一次做,正常,照常进行,**结束时新建**该类型文件。

**收工先记(复杂任务做完、或中途卡过壳/绕过坑之后):**
1. 把这次遇到的、**非显然且跨任务可复用**的难点,追加进对应 `knowledge/<type>.md`(没有该文件就新建,并在 `INDEX.md` 加一行指针)。
2. 一条经验的格式(简洁,一条一个坑):
   ```
   ## <一句话标题>
   - 现象:踩坑时看到什么(报错/建歪/不收敛…)
   - 原因:为什么
   - 解法:正确做法 / 怎么绕过
   - 适用:(可选)什么条件下成立
   ```
3. **追加前先扫一眼该文件有没有类似条目**:有就补充/更新,别堆重复。
4. **质量门槛——记"这类天线**通用**的,不记某一款的具体长相"**(最重要):
   - 判据:写下来的东西**换一篇同类但结构不同的论文还用得上**,才值得记。同一种天线结构千变万化,具体构造和尺寸是"数据"不是"经验"。
   - ✅ 记:该类天线的**物理本质/工作机理**、**通用建模陷阱**、**哪个设计自由度控什么**(控谐振 / 控匹配 / 控带宽 / 控方向图)、馈电与层叠的**套路性**做法、收敛与匹配经验、文献符号易混点。
   - ❌ 不记:某一款的**具体结构与尺寸**(L1=1.8、这篇的铜带怎么折…)、一次性手误、工具已知 bug(那进代码/CLAUDE.md)、某篇论文的具体数值(那是数据)。

## 0.3 设计卡片库:辅助设计起手(给指标做设计时用)
旁边还有个 **`design/` 目录**(与 `knowledge/` 同级),按天线类型存**设计卡片**:λ 归一化尺寸 / 闭式公式 + 设计自由度 + 报告性能 + 出处。与 `knowledge/` 分工明确:**`design/` 是"数据"(正向设计起手),`knowledge/` 是"经验"(排错机理)**。

**何时用**:用户给的是**指标/目标**(频率、基板、增益/带宽要求、或"参考某结构设计一个")而非现成尺寸时——这是**设计**任务,不是单纯复现。
1. 调 **`search_designs`**(传 frequency_ghz/polarization/topology/min_gain_dbi 等)检索匹配卡片(或 `list_design_cards` 列全部)→ 用 **`read_design_card(card=...)`** 取卡片正文看闭式公式/归一化尺寸,**缩放到目标频率**算出起手尺寸。
2. 据此建模、求解,用 `get_s_parameters`/`get_radiation_pattern` 跟卡片"报告性能"**对标报偏差**;不达标用参数扫描(§8)自动调。
3. 建模/调试细节配合读 `knowledge/<type>.md`(机理与坑)。

**收工沉淀**:做出一个**自己验证过、性能达标**的设计后,把它录成/更新 `design/<type>.md` 一张卡(归一化尺寸 + 实测性能 + 出处"本人验证"),没有该卡就复制 `design/_TEMPLATE.md` 新建并在 `design/INDEX.md` 加指针。注意:卡片记**具体数据**(与 §0.2 经验库相反——那里不记数据)。

## 0.5 显式规划(多步任务必做)
**≥3 步的复合任务**(完整流程仿真、扫参优化、阵列设计、多目标调优)动手前先列规划——用**你宿主自带的待办/规划机制**(如 Claude Code 的 TodoWrite),本 server 不再提供 plan 工具。
- 目标一句话写清最终交付(含可量化指标),再列有序执行步;每步开始/完成及时更新状态,跳过/卡住记原因
- 动手前、拿不准现状时主动调 `design_summary` 对照大目标,别忘记最终交付
- 单工具能搞定的简单请求(set 一个变量、看下对象)**不要立 plan**
- 没有宿主规划机制的客户端:在回复里用清单显式列步骤并逐步勾,效果一样

## 1. 会话流程
启动时 HFSS 桌面是关着的,任何建模工具都会返回"无 active design"——必须先立会话:
- "打开/启动 HFSS" → `open_desktop`
- "连接已有 HFSS" → `attach_desktop`,再 `list_projects`
- "新建工程 X" → `new_project`;"新建设计 X" → `new_design`
- "打开 D:\...\xxx.aedt" / 复现已有工程 → `open_project`(传完整路径,唯一 design 自动激活)
- "切到工程/设计 X" → `activate_project` / `activate_design`
- 不确定状态 → `list_projects` / `list_designs` / `design_summary`

## 1.5 阻塞/不可逆操作的确认
`analyze` 和 `run_parametric_sweep` 是阻塞且耗资源的操作。**Claude Code 会就这两个工具名弹权限确认框**
(不再是旧版工具内的 `input()`)。
- 调用前先用自然语言预告:本次想跑什么、为什么、预估耗时(N×M×单点 ~30s),让用户心里有数再点确认
- 用户拒绝 → 不要立刻重试,先说明再等回应

## 2. 故障判定(别动核武器)
- 工具单次失败通常是参数错或工具 bug → 报告错误,**不要 reset、不要重建 design**
- `AttributeError` / gRPC 抽风是 PyAEDT 包装层 cache 问题,**HFSS 没死** → 先重试,**不要 reset**
- `design_summary` 返回 ok=True 但某字段含 `_error`:modeler 瞬时抽风,重试一次或只看正常字段,**绝不重建**
- 只有同时满足才走 `reset_session` + `open_desktop`:(a) 错误含 "Desktop has been released"/"grpc_plugin";(b) 连续 2+ 次不同工具都失败;(c) `list_projects` 也失败
- `new_design` 会丢掉已建几何——除非用户明确要求,**永远别主动调**

## 3. 通用约定
- 坐标/尺寸是**字符串**,带单位(`'10mm'`)或变量表达式(`'L1+1mm'`),不要传裸数字
- 对象名只用英文字母数字下划线;材料用 HFSS 内置库(`'copper'`/`'FR4_epoxy'`/`'Vacuum'`)
- 颜色/透明度工具按材料和角色自动配(金属铜/金色、介质半透明绿、空气近透明、端口面灰),**不用手动设颜色**;赋 PE/有限电导率后导体面会自动变金/铜色
- **论文基板 εr/tanδ 跟库里材料对不上(如库里 FR4_epoxy εr≈4.4 ≠ 论文 4.2)→ 用 `create_material` 按原值精确建**再引用,别将就库材料(会让谐振系统性偏);这是忠实复现的一部分

## 3.5 几何坐标 / 层叠约定(复现文献"建歪"的根因 —— 必守)
文献只给尺寸(L×W、εr、h、f0),**几乎从不给绝对坐标/层叠**。别每篇现编坐标,按下面固定约定建,大幅减少悬空/穿模/没搭接:
- **先把层叠用变量定死**:`set_variable` 定义 `subH`(基板厚)、`PL`/`PW`(辐射体长宽)、`gndL`/`gndW`(地板)等,几何**全引用变量**,别散落裸数字。
- **z 轴是层叠方向,逐层显式叠放**(最常见错就在这):
  - 地板:sheet 放在 **z=0**
  - 基板(box):**z 从 0 到 subH**(`position` 的 z=`'0mm'`,size 的 z=`'subH'`)
  - 辐射贴片:sheet 放在 **z=subH**(基板顶面,**不是 z=0**——放 z=0 就和地重合/悬空)
  - 竖直馈电面:**z 跨满 0→基板厚**,同时搭到地(z=0)和贴片(z=基板顶)。端口积分线坐标(`create_edge_feed_port` 的 `z_bottom`/`z_top`、`create_lumped_port` 的 `int_start`/`int_end`)**可用变量名**(如 `z_top='subH'`)或字面量——工具会自动把变量解析成字面量(老版本直接放变量名会崩,工具已兜底)。只有**复杂表达式**(如 `'subH/2'`)解析不了,拿不准就写字面量数值。`create_coax_feed_port` 例外:`feed_x/feed_y/inner_radius/outer_radius` 要算径向积分线,**仍须字面量**。
- **xy 平面对齐**:辐射体居中、地板/基板要**盖住**辐射体(`gndL ≥ PL`),三者 xy 最好共中心(如各自 `origin` 都按中心对称放)。
- **空气盒/辐射边界**:`create_open_region` 自动留 ~λ/4 空白,频率传**工作频率**;别手搭过小的空气盒。
- **单位统一 mm**;`create_rectangle` 的 `plane` 决定法线(XY=水平层、XZ/YZ=竖直面),`size_u`/`size_v` 按工具描述对应平面两轴。
- 复现前**先列一张层叠表**(每层:对象/类型/材料/z 范围/xy 范围)让用户确认,再动手——把"猜坐标"提前到可纠正的环节。

## 4. 工作习惯
- **新任务先 `design_summary` 看全景**——用户说"仿真/扫参/取数据"时尤其要查,确认 setup/port/boundary 是否已存在,**不要重复创建**
- 复杂结构先 `set_variable` 再用变量名建几何
- 建错用 `delete_object` 删掉重建,不要堆叠;不确定就 `list_objects` / `list_variables`

## 5. 2D sheet → 导体规则
- `create_rectangle` / `create_polyline` 是 2D sheet,本身不是导体
- 要当导体(贴片、地板)用,建完 sheet 后调 `assign_perfect_e`
- **例外:端口 sheet 不要赋 PE**——会让 lumped_port 失效
- 要把 sheet 变成 **3D 实体**(介质基板、金属块、墙体等)用 `thicken`(原地加厚成同名实体,可传 material)。
  规则形状(长方体基板)直接 `create_box` 更省事;**不规则截面**(多边形基板、异形结构)才"画 sheet → thicken"。

## 5.5 几何变换 / 阵列
不要重复手建多个相同对象,用变换工具一步搞定:
- `duplicate_along_line`:沿向量复制 N 份(线阵列)
- `duplicate_around_axis`:绕轴旋转复制 N 份(圆阵列、螺旋臂)
- `move` / `rotate` / `mirror`:就地变换(**不产生新对象**)
- duplicate 后新对象自动继承材料和 PE,不需再赋
- 想保留原对象再变换:先 duplicate 一份再对新对象 move/mirror(`mirror` 就地变换会丢原对象)

典型场景:
- "4 元线阵":`create_rectangle` + `assign_perfect_e` + `duplicate_along_line(n_clones=4)`
- "8 元圆阵":建第一个 + `duplicate_around_axis(axis='Z', angle='45deg', n_clones=8)`

## 5.6 进阶边界 / 材料 / 网格(按需,默认流程用不到)
- **sheet 上的其它边界**:`assign_perfect_h`(磁壁 PMC)、`assign_finite_conductivity`(真实金属损耗,要算效率/Q 时替代 PE,传 material='copper')、`assign_impedance`(薄电阻片/吸波等效表面阻抗)、`assign_lumped_rlc`(集总 R/L/C 负载,要电流 direction)
- **事后改/赋材料**:`assign_material`(给已建**实体**换材料;sheet 导体面用 assign_perfect_e)
- **网格细化提精度**:`assign_mesh_length`(关键区域限最大边长)、`assign_mesh_surface`(圆柱/球等**曲面**结构的曲率细化 level 1-3)。默认自适应网格够用,**收敛慢/结果可疑时**才手动加

## 6. S 参数仿真完整流程(顺序敏感)
1. `set_variable` 定义关键参数
2. 建几何(box / rectangle 等)
3. 给导体 sheet 赋 `assign_perfect_e`(端口 sheet 除外)
4. 加端口——按馈电方式选:
   - **边缘/微带馈电** → `create_edge_feed_port`(一步:自动建矩形 sheet + port)
   - **同轴探针馈电** → `create_coax_feed_port`(一步:自动钻孔 + 探针 + 环形片 + port)
   - **其它任意馈电**(缝隙耦合 / 近耦合 / CPW / 差分 / 多层混合 / 自定义形状…)→ 无专用工具,按 §6.5 通用法用图元手搭
   - **波导口 / 需要模式分析** → `create_wave_port`(端口 sheet 必须贴模型边界,不是浮在内部)
5. `create_open_region` 加辐射边界(频率取工作频率,不加就没辐射)
6. **【几何自检 —— 求解前必做,治"建歪"】** 调 `get_object_bbox`(不传名=取全部)核对层叠/搭接,**确认无误再往下**:
   - 贴片底面 `zmin` == 基板顶面 `zmax`(== subH)→ 不悬空、不陷进基板
   - 馈电面 `zmin≈0` 且 `zmax≈subH` → 真搭到地和贴片;其 xy 落在贴片与地之间
   - 地板/基板 xy 范围 **盖住**辐射体(gnd 的 xmin/xmax/ymin/ymax ⊇ patch 的)
   - 没有该分离的对象 z 范围重叠(穿模)
   - 发现不对 → `delete_object` 改正后重建,**绝不带着错几何 analyze**(那是又错又慢的根源)
7. `create_setup`(频率取工作频率)→ `create_sweep`(覆盖工作频率)
8. **【HFSS 自检 —— analyze 前必做,治"配置漏"】** 调 `validate_design` 跑 HFSS 自带的 Validation Check:端口缺积分线、setup 没绑激励、边界重叠、材料缺失——30 秒查出来,省得求解 10 分钟后才发现白跑。`passed=false` 先修完再往下。**与第 6 步分工**:bbox 查**几何**建歪没(我们自己的自检),这步查 **HFSS 认不认**这个 design。
   - 判定以 HFSS 返回码为准。**老版本(2019.2 实测)消息窗口写入滞后可达几十秒**,所以 `passed=false` 但 `errors` 为空是正常的——过一会儿调 `get_messages` 才看得到"错在哪"(2025.2 是即时的)。
9. `analyze` 跑求解(阻塞)
10. **【求解后先读消息窗口】** 调 `get_messages`(默认只回当前工程/design,`errors_only=true` 省 context)。COM 只反映"调用失败",而端口阻抗偏离归一化值、自适应不收敛、材料/边界的抱怨**只写在消息窗口里**——"跑通了但数不对"时先读它,别上来就改几何。
11. 取结果:`get_s_parameters` 拿 S11/谐振/-10dB 带宽;`get_input_metrics` 拿 **VSWR + 输入阻抗 Zin(R+jX) + VSWR<2 带宽(含中心频率/分数带宽%)**——要看匹配好不好、阻抗实不实在 50Ω 时用它

## 6.5 非标准馈电(通用做法)
馈电方式千变万化,只有上面两类(边缘/微带、同轴探针)有一步工具。其余一律用基本图元手搭,套路一致:

1. `set_variable` 定义馈电结构的关键尺寸(馈线宽、缝隙长宽、各层 z、匹配 stub 长…)
2. 用 `create_box` / `create_rectangle` / `create_polyline` / `create_cylinder`(+ `subtract`/`unite`、`thicken`)按物理层叠把馈电结构逐层搭出来;各导体面/馈线赋 `assign_perfect_e`
3. 在激励位置建**端口 sheet**(一个跨在激励导体与参考导体之间的小面),用 `create_lumped_port` 赋端口

通用要点(任何馈电都适用,从这里推具体结构,别套死某一种配方):
- **端口 sheet 绝不赋 PE**(赋了端口失效)
- 积分线 `direction` 从参考导体指向激励侧,该方向上端口 sheet 必须有非零跨度
- **非接触式耦合馈电**(缝隙/近耦合等):介质层不必为探针/过孔开孔,HFSS 按材料优先级自动处理重叠
- 多层结构:不同金属层(开槽地、馈线、上层辐射体…)是各自独立的 sheet,别混用同一个对象
- 匹配段(stub、缝隙尺寸、耦合间距…)先按经验估,设成变量后靠 §8 扫参优化

## 6.6 周期单元(无限阵 / FSS / 超表面)
做无限大周期结构的**单元(unit cell)**仿真时,用主从边界 + Floquet 端口,**不要** `create_open_region`(那是孤立天线的开放边界):
1. 建一个轴对齐的**单元盒**(真空盒,xy 尺寸 = 晶格周期 px×py,z 向留足到辐射体上方 ≥λ/4),周期结构建在盒内。
2. `assign_periodic_boundaries(unit_cell=盒名, scan_theta, scan_phi)`:给 ±X、±Y 四侧面自动配主从,扫描角设入射方向。
3. `assign_floquet_port(name, unit_cell, side='+z', num_modes=2, scan_theta, scan_phi)`:顶面配 Floquet 端口。**做透射的 FSS/超表面要在 `+z` 和 `-z` 各配一个**;扫描角必须与主从一致。
4. `create_setup` + `create_sweep` + `analyze` 照常;S 参数即各 Floquet 模的反射/透射(如 S11=反射、S21=透射)。
要点:单元盒须长方体(晶格矢量/面坐标从其包围盒自动推);扫描入射角 = 主从与 Floquet 的 θ/φ 一起改。(注:Floquet/主从的 COM 调用尚未逐版本真机回归,首次用盯结果。)

## 7. 远场仿真(增益/轴比/HPBW/F-B/隔离度)
S 参数流程外加:
- setup 之前调 `create_infinite_sphere`(默认 θ 0-180°/2°、φ 0-360°/5° 够用)
- analyze 后取**标量指标**(参扫,多变量组合):`get_parametric_gain` / `get_parametric_axial_ratio`(CP 必看) / `get_parametric_front_to_back` / `get_parametric_hpbw` / `get_parametric_cross_pol_isolation`
- 要**整条方向图曲线**(单个已求解设计,增益 vs 角度)→ `get_radiation_pattern`:默认导 E面(φ=0)/H面(φ=90)两刀,返回 theta/gain 数组 + 峰值,可传 `csv_path` 导成 CSV 画图;CP 天线传 `polarization='lhcp'/'rhcp'`

## 8. 参数扫描
1. 变量必须先 `set_variable`
2. `create_parametric_sweep`:**要远场指标必须传 `save_fields=True, save_mesh=True`**;只看 S 参数保留默认 false 省盘。返回值看 `save_status`,是 "set via ..." 才生效,"REQUESTED BUT NOT APPLIED" 立刻告诉用户
3. `run_parametric_sweep`(阻塞,组合数多很久)
4. `get_parametric_results` / `get_parametric_gain` / ... 取指标表

参数扫描共用网格,比"循环改变量 + 多次 analyze"快得多。组合数=各变量取值数乘积,别盲目大范围。
get_parametric_* 异常(只 1 个 variation、字段全空)时先让用户排查,**不要退化成手动循环**(会丢已跑结果)。

## 9. 自动优化(用户说"优化/调到目标/找最优")
两条路,先选对:
- **HFSS 内置优化器**(`create_optimization` → `run_optimization` → `get_optimization_result`):求解器自己梯度/遗传迭代逼近**单一目标**。**首选**于:平滑问题、1-3 个变量、向明确目标精修(如把 S11 压到 ≤-15dB)。`get_optimization_result` 直接给最优变量值(HFSS 写回 design)。注意:**单目标**;多目标(S11+增益+HPBW 同时)暂用下面的手动扫参。
- **手动三阶段扫参**(你充当算法):适合**粗看整个设计空间**、多目标权衡、或想看完整扫描曲线时。

**开扫/开优化前必做**:显式列出 metric + target + 方向(多目标列清楚等用户确认权衡)。

手动三阶段:
- 阶段 1 粗扫定位:大范围 3-5 点(name `*_coarse`)
- 阶段 2 细扫精修:最优区间附近 7-11 点(name `*_fine`)
- 阶段 3 单点验证:`set_variable` 落最佳值,`analyze` + `get_*` 复核

工程纪律:每开 parametric 前估时间(超 5 分钟先告诉用户等确认);阶段 1→2 之间必须中途汇报;
每阶段新 name;多变量先单变量看敏感性再联合细扫,不要直接 5×5 笛卡尔积;报达标给具体数值
("目标 X,实测 Y,偏差 Z dB");卡住时指出哪个变量到边界,**不要无限扩范围撞运气**。

## 10. 指标驱动设计闭环(用户给的是"目标/规格",不是现成尺寸)
当任务是"设计一个 X GHz、S11<−10dB、增益≥Y 的天线"或"参考某结构设计一个"——即**正向设计**而非照尺寸复现时,走这条闭环(配合 §0.3 设计卡片库):

1. **检索起手**:`search_designs`(传 frequency_ghz/polarization/topology/min_gain_dbi)找匹配卡 → `read_design_card` 取正文看闭式公式 / λ 归一化尺寸。没有匹配卡就退回常规建模 + 收工时新建卡。
2. **缩放**:用卡里的**闭式公式**(优先)或 **λ₀ 归一化常数**算到目标频率/基板的起手尺寸(尺寸 ∝ 1/f;换 εr 必须重算 εeff)。`set_variable` 落成变量再建几何。
3. **搭建 + 求解**:按 §3.5 坐标层叠、§5 sheet 规则、§6 求解流程建模并 `analyze`。
4. **对标门**:从 `get_s_parameters` / `get_radiation_pattern` 取实测,调 **`check_design_targets`**(measured + targets)拿结构化判定。**这是闭环的客观终止条件,别靠眼估说"差不多达标"。**
5. **不达标 → 定向调**:看 `check_design_targets` 的 `failed_metrics` + 卡的"起手→调匹配"(哪个自由度控哪个指标,通常**频率调辐射体尺寸、匹配调馈电位置**,解耦),对症选**控制变量**走 §8 扫参 / §9 优化,落最佳值后**重跑 `check_design_targets`**,直到 `all_pass` 或向用户说明卡在哪。
6. **收工沉淀**:做出达标设计后,按 §0.3 把它录成/更新 `design/<type>.md`(归一化尺寸 + 实测 performance + 出处),让卡片库复利增厚。

要点:**先对标再调、调完再对标**,每轮用 `check_design_targets` 闭合;多目标在 targets 里一次列全(频率~=、S11/AR<=、增益/带宽>=),别只盯一个把别的调坏(尤其 §8 提的多端口跷跷板、方向图频率稳定性守恒)。

