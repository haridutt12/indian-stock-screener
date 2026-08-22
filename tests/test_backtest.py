"""Smoke tests for backtest simulation — focused on look-ahead bias."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import datetime
import pandas as pd
from unittest.mock import patch
from analysis.backtest import simulate_signal, backtest_summary


def _make_ohlc(dates_closes: list[tuple]) -> pd.DataFrame:
    """Build a minimal OHLC DataFrame for testing."""
    rows = []
    for d, close in dates_closes:
        rows.append({
            "Open": close * 0.99, "High": close * 1.01,
            "Low": close * 0.98, "Close": close, "Volume": 1_000_000,
        })
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in dates_closes])
    return pd.DataFrame(rows, index=idx)


def test_signal_day_bar_skipped():
    """A target hit on the signal day itself must NOT be counted as a win."""
    signal_date = "2024-01-02"
    # Day 0 (signal day): High = 115 — would trigger T1 (110) if not skipped
    # Day 1 (next session): High = 105 — below T1
    df = _make_ohlc([
        ("2024-01-02", 100.0),   # signal day — must be skipped
        ("2024-01-03", 103.0),   # next session — price moves but no trigger
        ("2024-01-04", 103.5),
    ])

    # Patch _fetch_ohlc to return our controlled DataFrame
    with patch("analysis.backtest._fetch_ohlc", return_value=df):
        result = simulate_signal(
            ticker="TEST.NS",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=120.0,
            signal_date=signal_date,
            max_days=5,
        )

    # Should expire (no trigger), NOT hit TARGET1 on the signal day
    assert result.get("simulated_outcome") == "EXPIRED", (
        f"Expected EXPIRED but got {result.get('simulated_outcome')} — "
        "signal-day bar was not skipped (look-ahead bias)"
    )


def test_target_hit_next_session():
    """A target hit on the session after the signal day counts correctly."""
    signal_date = "2024-01-02"
    df = _make_ohlc([
        ("2024-01-02", 100.0),   # signal day — skipped
        ("2024-01-03", 111.0),   # next session: High ~112 ≥ T1 (110)
    ])
    # Adjust High explicitly to ensure the trigger fires
    df.iloc[1, df.columns.get_loc("High")] = 112.0

    with patch("analysis.backtest._fetch_ohlc", return_value=df):
        result = simulate_signal(
            ticker="TEST.NS",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=120.0,
            signal_date=signal_date,
            max_days=5,
        )

    assert result.get("simulated_outcome") == "TARGET1_HIT"


def test_stop_loss_hit():
    signal_date = "2024-01-02"
    df = _make_ohlc([
        ("2024-01-02", 100.0),
        ("2024-01-03",  94.0),   # Low ~92 ≤ SL (95)
    ])
    df.iloc[1, df.columns.get_loc("Low")] = 92.0

    with patch("analysis.backtest._fetch_ohlc", return_value=df):
        result = simulate_signal(
            ticker="TEST.NS",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=120.0,
            signal_date=signal_date,
            max_days=5,
        )

    assert result.get("simulated_outcome") == "STOPPED"
    assert result.get("pnl_r") == -1.0


def test_short_target_hit():
    signal_date = "2024-01-02"
    df = _make_ohlc([
        ("2024-01-02", 100.0),
        ("2024-01-03",  88.0),   # Low ~86 ≤ T1 (90) for SHORT
    ])
    df.iloc[1, df.columns.get_loc("Low")] = 86.0

    with patch("analysis.backtest._fetch_ohlc", return_value=df):
        result = simulate_signal(
            ticker="TEST.NS",
            direction="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            target_1=90.0,
            target_2=80.0,
            signal_date=signal_date,
            max_days=5,
        )

    assert result.get("simulated_outcome") == "TARGET1_HIT"
    assert result.get("pnl_r") > 0


def test_backtest_summary_empty():
    assert backtest_summary(pd.DataFrame()) == {}


def test_backtest_summary_metrics():
    rows = [
        {"sim_pnl_r": 2.0,  "sim_bars": 3},
        {"sim_pnl_r": -1.0, "sim_bars": 2},
        {"sim_pnl_r": 1.5,  "sim_bars": 4},
    ]
    df = pd.DataFrame(rows)
    s = backtest_summary(df)
    assert s["total"] == 3
    assert s["wins"] == 2
    assert s["losses"] == 1
    assert abs(s["win_rate"] - 66.7) < 0.1
    assert s["pf"] is not None
    assert s["pf"] > 1.0
