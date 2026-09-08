# 经验库索引(按天线类型)

这是 HFSS 天线建模的**经验沉淀**:每类天线一个文件,记非显然、可复用的难点/坑/解法。
开工时读匹配类型的文件 + `_general.md`;收工时把新坑追加进去(详见 SKILL.md §0.2)。
**本目录会随使用变厚——这是设计意图,不是杂物。**

## 跨类型通用
- [_general.md](_general.md) — 不限天线类型的通用经验(建模/馈电/求解/匹配的共性坑)
- [_optimization.md](_optimization.md) — 参扫/匹配/方向图优化的坑与方法论(开工要扫参/调匹配/优化时先读)

## 按天线类型
- [microstrip-patch.md](microstrip-patch.md) — 矩形微带贴片(边馈/inset/探针/CP 切角)
- [magneto-electric-dipole.md](magneto-electric-dipole.md) — 磁电偶极子(平面振子 + 折叠短路贴片 + 腔体反射板)

<!-- 新天线类型:新建 <type>.md,在此加一行指针 -->
