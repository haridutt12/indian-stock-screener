"""
Page 1: Market Overview
- Index performance (Nifty 50, Bank Nifty, Sensex, sector indices)
- Market breadth (advances vs declines)
- Sector performance heatmap
- Top gainers and losers
- Market status
"""
import datetime as _dt
import streamlit as st
import pandas as pd
import yfinance as yf
from data.fetcher import fetch_index_data, fetch_stock_data, get_top_gainers_losers
from data.market_status import market_status, is_market_open
from ui.charts import index_line_chart, sector_heatmap, market_breadth_gauge, ytd_performance_chart
from ui.components import index_metric_card
from config.settings import INDICES
from config.stock_universe import NIFTY_50


def _live_quote(ticker: str) -> dict:
    """Fetch latest price + change vs prev close via fast_info. Returns {} on failure."""
    try:
        fi = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev  = float(fi.previous_close)
        return {
            "price": price,
            "change_pct": (price - prev) / prev * 100,
        }
    except Exception:
        return {}


st.set_page_config(page_title="Market Overview", layout="wide", page_icon="📊")
from ui.styles import inject_global_css; inject_global_css()
st.title("📊 Market Overview — Indian Markets")

# Market status banner
status = market_status()
is_holiday = not status["is_trading_day"]
status_color = "#26a69a" if status["is_market_open"] else ("#888" if is_holiday else "#ef5350")
st.markdown(
    f'<div style="background:{status_color}22; border-left: 4px solid {status_color}; '
    f'padding: 8px 16px; border-radius: 4px; margin-bottom: 16px;">'
    f'<b>{status["status_label"]}</b> · {status["datetime_ist"]}'
    f'</div>',
    unsafe_allow_html=True,
)
if is_holiday:
    st.info(
        "Today is a market holiday. All figures below reflect the **previous trading day's close**. "
        "No intraday data is available.",
        icon="🏖️",
    )

# ── MAJOR INDICES ──────────────────────────────────────────────────────────────
live = is_market_open()
st.subheader("Major Indices")
if live:
    st.caption("🟢 Live prices — refreshes every 5 minutes")

main_indices = {k: v for k, v in INDICES.items() if k in ["Nifty 50", "Bank Nifty", "Sensex"]}

# Fetch 1Y history once for the combined chart + metric cards
hist_1y: dict = {}
for name, ticker in main_indices.items():
    df = fetch_index_data(ticker, period="1y", interval="1d")
    if df is not None and not df.empty:
        hist_1y[name] = df

