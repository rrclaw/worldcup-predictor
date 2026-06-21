"""Tests for the betting payload builder in cli.py (P2.1)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from skill.helpers import cli, paths


def _make_slate(tmp: Path, date: str, bets: list[dict], bankroll: float = 10000.0):
    bets_dir = tmp / "bets"
    bets_dir.mkdir(parents=True, exist_ok=True)
    (bets_dir / f"{date}.json").write_text(json.dumps({
        "date": date, "bankroll": bankroll, "bets": bets,
    }))


def _stub_fetch_historical(matches: list[tuple]) -> pd.DataFrame:
    """matches = [(date, home, away, hs, as_), ...]."""
    cols = ["date", "home_team", "away_team", "home_score", "away_score", "tournament"]
    if not matches:
        return pd.DataFrame({c: [] for c in cols}).astype({"date": "datetime64[ns]"})
    return pd.DataFrame([
        {"date": pd.Timestamp(d), "home_team": h, "away_team": a,
         "home_score": hs, "away_score": as_, "tournament": paths.WC2026_TOURNAMENT}
        for (d, h, a, hs, as_) in matches
    ])


def test_no_bets_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    out = cli._betting_payload("2026-06-19")
    assert out == {"today": None, "history": [], "cumulative": None}


def test_today_slate_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · 1X2 home", "p_win": 0.5, "decimal_odds": 2.5,
         "edge": 0.1, "kelly_fraction": 0.025, "stake": 250.0, "market": "1x2"},
    ])
    with patch.object(cli.data_loader, "fetch_historical", return_value=_stub_fetch_historical([])):
        out = cli._betting_payload("2026-06-19")
    assert out["today"] is not None
    assert len(out["today"]["bets"]) == 1
    assert out["today"]["bets"][0]["label"] == "FRA vs ENG · 1X2 home"


def test_settlement_winning_bet(tmp_path, monkeypatch):
    """A 250 stake at 2.5 odds on a winning home pick → +375 profit."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · 1X2 home", "p_win": 0.5, "decimal_odds": 2.5,
         "edge": 0.1, "kelly_fraction": 0.025, "stake": 250.0, "market": "1x2"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")  # next-day publish settles yesterday
    assert out["cumulative"]["n_settled"] == 1
    assert out["cumulative"]["total_pnl"] == 375.0
    assert out["cumulative"]["total_stake"] == 250.0
    assert out["cumulative"]["roi"] == 1.5
    assert out["cumulative"]["max_drawdown"] == 0.0
    assert out["cumulative"]["current_bankroll"] == 10375.0


def test_settlement_losing_bet(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · 1X2 home", "p_win": 0.5, "decimal_odds": 2.5,
         "edge": 0.1, "kelly_fraction": 0.025, "stake": 250.0, "market": "1x2"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 0, 2)])  # away win
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == -250.0
    assert out["cumulative"]["roi"] == -1.0
    assert out["cumulative"]["current_bankroll"] == 9750.0


def test_max_drawdown_tracked(tmp_path, monkeypatch):
    """Win, lose, lose → peak after first day, drawdown after losses."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "A vs B · 1X2 home", "decimal_odds": 2.0, "stake": 1000.0, "market": "1x2"},
    ])
    _make_slate(tmp_path, "2026-06-20", [
        {"label": "C vs D · 1X2 home", "decimal_odds": 2.0, "stake": 1000.0, "market": "1x2"},
    ])
    _make_slate(tmp_path, "2026-06-21", [
        {"label": "E vs F · 1X2 home", "decimal_odds": 2.0, "stake": 1000.0, "market": "1x2"},
    ])
    matches = _stub_fetch_historical([
        ("2026-06-19", "A", "B", 2, 0),  # win:  bankroll 10000 → 11000 (peak)
        ("2026-06-20", "C", "D", 0, 1),  # loss: 11000 → 10000 (DD = 1000/11000 ≈ 0.0909)
        ("2026-06-21", "E", "F", 0, 1),  # loss: 10000 → 9000  (DD = 2000/11000 ≈ 0.1818)
    ])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-22")
    assert out["cumulative"]["n_settled"] == 3
    assert out["cumulative"]["current_bankroll"] == 9000.0
    assert abs(out["cumulative"]["max_drawdown"] - 2000 / 11000) < 1e-3


def test_unsettled_match_skipped(tmp_path, monkeypatch):
    """Bet on a match with no recorded result must NOT enter settlement."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "X vs Y · 1X2 home", "decimal_odds": 2.0, "stake": 1000.0, "market": "1x2"},
    ])
    with patch.object(cli.data_loader, "fetch_historical", return_value=_stub_fetch_historical([])):
        out = cli._betting_payload("2026-06-20")
    assert out["history"] == []
    assert out["cumulative"] is None


