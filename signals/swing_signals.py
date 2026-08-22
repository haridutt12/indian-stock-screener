"""
Swing trade signal generator (2-5 day holds).
Combines technical + fundamental + sentiment scoring.
"""
import pandas as pd
import numpy as np
import logging
from typing import Optional
from collections import defaultdict
import yfinance as yf

from data.fetcher import fetch_stock_data, fetch_bulk_fundamentals
from analysis.technical import compute_indicators, get_technical_summary
from analysis.fundamental import build_fundamental_df, score_fundamentals
from signals.signal_models import TradeSignal
from config.settings import (
    SMA_MID, SMA_LONG, RSI_PERIOD, ATR_PERIOD, EMA_FAST, EMA_SLOW,
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
    # RSI deeply oversold IN AN UPTREND — long-term trend filter prevents catching falling knives
    if (
        rsi is not None and rsi < 40
        and sma200 is not None and close > sma200
        and fund_scores.get("composite_score", 0.5) > 0.35
    ):
        matched_strategies.append("Oversold Reversal")

    # Strategy 4: Bullish Setup — above SMA200 with MACD momentum AND volume/RSI confirmation
    # Tightened: RSI must be in momentum zone (45-70) + volume or RSI confirmation
    if (
        sma200 is not None and close > sma200
        and macd_bullish is True
        and rsi is not None and 45 <= rsi < 70
        and (volume_ratio >= 1.3 or rsi >= 58)
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

    # Strategy 7: 52-Week High Breakout
    # Strong momentum anomaly: stocks breaking to new highs keep going (documented in NSE literature)
    if (
        sma200 is not None and close > sma200
        and rsi is not None and 55 <= rsi <= 78
        and volume_ratio >= VOLUME_SPIKE_MULTIPLIER
        and len(df) >= 200
    ):
        high_52w = float(df["Close"].rolling(252).max().iloc[-1])
        if high_52w > 0 and close >= high_52w * 0.988:
            matched_strategies.append("52W High Breakout")

    # Strategy 8: Bollinger Band Squeeze Breakout
    # Volatility contraction followed by expansion — reliable on daily timeframe
    if (
        "BB_bandwidth" in df_ind.columns
        and "BB_mid" in df_ind.columns
        and macd_bullish is True
        and rsi is not None and 45 <= rsi <= 72
        and len(df_ind) >= 25
    ):
        bw_series = df_ind["BB_bandwidth"].dropna()
        if len(bw_series) >= 20:
            bw_min_20 = float(bw_series.iloc[-20:-1].min())
            bw_now    = _f(latest.get("BB_bandwidth"))
            bb_mid    = _f(latest.get("BB_mid"))
            if bw_now is not None and bb_mid is not None and bw_min_20 > 0:
                in_squeeze = bw_now <= bw_min_20 * 1.1
                expanding  = bw_now > float(bw_series.iloc[-2]) if len(bw_series) >= 2 else False
                if in_squeeze and expanding and close > bb_mid:
                    matched_strategies.append("BB Squeeze Breakout")

    # Strategy 9: EMA Stack Pullback (Bull Flag)
    # All EMAs aligned bull stack; price pulls back to EMA21 — ideal re-entry in trend
    if (
        sma50 is not None and ema21 is not None
        and rsi is not None and 38 <= rsi <= 62
    ):
        ema9 = _f(latest.get(f"EMA_{EMA_FAST}"))
        if ema9 is not None and ema9 > ema21 > sma50 and close > sma200 if sma200 else True:
            pullback_to_ema21 = abs(close - ema21) / close < 0.022
            if pullback_to_ema21:
                matched_strategies.append("EMA Stack Pullback")

    # Strategy 10: RSI Bullish Divergence
    # Price makes lower low; RSI makes higher low — strongest mean-reversion setup
    if (
        rsi is not None and 20 <= rsi <= 50
        and sma200 is not None and close > sma200
        and f"RSI_{RSI_PERIOD}" in df_ind.columns
        and len(df_ind) >= 35
    ):
        _rsi_s   = df_ind[f"RSI_{RSI_PERIOD}"].dropna()
        _price_s = df_ind["Close"].dropna()
        if len(_rsi_s) >= 30 and len(_price_s) >= 30:
            _price_a = _price_s.iloc[-28:-12]
            _price_b = _price_s.iloc[-12:-1]
            _rsi_a   = _rsi_s.iloc[-28:-12]
            _rsi_b   = _rsi_s.iloc[-12:-1]
            if len(_price_a) >= 5 and len(_price_b) >= 5:
                _plow_a    = float(_price_a.min())
                _plow_b    = float(_price_b.min())
                _rsi_at_a  = float(_rsi_a.iloc[int(np.argmin(_price_a.values))])
                _rsi_at_b  = float(_rsi_b.iloc[int(np.argmin(_price_b.values))])
                if _plow_b < _plow_a * 0.998 and _rsi_at_b > _rsi_at_a + 4:
                    matched_strategies.append("RSI Divergence")

    # Strategy 11: MACD Histogram Momentum
    # Histogram turning positive for ≥3 bars from negative territory + price above SMA50
    # Captures early trend resumption without waiting for full crossover
    if (
        sma50 is not None and close > sma50
        and f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIG}" in df_ind.columns
        and len(df_ind) >= 15
    ):
        _hist = df_ind[f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIG}"].dropna()
        if len(_hist) >= 8:
            _h_recent = _hist.iloc[-5:].tolist()
            _h_before = _hist.iloc[-10:-5].tolist()
            _neg_before = sum(1 for h in _h_before if h < 0) >= 3
            _pos_turn   = all(h > 0 for h in _h_recent[-3:])
            _hist_acc   = _h_recent[-1] > _h_recent[-2] > _h_recent[-3]
            if _neg_before and _pos_turn and _hist_acc and volume_ratio >= 1.1:
                matched_strategies.append("MACD Histogram Momentum")

    # Strategy 12: Volume-Weighted Momentum (RVOL surge + price trend)
    # Abnormal volume (≥2.5×) with price ≥3% above 5-day low and above EMA21
    # Institutional accumulation signature
    if (
        ema21 is not None and close > ema21
        and volume_ratio >= 2.5
        and rsi is not None and 45 <= rsi <= 80
        and sma50 is not None and close > sma50
        and len(df_ind) >= 10
    ):
        _lows5 = df_ind["Close"].tail(5).min() if len(df_ind) >= 5 else close
        _bounce = (close - float(_lows5)) / float(_lows5) * 100 if float(_lows5) > 0 else 0
        if _bounce >= 3.0:
            matched_strategies.append("Volume Momentum")

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


def _compute_swing_short_signals(
    ticker: str,
    df: pd.DataFrame,
    fund_scores: dict,
    sentiment_score: float = 0.5,
    fund_info: dict = None,
) -> list[TradeSignal]:
    """Return SHORT swing signals for a single stock (bear-side strategies)."""
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

    atr          = summary.get("atr")
    rsi          = summary.get("rsi")
    macd_bullish = summary.get("macd_bullish")
    volume_ratio = summary.get("volume_ratio") or 1.0

    sma50  = _f(latest.get(f"SMA_{SMA_MID}"))
    sma200 = _f(latest.get(f"SMA_{SMA_LONG}"))

    if not atr or atr == 0:
        return []

    short_strategies = []

    # Strategy S1: Death Cross — SMA50 crossed below SMA200 recently (within 20 bars)
    if (
        sma50 is not None and sma200 is not None
        and sma50 < sma200
        and rsi is not None and 30 <= rsi <= 60
        and len(df_ind) >= 21
    ):
        prev50  = _f(df_ind[f"SMA_{SMA_MID}"].iloc[-21])
        prev200 = _f(df_ind[f"SMA_{SMA_LONG}"].iloc[-21])
        if prev50 is not None and prev200 is not None and prev50 > prev200:
            short_strategies.append("Death Cross")

    # Strategy S2: Overbought Reversal — RSI extended + MACD turning bearish
    if (
        rsi is not None and rsi > 65
        and macd_bullish is False
        and sma200 is not None and close > sma200 * 1.03
    ):
        short_strategies.append("Overbought Reversal")

    # Strategy S3: Trend Breakdown — price breaks below SMA50 with volume confirmation
    if (
        sma50 is not None and close < sma50
        and macd_bullish is False
        and volume_ratio >= VOLUME_SPIKE_MULTIPLIER
        and rsi is not None and rsi < 50
    ):
        short_strategies.append("Trend Breakdown")

    # Strategy S4: 52-Week Low Breakdown
    # Momentum reversal: stocks making new 52W lows under sustained selling pressure continue lower
    if (
        sma200 is not None and close < sma200
        and rsi is not None and 22 <= rsi <= 48
        and volume_ratio >= VOLUME_SPIKE_MULTIPLIER
        and len(df) >= 200
    ):
        low_52w = float(df["Close"].rolling(252).min().iloc[-1])
        if low_52w > 0 and close <= low_52w * 1.012:
            short_strategies.append("52W Low Breakdown")

    if not short_strategies:
        return []

    sl_distance = atr * 1.5
    stop_loss = round(close + sl_distance, 2)          # SL is ABOVE entry for SHORT
    target_1  = round(close - sl_distance * MIN_RISK_REWARD, 2)
    target_2  = round(close - sl_distance * MIN_RISK_REWARD * 1.5, 2)
    risk_reward = round((close - target_1) / (stop_loss - close), 2) if stop_loss != close else 0

    if risk_reward < MIN_RISK_REWARD or target_1 <= 0:
        return []

    name   = fund_info.get("longName", ticker) if fund_info else ticker
    sector = fund_info.get("sector", "Unknown") if fund_info else "Unknown"
    fund_composite = fund_scores.get("composite_score", 0.5)

    signals = []
    for strategy in short_strategies:
        conf_raw = (1 - fund_composite) * 0.35 + (1 - sentiment_score) * 0.15 + 0.5 * 0.5
        confidence = 5 if conf_raw >= 0.75 else (4 if conf_raw >= 0.60 else (3 if conf_raw >= 0.45 else 2))

        reasoning = (
            f"SHORT setup: {strategy}. RSI {rsi:.0f}." if rsi else f"SHORT setup: {strategy}."
        ) + (
            f" Volume {volume_ratio:.1f}x average." if volume_ratio > 1.5 else ""
        ) + f" ATR-based stop at {stop_loss:.2f} ({((stop_loss - close) / close * 100):.1f}% risk)."

        signals.append(TradeSignal(
            ticker=ticker,
            name=name,
            direction="SHORT",
            entry_price=round(close, 2),
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            confidence=confidence,
            strategy=strategy,
            timeframe="SWING",
            technical_score=round(summary.get("strength", 50) / 100, 3),
            fundamental_score=round(fund_composite, 3),
            sentiment_score=round(sentiment_score, 3),
            reasoning=reasoning,
            patterns=summary.get("patterns", []),
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
    # Market regime gate — check Nifty 50 trend to suppress low-confidence LONG signals in bear market
    _regime_bearish = False
    try:
        _nsei = yf.Ticker("^NSEI").history(period="60d", interval="1d", auto_adjust=True)
        if _nsei is not None and len(_nsei) >= 50:
            _nc  = float(_nsei["Close"].iloc[-1])
            _n20 = float(_nsei["Close"].rolling(20).mean().iloc[-1])
            _n50 = float(_nsei["Close"].rolling(50).mean().iloc[-1])
            _regime_bearish = _nc < _n50 and _nc < _n20
    except Exception:
        pass

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
            short_signals = _compute_swing_short_signals(
                ticker=ticker,
                df=df,
                fund_scores=fund_scores,
                sentiment_score=sentiment_score,
                fund_info=fund_info,
            )
            all_signals.extend(signals)
            all_signals.extend(short_signals)
            if on_tick:
                all_strats = [s.strategy for s in signals] + [s.strategy for s in short_signals]
                on_tick(ticker, all_strats, i + 1, total)
        except Exception as e:
            logger.warning(f"Error generating swing signal for {ticker}: {e}")
            if on_tick:
                on_tick(ticker, [], i + 1, total)

    # Market regime gate: in bearish regime, drop LONG signals with confidence < 3
    if _regime_bearish:
        _before = len(all_signals)
        all_signals = [
            s for s in all_signals
            if s.direction == "SHORT" or s.confidence >= 3
        ]
        _dropped = _before - len(all_signals)
        if _dropped:
            logger.info("Regime gate (bearish): dropped %d low-confidence LONG signal(s).", _dropped)

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
        from signals.signal_logger import get_signal_logger
        _sl = get_signal_logger()
        # Only collect signals that are genuinely NEW (not already in DB today)
        new_signals = [s for s in diverse if _sl.log_signal(s)]
        if new_signals:
            logger.info(f"Swing signal log: {len(new_signals)} new signals persisted")
            try:
                from notifications.telegram import notify_swing_signals
                notify_swing_signals(new_signals)   # Only alert for truly new signals
            except Exception as te:
                logger.warning(f"Telegram swing alert failed: {te}")
        else:
            logger.info("Swing signal log: all signals already exist — no Telegram alert sent")
    except Exception as e:
        logger.warning(f"Signal logging failed (swing): {e}")

    return diverse
