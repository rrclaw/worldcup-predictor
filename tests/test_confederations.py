"""Tests for `skill.model.confederations` lookup + `context.py` cross-confed factor."""
from __future__ import annotations

import math

from skill.model.confederations import (
    confederation, is_cross_confederation, confed_pair,
)
from skill.model.context import _confed_adjustment, CROSS_CONFED_GAP


def test_confederation_lookup():
    assert confederation("France") == "UEFA"
    assert confederation("Brazil") == "CONMEBOL"
    assert confederation("Mexico") == "CONCACAF"
    assert confederation("Saudi Arabia") == "AFC"
    assert confederation("Senegal") == "CAF"
    assert confederation("New Zealand") == "OFC"
    assert confederation("Atlantis") is None


def test_alias_coverage():
    """Country names with multiple historical / vendor spellings all resolve."""
    # Aliases must agree with each other (same confederation)
    assert confederation("South Korea") == confederation("Korea Republic") == "AFC"
    assert confederation("Türkiye") == confederation("Turkey") == "UEFA"
    assert confederation("Cabo Verde") == confederation("Cape Verde") == "CAF"
    assert confederation("Czech Republic") == confederation("Czechia") == "UEFA"
    # Common spellings that historically split across data sources
    assert confederation("United States") == "CONCACAF"
    assert confederation("Republic of Ireland") == confederation("Ireland") == "UEFA"


def test_cross_confederation_predicate():
    assert is_cross_confederation("France", "Saudi Arabia") is True
    assert is_cross_confederation("Brazil", "Mexico") is True
    assert is_cross_confederation("France", "Italy") is False
    assert is_cross_confederation("France", "Atlantis") is False  # unknown → no claim


def test_confed_pair_helper():
    assert confed_pair("France", "Italy") == ("UEFA", "UEFA")
    assert confed_pair("Mexico", "Atlantis") == ("CONCACAF", None)


def test_adjustment_strong_vs_weak():
    """UEFA (home) vs AFC (away) → home gets exp(+gap/2), away gets exp(-gap/2)."""
    lam_m, mu_m = _confed_adjustment("France", "Saudi Arabia")
    expected_strong = math.exp(CROSS_CONFED_GAP / 2)
    expected_weak = math.exp(-CROSS_CONFED_GAP / 2)
    assert abs(lam_m - expected_strong) < 1e-9
    assert abs(mu_m - expected_weak) < 1e-9


def test_adjustment_swapped_orientation():
    """AFC (home) vs UEFA (away) → away is the strong side."""
    lam_m, mu_m = _confed_adjustment("Saudi Arabia", "France")
    expected_strong = math.exp(CROSS_CONFED_GAP / 2)
    expected_weak = math.exp(-CROSS_CONFED_GAP / 2)
    assert abs(lam_m - expected_weak) < 1e-9
    assert abs(mu_m - expected_strong) < 1e-9


def test_adjustment_same_confed_noop():
    assert _confed_adjustment("France", "Italy") == (1.0, 1.0)
    assert _confed_adjustment("Brazil", "Argentina") == (1.0, 1.0)


def test_adjustment_uefa_vs_conmebol_noop():
    """Both in STRONG_CONFEDS but different — no a-priori sign in literature, leave to DC."""
    assert _confed_adjustment("France", "Brazil") == (1.0, 1.0)


def test_adjustment_unknown_country_noop():
    assert _confed_adjustment("France", "Atlantis") == (1.0, 1.0)


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
