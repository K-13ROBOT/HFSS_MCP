# 设计卡片库索引(辅助设计 / 正向设计)

**用途**:从指标出发**设计**天线(给频率/基板/性能目标 → 起手尺寸 → 仿真对标),而不是排错。
每类天线一张卡:λ 归一化尺寸 / 闭式公式 + 设计自由度 + 报告性能 + 出处。

**检索**:用 MCP 工具 `search_designs`(按频率/极化/拓扑/增益过滤)或 `list_design_cards`(列全部);返回里带 `card` 名,用 `read_design_card` 取正文看公式细节(走 MCP,不依赖客户端的文件读取能力)。卡顶部的 frontmatter 就是这俩工具的检索字段。

与 `../knowledge/` 的分工:
- **`design/`(本目录)= 数据**:具体尺寸、归一化常数、报告性能、文献出处 —— 服务正向设计。
- **`knowledge/` = 经验**:通用机理、建模陷阱、哪个自由度控什么 —— 服务排错。
- 两者互补:**设计时读 `design/<type>.md` 起手,建模/调试时配合读 `knowledge/<type>.md`。**

新建卡:复制 [`_TEMPLATE.md`](_TEMPLATE.md) 成 `<type>.md`,在下面加一行指针。
**先沉淀自己验证过的设计,再逐步收录文献。**

## 卡片
- [microstrip-patch.md](microstrip-patch.md) — 矩形微带贴片(闭式 W/L + inset 调匹配,任意 f₀/εr)

<!-- 新拓扑:复制 _TEMPLATE.md → <type>.md,在此加一行指针 -->
