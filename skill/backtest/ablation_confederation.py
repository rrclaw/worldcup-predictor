"""Walk-forward ablation: cross-confederation strength gap factor.

Hypothesis (from competitor hjjbh1314): the DC fit, calibrated mostly on
intra-confederation matches (qualifiers + regional cups dominate every
team's history), systematically MIS-rates the *strength gap* in the rare
cross-confederation games — typically over-rating CONCACAF / AFC / CAF
sides because they accumulate weak intra-confederation results that look
strong relative to their continent. A small uniform multiplicative bump
to the UEFA/CONMEBOL side's lambda (and a symmetric cut to the other
side's defence-equivalent) should help on the test set of cross-confed
matches in major tournaments.

Doctrine:
  * walk-forward only; DC refit per-match-batch on data strictly before T
  * compare BASELINE DC vs ADJUSTED on the SAME match outcomes (paired RPS)
  * a factor is adopted only if it shows monotonic-better behaviour across a
    grid of penalty magnitudes — same gate the rest factor passed (Run 12)
  * sweep two parameters: `gap` (UEFA/CONMEBOL bonus per cross-confed match)
    and `apply_to` (which side scaling)

Run:  PYTHONPATH=. python -m skill.backtest.ablation_confederation
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..helpers.data_loader import load_results
from ..model import dixon_coles as dc
from ..model.confederations import confederation
from ..model.elo import compute_elo_history
from . import metrics
from .walkforward import MAJOR


# Confederations the literature consistently rates strongest. The factor
# tested here is symmetric: when these meet a side from another confed, the
# stronger-confed side's lambda gets bumped up, the other side's lambda
# gets cut. We do NOT use hjjbh1314's hard-coded Elo numbers — those were
# fit for that author's Elo model on its own basis. We re-fit the magnitude
# here against THIS project's DC baseline, which is the doctrine's whole point.
STRONG_CONFEDS = {"UEFA", "CONMEBOL"}


def _adjustment(home: str, away: str, gap: float) -> tuple[float, float]:
    """Return (lam_mult, mu_mult) for a cross-confed match.

    gap = total log-lambda shift in favour of the stronger-confed side.
    Split symmetrically: stronger gets exp(+gap/2), weaker gets exp(-gap/2).
    For same-confed or unmapped pairs returns (1.0, 1.0).
    """
    h, a = confederation(home), confederation(away)
    if h is None or a is None or h == a:
        return 1.0, 1.0
    if h in STRONG_CONFEDS and a not in STRONG_CONFEDS:
        return float(np.exp(gap / 2)), float(np.exp(-gap / 2))
    if a in STRONG_CONFEDS and h not in STRONG_CONFEDS:
        return float(np.exp(-gap / 2)), float(np.exp(gap / 2))
    # both in STRONG_CONFEDS but different (UEFA vs CONMEBOL) — leave it; the
    # data-generating literature doesn't agree on a sign here, and DC trained
    # on history already captures it.
    return 1.0, 1.0


def _score(mp: dict, outcome: int) -> dict:
    p = np.clip(np.array([mp["p_home"], mp["p_draw"], mp["p_away"]]), 1e-9, None)
    p /= p.sum()
    return {"probs": p, "outcome": outcome,
            "rps": metrics.rps(p, outcome), "brier": metrics.brier(p, outcome),
            "log_loss": metrics.log_loss(p, outcome)}


def run(start="2010-01-01", end="2024-12-31", refit_days=60,
        gap=0.10, verbose=True):
    """One configuration. Returns dict with baseline vs adjusted metrics
    *restricted to cross-confed matches in the test window*."""
    results = load_results()
    hist, _ = compute_elo_history(results)
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    test = hist[(hist["date"] >= t0) & (hist["date"] <= t1)]
    test = test[test["tournament"].isin(MAJOR)]
    test = test.dropna(subset=["home_score", "away_score"]).sort_values("date")

    model = model_asof = None
    base_rows, adj_rows = [], []
    fired = 0

    for r in test.itertuples(index=False):
        as_of = r.date
        if model is None or (as_of - model_asof).days >= refit_days:
            try:
                model = dc.fit(results, as_of=as_of)
                model_asof = as_of
            except ValueError:
                model = None
                continue
        if not model or r.home_team not in model.attack or r.away_team not in model.attack:
            continue

        outcome = metrics.outcome_index(int(r.home_score), int(r.away_score))
        neutral = bool(r.neutral)

        lam_m, mu_m = _adjustment(r.home_team, r.away_team, gap)
        if (lam_m, mu_m) == (1.0, 1.0):
            continue   # same-confed or unmapped — outside the factor's scope
        fired += 1

        base = dc.match_probs(model, r.home_team, r.away_team, neutral)
        adj = dc.match_probs(model, r.home_team, r.away_team, neutral,
                             lam_mult=lam_m, mu_mult=mu_m)
        base_rows.append(_score(base, outcome))
        adj_rows.append(_score(adj, outcome))

    out = {
        "n": len(base_rows), "fired": fired, "gap": gap,
        "window": [start, end],
        "baseline": metrics.summarize(base_rows),
        "adjusted": metrics.summarize(adj_rows),
    }
    if verbose:
        b = out["baseline"].get("mean_rps")
        a = out["adjusted"].get("mean_rps")
        if b and a:
            verdict = "BETTER" if a < b else "worse"
            print(f"gap={gap:+.2f}  n={len(base_rows)}  "
                  f"baseline RPS={b:.5f}  adjusted RPS={a:.5f}  "
                  f"Δ={a-b:+.5f}  ({verdict})")
        else:
            print(f"gap={gap:+.2f}  n={len(base_rows)}  (insufficient data)")
    return out


if __name__ == "__main__":
    print("=== Cross-confederation gap ablation (walk-forward, majors 2010-2024) ===")
    print("Stronger side: UEFA + CONMEBOL.  Symmetric exp(±gap/2) on lambdas.")
    print()
    for gap in (0.00, 0.05, 0.10, 0.15, 0.20, 0.30):
        run(gap=gap)
