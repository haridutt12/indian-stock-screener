"""
Indian Stock Market Screener — Main Entry Point
Run with: streamlit run app.py
"""
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Indian Stock Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Indian Stock Market Screener — Powered by Python, Streamlit & Claude AI",
    },
)

# Custom CSS for dark theme polish
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    .stMetric label { font-size: 0.85rem; color: #aaa; }
    .stMetric value { font-size: 1.5rem; font-weight: bold; }
    div[data-testid="stMetricDelta"] { font-size: 0.9rem; }
    .stSidebar { background-color: #1a1a2e; }
    h1, h2, h3 { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Home page content
st.title("📊 Indian Stock Market Screener")
st.markdown("**AI-powered market analysis for NSE | Swing & Intraday Trade Ideas**")

st.markdown("""
---

### Navigate using the sidebar:

| Page | Description |
|------|-------------|
| 📊 **Market Overview** | Nifty 50, Bank Nifty, Sensex · Sector heatmap · Top gainers/losers |
| 📰 **News & Sentiment** | Claude AI-powered overnight news analysis · Sector outlook |
| 🔍 **Fundamental Screener** | Filter by PE, ROE, market cap, debt · Value/Growth picks |
| 📈 **Technical Screener** | RSI, MACD, moving averages · Breakout/Oversold presets |
| 💹 **Swing Trades** | 2–5 day trade ideas with entry, stop-loss & targets |
| ⚡ **Intraday Ideas** | Live ORB & VWAP Bounce signals during market hours |

---
""")

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
