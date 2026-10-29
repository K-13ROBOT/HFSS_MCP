# 流程:周期单元(无限阵 / FSS / 超表面)

(扩展工具,经 `extra_tools(group='periodic')` 看参数、`extra_tools(tool=..., arguments={...})` 调用)

> 做无限大周期结构的**单元**仿真。注意**不要** `create_open_region`——
> 那是孤立天线的开放边界,周期单元用主从边界 + Floquet 端口。

做无限大周期结构的**单元(unit cell)**仿真时,用主从边界 + Floquet 端口,**不要** `create_open_region`(那是孤立天线的开放边界):
1. 建一个轴对齐的**单元盒**(真空盒,xy 尺寸 = 晶格周期 px×py,z 向留足到辐射体上方 ≥λ/4),周期结构建在盒内。
2. `assign_periodic_boundaries(unit_cell=盒名, scan_theta, scan_phi)`:给 ±X、±Y 四侧面自动配主从,扫描角设入射方向。
3. `assign_floquet_port(name, unit_cell, side='+z', num_modes=2, scan_theta, scan_phi)`:顶面配 Floquet 端口。**做透射的 FSS/超表面要在 `+z` 和 `-z` 各配一个**;扫描角必须与主从一致。
4. `create_setup` + `create_sweep` + `analyze` 照常;S 参数即各 Floquet 模的反射/透射(如 S11=反射、S21=透射)。
要点:单元盒须长方体(晶格矢量/面坐标从其包围盒自动推);扫描入射角 = 主从与 Floquet 的 θ/φ 一起改。(注:Floquet/主从的 COM 调用尚未逐版本真机回归,首次用盯结果。)
