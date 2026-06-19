"""Sanity tests for `skill.model.derived_markets`.

Run with: PYTHONPATH=. python -m pytest tests/test_derived_markets.py -v
or:       PYTHONPATH=. python tests/test_derived_markets.py
"""
from __future__ import annotations

import numpy as np
from scipy.stats import poisson, skellam

from skill.model.derived_markets import (
    asian_handicap, over_under, derive_all, _fair_odds,
)


# Use rho=0 so DC reduces to pure independent Poissons — that lets us
# cross-check against scipy's analytic Skellam (X-Y) and direct Poisson(X+Y).
LAM_H, LAM_A, RHO = 1.5, 1.0, 0.0


def _approx(a, b, tol=5e-4):
    assert abs(a - b) < tol, f"{a} vs {b}, |diff|={abs(a-b):.6f} > {tol}"


def test_ah_zero_matches_skellam():
    """AH 0: home covers iff X-Y > 0; push iff X-Y == 0."""
    out = asian_handicap(LAM_H, LAM_A, RHO, 0.0)
    p_home_win = 1 - skellam.cdf(0, LAM_H, LAM_A)
    p_push = skellam.pmf(0, LAM_H, LAM_A)
    _approx(out["p_home"], p_home_win)
    _approx(out["p_push"], p_push)
    _approx(out["p_home"] + out["p_push"] + out["p_away"], 1.0)


def test_ah_minus_half_matches_skellam():
    """AH -0.5: home covers iff X-Y >= 1, no push."""
    out = asian_handicap(LAM_H, LAM_A, RHO, -0.5)
    p_home = 1 - skellam.cdf(0, LAM_H, LAM_A)
    _approx(out["p_home"], p_home)
    _approx(out["p_push"], 0.0)
    _approx(out["p_away"], 1 - p_home)


def test_ah_minus_one_integer_with_push():
    """AH -1: home covers if X-Y >= 2, push if X-Y == 1."""
    out = asian_handicap(LAM_H, LAM_A, RHO, -1.0)
    p_home = 1 - skellam.cdf(1, LAM_H, LAM_A)
    p_push = skellam.pmf(1, LAM_H, LAM_A)
    _approx(out["p_home"], p_home)
    _approx(out["p_push"], p_push)


def test_ah_quarter_line_consistent():
    """AH -0.25 = average of AH 0 and AH -0.5 outcomes."""
    q = asian_handicap(LAM_H, LAM_A, RHO, -0.25)
    a = asian_handicap(LAM_H, LAM_A, RHO, 0.0)
    b = asian_handicap(LAM_H, LAM_A, RHO, -0.5)
    expected_p_home = 0.5 * (a["p_home"] + b["p_home"]) + 0.25 * (a["p_push"] + b["p_push"])
    _approx(q["p_home"], expected_p_home)
    assert q["p_push"] == 0.0
    assert q["type"] == "quarter"


def test_ou_2_5_matches_total_poisson():
    """OU 2.5 with rho=0: total goals ~ Poisson(λh + λa)."""
    out = over_under(LAM_H, LAM_A, RHO, 2.5)
    total_lam = LAM_H + LAM_A
    p_over = 1 - poisson.cdf(2, total_lam)
    _approx(out["p_over"], p_over)
    _approx(out["p_under"], 1 - p_over)


def test_ou_3_integer_has_push():
    """OU 3.0: push if total == 3."""
    out = over_under(LAM_H, LAM_A, RHO, 3.0)
    total_lam = LAM_H + LAM_A
    p_push = poisson.pmf(3, total_lam)
    _approx(out["p_push"], p_push)


def test_fair_odds_zero_ev():
    """At fair odds, expected return per unit stake is 0."""
    p_win, p_push = 0.4, 0.1
    o = _fair_odds(p_win, p_push)
    p_lose = 1 - p_win - p_push
    ev = p_win * (o - 1) + p_push * 0 - p_lose * 1
    assert abs(ev) < 1e-6


def test_dc_low_score_correction_inflates_draws():
    """DC's rho<0 by construction inflates 0-0 and 1-1 (the published intent).

    Concretely, the AH-0 (draw-no-bet style integer line) push probability
    should rise when rho is set negative.
    """
    pure = asian_handicap(LAM_H, LAM_A, 0.0, 0.0)
    dc = asian_handicap(LAM_H, LAM_A, -0.08, 0.0)
    assert dc["p_push"] > pure["p_push"]


def test_derive_all_returns_full_ladder():
    out = derive_all(LAM_H, LAM_A, RHO)
    ah_lines = [r["line"] for r in out["asian_handicap"]]
    ou_lines = [r["line"] for r in out["over_under"]]
    assert -0.5 in ah_lines and 0.0 in ah_lines and 2.0 in ah_lines
    assert 2.5 in ou_lines and 3.0 in ou_lines


def test_probabilities_sum_to_one_everywhere():
    """For every line in the standard ladder, p_home+p_push+p_away ≈ 1
    (and likewise for OU)."""
    out = derive_all(LAM_H, LAM_A, -0.05)
    for r in out["asian_handicap"]:
        s = r["p_home"] + r["p_push"] + r["p_away"]
        _approx(s, 1.0, tol=1e-3)
    for r in out["over_under"]:
        s = r["p_over"] + r["p_push"] + r["p_under"]
        _approx(s, 1.0, tol=1e-3)


if __name__ == "__main__":
    import inspect
    failures = 0
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in fns:
        try:
            fn()
            print(f"  ok  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {name}: {e}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    raise SystemExit(failures)
