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
    VOLUME_SPIKE_MULTIPLIER, RSI_PERIOD, EMA_FAST, EMA_SLOW,
)

logger = logging.getLogger(__name__)

# Opening range is defined as first N candles of the session
OPENING_RANGE_CANDLES = 3   # First 15 min = 3 x 5-min candles
MIN_INTRADAY_SL_PCT   = 0.5  # Reject signals with SL tighter than 0.5% from entry
_ORB_VOL_MIN          = 1.2  # Volume multiple required for ORB/EMA signals
_VWAP_DIST_MAX        = 1.5  # Max % distance from daily VWAP to consider a bounce


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

    if close > or_high * 1.001 and volume_ratio >= _ORB_VOL_MIN:
        direction = "LONG"
        entry = close
        stop_loss = round(or_high - atr * 0.5, 2)
    elif close < or_low * 0.999 and volume_ratio >= _ORB_VOL_MIN:
        direction = "SHORT"
        entry = close
        stop_loss = round(or_low + atr * 0.5, 2)

    if direction is None:
        return None

    risk = abs(entry - stop_loss)
    if risk == 0:
        return None

    # Validate SL is on the correct side of entry
    if direction == "LONG" and stop_loss >= entry:
        return None
    if direction == "SHORT" and stop_loss <= entry:
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
    """VWAP Bounce signal — price bouncing off daily VWAP with RSI confirmation."""
    if df is None or len(df) < 20:
        return None

    df_ind = compute_indicators(df)
    if f"RSI_{RSI_PERIOD}" not in df_ind.columns:
        return None

    # Compute today's intraday VWAP (reset daily, not the multi-day cumsum)
    today = df_ind.index[-1].date()
    today_mask = df_ind.index.map(lambda x: x.date()) == today
    today_df = df_ind[today_mask]
    if len(today_df) < 3:
        return None
    vol_sum = today_df["Volume"].cumsum()
    if vol_sum.iloc[-1] == 0:
        return None
    daily_vwap = float((today_df["Close"] * today_df["Volume"]).cumsum().iloc[-1] / vol_sum.iloc[-1])

    latest = df_ind.iloc[-1]
    prev   = df_ind.iloc[-2]
    close  = float(latest["Close"])
    rsi    = float(latest[f"RSI_{RSI_PERIOD}"]) if not pd.isna(latest[f"RSI_{RSI_PERIOD}"]) else None
    atr_col = f"ATR_{ATR_PERIOD}"
    atr    = float(latest[atr_col]) if atr_col in df_ind.columns and not pd.isna(latest[atr_col]) else None

    if not rsi or not atr:
        return None

    distance_pct = (close - daily_vwap) / daily_vwap * 100
    direction = None

    # Price within _VWAP_DIST_MAX% below/above daily VWAP, with directional crossover
    if -_VWAP_DIST_MAX <= distance_pct <= _VWAP_DIST_MAX and rsi > 40 and float(prev["Close"]) < daily_vwap:
        direction = "LONG"  # bounced off daily VWAP from below
    elif -_VWAP_DIST_MAX <= distance_pct <= _VWAP_DIST_MAX and rsi < 60 and float(prev["Close"]) > daily_vwap:
        direction = "SHORT"  # rejected at daily VWAP from above

    if direction is None:
        return None

    entry = close
    stop_loss = round(entry - atr if direction == "LONG" else entry + atr, 2)
    risk = abs(entry - stop_loss)
    if risk == 0:
        return None

    # Validate SL is on the correct side of entry
    if direction == "LONG" and stop_loss >= entry:
        return None
    if direction == "SHORT" and stop_loss <= entry:
        return None

    target_1 = round(entry + risk * MIN_RISK_REWARD if direction == "LONG" else entry - risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5 if direction == "LONG" else entry - risk * 2.5, 2)
    rr = round(abs(target_1 - entry) / risk, 2) if risk > 0 else 0

    name = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"

    reasoning = (
        f"VWAP Bounce {direction}: RSI {rsi:.0f}, price at {distance_pct:+.2f}% from daily VWAP ({daily_vwap:.2f}). "
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


def _ema_crossover_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """EMA Crossover signal — EMA9 crosses EMA21 with volume confirmation."""
    if df is None or len(df) < 25:
        return None

    df_ind = compute_indicators(df)
    ema9_col  = f"EMA_{EMA_FAST}"
    ema21_col = f"EMA_{EMA_SLOW}"
    atr_col   = f"ATR_{ATR_PERIOD}"

    if ema9_col not in df_ind.columns or ema21_col not in df_ind.columns:
        return None

    latest = df_ind.iloc[-1]
    prev   = df_ind.iloc[-2]

    def _fv(col, row):
        v = row.get(col)
        return None if v is None or pd.isna(v) else float(v)

    ema9_now  = _fv(ema9_col, latest);  ema9_prev  = _fv(ema9_col, prev)
    ema21_now = _fv(ema21_col, latest); ema21_prev = _fv(ema21_col, prev)
    atr       = _fv(atr_col, latest)
    close     = float(latest["Close"])
    vwap      = _fv("VWAP", latest)
    vol_ratio = _fv("Volume_ratio", latest) or 1.0

    if None in (ema9_now, ema21_now, ema9_prev, ema21_prev, atr):
        return None
    if vol_ratio < _ORB_VOL_MIN:
        return None

    direction = None
    if ema9_prev <= ema21_prev and ema9_now > ema21_now:
        if vwap is None or close > vwap:
            direction = "LONG"
    elif ema9_prev >= ema21_prev and ema9_now < ema21_now:
        if vwap is None or close < vwap:
            direction = "SHORT"

    if direction is None:
        return None

    entry     = close
    stop_loss = round(entry - atr * 0.8 if direction == "LONG" else entry + atr * 0.8, 2)
    risk      = abs(entry - stop_loss)
    if risk == 0:
        return None
    if direction == "LONG"  and stop_loss >= entry: return None
    if direction == "SHORT" and stop_loss <= entry: return None

    target_1 = round(entry + risk * MIN_RISK_REWARD if direction == "LONG" else entry - risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5             if direction == "LONG" else entry - risk * 2.5, 2)
    rr       = round(abs(target_1 - entry) / risk, 2)

    name   = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    cross_dir = "above" if direction == "LONG" else "below"
    vwap_note = f" Price {'above' if direction == 'LONG' else 'below'} VWAP ({vwap:.2f})." if vwap else ""
    reasoning = (
        f"EMA Crossover {direction}: EMA{EMA_FAST} crossed {cross_dir} EMA{EMA_SLOW} "
        f"with {vol_ratio:.1f}x volume.{vwap_note} "
        f"Entry: {entry:.2f}, SL: {stop_loss:.2f}, T1: {target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction=direction,
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=4 if vol_ratio >= 2.5 else 3,
        strategy="EMA Crossover", timeframe="INTRADAY",
        technical_score=min(1.0, vol_ratio / 3.0),
        fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["EMA Crossover"],
        current_price=close, sector=sector,
    )


def _supertrend_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """Supertrend Signal — Supertrend just flipped bullish on the 5-min chart."""
    if df is None or len(df) < 25:
        return None

    df_ind = compute_indicators(df)
    if "Supertrend_dir" not in df_ind.columns or "Supertrend" not in df_ind.columns:
        return None

    latest  = df_ind.iloc[-1]
    close   = float(latest["Close"])
    st_dir  = latest.get("Supertrend_dir")

    atr_col = f"ATR_{ATR_PERIOD}"
    rsi_col = f"RSI_{RSI_PERIOD}"

    def _fv(col, row):
        v = row.get(col)
        return None if v is None or pd.isna(v) else float(v)

    atr    = _fv(atr_col, latest)
    rsi    = _fv(rsi_col, latest)
    vwap   = _fv("VWAP", latest)
    st_val = _fv("Supertrend", latest)

    if not atr:
        return None

    recent_dirs = df_ind["Supertrend_dir"].dropna().iloc[-6:]
    if len(recent_dirs) < 2:
        return None

    # ── Bullish flip ─────────────────────────────────────────────────────────
    if st_dir == "bull" and "bear" in recent_dirs.iloc[:-1].values:
        if rsi is not None and rsi > 72:
            return None
        if vwap is not None and close < vwap * 0.998:
            return None
        direction = "LONG"
        stop_loss = round(st_val * 0.998, 2) if st_val else round(close - atr, 2)
        risk      = abs(close - stop_loss)
        if risk == 0 or stop_loss >= close:
            return None
        target_1 = round(close + risk * MIN_RISK_REWARD, 2)
        target_2 = round(close + risk * 2.5, 2)
        rr       = round((target_1 - close) / risk, 2)
        name     = fund_info.get("longName", ticker) if fund_info else ticker
        sector   = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
        st_str   = f"{st_val:.2f}" if st_val else "N/A"
        rsi_note = f" RSI {rsi:.0f}." if rsi else ""
        reasoning = (
            f"Supertrend flipped BULLISH: Price {close:.2f} above Supertrend support {st_str}.{rsi_note} "
            f"Entry: {close:.2f}, SL: {stop_loss:.2f}, T1: {target_1:.2f}."
        )
        return TradeSignal(
            ticker=ticker, name=name, direction=direction,
            entry_price=round(close, 2), stop_loss=stop_loss,
            target_1=target_1, target_2=target_2, risk_reward=rr,
            confidence=4 if (rsi is not None and 50 <= rsi <= 65) else 3,
            strategy="Supertrend Signal", timeframe="INTRADAY",
            technical_score=0.7, fundamental_score=0.5, sentiment_score=0.5,
            reasoning=reasoning, patterns=["Supertrend Bull"],
            current_price=close, sector=sector,
        )

    # ── Bearish flip ─────────────────────────────────────────────────────────
    if st_dir == "bear" and "bull" in recent_dirs.iloc[:-1].values:
        if rsi is not None and rsi < 28:
            return None
        if vwap is not None and close > vwap * 1.002:
            return None
        direction = "SHORT"
        stop_loss = round(st_val * 1.002, 2) if st_val else round(close + atr, 2)
        risk      = abs(stop_loss - close)
        if risk == 0 or stop_loss <= close:
            return None
        target_1 = round(close - risk * MIN_RISK_REWARD, 2)
        target_2 = round(close - risk * 2.5, 2)
        rr       = round((close - target_1) / risk, 2)
        if target_1 <= 0:
            return None
        name     = fund_info.get("longName", ticker) if fund_info else ticker
        sector   = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
        st_str   = f"{st_val:.2f}" if st_val else "N/A"
        rsi_note = f" RSI {rsi:.0f}." if rsi else ""
        reasoning = (
            f"Supertrend flipped BEARISH: Price {close:.2f} below Supertrend resistance {st_str}.{rsi_note} "
            f"Entry: {close:.2f}, SL: {stop_loss:.2f}, T1: {target_1:.2f}."
        )
        return TradeSignal(
            ticker=ticker, name=name, direction=direction,
            entry_price=round(close, 2), stop_loss=stop_loss,
            target_1=target_1, target_2=target_2, risk_reward=rr,
            confidence=4 if (rsi is not None and 35 <= rsi <= 50) else 3,
            strategy="Supertrend Signal", timeframe="INTRADAY",
            technical_score=0.7, fundamental_score=0.5, sentiment_score=0.5,
            reasoning=reasoning, patterns=["Supertrend Bear"],
            current_price=close, sector=sector,
        )

    return None


def _gap_and_go_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """Gap and Go — price gaps >0.7% at open and continues through the opening range."""
    if df is None or len(df) < 20:
        return None

    today = df.index[-1].date()
    today_df   = df[df.index.date == today]
    prev_df    = df[df.index.date < today]

    if len(today_df) < OPENING_RANGE_CANDLES or len(prev_df) < 1:
        return None

    prev_close  = float(prev_df["Close"].iloc[-1])
    today_open  = float(today_df["Open"].iloc[0])
    gap_pct     = (today_open - prev_close) / prev_close * 100

    MIN_GAP = 0.7
    if abs(gap_pct) < MIN_GAP:
        return None

    or_range    = today_df.iloc[:OPENING_RANGE_CANDLES]
    or_high     = float(or_range["High"].max())
    or_low      = float(or_range["Low"].min())

    latest     = df.iloc[-1]
    close      = float(latest["Close"])
    df_ind     = compute_indicators(df)
    atr_col    = f"ATR_{ATR_PERIOD}"
    atr        = float(df_ind[atr_col].iloc[-1]) if atr_col in df_ind.columns and not pd.isna(df_ind[atr_col].iloc[-1]) else None
    if not atr:
        return None

    vol_mean   = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ratio  = float(latest["Volume"]) / float(vol_mean) if vol_mean and vol_mean > 0 else 1.0

    direction = None
    if gap_pct > MIN_GAP and close > or_high * 1.001 and close > today_open:
        direction = "LONG"
        stop_loss = round(or_low, 2)
    elif gap_pct < -MIN_GAP and close < or_low * 0.999 and close < today_open:
        direction = "SHORT"
        stop_loss = round(or_high, 2)

    if direction is None:
        return None

    entry = close
    risk  = abs(entry - stop_loss)
    if risk == 0 or risk / entry < MIN_INTRADAY_SL_PCT / 100:
        return None
    if direction == "LONG"  and stop_loss >= entry: return None
    if direction == "SHORT" and stop_loss <= entry: return None

    target_1 = round(entry + risk * MIN_RISK_REWARD if direction == "LONG" else entry - risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5             if direction == "LONG" else entry - risk * 2.5, 2)
    rr       = round(abs(target_1 - entry) / risk, 2)

    name   = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    gap_dir = "up" if gap_pct > 0 else "down"
    reasoning = (
        f"Gap and Go {direction}: {gap_pct:+.2f}% gap {gap_dir} from ₹{prev_close:.2f}. "
        f"Price continuing {'above OR high' if direction == 'LONG' else 'below OR low'} "
        f"with {vol_ratio:.1f}x volume. SL at OR {'low' if direction == 'LONG' else 'high'} "
        f"₹{stop_loss:.2f}. T1: ₹{target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction=direction,
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=4 if abs(gap_pct) >= 1.5 and vol_ratio >= 2.0 else 3,
        strategy="Gap and Go", timeframe="INTRADAY",
        technical_score=min(1.0, abs(gap_pct) / 2.0),
        fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["Gap"],
        current_price=close, sector=sector,
    )


def _vwap_reclaim_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """VWAP Reclaim — stock was below VWAP for 3+ candles then reclaims it with volume."""
    if df is None or len(df) < 25:
        return None

    df_ind  = compute_indicators(df)
    rsi_col = f"RSI_{RSI_PERIOD}"
    atr_col = f"ATR_{ATR_PERIOD}"
    if rsi_col not in df_ind.columns:
        return None

    today     = df_ind.index[-1].date()
    today_mask = df_ind.index.map(lambda x: x.date()) == today
    today_df  = df_ind[today_mask]
    if len(today_df) < 5:
        return None

    vol_sum = today_df["Volume"].cumsum()
    if vol_sum.iloc[-1] == 0:
        return None
    daily_vwap = float(
        (today_df["Close"] * today_df["Volume"]).cumsum().iloc[-1] / vol_sum.iloc[-1]
    )

    latest = df_ind.iloc[-1]
    close  = float(latest["Close"])
    rsi    = float(latest[rsi_col]) if not pd.isna(latest[rsi_col]) else None
    atr    = float(latest[atr_col]) if atr_col in df_ind.columns and not pd.isna(latest[atr_col]) else None

    if not rsi or not atr:
        return None
    if close <= daily_vwap or rsi < 45:
        return None

    # 3 prior candles (today) must all have been below VWAP
    prior = today_df["Close"].iloc[-4:-1]
    if len(prior) < 3 or not all(float(c) < daily_vwap for c in prior):
        return None

    vol_mean  = df_ind["Volume"].rolling(20).mean().iloc[-1]
    vol_ratio = float(latest["Volume"]) / float(vol_mean) if vol_mean and vol_mean > 0 else 1.0
    if vol_ratio < 1.3:
        return None

    entry     = close
    stop_loss = round(daily_vwap - atr * 0.3, 2)
    risk      = abs(entry - stop_loss)
    if risk == 0 or stop_loss >= entry or risk / entry < MIN_INTRADAY_SL_PCT / 100:
        return None

    target_1 = round(entry + risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5, 2)
    rr       = round(abs(target_1 - entry) / risk, 2)

    name   = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    reasoning = (
        f"VWAP Reclaim LONG: Was below VWAP ({daily_vwap:.2f}) for 3+ candles, "
        f"now reclaimed with {vol_ratio:.1f}x volume and RSI {rsi:.0f}. "
        f"SL just below VWAP at ₹{stop_loss:.2f}. T1: ₹{target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction="LONG",
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=4 if vol_ratio >= 2.0 and rsi >= 55 else 3,
        strategy="VWAP Reclaim", timeframe="INTRADAY",
        technical_score=min(1.0, vol_ratio / 3.0),
        fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["VWAP Reclaim"],
        current_price=close, sector=sector,
    )


def _camarilla_pivot_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """Camarilla Pivot S3/R3 — institutional S/R level bounce with volume confirmation."""
    if df is None or len(df) < 20:
        return None

    today    = df.index[-1].date()
    today_df = df[df.index.date == today]
    prev_df  = df[df.index.date < today]

    if len(today_df) < OPENING_RANGE_CANDLES or len(prev_df) < 1:
        return None

    prev_high  = float(prev_df["High"].max())
    prev_low   = float(prev_df["Low"].min())
    prev_close = float(prev_df["Close"].iloc[-1])
    pivot_range = prev_high - prev_low

    if pivot_range <= 0:
        return None

    s3 = round(prev_close - pivot_range * 1.1 / 4, 2)
    r3 = round(prev_close + pivot_range * 1.1 / 4, 2)
    s4 = round(prev_close - pivot_range * 1.1 / 2, 2)
    r4 = round(prev_close + pivot_range * 1.1 / 2, 2)

    latest   = df.iloc[-1]
    prev_bar = df.iloc[-2]
    close    = float(latest["Close"])

    df_ind  = compute_indicators(df)
    atr_col = f"ATR_{ATR_PERIOD}"
    rsi_col = f"RSI_{RSI_PERIOD}"
    atr = float(df_ind[atr_col].iloc[-1]) if atr_col in df_ind.columns and not pd.isna(df_ind[atr_col].iloc[-1]) else None
    rsi = float(df_ind[rsi_col].iloc[-1]) if rsi_col in df_ind.columns and not pd.isna(df_ind[rsi_col].iloc[-1]) else None

    if not atr or not rsi:
        return None

    vol_mean  = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ratio = float(latest["Volume"]) / float(vol_mean) if vol_mean and vol_mean > 0 else 1.0

    direction = None
    stop_loss = None
    level_name = ""
    level_val  = 0.0

    # S3 Bounce: prev bar touched S3, current bar bouncing above it
    if (
        float(prev_bar["Low"]) <= s3 * 1.003
        and close > s3
        and close > float(prev_bar["Close"])
        and rsi < 48
        and vol_ratio >= 1.2
    ):
        direction  = "LONG"
        stop_loss  = round(s4 - atr * 0.15, 2)
        level_name = "S3"
        level_val  = s3

    # R3 Rejection: prev bar touched R3, current bar dropping below it
    elif (
        float(prev_bar["High"]) >= r3 * 0.997
        and close < r3
        and close < float(prev_bar["Close"])
        and rsi > 52
        and vol_ratio >= 1.2
    ):
        direction  = "SHORT"
        stop_loss  = round(r4 + atr * 0.15, 2)
        level_name = "R3"
        level_val  = r3

    if direction is None or stop_loss is None:
        return None

    entry = close
    risk  = abs(entry - stop_loss)
    if risk == 0 or risk / entry < MIN_INTRADAY_SL_PCT / 100:
        return None
    if direction == "LONG"  and stop_loss >= entry: return None
    if direction == "SHORT" and stop_loss <= entry: return None

    target_1 = round(entry + risk * MIN_RISK_REWARD if direction == "LONG" else entry - risk * MIN_RISK_REWARD, 2)
    target_2 = round(entry + risk * 2.5             if direction == "LONG" else entry - risk * 2.5, 2)
    rr       = round(abs(target_1 - entry) / risk, 2)

    name   = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    action = "Bounce" if direction == "LONG" else "Rejection"
    reasoning = (
        f"Camarilla {level_name} {action} {direction}: Price {'touched' if direction == 'LONG' else 'rejected at'} "
        f"{level_name} ({level_val:.2f}) with {vol_ratio:.1f}× volume and RSI {rsi:.0f}. "
        f"SL at {'S4' if direction == 'LONG' else 'R4'} buffer ₹{stop_loss:.2f}. T1: ₹{target_1:.2f}."
    )

    return TradeSignal(
        ticker=ticker, name=name, direction=direction,
        entry_price=round(entry, 2), stop_loss=stop_loss,
        target_1=target_1, target_2=target_2, risk_reward=rr,
        confidence=4 if vol_ratio >= 2.0 else 3,
        strategy="Camarilla Pivot", timeframe="INTRADAY",
        technical_score=min(1.0, vol_ratio / 3.0),
        fundamental_score=0.5, sentiment_score=0.5,
        reasoning=reasoning, patterns=["Camarilla"],
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

        for strategy_fn in [_gap_and_go_signal, _camarilla_pivot_signal, _orb_signal, _supertrend_signal, _ema_crossover_signal, _vwap_reclaim_signal, _vwap_bounce_signal]:
            try:
                signal = strategy_fn(ticker, df, fund_info)
                if signal:
                    if signal.stop_loss_pct < MIN_INTRADAY_SL_PCT:
                        logger.debug(
                            f"Skipping {ticker} ({signal.strategy}): SL {signal.stop_loss_pct:.2f}% < {MIN_INTRADAY_SL_PCT}%"
                        )
                        continue
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
            _sl = get_signal_logger()
            # Only collect signals that are genuinely NEW (not already in DB today)
            new_signals = [s for s in signals if _sl.log_signal(s)]
            if new_signals:
                logger.info(f"Intraday signal log: {len(new_signals)} new signals persisted")
                try:
                    from notifications.telegram import notify_intraday_signals
                    notify_intraday_signals(new_signals)   # Only alert for truly new signals
                except Exception as te:
                    logger.warning(f"Telegram intraday alert failed: {te}")
            else:
                logger.info("Intraday signal log: all signals already exist — no Telegram alert sent")
    except Exception as e:
        logger.warning(f"Signal logging failed (intraday): {e}")

    return signals
