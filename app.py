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
    try:
        from scheduler.jobs import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")


def _catchup_signals():
    from datetime import date
    from data.market_status import is_trading_day
    import pytz
    from datetime import datetime

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    today = date.today().isoformat()

    if not is_trading_day() or now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return

    try:
        from signals.signal_logger import get_signal_logger
        existing = get_signal_logger().get_signals(days_back=1)
        if any(s.get("signal_date") == today for s in existing):
            return
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
        except Exception as e:
            logger.error(f"Catch-up signal generation failed: {e}")

    threading.Thread(target=_generate, daemon=True).start()


_start_scheduler()

try:
    from signals.signal_logger import get_signal_logger
    get_signal_logger().purge_non_trading_day_signals()
except Exception:
    pass

_catchup_signals()

st.set_page_config(
    page_title="IndiaScreener — AI Stock Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "IndiaScreener — AI-powered stock screener for Indian retail investors.",
    },
)

from ui.styles import inject_global_css
inject_global_css()

from data.market_status import market_status
status       = market_status()
is_open      = status["is_market_open"]
status_color = "#00c896" if is_open else "#ff4d6d"
status_label = status["status_label"]
status_time  = status["datetime_ist"]

pill_rgb   = "0,200,150" if is_open else "255,77,109"
pulse_anim = "animation:pulse 1.5s infinite;" if is_open else ""

# ── Hero ────────────────────────────────────────────────────────────────────────
hero_html = (
    '<div style="background:linear-gradient(135deg,#0d1b2a 0%,#1a1a2e 55%,#0f172a 100%);'
    'border:1px solid rgba(255,255,255,0.07);border-radius:20px;'
    'padding:40px 48px 36px;margin-bottom:28px;position:relative;overflow:hidden;">'

    '<div style="position:absolute;top:-70px;right:-70px;width:300px;height:300px;'
    'background:radial-gradient(circle,rgba(240,180,41,0.10),transparent 70%);"></div>'
    '<div style="position:absolute;bottom:-50px;left:180px;width:240px;height:240px;'
    'background:radial-gradient(circle,rgba(0,200,150,0.07),transparent 70%);"></div>'

    '<div style="position:relative;z-index:1;">'

    f'<div style="display:inline-flex;align-items:center;gap:7px;'
    f'background:rgba({pill_rgb},0.12);border:1px solid rgba({pill_rgb},0.3);'
    f'border-radius:20px;padding:5px 14px;font-size:0.72rem;font-weight:700;'
    f'color:{status_color};letter-spacing:0.08em;text-transform:uppercase;margin-bottom:20px;">'
    f'<span style="width:7px;height:7px;border-radius:50%;background:{status_color};{pulse_anim}"></span>'
    f'&nbsp;{status_label}&nbsp;&middot;&nbsp;{status_time}</div>'

    '<h1 style="font-size:2.6rem;font-weight:800;margin:0 0 12px;letter-spacing:-0.03em;'
    'line-height:1.15;background:linear-gradient(135deg,#e8eaf0 30%,#7f8ea3 100%);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
    'IndiaScreener</h1>'

    '<p style="color:#7f8ea3;font-size:1.05rem;margin:0 0 20px;line-height:1.65;max-width:560px;">'
    'AI-powered stock analysis for Indian retail investors — '
    'technical &amp; fundamental screening, live signals, '
    'swing trades and a WhatsApp tip detector, all in one place.</p>'

    '<div style="display:flex;gap:24px;flex-wrap:wrap;">'
    '<div style="display:flex;align-items:center;gap:7px;color:#6b7a99;font-size:0.82rem;">'
    '<span style="color:#f0b429;">●</span> NSE / BSE Real-time Data</div>'
    '<div style="display:flex;align-items:center;gap:7px;color:#6b7a99;font-size:0.82rem;">'
    '<span style="color:#f0b429;">●</span> Nifty 50 + Nifty 200</div>'
    '<div style="display:flex;align-items:center;gap:7px;color:#6b7a99;font-size:0.82rem;">'
    '<span style="color:#f0b429;">●</span> Claude AI Analysis</div>'
    '<div style="display:flex;align-items:center;gap:7px;color:#6b7a99;font-size:0.82rem;">'
    '<span style="color:#f0b429;">●</span> 8 Integrated Tools</div>'
    '</div>'

    '</div></div>'
)
st.markdown(hero_html, unsafe_allow_html=True)

