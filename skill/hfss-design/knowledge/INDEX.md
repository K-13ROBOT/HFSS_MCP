# 经验库索引(按天线类型)

这是 HFSS 天线建模的**经验沉淀**:每类天线一个文件,记非显然、可复用的难点/坑/解法。
开工时读匹配类型的文件 + `_general.md`;收工时把新坑追加进去(详见 `flow/capture-learning.md`)。
**本目录会随使用变厚——这是设计意图,不是杂物。**

## 跨类型通用
- [_general.md](_general.md) — **建模本身**的共性坑:几何/布尔/端口/材料/复现文献、以及远场对标的读图陷阱(不限天线类型,开工必读)
- [_optimization.md](_optimization.md) — 参扫/匹配/方向图优化的坑与方法论(开工要扫参/调匹配/优化时先读)
- [_solving.md](_solving.md) — **求解与工程运维**:setup/扫频怎么组织(调参只留一个 setup!)、扫频类型选择、求解崩了怎么判、超时≠失败、会话挂掉的恢复流程、取数前查时间戳(要跑长求解、或求解莫名变慢/失败时先读)

## 按天线类型
- [microstrip-patch.md](microstrip-patch.md) — 矩形微带贴片(边馈/inset/探针/CP 切角)
- [magneto-electric-dipole.md](magneto-electric-dipole.md) — 磁电偶极子/互补天线(电偶极+短路 λ/4 贴片:双谐振分工、Γ 探针匹配、降高度代价、双极化机理)

- [vivaldi-tapered-slot.md](vivaldi-tapered-slot.md) - 渐变槽天线 Vivaldi/AVA/BAVA(行波"辐射完"判据、超宽带分带建模、t_eff 判据用法转变、渐变段长度由最低频定、AVA vs BAVA 选型)

- [quadrifilar-helix.md](quadrifilar-helix.md) — 四臂螺旋 QHA/PQHA(臂谐振长度族与多层排布铁律、做双频的四条路哪条通、相序决定旋向与方向图形态、方向图带宽只有 10%、真螺旋面建法与端头切平自检)。**尺寸/性能数据在 [`../design/quadrifilar-helix.md`](../design/quadrifilar-helix.md)**

- [phased-array.md](phased-array.md) — 相控阵扫描(孤立方向图+有源失配为何算不准、嵌入单元方向图/无限阵 cosθ(1−|Γ|²)、有源失配两种口径、扫描盲点估算、周期单元建模)

<!-- 新天线类型:新建 <type>.md,在此加一行指针 -->
