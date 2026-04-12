"""
RSS feed aggregation for Indian financial news.
"""
import feedparser
import requests
from datetime import datetime, timezone
from typing import Optional
import logging
import time

from data.cache_manager import get_cache
from config.settings import CACHE_TTL_NEWS

logger = logging.getLogger(__name__)

# RSS feed sources for Indian market news
NEWS_SOURCES = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Moneycontrol Markets": "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "Livemint Markets": "https://www.livemint.com/rss/markets",
    "Business Standard Markets": "https://www.business-standard.com/rss/markets-106.rss",
    "NSE Official": "https://www.nseindia.com/api/rss?type=press-release",
}

# Google News RSS for Indian business news
GOOGLE_NEWS_INDIA_BUSINESS = "https://news.google.com/rss/search?q=indian+stock+market+NSE+BSE&hl=en-IN&gl=IN&ceid=IN:en"


def _parse_feed(url: str, source_name: str) -> list[dict]:
    """Parse a single RSS feed and return normalized news items."""
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"}
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.content)
        for entry in feed.entries[:15]:  # Cap at 15 per source
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            items.append({
                "title": entry.get("title", "").strip(),
                "summary": entry.get("summary", "").strip()[:500],
                "url": entry.get("link", ""),
                "source": source_name,
                "published_at": published,
                "published_str": published.strftime("%Y-%m-%d %H:%M UTC") if published else "Unknown",
            })
    except Exception as e:
        logger.warning(f"Failed to fetch {source_name}: {e}")
    return items


def fetch_market_news(sources: Optional[list[str]] = None, use_cache: bool = True) -> list[dict]:
    """
    Aggregate market news from configured RSS feeds.
    Returns list of news items sorted by published time (newest first).
    """
    cache = get_cache()
    cache_key = "news:market"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    feed_sources = {**NEWS_SOURCES}
    feed_sources["Google News India"] = GOOGLE_NEWS_INDIA_BUSINESS

    if sources:
        feed_sources = {k: v for k, v in feed_sources.items() if k in sources}

    all_news = []
    for source_name, url in feed_sources.items():
        items = _parse_feed(url, source_name)
        all_news.extend(items)
        time.sleep(0.3)  # Polite delay between requests

    # Sort by published time, newest first
    all_news.sort(
        key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    # Deduplicate by title similarity (simple approach)
    seen_titles = set()
    deduped = []
    for item in all_news:
        title_key = item["title"][:60].lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(item)

    if use_cache:
        cache.set(cache_key, deduped, CACHE_TTL_NEWS)
    return deduped


def fetch_stock_news(stock_name: str, ticker: str, use_cache: bool = True) -> list[dict]:
    """
    Fetch news for a specific stock using Google News RSS.
    """
    cache = get_cache()
    cache_key = f"news:stock:{ticker}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    query = f"{stock_name} NSE stock"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    items = _parse_feed(url, f"Google News - {stock_name}")

    if use_cache:
        cache.set(cache_key, items, CACHE_TTL_NEWS)
    return items


def format_news_for_claude(news_items: list[dict], max_items: int = 30) -> str:
    """
    Format news items into a string suitable for Claude API analysis.
    """
    lines = []
    for i, item in enumerate(news_items[:max_items], 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:200]}")
    return "\n".join(lines)
