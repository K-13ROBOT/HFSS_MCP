# 通用经验(不限天线类型)

## 零厚度金属辐射体用 PE,不要 thicken
- 现象:把贴片/振子/地板 thicken 成实体,网格变重、求解变慢,且很多论文本就是 zero-thickness。
- 解法:辐射金属面一律 `create_rectangle`/`create_polyline` + `assign_perfect_e`(理想导体零厚度)。只有介质基板、金属块、探针这种真有体积的才用 box/cylinder/thicken。

## 边馈贴片单独不会匹配 50Ω
- 现象:贴片边缘直接馈电,S11 只有 -2~-3dB,根本不匹配。
- 原因:贴片边缘输入阻抗 ~200-300Ω,远离 50Ω。
- 解法:用 inset 馈电(把馈线缩进贴片,深度调阻抗)、λ/4 阻抗变换段、或探针偏置到 50Ω 点。匹配靠把馈电位置设成变量后扫参找最优(`create_parametric_sweep` + `get_parametric_results`)。

## 论文基板 εr/tanδ 跟库里对不上 → 用 create_material 精确建,别将就
- 现象:复现后谐振频率系统性偏几个百分点。
- 原因:HFSS 库里现成材料(如 `FR4_epoxy` εr≈4.4)常和论文标的(如 εr=4.2)不等;εr 越高谐振越低,Δf/f≈−Δεr/(2εr)。
- 解法:论文给了 εr/tanδ 就用 `create_material` 按原值精确建(再 `material='该名'` 引用),别用近似的库材料。这是"忠实复现"的一部分,不算改尺寸。

## 端口积分线坐标可用变量名
- 现象:旧认知里端口坐标必须字面量,变量会崩。
- 解法:`create_edge_feed_port`/`create_lumped_port` 现在内部会把变量名解析成字面量,可直接传 `'subH'`。但**复杂表达式**(如 `'subH/2'`)解析不了,拿不准写字面量。`create_coax_feed_port` 例外:feed_x/y/radius 仍须字面量。
- 补充:**取负的裸变量也算复杂表达式**(如 `feed_y='-Lf'`)——会在 AssignLumpedPort 阶段崩(`com_error 发生意外`),用字面量(`'-4.8mm'`)。

## 端口创建半途失败会留孤儿 sheet,要清
- 现象:`create_edge_feed_port` 报 AssignLumpedPort 失败,但 sheet 已经建出来了;重试又建一个,`design_summary` 里出现 `P1_sheet` + `P1_sheet_1` 两个同位置 sheet,只有一个挂着端口。
- 解法:别凭名字顺序猜哪个是孤儿(实测端口可能挂在先建的那个上)。把两个 sheet 都 `delete_object` 删掉,再干净地 `create_edge_feed_port` 重建一次;删后 `design_summary` 看 excitations 确认端口在。

## 建几何工具返回的 name 是"请求名",不是 HFSS 实际用的名
- 现象:上一步操作崩溃后重建同名对象,`create_polyline` 全部返回 `ok:true, name:"ARMB_M00"`,
  但接着 `unite` 这批名字却报 `com_error 发生意外`。`list_objects` 一看,实际对象全叫 `ARMB_M00_1`。
- 原因:崩溃残留让原名仍被占用,HFSS 自动追加 `_1` 改名;而工具回显的是**我传进去的名字**,不是 HFSS 落盘的名字。
- 解法:**任何一次操作失败/崩溃之后,重建对象前先 `list_objects` 核对实际名字**,别拿返回值当真。
  批量建几何时尤其要查——32 个对象全错名,后面每一步都连锁失败。

## 崩溃残留的边界会引用 null body,validate 报错且删不掉
- 现象:几何操作崩溃后,`design_summary` 里几何和边界看着都齐,但 `validate_design` 报
  `Null body found for part XXX`;`delete_object(['XXX'])` 返回 `missing`(工具的对象列表里根本没有它)。
- 原因:崩溃前已把 PE 赋给了那个对象,对象被回滚删除、**边界还挂着**,于是边界指向一个空 body。
  它不在对象列表里,现有工具够不着。
- 解法:工具集没有删边界的手段 → **在同工程里 `new_design` 换个名字从头重建**(几何脚本化后重建很快),
  别跟残留较劲。重建时顺手把边界名也换掉:**`assign_perfect_e` 用已存在的边界名会直接 COM 报错**,
  这也是判断"是不是名字被占"的快速判据。

## 求解进行中绝不要发任何建模调用——会把正在跑的 analyze 一起打挂
- 现象:`analyze` 在后台跑,期间调了一次 `new_design`。该调用自己阻塞转后台,55 分钟后
  **analyze 返回 `com_error 发生意外` 失败**,整轮求解白跑。
- 原因:HFSS 的 COM 是串行的。求解期间的建模调用不只是排队,还可能打断求解器状态。
- 解法:**求解期间只做不碰 HFSS 的事**(本地算坐标、写文档、读论文)。要建对照模型,
  等当前 analyze 的完成通知到了再动手。
- 补充:曾怀疑"求解期间并行发只读调用(bbox)也会打挂 analyze",但那次消息窗口的真实报错是求解子进程起不来
  (见下一条),**因果未证实**。稳妥做法仍是求解期间不发任何 COM 调用,但别把这当成已验证的结论。
## 几何操作失败会静默删掉 blank/结果对象,且留下删不掉的 null body
- 现象:`unite` 或 `subtract` 报 `com_error`(甚至**报 ok**),之后 `list_objects` 里结果对象凭空消失;
  再 `validate_design` 就报 `Null body found for part XXX`。
