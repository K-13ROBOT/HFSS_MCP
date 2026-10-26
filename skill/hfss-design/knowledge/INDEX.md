# 经验库索引

**经验沉淀**:记非显然、可复用的难点/坑/解法。与隔壁两个目录的分工:
`flow/` 回答**怎么做**(步骤)、`design/` 存**可缩放的数据**(公式/归一化尺寸)、
本目录回答**会踩什么坑、为什么会砸、怎么判断**。本目录会随使用变厚——这是设计意图,不是杂物。
收工怎么往里记,见 [`../flow/capture-learning.md`](../flow/capture-learning.md)。

下面分**三组,触发条件不同**,别全量加载。

## 一、开工必读(不论什么天线、什么任务)
- [_general.md](_general.md) — **建模本身**的共性坑:零厚度 PE、材料精确建、几何操作失败后的核对、
  布尔限制、弱接触假谐振、坐标写死不联动、复现文献的读图陷阱

## 二、按任务阶段(只在做那件事时读)
> 这两篇是**按任务**切的,不是按天线类型 —— 和 `flow/` 同一个轴,但装的是坑不是步骤。
> 对应的流程卡分别是 `flow/tuning.md` 和 `flow/s-parameters.md`,**两边互补不重复**:
> 卡讲怎么做,这里讲做的时候会踩什么。

- [_optimization.md](_optimization.md) — **要扫参 / 调匹配 / 优化方向图时读**:
  参扫 vs 手工逐点怎么选、优化的判断陷阱、频率类旋钮的线性缩放律、匹配卡住时读输入阻抗、
  宽带双调谐看反射环环心、别去追小于"仿真重复性"的余量
- [_solving.md](_solving.md) — **要跑长求解、或求解莫名变慢/失败/结果可疑时读**:
  setup 怎么组织(**调参期间只留一个 setup**)、扫频类型选择、
  结果可不可信(欠收敛、改边界不重剖网格、镜像/对称自检、多频自适应)、
  网格与内存、求解崩了怎么判、超时≠失败、会话挂掉的恢复流程

## 三、按天线类型(认出是哪类就读哪篇)
- [microstrip-patch.md](microstrip-patch.md) — 矩形微带贴片(边馈/inset/探针/CP 切角)
- [magneto-electric-dipole.md](magneto-electric-dipole.md) — 磁电偶极子/互补天线(电偶极+短路 λ/4 贴片:双谐振分工、Γ 探针匹配、降高度代价、双极化机理)

- [vivaldi-tapered-slot.md](vivaldi-tapered-slot.md) - 渐变槽天线 Vivaldi/AVA/BAVA(行波"辐射完"判据、超宽带分带建模、t_eff 判据用法转变、渐变段长度由最低频定、AVA vs BAVA 选型)

- [quadrifilar-helix.md](quadrifilar-helix.md) — 四臂螺旋 QHA/PQHA(臂谐振长度族与多层排布铁律、做双频的四条路哪条通、相序决定旋向与方向图形态、方向图带宽只有 10%、真螺旋面建法与端头切平自检)。**尺寸/性能数据在 [`../design/quadrifilar-helix.md`](../design/quadrifilar-helix.md)**

- [phased-array.md](phased-array.md) — 相控阵扫描(孤立方向图+有源失配为何算不准、嵌入单元方向图/无限阵 cosθ(1−|Γ|²)、有源失配两种口径、扫描盲点估算、周期单元建模)

<!-- 新天线类型:新建 <type>.md,在此加一行指针 -->
