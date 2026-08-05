"""
NiftyEdge — App entry point and navigation controller.
All home page content lives in home.py; this file wires up st.navigation()
so the sidebar shows "Home" instead of "app".
"""
import logging
import threading
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_catchup_running = threading.Event()


@st.cache_resource
def _start_scheduler():
    try:
        from scheduler.jobs import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error("Scheduler failed to start: %s", e)


def _catchup_signals():
    from datetime import date, datetime
    from data.market_status import is_trading_day

    if _catchup_running.is_set():
        return

    import pytz
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    today = date.today().isoformat()

    try:
        from signals.signal_logger import get_signal_logger
        existing = get_signal_logger().get_signals(days_back=1)
        if any(s.get("signal_date") == today for s in existing):
            return
    except Exception:
        return

    def _generate():
        _catchup_running.set()
        try:
            from signals.swing_signals import generate_swing_signals
            from config.stock_universe import NIFTY_50
            tickers = list(NIFTY_50.values())
            generate_swing_signals(tickers)
            if is_trading_day() and (now.hour > 9 or (now.hour == 9 and now.minute >= 30)):
                if now.hour < 15 or (now.hour == 15 and now.minute < 30):
                    from signals.intraday_signals import generate_intraday_signals
                    generate_intraday_signals(tickers)
        except Exception as e:
            logger.error("Catch-up signal generation failed: %s", e)
        finally:
            _catchup_running.clear()

    threading.Thread(target=_generate, daemon=True).start()


st.set_page_config(
    page_title="NiftyEdge — AI Stock Analysis",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "NiftyEdge — AI-powered stock analysis for Indian retail investors."},
)

_start_scheduler()

# Record the visit once per session
if not st.session_state.get("_ne_visit_recorded"):
    try:
        from auth.user_store import upsert_user as _upsert
        _upsert(
            st.user.email,
            getattr(st.user, "name",    "") or "",
            getattr(st.user, "picture", "") or "",
        )
        st.session_state["_ne_visit_recorded"] = True
    except Exception:
        pass

try:
    from signals.signal_logger import get_signal_logger as _gl
    _gl().purge_non_trading_day_signals()
except Exception:
    pass

_catchup_signals()

pg = st.navigation(
    [
        st.Page("home.py",                          title="Home",                 icon="🏠", default=True),
        st.Page("pages/1_Market_Overview.py",       title="Market Overview",      icon="📊"),
        st.Page("pages/2_Smart_Money.py",           title="Smart Money",          icon="💰"),
        st.Page("pages/3_Signal_Log.py",            title="Signal Log",           icon="📋"),
        st.Page("pages/4_Swing_Trades.py",          title="Swing Trades",         icon="📈"),
        st.Page("pages/5_Intraday_Ideas.py",        title="Intraday Ideas",       icon="⚡"),
        st.Page("pages/6_Technical_Screener.py",    title="Technical Screener",   icon="🔍"),
        st.Page("pages/7_Fundamental_Screener.py",  title="Fundamental Screener", icon="📊"),
        st.Page("pages/8_News_Sentiment.py",        title="News & Sentiment",     icon="📰"),
        st.Page("pages/9_Tip_Analyzer.py",          title="Tip Analyzer",         icon="🛡️"),
        st.Page("pages/10_AI_Analyst.py",           title="AI Analyst",           icon="🤖"),
        st.Page("pages/11_Portfolio_Health.py",     title="Portfolio Health",     icon="📊"),
    ],
    position="sidebar",
)

pg.run()
