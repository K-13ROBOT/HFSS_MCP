# 流程:指标驱动设计闭环(正向设计)

> 用户给的是**目标/规格**而非现成尺寸时走这条。照尺寸复现走 [reproduce-paper.md](reproduce-paper.md)。

1. **检索起手**:`search_designs`(frequency_ghz / polarization / topology / min_gain_dbi)→ `read_design_card` 看闭式公式 / λ 归一化尺寸。
   **没有匹配卡** → 转 `hfss-search` skill 查文献,拿到起手尺寸后回第 2 步;用户不想查文献就按常规建模。
2. **缩放**:用闭式公式(优先)或 λ₀ 归一化常数算到目标频率/基板(尺寸 ∝ 1/f;换 εr 必须重算 εeff),`set_variable` 落成变量。
3. **搭建 + 求解**:按 `SKILL.md` §4 坐标层叠、§5 sheet 规则和 `s-parameters.md` 建模求解。
4. **对标**:取实测,调 `check_design_targets`(measured + targets,多目标一次列全)。这是闭环的终止条件,别靠眼估。
5. **不达标 → 定向调**:按 `failed_metrics` 和卡里"哪个自由度控哪个指标"选控制变量,走 `tuning.md`,调完回第 4 步。
   - 选不出该动谁 → `tuning.md` 的灵敏度分析
   - 扫了一轮方向不对、或不知道结构为什么不工作 → `diagnose-current.md`
6. **达标后** → `capture-learning.md` 录卡片(用户确认要沉淀时)。
