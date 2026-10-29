# 流程:远场(增益/轴比/HPBW/前后比/隔离度)

> 在 [s-parameters.md](s-parameters.md) 的流程之上追加。

1. `create_infinite_sphere`(默认 θ 0-180°/2°、φ 0-360°/5° 够用)。需要已有辐射边界;
   求解之后再建也行,不用重解(2019.2 实测)。
2. **多端口天线先 `set_port_excitation` 设好各口幅相**:不设就是全部 1W/0deg 的同相馈电。
   双馈 CP 一口 90deg、差分 180deg、相控阵按扫描角给相位梯度。它是后处理权重,设完直接取,不用重解。
3. 取数:
   - 整条方向图(增益 vs 角度)→ `get_radiation_pattern`;CP 传 `polarization='lhcp'/'rhcp'`
   - 轴比 vs 频率 + 3dB 轴比带宽 → `get_axial_ratio`(需要存场离散扫频,见 s-parameters 第 6 步)
   - 参扫各组合的标量指标 → `get_parametric_gain` / `_axial_ratio` / `_front_to_back` / `_hpbw` / `_cross_pol_isolation`
   - 看自适应频点之外的频点:取那条存场离散扫频,用 `freq` 指定频点(必须是扫频里有的点)

**先确认自适应频率落在谐振上**:`LastAdaptive` 取的是 setup 频率那一点,谐振移走了 realized gain 会因失配塌掉
(见 `_solving.md`「取远场前先确认…」)。

## 这张卡做完去哪
- 方向图/轴比不达标 → `tuning.md`;调不动 → `diagnose-current.md`
- 远场取完、磁盘吃紧 → `cleanup_solutions`(清完场远场就取不到了,顺序别反)
- 达标了 → `capture-learning.md`
