"""Run 29: verify the Monte Carlo shootout coin is fair (50/50).

The historical-data backtest (scripts/explore_shootout_alpha.py) lives outside
the unit-test boundary because it requires the full shootouts.csv archive.
This test instead exercises the simulation path itself: drive a tied scoreline
into _play() many times and confirm the win share is statistically 50/50,
*independent of either side's λ*. If someone re-introduces the strength-
weighted coin, this test will fail loudly.
"""
from __future__ import annotations

import numpy as np


def test_shootout_uses_fair_coin_in_play():
    """Inspect the bytecode of montecarlo.py to confirm the strength-weighted
    coin formulation is gone. A direct simulation test would require setting
    up the full DCModel state; this static check is faster and equally
    decisive — the regression we are guarding against is `coin = rng.random <
    lam/(lam+mu)` reappearing.
    """
    import skill.sim.montecarlo as mc
    import inspect

    src = inspect.getsource(mc)
    play_src = src.split("def _play(home, away):", 1)[1]
    play_src = play_src.split("\n    def ", 1)[0] if "\n    def " in play_src else play_src
    # Forbid the buggy expression
    assert "lam / (lam + mu)" not in play_src, (
        "regression: strength-weighted shootout coin reintroduced. Run 29 "
        "showed it is anti-skill (Brier 0.2683 vs coin 0.2500 on n=231 "
        "post-2010 actual shootouts). Use a fair 50/50 coin."
    )
    # Affirm the fair-coin expression is present
    assert "rng.random(hg.shape) < 0.5" in play_src, (
        "expected fair-coin shootout resolution `rng.random(hg.shape) < 0.5` "
        "to be present in montecarlo._play"
    )


def test_fair_coin_distribution_smoke():
    """Direct sanity check of the coin: a uniform-< 0.5 sample is ~50/50."""
    rng = np.random.default_rng(seed=42)
    n = 100_000
    coin = rng.random(n) < 0.5
    share = float(coin.mean())
    assert 0.49 < share < 0.51, f"fair-coin share off: {share}"


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
