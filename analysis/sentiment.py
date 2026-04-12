"""
Claude API integration for news sentiment analysis.
Uses claude-sonnet-4-6 for cost efficiency.
"""
import json
import os
import logging
from typing import Optional

from data.cache_manager import get_cache
from config.settings import CACHE_TTL_SENTIMENT

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


def _get_client():
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


def analyze_market_sentiment(news_text: str, use_cache: bool = True) -> Optional[dict]:
    """
    Analyze overall market sentiment from aggregated news.
    Returns structured sentiment dict or None if Claude API unavailable.
    """
    cache = get_cache()
    cache_key = "sentiment:market"

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    client = _get_client()
    if client is None:
        return _fallback_sentiment()

    try:
        prompt = MARKET_SENTIMENT_PROMPT.format(news_text=news_text[:8000])
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code blocks if present
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
        return _fallback_sentiment()
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _fallback_sentiment()


def analyze_stock_news(stock_name: str, ticker: str, news_text: str, use_cache: bool = True) -> Optional[dict]:
    """
    Analyze news sentiment for a specific stock.
    """
    cache = get_cache()
    cache_key = f"sentiment:stock:{ticker}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    client = _get_client()
    if client is None:
        return None

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
        return None


def _fallback_sentiment() -> dict:
    """Return neutral sentiment when Claude API is unavailable."""
    return {
        "overall_sentiment": 5,
        "sentiment_label": "Neutral",
        "key_themes": ["Data unavailable — set ANTHROPIC_API_KEY for AI analysis"],
        "sector_outlook": {
            s: "neutral" for s in ["IT", "Banking", "Pharma", "FMCG", "Auto", "Metal", "Energy"]
        },
        "stock_mentions": [],
        "overnight_summary": "AI analysis unavailable. Please set your ANTHROPIC_API_KEY in the .env file to enable market sentiment analysis.",
        "trade_implications": "Set ANTHROPIC_API_KEY to get AI-powered trade insights.",
        "key_risks": [],
        "key_catalysts": [],
        "_fallback": True,
    }


def has_api_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))
