"""
Page 1: Market Overview
- Index performance (Nifty 50, Bank Nifty, Sensex, sector indices)
- Market breadth (advances vs declines)
- Sector performance heatmap
- Top gainers and losers
- Market status
"""
import streamlit as st
import pandas as pd
from data.fetcher import fetch_index_data, fetch_stock_data, get_top_gainers_losers
from data.market_status import market_status
from analysis.technical import compute_indicators
from ui.charts import index_line_chart, sector_heatmap, market_breadth_gauge
from ui.components import index_metric_card
from ui.formatters import format_pct
from config.settings import INDICES
from config.stock_universe import NIFTY_50, get_universe_tickers

st.set_page_config(page_title="Market Overview", layout="wide", page_icon="📊")
st.title("📊 Market Overview — Indian Markets")

# Market status banner
status = market_status()
status_color = "#26a69a" if status["is_market_open"] else "#ef5350"
st.markdown(
    f'<div style="background:{status_color}22; border-left: 4px solid {status_color}; '
    f'padding: 8px 16px; border-radius: 4px; margin-bottom: 16px;">'
    f'<b>{status["status_label"]}</b> · {status["datetime_ist"]}'
    f'</div>',
    unsafe_allow_html=True,
)

# ── MAJOR INDICES ──────────────────────────────────────────────────────────────
st.subheader("Major Indices")
main_indices = {k: v for k, v in INDICES.items() if k in ["Nifty 50", "Bank Nifty", "Sensex"]}
cols = st.columns(len(main_indices))

for col, (name, ticker) in zip(cols, main_indices.items()):
    with col:
        df = fetch_index_data(ticker, period="5d", interval="1d")
        if df is not None and len(df) >= 2:
            curr = df["Close"].iloc[-1]
            prev = df["Close"].iloc[-2]
            chg = (curr - prev) / prev * 100
            with st.container():
                index_metric_card(name, curr, chg)
                fig = index_line_chart(df.tail(90), name)
                st.plotly_chart(fig, width="stretch", key=f"idx_{ticker}")
        else:
            col.warning(f"{name}: No data")

st.divider()

# ── SECTOR INDICES ─────────────────────────────────────────────────────────────
st.subheader("Sector Performance")
sector_indices = {k: v for k, v in INDICES.items()
                  if k not in ["Nifty 50", "Bank Nifty", "Sensex"]}
sector_data = []
s_cols = st.columns(min(len(sector_indices), 4))

for i, (name, ticker) in enumerate(sector_indices.items()):
    df = fetch_index_data(ticker, period="5d", interval="1d")
    if df is not None and len(df) >= 2:
        curr = df["Close"].iloc[-1]
        prev = df["Close"].iloc[-2]
        chg = (curr - prev) / prev * 100
        sector_data.append({"sector": name, "change_pct": chg, "market_cap": abs(curr)})
        with s_cols[i % 4]:
            arrow = "▲" if chg >= 0 else "▼"
            color = "#26a69a" if chg >= 0 else "#ef5350"
            st.markdown(
                f'<div style="padding:8px; border-radius:6px; border:1px solid #333; margin:4px 0;">'
                f'<b>{name}</b><br>'
                f'<span style="color:{color}; font-size:1.1em;">{arrow} {abs(chg):.2f}%</span> &nbsp;'
                f'<span style="color:#aaa; font-size:0.85em;">{curr:,.2f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.divider()

# ── SECTOR HEATMAP ─────────────────────────────────────────────────────────────
if sector_data:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Sector Heatmap")
        fig = sector_heatmap(sector_data)
        st.plotly_chart(fig, width="stretch")

    # ── MARKET BREADTH ─────────────────────────────────────────────────────────
    with col2:
        st.subheader("Market Breadth")
        with st.spinner("Calculating breadth..."):
            tickers = list(NIFTY_50.values())
            price_data = fetch_stock_data(tickers, period="5d", interval="1d")
            advances = declines = 0
            for ticker, df in price_data.items():
                if df is not None and len(df) >= 2:
                    chg = df["Close"].iloc[-1] - df["Close"].iloc[-2]
                    if chg > 0:
                        advances += 1
                    elif chg < 0:
                        declines += 1
        fig = market_breadth_gauge(advances, declines)
        st.plotly_chart(fig, width="stretch")

st.divider()

# ── TOP GAINERS & LOSERS ───────────────────────────────────────────────────────
st.subheader("Top Gainers & Losers (Nifty 50)")
with st.spinner("Fetching movers..."):
    movers = get_top_gainers_losers(list(NIFTY_50.values()), top_n=5)

g_col, l_col = st.columns(2)
with g_col:
    st.markdown("**🟢 Top Gainers**")
    for item in movers.get("gainers", []):
        chg = item["change_pct"]
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #222;">'
            f'<span><b>{item["ticker"].replace(".NS","")}</b></span>'
            f'<span><span style="color:#aaa;">₹{item["price"]:.2f}</span> '
            f'<span style="color:#26a69a;">▲ {chg:.2f}%</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

with l_col:
    st.markdown("**🔴 Top Losers**")
    for item in movers.get("losers", []):
        chg = item["change_pct"]
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #222;">'
            f'<span><b>{item["ticker"].replace(".NS","")}</b></span>'
            f'<span><span style="color:#aaa;">₹{item["price"]:.2f}</span> '
            f'<span style="color:#ef5350;">▼ {abs(chg):.2f}%</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

# Auto-refresh during market hours
if status["is_market_open"]:
    st.caption("Auto-refreshing every 5 minutes during market hours.")
    st.markdown(
        '<meta http-equiv="refresh" content="300">',
        unsafe_allow_html=True,
    )
