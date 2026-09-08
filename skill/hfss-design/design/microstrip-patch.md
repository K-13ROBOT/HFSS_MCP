---
topology: microstrip-patch
aliases: [patch, 贴片, 微带贴片, microstrip]
freq_ghz_min: 1
freq_ghz_max: 10
eps_r: any
feed: [inset-microstrip, coax-probe]
polarization: linear
s11_db: -11.7
bw_pct_min: 2
bw_pct_max: 5
gain_dbi_min: 5
gain_dbi_max: 7
source: 本人验证 + Balanis Ch.14
---

# 矩形微带贴片 设计卡片

> 一句话:最常见的平面单极化天线,窄带(~2–5%),易做、易匹配。给定中心频率 + 基板 → 闭式算出起手 W/L → 扫馈电位置调匹配。
> 关联经验:[../knowledge/microstrip-patch.md](../knowledge/microstrip-patch.md) ←建模/调试时配合读

## 适用范围
- **拓扑类别**:矩形贴片,边馈 / inset 馈 / 探针馈
- **已验证频段**:闭式公式无频率上限,常用 1–10 GHz
- **基板**:任意 εr / h(公式含进去了)
- **馈电方式**:50Ω 微带 inset(本卡主线)/ 同轴探针

## 设计公式 ★核心(服务任意 f₀ / εr,这就是 λ 缩放)
c = 3e8 m/s,f₀ = 中心频率。

1. **宽度** W = (c / 2f₀)·√(2/(εr+1))
2. **有效介电常数** εeff = (εr+1)/2 + (εr−1)/2 · [1 + 12h/W]^(−1/2)
3. **边缘延伸** ΔL = 0.412·h·(εeff+0.3)(W/h+0.264) / [(εeff−0.258)(W/h+0.8)]
4. **长度**(定谐振频率)L = c / (2f₀√εeff) − 2ΔL
5. **地板**:Lg ≥ L+6h、Wg ≥ W+6h(各边留 ≥3h 余量,太小会偏频/抬高后瓣)
6. **50Ω 馈线宽** w₅₀:解标准微带阻抗式;FR4(εr4.4/h1.6mm)≈ 3.0mm 可作起手

> 换频率:全部尺寸 ∝ 1/f₀(εr 不变时 W/λ₀、L/λ₀ 是常数)。换 εr 必须重算(εeff 变)。

## 起手 → 调匹配(解耦,别用尺寸凑两个目标)
- **控谐振频率** = L(L≈半波长/√εeff)。频偏了改 L,别动馈电。
- **控阻抗匹配** = inset 深度 y₀(或探针位置)。**不改 W/L**。
  - Rin(y₀) = Rin(0)·cos²(π y₀ / L);Rin(0) 是边缘输入阻抗(~150–300Ω,先仿真读出),解出 50Ω 对应 y₀。
  - 实操:把 `y0` 设成变量,`create_parametric_sweep` 扫 0→L/3,挑 S11 最低那点。详见关联经验"匹配靠扫馈电位置"。

## 报告性能(对标用 —— 本人验证基线)
| 指标 | 值 |
|---|---|
| 阻抗匹配 | S11 ≈ −11.7 dB / VSWR ≈ 1.7 / Zin ≈ 50Ω |
| 带宽 | 窄带,典型 −10dB 带宽 2–5% |
| 峰值增益 | 单片典型 5–7 dBi |

- **出处**:本人验证(探针贴片,整条 native 管线 2019.2 实测自洽);闭式公式据 Balanis《Antenna Theory》Ch.14。

## worked example(2.45 GHz / FR4 εr=4.4 / h=1.6mm)
代入上式:W ≈ **37.3 mm**,εeff ≈ 4.08,ΔL ≈ 0.74 mm,L ≈ **28.8 mm**;Lg ≈ 38.4、Wg ≈ 46.9 mm;w₅₀ ≈ 3.0 mm。
归一化(εr=4.4):W/λ₀ ≈ 0.305,L/λ₀ ≈ 0.236 —— 同基板换频率直接按此缩放。

## 建模配方要点
- 层叠 z 顺序固定:地 z=0 / 基板 0→h / 贴片 z=h(详见关联经验,建完 `get_object_bbox` 自检)。
- inset = 在贴片靠馈电边 `subtract` 两条对称槽 + 50Ω 线伸进 notch 到 y₀。
- 求解流程走 SKILL §6;先 L 对频率,再扫 y₀ 压 S11。
