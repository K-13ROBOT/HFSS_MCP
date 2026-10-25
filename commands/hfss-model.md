# HFSS 建模:把天线建出来并求解

读 `~/.claude/skills/hfss-design/SKILL.md` —— 常驻约定(坐标层叠、sheet 规则、故障判定、卡住了怎么办),
**然后按它的路由表判断这次属于哪种,去读对应的流程卡**:

- **开工第一件事**(任何天线任务) → `flow/capture-learning.md`
  ⚠️ 不读经验库 = 每次从零踩坑
- 照论文尺寸复现 → `flow/reproduce-paper.md`
  ⚠️ **尺寸只从参数表/正文抽,绝不在图上量**;拓扑有歧义先让用户确认
- 给的是**目标/规格**不是现成尺寸 → `flow/design-loop.md`
  ⚠️ 先对标再调、调完再对标,别靠眼估说"差不多达标"
- 跑 S 参数 / 完整求解一个设计 → `flow/s-parameters.md`
  ⚠️ **顺序敏感**;求解前 bbox + validate 两道自检不许跳
- 取远场(增益/轴比/HPBW/前后比) → `flow/farfield.md`
  ⚠️ **无穷远球面必须在 `create_setup` 之前建**(事后补要重解);**多端口必须先 `set_port_excitation` 设幅相**,否则算的是同相馈电
- 非标准馈电(缝隙/近耦合/CPW/差分/多层) → `flow/feeding.md`
  ⚠️ **端口 sheet 绝不赋 PE**;积分线方向上要有非零跨度
- 腔体/滤波器/DRA,要谐振频率与 Q → `flow/eigenmode.md`
  ⚠️ **design 必须建成 Eigenmode 类型**,不要端口;Q=0 是无耗不是出错
- 无限阵 / FSS / 超表面单元 → `flow/periodic.md`
  ⚠️ **不要 `create_open_region`**,那是孤立天线的边界
- 阵列复制、改网格、建螺旋 → `flow/geometry-advanced.md`
  ⚠️ **切 sheet 只能用 `split`**,solid 去 subtract 会把 sheet 一起删掉
- 板厂叠层表还原多层板 → 转 `hfss-stackup` skill
  ⚠️ 读错一条行业约定,整板厚度就错
- 要找文献 / 卡片库没有匹配拓扑 → 转 `hfss-search` skill
  ⚠️ 先查本地库,别一上来就联网

一个任务读 3~4 份是正常的。拿不准读哪张就先读路由表本身。

⚠️ **任务性质中途变了就回路由表重查**,别抱着一张卡走到黑。
最常见的转变:建完发现指标差得远 → 该转 `/hfss-tune`。

> 上面这份分支列表由 `make_commands.py` 从 `SKILL.md` 的路由表生成,别手改 ——
> 改路由表后重跑脚本即可。

---

用户的要求:

$ARGUMENTS
