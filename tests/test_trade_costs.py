"""Smoke tests for trade cost calculation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from signals.trade_costs import compute_trade_cost, DEFAULT_POSITION_SIZE_INR


def test_long_intraday_costs_are_positive():
    r = compute_trade_cost(100.0, 102.0, "LONG", "INTRADAY")
    assert r["cost_total_inr"] > 0
    assert r["gross_pnl_inr"] > 0
    assert r["net_pnl_inr"] < r["gross_pnl_inr"]


def test_long_swing_costs_higher_than_intraday():
    r_intra = compute_trade_cost(500.0, 510.0, "LONG", "INTRADAY")
    r_swing = compute_trade_cost(500.0, 510.0, "LONG", "SWING")
    # Delivery STT (0.1% both sides) > intraday STT (0.025% sell only)
    assert r_swing["stt_inr"] > r_intra["stt_inr"]


def test_losing_trade_net_pnl_negative():
    r = compute_trade_cost(100.0, 95.0, "LONG", "SWING", stop_loss=95.0)
    assert r["net_pnl_inr"] < 0
    assert r["net_pnl_r"] is not None
    assert r["net_pnl_r"] < 0


def test_short_winning_trade():
    r = compute_trade_cost(200.0, 190.0, "SHORT", "INTRADAY", stop_loss=210.0)
    assert r["gross_pnl_inr"] > 0
    assert r["net_pnl_inr"] > 0
    assert r["net_pnl_r"] is not None and r["net_pnl_r"] > 0


def test_r_multiple_calculation():
    # Entry 100, SL 95, T1 110 → risk = 5, gain = 10 → gross R = 2.0
    r = compute_trade_cost(100.0, 110.0, "LONG", "SWING", stop_loss=95.0)
    assert r["net_pnl_r"] is not None
    # Net R should be slightly below 2.0 after costs
    assert 1.5 < r["net_pnl_r"] < 2.0


def test_zero_entry_price_returns_zero_cost():
    r = compute_trade_cost(0.0, 100.0, "LONG", "SWING")
    assert r["cost_total_inr"] == 0.0
    assert r["net_pnl_inr"] == 0.0


def test_cost_components_sum_to_total():
    r = compute_trade_cost(250.0, 260.0, "LONG", "SWING")
    component_sum = (
        r["brokerage_inr"] + r["stt_inr"] + r["exchange_charges_inr"]
        + r["stamp_duty_inr"] + r["sebi_charges_inr"] + r["gst_inr"]
        + r["slippage_inr"]
    )
    assert abs(component_sum - r["cost_total_inr"]) < 0.01


def test_zero_slippage_is_lower_than_default():
    r_default  = compute_trade_cost(100.0, 105.0, "LONG", "SWING")
    r_no_slip  = compute_trade_cost(100.0, 105.0, "LONG", "SWING", slippage_rate=0.0)
    assert r_default["cost_total_inr"] > r_no_slip["cost_total_inr"]
    assert r_no_slip["slippage_inr"] == 0.0


def test_slippage_present_in_zero_entry_result():
    r = compute_trade_cost(0.0, 100.0, "LONG", "SWING")
    assert "slippage_inr" in r
    assert r["slippage_inr"] == 0.0


def test_default_position_size_used():
    r = compute_trade_cost(100.0, 105.0, "LONG", "SWING")
    assert abs(r["position_size_inr"] - DEFAULT_POSITION_SIZE_INR) < 0.01


def test_custom_position_size():
    r = compute_trade_cost(100.0, 105.0, "LONG", "SWING", position_size_inr=500_000)
    assert abs(r["position_size_inr"] - 500_000) < 0.01
