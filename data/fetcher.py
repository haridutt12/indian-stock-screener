"""
Core data fetcher — wraps yfinance with caching.
Daily OHLCV → persistent SQLite price store (incremental updates, instant reads).
Intraday OHLCV → TTL-based pickle cache (refreshed every 5 min during market hours).
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


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse yfinance MultiIndex columns (Price, Ticker) → flat string names."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def _period_to_days(period: str) -> int:
    """Convert yfinance period string to approximate calendar days."""
    mapping = {"1d": 1, "5d": 7, "1mo": 35, "3mo": 100,
               "6mo": 200, "1y": 380, "2y": 760, "5y": 1900}
    return mapping.get(period, 504)


def fetch_stock_data(
    tickers: list[str],
    period: str = YFINANCE_PERIOD_DAILY,
    interval: str = YFINANCE_INTERVAL_DAILY,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for a list of tickers.
    Returns {ticker: DataFrame} with columns [Open, High, Low, Close, Volume].

    Daily (interval=1d): served from the persistent SQLite price store.
      - First call bootstraps from yfinance (once per ticker).
      - Subsequent calls are pure DB reads (~30ms for 50 tickers).
      - Stale tickers are refreshed incrementally (last 10 days only).

    Intraday (interval=5m/15m/…): uses the existing TTL pickle cache.
    """
    is_daily = (interval == YFINANCE_INTERVAL_DAILY)

    # ── Daily data: use price store ────────────────────────────────────────────
    if is_daily and use_cache:
        from data.price_store import load, refresh as ps_refresh
        results = {}
        missing = []

        for ticker in tickers:
            df = load(ticker, days=_period_to_days(period))
            if df is not None and not df.empty:
                results[ticker] = df
            else:
                missing.append(ticker)

        if missing:
            logger.info(f"fetcher: price store miss for {len(missing)} tickers — fetching…")
            ps_refresh(missing)
            for ticker in missing:
                df = load(ticker, days=_period_to_days(period))
                if df is not None:
                    results[ticker] = df

        return results

    # ── Intraday data: TTL pickle cache ────────────────────────────────────────
    ttl = CACHE_TTL_PRICE_INTRADAY
    cache = get_cache()
    results = {}
    to_fetch = []

    if use_cache:
        for ticker in tickers:
            key = f"price:{ticker}:{period}:{interval}"
            cached = cache.get(key)
            if cached is not None:
                results[ticker] = _flatten(cached)
            else:
                to_fetch.append(ticker)
    else:
        to_fetch = list(tickers)

    if to_fetch:
        try:
            raw = yf.download(
                to_fetch, period=period, interval=interval,
                group_by="ticker", auto_adjust=True, progress=False, threads=True,
            )
            for ticker in to_fetch:
                try:
                    df = _flatten(raw[ticker].copy() if len(to_fetch) > 1 else raw.copy())
                    df = df.dropna(how="all")
                    df.index = pd.to_datetime(df.index)
                    if not df.empty:
                        results[ticker] = df
                        if use_cache:
                            cache.set(f"price:{ticker}:{period}:{interval}", df, ttl)
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


def get_top_gainers_losers(tickers: list[str], top_n: int = 5) -> dict:
    """
    Returns top N gainers and losers from the given ticker list.
    Uses daily data (today's change).
    """
    data = fetch_stock_data(tickers, period="5d", interval="1d")
    changes = []
    for ticker, df in data.items():
        if len(df) < 2:
            continue
        try:
            import math
            prev = float(df["Close"].iloc[-2])
            curr = float(df["Close"].iloc[-1])
            if math.isnan(prev) or math.isnan(curr) or prev == 0:
                continue
            pct_change = (curr - prev) / prev * 100
            changes.append({"ticker": ticker, "price": curr, "change_pct": pct_change})
        except Exception:
            continue

    if not changes:
        return {"gainers": [], "losers": []}
    changes_df = pd.DataFrame(changes).sort_values("change_pct", ascending=False)
    return {
        "gainers": changes_df.head(top_n).to_dict("records"),
        "losers": changes_df.tail(top_n).to_dict("records"),
    }
