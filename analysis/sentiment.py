"""
Sentiment analysis with two engines:
  1. Claude (Anthropic) — if ANTHROPIC_API_KEY is set
  2. VADER               — free, local, no API key required

Both return the same structured dict so the rest of the app is unaffected.
"""
import json
import os
import re
import logging
from typing import Optional

from data.cache_manager import get_cache
from config.settings import CACHE_TTL_SENTIMENT

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Sector keyword map for VADER engine ───────────────────────────────────────
_SECTOR_KEYWORDS = {
    "IT":      ["infosys", "tcs", "wipro", "hcl", "tech mahindra", "ltimindtree",
                "mphasis", "coforge", "software", "it sector", "technology", "saas",
                "cloud", "digital", "cybersecurity"],
    "Banking": ["sbi", "hdfc bank", "icici bank", "kotak", "axis bank", "pnb",
                "bank of baroda", "canara", "banking", "nbfc", "rbi", "repo rate",
                "credit", "loan", "npa", "microfinance"],
    "Pharma":  ["sun pharma", "dr reddy", "cipla", "divi", "biocon", "aurobindo",
                "lupin", "pharma", "drug", "fda", "usfda", "api", "generic"],
    "FMCG":    ["hindustan unilever", "itc", "nestle", "dabur", "marico", "britannia",
                "godrej", "fmcg", "consumer", "rural demand", "volume growth"],
    "Auto":    ["maruti", "tata motors", "m&m", "hero motocorp", "bajaj auto", "tvs",
                "ashok leyland", "eicher", "auto", "vehicle", "ev", "electric vehicle",
                "two-wheeler", "passenger vehicle"],
    "Metal":   ["tata steel", "jsw steel", "hindalco", "vedanta", "sail", "nalco",
                "steel", "aluminium", "copper", "zinc", "metal", "mining", "iron ore"],
    "Energy":  ["reliance", "ongc", "bpcl", "iocl", "ntpc", "power grid", "adani green",
                "tata power", "oil", "gas", "crude", "renewable", "solar", "energy"],
}

# Known NSE tickers and company fragments for stock-mention detection
_STOCK_MAP = {
    "RELIANCE": ["reliance", "ril"],
    "TCS":      ["tcs", "tata consultancy"],
    "INFY":     ["infosys"],
    "HDFCBANK": ["hdfc bank"],
    "ICICIBANK":["icici bank"],
    "SBIN":     ["sbi", "state bank"],
    "WIPRO":    ["wipro"],
    "HCLTECH":  ["hcl tech"],
    "MARUTI":   ["maruti", "msil"],
    "TATAMOTORS":["tata motors"],
    "SUNPHARMA":["sun pharma"],
    "DRREDDY":  ["dr reddy"],
    "BAJFINANCE":["bajaj finance"],
    "KOTAKBANK":["kotak"],
    "AXISBANK": ["axis bank"],
    "ITC":      ["itc"],
    "HINDUNILVR":["hindustan unilever", "hul"],
    "TATASTEEL":["tata steel"],
    "ADANIENT": ["adani"],
    "ONGC":     ["ongc"],
}


def _get_vader():
    """Return a VADER SentimentIntensityAnalyzer, or None if unavailable."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except ImportError:
        logger.warning("vaderSentiment not installed; falling back to neutral.")
        return None


def _get_claude_client():
    """Lazy-load Anthropic client."""
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("anthropic package not installed")
        return None


# ── Claude prompts (unchanged) ─────────────────────────────────────────────────

MARKET_SENTIMENT_PROMPT = """You are an expert Indian stock market analyst. Analyze the following news headlines and summaries from today's Indian financial news.

NEWS:
{news_text}

Provide a structured JSON analysis with exactly these fields:
{{
  "overall_sentiment": <integer 1-10, where 1=very bearish, 5=neutral, 10=very bullish>,
  "sentiment_label": "<Strongly Bullish|Bullish|Neutral|Bearish|Strongly Bearish>",
  "key_themes": ["<theme1>", "<theme2>", "<theme3>"],
  "sector_outlook": {{
    "IT": "<bullish|neutral|bearish>",
    "Banking": "<bullish|neutral|bearish>",
    "Pharma": "<bullish|neutral|bearish>",
    "FMCG": "<bullish|neutral|bearish>",
    "Auto": "<bullish|neutral|bearish>",
    "Metal": "<bullish|neutral|bearish>",
    "Energy": "<bullish|neutral|bearish>"
  }},
  "stock_mentions": [
    {{"symbol": "<NSE symbol>", "sentiment": "<positive|negative|neutral>", "reason": "<brief reason>"}}
  ],
  "overnight_summary": "<2-3 paragraph narrative of overnight/morning market developments and what they mean for Indian markets today>",
  "trade_implications": "<2-3 actionable insights for traders today based on the news>",
  "key_risks": ["<risk1>", "<risk2>"],
  "key_catalysts": ["<catalyst1>", "<catalyst2>"]
}}

