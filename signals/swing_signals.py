"""
Swing trade signal generator (2-5 day holds).
Combines technical + fundamental + sentiment scoring.
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional
from collections import defaultdict

from data.fetcher import fetch_stock_data, fetch_bulk_fundamentals
from analysis.technical import compute_indicators, get_technical_summary
from analysis.fundamental import build_fundamental_df, score_fundamentals
from signals.signal_models import TradeSignal
from config.settings import (
    SMA_MID, SMA_LONG, RSI_PERIOD, ATR_PERIOD, EMA_SLOW,
    MIN_RISK_REWARD, MAX_SWING_SIGNALS, VOLUME_SPIKE_MULTIPLIER,
)

logger = logging.getLogger(__name__)


def _compute_swing_signals(
    ticker: str,
    df: pd.DataFrame,
    fund_scores: dict,
    sentiment_score: float = 0.5,
    fund_info: dict = None,
) -> list[TradeSignal]:
    """
    Return all matching swing signals for a single stock.
    Each matched strategy produces a separate TradeSignal.
    """
    if df is None or len(df) < 60:
        return []

    df_ind = compute_indicators(df)
    summary = get_technical_summary(df_ind)

    if not summary:
        return []

    latest = df_ind.iloc[-1]

    def _f(val):
        try:
            v = float(val)
            return None if (v != v) else v
        except (TypeError, ValueError):
            return None

    close = _f(latest["Close"])
    if close is None:
        return []

    atr = summary.get("atr")
    rsi = summary.get("rsi")
    patterns = summary.get("patterns", [])
    macd_bullish = summary.get("macd_bullish")
    volume_ratio = summary.get("volume_ratio") or 1.0

    sma50  = _f(latest.get(f"SMA_{SMA_MID}"))
    sma200 = _f(latest.get(f"SMA_{SMA_LONG}"))
    ema21  = _f(latest.get(f"EMA_{EMA_SLOW}"))

    if not atr or atr == 0:
        return []

    matched_strategies = []

    # Strategy 1: Trend Pullback
    # Stock in uptrend (above SMA50 & SMA200), pulled back toward EMA21
    if (
        sma50 is not None and sma200 is not None and ema21 is not None
        and close > sma50 and sma50 > sma200
        and abs(close - ema21) / close < 0.05
        and rsi is not None and 35 <= rsi <= 65
    ):
        matched_strategies.append("Trend Pullback")

    # Strategy 2: Volume Breakout
    # Price above SMA200, RSI showing momentum, volume confirming
    if (
        sma200 is not None and close > sma200
        and rsi is not None and 50 <= rsi <= 75
        and volume_ratio >= VOLUME_SPIKE_MULTIPLIER
    ):
        matched_strategies.append("Volume Breakout")

    # Strategy 3: Oversold Reversal
    # RSI deeply oversold — relaxed fundamental requirement
    if (
        rsi is not None and rsi < 40
        and fund_scores.get("composite_score", 0.5) > 0.35
    ):
        matched_strategies.append("Oversold Reversal")

    # Strategy 4: Bullish Setup (broader catch-all)
    # Above SMA200 + MACD bullish + RSI not overbought
    if (
        sma200 is not None and close > sma200
        and macd_bullish is True
        and rsi is not None and rsi < 70
    ):
        matched_strategies.append("Bullish Setup")

    # Strategy 5: Golden Cross — SMA50 crossed above SMA200 within 20 bars
    if (
        sma50 is not None and sma200 is not None
        and sma50 > sma200
        and rsi is not None and 45 <= rsi <= 72
        and len(df_ind) >= 21
    ):
        prev50  = _f(df_ind[f"SMA_{SMA_MID}"].iloc[-21])
        prev200 = _f(df_ind[f"SMA_{SMA_LONG}"].iloc[-21])
        if prev50 is not None and prev200 is not None and prev50 < prev200:
            matched_strategies.append("Golden Cross")

    # Strategy 6: Supertrend Reversal — flipped to bull within 5 bars
    if (
        "Supertrend_dir" in df_ind.columns
        and macd_bullish is True
        and rsi is not None and rsi < 70
    ):
        recent_dirs = df_ind["Supertrend_dir"].dropna().iloc[-6:]
        if (
            len(recent_dirs) >= 2
            and recent_dirs.iloc[-1] == "bull"
            and "bear" in recent_dirs.iloc[:-1].values
        ):
            matched_strategies.append("Supertrend Reversal")

    if not matched_strategies:
        return []

    # ATR-based stops and targets (same for all strategies on this stock)
    sl_distance = atr * 1.5
    stop_loss = round(close - sl_distance, 2)
    target_1 = round(close + sl_distance * MIN_RISK_REWARD, 2)
    target_2 = round(close + sl_distance * MIN_RISK_REWARD * 1.5, 2)
    risk_reward = round((target_1 - close) / (close - stop_loss), 2) if close != stop_loss else 0

    if risk_reward < MIN_RISK_REWARD:
        return []

    name = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    fund_composite = fund_scores.get("composite_score", 0.5)

    signals = []
    for strategy in matched_strategies:
        raw_strength = summary.get("strength", 50)
        if strategy in ("Oversold Reversal", "Supertrend Reversal"):
            raw_strength = max(raw_strength, 50)
        tech_score = raw_strength / 100

        conf_raw = tech_score * 0.5 + fund_composite * 0.35 + sentiment_score * 0.15

        if conf_raw >= 0.75:
            confidence = 5
        elif conf_raw >= 0.60:
            confidence = 4
        elif conf_raw >= 0.45:
            confidence = 3
        else:
            confidence = 2

        reasoning_parts = [
            f"Strategy: {strategy}.",
            f"RSI at {rsi:.0f}" if rsi else "",
            f"Volume {volume_ratio:.1f}x average" if volume_ratio > 1 else "",
            "Above SMA50 and SMA200 — in uptrend" if "Above SMA200" in patterns and "Above SMA50" in patterns else "",
            f"Fundamental score: {fund_composite:.2f} ({fund_scores.get('classification', '')})",
            f"ATR-based stop at {stop_loss} ({((close - stop_loss) / close * 100):.1f}% risk)",
            f"Targets: {target_1} (1:2 R/R) and {target_2} (1:3 R/R)",
        ]
        reasoning = " ".join(p for p in reasoning_parts if p)

        signals.append(TradeSignal(
            ticker=ticker,
            name=name,
            direction="LONG",
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
        ))

    return signals


def generate_swing_signals(
    tickers: list[str],
    sentiment_score: float = 0.5,
    use_cache: bool = True,
    on_tick=None,
) -> list[TradeSignal]:
    """
    Generate swing trade signals for the given ticker list.
    Returns up to MAX_SWING_SIGNALS ranked by confidence, with strategy diversity.

    Args:
        tickers: List of yfinance tickers (e.g., ['RELIANCE.NS'])
        sentiment_score: Market-level sentiment score (0-1) from Claude analysis
        use_cache: Whether to use cached price/fundamental data
        on_tick: Optional callback(ticker, strategies, done, total) called after each ticker
    """
    price_data = fetch_stock_data(tickers, use_cache=use_cache)

    fund_df = fetch_bulk_fundamentals(tickers)
    fund_map = {}
    if not fund_df.empty:
        for _, row in fund_df.iterrows():
            t = row.get("ticker")
            if t:
                fund_map[t] = row.to_dict()

    all_signals: list[TradeSignal] = []
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        df = price_data.get(ticker)
        fund_info = fund_map.get(ticker, {})
        fund_scores = score_fundamentals(fund_info) if fund_info else {}

        try:
            signals = _compute_swing_signals(
                ticker=ticker,
                df=df,
                fund_scores=fund_scores,
                sentiment_score=sentiment_score,
                fund_info=fund_info,
            )
            all_signals.extend(signals)
            if on_tick:
                on_tick(ticker, [s.strategy for s in signals], i + 1, total)
        except Exception as e:
            logger.warning(f"Error generating swing signal for {ticker}: {e}")
            if on_tick:
                on_tick(ticker, [], i + 1, total)

    # Diversity-first selection: round-robin across strategies so all represented strategies appear
    by_strategy: dict[str, list[TradeSignal]] = defaultdict(list)
    for s in all_signals:
        by_strategy[s.strategy].append(s)

    for strat in by_strategy:
        by_strategy[strat].sort(
            key=lambda s: (s.confidence, s.technical_score + s.fundamental_score),
            reverse=True,
        )

    diverse: list[TradeSignal] = []
    round_num = 0
    strategy_keys = sorted(by_strategy.keys())
    while len(diverse) < MAX_SWING_SIGNALS:
        added = False
        for strat in strategy_keys:
            group = by_strategy[strat]
            if round_num < len(group):
                diverse.append(group[round_num])
                added = True
                if len(diverse) >= MAX_SWING_SIGNALS:
                    break
        if not added:
            break
        round_num += 1

    diverse.sort(key=lambda s: (s.confidence, s.technical_score + s.fundamental_score), reverse=True)

    try:
        from data.market_status import is_trading_day
        if is_trading_day():
            from signals.signal_logger import get_signal_logger
            get_signal_logger().log_signals(diverse)
            try:
                from notifications.telegram import notify_swing_signals
                notify_swing_signals(diverse)
            except Exception as te:
                logger.warning(f"Telegram swing alert failed: {te}")
    except Exception as e:
        logger.warning(f"Signal logging failed (swing): {e}")

    return diverse
