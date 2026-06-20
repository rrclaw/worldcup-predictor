# worldcup-predictor

Per-match probability predictions for the 2026 FIFA World Cup (USA/Canada/Mexico, 48 teams,
104 matches), with daily live re-forecasting and a public dashboard.

**Philosophy — market-anchored ensemble.** Bookmaker consensus is hard to beat over the long run,
but blindly copying odds has no edge. So we anchor on the de-vigged market consensus as a strong
prior, then layer a Dixon-Coles bivariate Poisson model, ELO strength priors, and contextual
adjustments (altitude, weather, rest days, travel, injuries) to produce a calibrated forecast — and
surface where the model *disagrees* with the market as the interesting signal.

## What it outputs

- **Per match:** 1X2 (win/draw/loss), full scoreline distribution, **Asian Handicap** ladder,
  **Over/Under** ladder, both-teams-to-score. AH/OU prices are derived analytically from the
  Dixon-Coles score grid (no extra fitting), with integer / half / quarter lines and explicit
  push handling.
- **Tournament:** Monte Carlo simulation (≥50k runs) over the full bracket → group-advancement,
  per-round survival, and title-winning probabilities for every team.
- **Live:** during the tournament, a daily pipeline pulls fresh odds, prediction-market prices,
  injuries/lineups and weather, re-runs predictions, and tracks realized accuracy (RPS/Brier).
- **Bet slate:** `cli bet` drafts a stake-sized recommendation list against the live market
  using a quarter-Kelly portfolio sizer with a per-market acceptance whitelist (only
  walk-forward-validated markets can carry stakes — see `reports/backtests/FINDINGS.md`).
- **Dashboard betting panel:** today's slate, cumulative P&L, ROI, and max drawdown are
  surfaced on the public dashboard (`site/index.html`). Each settled match is reconciled
  against the actual result in the next `cli publish` run; no live tournament results are
  required for the panel to render gracefully.

## Model

1. **Market prior** — multiple bookmakers' 1X2 odds de-vigged to consensus implied probabilities,
   blended with prediction-market prices by liquidity → `P_market`.
2. **Statistical model** — Dixon-Coles bivariate Poisson with low-score correction and exponential
   time decay (ξ tuned by backtest); ELO rating difference as an attack/defence prior → `P_model`.
3. **Context layer** — small multiplicative adjustments to expected goals λ for altitude,
   rest-day differential, travel distance, key absences, and the cross-confederation
   strength gap (UEFA / CONMEBOL teams systematically under-priced when they meet sides
   from other confederations — Run 28). Adjustment magnitudes are constrained by the
   backtest; weather was tested on 1642 matches and rejected (Run 19/20).
4. **Ensemble + calibration** — `P_final = w·P_market + (1-w)·P_model_adj`, with `w` fit on
   calibration metrics, then isotonic calibration. `edge = P_final − P_market`.

## Backtesting discipline

- **Walk-forward only.** Predictions for date T use strictly data available at ≤T; ELO and decay are
  recomputed as-of. No look-ahead.
- **Metrics:** RPS (the standard for football 1X2), Brier, log-loss, calibration curves.
- **Baselines to beat:** raw market odds and pure-ELO. A factor is kept only if it shows a stable
  positive contribution in walk-forward; low-sample factors are flagged as low-confidence.
- **Per-market acceptance** (Run 27): a derived market (AH line, OU line) can only carry bets
  after it beats a no-skill baseline on Brier in walk-forward. AH ±0.5 / ±1.5 cleared; OU 1.5
  is empirically anti-skill and is hard-blocked in `cli bet`.
- **Penalty shootouts are a fair coin** (Run 29): the prior strength-weighted formulation was
  empirically anti-skill on n=231 actual shootouts (Brier 0.2683 vs coin's 0.2500); a Bayesian
  team-skill prior (n=339 shrinkage sweep) is also worse than a coin. No team-level shootout
  skill is recoverable from the available samples — fair 50/50 it is.

## Data sources (all free / no-key by default)

| Data | Source |
|------|--------|
| Historical results **+ WC2026 fixtures** | martj42 `international_results` (public GitHub CSV, no auth) |
| ELO ratings | computed in-repo from results; optional eloratings.net cross-check |
| Live fixtures / scores | football-data.org (free tier covers the World Cup) |
| Weather | Open-Meteo (free, no key) |
| Venues | bundled static table (altitude, surface, roof, coordinates) |
| Prediction market | Polymarket Gamma API (free, no key) |
| Live odds | public aggregated odds; optional The Odds API (paid) |
| Injuries / form / xG (optional) | `machina-sports/sports-skills` if installed |
| Tournament-long injuries | curated `data/injuries_wc2026.json` (a *prior*: absentees dropped from the XI, strength recomputed) |

The repo is **self-contained** — it talks to public APIs directly and implements its own betting
math (de-vig, edge, Kelly), so it has no hard dependency on third-party data packages.
[`machina-sports/sports-skills`](https://github.com/machina-sports/sports-skills) (MIT) is supported
as an optional enhancement for richer injury/xG/lineup data when installed.

## Optional paid upgrades

Everything above runs free. If you want to strengthen the **market-anchor** layer, there is exactly
one upgrade worth paying for — and one popular source that is deliberately *not* recommended.

| Upgrade | Verdict | Why |
|---------|---------|-----|
| **Pinnacle closing line** (via [The Odds API](https://the-odds-api.com) Business tier, ~$99) | ✅ **recommended** | Pinnacle's closing odds are the academic gold standard for sharpness — a low-margin book that moves on sharp money, not public sentiment. It is the single best signal you can add to the consensus anchor. Drop-in: set `ODDS_API_KEY` in `.env` and the loader picks it up; no model change needed. |
| **Macau odds / 澳门盘 (澳彩, Macau Slot)** | ❌ **not recommended** | A retail-facing Asian-Handicap book whose line reflects (Chinese) public money, **not** sharper than Pinnacle's close. It would add a correlated, public-biased signal — noise, not alpha. It also has no free/clean API (only ToS-gray scraping) and no free historical archive, so it **cannot be walk-forward validated** under this repo's "a factor must beat baseline to be adopted" rule. Same reasoning rules out other retail Asian books. |

The principle: pay for **sharpness and orthogonality** (Pinnacle's close), not for *more of the same*
retail signal the consensus already contains.

## Setup

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in free keys (football-data.org, optionally Kaggle)

PYTHONPATH=. python -m skill.helpers.cli fetch --all
PYTHONPATH=. python -m skill.helpers.cli predict --all --simulate
PYTHONPATH=. python -m skill.helpers.cli backtest --start 2010-01-01 --end 2026-05-31

# Walk-forward calibration of the derived AH/OU markets:
PYTHONPATH=. python -m skill.helpers.cli backtest --markets --start 2018-01-01 --end 2024-12-31

# Daily bet slate (Quarter Kelly, per-market whitelist enforced):
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 10000

# Run unit tests (44 tests across derived_markets, kelly, walkforward_markets,
# confederations, shootout fair-coin guard, betting payload):
for f in tests/test_*.py; do PYTHONPATH=. python "$f"; done
```

See [`CHANGELOG.md`](CHANGELOG.md) for behaviour changes between releases.

## License

MIT. Methodology builds on the classic Dixon-Coles (1997) approach and the open
`machina-sports/sports-skills` data toolkit.
