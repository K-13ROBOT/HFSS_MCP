# 流程:进阶几何(变换/阵列/边界/网格/螺旋/改已有对象)

> 按需读。默认建模只要 `SKILL.md` 的 sheet→导体规则就够。

## 几何变换 / 阵列
相同对象别手建多个,用变换工具:
- `duplicate_along_line`(线阵)、`duplicate_around_axis`(圆阵、多臂)
- `move` / `rotate` / `mirror` 是就地变换,不产生新对象;要保留原对象先 duplicate 再变换
- **复制出来的副本带材料、端口,但不带 PE**(2019.2 实测 PE 组仍只含源对象)——复制完对副本重新 `assign_perfect_e`。
  快速判据:阵中任挑一个复制单元看无源 S11,应与原单元相近

例:4 元线阵 = `create_rectangle` + `duplicate_along_line(n_clones=4)` + 对全部单元 `assign_perfect_e`。

## 改已有对象的参数
不想删了重建、或尺寸是写死在建模历史里的(多边形的点、布尔里被消耗的工具圆):
`get_object_history` 看历史 → `set_history_props` 改单项 / `replace_in_history` 把写死的值批量换成变量。
**变量表里找不到的旋钮,常常就藏在这里。**

## 进阶边界 / 材料 / 网格(默认流程用不到)
- sheet 的其它边界:`assign_perfect_h`(PMC)、`assign_finite_conductivity`(真实金属损耗,算效率/Q 时替代 PE)、
  `assign_impedance`(薄电阻片)、`assign_lumped_rlc`(集总 R/L/C)
- 给已建实体换材料:`assign_material`
- 网格细化:`assign_mesh_length`(关键区域限边长)、`assign_mesh_surface`(曲面逼近,推荐直接传 `normal_dev`)。
  默认自适应网格够用,窄缝/高 Q/收敛慢/结果可疑时才手动加

## 螺旋结构
沿圆柱面卷绕的结构一律用 `create_helix` 扫出来,不要用平面片拼(拼出来是圆柱的弦,相邻件对不上会悬空,也没法参数化)。
同一螺旋上 z 偏移的几条带各扫一次,边是重合的螺旋线,可以 `unite`。
旋向自检:扫完看 bbox 与预期对比,不对就换 `right_hand`。四臂螺旋的细节见 `knowledge/quadrifilar-helix.md`。