def test_ah_settlement_home_wins(tmp_path, monkeypatch):
    """AH -0.5 home: FRA wins 2-0 → home covers → profit = stake × (odds-1)."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH -0.5 home", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ah_minus_0.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 0)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["n_settled"] == 1
    assert abs(out["cumulative"]["total_pnl"] - 180.0) < 0.01  # 200 × (1.9−1)
    assert out["cumulative"]["current_bankroll"] == pytest.approx(10180.0, abs=0.01)


def test_ah_settlement_home_loses(tmp_path, monkeypatch):
    """AH -0.5 home: FRA loses 0-1 → home does not cover → lose stake."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH -0.5 home", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ah_minus_0.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 0, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == -200.0
    assert out["cumulative"]["current_bankroll"] == pytest.approx(9800.0, abs=0.01)


def test_ah_settlement_draw_is_loss_for_minus_half(tmp_path, monkeypatch):
    """AH -0.5 home: draw 1-1 → home does not cover (-0.5 line) → lose stake."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH -0.5 home", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ah_minus_0.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 1, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == -200.0


def test_ah_settlement_plus_half_draw_wins(tmp_path, monkeypatch):
    """AH +0.5 home: draw 1-1 → home covers (+0.5 line) → profit."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH +0.5 home", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ah_plus_0.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 1, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == pytest.approx(180.0, abs=0.01)


def test_ah_integer_push_refunds_stake(tmp_path, monkeypatch):
    """AH 0 home, draw 1-1: margin=0 → adjusted=0 → push, stake refunded."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH 0 home", "decimal_odds": 2.0, "stake": 200.0,
         "market": "ah_0"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 1, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["n_settled"] == 1
    assert out["cumulative"]["total_pnl"] == 0.0  # push, no profit/loss


def test_ah_minus_1_integer_home_wins_by_2(tmp_path, monkeypatch):
    """AH -1 home, win 2-0: margin=2, adjusted=1>0 → home covers."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH -1 home", "decimal_odds": 2.0, "stake": 200.0,
         "market": "ah_minus_1"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 0)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == 200.0


def test_ah_minus_1_integer_home_wins_by_1_pushes(tmp_path, monkeypatch):
    """AH -1 home, win 1-0: margin=1, adjusted=0 → push."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · AH -1 home", "decimal_odds": 2.0, "stake": 200.0,
         "market": "ah_minus_1"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 1, 0)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == 0.0


def test_ou_2_5_over_wins(tmp_path, monkeypatch):
    """OU 2.5 over, total goals 3 → over wins."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · OU 2.5 over", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ou_2.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == pytest.approx(180.0, abs=0.01)


def test_ou_2_5_under_loses_when_total_3(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · OU 2.5 under", "decimal_odds": 1.9, "stake": 200.0,
         "market": "ou_2.5"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == -200.0


def test_ou_3_integer_total_3_pushes(tmp_path, monkeypatch):
    """OU 3 over, total 3 → push, stake refunded."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · OU 3 over", "decimal_odds": 2.0, "stake": 200.0,
         "market": "ou_3"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"]["total_pnl"] == 0.0


def test_unknown_market_label_skipped(tmp_path, monkeypatch):
    """Unknown market label (e.g. BTTS) must skip, not crash."""
    monkeypatch.setattr(paths, "REPORTS", tmp_path)
    _make_slate(tmp_path, "2026-06-19", [
        {"label": "FRA vs ENG · BTTS yes", "decimal_odds": 1.9, "stake": 200.0,
         "market": "btts"},
    ])
    matches = _stub_fetch_historical([("2026-06-19", "FRA", "ENG", 2, 1)])
    with patch.object(cli.data_loader, "fetch_historical", return_value=matches):
        out = cli._betting_payload("2026-06-20")
    assert out["cumulative"] is None


if __name__ == "__main__":
    import inspect
    import tempfile
    failures = 0
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in fns:
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)

                class _M:
                    def setattr(self, obj, attr, value):
                        if not hasattr(self, "_saved"):
                            self._saved = []
                        self._saved.append((obj, attr, getattr(obj, attr)))
                        setattr(obj, attr, value)

                    def restore(self):
                        for obj, attr, val in reversed(getattr(self, "_saved", [])):
                            setattr(obj, attr, val)
                m = _M()
                try:
                    fn(tmp, m)
                finally:
                    m.restore()
            print(f"  ok  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    raise SystemExit(failures)
