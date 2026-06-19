# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/).

Categories used: `Added` · `Changed` · `Deprecated` · `Removed` · `Fixed` · `Security` · `Backtest`.
Doctrine: a `Backtest` entry is required whenever a prediction factor is added,
removed, or has its weight changed (cross-references `reports/backtests/FINDINGS.md`).

---

## [Unreleased]

### Added
- **Cross-confederation strength gap factor** (`skill/model/confederations.py`,
  `data/confederations.json`). The DC fit, calibrated mostly on intra-confed
  matches, systematically under-prices the strength gap when UEFA / CONMEBOL
  meet other confederations; a symmetric ±0.075 log-lambda shift corrects it.
  Wired into `context.py` and surfaced as a per-fixture note. (P1.1, Run 28)
- 9 new unit tests in `tests/test_confederations.py` covering country lookup,
  alias coverage, the strong-vs-weak adjustment, and same-confed no-op behaviour.

### Backtest
- **Run 28** (FINDINGS.md) — cross-confederation gap on majors 2010-2024
  (n=212 cross-confed matches). Monotonically better at every tested gap
  (0.05 → 0.30), peak Δ −0.00234 at gap=0.20-0.22. Adopted gap=0.15 (inside
  tested-good range, conservative against single-sample peak overfitting,
  matching Run 12's discipline). Magnitude is 1-2 orders larger than the
  rest factor and same band as talent / FC25 / 3-year window.

---

## [0.1.0] — 2026-06-19

First versioned release: pivot from descriptive 1X2 forecasts to stake-ready
Asian Handicap / Over-Under bet slates. Merged in PR #1
(`feat/asian-handicap-kelly`).

### Added
- **Walk-forward AH/OU calibration backtest** (`skill/backtest/walkforward_markets.py`)
  with `cli backtest --markets`. Tests Brier / log-loss / ECE per line vs a
  no-skill base-rate baseline. (P1.3)
- **Per-market acceptance whitelist** in `skill/bet/kelly.py`. Markets that
  fail walk-forward calibration cannot be bet on, regardless of any individual
  edge — same anti-curve-fitting rule as Runs 14/16/17.
- **Asian Handicap & Over/Under fair-price derivation** (`skill/model/derived_markets.py`).
  Integrates the existing Dixon-Coles score grid into AH/OU probabilities and
  EV-zero fair odds. Supports integer / half / quarter lines with push handling.
  Cross-validated against the Skellam (margin) and Poisson (total) closed forms
  at `rho=0`. (P0.1 + P0.2a)
- **Kelly portfolio engine** (`skill/bet/kelly.py`). Quarter-Kelly default with
  the discipline locked in `.claude/plans/optimization_backlog.md §9`:
  per-bet cap 5%, portfolio cap 30%, edge gate 3%, signal floor 0.5%. (P0.3)
- **`cli bet` subcommand**. Reads the latest predictions, drafts a stake-sized
  slate against the live per-match 1X2 market, and logs each slate to
  `reports/bets/<date>.json` for later settlement by `cli review`.
- `tests/` directory with 26 unit tests covering AH/OU derivation, Kelly
  discipline, and walk-forward market metrics (`PYTHONPATH=. python tests/test_*.py`).
- `docs/competitor_analysis.md` — horizontal review of 9 GitHub
  worldcup-predictor projects, anchoring the optimization backlog.

### Changed
- `_predict_one` now attaches `derived` (the full AH/OU ladder) to every
  fixture's prediction record. Existing fields are unchanged.

### Backtest
- **Run 27** (FINDINGS.md) — derived AH/OU calibration on majors 2018-2024
  (n=574). All four Asian Handicap lines (-1.5, -0.5, +0.5, +1.5) beat the
  no-skill baseline on Brier by 0.020-0.049 with comparable ECE; **AH ADOPTED**
  for `cli bet`. Over/Under is marginal: OU 1.5 is *anti-skill* (Brier 0.005
  worse than baseline) and **REJECTED**; OU 2.5 / OU 3.5 are accepted with
  low-confidence flags. Whitelist enforces the decision in code.

### Deferred
- **Live Pinnacle AH/OU feed** (P0.2b). Pinnacle's official API was closed to
  the public in 2025-07; The Odds API ($30/mo) is the only compliant relay
  and will be onboarded for the European league season, not for the World Cup.
  Until then `cli bet` only acts on 1X2 markets (Polymarket / Kalshi); AH/OU
  bets are intentionally suppressed to avoid self-arbitrage against the
  model's own fair price.

---

## Conventions for future releases

- **Versioning**: bump `MAJOR.MINOR.PATCH` on tagged releases.
  - `MAJOR` — incompatible CLI / report-schema change
  - `MINOR` — new prediction factor, new market, new CLI subcommand
  - `PATCH` — bug fix, doc update, dependency bump with no behaviour change
- **Tag format**: `vX.Y.Z` (annotated tag). Pre-tournament and end-of-tournament
  snapshots get tagged so live results stay reproducible.
- **A release entry must answer three questions**:
  1. What changed (Added / Changed / Fixed)?
  2. Did any factor enter or leave the model? (Backtest entry, with `Run NN`
     reference to FINDINGS.md.)
  3. Is the dashboard schema (`site/data.json` keys) backwards-compatible?
- **Unreleased changes accumulate at the top** under `## [Unreleased]`. On
  release, the section is renamed to `## [vX.Y.Z] — YYYY-MM-DD` and a new
  empty `[Unreleased]` is created.
