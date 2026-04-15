"""
Outcome Tracker: Resolves OPEN signals against actual price data.

Called by the post-market scheduler job (4:30 PM IST) to determine whether
each open signal hit its target, stopped out, or was squared off / expired.

Resolution logic
----------------
LONG signals:
  Stop takes priority on the same candle (conservative).
  STOPPED       : candle Low  <= stop_loss
  TARGET2_HIT   : candle High >= target_2  (checked after stop)
  TARGET1_HIT   : candle High >= target_1

SHORT signals:
  STOPPED       : candle High >= stop_loss
  TARGET2_HIT   : candle Low  <= target_2
  TARGET1_HIT   : candle Low  <= target_1

End-of-day rules
----------------
  INTRADAY : Any open position is SQUARED_OFF at the last 5-min candle's
             close price at market end (3:30 PM IST). No exceptions.
  SWING    : Position expires (EXPIRED) after SWING_EXPIRY_DAYS calendar days
             if no trigger fires. Exit price = last available daily close.

Transaction costs are computed for every resolved trade and stored alongside
the outcome so the dashboard shows realistic net P&L.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

from data.fetcher import fetch_single_stock
from signals.signal_logger import (
    get_signal_logger,
    OUTCOME_OPEN,
    OUTCOME_TARGET1,
    OUTCOME_TARGET2,
    OUTCOME_STOPPED,
    OUTCOME_SQUARED_OFF,
    OUTCOME_EXPIRED,
    SWING_EXPIRY_DAYS,
)
from signals.trade_costs import compute_trade_cost, DEFAULT_POSITION_SIZE_INR
from config.settings import (
    YFINANCE_PERIOD_INTRADAY,
    YFINANCE_INTERVAL_INTRADAY,
    YFINANCE_INTERVAL_DAILY,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pnl_r(entry: float, stop: float, exit_price: float, direction: str) -> float:
    """Gross risk-normalised P&L (R-multiple), before costs."""
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    if direction == "LONG":
        return round((exit_price - entry) / risk, 3)
    return round((entry - exit_price) / risk, 3)


def _resolve_candles(
    df: pd.DataFrame,
    direction: str,
    entry: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    from_dt: Optional[datetime] = None,
) -> Optional[dict]:
    """
    Walk candles in chronological order and return the first triggered outcome.

    Returns a dict with: outcome, price, at, max_gain_pct, max_loss_pct, pnl_r
    or None if no trigger found within the provided candles.
    """
    if df is None or df.empty:
        return None

    if from_dt is not None:
        if from_dt.tzinfo is None:
            from_dt = IST.localize(from_dt)
        idx = df.index
        if idx.tzinfo is None:
            idx = idx.tz_localize("UTC").tz_convert(IST)
        else:
            idx = idx.tz_convert(IST)
        df = df[idx >= from_dt]

    if df.empty:
        return None

    max_high = entry
    min_low  = entry

    for ts, row in df.iterrows():
        high = float(row["High"])
        low  = float(row["Low"])
        max_high = max(max_high, high)
        min_low  = min(min_low, low)

        if direction == "LONG":
            if low <= stop_loss:
                return _result(OUTCOME_STOPPED, stop_loss, ts, entry, max_high, min_low)
            if high >= target_2:
                return _result(OUTCOME_TARGET2, target_2, ts, entry, max_high, min_low)
            if high >= target_1:
                return _result(OUTCOME_TARGET1, target_1, ts, entry, max_high, min_low)
        else:  # SHORT
            if high >= stop_loss:
                return _result(OUTCOME_STOPPED, stop_loss, ts, entry, max_high, min_low)
            if low <= target_2:
                return _result(OUTCOME_TARGET2, target_2, ts, entry, max_high, min_low)
            if low <= target_1:
                return _result(OUTCOME_TARGET1, target_1, ts, entry, max_high, min_low)

    return None


def _result(outcome: str, price: float, ts, entry: float, max_high: float, min_low: float) -> dict:
    return {
        "outcome":      outcome,
        "price":        price,
        "at":           str(ts),
        "max_gain_pct": round((max_high - entry) / entry * 100, 2),
        "max_loss_pct": round((entry - min_low)  / entry * 100, 2),
    }


# ── Intraday resolver ──────────────────────────────────────────────────────────

def _resolve_intraday(signal: dict) -> Optional[dict]:
    """
    Resolve an intraday signal.

    Priority:
      1. Target / stop hit during the session  → TARGET1/2_HIT or STOPPED
      2. Market close reached without trigger  → SQUARED_OFF at last candle close
      3. Market still open                     → None (check again later)
      4. Past signal date (missed)             → SQUARED_OFF at EOD proxy
    """
    signal_date = signal["signal_date"]
    now_ist     = datetime.now(IST)
    today_str   = now_ist.strftime("%Y-%m-%d")

    # Past-date intraday signals: mark squared off at entry (no data)
    if signal_date < today_str:
        return {
            "outcome":      OUTCOME_SQUARED_OFF,
            "price":        signal["entry_price"],
            "at":           f"{signal_date} 15:30:00",
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        0.0,
        }

    # Fetch 5-min data for today
    df = fetch_single_stock(
        signal["ticker"],
        period=YFINANCE_PERIOD_INTRADAY,
        interval=YFINANCE_INTERVAL_INTRADAY,
        use_cache=False,
    )
    if df is None or df.empty:
        return None

    # Start scanning from when the signal was logged
    logged_at_str = signal.get("logged_at", f"{signal_date} 09:15:00")
    try:
        from_dt = IST.localize(datetime.strptime(logged_at_str, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        from_dt = None

    result = _resolve_candles(
        df,
        direction=signal["direction"],
        entry=signal["entry_price"],
        stop_loss=signal["stop_loss"],
        target_1=signal["target_1"],
        target_2=signal["target_2"],
        from_dt=from_dt,
    )
    if result:
        result["pnl_r"] = _pnl_r(
            signal["entry_price"], signal["stop_loss"],
            result["price"], signal["direction"],
        )
        return result

    # Market closed and no trigger → MANDATORY square-off
    market_close = now_ist.replace(hour=15, minute=31, second=0, microsecond=0)
    if now_ist >= market_close:
        last_price = float(df["Close"].iloc[-1])
        return {
            "outcome":      OUTCOME_SQUARED_OFF,
            "price":        last_price,
            "at":           now_ist.replace(hour=15, minute=30, second=0).strftime("%Y-%m-%d %H:%M:%S"),
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        _pnl_r(signal["entry_price"], signal["stop_loss"], last_price, signal["direction"]),
        }

    return None  # market still open; no trigger yet


# ── Swing resolver ─────────────────────────────────────────────────────────────

def _resolve_swing(signal: dict) -> Optional[dict]:
    """
    Resolve a swing signal against daily candles since signal date.
    Returns EXPIRED after SWING_EXPIRY_DAYS if no trigger fires.
    """
    try:
        signal_dt = datetime.strptime(signal["signal_date"], "%Y-%m-%d")
    except ValueError:
        return None

    expiry_dt = signal_dt + timedelta(days=SWING_EXPIRY_DAYS)
    now_ist   = datetime.now(IST)

    df = fetch_single_stock(
        signal["ticker"],
        period="6mo",
        interval=YFINANCE_INTERVAL_DAILY,
        use_cache=True,
    )
    if df is None or df.empty:
        return None

    df.index = pd.to_datetime(df.index)
    tz = df.index.tzinfo
    cutoff = (
        pd.Timestamp(signal_dt, tz=tz) + pd.Timedelta(days=1)
        if tz else
        pd.Timestamp(signal_dt) + pd.Timedelta(days=1)
    )
    df_after = df[df.index >= cutoff]

    result = _resolve_candles(
        df_after,
        direction=signal["direction"],
        entry=signal["entry_price"],
        stop_loss=signal["stop_loss"],
        target_1=signal["target_1"],
        target_2=signal["target_2"],
    )
    if result:
        result["pnl_r"] = _pnl_r(
            signal["entry_price"], signal["stop_loss"],
            result["price"], signal["direction"],
        )
        return result

    # Past expiry → close at last available price
    if now_ist.date() >= expiry_dt.date():
        last_price = float(df_after["Close"].iloc[-1]) if not df_after.empty else signal["entry_price"]
        return {
            "outcome":      OUTCOME_EXPIRED,
            "price":        last_price,
            "at":           now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        _pnl_r(signal["entry_price"], signal["stop_loss"], last_price, signal["direction"]),
        }

    return None  # still within hold window; no trigger yet


# ── Main entry point ───────────────────────────────────────────────────────────

def update_open_signal_outcomes(
    position_size_inr: float = DEFAULT_POSITION_SIZE_INR,
    timeframe: str = None,
) -> int:
    """
    Iterate OPEN signals, resolve each against price data, and write
    outcome + cost breakdown back to the DB.

    Args:
        position_size_inr: Capital per trade for cost/P&L calculations (default ₹1L)
        timeframe: Optional — 'INTRADAY' or 'SWING'. None resolves all open signals.

    Returns the number of signals resolved.
    """
    log          = get_signal_logger()
    open_signals = log.get_open_signals(timeframe=timeframe)

    if not open_signals:
        logger.info("Outcome tracker: no open signals to resolve.")
        return 0

    resolved = 0
    for sig in open_signals:
        try:
            if sig["timeframe"] == "INTRADAY":
                result = _resolve_intraday(sig)
            else:
                result = _resolve_swing(sig)

            if not result:
                continue

            # Compute realistic transaction costs
            cost = compute_trade_cost(
                entry_price=sig["entry_price"],
                exit_price=result["price"],
                direction=sig["direction"],
                timeframe=sig["timeframe"],
                position_size_inr=position_size_inr,
                stop_loss=sig["stop_loss"],
            )

            log.update_outcome(
                signal_id=sig["signal_id"],
                outcome=result["outcome"],
                outcome_price=result["price"],
                outcome_at=result["at"],
                max_gain_pct=result.get("max_gain_pct"),
                max_loss_pct=result.get("max_loss_pct"),
                pnl_r=result.get("pnl_r"),
                cost_breakdown=cost,
            )

            resolved += 1
            logger.info(
                f"[{sig['ticker']}] {sig['strategy']} → {result['outcome']} "
                f"@ ₹{result['price']:.2f}  "
                f"net P&L ₹{cost['net_pnl_inr']:+.2f}  "
                f"({cost['net_pnl_r']:+.2f}R after ₹{cost['cost_total_inr']:.2f} costs)"
                if cost.get("net_pnl_r") is not None else
                f"[{sig['ticker']}] {sig['strategy']} → {result['outcome']} "
                f"@ ₹{result['price']:.2f}  net P&L ₹{cost['net_pnl_inr']:+.2f}"
            )

        except Exception as exc:
            logger.error(f"Outcome tracker error for {sig.get('ticker')}: {exc}")

    logger.info(f"Outcome tracker: resolved {resolved}/{len(open_signals)} open signals.")
    return resolved
