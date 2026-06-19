# 竞品横向对比分析（2026-06-19）

调研对象：GitHub 上 star 最高的 9 个 worldcup-predictor / world-cup-2026 项目
调研目的：博采众长，找出最佳实践，并指导本项目向「让球盘 / 大小球量化下注」方向演进

---

## 一、综合评分汇总

| 项目 | 核心模型 | 输出 λ | 市场集成 | 走前回测 | AH/OU 支持 | 下注价值 |
|---|---|---|---|---|---|---|
| **rrclaw（本项目）** | Dixon-Coles MLE + 市场锚定 | ✅ | ✅ Polymarket+Kalshi(0.60) | ✅ 26 轮 | ❌ 仅差最后一步 | **架构最强** |
| lbenz730 | 贝叶斯双变量泊松（Stan MCMC） | ✅ 原生 | ❌ | ❌ 无数值披露 | ❌ 需二开 | 2/5 |
| hjjbh1314 | Elo + Logit + Platt 校准 | ❌ | ❌ 抓取未集成 | ✅ RPS=0.1707 | ❌ | 2/5 |
| Hicruben | Elo + DC 低分修正 + MC | ✅ 简化公式 | ❌ | ✅ RPS=0.175 | ❌ | 2/5 |
| dexorynlabs | Elo + 独立泊松 + 贝叶斯点球 | ✅ 线性公式 | ❌ 仅冠军赔率 devig | ❌ | ❌ | 2/5 |
| goaliqlab | Elo + XGBoost 分类 | ❌ 启发式 | ❌ | ❌ 仅交叉验证 | ❌ | 1.5/5 |
| javierruanohdez | GBM 分类 + FIFA 积分 | ❌ | ❌ | ❌ 平局 F1=7% | ❌ | 1/5 |
| EhteshamBahoo | 随机森林回归 | ❌ | ❌ | ❌ | ❌ | 1/5 |
| Currybon30 | 泊松回归 + Ridge + MC | ✅ 有 λ | ❌ | ❌ | ❌ 需二开 | 2/5 |

**结论**：本项目在「走前回测验证 + 市场集成深度 + 真实 λ 输出」三个维度同时占优；其他 8 个项目均无法做到三者兼具。

---

## 二、值得借鉴的独特方法

### 2.1 hjjbh1314 — 洲际强度修正（Confederation Gap）
- 数值：UEFA +117 / CONMEBOL +95 / CONCACAF -45 / AFC -120 / CAF -171（Elo 分）
- 验证：跨洲赛事（如 WC 小组赛）准确率提升 1.5%
- **可移植性：高**。本项目在 `skill/model/context.py` 增加 confederation gap 调整即可

### 2.2 dexorynlabs — 贝叶斯点球大战模型
- 数据：103 条历史点球大战记录
- 改进：用历史先验代替随机 50/50，强弱队点球差异约 ±8%
- **可移植性：中**。修改 `skill/sim/montecarlo.py` 中的点球分支即可

### 2.3 lbenz730 — 贝叶斯不确定性量化（Stan MCMC）
- 提供后验置信区间，可识别"高不确定性"比赛（不下注）
- **可移植性：低**。代价大，本项目 MLE+市场集成已基本平替

### 2.4 Currybon30 — 附属市场（角球 / 红牌）
- 同时预测角球数、红牌数
- **可移植性：可选**。本项目以让球+大小球为优先

---

## 三、被验证无效或低价值的方法（避免重复试错）

- **goaliqlab / javierruanohdez 的 ML 分类路线**：放弃 λ，丢失进球分布信息，平局 F1 极低（7%）
- **lbenz730 的纯统计无市场锚定**：无 Polymarket/Pinnacle 比对，Argentina 类强队系统性高估
- **EhteshamBahoo 的随机森林回归预测进球数**：无概率分布，无校准

---

## 四、让球盘 / 大小球（Asian Handicap / Over-Under）行业最佳实践

### 4.1 数学框架

- 让球盘核心：在双变量泊松的得分矩阵 `P(X=i, Y=j)` 上做条件累加
  - 半球线（±0.5）：直接累加 `i - j > h` 的格点
  - 整球线（±1.0）：需单独处理 push（退注）
  - 四分线（±0.25）：拆为两个半仓平均
- 大小球：对边际 `X+Y` 做累加
- Skellam 分布：净胜球 D = X − Y ~ Skellam(λh, λa)，用于让球盘快速定价

### 4.2 关键开源参考

| 项目 | 价值 | 链接 |
|---|---|---|
| **martineastwood/penaltyblog** | Python 足球量化库，原生支持 AH + OU + DC + 双变量泊松 | github.com/martineastwood/penaltyblog |
| **opisthokonta/goalmodel** | R 语言，支持用 xG 替换实际进球作为 λ 输入 | github.com/opisthokonta/goalmodel |
| Constantinou (2022) arXiv 2003.09384 | 第一篇专攻亚盘市场效率的学术论文 | arxiv.org/pdf/2003.09384 |

### 4.3 为何 Dixon-Coles 直接可用，而 Elo 不行
- DC：原生输出进球联合分布 → 任何基于进球的市场（AH / OU / 比分 / BTTS）都能精确算
- Elo：只能输出 1X2 三元组，反推 λ 需额外假设，引入误差
- **本项目已具备 DC 框架，离让球盘只差两个累加函数（约 50 行代码）**

---

## 五、最终采纳清单

### 5.1 立即采纳（与本项目架构高度契合）
1. **让球盘 + 大小球计算函数**（基于现有 `scoreline_matrix`）
2. **Pinnacle 亚盘赔率接入**（已有 `ODDS_API_KEY` 接口）
3. **凯利公式下注金额计算**（量化投资标准做法）
4. **洲际强度修正**（hjjbh1314 验证有效）
5. **贝叶斯点球大战模型**（dexorynlabs 思路）

### 5.2 待评估
- xG 替代实际进球作为 DC 输入（需评估 xG 数据源覆盖度）
- 角球 / 红牌附属市场（Currybon30 思路，优先级低）

### 5.3 拒绝
- 纯 ML 分类（goaliqlab / javierruanohdez 路线）：丢失 λ，平局预测崩溃
- Bayesian MCMC 框架（lbenz730）：成本高于收益
- FIFA 排名作为主特征：本项目已有 clubelo + EA FC25，更细致

---

详细优化任务和实施计划见 `.claude/plans/optimization_backlog.md`。