# ── Feature cards ────────────────────────────────────────────────────────────────
FEATURES = [
    {
        "icon": "📊",
        "title": "Market Overview",
        "desc": "Live Nifty 50, Bank Nifty & Sensex with YTD performance comparison chart, sector heatmap, and top movers.",
        "page": "pages/1_Market_Overview.py",
        "tag": "LIVE" if is_open else "EOD",
        "tag_color": "#00c896" if is_open else "#f0b429",
    },
    {
        "icon": "📰",
        "title": "News & Sentiment",
        "desc": "Claude AI reads overnight news and delivers a market summary, sector outlook, and key risk/catalyst breakdown.",
        "page": "pages/2_News_Sentiment.py",
        "tag": "AI",
        "tag_color": "#7c83fd",
    },
    {
        "icon": "🔍",
        "title": "Fundamental Screener",
        "desc": "Filter Nifty 200 stocks by PE ratio, ROE, market cap, debt-to-equity, and revenue growth.",
        "page": "pages/3_Fundamental_Screener.py",
        "tag": "VALUE",
        "tag_color": "#f0b429",
    },
    {
        "icon": "📈",
        "title": "Technical Screener",
        "desc": "Scan for RSI, MACD, Golden Cross, volume breakouts. Presets: Oversold · Breakout · Momentum.",
        "page": "pages/4_Technical_Screener.py",
        "tag": "SCAN",
        "tag_color": "#f0b429",
    },
    {
        "icon": "💹",
        "title": "Swing Trades",
        "desc": "Algorithm-generated 2–5 day trade ideas with entry price, stop-loss and two profit targets.",
        "page": "pages/5_Swing_Trades.py",
        "tag": "SIGNALS",
        "tag_color": "#00c896",
    },
    {
        "icon": "⚡",
        "title": "Intraday Ideas",
        "desc": "ORB (Opening Range Breakout) and VWAP Bounce signals updated in real time during market hours.",
        "page": "pages/6_Intraday_Ideas.py",
        "tag": "INTRADAY",
        "tag_color": "#00c896" if is_open else "#6b7a99",
    },
    {
        "icon": "📋",
        "title": "Signal Log & Journal",
        "desc": "Every signal tracked with outcome — win rate, P&L, strategy performance, and exportable trade history.",
        "page": "pages/7_Signal_Log.py",
        "tag": "JOURNAL",
        "tag_color": "#7c83fd",
    },
    {
        "icon": "🛡️",
        "title": "Tip Analyzer",
        "desc": "Paste any WhatsApp or Telegram stock tip — AI scores it for pump-and-dump risk and gives a plain-English verdict.",
        "page": "pages/8_Tip_Analyzer.py",
        "tag": "AI",
        "tag_color": "#ff4d6d",
    },
]

st.markdown(
    '<p style="color:#6b7a99;font-size:0.72rem;font-weight:700;letter-spacing:0.1em;'
    'text-transform:uppercase;margin-bottom:14px;">Tools</p>',
    unsafe_allow_html=True,
)

cols = st.columns(4)
for i, feat in enumerate(FEATURES):
    with cols[i % 4]:
        tag_html = (
            f'<span style="font-size:0.62rem;font-weight:700;letter-spacing:0.08em;'
            f'color:{feat["tag_color"]};background:{feat["tag_color"]}22;'
            f'border:1px solid {feat["tag_color"]}44;'
            f'border-radius:4px;padding:2px 7px;">{feat["tag"]}</span>'
        )
        st.markdown(
            f'<div style="background:#1e2235;border:1px solid rgba(255,255,255,0.07);'
            f'border-radius:14px;padding:20px;margin-bottom:4px;min-height:130px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">'
            f'<span style="font-size:1.6rem;">{feat["icon"]}</span>'
            f'{tag_html}</div>'
            f'<div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;">{feat["title"]}</div>'
            f'<div style="font-size:0.78rem;color:#6b7a99;line-height:1.55;">{feat["desc"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.page_link(feat["page"], label=f"Open {feat['title']} →")

# ── Footer ───────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="display:flex;justify-content:space-between;align-items:center;'
    'flex-wrap:wrap;gap:8px;">'
    '<span style="color:#6b7a99;font-size:0.75rem;">'
    '⚠️ For educational &amp; informational purposes only — not financial advice. '
    'Always do your own research and use proper risk management.'
    '</span>'
    '<span style="color:#3a3f55;font-size:0.72rem;">Powered by yfinance · Claude AI · Streamlit</span>'
    '</div>',
    unsafe_allow_html=True,
)
