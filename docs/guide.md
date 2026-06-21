# worldcup-predictor 使用指南

本文档面向日常使用者，覆盖环境搭建、每日操作流程、下注建议的解读方式、
底层模型原理，以及所有 CLI 参数的完整说明。

---

## 1. 环境搭建

```bash
# 克隆仓库
git clone https://github.com/beersoccer/worldcup-predictor.git
cd worldcup-predictor

# 创建 Python 3.11 虚拟环境并激活
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API 密钥（仅免费 key 是必须的）
cp .env.example .env
```

`.env` 中的关键字段：

| 变量 | 是否必须 | 说明 |
|---|---|---|
| `FOOTBALLDATA_KEY` | 必须（免费） | football-data.org 赛程/比分，注册即得 |
| `APIFOOTBALL_KEY` | 可选（免费） | API-Football 首发阵容，注册即得 |
| `ODDS_API_KEY` | 可选（付费） | The Odds API，含 Pinnacle 盘口，约 $30/月 |

**所有命令都需要** `PYTHONPATH=.` 前缀和激活的 venv。

---

## 2. 每日操作流程

### 2.1 标准流程（比赛日）

```bash
# Step 1：赛前下午 — 拉取全量数据
PYTHONPATH=. python -m skill.helpers.cli fetch --all

# Step 2：生成预测（含 50k 蒙特卡洛模拟）
PYTHONPATH=. python -m skill.helpers.cli predict --all --simulate

# Step 3：查看今日推荐下注（默认 AH 让球盘模式）
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 10000

# Step 4（可选）：发布到本地看板
PYTHONPATH=. python -m skill.helpers.cli publish
python3 -m http.server 8780 --directory site   # 浏览器打开 http://localhost:8780

# Step 5：赛前 30 分钟再次更新（获取最新 Polymarket 价格 + 确认首发）
PYTHONPATH=. python -m skill.helpers.cli fetch --all
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 10000
```

### 2.2 赛后结算（次日）

```bash
# 自动回填结果、重新预测、更新 P&L
PYTHONPATH=. python -m skill.helpers.cli review
```

`review` 会：拉取已完赛结果 → 重新预测剩余场次 → 更新看板（含累计 P&L、ROI、最大回撤）。

---

## 3. bet 命令详解

### 3.1 基本语法

```bash
PYTHONPATH=. python -m skill.helpers.cli bet [选项]
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--bankroll` | 10000 | 当前本金（任意单位，输出 stake 与之成比例） |
| `--mode` | `ahou` | 推荐市场，见下表 |
| `--date` | 今日 | 指定预测日期，格式 `YYYY-MM-DD` |

### 3.2 五种模式对比

| 模式 | 命令 | 输出 | 适用场景 |
|---|---|---|---|
| `ahou`（默认） | `bet --mode ahou` | 让球盘 + 大小盘各 3 条线 | 推荐日常使用，对齐主流亚洲盘口 |
| `ah` | `bet --mode ah` | 让球盘 3 条线 | 仅看让球盘 |
| `ou` | `bet --mode ou` | 大小盘 3 条线 | 仅看大小盘 |
| `1x2` | `bet --mode 1x2` | 胜平负 | 看欧赔输赢盘 |
| `all` | `bet --mode all` | 1X2 + AH + OU 全部 | Kelly 在所有市场间统一分配仓位 |

**自动选线规则**（动态、按比赛而异）：

- **让球盘主线** = `round-to-half(-(λ_h - λ_a))`，再叠加 ±0.5 形成 3 条线
  - 例：FRA(λ=1.65) vs MAR(λ=0.88)，差 0.77 → 主线 -1.0，3 条线 = [-1.5, -1.0, -0.5]
- **大小盘主线** = `round-to-half(λ_h + λ_a)`，再叠加 ±0.5
  - 例：总进球 2.53 → 主线 2.5，3 条线 = [2.0, 2.5, 3.0]
- 让球盘范围 [-3, +3]，大小盘范围 [1.5, 4.5]，超出截断

### 3.3 输出解读

```
Bet                                          p_win    odds    edge     stake
FRA vs MAR · AH -0.5 home                   0.623    1.847   8.3%    415.00
ARG vs MEX · AH +0.5 home                   0.712    1.680   5.1%    195.00
───────────────────────────────────────────────────────────────────────────
TOTAL                                                                 610.00

logged → reports/bets/2026-06-20.json
```

各字段含义：

| 字段 | 含义 |
|---|---|
| `Bet` | 比赛 · 市场类型 · 方向（home/away/draw） |
| `p_win` | 模型估算的赢盘概率（DC + 上下文层 + 市场锚定） |
| `odds` | 市场隐含赔率（1 / 市场隐含概率，无佣金） |
| `edge` | 模型概率 − 市场隐含概率；≥ 3% 才会进入建议 |
| `stake` | 建议押注金额（按 1/4 Kelly 计算，已受单注 5% 上限约束） |

**AH 方向解读：**
- `AH -0.5 home`：押主队赢（需赢至少 1 球）
- `AH +0.5 home`：押主队不输（赢或平均可）
- `AH -0.5 away` / `AH +0.5 away`：客队方向，反之亦然

