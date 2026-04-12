"""
Composable stock screener — filter + rank engine with presets.
"""
import pandas as pd
import numpy as np
from typing import Optional
import logging

from data.fetcher import fetch_bulk_fundamentals, fetch_stock_data
from analysis.technical import compute_indicators, get_technical_summary
from analysis.fundamental import build_fundamental_df, score_fundamentals
from config.settings import SMA_MID, SMA_LONG, RSI_PERIOD, VOLUME_SPIKE_MULTIPLIER

logger = logging.getLogger(__name__)


class StockScreener:
    def __init__(self):
        self._filters: list[tuple] = []
        self._sort_col: Optional[str] = None
        self._sort_asc: bool = False

    def add_filter(self, column: str, operator: str, value: float) -> "StockScreener":
        """Add a filter: column, operator (gt/lt/gte/lte/eq/between), value."""
        self._filters.append((column, operator, value))
        return self

    def set_sort(self, column: str, ascending: bool = False) -> "StockScreener":
        self._sort_col = column
        self._sort_asc = ascending
        return self

    def reset(self) -> "StockScreener":
        self._filters = []
        self._sort_col = None
        return self

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = pd.Series([True] * len(df), index=df.index)
        for col, op, val in self._filters:
            if col not in df.columns:
                continue
            col_data = pd.to_numeric(df[col], errors="coerce")
            if op == "gt":
                mask &= col_data > val
            elif op == "lt":
                mask &= col_data < val
            elif op == "gte":
                mask &= col_data >= val
            elif op == "lte":
                mask &= col_data <= val
            elif op == "eq":
                mask &= col_data == val
            elif op == "between" and isinstance(val, (list, tuple)) and len(val) == 2:
                mask &= col_data.between(val[0], val[1])
        return df[mask].copy()

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply filters and sort to a pre-built screening DataFrame."""
        result = self._apply_filters(df)
        if self._sort_col and self._sort_col in result.columns:
            result = result.sort_values(self._sort_col, ascending=self._sort_asc)
        return result.reset_index(drop=True)


def build_screen_data(tickers: list[str]) -> pd.DataFrame:
    """
    Build combined fundamental + technical screening DataFrame.
    Fetches fundamentals and adds key technical signals.
    """
    # Fetch fundamentals
    fundamentals = fetch_bulk_fundamentals(tickers)
    if fundamentals.empty:
        return pd.DataFrame()

    fund_df = build_fundamental_df(fundamentals.to_dict("records"))

    # Fetch technical data and add key signals
    price_data = fetch_stock_data(tickers)
    tech_rows = []
    for ticker in tickers:
        df = price_data.get(ticker)
        if df is None or df.empty:
            tech_rows.append({"ticker": ticker})
            continue
        summary = get_technical_summary(df)
        tech_rows.append({
            "ticker": ticker,
            "rsi": summary.get("rsi"),
            "trend": summary.get("trend"),
            "tech_strength": summary.get("strength"),
            "atr": summary.get("atr"),
            "volume_ratio": summary.get("volume_ratio"),
            "above_sma50": "Above SMA50" in summary.get("patterns", []),
            "above_sma200": "Above SMA200" in summary.get("patterns", []),
            "golden_cross": "Golden Cross" in summary.get("patterns", []),
            "macd_bullish": summary.get("macd_bullish"),
            "support": summary.get("support"),
            "resistance": summary.get("resistance"),
        })

    tech_df = pd.DataFrame(tech_rows)
    result = fund_df.merge(tech_df, on="ticker", how="left")
    return result


# ── PRESET SCREENERS ──────────────────────────────────────────────────────────

def preset_value_picks(df: pd.DataFrame) -> pd.DataFrame:
    """Low PE, high ROE, low debt, above SMA200."""
    s = StockScreener()
    s.add_filter("pe", "lt", 20)
    s.add_filter("pe", "gt", 0)
    s.add_filter("roe_pct", "gt", 15)
    s.add_filter("debt_equity", "lt", 100)
    s.set_sort("composite_score", ascending=False)
    return s.run(df)


def preset_momentum_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """RSI 50-70, above SMA200, volume spike."""
    s = StockScreener()
    s.add_filter("rsi", "gte", 50)
    s.add_filter("rsi", "lte", 70)
    s.add_filter("volume_ratio", "gte", VOLUME_SPIKE_MULTIPLIER)
    s.set_sort("tech_strength", ascending=False)
    return s.run(df[df.get("above_sma200", pd.Series(dtype=bool)).fillna(False)])


def preset_oversold_bounce(df: pd.DataFrame) -> pd.DataFrame:
    """RSI < 30, decent fundamentals."""
    s = StockScreener()
    s.add_filter("rsi", "lt", 35)
    s.add_filter("composite_score", "gt", 0.4)
    s.set_sort("composite_score", ascending=False)
    return s.run(df)


def preset_dividend_stars(df: pd.DataFrame) -> pd.DataFrame:
    """Dividend yield > 2%, healthy balance sheet."""
    s = StockScreener()
    s.add_filter("div_yield_pct", "gt", 2.0)
    s.add_filter("health_score", "gt", 0.5)
    s.set_sort("div_yield_pct", ascending=False)
    return s.run(df)


def preset_quality_compounders(df: pd.DataFrame) -> pd.DataFrame:
    """High ROE, strong margins, manageable debt."""
    s = StockScreener()
    s.add_filter("roe_pct", "gt", 20)
    s.add_filter("profit_margin_pct", "gt", 10)
    s.add_filter("health_score", "gt", 0.6)
    s.set_sort("profitability_score", ascending=False)
    return s.run(df)


PRESETS = {
    "Value Picks": preset_value_picks,
    "Momentum Breakout": preset_momentum_breakout,
    "Oversold Bounce": preset_oversold_bounce,
    "Dividend Stars": preset_dividend_stars,
    "Quality Compounders": preset_quality_compounders,
}
