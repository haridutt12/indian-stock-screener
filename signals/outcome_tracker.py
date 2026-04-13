"""
Outcome Tracker: Resolves OPEN signals against actual price data.

Called by the post-market scheduler job (4:30 PM IST) to determine whether
each open signal hit its target, stopped out, or expired.

Logic
-----
LONG signals:
  - TARGET2_HIT  : any candle's High  >= target_2
  - TARGET1_HIT  : any candle's High  >= target_1
  - STOPPED       : any candle's Low   <= stop_loss
  (stop takes priority on the same candle — conservative backtesting)

SHORT signals:
  - TARGET2_HIT  : any candle's Low   <= target_2
  - TARGET1_HIT  : any candle's Low   <= target_1
  - STOPPED       : any candle's High  >= stop_loss

Expiry
------
  INTRADAY  → EXPIRED if no trigger by end of signal date
  SWING     → EXPIRED after SWING_EXPIRY_DAYS calendar days
"""
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
    OUTCOME_EXPIRED,
    SWING_EXPIRY_DAYS,
)
from config.settings import (
    YFINANCE_PERIOD_INTRADAY,
    YFINANCE_INTERVAL_INTRADAY,
    YFINANCE_INTERVAL_DAILY,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def _pnl_r(entry: float, stop: float, exit_price: float, direction: str) -> float:
    """Risk-normalised P&L (R-multiple)."""
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    if direction == "LONG":
        return round((exit_price - entry) / risk, 3)
    else:
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
    Walk candles in order and return the first outcome that triggers.

    Returns a dict with keys: outcome, price, at, max_gain_pct, max_loss_pct, pnl_r
    or None if no trigger found.
    """
    if df is None or df.empty:
        return None

    # Optionally filter to candles after signal time
    if from_dt is not None:
        # Make from_dt timezone-aware to match DataFrame index
        if from_dt.tzinfo is None:
            from_dt = IST.localize(from_dt)
        # Convert index timezone if needed
        idx = df.index
        if idx.tzinfo is None:
            idx = idx.tz_localize("UTC")
        idx = idx.tz_convert(IST)
        df = df[idx >= from_dt]

    if df.empty:
        return None

    max_high = entry
    min_low = entry

    for ts, row in df.iterrows():
        high = float(row["High"])
        low  = float(row["Low"])
        max_high = max(max_high, high)
        min_low  = min(min_low, low)

        if direction == "LONG":
            # Stop takes priority on the same candle (conservative)
            if low <= stop_loss:
                return {
                    "outcome":      OUTCOME_STOPPED,
                    "price":        stop_loss,
                    "at":           str(ts),
                    "max_gain_pct": round((max_high - entry) / entry * 100, 2),
                    "max_loss_pct": round((entry - min_low)  / entry * 100, 2),
                    "pnl_r":        -1.0,
                }
            if high >= target_2:
                return {
                    "outcome":      OUTCOME_TARGET2,
                    "price":        target_2,
                    "at":           str(ts),
                    "max_gain_pct": round((max_high - entry) / entry * 100, 2),
                    "max_loss_pct": round((entry - min_low)  / entry * 100, 2),
                    "pnl_r":        _pnl_r(entry, stop_loss, target_2, direction),
                }
            if high >= target_1:
                return {
                    "outcome":      OUTCOME_TARGET1,
                    "price":        target_1,
                    "at":           str(ts),
                    "max_gain_pct": round((max_high - entry) / entry * 100, 2),
                    "max_loss_pct": round((entry - min_low)  / entry * 100, 2),
                    "pnl_r":        _pnl_r(entry, stop_loss, target_1, direction),
                }
        else:  # SHORT
            if high >= stop_loss:
                return {
                    "outcome":      OUTCOME_STOPPED,
                    "price":        stop_loss,
                    "at":           str(ts),
                    "max_gain_pct": round((entry - min_low)  / entry * 100, 2),
                    "max_loss_pct": round((max_high - entry) / entry * 100, 2),
                    "pnl_r":        -1.0,
                }
            if low <= target_2:
                return {
                    "outcome":      OUTCOME_TARGET2,
                    "price":        target_2,
                    "at":           str(ts),
                    "max_gain_pct": round((entry - min_low)  / entry * 100, 2),
                    "max_loss_pct": round((max_high - entry) / entry * 100, 2),
                    "pnl_r":        _pnl_r(entry, stop_loss, target_2, direction),
                }
            if low <= target_1:
                return {
                    "outcome":      OUTCOME_TARGET1,
                    "price":        target_1,
                    "at":           str(ts),
                    "max_gain_pct": round((entry - min_low)  / entry * 100, 2),
                    "max_loss_pct": round((max_high - entry) / entry * 100, 2),
                    "pnl_r":        _pnl_r(entry, stop_loss, target_1, direction),
                }

    return None  # no trigger yet


def _resolve_intraday(signal: dict) -> Optional[dict]:
    """
    Resolve an intraday signal against same-day 5-min candles.
    Returns outcome dict or {"outcome": OUTCOME_EXPIRED, ...} if market closed.
    """
    signal_date = signal["signal_date"]
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    # Only process signals from today or earlier
    if signal_date > today_str:
        return None

    # Intraday signals from past days: always EXPIRED (missed them)
    if signal_date < today_str:
        last_close = float(signal["entry_price"])  # best proxy we have
        return {
            "outcome":      OUTCOME_EXPIRED,
            "price":        last_close,
            "at":           f"{signal_date} 15:30:00",
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        0.0,
        }

    # Same-day: fetch 5-min data and check
    df = fetch_single_stock(
        signal["ticker"],
        period=YFINANCE_PERIOD_INTRADAY,
        interval=YFINANCE_INTERVAL_INTRADAY,
        use_cache=False,
    )
    if df is None or df.empty:
        return None

    # Filter to today's candles after signal time
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
        return result

    # Market closed and no trigger → EXPIRED
    market_close = now_ist.replace(hour=15, minute=31, second=0, microsecond=0)
    if now_ist >= market_close:
        last_price = float(df["Close"].iloc[-1]) if not df.empty else signal["entry_price"]
        return {
            "outcome":      OUTCOME_EXPIRED,
            "price":        last_price,
            "at":           f"{today_str} 15:30:00",
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        0.0,
        }

    return None  # market still open, no trigger yet


def _resolve_swing(signal: dict) -> Optional[dict]:
    """
    Resolve a swing signal against daily candles since signal date.
    Returns outcome dict or EXPIRED after SWING_EXPIRY_DAYS.
    """
    signal_date_str = signal["signal_date"]
    try:
        signal_dt = datetime.strptime(signal_date_str, "%Y-%m-%d")
    except ValueError:
        return None

    now_ist = datetime.now(IST)
    expiry_dt = signal_dt + timedelta(days=SWING_EXPIRY_DAYS)

    # Fetch daily data (6-month history covers any reasonable swing window)
    df = fetch_single_stock(
        signal["ticker"],
        period="6mo",
        interval=YFINANCE_INTERVAL_DAILY,
        use_cache=True,
    )
    if df is None or df.empty:
        return None

    # Only look at candles after signal date
    df.index = pd.to_datetime(df.index)
    if df.index.tzinfo is not None:
        cutoff = pd.Timestamp(signal_dt, tz=df.index.tzinfo) + pd.Timedelta(days=1)
    else:
        cutoff = pd.Timestamp(signal_dt) + pd.Timedelta(days=1)
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
        return result

    # Check expiry
    if now_ist.date() >= expiry_dt.date():
        last_price = float(df_after["Close"].iloc[-1]) if not df_after.empty else signal["entry_price"]
        entry = signal["entry_price"]
        stop  = signal["stop_loss"]
        return {
            "outcome":      OUTCOME_EXPIRED,
            "price":        last_price,
            "at":           now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            "max_gain_pct": None,
            "max_loss_pct": None,
            "pnl_r":        _pnl_r(entry, stop, last_price, signal["direction"]),
        }

    return None  # still within holding window, no trigger yet


def update_open_signal_outcomes() -> int:
    """
    Main entry point called by the scheduler.

    Iterates all OPEN signals, attempts to resolve each against price data,
    and writes outcomes back to the DB.

    Returns the number of signals resolved.
    """
    log = get_signal_logger()
    open_signals = log.get_open_signals()

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

            if result:
                log.update_outcome(
                    signal_id=sig["signal_id"],
                    outcome=result["outcome"],
                    outcome_price=result["price"],
                    outcome_at=result["at"],
                    max_gain_pct=result.get("max_gain_pct"),
                    max_loss_pct=result.get("max_loss_pct"),
                    pnl_r=result.get("pnl_r"),
                )
                resolved += 1
                logger.info(
                    f"[{sig['ticker']}] {sig['strategy']} → {result['outcome']} "
                    f"@ {result['price']:.2f} (pnl_r={result.get('pnl_r')})"
                )
        except Exception as exc:
            logger.error(f"Outcome tracker error for {sig.get('ticker')}: {exc}")

    logger.info(f"Outcome tracker: resolved {resolved}/{len(open_signals)} open signals.")
    return resolved