---

## 4. 底层模型原理

### 4.1 第一层：Dixon-Coles 期望进球

模型从 49,000+ 场历史国际比赛中拟合每支球队的**进攻力 α** 和**防守力 β**，
预测主客队各自的期望进球（λ_home、λ_away）：

```
λ_home = exp(α_home − β_away + home_advantage)
λ_away = exp(α_away − β_home)
```

加入 Dixon-Coles 低分修正（ρ 参数，避免 0-0/1-0/0-1/1-1 系统性低估），
和指数时间衰减（ξ=0.001，最近比赛权重更高）。训练窗口：截至预测日前 3 年。

有了 λ_home 和 λ_away，把每个可能的比分（0-0 到 10-10）的概率全部算出来，
组成一张 **11×11 的得分矩阵**，这是所有下游计算的基础。

### 4.2 第二层：强度调整

三个可选增强器，各以 10% 权重（`TALENT_WEIGHT`）叠入：

| 模块 | 数据源 | 说明 |
|---|---|---|
| `talent.py` | ClubElo.com | 俱乐部 ELO 均值 → 国家队进攻/防守强度 |
| `fcratings.py` | EA FC25 球员评分 | OVR + 攻防分项 → 强度先验 |
| `injuries.py` | `data/injuries_wc2026.json` | 赛前缺阵球员从阵容移除后重算强度 |

**跨联合会修正**（Run 28）：UEFA/CONMEBOL 与其他联合会对阵时，
主流模型系统性低估强队优势 → 对强队 λ 乘以 `exp(+0.075)`（gap=0.15）。

### 4.3 第三层：比赛情境层

对 λ_home / λ_away 施加场景乘数：

| 因素 | 状态 | 说明 |
|---|---|---|
| 海拔 | ✅ 采用 | 主场海拔 >2000m → 客队 λ 下调 |
| 休息日差 | ✅ 采用（Run 12） | 多休 1 天 → 己方 λ +约 2% |
| 天气 | ❌ 拒绝（Run 19/20） | 1642 场回测无显著信号 |
| 其他 10 项 | ❌ 全部拒绝 | 重要性、死橡皮、卫冕冠军等均无信号 |

### 4.4 第四层：市场锚定集成

```
P_final = 0.60 × P_market + 0.40 × P_model_adj
```

- `P_market`：Polymarket + Kalshi + The Odds API（若有 key）多源平均、去佣归一
- `P_model_adj`：DC + 强度 + 情境的综合模型概率
- 权重 `MARKET_WEIGHT=0.60` 经 Run 26 walk-forward 验证

### 4.5 让球盘 / 大小盘的 edge 来源（业界标准做法）

参考 Pinnacle 与学术文献，欧赔（1X2）转亚盘（AH/OU）的标准做法是
**反解市场隐含的进球期望 (λ_h^M, λ_a^M)**：

**步骤：**
1. 已知 DC 模型给出 `(λ_h^DC, λ_a^DC, ρ)` → 通过得分矩阵输出 1X2
2. **保持 ρ 不变**（ρ 是联赛级低分修正，不是单场参数），用 L-BFGS-B 反解
   `(λ_h^M, λ_a^M)`，使其经 DC 得分矩阵后输出**与市场 1X2 完全一致**
3. 用反解的市场 λ 通过同一套 `asian_handicap()` / `over_under()` 函数，
   计算**任意 AH/OU 线**的市场隐含概率
4. `edge = DC概率 − 市场λ概率`，所有线条统一比较

**优势：**
- 保留 DC 的 ρ 低分修正，不像粗暴的 Skellam 假设独立 Poisson
- 一次反解，所有 AH/OU 线（±0.5、±1、±1.5、±2、±2.5、OU 2/2.5/3/3.5/4）都可算 edge
- 与 Pinnacle 的"1X2 + AH + OU 内部一致定价"逻辑同源

**白名单约束：**
- OU 1.5 已在 Run 27 中实证拒绝（反技能），硬封锁
- AH 整数线（0、±1、±2）和 OU 整数线（2、3、4）已加入白名单，
  但**待 P3.4 完成各线独立 walk-forward 后才正式验证**——目前依赖
  λ 反解的内部一致性间接信任

### 4.6 罚点球：公平硬币（Run 29）

淘汰赛点球大战使用 **50/50 硬币**，不使用强度加权。
Walk-forward 在 231 场实际点球上证明：强度加权方案 Brier=0.2683，
硬币 Brier=0.2500，前者反技能。在可用样本量下无法恢复球队级点球技能。

---

## 5. 凯利公式与资金管理

### 5.1 参数设置

| 参数 | 值 | 说明 |
|---|---|---|
| Kelly 分数 | 1/4（25%） | 全 Kelly 风险太大，缩为 1/4 保守执行 |
| 单注上限 | 本金 5% | 防止单笔大赌 |
| 总仓位上限 | 本金 30% | 同日多注合并不超过 30% |
| Edge 门槛 | 3% | 低于此不下注 |
| 最小注额 | 本金 0.5% | 信号太弱的注单丢弃 |

### 5.2 建议执行原则

