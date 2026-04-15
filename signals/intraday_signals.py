"""
Intraday trade signal generator.
Strategies: Opening Range Breakout (ORB), VWAP Bounce.
Only generates signals during market hours.
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional

from data.fetcher import fetch_stock_data
from data.market_status import is_market_open
from analysis.technical import compute_indicators
from signals.signal_models import TradeSignal
from config.settings import (
    YFINANCE_PERIOD_INTRADAY, YFINANCE_INTERVAL_INTRADAY,
    ATR_PERIOD, MIN_RISK_REWARD, MAX_INTRADAY_SIGNALS,
    VOLUME_SPIKE_MULTIPLIER, RSI_PERIOD,
)

logger = logging.getLogger(__name__)

# Opening range is defined as first N candles of the session
OPENING_RANGE_CANDLES = 3   # First 15 min = 3 x 5-min candles


def _get_opening_range(df: pd.DataFrame) -> tuple[float, float]:
    """Get high/low of the opening range (first N 5-min candles of today)."""
    if df is None or df.empty:
        return None, None
    today = df.index[-1].date()
    today_df = df[df.index.date == today]
    if len(today_df) < OPENING_RANGE_CANDLES:
        return None, None
    opening = today_df.iloc[:OPENING_RANGE_CANDLES]
    return float(opening["High"].max()), float(opening["Low"].min())


def _orb_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """Opening Range Breakout signal."""
    if df is None or len(df) < 20:
        return None

    or_high, or_low = _get_opening_range(df)
    if or_high is None:
        return None

    latest = df.iloc[-1]
    close = float(latest["Close"])
    volume_ratio = float(latest["Volume"]) / float(df["Volume"].rolling(20).mean().iloc[-1]) if df["Volume"].mean() > 0 else 1

    # ATR from recent data
    df_ind = compute_indicators(df)
    atr = df_ind[f"ATR_{ATR_PERIOD}"].iloc[-1] if f"ATR_{ATR_PERIOD}" in df_ind.columns else None
    if not atr or pd.isna(atr):
        return None

    direction = None
    strategy = "Opening Range Breakout"

    if close > or_high * 1.001 and volume_ratio >= VOLUME_SPIKE_MULTIPLIER:
        direction = "LONG"
        entry = close
        stop_loss = round(or_high - atr * 0.5, 2)
    elif close < or_low * 0.999 and volume_ratio >= VOLUME_SPIKE_MULTIPLIER:
        direction = "SHORT"
        entry = close
        stop_loss = round(or_low + atr * 0.5, 2)

    if direction is None:
        return None

    risk = abs(entry - stop_loss)
    if risk == 0:
        return None

    target_1 = round(entry + (risk * MIN_RISK_REWARD if direction == "LONG" else -risk * MIN_RISK_REWARD), 2)
    target_2 = round(entry + (risk * MIN_RISK_REWARD * 1.5 if direction == "LONG" else -risk * MIN_RISK_REWARD * 1.5), 2)
    rr = round(abs(target_1 - entry) / risk, 2)

    name = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"

    reasoning = (
        f"ORB {direction}: Price {'broke above' if direction == 'LONG' else 'broke below'} "
        f"opening range {'high' if direction == 'LONG' else 'low'} of {or_high if direction == 'LONG' else or_low:.2f} "
        f"with {volume_ratio:.1f}x volume. Entry: {entry:.2f}, SL: {stop_loss:.2f}, T1: {target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction=direction,
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=4 if volume_ratio >= 3.0 else 3, strategy=strategy, timeframe="INTRADAY",
        technical_score=min(1.0, volume_ratio / 3),
        fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["ORB"],
        current_price=close, sector=sector,
    )


def _vwap_bounce_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """VWAP Bounce signal — price bouncing off VWAP with RSI confirmation."""
    if df is None or len(df) < 20:
        return None

    df_ind = compute_indicators(df)
    if "VWAP" not in df_ind.columns or f"RSI_{RSI_PERIOD}" not in df_ind.columns:
        return None

    latest = df_ind.iloc[-1]
    prev = df_ind.iloc[-2]
    close = float(latest["Close"])
    vwap = float(latest["VWAP"]) if not pd.isna(latest["VWAP"]) else None
    rsi = float(latest[f"RSI_{14}"]) if not pd.isna(latest[f"RSI_{14}"]) else None
    atr = float(latest[f"ATR_{ATR_PERIOD}"]) if f"ATR_{ATR_PERIOD}" in df_ind.columns and not pd.isna(latest[f"ATR_{ATR_PERIOD}"]) else None

    if not vwap or not rsi or not atr:
        return None

    # VWAP bounce long: price touched VWAP from above and bouncing back up
    distance_pct = (close - vwap) / vwap * 100
    direction = None

    if -0.3 <= distance_pct <= 0.5 and rsi > 45 and float(prev["Close"]) < vwap:
        direction = "LONG"  # bounced off VWAP from below
    elif -0.5 <= distance_pct <= 0.3 and rsi < 55 and float(prev["Close"]) > vwap:
        direction = "SHORT"  # rejected at VWAP from above

    if direction is None:
        return None

    entry = close
    stop_loss = round(entry - atr if direction == "LONG" else entry + atr, 2)
    risk = abs(entry - stop_loss)
    target_1 = round(entry + risk * MIN_RISK_REWARD if direction == "LONG" else entry - risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5 if direction == "LONG" else entry - risk * 2.5, 2)
    rr = round(abs(target_1 - entry) / risk, 2) if risk > 0 else 0

    name = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"

    reasoning = (
        f"VWAP Bounce {direction}: RSI {rsi:.0f}, price at {distance_pct:+.2f}% from VWAP ({vwap:.2f}). "
        f"Entry: {entry:.2f}, SL: {stop_loss:.2f}, T1: {target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction=direction,
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=3, strategy="VWAP Bounce", timeframe="INTRADAY",
        technical_score=0.5, fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["VWAP Bounce"],
        current_price=close, sector=sector,
    )


def generate_intraday_signals(
    tickers: list[str],
    fund_map: dict = None,
) -> list[TradeSignal]:
    """
    Generate intraday signals for a list of liquid tickers.
    Only runs if market is open.
    """
    if not is_market_open():
        return []

    # Fetch 5-min intraday data
    price_data = fetch_stock_data(
        tickers,
        period=YFINANCE_PERIOD_INTRADAY,
        interval=YFINANCE_INTERVAL_INTRADAY,
        use_cache=True,
    )

    signals = []
    for ticker in tickers:
        df = price_data.get(ticker)
        fund_info = (fund_map or {}).get(ticker, {})

        for strategy_fn in [_orb_signal, _vwap_bounce_signal]:
            try:
                signal = strategy_fn(ticker, df, fund_info)
                if signal:
                    signals.append(signal)
                    break  # One signal per stock
            except Exception as e:
                logger.warning(f"Intraday signal error for {ticker}: {e}")

    signals.sort(key=lambda s: s.confidence, reverse=True)
    signals = signals[:MAX_INTRADAY_SIGNALS]

    # Persist signals for backtesting — only on actual trading days
    try:
        from data.market_status import is_trading_day
        if is_trading_day():
            from signals.signal_logger import get_signal_logger
            get_signal_logger().log_signals(signals)
            # Telegram alerts
            try:
                from notifications.telegram import notify_intraday_signals
                notify_intraday_signals(signals)
            except Exception as te:
                logger.warning(f"Telegram intraday alert failed: {te}")
    except Exception as e:
        logger.warning(f"Signal logging failed (intraday): {e}")

    return signals
