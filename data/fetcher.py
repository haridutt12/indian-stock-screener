"""
Core data fetcher — wraps yfinance with caching.
All price data for NSE stocks uses .NS suffix.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional
import logging

from data.cache_manager import get_cache
from config.settings import (
    CACHE_TTL_PRICE_DAILY, CACHE_TTL_PRICE_INTRADAY,
    CACHE_TTL_FUNDAMENTALS,
    YFINANCE_PERIOD_DAILY, YFINANCE_PERIOD_INTRADAY,
    YFINANCE_INTERVAL_DAILY, YFINANCE_INTERVAL_INTRADAY,
)

logger = logging.getLogger(__name__)


def fetch_stock_data(
    tickers: list[str],
    period: str = YFINANCE_PERIOD_DAILY,
    interval: str = YFINANCE_INTERVAL_DAILY,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for a list of tickers.
    Returns {ticker: DataFrame} with columns [Open, High, Low, Close, Volume].
    """
    ttl = CACHE_TTL_PRICE_INTRADAY if "m" in interval else CACHE_TTL_PRICE_DAILY
    cache = get_cache()
    results = {}
    to_fetch = []

    if use_cache:
        for ticker in tickers:
            key = f"price:{ticker}:{period}:{interval}"
            cached = cache.get(key)
            if cached is not None:
                results[ticker] = cached
            else:
                to_fetch.append(ticker)
    else:
        to_fetch = list(tickers)

    if to_fetch:
        try:
            raw = yf.download(
                to_fetch,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            for ticker in to_fetch:
                try:
                    if len(to_fetch) == 1:
                        df = raw.copy()
                    else:
                        df = raw[ticker].copy()
                    df = df.dropna(how="all")
                    df.index = pd.to_datetime(df.index)
                    if not df.empty:
                        results[ticker] = df
                        if use_cache:
                            key = f"price:{ticker}:{period}:{interval}"
                            cache.set(key, df, ttl)
                except Exception as e:
                    logger.warning(f"Could not extract data for {ticker}: {e}")
        except Exception as e:
            logger.error(f"yfinance download failed: {e}")

    return results


def fetch_single_stock(
    ticker: str,
    period: str = YFINANCE_PERIOD_DAILY,
    interval: str = YFINANCE_INTERVAL_DAILY,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV for a single ticker."""
    result = fetch_stock_data([ticker], period=period, interval=interval, use_cache=use_cache)
    return result.get(ticker)


def fetch_index_data(
    index_ticker: str = "^NSEI",
    period: str = YFINANCE_PERIOD_DAILY,
    interval: str = YFINANCE_INTERVAL_DAILY,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV for a market index (e.g. ^NSEI, ^NSEBANK)."""
    cache = get_cache()
    ttl = CACHE_TTL_PRICE_INTRADAY if "m" in interval else CACHE_TTL_PRICE_DAILY
    key = f"index:{index_ticker}:{period}:{interval}"

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    try:
        ticker_obj = yf.Ticker(index_ticker)
        df = ticker_obj.history(period=period, interval=interval, auto_adjust=True)
        df = df.dropna(how="all")
        if not df.empty:
            if use_cache:
                cache.set(key, df, ttl)
            return df
    except Exception as e:
        logger.error(f"Failed to fetch index {index_ticker}: {e}")
    return None


def fetch_fundamentals(ticker: str, use_cache: bool = True) -> dict:
    """
    Fetch fundamental data for a single ticker via yfinance Ticker.info.
    Returns a dict with PE, market cap, ROE, etc.
    """
    cache = get_cache()
    key = f"fundamentals:{ticker}"

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    try:
        info = yf.Ticker(ticker).info
        fundamentals = {
            "ticker": ticker,
            "longName": info.get("longName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
            "trailingEps": info.get("trailingEps"),
            "forwardEps": info.get("forwardEps"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "profitMargins": info.get("profitMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "debtToEquity": info.get("debtToEquity"),
            "currentRatio": info.get("currentRatio"),
            "quickRatio": info.get("quickRatio"),
            "dividendYield": info.get("dividendYield"),
            "payoutRatio": info.get("payoutRatio"),
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "averageVolume": info.get("averageVolume"),
            "volume": info.get("volume"),
        }
        if use_cache:
            cache.set(key, fundamentals, CACHE_TTL_FUNDAMENTALS)
        return fundamentals
    except Exception as e:
        logger.error(f"Failed to fetch fundamentals for {ticker}: {e}")
        return {"ticker": ticker}


def fetch_bulk_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """
    Fetch fundamentals for multiple tickers and return as DataFrame.
    Used by the screener.
    """
    rows = []
    for ticker in tickers:
        data = fetch_fundamentals(ticker)
        rows.append(data)
    return pd.DataFrame(rows)


def fetch_current_price(ticker: str) -> Optional[float]:
    """Quick fetch of latest price for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        price = t.info.get("currentPrice") or t.info.get("regularMarketPrice")
        return float(price) if price else None
    except Exception:
        return None


def fetch_live_quote(ticker: str) -> dict:
    """
    Fetch the latest price + change vs previous close using fast_info.
    Cached for 5 minutes. Works live during market hours and returns
    the closing price outside market hours — always more up-to-date
    than daily OHLCV data.

    Returns dict with keys: price, prev_close, change, change_pct
    Returns {} on failure.
    """
    cache = get_cache()
    key = f"live:{ticker}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        fi = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev = float(fi.previous_close)
        result = {
            "price": price,
            "prev_close": prev,
            "change": price - prev,
            "change_pct": (price - prev) / prev * 100,
        }
        cache.set(key, result, CACHE_TTL_PRICE_INTRADAY)
        return result
    except Exception as e:
        logger.warning(f"fetch_live_quote failed for {ticker}: {e}")
        return {}


def get_top_gainers_losers(tickers: list[str], top_n: int = 5) -> dict:
    """
    Returns top N gainers and losers from the given ticker list.
    During market hours uses 5-min intraday data for live prices.
    Outside market hours falls back to daily data.
    """
    from data.market_status import is_market_open
    if is_market_open():
        # Use intraday 5m data: last candle = current price,
        # previous day's last candle = previous close
        data = fetch_stock_data(tickers, period="2d", interval="5m", use_cache=True)
        changes = []
        for ticker, df in data.items():
            if df is None or df.empty:
                continue
            df = df.dropna(subset=["Close"])
            today = df.index[-1].date()
            today_df = df[df.index.date == today]
            prev_df  = df[df.index.date < today]
            if today_df.empty or prev_df.empty:
                continue
            curr_close = float(today_df["Close"].iloc[-1])
            prev_close = float(prev_df["Close"].iloc[-1])
            pct_change = (curr_close - prev_close) / prev_close * 100
            changes.append({"ticker": ticker, "price": curr_close, "change_pct": pct_change})
    else:
        data = fetch_stock_data(tickers, period="5d", interval="1d")
        changes = []
        for ticker, df in data.items():
            if df is not None and len(df) >= 2:
                prev_close = float(df["Close"].iloc[-2])
                curr_close = float(df["Close"].iloc[-1])
                pct_change = (curr_close - prev_close) / prev_close * 100
                changes.append({"ticker": ticker, "price": curr_close, "change_pct": pct_change})

    if not changes:
        return {"gainers": [], "losers": []}

    changes_df = pd.DataFrame(changes).sort_values("change_pct", ascending=False)
    return {
        "gainers": changes_df.head(top_n).to_dict("records"),
        "losers": changes_df.tail(top_n).to_dict("records"),
    }
