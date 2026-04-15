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

# Custom CSS — keep metric/typography polish but do NOT override sidebar bg
# (overriding sidebar bg with a dark colour hides Streamlit's page navigation links)
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    .stMetric label { font-size: 0.85rem; color: #aaa; }
    .stMetric value { font-size: 1.5rem; font-weight: bold; }
    div[data-testid="stMetricDelta"] { font-size: 0.9rem; }
    h1, h2, h3 { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Home page content
st.title("📊 Indian Stock Market Screener")
st.markdown("**AI-powered market analysis for NSE | Swing & Intraday Trade Ideas**")

st.markdown("---")
st.subheader("Quick Navigation")
st.caption("Click any page below — or use the sidebar on the left.")

col1, col2 = st.columns(2)

with col1:
    st.page_link("pages/1_Market_Overview.py",     label="📊 Market Overview",       help="Nifty 50, Bank Nifty, Sensex · Sector heatmap · Top gainers/losers")
    st.page_link("pages/2_News_Sentiment.py",      label="📰 News & Sentiment",       help="Claude AI-powered overnight news analysis · Sector outlook")
    st.page_link("pages/3_Fundamental_Screener.py",label="🔍 Fundamental Screener",   help="Filter by PE, ROE, market cap, debt · Value/Growth picks")
    st.page_link("pages/4_Technical_Screener.py",  label="📈 Technical Screener",     help="RSI, MACD, moving averages · Breakout/Oversold presets")

with col2:
    st.page_link("pages/5_Swing_Trades.py",        label="💹 Swing Trades",           help="2–5 day trade ideas with entry, stop-loss & targets")
    st.page_link("pages/6_Intraday_Ideas.py",      label="⚡ Intraday Ideas",          help="Live ORB & VWAP Bounce signals during market hours")
    st.page_link("pages/7_Signal_Log.py",          label="📋 Signal Log & Backtesting",help="All past signals with outcomes, P&L and win-rate stats")

st.markdown("---")

# Quick market status on home page
from data.market_status import market_status
status = market_status()
status_color = "#26a69a" if status["is_market_open"] else "#ef5350"
st.markdown(
    f'<div style="background:{status_color}22; border-left: 4px solid {status_color}; '
    f'padding: 12px 16px; border-radius: 4px;">'
    f'<b>{status["status_label"]}</b> &nbsp;·&nbsp; {status["datetime_ist"]}'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown("---")
st.caption(
    "⚠️ **Disclaimer**: This tool is for educational and informational purposes only. "
    "Not financial advice. Always do your own research and use proper risk management."
)
