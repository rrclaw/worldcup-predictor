"""Asian Handicap & Over/Under fair-price derivation from Dixon-Coles score grid.

The DC score matrix `P(X=i, Y=j)` already encodes everything needed for any
goal-based market. We integrate it analytically — no Monte Carlo, no extra
parameters, no extra fitting.

A bookmaker's AH/OU price = (de-vigged) probability of home covering / over hitting,
inverted to decimal odds. Reproducing that probability from the model gives a
"fair price" that, compared to the live market, is a pure model edge — same as
the existing 1X2 path uses Polymarket as anchor.

Lines we support:
  * AH integer (0, ±1, ±2, …)        — three outcomes: home cover / push / away cover
  * AH half line (±0.5, ±1.5, …)     — two outcomes (no push)
  * AH quarter line (±0.25, ±0.75, …) — split bet: half stake on the adjacent integer
                                        line, half on the adjacent half line
  * OU same three flavours on total goals

Quarter-line semantics (Pinnacle / Asian convention):
  AH -0.25 = half stake on AH 0 + half stake on AH -0.5
  AH -0.75 = half stake on AH -0.5 + half stake on AH -1.0
  Pay-out per half: win = stake×(odds−1), push = 0 (returned), loss = −stake.
We expose the *probability* a bettor breaks even or better (the relevant input
to Kelly), and the expected return per unit stake at fair (no-vig) odds is 0.
"""
from __future__ import annotations

import numpy as np

from .dixon_coles import scoreline_matrix


# -- AH on margin = home_goals - away_goals -----------------------------------

def _ah_integer(grid: np.ndarray, line: float) -> tuple[float, float, float]:
    """AH integer line. Returns (p_home_cover, p_push, p_away_cover).

    Convention: line is the handicap *applied to the home team*.
    AH home -1 = line=-1 → home covers iff (home - away) > 1, push iff (home - away) == 1.
    """
    n = grid.shape[0]
    i, j = np.indices((n, n))
    margin = i - j  # home margin
    p_home = float(grid[margin > -line].sum())
    p_push = float(grid[margin == -line].sum())
    p_away = float(grid[margin < -line].sum())
    return p_home, p_push, p_away


def _ah_half(grid: np.ndarray, line: float) -> tuple[float, float, float]:
    """AH half line — no push possible."""
    n = grid.shape[0]
    i, j = np.indices((n, n))
    margin = i - j
    p_home = float(grid[margin > -line].sum())
    return p_home, 0.0, 1.0 - p_home


def asian_handicap(lam_h: float, lam_a: float, rho: float, line: float,
                   max_goals: int = 10) -> dict:
    """Probability of each outcome on AH `line` (handicap on home team).

    Returns dict with:
      * p_home, p_push, p_away — probability of each settlement
      * fair_home, fair_away   — fair decimal odds (1 / win-prob, accounting for push refund)
      * ev_home, ev_away       — expected return per unit stake at fair odds (always 0)

    Quarter-line bets are split into two half-stakes; we report the *blended*
    probability of any positive return on the full bet, and the fair odds at
    which expected value is zero.
    """
    grid = scoreline_matrix(lam_h, lam_a, rho, max_goals)
    line4 = round(line * 4)  # work in quarter units to dodge float quirks

    if line4 % 2 == 0:  # integer or half (line × 4 even → line × 2 integer)
        if line4 % 4 == 0:  # integer
            p_h, p_push, p_a = _ah_integer(grid, line)
        else:  # half
            p_h, p_push, p_a = _ah_half(grid, line)
        fair_home = _fair_odds(p_h, p_push)
        fair_away = _fair_odds(p_a, p_push)
        return {
            "line": line,
            "type": "integer" if line4 % 4 == 0 else "half",
            "p_home": round(p_h, 4),
            "p_push": round(p_push, 4),
            "p_away": round(p_a, 4),
            "fair_home_odds": fair_home,
            "fair_away_odds": fair_away,
        }

    # quarter line: average of two adjacent lines (one integer, one half)
    if line4 % 4 == 1:           # e.g. -0.25 = avg(0, -0.5);  +0.75 = avg(+0.5, +1)
        line_lo, line_hi = line - 0.25, line + 0.25
    else:                         # line4 % 4 == 3, e.g. -0.75 = avg(-0.5, -1)
        line_lo, line_hi = line - 0.25, line + 0.25

    a = asian_handicap(lam_h, lam_a, rho, line_lo, max_goals)
    b = asian_handicap(lam_h, lam_a, rho, line_hi, max_goals)
    # On a quarter line each leg gets half the stake; outcomes blend linearly.
    p_h = 0.5 * (a["p_home"] + b["p_home"]) + 0.25 * (a["p_push"] + b["p_push"])
    p_a = 0.5 * (a["p_away"] + b["p_away"]) + 0.25 * (a["p_push"] + b["p_push"])
    # Half-win/half-push gives a fractional payout; fair odds derived from EV=0.
    return {
        "line": line,
        "type": "quarter",
        "p_home": round(p_h, 4),
        "p_push": 0.0,
        "p_away": round(p_a, 4),
        "fair_home_odds": _fair_odds_quarter(a, b, side="home"),
        "fair_away_odds": _fair_odds_quarter(a, b, side="away"),
    }


