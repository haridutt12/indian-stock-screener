"""
Indian Stock Market Screener — Main Entry Point
Run with: streamlit run app.py
"""
import logging
import threading
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@st.cache_resource
def _start_scheduler():
    """Start the background scheduler once per app instance."""
    try:
        from scheduler.jobs import start_scheduler
        start_scheduler()
        logger.info("Background scheduler started.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")


def _catchup_signals():
    """
    If the app wakes from sleep and the scheduler missed today's signals,
    generate them now in a background thread (non-blocking).
    """
    from datetime import date
    from data.market_status import is_trading_day
    import pytz

    ist = pytz.timezone("Asia/Kolkata")
    from datetime import datetime
    now = datetime.now(ist)
    today = date.today().isoformat()

    # Only run on trading days after 9:30 AM IST
    if not is_trading_day() or now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return

    try:
        from signals.signal_logger import get_signal_logger
        existing = get_signal_logger().get_signals(days_back=1)
        today_signals = [s for s in existing if s.get("signal_date") == today]
        if today_signals:
            return   # already logged today
    except Exception:
        return

    def _generate():
        try:
            from signals.swing_signals import generate_swing_signals
            from signals.intraday_signals import generate_intraday_signals
            from config.stock_universe import NIFTY_50
            tickers = list(NIFTY_50.values())
            generate_swing_signals(tickers)
            if now.hour < 15 or (now.hour == 15 and now.minute < 30):
                generate_intraday_signals(tickers)
            logger.info("Catch-up signal generation complete.")
        except Exception as e:
            logger.error(f"Catch-up signal generation failed: {e}")

    threading.Thread(target=_generate, daemon=True).start()


_start_scheduler()

# Remove any signals that were accidentally logged on holidays or weekends
try:
    from signals.signal_logger import get_signal_logger
    get_signal_logger().purge_non_trading_day_signals()
except Exception:
    pass

_catchup_signals()

st.set_page_config(
    page_title="Indian Stock Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Indian Stock Market Screener — Powered by Python, Streamlit & Claude AI",
    },
)

from ui.styles import inject_global_css
inject_global_css()

# ── Market status ───────────────────────────────────────────────────────────────
from data.market_status import market_status
status       = market_status()
is_open      = status["is_market_open"]
status_color = "#00c896" if is_open else "#ff4d6d"
status_label = status["status_label"]
status_time  = status["datetime_ist"]

# ── Hero banner ─────────────────────────────────────────────────────────────────
# Pre-compute all dynamic parts to keep the HTML string simple and parser-friendly
pill_rgb      = "0,200,150" if is_open else "255,77,109"
pulse_anim    = "animation:pulse 1.5s infinite;" if is_open else ""

hero_html = (
    '<div style="background:linear-gradient(135deg,#0d1b2a 0%,#1a1a2e 55%,#0f172a 100%);'
    'border:1px solid rgba(255,255,255,0.07);border-radius:20px;'
    'padding:36px 44px 32px;margin-bottom:24px;position:relative;overflow:hidden;">'

    # decorative blobs
    '<div style="position:absolute;top:-70px;right:-70px;width:280px;height:280px;'
    'background:radial-gradient(circle,rgba(240,180,41,0.10),transparent 70%);"></div>'
    '<div style="position:absolute;bottom:-50px;left:160px;width:220px;height:220px;'
    'background:radial-gradient(circle,rgba(0,200,150,0.07),transparent 70%);"></div>'

    # content wrapper
    '<div style="position:relative;z-index:1;">'

    # status pill
    f'<div style="display:inline-flex;align-items:center;gap:7px;'
    f'background:rgba({pill_rgb},0.12);border:1px solid rgba({pill_rgb},0.3);'
    f'border-radius:20px;padding:5px 14px;font-size:0.72rem;font-weight:700;'
    f'color:{status_color};letter-spacing:0.08em;text-transform:uppercase;margin-bottom:18px;">'
    f'<span style="width:7px;height:7px;border-radius:50%;background:{status_color};{pulse_anim}"></span>'
    f'&nbsp;{status_label}&nbsp;&middot;&nbsp;{status_time}</div>'

    # heading
    '<h1 style="font-size:2.5rem;font-weight:800;margin:0 0 10px;letter-spacing:-0.03em;'
    'line-height:1.15;background:linear-gradient(135deg,#e8eaf0 30%,#7f8ea3 100%);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
    'Indian Stock Screener</h1>'

    # subtitle
    '<p style="color:#7f8ea3;font-size:1rem;margin:0;line-height:1.65;">'
    'AI-powered swing &amp; intraday signals &nbsp;&middot;&nbsp;'
    'NSE technical &amp; fundamental screener &nbsp;&middot;&nbsp;'
    'Real-time news sentiment</p>'

    '</div></div>'
)
st.markdown(hero_html, unsafe_allow_html=True)

# ── Navigation tiles ─────────────────────────────────────────────────────────────
st.markdown('<p style="color:#6b7a99;font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;">Navigate</p>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/1_Market_Overview.py",      label="📊  Market Overview",        help="Nifty 50, Bank Nifty, Sensex · Sector heatmap · Live gainers/losers")
    st.page_link("pages/2_News_Sentiment.py",       label="📰  News & Sentiment",        help="Claude AI overnight news analysis · Sector outlook")
    st.page_link("pages/3_Fundamental_Screener.py", label="🔍  Fundamental Screener",    help="Filter by PE, ROE, market cap, debt · Value / Growth picks")
    st.page_link("pages/4_Technical_Screener.py",   label="📈  Technical Screener",      help="RSI, MACD, moving averages · Breakout / Oversold presets")
with col2:
    st.page_link("pages/5_Swing_Trades.py",         label="💹  Swing Trades",            help="2–5 day signals with entry, stop-loss & targets")
    st.page_link("pages/6_Intraday_Ideas.py",       label="⚡  Intraday Ideas",           help="Live ORB & VWAP Bounce signals during market hours")
    st.page_link("pages/7_Signal_Log.py",           label="📋  Signal Log & Journal",    help="All signals with outcomes, net P&L and win-rate stats")
    st.page_link("pages/8_Tip_Analyzer.py",         label="🔍  Tip Analyzer",            help="Paste any WhatsApp/Telegram tip — AI pump detector & credibility verdict")

st.markdown("---")
st.caption(
    "⚠️ For educational and informational purposes only — not financial advice. "
    "Always do your own research and use proper risk management."
)
