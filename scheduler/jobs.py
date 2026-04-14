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


def run_intraday_signal_scan():
    """9:30 AM IST — Generate and log intraday signals after first full candle."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running intraday signal scan...")
    try:
        from signals.intraday_signals import generate_intraday_signals
        from config.stock_universe import NIFTY_50

        tickers = list(NIFTY_50.values())
        signals = generate_intraday_signals(tickers)   # logging is inside the function
        logger.info(f"Intraday signal scan done. {len(signals)} signal(s) logged.")
    except Exception as e:
        logger.error(f"Intraday signal scan failed: {e}")


def run_pre_market_scan():
    """8:45 AM IST — Fetch news, run sentiment, generate swing signals, send morning briefing."""
    if not is_trading_day():
        return
    logger.info(f"[{datetime.now(IST)}] Running pre-market scan...")
    try:
        from data.news_fetcher import fetch_market_news, format_news_for_claude
        from analysis.sentiment import analyze_market_sentiment, has_api_key
        from signals.swing_signals import generate_swing_signals
        from config.stock_universe import NIFTY_50

        news = fetch_market_news(use_cache=False)
        sentiment = analyze_market_sentiment(
            format_news_for_claude(news, max_items=30),
            news_items=news,
            use_cache=False,
        )
        sentiment_score = sentiment.get("overall_sentiment", 5) / 10

        tickers = list(NIFTY_50.values())
        # generate_swing_signals already calls log_signals + notify_swing_signals internally
        signals = generate_swing_signals(tickers, sentiment_score=sentiment_score, use_cache=False)

        cache = get_cache()
        cache.set("pre_market:swing_signals", [s.to_dict() for s in signals], 3600 * 8)

        # Morning briefing Telegram message
        try:
            from notifications.telegram import format_morning_briefing, send_message
            msg = format_morning_briefing(
                sentiment=sentiment,
                swing_count=len(signals),
                intraday_count=0,   # intraday job runs at 9:30
            )
            send_message(msg)
        except Exception as te:
            logger.warning(f"Morning briefing Telegram failed: {te}")

        logger.info(f"Pre-market scan done. {len(signals)} swing signals generated.")
    except Exception as e:
        logger.error(f"Pre-market scan failed: {e}")


def _send_market_update(label: str):
    """Shared helper — fetch live data and push a market update to Telegram."""
    try:
        from data.fetcher import fetch_index_data, get_top_gainers_losers
        from data.news_fetcher import fetch_market_news
        from notifications.telegram import format_market_update, send_message
        from config.settings import INDICES

        indices = {}
        for name, ticker in list(INDICES.items())[:4]:   # Nifty50, BankNifty, Sensex, Midcap
            df = fetch_index_data(ticker, period="2d", interval="1d")
            if df is not None and len(df) >= 2:
                price  = float(df["Close"].iloc[-1])
                change = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
                indices[name] = {"price": price, "change_pct": round(float(change), 2)}

        gainers, losers = get_top_gainers_losers()
        news = fetch_market_news(use_cache=True)

        # Quick breadth calc from gainers/losers list
        advances = sum(1 for g in gainers)
        declines = sum(1 for l in losers)

        msg = format_market_update(
            label=label,
            indices=indices,
            top_gainers=gainers[:3],
            top_losers=losers[:3],
            advances=advances,
            declines=declines,
            news_headlines=news[:3],
        )
        send_message(msg)
        logger.info(f"Market update '{label}' sent to Telegram.")
    except Exception as e:
        logger.error(f"Market update '{label}' failed: {e}")


def run_midday_update():
    """12:00 PM IST — Mid-day market snapshot."""
    if not is_trading_day():
        return
    _send_market_update("Mid-Day Update")


def run_closing_update():
    """3:35 PM IST — Market closing summary."""
    if not is_trading_day():
        return
    _send_market_update("Market Closing Summary")


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

    # Pre-market: 8:45 AM IST Mon-Fri — fetch news + generate swing signals
    scheduler.add_job(
        run_pre_market_scan,
        CronTrigger(hour=8, minute=45, day_of_week="0-4", timezone=IST),
        id="pre_market_scan",
        replace_existing=True,
    )

    # Intraday signals: 9:30 AM IST Mon-Fri — after first full candle
    scheduler.add_job(
        run_intraday_signal_scan,
        CronTrigger(hour=9, minute=30, day_of_week="0-4", timezone=IST),
        id="intraday_signal_scan",
        replace_existing=True,
    )

    # Mid-day update: 12:00 PM IST Mon-Fri
    scheduler.add_job(
        run_midday_update,
        CronTrigger(hour=12, minute=0, day_of_week="0-4", timezone=IST),
        id="midday_update", replace_existing=True,
    )

    # Closing summary: 3:35 PM IST Mon-Fri (5 min after market close)
    scheduler.add_job(
        run_closing_update,
        CronTrigger(hour=15, minute=35, day_of_week="0-4", timezone=IST),
        id="closing_update", replace_existing=True,
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
