"""
Fundamental analysis and scoring for Indian stocks.
"""
import pandas as pd
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Sector average PE ratios for relative valuation (approximate, 2025)
SECTOR_PE_BENCHMARKS = {
    "IT": 28,
    "Banking": 14,
    "Finance": 20,
    "Pharma": 30,
    "FMCG": 50,
    "Auto": 22,
    "Metal": 10,
    "Oil & Gas": 12,
    "Cement": 25,
    "Infra": 35,
    "Energy": 18,
    "Consumer": 45,
    "Healthcare": 35,
    "Conglomerate": 30,
    "New-age Tech": 80,
    "Ports": 20,
    "Unknown": 25,
}


def _safe(val, default=None):
    """Return value if not None/NaN, else default."""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except Exception:
        pass
    return val


def score_valuation(info: dict) -> float:
    """Score valuation quality (0=expensive, 1=cheap). Lower PE/PB is better."""
    pe = _safe(info.get("trailingPE"))
    pb = _safe(info.get("priceToBook"))
    sector = _safe(info.get("sector"), "Unknown")
    benchmark_pe = SECTOR_PE_BENCHMARKS.get(sector, 25)

    scores = []
    if pe and pe > 0:
        # PE relative to sector: below benchmark scores high
        pe_score = max(0, min(1, (benchmark_pe - pe) / benchmark_pe + 0.5))
        scores.append(pe_score)
    if pb and pb > 0:
        # PB < 1 = undervalued, PB 1-3 = fair, PB > 5 = expensive
        pb_score = max(0, min(1, (3 - pb) / 4 + 0.5))
        scores.append(pb_score)

    return float(np.mean(scores)) if scores else 0.5


def score_profitability(info: dict) -> float:
    """Score profitability (ROE, margins). Higher is better."""
    roe = _safe(info.get("returnOnEquity"))
    profit_margin = _safe(info.get("profitMargins"))
    op_margin = _safe(info.get("operatingMargins"))

    scores = []
    if roe is not None:
        # ROE > 20% is excellent, < 5% is poor
        scores.append(max(0, min(1, roe / 0.25)))
    if profit_margin is not None:
        # Net margin > 20% = excellent, < 5% = poor
        scores.append(max(0, min(1, profit_margin / 0.20)))
    if op_margin is not None:
        scores.append(max(0, min(1, op_margin / 0.25)))

    return float(np.mean(scores)) if scores else 0.5


def score_growth(info: dict) -> float:
    """Score revenue/earnings growth. Higher is better."""
    revenue_growth = _safe(info.get("revenueGrowth"))
    earnings_growth = _safe(info.get("earningsGrowth"))

    scores = []
    if revenue_growth is not None:
        # > 20% = excellent, < 0% = poor
        scores.append(max(0, min(1, revenue_growth / 0.20 * 0.7 + 0.3)))
    if earnings_growth is not None:
        scores.append(max(0, min(1, earnings_growth / 0.25 * 0.7 + 0.3)))

    return float(np.mean(scores)) if scores else 0.5


def score_financial_health(info: dict) -> float:
    """Score balance sheet strength. Lower debt, higher liquidity is better."""
    debt_to_equity = _safe(info.get("debtToEquity"))
    current_ratio = _safe(info.get("currentRatio"))

    scores = []
    if debt_to_equity is not None and debt_to_equity >= 0:
        # D/E < 0.5 = excellent, D/E > 2 = poor
        scores.append(max(0, min(1, 1 - debt_to_equity / 3)))
    if current_ratio is not None:
        # > 2 = healthy, < 1 = concerning
        scores.append(max(0, min(1, current_ratio / 2.5)))

    return float(np.mean(scores)) if scores else 0.5


def score_dividend(info: dict) -> float:
    """Score dividend attractiveness."""
    div_yield = _safe(info.get("dividendYield"))
    payout_ratio = _safe(info.get("payoutRatio"))

    if div_yield is None or div_yield == 0:
        return 0.3  # No dividend — neutral-low
    scores = [min(1.0, div_yield / 0.05)]  # 5%+ yield = max score
    if payout_ratio is not None and 0 < payout_ratio < 1:
        # Sustainable payout 20-60% is ideal
        payout_score = 1 - abs(payout_ratio - 0.4) / 0.5
        scores.append(max(0, payout_score))

    return float(np.mean(scores))


def score_fundamentals(info: dict) -> dict:
    """
    Compute composite fundamental score for a stock.
    Returns scores dict with individual components and weighted composite.
    """
    valuation = score_valuation(info)
    profitability = score_profitability(info)
    growth = score_growth(info)
    health = score_financial_health(info)
    dividend = score_dividend(info)

    # Weighted composite (profitability and health matter most for Indian market)
    composite = (
        valuation * 0.20 +
        profitability * 0.30 +
        growth * 0.25 +
        health * 0.15 +
        dividend * 0.10
    )

    return {
        "valuation_score": round(valuation, 3),
        "profitability_score": round(profitability, 3),
        "growth_score": round(growth, 3),
        "health_score": round(health, 3),
        "dividend_score": round(dividend, 3),
        "composite_score": round(composite, 3),
    }


def classify_stock(scores: dict, info: dict) -> str:
    """Classify stock into a category based on fundamental scores."""
    pe = _safe(info.get("trailingPE"))
    div_yield = _safe(info.get("dividendYield"), 0)

    if scores["valuation_score"] > 0.7 and scores["profitability_score"] > 0.6:
        return "Value Pick"
    if scores["growth_score"] > 0.7 and scores["profitability_score"] > 0.6:
        return "Growth Stock"
    if div_yield and div_yield > 0.03 and scores["health_score"] > 0.6:
        return "Dividend Play"
    if scores["profitability_score"] > 0.7 and scores["health_score"] > 0.7:
        return "Quality Compounder"
    if scores["composite_score"] < 0.4 and scores["growth_score"] > 0.5:
        return "Turnaround Candidate"
    return "Fairly Valued"


def build_fundamental_df(fundamentals_list: list[dict]) -> pd.DataFrame:
    """
    Build a screener-ready DataFrame from a list of fundamental dicts.
    Adds score columns.
    """
    rows = []
    for info in fundamentals_list:
        if not info.get("ticker"):
            continue
        scores = score_fundamentals(info)
        classification = classify_stock(scores, info)
        market_cap = info.get("marketCap")
        market_cap_cr = round(market_cap / 1e7, 0) if market_cap else None  # Convert to crores

        row = {
            "ticker": info["ticker"],
            "name": info.get("longName", info["ticker"]),
            "sector": info.get("sector", "Unknown"),
            "price": info.get("currentPrice"),
            "market_cap_cr": market_cap_cr,
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "roe_pct": round(info["returnOnEquity"] * 100, 1) if info.get("returnOnEquity") else None,
            "profit_margin_pct": round(info["profitMargins"] * 100, 1) if info.get("profitMargins") else None,
            "revenue_growth_pct": round(info["revenueGrowth"] * 100, 1) if info.get("revenueGrowth") else None,
            "debt_equity": info.get("debtToEquity"),
            "div_yield_pct": round(info["dividendYield"] * 100, 2) if info.get("dividendYield") else 0,
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "classification": classification,
            **scores,
        }
        rows.append(row)

    return pd.DataFrame(rows)
