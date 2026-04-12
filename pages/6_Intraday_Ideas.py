"""
Page 6: Intraday Trade Ideas
- Only active during NSE market hours (9:15–15:30 IST)
- Opening Range Breakout and VWAP Bounce signals
- Auto-refresh every 5 minutes
"""
import streamlit as st
from data.fetcher import fetch_bulk_fundamentals
from data.market_status import market_status, is_market_open
from signals.intraday_signals import generate_intraday_signals
from ui.components import signal_card
from ui.charts import candlestick_chart
from data.fetcher import fetch_single_stock
from analysis.technical import compute_indicators
from config.stock_universe import NIFTY_50
from config.settings import INTRADAY_LIQUID_STOCKS, YFINANCE_PERIOD_INTRADAY, YFINANCE_INTERVAL_INTRADAY
from data.fetcher import fetch_stock_data

st.set_page_config(page_title="Intraday Ideas", layout="wide", page_icon="⚡")
st.title("⚡ Intraday Trade Ideas")

status = market_status()

# Status banner
if status["is_market_open"]:
    st.success(f"🟢 Market is OPEN · {status['datetime_ist']}")
elif status["is_pre_market"]:
    st.warning(f"🟡 Pre-Market Session · Market opens at {status['market_open_time']}")
else:
    st.error(f"🔴 {status['status_label']} · {status['datetime_ist']}")
    st.info(
        "Intraday signals are only generated during market hours "
        f"({status['market_open_time']} – {status['market_close_time']}).\n\n"
        "Come back when the market is open to see live trade ideas."
    )
    st.subheader("What to expect during market hours:")
    st.markdown("""
    - **Opening Range Breakout (ORB)**: Signals when price breaks the first 15-min high/low with volume confirmation
    - **VWAP Bounce**: Signals when price bounces off VWAP with RSI confirmation
    - **Auto-refresh**: Page refreshes every 5 minutes
    - **Top 30 liquid Nifty stocks** are scanned for intraday opportunities
    """)
    st.stop()

# ── SELECT LIQUID STOCKS ───────────────────────────────────────────────────────
# Sort Nifty 50 by volume to pick most liquid
@st.cache_data(ttl=900)
def get_liquid_tickers(n: int = INTRADAY_LIQUID_STOCKS) -> list[str]:
    tickers = list(NIFTY_50.values())
    price_data = fetch_stock_data(tickers, period="5d", interval="1d")
    volumes = []
    for ticker, df in price_data.items():
        if df is not None and not df.empty:
            avg_vol = df["Volume"].mean()
            volumes.append((ticker, avg_vol))
    volumes.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in volumes[:n]]

with st.spinner("Selecting liquid stocks..."):
    liquid_tickers = get_liquid_tickers()

# Fetch fund info for names
@st.cache_data(ttl=3600)
def get_fund_map(tickers):
    fund_df = fetch_bulk_fundamentals(tickers)
    if fund_df.empty:
        return {}
    return {row["ticker"]: row.to_dict() for _, row in fund_df.iterrows()}

fund_map = get_fund_map(tuple(liquid_tickers))

# ── GENERATE SIGNALS ───────────────────────────────────────────────────────────
with st.spinner(f"Scanning {len(liquid_tickers)} liquid stocks for intraday setups..."):
    signals = generate_intraday_signals(liquid_tickers, fund_map=fund_map)

# ── METRICS ────────────────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("Stocks Scanned", len(liquid_tickers))
m2.metric("Signals Found", len(signals))
m3.metric("Strategies", "ORB + VWAP Bounce")

st.divider()

if not signals:
    st.info(
        "No intraday setups found at the moment. "
        "Signals appear when price breaks the opening range or bounces off VWAP with volume. "
        "The page will refresh in 5 minutes."
    )
else:
    st.subheader(f"Live Trade Signals ({len(signals)})")
    for signal in signals:
        sd = signal.to_dict()
        signal_card(sd)

        with st.expander(f"📊 5-min Chart: {signal.ticker}", expanded=False):
            df = fetch_single_stock(
                signal.ticker,
                period=YFINANCE_PERIOD_INTRADAY,
                interval=YFINANCE_INTERVAL_INTRADAY,
            )
            if df is not None and not df.empty:
                df_ind = compute_indicators(df)
                fig = candlestick_chart(
                    df_ind, signal.ticker,
                    show_sma=False, show_volume=True,
                    signal_lines={
                        "entry": signal.entry_price,
                        "stop_loss": signal.stop_loss,
                        "target_1": signal.target_1,
                    },
                )
                st.plotly_chart(fig, width="stretch")
