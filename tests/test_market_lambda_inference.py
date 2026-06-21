"""Tests for 1X2 → market-implied λ inference (industry-standard AH/OU pricing)."""
from __future__ import annotations

from skill.model.derived_markets import (
    _dc_1x2,
    infer_market_lambdas,
    round_to_half,
)


def _approx(a: float, b: float, eps: float = 1e-3) -> bool:
    return abs(a - b) < eps


def test_inference_recovers_dc_lambdas_zero_rho():
    """If the 1X2 input came from DC itself, inversion must recover the same λ."""
    lam_h, lam_a, rho = 1.6, 0.9, 0.0
    p1x2 = _dc_1x2(lam_h, lam_a, rho)
    out = infer_market_lambdas(p1x2, lam_h_dc=1.5, lam_a_dc=1.0, rho=rho)
    assert out is not None
    lh_m, la_m = out
    assert _approx(lh_m, lam_h, eps=1e-3)
    assert _approx(la_m, lam_a, eps=1e-3)


def test_inference_recovers_with_negative_rho():
    """ρ < 0 (DC's low-score correction) must be preserved through inversion."""
    lam_h, lam_a, rho = 1.4, 1.1, -0.08
    p1x2 = _dc_1x2(lam_h, lam_a, rho)
    out = infer_market_lambdas(p1x2, lam_h_dc=1.3, lam_a_dc=1.2, rho=rho)
    assert out is not None
    lh_m, la_m = out
    assert _approx(lh_m, lam_h, eps=2e-3)
    assert _approx(la_m, lam_a, eps=2e-3)


def test_inference_handles_market_diverging_from_model():
    """Market favours away more than DC does → inferred λ_a > λ_a^DC."""
    # DC fits a balanced 1.4 vs 1.0 game, but market thinks underdog stronger
    market_1x2 = (0.40, 0.27, 0.33)  # away has more weight than balanced 1.4/1.0 would give
    out = infer_market_lambdas(market_1x2, lam_h_dc=1.4, lam_a_dc=1.0, rho=-0.05)
    assert out is not None
    lh_m, la_m = out
    # away should infer higher than the DC starting point
    assert la_m > 1.0


def test_inference_returns_none_on_invalid_sum():
    assert infer_market_lambdas((0.5, 0.3, 0.5), 1.0, 1.0, 0.0) is None


def test_inference_returns_none_on_negative_prob():
    assert infer_market_lambdas((0.6, -0.1, 0.5), 1.0, 1.0, 0.0) is None


def test_inference_returns_none_on_wrong_shape():
    assert infer_market_lambdas((0.5, 0.5), 1.0, 1.0, 0.0) is None
    assert infer_market_lambdas((0.3, 0.3, 0.3, 0.1), 1.0, 1.0, 0.0) is None


def test_inference_low_scoring_match():
    """Defensive game (e.g. 0.7 vs 0.5) → 1X2 still invertible."""
    lam_h, lam_a, rho = 0.7, 0.5, -0.07
    p1x2 = _dc_1x2(lam_h, lam_a, rho)
    out = infer_market_lambdas(p1x2, lam_h_dc=0.9, lam_a_dc=0.9, rho=rho)
    assert out is not None
    lh_m, la_m = out
    assert _approx(lh_m, lam_h, eps=3e-3)
    assert _approx(la_m, lam_a, eps=3e-3)


def test_inference_renormalises_small_rounding_error():
    """1X2 sums to 0.999 (rounding) → inversion still works."""
    lam_h, lam_a, rho = 1.5, 1.0, 0.0
    ph, pd, pa = _dc_1x2(lam_h, lam_a, rho)
    # introduce a tiny rounding so sum ≠ 1
    p1x2 = (round(ph, 3), round(pd, 3), round(pa, 3))
    out = infer_market_lambdas(p1x2, lam_h_dc=lam_h, lam_a_dc=lam_a, rho=rho)
    assert out is not None


def test_round_to_half():
    assert round_to_half(1.2) == 1.0
    assert round_to_half(1.3) == 1.5
    assert round_to_half(2.7) == 2.5
    assert round_to_half(2.8) == 3.0
    assert round_to_half(-0.4) == -0.5
    assert round_to_half(0.0) == 0.0


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
        except Exception as e:
            failures += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    raise SystemExit(failures)
