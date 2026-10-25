# 流程:进阶几何(变换/阵列/边界/网格/螺旋)

> 按需读。默认建模流程只要 `SKILL.md` 的 sheet→导体规则就够,
> 下面这些是做阵列、改网格、建螺旋这类结构时才用到的。

不要重复手建多个相同对象,用变换工具一步搞定:
- `duplicate_along_line`:沿向量复制 N 份(线阵列)
- `duplicate_around_axis`:绕轴旋转复制 N 份(圆阵列、螺旋臂)
- `move` / `rotate` / `mirror`:就地变换(**不产生新对象**)
- duplicate 后新对象自动继承材料和 PE,不需再赋
- 想保留原对象再变换:先 duplicate 一份再对新对象 move/mirror(`mirror` 就地变换会丢原对象)

典型场景:
- "4 元线阵":`create_rectangle` + `assign_perfect_e` + `duplicate_along_line(n_clones=4)`
- "8 元圆阵":建第一个 + `duplicate_around_axis(axis='Z', angle='45deg', n_clones=8)`

- **sheet 上的其它边界**:`assign_perfect_h`(磁壁 PMC)、`assign_finite_conductivity`(真实金属损耗,要算效率/Q 时替代 PE,传 material='copper')、`assign_impedance`(薄电阻片/吸波等效表面阻抗)、`assign_lumped_rlc`(集总 R/L/C 负载,要电流方向线 `current_start`→`current_end`)
- **事后改/赋材料**:`assign_material`(给已建**实体**换材料;sheet 导体面用 assign_perfect_e)
- **网格细化提精度**:`assign_mesh_length`(关键区域限最大边长)、`assign_mesh_surface`(圆柱/螺旋/球等**曲面**的初始多边形逼近细化)。⚠️ **slider 的全局默认是 5、数字越大越细**——传 level=2 是在**变粗**,不是细化;**推荐直接传 `normal_dev`**(如 `'5deg'`,法向偏差,半径 R 的弦高≈R(1−cos(dev/2))),含义明确不易弄反。默认自适应网格够用,**窄缝/高 Q 模/收敛慢/结果可疑时**才手动加

**沿圆柱面卷绕的结构一律用 `create_helix` 扫出来,不要用 polyline 平面片拼** —— 拼出来的是圆柱的弦,
相邻部件边对不上会悬空,而且整体没法参数化。四臂螺旋、单臂螺旋、轴模螺旋、螺旋加载臂都适用。
(具体参数和轮廓怎么画见工具描述;四臂螺旋的方向余弦换算、端头切平、分数匝反解见
`knowledge/quadrifilar-helix.md`。)
- 同一螺旋上 z 偏移的多条带(主臂/缝/寄生臂)各扫一次:它们的边是**完全重合的螺旋线**,
  `unite` 成一张片即可,天然连通。
- 旋向自检:扫完看 bbox 的 y 范围与预期(右旋时顶端落在 φ 增大方向)对比,不对就换 `right_hand`。
