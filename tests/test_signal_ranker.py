"""Smoke tests for signal ranking logic."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import datetime
from signals.signal_ranker import score_signal, _entry_timing_score, _age_penalty, _sl_breached


def _make_sig(
    ticker="RELIANCE.NS", direction="LONG",
    entry=100.0, sl=95.0, t1=110.0, t2=120.0,
    rr=2.0, confidence=3, tech=0.7, fund=0.6,
    timeframe="SWING", signal_date=None,
):
    if signal_date is None:
        signal_date = datetime.date.today().isoformat()
    return {
        "ticker": ticker, "direction": direction,
        "entry_price": entry, "stop_loss": sl,
        "target_1": t1, "target_2": t2,
        "risk_reward": rr, "confidence": confidence,
        "technical_score": tech, "fundamental_score": fund,
        "timeframe": timeframe, "signal_date": signal_date,
    }


def test_score_at_entry_is_near_max():
    sig = _make_sig(entry=100.0)
    score, bd = score_signal(sig, curr_price=100.0)
    # At entry with RR=2, conf=3, tech=0.7, fund=0.6 — no age penalty
    assert score > 60
    assert bd["Entry Timing"] == 20.0


def test_sl_breached_long():
    sig = _make_sig(entry=100.0, sl=95.0, direction="LONG")
    assert _sl_breached(sig, curr_price=94.9) is True
    assert _sl_breached(sig, curr_price=95.0) is True
    assert _sl_breached(sig, curr_price=95.1) is False


def test_sl_breached_short():
    sig = _make_sig(entry=100.0, sl=105.0, direction="SHORT")
    assert _sl_breached(sig, curr_price=105.1) is True
    assert _sl_breached(sig, curr_price=104.9) is False


def test_sl_breached_none_price():
    sig = _make_sig()
    assert _sl_breached(sig, curr_price=None) is False


def test_entry_timing_decay():
    # Score should decay as price moves away from entry
    assert _entry_timing_score(0.0) == 20.0
    assert _entry_timing_score(1.0) < 20.0
    assert _entry_timing_score(3.0) < _entry_timing_score(1.0)
    assert _entry_timing_score(7.0) < 1.0  # near zero at 7%


def test_entry_timing_no_penalty_below_entry():
    assert _entry_timing_score(-5.0) == 20.0


def test_age_penalty_swing_grace():
    today = datetime.date.today()
    # 3 days old — still in grace period for SWING
    d3 = (today - datetime.timedelta(days=3)).isoformat()
    sig = _make_sig(signal_date=d3, timeframe="SWING")
    assert _age_penalty(sig) == 0.0


def test_age_penalty_swing_after_grace():
    today = datetime.date.today()
    d5 = (today - datetime.timedelta(days=5)).isoformat()
    sig = _make_sig(signal_date=d5, timeframe="SWING")
    # 5 days old, grace=3, rate=1/day → penalty=2
    assert _age_penalty(sig) == 2.0


def test_age_penalty_intraday_after_grace():
    today = datetime.date.today()
    d3 = (today - datetime.timedelta(days=3)).isoformat()
    sig = _make_sig(signal_date=d3, timeframe="INTRADAY")
    # 3 days old, grace=1, rate=2/day → penalty=4 (capped at 10)
    assert _age_penalty(sig) == 4.0


def test_age_penalty_capped_at_10():
    today = datetime.date.today()
    d30 = (today - datetime.timedelta(days=30)).isoformat()
    sig = _make_sig(signal_date=d30, timeframe="SWING")
    assert _age_penalty(sig) == 10.0


def test_score_components_sum_to_total():
    sig = _make_sig()
    score, bd = score_signal(sig, curr_price=100.0)
    component_sum = (
        bd["Confidence"] + bd["Technical"] + bd["Fundamental"]
        + bd["Risk/Reward"] + bd["Entry Timing"]
    )
    assert abs(component_sum - score) < 0.01


def test_score_bounded_0_100():
    sig = _make_sig(confidence=5, tech=1.0, fund=1.0, rr=5.0)
    score, _ = score_signal(sig, curr_price=100.0)
    assert 0 <= score <= 100


def test_score_without_price():
    sig = _make_sig()
    score, bd = score_signal(sig, curr_price=None)
    # Entry Timing defaults to 10 when price is unavailable
    assert bd["Entry Timing"] <= 10.0
    assert score > 0
