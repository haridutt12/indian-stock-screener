"""
Realistic NSE equity transaction cost calculator.

Rates current as of 2024-25 (NSE, discount broker / flat-fee model):

  Brokerage       : ₹20 per executed order (flat), each leg
  STT             : Intraday 0.025% sell-side | Delivery 0.1% both sides
  Exchange (NSE)  : 0.00345% of turnover
  SEBI charges    : 0.0001% of turnover  (₹10 per crore)
  Stamp duty      : Intraday 0.003% buy-side | Delivery 0.015% buy-side
  GST             : 18% on (brokerage + exchange + SEBI)

Default position size ₹1,00,000 (₹1 lakh) — change via POSITION_SIZE_INR in config.

Usage::

    from signals.trade_costs import compute_trade_cost
    cost = compute_trade_cost(
        entry_price=2500.0, exit_price=2550.0,
        direction="LONG", timeframe="INTRADAY",
    )
    print(cost["net_pnl_inr"], cost["cost_total_inr"])
"""

from __future__ import annotations

# Default position size in INR (₹1 lakh).
# Users with larger accounts can adjust this; all P&L figures scale proportionally.
DEFAULT_POSITION_SIZE_INR: float = 100_000.0

# Brokerage per order leg (INR, flat fee — Zerodha / Upstox / similar)
BROKERAGE_PER_LEG: float = 20.0

# STT rates
STT_INTRADAY_SELL: float = 0.00025     # 0.025 % — sell side only
STT_DELIVERY_BOTH: float = 0.001       # 0.1 %   — buy + sell

# NSE exchange transaction charge
EXCHANGE_CHARGE_RATE: float = 0.0000345  # 0.00345 %

# SEBI turnover fee
SEBI_CHARGE_RATE: float = 0.000001      # 0.0001 %

# Stamp duty
STAMP_INTRADAY_BUY: float = 0.00003    # 0.003 % — buy side only
STAMP_DELIVERY_BUY: float = 0.00015   # 0.015 % — buy side only

# GST on brokerage + exchange + SEBI
GST_RATE: float = 0.18


def compute_trade_cost(
    entry_price: float,
    exit_price: float,
    direction: str,                      # "LONG" or "SHORT"
    timeframe: str,                      # "INTRADAY" or "SWING"
    position_size_inr: float = DEFAULT_POSITION_SIZE_INR,
    stop_loss: float | None = None,      # used to express net_pnl in R-multiples
) -> dict:
    """
    Compute a full cost breakdown and net P&L for a round-trip trade.

    Args:
        entry_price       : Signal entry price (INR per share)
        exit_price        : Actual exit / resolution price
        direction         : "LONG" or "SHORT"
        timeframe         : "INTRADAY" or "SWING"
        position_size_inr : Capital deployed (default ₹1 lakh)
        stop_loss         : Original stop-loss price (for R-multiple calc)

    Returns a dict with individual cost lines, totals, gross/net P&L, and R-multiple.
    """
    if entry_price <= 0:
        return _zero_cost(position_size_inr)

    qty = position_size_inr / entry_price   # shares bought/sold

    # Turnover values
    entry_value = qty * entry_price
    exit_value  = qty * exit_price
    turnover    = entry_value + exit_value

    # ── Identify buy/sell sides ───────────────────────────────────────────────
    if direction == "LONG":
        buy_value  = entry_value
        sell_value = exit_value
    else:  # SHORT: sell at entry, buy back at exit
        sell_value = entry_value
        buy_value  = exit_value

    # ── Brokerage ─────────────────────────────────────────────────────────────
    # ₹20 per leg but also capped at 0.03% of trade value (SEBI rule)
    brokerage_entry = min(BROKERAGE_PER_LEG, 0.0003 * entry_value)
    brokerage_exit  = min(BROKERAGE_PER_LEG, 0.0003 * exit_value)
    brokerage       = brokerage_entry + brokerage_exit

    # ── STT ───────────────────────────────────────────────────────────────────
    if timeframe == "INTRADAY":
        stt = STT_INTRADAY_SELL * sell_value
    else:
        stt = STT_DELIVERY_BOTH * turnover

    # ── Exchange transaction charges ──────────────────────────────────────────
    exchange_charges = EXCHANGE_CHARGE_RATE * turnover

    # ── SEBI fees ─────────────────────────────────────────────────────────────
    sebi_charges = SEBI_CHARGE_RATE * turnover

    # ── Stamp duty ────────────────────────────────────────────────────────────
    if timeframe == "INTRADAY":
        stamp_duty = STAMP_INTRADAY_BUY * buy_value
    else:
        stamp_duty = STAMP_DELIVERY_BUY * buy_value

    # ── GST (18 % on brokerage + exchange + SEBI) ─────────────────────────────
    gst = GST_RATE * (brokerage + exchange_charges + sebi_charges)

    # ── Totals ────────────────────────────────────────────────────────────────
    cost_total = brokerage + stt + exchange_charges + stamp_duty + sebi_charges + gst

    # ── Gross P&L ─────────────────────────────────────────────────────────────
    if direction == "LONG":
        gross_pnl = exit_value - entry_value
    else:
        gross_pnl = entry_value - exit_value

    net_pnl     = gross_pnl - cost_total
    net_pnl_pct = (net_pnl / entry_value) * 100

    # ── R-multiple (net) ──────────────────────────────────────────────────────
    net_pnl_r: float | None = None
    if stop_loss is not None and stop_loss != entry_price:
        risk_per_share = abs(entry_price - stop_loss)
        risk_inr       = risk_per_share * qty
        net_pnl_r      = round(net_pnl / risk_inr, 3) if risk_inr > 0 else None

    return {
        # Cost breakdown
        "brokerage_inr":       round(brokerage, 2),
        "stt_inr":             round(stt, 2),
        "exchange_charges_inr": round(exchange_charges, 2),
        "stamp_duty_inr":      round(stamp_duty, 2),
        "sebi_charges_inr":    round(sebi_charges, 4),
        "gst_inr":             round(gst, 2),
        "cost_total_inr":      round(cost_total, 2),
        "cost_total_pct":      round(cost_total / entry_value * 100, 4),
        # P&L
        "qty":                 round(qty, 4),
        "position_size_inr":   round(position_size_inr, 2),
        "gross_pnl_inr":       round(gross_pnl, 2),
        "net_pnl_inr":         round(net_pnl, 2),
        "net_pnl_pct":         round(net_pnl_pct, 4),
        "net_pnl_r":           net_pnl_r,
    }


def _zero_cost(position_size_inr: float) -> dict:
    """Return a blank cost dict when prices are invalid."""
    return {
        "brokerage_inr": 0.0, "stt_inr": 0.0,
        "exchange_charges_inr": 0.0, "stamp_duty_inr": 0.0,
        "sebi_charges_inr": 0.0, "gst_inr": 0.0,
        "cost_total_inr": 0.0, "cost_total_pct": 0.0,
        "qty": 0.0, "position_size_inr": position_size_inr,
        "gross_pnl_inr": 0.0, "net_pnl_inr": 0.0,
        "net_pnl_pct": 0.0, "net_pnl_r": None,
    }
