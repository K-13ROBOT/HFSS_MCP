# HFSS 建模:把天线建出来并求解

读 `~/.claude/skills/hfss-design/SKILL.md` —— 常驻约定(坐标层叠、sheet 规则、故障判定、卡住了怎么办),
**然后按它的路由表判断这次属于哪种,去读对应的流程卡**:

- 照论文尺寸复现 → `flow/reproduce-paper.md`(先解析结构图,治"建歪")
- 给的是指标不是尺寸 → `flow/design-loop.md`(正向设计闭环)
- 要跑 S 参数 / 完整求解 → `flow/s-parameters.md`(**顺序敏感,跳步会白跑**)
- 非标准馈电(缝隙/近耦合/CPW/差分/多层)→ `flow/feeding.md`
- 要远场(增益/轴比/HPBW)→ `flow/farfield.md`
- 腔体/滤波器/DRA 要谐振频率与 Q → `flow/eigenmode.md`(不要端口)
- 无限阵 / FSS / 超表面单元 → `flow/periodic.md`
- 阵列复制、改网格、建螺旋 → `flow/geometry-advanced.md`
- 板厂叠层表还原多层板 → 转 `hfss-stackup` skill

**开工先读 `flow/capture-learning.md`**(经验库 + 卡片库),站在过往经验上;
**收工回去记**——这是整套东西复利增长的机制,跳过它每次都从零踩坑。

一个任务读 3~4 份是正常的。拿不准读哪张就先读路由表。

---

用户的要求:

$ARGUMENTS
