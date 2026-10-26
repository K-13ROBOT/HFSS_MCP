# 流程:S 参数仿真(驱动求解)

> 建几何 → 加端口边界 → 双自检 → 求解 → 取结果 的完整顺序。**顺序敏感**,跳步会白跑。
> 本征模求解不走这条(不要端口),见 [`eigenmode.md`](eigenmode.md)。
> **配套经验:[`../knowledge/_solving.md`](../knowledge/_solving.md)** —— 本卡讲步骤,
> 那边讲这些步骤会踩什么坑(setup 怎么组织、求解崩了怎么判、超时≠失败、
> 内存与 license 的硬限)。**要跑长求解、或结果可疑时必读。**

1. `set_variable` 定义关键参数
2. 建几何(box / rectangle 等)
3. 给导体 sheet 赋 `assign_perfect_e`(端口 sheet 除外)
4. 加端口——按馈电方式选:
   - **边缘/微带馈电** → `create_edge_feed_port`(一步:自动建矩形 sheet + port)
   - **同轴探针馈电** → `create_coax_feed_port`(一步:自动钻孔 + 探针 + 环形片 + port)
   - **其它任意馈电**(缝隙耦合 / 近耦合 / CPW / 差分 / 多层混合 / 自定义形状…)→ 无专用工具,按 `feeding.md` 通用法用图元手搭
   - **波导口 / 需要模式分析**(矩形/圆波导、SIW、要看高次模或 de-embed)→ `create_wave_port(name, sheet)`:**端口 sheet 必须贴模型外边界**,浮在求解域内部的要改用 `create_lumped_port`;单模只看 S 参数可不给积分线,要定阻抗归一化方向才传 `int_start`/`int_end`;看高次模加 `num_modes`
5. `create_open_region` 加辐射边界(频率取工作频率,不加就没辐射)
6. **【几何自检 —— 求解前必做,治"建歪"】** 调 `get_object_bbox`(不传名=取全部)核对层叠/搭接,**确认无误再往下**:
   - 贴片底面 `zmin` == 基板顶面 `zmax`(== subH)→ 不悬空、不陷进基板
   - 馈电面 `zmin≈0` 且 `zmax≈subH` → 真搭到地和贴片;其 xy 落在贴片与地之间
   - 地板/基板 xy 范围 **盖住**辐射体(gnd 的 xmin/xmax/ymin/ymax ⊇ patch 的)
   - 没有该分离的对象 z 范围重叠(穿模)
   - 发现不对 → `delete_object` 改正后重建,**绝不带着错几何 analyze**(那是又错又慢的根源)
7. **【建 setup 之前先往后看一步 —— 漏了就得整解重跑】**
   问自己:**这个设计后面要取远场吗?** 要的话现在就把前置条件办了,
   这两样都是"事后补 = 重新求解一遍":

   | 后面要做 | 现在必须先办 | 补办的代价 |
   |---|---|---|
   | 远场(增益/轴比/方向图)| **`create_infinite_sphere` 必须在 `create_setup` 之前建**;扫频要 `sweep_type='Discrete'` + `save_fields=True` | setup 建完再补球面,得重建 setup 重解 |
   | 轴比 vs 频率(`get_axial_ratio`)| 同远场,且扫频**必须** Discrete + save_fields(只设 `save_rad_fields` 不生效) | 整条扫频重解 |

   拿不准后面要不要 → **就当要**:无穷远球面不参与求解,零成本;事后补才贵。细节见 [`farfield.md`](farfield.md)。

   电流诊断**不用**提前办:采样线用 `create_polyline(non_model=True)` 画,求解后补画也不作废解
   (见 [`diagnose-current.md`](diagnose-current.md) 的铁律①)。

8. `create_setup`(频率取工作频率)→ `create_sweep`(覆盖工作频率)。
   **存场扫频(`save_fields=True`)要当耗材管**:每条扫频在之后**每次** analyze 里都会重算,存场频点每个要写完整三维场(实测 ~90-100 秒/点、几百 MB/点),堆几条下来单轮求解能从十几分钟涨到一两个小时。取场/取远场用完就 `delete_sweep(setup, names, confirm=True)` 清掉,只留调参真正要看的那条
   - **更稳的做法是按用途分 setup**:调参一个(只挂一条插值扫频、`save_fields=False`),取远场另一个(存场扫频只放要看的那几个频点)。`analyze(setup=...)` 只跑指定的那个,于是调参轮次始终是"最短的那条";远场 setup 只在尺寸定稿后跑一次。比"用完再删"少丢结果、也少一次重算
   - 代价要按**整轮**算,别只看扫频本身:几何一改,自适应网格要重做,setup 下**所有**扫频都跟着重算。所以拖慢的不是"多存了几个场",而是"每轮都重存一遍"
9. **【HFSS 自检 —— analyze 前必做,治"配置漏"】** 调 `validate_design` 跑 HFSS 自带的 Validation Check:端口缺积分线、setup 没绑激励、边界重叠、材料缺失——30 秒查出来,省得求解 10 分钟后才发现白跑。`passed=false` 先修完再往下。**与第 6 步分工**:bbox 查**几何**建歪没(我们自己的自检),这步查 **HFSS 认不认**这个 design。
   - 判定以 HFSS 返回码为准。**老版本(2019.2 实测)消息窗口写入滞后可达几十秒**,所以 `passed=false` 但 `errors` 为空是正常的——过一会儿调 `get_messages` 才看得到"错在哪"(2025.2 是即时的)。
10. `analyze` 跑求解(阻塞)
10.5 **【analyze 的返回值里带着收敛体检,看一眼】** `convergence` 字段,都是**当前这组设计变量**的:
   是否收敛、`passes_completed/passes_max`、末轮单元数、判据与末轮值、
   **`consec_passes_required/achieved`(要求/实际连续几遍满足)**、
   **`solution_freq` + `solution_freq_type`(自适应频率,单频还是多频)**、`reused_cached_solution`。
   `warnings` 只在确定出事时才有 —— 没收敛 / 根本没解 / **当前变量组合没有可用的解(解被作废)** ——
   **有就停,别往下取数**。频点不对(比如复制 design 后被静默重置成单频 5 GHz)只有这里能当场看见。
   **自己写脚本求解、没走 `analyze` 的,事后调 `get_convergence(setup)` 补查** —— 同样的检查,
   不补就等于工具层的检查对你全部失效。
11. **【求解后先读消息窗口】** 调 `get_messages`(默认只回当前工程/design,`errors_only=true` 省 context)。COM 只反映"调用失败",而端口阻抗偏离归一化值、自适应不收敛、材料/边界的抱怨**只写在消息窗口里**——"跑通了但数不对"时先读它,别上来就改几何。
12. 取结果:`get_s_parameters` 拿 S11/谐振/-10dB 带宽;`get_input_metrics` 拿 **VSWR + 输入阻抗 Zin(R+jX) + VSWR<2 带宽(含中心频率/分数带宽%)**——要看匹配好不好、阻抗实不实在 50Ω 时用它
13. **【只在需要时】指标不对且不知道为什么** → 进 `diagnose-current.md` 看电流分布,**别盲调**

## 这张卡做完去哪
- 要**增益/轴比/方向图** → `farfield.md`(多端口记得先设幅相)
- 指标**不达标** → `tuning.md`(先问该动哪个变量,再扫)
- 指标不对但**不知道为什么** → `diagnose-current.md`(看机理,别盲调)
- 达标了 → `capture-learning.md` 把经验和卡片沉淀下来
- 馈电结构没有现成一步工具 → `feeding.md`