Return ONLY valid JSON, no other text."""

STOCK_SENTIMENT_PROMPT = """You are an expert Indian stock market analyst. Analyze news about {stock_name} ({ticker}).

NEWS:
{news_text}

Provide JSON with:
{{
  "sentiment": <integer 1-10>,
  "sentiment_label": "<Strongly Bullish|Bullish|Neutral|Bearish|Strongly Bearish>",
  "signal": "<BUY|HOLD|SELL|NEUTRAL>",
  "summary": "<2-3 sentences about what the news means for the stock>",
  "key_points": ["<point1>", "<point2>", "<point3>"],
  "catalysts": ["<positive catalyst>"],
  "risks": ["<risk>"]
}}

Return ONLY valid JSON."""


# ── VADER engine ───────────────────────────────────────────────────────────────

def _compound_to_score(compound: float) -> int:
    """Map VADER compound (-1..+1) to 1-10 integer scale."""
    return max(1, min(10, round((compound + 1) * 4.5 + 1)))


def _compound_to_label(compound: float) -> str:
    if compound >= 0.50:  return "Strongly Bullish"
    if compound >= 0.15:  return "Bullish"
    if compound >= -0.15: return "Neutral"
    if compound >= -0.50: return "Bearish"
    return "Strongly Bearish"


def _sector_label(compound: float) -> str:
    if compound >= 0.10:  return "bullish"
    if compound <= -0.10: return "bearish"
    return "neutral"


def _vader_market_sentiment(news_items: list[dict]) -> dict:
    """
    Run VADER over each news headline+summary, then aggregate into the same
    structured dict that the Claude engine returns.
    """
    sia = _get_vader()
    if sia is None:
        return _fallback_sentiment()

    if not news_items:
        return _fallback_sentiment()

    scored = []
    for item in news_items:
        text = (item.get("title") or "") + " " + (item.get("summary") or "")
        scores = sia.polarity_scores(text)
        scored.append({"item": item, "compound": scores["compound"], "scores": scores})

    compounds = [s["compound"] for s in scored]
    avg_compound = sum(compounds) / len(compounds)
    overall_score = _compound_to_score(avg_compound)
    label = _compound_to_label(avg_compound)

    # ── Sector outlook ─────────────────────────────────────────────────────────
    sector_compounds: dict[str, list[float]] = {s: [] for s in _SECTOR_KEYWORDS}
    for s in scored:
        text_lower = (
            (s["item"].get("title") or "") + " " + (s["item"].get("summary") or "")
        ).lower()
        for sector, keywords in _SECTOR_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                sector_compounds[sector].append(s["compound"])

    sector_outlook = {}
    for sector, vals in sector_compounds.items():
        if vals:
            sector_outlook[sector] = _sector_label(sum(vals) / len(vals))
        else:
            sector_outlook[sector] = "neutral"

    # ── Stock mentions ─────────────────────────────────────────────────────────
    stock_hits: dict[str, list[float]] = {}
    for s in scored:
        text_lower = (
            (s["item"].get("title") or "") + " " + (s["item"].get("summary") or "")
        ).lower()
        for symbol, fragments in _STOCK_MAP.items():
            if any(frag in text_lower for frag in fragments):
                stock_hits.setdefault(symbol, []).append(s["compound"])

    stock_mentions = []
    for symbol, vals in stock_hits.items():
        avg = sum(vals) / len(vals)
        sent = "positive" if avg > 0.05 else ("negative" if avg < -0.05 else "neutral")
        # Find a representative headline
        reason = next(
            (s["item"].get("title", "")[:80]
             for s in scored
             if any(frag in (s["item"].get("title","")+" "+s["item"].get("summary","")).lower()
                    for frag in _STOCK_MAP[symbol])),
            "",
        )
        stock_mentions.append({"symbol": symbol, "sentiment": sent, "reason": reason})

    # ── Key themes: top positive & negative headlines ──────────────────────────
    sorted_scored = sorted(scored, key=lambda x: x["compound"])
    top_neg = sorted_scored[:2]
    top_pos = sorted_scored[-2:][::-1]

    themes = []
    for s in top_pos + top_neg:
        t = s["item"].get("title", "")
        if t and t not in themes:
            themes.append(t[:70])
    themes = themes[:4]

    # ── Summary & implications ─────────────────────────────────────────────────
    pos_count = sum(1 for c in compounds if c > 0.05)
    neg_count = sum(1 for c in compounds if c < -0.05)
    neu_count = len(compounds) - pos_count - neg_count

    summary = (
        f"VADER rule-based analysis of {len(news_items)} headlines: "
        f"{pos_count} positive, {neu_count} neutral, {neg_count} negative. "
        f"Average sentiment compound score: {avg_compound:+.3f} → **{label}**.\n\n"
    )
    if top_pos:
        summary += "Top positive: " + "; ".join(s["item"].get("title","")[:60] for s in top_pos) + ".\n\n"
    if top_neg:
        summary += "Top negative: " + "; ".join(s["item"].get("title","")[:60] for s in top_neg) + "."

    implications = (
        f"Market tone is {label.lower()} based on news flow. "
        "For deeper AI-generated insights (sector rotation, trade setups), "
        "add a free Google Gemini API key or an Anthropic API key."
    )

    catalysts = [s["item"].get("title","")[:60] for s in top_pos if s["compound"] > 0.2][:2]
    risks     = [s["item"].get("title","")[:60] for s in top_neg if s["compound"] < -0.2][:2]

    return {
        "overall_sentiment": overall_score,
        "sentiment_label":   label,
        "key_themes":        themes,
        "sector_outlook":    sector_outlook,
        "stock_mentions":    stock_mentions[:8],
        "overnight_summary": summary,
        "trade_implications": implications,
        "key_risks":         risks,
        "key_catalysts":     catalysts,
        "_engine":           "vader",
    }


def _vader_stock_sentiment(stock_name: str, ticker: str, news_items: list[dict]) -> Optional[dict]:
    sia = _get_vader()
    if sia is None:
        return None

    if not news_items:
        return None

    compounds = []
    points = []
    for item in news_items[:10]:
        text = (item.get("title") or "") + " " + (item.get("summary") or "")
        sc = sia.polarity_scores(text)
        compounds.append(sc["compound"])
        if item.get("title"):
            points.append(item["title"][:80])

    avg = sum(compounds) / len(compounds)
    score = _compound_to_score(avg)
    label = _compound_to_label(avg)
    signal = (
        "BUY"  if avg >= 0.25 else
        "SELL" if avg <= -0.25 else
        "HOLD" if avg >= 0.05 else "NEUTRAL"
    )

    return {
        "sentiment":       score,
        "sentiment_label": label,
        "signal":          signal,
        "summary":         (
            f"VADER analysis of {len(compounds)} news items for {stock_name}. "
            f"Average compound: {avg:+.3f} → {label}."
        ),
        "key_points":  points[:3],
        "catalysts":   [p for p, c in zip(points, compounds) if c > 0.2][:2],
        "risks":       [p for p, c in zip(points, compounds) if c < -0.2][:2],
        "_engine":     "vader",
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_market_sentiment(news_text: str, use_cache: bool = True,
                             news_items: Optional[list] = None) -> Optional[dict]:
    """
    Analyze overall market sentiment.
    Uses Claude if ANTHROPIC_API_KEY is set, else falls back to VADER (free).
    """
    cache = get_cache()
    cache_key = "sentiment:market"

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    client = _get_claude_client()
    if client is not None:
        # ── Claude path ────────────────────────────────────────────────────────
        try:
            prompt = MARKET_SENTIMENT_PROMPT.format(news_text=news_text[:8000])
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            if use_cache:
                cache.set(cache_key, result, CACHE_TTL_SENTIMENT)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
        except Exception as e:
            logger.error(f"Claude API error: {e}")

    # ── VADER path (free fallback) ─────────────────────────────────────────────
    items = news_items or []
    result = _vader_market_sentiment(items)
    if use_cache:
        cache.set(cache_key, result, CACHE_TTL_SENTIMENT)
    return result


def analyze_stock_news(stock_name: str, ticker: str, news_text: str,
                       use_cache: bool = True,
                       news_items: Optional[list] = None) -> Optional[dict]:
    """
    Analyze news sentiment for a specific stock.
    Uses Claude if available, else VADER.
    """
    cache = get_cache()
    cache_key = f"sentiment:stock:{ticker}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    client = _get_claude_client()
    if client is not None:
        try:
            prompt = STOCK_SENTIMENT_PROMPT.format(
                stock_name=stock_name, ticker=ticker, news_text=news_text[:4000]
            )
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
            if use_cache:
                cache.set(cache_key, result, CACHE_TTL_SENTIMENT)
            return result
        except Exception as e:
            logger.error(f"Claude stock sentiment error for {ticker}: {e}")

    # ── VADER fallback ─────────────────────────────────────────────────────────
    result = _vader_stock_sentiment(stock_name, ticker, news_items or [])
    if result and use_cache:
        cache.set(cache_key, result, CACHE_TTL_SENTIMENT)
    return result


def _fallback_sentiment() -> dict:
    """Neutral placeholder when both Claude and VADER are unavailable."""
    return {
        "overall_sentiment": 5,
        "sentiment_label": "Neutral",
        "key_themes": ["Install vaderSentiment for free offline analysis"],
        "sector_outlook": {s: "neutral" for s in _SECTOR_KEYWORDS},
        "stock_mentions": [],
        "overnight_summary": "Sentiment engine unavailable.",
        "trade_implications": "—",
        "key_risks": [],
        "key_catalysts": [],
        "_fallback": True,
    }


def has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def get_engine_name() -> str:
    """Returns which sentiment engine is active."""
    return "Claude AI" if has_api_key() else "VADER (free)"