# ── Metric cards ───────────────────────────────────────────────────────────────
cols = st.columns(len(main_indices))
for col, (name, ticker) in zip(cols, main_indices.items()):
    df = hist_1y.get(name)
    if df is not None and len(df) >= 2:
        if live:
            quote = _live_quote(ticker)
            curr     = quote.get("price", float(df["Close"].iloc[-1]))
            day_chg  = quote.get("change_pct", 0.0)
            as_of_str = "Live"
        else:
            curr      = float(df["Close"].iloc[-1])
            prev_day  = float(df["Close"].iloc[-2])
            day_chg   = (curr - prev_day) / prev_day * 100
            as_of     = df.index[-1]
            as_of_str = as_of.strftime("%d %b %Y") if hasattr(as_of, "strftime") else str(as_of)[:10]

        # YTD return: from Jan 1 of current year
        jan1 = _dt.date(df.index[-1].year, 1, 1)
        ytd_df = df[df.index.date >= jan1]
        ytd_pct = None
        if not ytd_df.empty:
            ytd_base = float(ytd_df["Close"].iloc[0])
            ytd_pct  = (curr - ytd_base) / ytd_base * 100
        ytd_label = f"YTD {ytd_pct:+.2f}%" if ytd_pct is not None else ""

        day_arrow = "▲" if day_chg >= 0 else "▼"
        day_color = "#00c896" if day_chg >= 0 else "#ff4d6d"
        ytd_color = "#00c896" if (ytd_pct is None or ytd_pct >= 0) else "#ff4d6d"

        with col:
            st.markdown(
                f'<div style="background:#1e2235;border-radius:12px;padding:16px 20px;'
                f'border:1px solid rgba(255,255,255,0.07);margin-bottom:8px;">'
                f'<div style="font-size:0.75rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">'
                f'{name}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;'
                f'letter-spacing:-0.02em;">{curr:,.2f}</div>'
                f'<div style="display:flex;gap:12px;margin-top:6px;align-items:center;">'
                f'<span style="font-size:0.9rem;font-weight:700;color:{day_color};">'
                f'{day_arrow} {abs(day_chg):.2f}% today</span>'
                + (f'<span style="font-size:0.8rem;color:{ytd_color};opacity:0.85;">{ytd_label}</span>'
                   if ytd_label else '')
                + f'</div>'
                f'<div style="font-size:0.72rem;color:#6b7a99;margin-top:4px;">{as_of_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        with col:
            st.warning(f"{name}: No data")

# ── Combined YTD performance chart ─────────────────────────────────────────────
if hist_1y:
    st.markdown("#### Index Performance Comparison")
    try:
        fig_ytd = ytd_performance_chart(hist_1y)
        st.plotly_chart(fig_ytd, use_container_width=True, key="ytd_chart")
    except Exception as _e:
        st.info("Chart temporarily unavailable — data will appear on next refresh.")

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
        if live:
            quote = _live_quote(ticker)
            curr = quote.get("price", float(df["Close"].iloc[-1]))
            chg  = quote.get("change_pct", 0.0)
        else:
            curr = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            chg  = (curr - prev) / prev * 100
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
            advances = declines = 0
            if live:
                price_data = fetch_stock_data(tickers, period="2d", interval="5m", use_cache=True)
                for ticker, df in price_data.items():
                    if df is None or df.empty:
                        continue
                    df = df.dropna(subset=["Close"])
                    today     = df.index[-1].date()
                    today_df  = df[df.index.date == today]
                    prev_df   = df[df.index.date < today]
                    if today_df.empty or prev_df.empty:
                        continue
                    chg = float(today_df["Close"].iloc[-1]) - float(prev_df["Close"].iloc[-1])
                    if chg > 0:
                        advances += 1
                    elif chg < 0:
                        declines += 1
            else:
                price_data = fetch_stock_data(tickers, period="5d", interval="1d")
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
    if live:
        # Use 5m intraday data vs yesterday's close for real-time movers
        tickers = list(NIFTY_50.values())
        price_data = fetch_stock_data(tickers, period="2d", interval="5m", use_cache=True)
        changes = []
        for ticker, df in price_data.items():
            if df is None or df.empty:
                continue
            df = df.dropna(subset=["Close"])
            today    = df.index[-1].date()
            today_df = df[df.index.date == today]
            prev_df  = df[df.index.date < today]
            if today_df.empty or prev_df.empty:
                continue
            curr_close = float(today_df["Close"].iloc[-1])
            prev_close = float(prev_df["Close"].iloc[-1])
            pct = (curr_close - prev_close) / prev_close * 100
            changes.append({"ticker": ticker, "price": curr_close, "change_pct": pct})
        if changes:
            changes_df = pd.DataFrame(changes).sort_values("change_pct", ascending=False)
            movers = {
                "gainers": changes_df.head(5).to_dict("records"),
                "losers":  changes_df.tail(5).to_dict("records"),
            }
        else:
            movers = get_top_gainers_losers(list(NIFTY_50.values()), top_n=5)
    else:
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
from datetime import datetime
import pytz
now_str = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S IST")
st.caption(f"Last updated: {now_str}")
if status["is_market_open"]:
    st.caption("Auto-refreshing every 5 minutes during market hours.")
    st.markdown(
        '<meta http-equiv="refresh" content="300">',
        unsafe_allow_html=True,
    )
