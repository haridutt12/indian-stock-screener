"""
Signal backtest engine.
Given a list of closed signals from the DB, replay each against historical
OHLC price data to compute true out-of-sample statistics.

Note: This validates logged signal outcomes rather than generating new ones.
It's useful to check if outcomes were resolved at the correct prices.
"""
import logging
from typing import Optional
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _fetch_ohlc(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch daily OHLC from yfinance for the given date range."""
    try:
        df = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).normalize()
        return df
    except Exception as exc:
        logger.debug("backtest ohlc fetch failed for %s: %s", ticker, exc)
        return None


def simulate_signal(
    ticker: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    signal_date: str,
    max_days: int = 20,
) -> dict:
    """
    Simulate a single signal against historical daily OHLC.
    Returns dict with:
      - simulated_outcome: STOPPED / TARGET1_HIT / TARGET2_HIT / EXPIRED
      - exit_day: index (0 = signal day)
      - exit_price: simulated exit price
      - pnl_r: P&L in R-multiples
      - bars_held: number of bars in trade
    """
    import datetime
    try:
        start_dt = datetime.date.fromisoformat(signal_date)
        end_dt   = start_dt + datetime.timedelta(days=max_days + 10)
    except Exception:
        return {"error": "invalid signal_date"}

    df = _fetch_ohlc(ticker, start_dt.isoformat(), end_dt.isoformat())
    if df is None or len(df) < 2:
        return {"error": "no_data"}

    # Risk per unit (for R-multiple calculation)
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit <= 0:
        return {"error": "zero_risk"}

    is_long = direction == "LONG"
    bars_held = 0

    for i, (dt, row) in enumerate(df.iterrows()):
        # Skip the signal date itself — the signal was generated at/after close,
        # so the earliest tradeable bar is the next session.
        if hasattr(dt, "date"):
            bar_date = dt.date()
        else:
            bar_date = dt
        if bar_date <= start_dt:
            continue
        bars_held += 1
        high = float(row["High"])
        low  = float(row["Low"])

        if is_long:
            if low <= stop_loss:
                pnl = stop_loss - entry_price
                return {
                    "simulated_outcome": "STOPPED",
                    "exit_day": i, "exit_price": stop_loss,
                    "pnl_r": round(pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }
            if high >= target_2:
                pnl = target_2 - entry_price
                return {
                    "simulated_outcome": "TARGET2_HIT",
                    "exit_day": i, "exit_price": target_2,
                    "pnl_r": round(pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }
            if high >= target_1:
                pnl = target_1 - entry_price
                return {
                    "simulated_outcome": "TARGET1_HIT",
                    "exit_day": i, "exit_price": target_1,
                    "pnl_r": round(pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }
        else:  # SHORT
            if high >= stop_loss:
                pnl = entry_price - stop_loss
                return {
                    "simulated_outcome": "STOPPED",
                    "exit_day": i, "exit_price": stop_loss,
                    "pnl_r": round(-pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }
            if low <= target_2:
                pnl = entry_price - target_2
                return {
                    "simulated_outcome": "TARGET2_HIT",
                    "exit_day": i, "exit_price": target_2,
                    "pnl_r": round(pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }
            if low <= target_1:
                pnl = entry_price - target_1
                return {
                    "simulated_outcome": "TARGET1_HIT",
                    "exit_day": i, "exit_price": target_1,
                    "pnl_r": round(pnl / risk_per_unit, 2),
                    "bars_held": bars_held,
                }

        if bars_held >= max_days:
            break

    # Expired without hitting any level
    last_close = float(df["Close"].iloc[-1])
    pnl = (last_close - entry_price) if is_long else (entry_price - last_close)
    return {
        "simulated_outcome": "EXPIRED",
        "exit_day": bars_held, "exit_price": last_close,
        "pnl_r": round(pnl / risk_per_unit, 2),
        "bars_held": bars_held,
    }


def backtest_signals(signals: list[dict], max_days: int = 20) -> pd.DataFrame:
    """
    Backtest a list of signal dicts against historical OHLC.
    Returns a DataFrame with one row per signal + simulated outcome columns.
    Only processes CLOSED signals (with a real outcome) for validation.
    """
    results = []
    for sig in signals:
        if not all(sig.get(k) for k in ("ticker", "direction", "entry_price", "stop_loss", "target_1", "target_2", "signal_date")):
            continue
        sim = simulate_signal(
            ticker       = sig["ticker"],
            direction    = sig["direction"],
            entry_price  = float(sig["entry_price"]),
            stop_loss    = float(sig["stop_loss"]),
            target_1     = float(sig["target_1"]),
            target_2     = float(sig["target_2"]),
            signal_date  = sig["signal_date"],
            max_days     = max_days,
        )
        results.append({
            "ticker":            sig["ticker"].replace(".NS", ""),
            "strategy":         sig.get("strategy", ""),
            "direction":        sig["direction"],
            "signal_date":      sig["signal_date"],
            "logged_outcome":   sig.get("outcome", ""),
            "sim_outcome":      sim.get("simulated_outcome", sim.get("error", "error")),
            "sim_pnl_r":        sim.get("pnl_r"),
            "sim_bars":         sim.get("bars_held"),
            "logged_pnl_r":     sig.get("net_pnl_r"),
            "outcome_match":    (
                sim.get("simulated_outcome", "") == sig.get("outcome", "")
                if "error" not in sim else None
            ),
        })
    return pd.DataFrame(results) if results else pd.DataFrame()


def backtest_summary(df: pd.DataFrame) -> dict:
    """Compute summary statistics from a backtest DataFrame."""
    if df.empty:
        return {}
    valid = df[df["sim_pnl_r"].notna()].copy()
    if valid.empty:
        return {}

    total     = len(valid)
    wins      = sum(valid["sim_pnl_r"] > 0)
    losses    = sum(valid["sim_pnl_r"] < 0)
    avg_win   = float(valid[valid["sim_pnl_r"] > 0]["sim_pnl_r"].mean()) if wins > 0 else 0.0
    avg_loss  = float(valid[valid["sim_pnl_r"] < 0]["sim_pnl_r"].mean()) if losses > 0 else 0.0
    avg_r     = float(valid["sim_pnl_r"].mean())
    pf        = abs(valid[valid["sim_pnl_r"] > 0]["sim_pnl_r"].sum() /
                    valid[valid["sim_pnl_r"] < 0]["sim_pnl_r"].sum()) if losses > 0 else None
    avg_bars  = float(valid["sim_bars"].mean()) if "sim_bars" in valid.columns else None

    return {
        "total":    total,
        "wins":     wins,
        "losses":   losses,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "avg_r":    round(avg_r, 3),
        "avg_win":  round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "pf":       round(pf, 2) if pf else None,
        "avg_bars": round(avg_bars, 1) if avg_bars else None,
    }
