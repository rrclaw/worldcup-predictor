"""Unit tests for `skill.backtest.walkforward_markets`.

These cover the metric helpers in isolation. Full end-to-end backtest is run
via `cli backtest --markets` and lives in `reports/backtests/`.
"""
from __future__ import annotations

import numpy as np

from skill.backtest.walkforward_markets import (
    _ah_outcome, _ou_outcome, _bucket_ece, _market_metrics, _baseline_metrics,
)


def _approx(a, b, tol=1e-6):
    assert abs(a - b) < tol, f"{a} vs {b}"


def test_ah_outcome_half_line():
    """AH -0.5 covers iff margin > 0; AH +0.5 covers iff margin > -1."""
    assert _ah_outcome(margin=2, line=-0.5) == 1
    assert _ah_outcome(margin=0, line=-0.5) == 0
    assert _ah_outcome(margin=-1, line=-0.5) == 0
    assert _ah_outcome(margin=0, line=0.5) == 1   # +0.5 covers a draw
    assert _ah_outcome(margin=-1, line=0.5) == 0  # +0.5 doesn't cover a 1-goal loss


def test_ou_outcome():
    assert _ou_outcome(total=3, line=2.5) == 1
    assert _ou_outcome(total=2, line=2.5) == 0


def test_perfect_calibration_zero_ece():
    """If predicted prob always matches outcome rate within bucket, ECE is 0."""
    np.random.seed(0)
    p = np.repeat([0.1, 0.5, 0.9], 100)
    y = np.concatenate([
        np.random.binomial(1, 0.1, 100),
        np.random.binomial(1, 0.5, 100),
        np.random.binomial(1, 0.9, 100),
    ])
    ece = _bucket_ece(p, y, n_bins=10)
    assert ece < 0.05  # large-N ≈ 0; small-N has sampling noise


def test_extreme_overconfidence_high_ece():
    """If we predict 0.9 but the truth is 50/50, ECE should be near 0.4."""
    p = np.full(200, 0.9)
    y = np.random.binomial(1, 0.5, 200)
    ece = _bucket_ece(p, y)
    assert ece > 0.3


def test_market_metrics_perfect_predictor():
    """Probability 1 on every truth → Brier 0, log-loss → 0, accuracy 1."""
    p = np.array([1.0, 0.0, 1.0, 0.0])
    y = np.array([1, 0, 1, 0])
    m = _market_metrics(p, y)
    assert m["brier"] < 1e-9
    assert m["top_pick_accuracy"] == 1.0
    assert m["n"] == 4


def test_baseline_constant_brier_matches_variance():
    """Constant prediction p=base_rate has Brier = base_rate(1−base_rate)."""
    y = np.array([1, 1, 0, 1, 0, 0, 1, 1])  # base_rate = 5/8 = 0.625
    base = float(y.mean())
    out = _baseline_metrics(y, base)
    expected = base * (1 - base)
    _approx(out["brier"], expected, tol=1e-3)


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
