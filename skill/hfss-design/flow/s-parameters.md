# 流程:S 参数仿真(驱动求解)

> 建几何 → 端口边界 → 双自检 → 求解 → 取结果。**顺序敏感**,跳步会白跑。
> 本征模不走这条,见 [`eigenmode.md`](eigenmode.md)。
> 配套经验:[`../knowledge/_solving.md`](../knowledge/_solving.md)(setup 怎么组织、结果可不可信、求解崩了怎么判),
> 要跑长求解或结果可疑时读。

1. `set_variable` 定义关键参数,建几何(按 `SKILL.md` §4 坐标约定)
2. 导体 sheet 赋 `assign_perfect_e`(端口 sheet 除外)
3. 加端口,按馈电方式选:
   - 边缘/微带馈电 → `create_edge_feed_port`
   - 同轴探针 → `create_coax_feed_port`
   - 波导口 / 要看高次模或 de-embed → `create_wave_port`(sheet 必须贴模型外边界)
   - 其它(缝隙耦合 / 近耦合 / CPW / 差分 / 多层)→ 按 [`feeding.md`](feeding.md) 用图元手搭 + `create_lumped_port`
4. `create_open_region` 加辐射边界(频率取工作频率)
5. **几何自检(求解前必做)**:`get_object_bbox`(不传名取全部)核对:
   - 贴片 `zmin` == 基板 `zmax`(不悬空、不陷进基板)
   - 馈电面 z 跨满 0→subH,真搭到地和贴片
   - 地板/基板的 xy 范围盖住辐射体;该分离的对象 z 范围不重叠
   - 不对就改正后重建,**绝不带着错几何 analyze**
6. `create_setup`(频率取工作频率)→ `create_sweep`(覆盖工作频带)。
   - **后面要看远场随频率变化(增益/轴比 vs 频率)**,扫频现在就建成 `sweep_type='Discrete', save_fields=True`,
     事后改扫频类型要重解。只看自适应频点的方向图不用管这条;无穷远球面求解后再建也行。
   - 调参期间一个 setup 只挂一条不存场的插值扫频;存场扫频单独放远场 setup、只建要看的频点
     (见 `_solving.md`「setup 分工」)。
7. **HFSS 自检(analyze 前必做)**:`validate_design`。`passed=false` 先修完。
   bbox 查几何建歪没,这步查 HFSS 认不认这个 design。2019.2 的消息窗口写入有延迟,`errors` 为空时过一会儿再 `get_messages`。
8. `analyze`。返回值里的 `convergence` 是当前这组变量的收敛体检;**有 `warnings` 就停,别往下取数**。
   不是用 `analyze` 求解的(自己写脚本),事后调 `get_convergence(setup)` 补查。
9. **读消息窗口**:`get_messages(errors_only=true)`。端口阻抗偏离、不收敛、解被作废只写在这里。
10. 取结果:`get_s_parameters`(S11/谐振/-10dB 带宽);`get_input_metrics`(VSWR、输入阻抗、阻抗带宽;
    传 `bands` 做反射环体检)。

## 这张卡做完去哪
- 要增益/轴比/方向图 → `farfield.md`
- 指标不达标 → `tuning.md`;不知道为什么不对 → `diagnose-current.md`
- 达标了 → `capture-learning.md`
