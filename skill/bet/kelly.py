"""Kelly-criterion stake sizing for value bets.

Convention: every "opportunity" describes a single binary settlement
(`p_win` of payout `decimal_odds − 1` per unit stake, otherwise lose 1 unit).
Push-bearing markets (AH integer / OU integer) must be reduced to that form
upstream — see `derived_markets._fair_odds` for the standard reduction.

Discipline (per .claude/plans/optimization_backlog.md §9):
  * default fraction = 0.25 (quarter Kelly) — guards against parameter error
  * single-bet cap     = 5% of bankroll
  * portfolio cap      = 30% of bankroll across all simultaneous bets
  * edge gate          = 3% (model prob − implied market prob) — below this we don't bet
  * minimum stake      = 0.5% of bankroll — sub-noise signals dropped
"""
from __future__ import annotations

from dataclasses import dataclass


# Doctrine constants — change only with a documented backtest decision.
DEFAULT_KELLY_FRACTION = 0.25
DEFAULT_MAX_PER_BET = 0.05      # 5% bankroll
DEFAULT_MAX_TOTAL = 0.30        # 30% bankroll
DEFAULT_EDGE_THRESHOLD = 0.03   # 3 percentage points
DEFAULT_MIN_FRACTION = 0.005    # 0.5% bankroll

# Per-market acceptance whitelist (FINDINGS.md Run 27 — P1.3).
# Markets that failed walk-forward calibration cannot be bet on regardless of
# how attractive any single edge looks: refusing them is the same anti-curve-
# fitting rule that protected the model in Runs 14/16/17.
MARKET_WHITELIST = {
    "1x2": True,         # validated headline metric (Run 23, ECE 0.0144)
    "ah_minus_1.5": True,
    "ah_minus_0.5": True,
    "ah_plus_0.5": True,
    "ah_plus_1.5": True,
    "ou_1.5": False,     # REJECTED — model Brier 0.005 worse than no-skill baseline
    "ou_2.5": True,      # marginally accepted; flag low-confidence in cli bet
    "ou_3.5": True,      # accepted but low-confidence
}


def is_whitelisted(market: str) -> bool:
    """Return True iff `market` is approved for stake sizing.

    Unknown markets default to False (fail closed) — adding a new market
    requires a backtest entry in FINDINGS.md and an explicit whitelist line.
    """
    return MARKET_WHITELIST.get(market.lower(), False)


@dataclass
class Opportunity:
    label: str           # human-readable e.g. "FRA vs ENG · AH -0.5 home"
    p_win: float         # model's calibrated win probability
    decimal_odds: float  # market decimal odds (or fair odds when no market)
    p_market: float | None = None  # de-vigged implied market prob, if known
    market: str = "1x2"  # whitelist key — see MARKET_WHITELIST


def kelly_fraction(p: float, decimal_odds: float, fraction: float = DEFAULT_KELLY_FRACTION) -> float:
    """Fractional Kelly. Returns 0 if no positive edge.

    Full Kelly: f* = (b·p − q) / b where b = decimal_odds − 1, q = 1 − p.
    """
    if decimal_odds <= 1.0 or not (0.0 < p < 1.0):
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - p
    f_full = (b * p - q) / b
    if f_full <= 0:
        return 0.0
    return f_full * fraction


def edge(p: float, decimal_odds: float) -> float:
    """Edge = model prob − implied market prob."""
    if decimal_odds <= 1.0:
        return 0.0
    return p - 1.0 / decimal_odds


def portfolio_kelly(
    opportunities: list[Opportunity],
    bankroll: float,
    fraction: float = DEFAULT_KELLY_FRACTION,
    max_per_bet: float = DEFAULT_MAX_PER_BET,
    max_total: float = DEFAULT_MAX_TOTAL,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
    min_fraction: float = DEFAULT_MIN_FRACTION,
) -> list[dict]:
    """Stake-size a slate of opportunities.

    Pipeline:
      1. drop opportunities with edge < threshold
      2. compute fractional Kelly per opportunity
      3. cap each at `max_per_bet`
      4. drop those below `min_fraction` (signal too weak)
      5. if sum > `max_total`, scale down proportionally

    Returns one row per accepted bet, sorted by stake descending.
    """
    accepted = []
    for op in opportunities:
        if not is_whitelisted(op.market):
            continue   # FINDINGS Run 27: rejected markets fail closed
        e = edge(op.p_win, op.decimal_odds)
        if e < edge_threshold:
            continue
        f = kelly_fraction(op.p_win, op.decimal_odds, fraction)
        f = min(f, max_per_bet)
        if f < min_fraction:
            continue
        accepted.append({
            "label": op.label, "market": op.market,
            "p_win": round(op.p_win, 4),
            "decimal_odds": op.decimal_odds, "edge": round(e, 4),
            "kelly_fraction": round(f, 4),
        })

    total = sum(r["kelly_fraction"] for r in accepted)
    if total > max_total and total > 0:
        scale = max_total / total
        for r in accepted:
            r["kelly_fraction"] = round(r["kelly_fraction"] * scale, 4)
            r["scaled_for_portfolio"] = True

    for r in accepted:
        r["stake"] = round(bankroll * r["kelly_fraction"], 2)

    accepted.sort(key=lambda r: -r["stake"])
    return accepted
