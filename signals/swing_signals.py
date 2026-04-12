"""
Swing trade signal generator (2-5 day holds).
Combines technical + fundamental + sentiment scoring.
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional

from data.fetcher import fetch_stock_data, fetch_bulk_fundamentals
from analysis.technical import compute_indicators, get_technical_summary
from analysis.fundamental import build_fundamental_df, score_fundamentals
from signals.signal_models import TradeSignal
from config.settings import (
    SMA_MID, SMA_LONG, RSI_PERIOD, ATR_PERIOD,
    MIN_RISK_REWARD, MAX_SWING_SIGNALS, VOLUME_SPIKE_MULTIPLIER,
)

logger = logging.getLogger(__name__)


def _compute_swing_signal(
    ticker: str,
    df: pd.DataFrame,
    fund_scores: dict,
    sentiment_score: float = 0.5,
    fund_info: dict = None,
) -> Optional[TradeSignal]:
    """Attempt to generate a swing signal for a single stock."""
    if df is None or len(df) < 60:
        return None

    df_ind = compute_indicators(df)
    summary = get_technical_summary(df_ind)

    if not summary:
        return None

    latest = df_ind.iloc[-1]
    close = float(latest["Close"])
    atr = summary.get("atr")
    rsi = summary.get("rsi")
    patterns = summary.get("patterns", [])
    macd_bullish = summary.get("macd_bullish")
    volume_ratio = summary.get("volume_ratio", 1)

    sma50 = latest.get(f"SMA_{SMA_MID}")
    sma200 = latest.get(f"SMA_{SMA_LONG}")
    ema21 = latest.get("EMA_21")

    if not atr or atr == 0:
        return None

    strategy = None
    direction = "LONG"

    # Strategy 1: Trend Pullback
    # Stock in uptrend, pulled back to EMA21, RSI cooling off
    if (
        sma50 and sma200 and ema21
        and close > sma50 > sma200
        and ema21 is not None and abs(close - ema21) / close < 0.02
        and rsi is not None and 40 <= rsi <= 62
    ):
        strategy = "Trend Pullback"

    # Strategy 2: Breakout with volume
    elif (
        volume_ratio >= VOLUME_SPIKE_MULTIPLIER
        and sma200 and close > sma200
        and rsi is not None and 50 <= rsi <= 72
        and macd_bullish
    ):
        strategy = "Volume Breakout"

    # Strategy 3: Oversold Reversal
    elif (
        rsi is not None and rsi < 32
        and fund_scores.get("composite_score", 0) > 0.45
        and fund_scores.get("health_score", 0) > 0.4
    ):
        strategy = "Oversold Reversal"

    if strategy is None:
        return None

    # ATR-based stops and targets
    sl_distance = atr * 1.5
    stop_loss = round(close - sl_distance, 2)
    target_1 = round(close + sl_distance * MIN_RISK_REWARD, 2)
    target_2 = round(close + sl_distance * MIN_RISK_REWARD * 1.5, 2)
    risk_reward = round((target_1 - close) / (close - stop_loss), 2) if close != stop_loss else 0

    if risk_reward < MIN_RISK_REWARD:
        return None

    # Confidence scoring (1-5)
    tech_score = summary.get("strength", 50) / 100
    fund_composite = fund_scores.get("composite_score", 0.5)
    conf_raw = (tech_score * 0.5 + fund_composite * 0.35 + sentiment_score * 0.15)
    confidence = max(1, min(5, round(conf_raw * 5)))

    # Build reasoning
    reasoning_parts = [
        f"Strategy: {strategy}.",
        f"RSI at {rsi:.0f}" if rsi else "",
        f"Volume {volume_ratio:.1f}x average" if volume_ratio > 1 else "",
        f"Above SMA50 and SMA200 — in uptrend" if "Above SMA200" in patterns and "Above SMA50" in patterns else "",
        f"Fundamental score: {fund_composite:.2f} ({fund_scores.get('classification', '')})",
        f"ATR-based stop at {stop_loss} ({((close-stop_loss)/close*100):.1f}% risk)",
        f"Targets: {target_1} (1:2 R/R) and {target_2} (1:3 R/R)",
    ]
    reasoning = " ".join(p for p in reasoning_parts if p)

    name = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"

    return TradeSignal(
        ticker=ticker,
        name=name,
        direction=direction,
        entry_price=round(close, 2),
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        risk_reward=risk_reward,
        confidence=confidence,
        strategy=strategy,
        timeframe="SWING",
        technical_score=round(tech_score, 3),
        fundamental_score=round(fund_composite, 3),
        sentiment_score=round(sentiment_score, 3),
        reasoning=reasoning,
        patterns=patterns,
        current_price=close,
        sector=sector,
    )


def generate_swing_signals(
    tickers: list[str],
    sentiment_score: float = 0.5,
    use_cache: bool = True,
) -> list[TradeSignal]:
    """
    Generate swing trade signals for the given ticker list.
    Returns up to MAX_SWING_SIGNALS ranked by confidence.

    Args:
        tickers: List of yfinance tickers (e.g., ['RELIANCE.NS'])
        sentiment_score: Market-level sentiment score (0-1) from Claude analysis
        use_cache: Whether to use cached price/fundamental data
    """
    # Fetch all price data in batch
    price_data = fetch_stock_data(tickers, use_cache=use_cache)

    # Fetch fundamentals
    fund_df = fetch_bulk_fundamentals(tickers)
    fund_map = {}
    if not fund_df.empty:
        for _, row in fund_df.iterrows():
            ticker = row.get("ticker")
            if ticker:
                fund_map[ticker] = row.to_dict()

    signals = []
    for ticker in tickers:
        df = price_data.get(ticker)
        fund_info = fund_map.get(ticker, {})
        fund_scores = score_fundamentals(fund_info) if fund_info else {}

        try:
            signal = _compute_swing_signal(
                ticker=ticker,
                df=df,
                fund_scores=fund_scores,
                sentiment_score=sentiment_score,
                fund_info=fund_info,
            )
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.warning(f"Error generating swing signal for {ticker}: {e}")

    # Sort by confidence desc, then by composite score
    signals.sort(key=lambda s: (s.confidence, s.technical_score + s.fundamental_score), reverse=True)
    return signals[:MAX_SWING_SIGNALS]
