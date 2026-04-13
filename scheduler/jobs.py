"""
APScheduler background jobs for automated scans.
Runs as background thread within the Streamlit process,
or can be run standalone: python -m scheduler.jobs
"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from data.market_status import is_trading_day
from data.cache_manager import get_cache

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def run_pre_market_scan():
    """8:45 AM IST — Fetch news, run sentiment, generate swing signals."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running pre-market scan...")
    try:
        from data.news_fetcher import fetch_market_news, format_news_for_claude
        from analysis.sentiment import analyze_market_sentiment, has_api_key
        from signals.swing_signals import generate_swing_signals
        from config.stock_universe import NIFTY_50

        news = fetch_market_news(use_cache=False)
        if has_api_key():
            news_text = format_news_for_claude(news, max_items=30)
            sentiment = analyze_market_sentiment(news_text, use_cache=False)
            sentiment_score = sentiment.get("overall_sentiment", 5) / 10
        else:
            sentiment_score = 0.5

        tickers = list(NIFTY_50.values())
        signals = generate_swing_signals(tickers, sentiment_score=sentiment_score, use_cache=False)
        # Cache results
        cache = get_cache()
        cache.set("pre_market:swing_signals", [s.to_dict() for s in signals], 3600 * 8)
        logger.info(f"Pre-market scan done. {len(signals)} swing signals generated.")
    except Exception as e:
        logger.error(f"Pre-market scan failed: {e}")


def run_intraday_refresh():
    """Every 5 min during 9:15–15:30 IST — Refresh prices and intraday signals."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running intraday refresh...")
    try:
        from data.cache_manager import get_cache
        cache = get_cache()
        # Invalidate intraday price caches so fresh data is fetched on next access
        cache.invalidate_pattern("price:")
        logger.info("Intraday cache invalidated.")
    except Exception as e:
        logger.error(f"Intraday refresh failed: {e}")


def run_post_market_scan():
    """4:00 PM IST — Full technical scan, update fundamentals."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running post-market scan...")
    try:
        from analysis.screener import build_screen_data
        from config.stock_universe import NIFTY_200
        from data.cache_manager import get_cache

        tickers = list(NIFTY_200.values())
        screen_df = build_screen_data(tickers)
        cache = get_cache()
        cache.set("post_market:screen_data", screen_df.to_dict("records"), 3600 * 18)
        logger.info(f"Post-market scan done. {len(screen_df)} stocks screened.")
    except Exception as e:
        logger.error(f"Post-market scan failed: {e}")


def run_outcome_tracker():
    """4:30 PM IST — Resolve open signal outcomes against today's price data."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running outcome tracker...")
    try:
        from signals.outcome_tracker import update_open_signal_outcomes
        resolved = update_open_signal_outcomes()
        logger.info(f"Outcome tracker done. {resolved} signal(s) resolved.")
    except Exception as e:
        logger.error(f"Outcome tracker failed: {e}")


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    # Pre-market: 8:45 AM IST Mon-Fri
    scheduler.add_job(
        run_pre_market_scan,
        CronTrigger(hour=8, minute=45, day_of_week="0-4", timezone=IST),
        id="pre_market_scan",
        replace_existing=True,
    )

    # Intraday refresh: Every 5 min, 9:15–15:30 IST Mon-Fri
    scheduler.add_job(
        run_intraday_refresh,
        CronTrigger(minute="*/5", hour="9-15", day_of_week="0-4", timezone=IST),
        id="intraday_refresh",
        replace_existing=True,
    )

    # Post-market: 4:00 PM IST Mon-Fri
    scheduler.add_job(
        run_post_market_scan,
        CronTrigger(hour=16, minute=0, day_of_week="0-4", timezone=IST),
        id="post_market_scan",
        replace_existing=True,
    )

    # Outcome tracker: 4:30 PM IST Mon-Fri — resolves open signals
    scheduler.add_job(
        run_outcome_tracker,
        CronTrigger(hour=16, minute=30, day_of_week="0-4", timezone=IST),
        id="outcome_tracker",
        replace_existing=True,
    )

    return scheduler


# Singleton scheduler
_scheduler = None

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
    return _scheduler


def start_scheduler():
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info("Scheduler started.")


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)
    start_scheduler()
    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        get_scheduler().shutdown()
        logger.info("Scheduler stopped.")