1. **严格按 stake 执行**，不因"手感"加减仓
2. **赛前 30 分钟最后一次 `fetch`**，确保 Polymarket 价格是最新的
3. 整个世界杯约产生 20–30 注（edge 达标），每注约占本金 2–4%
4. 短期方差是正常的，即使模型有 5% edge，也可能连续 5 场亏损

---

## 6. 完整 CLI 参考

```bash
PYTHONPATH=. python -m skill.helpers.cli <subcommand> [args]
```

| 子命令 | 参数 | 用途 |
|---|---|---|
| `fetch --all` | — | 拉取历史结果、赛程、阵容、赔率、天气、首发 |
| `predict --all --simulate` | `--sims N`（默认 50000） | 预测全部 104 场 + 蒙特卡洛锦标赛模拟 |
| `predict --match wc2026-000` | — | 单场预测（调试用） |
| `publish [--date]` | — | 打包报告 → `site/data.json` |
| `review` | `--sims N` | 赛后结算：补充结果、重预测、更新 P&L |
| `market [--date]` | — | 打印夺冠赔率：模型 vs Polymarket + edge |
| `bet --bankroll N` | `--mode [ah\|1x2\|both]`，`--date` | 生成今日下注建议 |
| `players --match <id>` | `--refresh` | 每场比赛可能进球的球员列表 |
| `portraits [--topk N]` | — | 预下载球员头像到 `site/portraits/` |
| `backtest` | `--start`，`--end`，`--xi`，`--markets` | Walk-forward 回测（1X2 或 AH/OU） |

---

## 7. 输出文件说明

| 文件 | 生成命令 | 内容 |
|---|---|---|
| `reports/YYYY-MM-DD/predictions.json` | `predict` | 每场比赛的概率、λ、AH/OU 公允赔率 |
| `reports/YYYY-MM-DD/simulation.json` | `predict --simulate` | 蒙特卡洛夺冠概率、各轮晋级率 |
| `reports/YYYY-MM-DD/bracket.json` | `predict --simulate` | 最大概率单链赛程预测 |
| `reports/bets/YYYY-MM-DD.json` | `bet` | 当日下注建议（含 Kelly 参数、edge） |
| `site/data.json` | `publish` | 看板全量数据（预测 + 模拟 + 下注面板） |
| `reports/backtests/backtest_*.json` | `backtest` | Walk-forward 回测结果 |

---

## 8. 数据来源

| 数据 | 来源 | 是否免费 |
|---|---|---|
| 历史比赛结果 + WC2026 赛程 | martj42/international_results（GitHub CSV） | ✅ 免费 |
| 赛程 / 实时比分 | football-data.org 免费层 | ✅ 免费 |
| 首发阵容 | API-Football 免费层 | ✅ 免费（需 key） |
| 预测市场价格（1X2） | Polymarket Gamma API + Kalshi | ✅ 免费 |
| 天气（仅展示） | Open-Meteo | ✅ 免费 |
| 球员评分先验 | EA FC25 OVR | ✅ 免费 |
| ClubElo 俱乐部评分 | clubelo.com | ✅ 免费 |
| 已验证盘口（Pinnacle） | The Odds API（Business 层） | ❌ ~$30/月 |

---

## 9. 回测与因子验证纪律

所有预测因子必须满足：
1. **Walk-forward 验证**：用严格截止日期 T 之前的数据预测 T 之后，绝无回望
2. **必须超越基线**：打败 ELO 基线或 DC 基线，才能进入模型
3. **失败因子记录在案**：见 `reports/backtests/FINDINGS.md`（共 29 次实验）

已拒绝因子（实验后放弃）：天气、气候差、重要性、死橡皮、卫冕冠军、年龄乘数、
裁判因素、贝叶斯点球技能、OU 1.5 市场、强度加权点球。

---

## 10. 常见问题

**Q: `bet` 命令输出"Slate empty"，没有推荐？**  
A: 两种原因：(1) 当日比赛无 Polymarket 报价（AH 的市场锚点来自 1X2，而 1X2 需要 Polymarket）；(2) 所有比赛的 edge 都低于 3%。先跑 `fetch --all` 确认有市场数据，或用 `market` 命令检查。

**Q: 为什么默认是 `--mode ahou`？**  
A: 主流亚洲盘口同时提供让球盘和大小盘三栏式（输赢盘/让球盘/大小盘），
ahou 模式与之对齐，Kelly 在两个市场之间统一分配仓位。

**Q: 现在 AH ±1.5、±2.5、整数线、OU 各档都能下注吗？**  
A: 是的。1X2→λ_market 反解出市场隐含的进球期望后，所有线条的市场隐含概率
都可以一致地计算。不再受限于早期 ±0.5 的 3 桶映射。

**Q: 点球大战概率为何是 50/50？**  
A: Walk-forward 在 231 场实际点球上验证，任何基于球队强度的加权方案都比硬币更差（Run 29）。

**Q: 如何查看历史下注的盈亏？**  
A: 运行 `review` 后，看板的"Betting"面板会显示累计 P&L、ROI 和最大回撤。
或直接读 `reports/bets/` 目录下各日期的 JSON 文件。
