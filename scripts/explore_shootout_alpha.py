"""Walk-forward evaluation of penalty shootout predictors.

Tests four candidates:
  - coin       : 50/50 (information-free baseline)
  - raw_rate   : team's prior win rate (no shrinkage)
  - shrink_α   : Bayesian shrinkage to 50% with various alphas
  - dc_strength: lam_h / (lam_h + lam_a) using current MC's per-match DC λ
                 (THE PROJECT'S CURRENT CODE PATH — what _play() actually does)

The dc_strength column requires fitting DC at each shootout's date, so we
restrict it to a recent window where DC has good coverage and use the latest
production model as a stable surrogate (the experiment is calibration-only,
not for adoption).

Run: PYTHONPATH=. python scripts/explore_shootout_alpha.py
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from skill.helpers import paths

df = pd.read_csv(paths.HISTORICAL / "shootouts.csv").sort_values("date").reset_index(drop=True)
n = len(df)
split = int(n * 0.5)
print(f"Total shootouts: {n}; warmup: first {split}; evaluate on next {n-split}")
print()


def evaluate(alpha: float):
    """Walk-forward: predict each post-split shootout using only prior data."""
    correct_coin = correct_raw = correct_shrink = 0
    brier_coin = brier_raw = brier_shrink = 0.0
    n_eval = 0
    wins = defaultdict(int)
    games = defaultdict(int)
    for i, r in enumerate(df.itertuples(index=False)):
        h, a, w = r.home_team, r.away_team, r.winner
        if i >= split:
            gh, gh_w = games[h], wins[h]
            ga, ga_w = games[a], wins[a]
            # Coin
            p_coin = 0.5
            # Raw historical win rate
            rh = gh_w / gh if gh else 0.5
            ra = ga_w / ga if ga else 0.5
            p_raw = rh / (rh + ra) if (rh + ra) > 0 else 0.5
            # Bayesian shrinkage to 50%
            sh = (gh_w + alpha) / (gh + 2 * alpha)
            sa = (ga_w + alpha) / (ga + 2 * alpha)
            p_shrink = sh / (sh + sa)

            home_won = (w == h)
            correct_coin += int((p_coin >= 0.5) == home_won) if p_coin != 0.5 else 0
            correct_raw += int((p_raw > 0.5) == home_won)
            correct_shrink += int((p_shrink > 0.5) == home_won)
            brier_coin += (p_coin - int(home_won)) ** 2
            brier_raw += (p_raw - int(home_won)) ** 2
            brier_shrink += (p_shrink - int(home_won)) ** 2
            n_eval += 1
        wins[w] += 1
        games[h] += 1
        games[a] += 1
    return {
        "alpha": alpha, "n": n_eval,
        "acc_coin": correct_coin / n_eval,
        "acc_raw": correct_raw / n_eval,
        "acc_shrink": correct_shrink / n_eval,
        "brier_coin": brier_coin / n_eval,
        "brier_raw": brier_raw / n_eval,
        "brier_shrink": brier_shrink / n_eval,
    }


print(f"{'alpha':>7}{'n':>5}{'acc_coin':>10}{'acc_raw':>10}{'acc_shrink':>12}"
      f"{'brier_coin':>12}{'brier_raw':>11}{'brier_shrink':>14}")
for alpha in (0.5, 1, 2, 3, 5, 10, 20, 50):
    r = evaluate(alpha)
    print(f"{alpha:>7.1f}{r['n']:>5}{r['acc_coin']:>10.3f}{r['acc_raw']:>10.3f}"
          f"{r['acc_shrink']:>12.3f}{r['brier_coin']:>12.4f}{r['brier_raw']:>11.4f}"
          f"{r['brier_shrink']:>14.4f}")


# --- Strength-weighted comparison (current production code) ----------------
print()
print("--- Strength-weighted vs coin: how does the project's current "
      "lam/(lam+mu) approach score? ---")
from skill.helpers.data_loader import load_results
from skill.model.dixon_coles import fit as dc_fit
results = load_results()

# Restrict to shootouts with both teams seen recently in DC training data
# (post-2010, well-supported).
recent = df[df["date"] >= "2010-01-01"].reset_index(drop=True)
print(f"Recent shootouts (>=2010): {len(recent)}")

correct_strength = 0
correct_coin = 0
brier_strength = 0.0
brier_coin = 0.0
n_eval = 0

# Refit DC every ~365 days for speed (the prediction is robust to small drifts)
model = None
model_asof = None
for r in recent.itertuples(index=False):
    as_of = pd.Timestamp(r.date)
    if model is None or (as_of - model_asof).days >= 365:
        try:
            model = dc_fit(results, as_of=as_of)
            model_asof = as_of
        except ValueError:
            continue
    if r.home_team not in model.attack or r.away_team not in model.attack:
        continue
    lam_h, lam_a = model.lambdas(r.home_team, r.away_team, neutral=True)
    p_strength_home = lam_h / (lam_h + lam_a)
    home_won = int(r.winner == r.home_team)

    correct_strength += int((p_strength_home > 0.5) == bool(home_won))
    correct_coin += int(home_won)  # if we guess home: home_won; else 1-home_won
    brier_strength += (p_strength_home - home_won) ** 2
    brier_coin += (0.5 - home_won) ** 2
    n_eval += 1

print(f"n={n_eval}")
print(f"  strength-weighted:  acc={correct_strength/n_eval:.3f}  "
      f"brier={brier_strength/n_eval:.4f}")
print(f"  coin (always 0.5):  acc={correct_coin/n_eval:.3f}* "
      f"brier={brier_coin/n_eval:.4f}")
print("  (* coin acc == base rate of home_team winning shootouts)")