- 排查:**`unite` 返回 ok 不等于成功**。合并后立刻 `get_object_bbox` 查一下——
  bbox 全 0 或对象不在 `list_objects` 里,就是失败了。这是最快的判据。
- null body 清不掉:`delete_object` 说 missing;建同名对象想顶替也不行(HFSS 会自动改名成 `XXX_1`,
  原名仍被占)。**没有工具能清除它**。
- 它是**致命的**:带着 null body 跑 `analyze`,4 秒就 `com_error` 失败(不是警告)。
  好处是失败极快,所以"先试跑一次"比立刻重建划算——代价只有几秒。
- 解法:只能 `new_design` 换个名字重建。所以**几何脚本化**(坐标由脚本生成、分批贴)很值得,
  重建一遍才十几次调用。

## sheet 不能用 solid 去 subtract
- 现象:想用 box 把 sheet 切掉一截,`subtract(blank=sheet, tools=[box])` 报 `com_error`,
  并把 blank 的 sheet 一起删了。
- 原因:布尔要求 blank 和 tool 同类型(sheet-sheet / solid-solid)。
- 解法:要按某个平面裁剪分段建出来的 sheet,**在生成坐标时直接把顶点钳制到该平面**。
  分段法每段的点都落在两条竖直线上,只改 z 不破坏共面性,钳制后端头自然成为水平边。
  钳制后若某段两个端点重合,要**去掉重复点**按三角形(3 点)提交,否则覆面会出问题。

## 取远场前先确认 setup 的自适应频率落在谐振点上,否则 realized gain 是失配假象
- 现象:同一个天线,改了介质加载后重跑,`get_radiation_pattern` 的峰值增益从 +4.0 dBi 掉到 **−5.6 dBi**,
  方向图也不再是预期形状(峰值跑偏、单调下降)。看着像天线被改坏了。
- 原因:`get_radiation_pattern` 默认取 `LastAdaptive`,即 **setup 的自适应频率那一点**。
  几何/材料一改,谐振点跟着移动,原来设的自适应频率可能落到了谐振之外——
  **双频天线尤其危险,两个谐振之间就是失配峰**。realized gain 含失配损耗,自然塌掉。
- 判据:把 `get_s_parameters` 返回的各谐振 `-10dB` 区间和 setup 频率对一下,
  setup 频率不在任何一个区间内,远场就不能用。
- 解法:**为每个要考察的谐振点新建一个 setup**(频率设在该谐振上)再 analyze,用它的 LastAdaptive 取远场。
  顺手在该 setup 上挂一条 `Discrete + save_fields` 的扫频,一次求解同时拿到方向图和轴比曲线,省一轮。
- 引申:realized gain 天生含失配。要看天线本身的方向性,别在失配频点上比较增益。

## 两个"对象还没有就建不了"的顺序依赖:扫频要等端口,远场球要等辐射边界
- 现象:`create_sweep` 报 `InsertFrequencySweep com_error 发生意外`;`create_infinite_sphere` 报 `InsertFarFieldSphereSetup com_error`。
- 原因:设计里还没有任何端口/激励时插扫频会失败;还没有 `create_open_region`(辐射边界)时插远场球会失败。
- 解法:按 端口 → 扫频、`create_open_region` → 远场球 的顺序建;setup 本身可以早建。失败后补齐前置再重试即可,无副作用。

## analyze 返回 com_error 时先读消息窗口:可能是求解器子进程起不来(hf3d / MPI)
- 现象:`analyze` 跑了很久后返回 `com_error 发生意外`;消息窗口里是 `Unable to create child process: hf3d`、
  `The attempted launch of solvers via MPI failed while connecting to communication pipes`、`The HFSS solver failed to start`,
  常伴随 `Interpolating frequency sweep did NOT converge`(插值扫频阶段要反复拉起求解进程,最容易撞上)。
- 判据:这是**求解进程启动失败**,不是模型/几何错误,也不一定是并发 COM 调用引起的——别急着改模型。
- 补充(实测):同一 design 里反复出现(11:25、14:42 两次),资源充足(RAM 9GB 空闲、磁盘几十 GB)。
  第二次 analyze 仍返回 ok、151 点数据完整,但耗时从 ~500s 拖到 ~2600s——**报错不一定让结果失效,
  先看数据是否完整平滑,再决定要不要重跑**。
- 排查:先看内存与磁盘余量;工程里开了很多 design、跑过大量求解时资源压力大。偶发的可直接重跑一次;
  反复出现就存盘后重启 AEDT(`open_desktop` 重开),或减少扫频点数/改 Discrete 少点扫频降低进程启动次数。

## 设计变量名不要用单字母 `R`(实测 HFSS 2025.2)
- `set_variable(name="R", ...)` 报 com_error "发生意外"(-2147024382),同一 design 里 `P`、`Htop`、`wm` 都能正常建。
- 推断 `R` 与 HFSS 内部保留名/单位符号冲突。半径类变量改用 `Rh`、`r0` 这类名字。
- **`Pi` 同样建不了**(2026-09-16 实测,报一模一样的 com_error):`pi` 是表达式里的圆周率常量。螺距类变量用 `Pit`、`P`、`Pch`。
- 规律:单字母或与内置常量/单位同名的变量名都要避开;报错信息只有"发生意外",不会告诉你是名字冲突。