# -- OU on total = home + away ------------------------------------------------

def over_under(lam_h: float, lam_a: float, rho: float, line: float,
               max_goals: int = 10) -> dict:
    """Probability of Over / Push / Under for total goals `line`.

    Same line conventions as AH (integer / half / quarter)."""
    grid = scoreline_matrix(lam_h, lam_a, rho, max_goals)
    n = grid.shape[0]
    i, j = np.indices((n, n))
    total = i + j
    line4 = round(line * 4)

    if line4 % 4 == 0:           # integer
        p_over = float(grid[total > line].sum())
        p_push = float(grid[total == line].sum())
        p_under = float(grid[total < line].sum())
        kind = "integer"
    elif line4 % 2 == 0:         # half
        p_over = float(grid[total > line].sum())
        p_push, p_under = 0.0, 1.0 - p_over
        kind = "half"
    else:                         # quarter
        a = over_under(lam_h, lam_a, rho, line - 0.25, max_goals)
        b = over_under(lam_h, lam_a, rho, line + 0.25, max_goals)
        p_over = 0.5 * (a["p_over"] + b["p_over"]) + 0.25 * (a["p_push"] + b["p_push"])
        p_under = 0.5 * (a["p_under"] + b["p_under"]) + 0.25 * (a["p_push"] + b["p_push"])
        return {
            "line": line, "type": "quarter",
            "p_over": round(p_over, 4), "p_push": 0.0, "p_under": round(p_under, 4),
            "fair_over_odds": _fair_odds_quarter(a, b, side="over"),
            "fair_under_odds": _fair_odds_quarter(a, b, side="under"),
        }

    return {
        "line": line, "type": kind,
        "p_over": round(p_over, 4),
        "p_push": round(p_push, 4),
        "p_under": round(p_under, 4),
        "fair_over_odds": _fair_odds(p_over, p_push),
        "fair_under_odds": _fair_odds(p_under, p_push),
    }


# -- Fair-odds helpers --------------------------------------------------------

def _fair_odds(p_win: float, p_push: float) -> float | None:
    """Decimal fair odds: stake returned on push, lost on the other side.
    EV = p_win·(O−1) + p_push·0 + p_lose·(−1) = 0  ⇒  O = 1 + p_lose/p_win.
    """
    if p_win <= 1e-9:
        return None
    p_lose = 1.0 - p_win - p_push
    return round(1.0 + p_lose / p_win, 3)


def _fair_odds_quarter(a: dict, b: dict, side: str) -> float | None:
    """Fair odds on a quarter-line bet, derived from the two underlying legs.

    Quarter-line settlement (per unit total stake):
      win on both legs    → return = O − 1
      win one + push one  → return = (O − 1) / 2
      win one + lose one  → return = −1/2
      lose both           → return = −1
    Solve for O so EV = 0.
    """
    if side == "home":
        pw_a, pp_a, pl_a = a["p_home"], a["p_push"], a["p_away"]
        pw_b, pp_b, pl_b = b["p_home"], b["p_push"], b["p_away"]
    elif side == "away":
        pw_a, pp_a, pl_a = a["p_away"], a["p_push"], a["p_home"]
        pw_b, pp_b, pl_b = b["p_away"], b["p_push"], b["p_home"]
    elif side == "over":
        pw_a, pp_a, pl_a = a["p_over"], a["p_push"], a["p_under"]
        pw_b, pp_b, pl_b = b["p_over"], b["p_push"], b["p_under"]
    else:  # under
        pw_a, pp_a, pl_a = a["p_under"], a["p_push"], a["p_over"]
        pw_b, pp_b, pl_b = b["p_under"], b["p_push"], b["p_over"]
    p_both_win = pw_a * pw_b
    p_one_win_one_push = pw_a * pp_b + pp_a * pw_b
    p_split = pw_a * pl_b + pl_a * pw_b
    p_one_lose_one_push = pl_a * pp_b + pp_a * pl_b
    p_both_lose = pl_a * pl_b
    # EV = p_both_win·(O-1) + p_one_win_one_push·(O-1)/2 - p_split/2
    #      - p_one_lose_one_push·1 - p_both_lose·1 = 0
    coeff_O = p_both_win + 0.5 * p_one_win_one_push
    const = -(p_both_win + 0.5 * p_one_win_one_push) - 0.5 * p_split \
            - p_one_lose_one_push - p_both_lose
    if coeff_O <= 1e-9:
        return None
    return round(-const / coeff_O, 3)


# -- Convenience: standard line set per match --------------------------------

def derive_all(lam_h: float, lam_a: float, rho: float,
               ah_lines: tuple[float, ...] = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0),
               ou_lines: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0),
               max_goals: int = 10) -> dict:
    """Standard AH + OU line ladder for one fixture, ready for dashboard /
    Kelly comparison against bookmaker prices."""
    return {
        "asian_handicap": [asian_handicap(lam_h, lam_a, rho, ln, max_goals)
                           for ln in ah_lines],
        "over_under": [over_under(lam_h, lam_a, rho, ln, max_goals)
                       for ln in ou_lines],
    }
