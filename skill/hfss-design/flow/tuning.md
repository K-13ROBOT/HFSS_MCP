# 流程:调参(网格校准 → 选旋钮 → 扫参 / 优化 → 公差)

> 指标不达标时怎么调。退出条件见 `SKILL.md`「卡住了怎么办」(按轮数和未达标项数,不按"方向对不对"判)。
> 配套经验:[`../knowledge/_optimization.md`](../knowledge/_optimization.md)(参扫 vs 手工、线性缩放律、仿真重复性)。

## 第零步:调参之前先做一次网格校准(不许跳)

调参的每一轮都建立在"当前网格算得准"上。拿当前设计(基准点)换一个明显更严的设置重解一次,比对关键指标。
校准本身是一次完整求解,先估时长。

- **另建一个校准 setup**(如 `Setup_cal`),不动基准 setup(`create_setup` 改不了已有 setup;删了重建会连基准解一起删掉)。
  `Setup_cal` 里:`max_delta_s` 降一档并加大 `max_passes`,**同时 `min_converged_passes=2`**
  (只降 ΔS 不要求连续两遍,网格粗时恰好一遍满足照样判收敛,等于没收紧)。
- 给 `Setup_cal` 也建一条同范围扫频(否则比不了频段边缘);之后取结果**显式传 `setup='Setup_cal'`**(不传默认取第一个)。
- 比**关键指标的偏移**(谐振频率、频段边缘、匹配深度),先确认更严的那次真的更严(单元数涨了、确实连续两遍)。
  - **偏移 < 1%** → 网格够用,用基准 setup 调参,`Setup_cal` 删掉免得误取
  - **偏移 ≥ 1%** → 当前网格下调出来的东西不可信,改用 `Setup_cal` 的判据调参
- `analyze` 返回 `converged: false` 时不用校准,先加大 `max_passes` 重解。

## 多谐振结构先看电流

**多谐振结构**(双频、宽带多模、寄生加载):第一次不达标就先去 `diagnose-current.md`,
在每个谐振点各取一次电流,搞清楚"谁负责哪个谐振"再选旋钮。一个尺寸常同时动好几个谐振,不知道谁管谁就扫,大概率动错旋钮。

## 选方法

| 情况 | 用什么 |
|---|---|
| 候选变量多、不知道谁重要 | **灵敏度分析**,把 `relative` 小的固定掉 |
| 只剩 1~2 个旋钮、只差定值 | **参扫** |
| 单一平滑目标、1~3 个变量 | **内置优化器** |
| 方向未知 | 先手工单点试探定方向,再用上面的定值 |

开扫/开优化前显式列出 metric + target + 方向(多目标列清楚等用户确认权衡);组合数多的先估耗时告诉用户。

### 灵敏度分析
`create_sensitivity` + `run_sensitivity` + `get_sensitivity_result`:工作点附近每个变量对指标的偏导,给排序和相对权重。
- `relative` 远小于 1 的变量扫了也是白扫,直接固定
- `verdict` 提示一家独大(只扫它)或两个量级相当(得二维扫或先固定其一)
- `nonlinearity` 大说明工作点附近非线性强,别线性外推估步长,缩小扫描范围

### 参扫
1. 变量先 `set_variable`;`create_parametric_sweep` 要远场指标传 `save_fields=True`
2. `run_parametric_sweep`(阻塞)→ `get_parametric_results`(S11)/ `get_parametric_farfield`(远场指标)
- 参扫共用网格,比循环改变量多次 analyze 快得多;多变量先单变量看敏感性,别直接 5×5 笛卡尔积
- 粗扫(3~5 点)定位 → 最优区间细扫(7~11 点)→ `set_variable` 落最佳值单点 `analyze` 复核
- 卡住时指出哪个变量到了边界,**别无限扩范围撞运气**
- **参扫按 ID 引用 setup**:删了 setup(哪怕同名重建)原参扫就接不上了(`run_parametric_sweep` 会报一组都没解),
  用 `delete_parametric` 清掉,连参扫一起重建

### 内置优化器
`create_optimization` → `run_optimization` → `get_optimization_result`:单一目标、平滑问题、1~3 个变量向明确目标精修。
只支持单目标,多目标同时调用参扫。

## 公差与良率(设计达标之后、投板之前)
`create_statistical` + `run_statistical` + `get_statistical_result`:给变量加公差分布做蒙特卡洛,给了 `spec_value` 直接算良率。
- 调参过程中不要做,设计还在变,算了也作废;对不达标的设计算良率没意义
- 板厂的 ±公差通常是 3σ:±0.3mm → `std_dev='0.1mm'`;加工公差用 `Gaussian`,估最坏情况用 `Uniform`
- **代价是 trials 次完整求解**,先预告耗时等用户确认;先 10~20 次看趋势,要可信的良率再上 50+
- 重点看 `spread` / `std_dev`:良率低时用灵敏度定位拖后腿的变量,要么卡紧那一项公差,要么改设计让它不敏感

## 这张卡做完去哪
- 达标 → `capture-learning.md` 录卡片;投板前回本卡做公差
- 到了退出条件 → `diagnose-current.md` 看机理;诊断完改了还不动 → 停下来交给用户
