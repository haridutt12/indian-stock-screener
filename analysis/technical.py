"""
Technical indicator calculations using pandas and numpy.
"""
import pandas as pd
import numpy as np
import logging
from config.settings import (
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD, ATR_PERIOD,
    SMA_SHORT, SMA_MID, SMA_LONG,
    EMA_FAST, EMA_SLOW, VOLUME_AVG_PERIOD,
    VOLUME_SPIKE_MULTIPLIER,
)

logger = logging.getLogger(__name__)


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=length).mean()


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _macd(series: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"MACD": macd_line, "MACD_signal": signal_line, "MACD_hist": hist})


def _bbands(series: pd.Series, length: int, std: float) -> pd.DataFrame:
    middle = _sma(series, length)
    stddev = series.rolling(length, min_periods=length).std()
    upper = middle + std * stddev
    lower = middle - std * stddev
    bandwidth = (upper - lower) / middle
    percent = (series - lower) / (upper - lower)
    return pd.DataFrame({
        "BB_lower": lower,
        "BB_mid": middle,
        "BB_upper": upper,
        "BB_bandwidth": bandwidth,
        "BB_percent": percent,
    })


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(length, min_periods=length).mean()


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    atr = _atr(high, low, close, length)
    hl2 = (high + low) / 2
    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr

    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    for i in range(1, len(close)):
        if (upperband.iat[i] < final_upper.iat[i - 1]) or (close.iat[i - 1] > final_upper.iat[i - 1]):
            final_upper.iat[i] = upperband.iat[i]
        else:
            final_upper.iat[i] = final_upper.iat[i - 1]

        if (lowerband.iat[i] > final_lower.iat[i - 1]) or (close.iat[i - 1] < final_lower.iat[i - 1]):
            final_lower.iat[i] = lowerband.iat[i]
        else:
            final_lower.iat[i] = final_lower.iat[i - 1]

    trend = pd.Series(index=close.index, dtype="object")
    supertrend = pd.Series(index=close.index, dtype="float64")
    current_trend = True
    for i in range(len(close)):
        if i == 0:
            supertrend.iat[0] = np.nan
            trend.iat[0] = "bull"
            continue

        if close.iat[i] > final_upper.iat[i - 1]:
            current_trend = True
        elif close.iat[i] < final_lower.iat[i - 1]:
            current_trend = False

        if current_trend:
            supertrend.iat[i] = final_lower.iat[i]
            trend.iat[i] = "bull"
        else:
            supertrend.iat[i] = final_upper.iat[i]
            trend.iat[i] = "bear"

    return pd.DataFrame({"Supertrend": supertrend, "Supertrend_dir": trend})


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicator columns to an OHLCV DataFrame.
    Returns DataFrame with added indicator columns.
    """
    if df is None or len(df) < 30:
        return df

    df = df.copy()
    try:
        df[f"SMA_{SMA_SHORT}"] = _sma(df["Close"], SMA_SHORT)
        df[f"SMA_{SMA_MID}"] = _sma(df["Close"], SMA_MID)
        df[f"SMA_{SMA_LONG}"] = _sma(df["Close"], SMA_LONG)
        df[f"EMA_{EMA_FAST}"] = _ema(df["Close"], EMA_FAST)
        df[f"EMA_{EMA_SLOW}"] = _ema(df["Close"], EMA_SLOW)
        df[f"RSI_{RSI_PERIOD}"] = _rsi(df["Close"], RSI_PERIOD)

        macd = _macd(df["Close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        df = pd.concat([df, macd], axis=1)

        bb = _bbands(df["Close"], BB_PERIOD, BB_STD)
        df = pd.concat([df, bb], axis=1)

        df[f"ATR_{ATR_PERIOD}"] = _atr(df["High"], df["Low"], df["Close"], ATR_PERIOD)
        df[f"Volume_SMA_{VOLUME_AVG_PERIOD}"] = _sma(df["Volume"], VOLUME_AVG_PERIOD)
        df["Volume_ratio"] = df["Volume"] / df[f"Volume_SMA_{VOLUME_AVG_PERIOD}"]

        if "Volume" in df.columns:
            df["VWAP"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()

        supertrend = _supertrend(df["High"], df["Low"], df["Close"], length=10, multiplier=3.0)
        df = pd.concat([df, supertrend], axis=1)
    except Exception as e:
        logger.error(f"Error computing indicators: {e}")

    return df


def detect_patterns(df: pd.DataFrame) -> list[str]:
    """
    Detect notable technical patterns on the latest candle.
    Returns list of pattern names.
    """
    patterns = []
    if df is None or len(df) < 2:
        return patterns

    def _s(val):
        """Safe scalar extraction."""
        try:
            v = float(val)
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return None

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    # Golden Cross / Death Cross — state-based: SMA50 position vs SMA200
    sma50_col = f"SMA_{SMA_MID}"
    sma200_col = f"SMA_{SMA_LONG}"
    if sma50_col in df.columns and sma200_col in df.columns:
        l50, l200 = _s(latest[sma50_col]), _s(latest[sma200_col])
        if l50 is not None and l200 is not None:
            if l50 > l200:
                patterns.append("Golden Cross")
            else:
                patterns.append("Death Cross")

    # RSI signals
    rsi_col = f"RSI_{RSI_PERIOD}"
    if rsi_col in df.columns:
        rsi = _s(latest[rsi_col])
        if rsi is not None:
            if rsi < 30:
                patterns.append("RSI Oversold")
            elif rsi > 70:
                patterns.append("RSI Overbought")
            elif 45 <= rsi <= 55:
                patterns.append("RSI Neutral")

    # MACD crossover
    if "MACD" in df.columns and "MACD_signal" in df.columns and prev is not None:
        lm, ls = _s(latest["MACD"]), _s(latest["MACD_signal"])
        pm, ps = _s(prev["MACD"]), _s(prev["MACD_signal"])
        if None not in (lm, ls, pm, ps):
            if pm < ps and lm > ls:
                patterns.append("MACD Bullish Crossover")
            elif pm > ps and lm < ls:
                patterns.append("MACD Bearish Crossover")

    # Bollinger Band squeeze
    if "BB_bandwidth" in df.columns:
        bw = df["BB_bandwidth"].dropna()
        lbw = _s(latest["BB_bandwidth"])
        if len(bw) >= 20 and lbw is not None:
            min_bw = _s(bw.rolling(20).min().iloc[-1])
            if min_bw is not None and lbw < min_bw * 1.1:
                patterns.append("Bollinger Squeeze")

    # Volume breakout
    if "Volume_ratio" in df.columns:
        vr = _s(latest["Volume_ratio"])
        if vr is not None and vr >= VOLUME_SPIKE_MULTIPLIER:
            patterns.append("Volume Spike")

    # Price vs moving averages
    close = _s(latest["Close"])
    if close is not None:
        sma200 = _s(latest.get(sma200_col))
        if sma200 is not None:
            patterns.append("Above SMA200" if close > sma200 else "Below SMA200")
        sma50 = _s(latest.get(sma50_col))
        if sma50 is not None and close > sma50:
            patterns.append("Above SMA50")

    return patterns


def get_technical_summary(df: pd.DataFrame) -> dict:
    """
    Returns a summary of the current technical setup for a stock.
    """
    if df is None or df.empty:
        return {}

    df_with_indicators = compute_indicators(df)
    patterns = detect_patterns(df_with_indicators)
    latest = df_with_indicators.iloc[-1]

    def _scalar(val):
        """Extract scalar from potentially Series/array value."""
        if val is None:
            return None
        try:
            v = float(val)
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return None

    rsi = _scalar(latest.get(f"RSI_{RSI_PERIOD}"))
    macd = _scalar(latest.get("MACD"))
    macd_signal = _scalar(latest.get("MACD_signal"))
    sma50 = _scalar(latest.get(f"SMA_{SMA_MID}"))
    sma200 = _scalar(latest.get(f"SMA_{SMA_LONG}"))
    close = _scalar(latest["Close"])
    atr = _scalar(latest.get(f"ATR_{ATR_PERIOD}"))

    # Trend determination
    trend = "Neutral"
    if sma50 and sma200 and close:
        if close > sma50 > sma200:
            trend = "Strong Uptrend"
        elif close > sma200:
            trend = "Uptrend"
        elif close < sma50 < sma200:
            trend = "Strong Downtrend"
        elif close < sma200:
            trend = "Downtrend"

    # Trend strength (0-100)
    strength = 50
    bullish_signals = sum([
        "Golden Cross" in patterns,
        "MACD Bullish Crossover" in patterns,
        "Above SMA200" in patterns,
        "Above SMA50" in patterns,
        rsi is not None and not pd.isna(rsi) and 50 < rsi < 70,
        macd is not None and macd_signal is not None and macd > macd_signal,
    ])
    bearish_signals = sum([
        "Death Cross" in patterns,
        "MACD Bearish Crossover" in patterns,
        "Below SMA200" in patterns,
        rsi is not None and not pd.isna(rsi) and rsi < 40,
        macd is not None and macd_signal is not None and macd < macd_signal,
    ])
    strength = min(100, max(0, 50 + (bullish_signals - bearish_signals) * 10))

    # Support/resistance (simple: recent swing highs/lows)
    recent = df_with_indicators.tail(30)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())

    return {
        "trend": trend,
        "strength": strength,
        "rsi": round(float(rsi), 1) if rsi is not None and not pd.isna(rsi) else None,
        "macd_bullish": macd > macd_signal if (macd is not None and macd_signal is not None) else None,
        "atr": round(float(atr), 2) if atr is not None and not pd.isna(atr) else None,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "close": round(float(close), 2),
        "patterns": patterns,
        "volume_ratio": round(float(latest.get("Volume_ratio", 1)), 2),
    }
