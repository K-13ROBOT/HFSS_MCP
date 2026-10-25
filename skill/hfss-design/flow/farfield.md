# 流程:远场(增益/轴比/HPBW/前后比/隔离度)

> 在 [s-parameters.md](s-parameters.md) 的流程之上追加。**多端口天线取远场前
> 必须先设各口幅相**,否则算出来的是同相馈电的结果,不是实际的。

S 参数流程外加:
- setup 之前调 `create_infinite_sphere`(默认 θ 0-180°/2°、φ 0-360°/5° 够用)
- analyze 后取**标量指标**(参扫,多变量组合):`get_parametric_gain` / `get_parametric_axial_ratio`(CP 必看) / `get_parametric_front_to_back` / `get_parametric_hpbw` / `get_parametric_cross_pol_isolation`
- **多端口天线取远场之前,先用 `set_port_excitation` 设好各口幅相** —— 不设的话默认全部 1W/0deg,
  算出来的是**同相馈电**的结果,不是实际的。双馈 CP(正交双探针 + 90° 电桥)要把一个口设 90deg、
  差分馈电 180deg、相控阵按扫描角给相位梯度。
  ⚠️ **全量替换语义**:没在 `sources` 里列出的端口会被补成 1W/0deg,别只列要改的那个。
  改的是后处理叠加权重不是求解本身,所以**设完直接取远场,不需要重新 analyze**(零成本)。
- 单个已求解设计(非参扫)直接取 **轴比 vs 频率 + 3dB AR 带宽** → `get_axial_ratio`(默认 boresight θ=0/φ=0)。CP 天线 analyze 完先用它,不必为看一个 AR 去建参扫。
  **前提**:扫频必须建成 `create_sweep(..., sweep_type='Discrete', save_fields=True)`——实测 2025.2 上只设 `save_rad_fields` 不生效(远场报告报 com_error)。要取 AR 就在建 sweep 时一并设好,别等 analyze 完再发现白跑
- 要**整条方向图曲线**(单个已求解设计,增益 vs 角度)→ `get_radiation_pattern`:默认导 E面(φ=0)/H面(φ=90)两刀,返回 theta/gain 数组 + 峰值(CSV 自动落在 exports/,无需传路径);CP 天线传 `polarization='lhcp'/'rhcp'`。
  对多频点的存场扫频(`Discrete + save_fields=True`)一次取全部频点:每刀给 `by_freq`,另有 `boresight_gain_dB` 汇总轴向增益 vs 频率;
  只要一个频点就传 `freq='38.5GHz'`。⚠️ theta 只扫 0–180°,所以 φ=0 那刀只覆盖 +x 半边,另一半在 φ=180,要完整切面就把 180deg 也加进 `phi_cuts`

## 这张卡做完去哪
- 方向图/轴比**不达标** → `tuning.md`;调不动 → `diagnose-current.md`
- 远场取完、磁盘吃紧 → 可以 `cleanup_solutions` 清场了(**顺序别反:清完场远场就取不到了**)
- 达标了 → `capture-learning.md` 沉淀
