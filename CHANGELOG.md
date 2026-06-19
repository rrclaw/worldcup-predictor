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
- `tests/` directory with 18 unit tests covering AH/OU derivation and Kelly
  discipline (`PYTHONPATH=. python tests/test_*.py`).
- `docs/competitor_analysis.md` — horizontal review of 9 GitHub
  worldcup-predictor projects, anchoring the optimization backlog.

### Changed
- `_predict_one` now attaches `derived` (the full AH/OU ladder) to every
  fixture's prediction record. Existing fields are unchanged.

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
