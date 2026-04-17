"""
Page 1: Market Overview
Live prices update in-place via st.fragment — no full page refresh.
"""
import datetime as _dt
import streamlit as st
import pandas as pd
import pytz as _pytz
import yfinance as yf

from data.fetcher import fetch_index_data, fetch_stock_data
from data.market_status import market_status, is_market_open
from ui.charts import sector_heatmap, market_breadth_gauge, ytd_performance_chart
from config.settings import INDICES
from config.stock_universe import NIFTY_50

_IST = _pytz.timezone("Asia/Kolkata")


def _live_quote(ticker: str) -> dict:
    """One fast_info call — returns {} on any failure."""
    try:
        fi    = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev  = float(fi.previous_close)
        return {"price": price, "change_pct": (price - prev) / prev * 100}
    except Exception:
        return {}


# ── Page shell (static — renders once per page load) ──────────────────────────
st.set_page_config(page_title="Market Overview", layout="wide", page_icon="📊")
from ui.styles import inject_global_css; inject_global_css()
st.title("📊 Market Overview — Indian Markets")

status     = market_status()
is_holiday = not status["is_trading_day"]
sc = "#26a69a" if status["is_market_open"] else ("#888" if is_holiday else "#ef5350")
st.markdown(
    f'<div style="background:{sc}22;border-left:4px solid {sc};'
    f'padding:8px 16px;border-radius:4px;margin-bottom:16px;">'
    f'<b>{status["status_label"]}</b> · {status["datetime_ist"]}</div>',
    unsafe_allow_html=True,
)
if is_holiday:
    st.info(
        "Today is a market holiday. All figures reflect the **previous trading day's close**.",
        icon="🏖️",
    )

# ── Load 1Y daily history once (used for chart + YTD calc inside fragment) ────
main_indices   = {k: v for k, v in INDICES.items() if k in ["Nifty 50", "Bank Nifty", "Sensex"]}
sector_indices = {k: v for k, v in INDICES.items() if k not in main_indices}

hist_1y: dict = {}
for _name, _ticker in main_indices.items():
    _df = fetch_index_data(_ticker, period="1y", interval="1d")
    if _df is not None and not _df.empty:
        hist_1y[_name] = _df

# ── Fragment 1: major index cards — refreshes every 30 s during market ─────────
_fast_interval = 30 if status["is_market_open"] else None


@st.fragment(run_every=_fast_interval)
def _index_metrics():
    _live = is_market_open()
    st.subheader("Major Indices")
    cols = st.columns(len(main_indices))

    for col, (name, ticker) in zip(cols, main_indices.items()):
        df = hist_1y.get(name)
        if df is None or len(df) < 2:
            with col:
                st.warning(f"{name}: No data")
            continue

        if _live:
            q       = _live_quote(ticker)
            curr    = q.get("price", float(df["Close"].iloc[-1]))
            day_chg = q.get("change_pct", 0.0)
            as_of   = "Live"
        else:
            curr    = float(df["Close"].iloc[-1])
            day_chg = (curr - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
            as_of   = str(df.index[-1])[:10]

        jan1    = _dt.date(df.index[-1].year, 1, 1)
        ytd_df  = df[df.index.date >= jan1]
        ytd_pct = (
            (curr - float(ytd_df["Close"].iloc[0])) / float(ytd_df["Close"].iloc[0]) * 100
            if not ytd_df.empty else None
        )

        day_arrow = "▲" if day_chg >= 0 else "▼"
        day_color = "#00c896" if day_chg >= 0 else "#ff4d6d"
        ytd_color = "#00c896" if (ytd_pct is None or ytd_pct >= 0) else "#ff4d6d"
        ytd_label = f"YTD {ytd_pct:+.2f}%" if ytd_pct is not None else ""

        with col:
            st.markdown(
                f'<div style="background:#1e2235;border-radius:12px;padding:16px 20px;'
                f'border:1px solid rgba(255,255,255,0.07);margin-bottom:8px;">'
                f'<div style="font-size:0.75rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{name}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;'
                f'letter-spacing:-0.02em;">{curr:,.2f}</div>'
                f'<div style="display:flex;gap:12px;margin-top:6px;align-items:center;">'
                f'<span style="font-size:0.9rem;font-weight:700;color:{day_color};">'
                f'{day_arrow} {abs(day_chg):.2f}% today</span>'
                + (f'<span style="font-size:0.8rem;color:{ytd_color};opacity:0.85;">'
                   f'{ytd_label}</span>' if ytd_label else '')
                + f'</div>'
                f'<div style="font-size:0.72rem;color:#6b7a99;margin-top:4px;">{as_of}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if _live:
        _ts = _dt.datetime.now(_IST).strftime("%H:%M:%S")
        st.caption(f"↻ {_ts} IST · prices update every 30s")


_index_metrics()

# ── Static: YTD chart — heavy fetch done once, no need for live updates ────────
if hist_1y:
    st.markdown("#### Index Performance Comparison")
    try:
        st.plotly_chart(ytd_performance_chart(hist_1y), use_container_width=True, key="ytd_chart")
    except Exception:
        st.info("Chart temporarily unavailable.")

st.divider()

# ── Fragment 2: sector tiles + heatmap + breadth + movers — every 2 min ────────
_slow_interval = 120 if status["is_market_open"] else None


@st.fragment(run_every=_slow_interval)
def _market_data():
    _live = is_market_open()

    # ── Sector tiles ───────────────────────────────────────────────────────────
    st.subheader("Sector Performance")
    sector_data = []
    s_cols = st.columns(min(len(sector_indices), 4))

    for i, (name, ticker) in enumerate(sector_indices.items()):
        df = fetch_index_data(ticker, period="5d", interval="1d")
        if df is None or len(df) < 2:
            continue
        if _live:
            q    = _live_quote(ticker)
            curr = q.get("price", float(df["Close"].iloc[-1]))
            chg  = q.get("change_pct", 0.0)
        else:
            curr = float(df["Close"].iloc[-1])
            chg  = (curr - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
        sector_data.append({"sector": name, "change_pct": chg, "market_cap": abs(curr)})
        arrow = "▲" if chg >= 0 else "▼"
        color = "#26a69a" if chg >= 0 else "#ef5350"
        with s_cols[i % 4]:
            st.markdown(
                f'<div style="padding:8px;border-radius:6px;border:1px solid #333;margin:4px 0;">'
                f'<b>{name}</b><br>'
                f'<span style="color:{color};font-size:1.1em;">{arrow} {abs(chg):.2f}%</span>'
                f'&nbsp;<span style="color:#aaa;font-size:0.85em;">{curr:,.2f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if not sector_data:
        return

    st.divider()

    # ── Fetch all Nifty 50 prices once — reuse for breadth AND movers ─────────
    nifty_tickers = list(NIFTY_50.values())
    if _live:
        price_data = fetch_stock_data(nifty_tickers, period="2d", interval="5m", use_cache=True)
    else:
        price_data = fetch_stock_data(nifty_tickers, period="5d", interval="1d")

    # ── Heatmap + Breadth ──────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Sector Heatmap")
        try:
            st.plotly_chart(sector_heatmap(sector_data), width="stretch")
        except Exception:
            pass

    with c2:
        st.subheader("Market Breadth")
        advances = declines = 0
        for t, df in price_data.items():
            if df is None or df.empty:
                continue
            if _live:
                df = df.dropna(subset=["Close"])
                today    = df.index[-1].date()
                today_df = df[df.index.date == today]
                prev_df  = df[df.index.date < today]
                if today_df.empty or prev_df.empty:
                    continue
                chg = float(today_df["Close"].iloc[-1]) - float(prev_df["Close"].iloc[-1])
            else:
                if len(df) < 2:
                    continue
                chg = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
            advances += (1 if chg > 0 else 0)
            declines += (1 if chg < 0 else 0)
        try:
            st.plotly_chart(market_breadth_gauge(advances, declines), width="stretch")
        except Exception:
            pass

    st.divider()

    # ── Top Gainers / Losers ───────────────────────────────────────────────────
    st.subheader("Top Gainers & Losers (Nifty 50)")
    changes = []
    for t, df in price_data.items():
        if df is None or df.empty:
            continue
        try:
            if _live:
                df = df.dropna(subset=["Close"])
                today    = df.index[-1].date()
                today_df = df[df.index.date == today]
                prev_df  = df[df.index.date < today]
                if today_df.empty or prev_df.empty:
                    continue
                curr_p = float(today_df["Close"].iloc[-1])
                prev_p = float(prev_df["Close"].iloc[-1])
            else:
                if len(df) < 2:
                    continue
                curr_p = float(df["Close"].iloc[-1])
                prev_p = float(df["Close"].iloc[-2])
            changes.append({"ticker": t, "price": curr_p,
                            "change_pct": (curr_p - prev_p) / prev_p * 100})
        except Exception:
            continue

    g_col, l_col = st.columns(2)
    if changes:
        df_ch = pd.DataFrame(changes).sort_values("change_pct", ascending=False)
        gainers = df_ch.head(5).to_dict("records")
        losers  = df_ch.tail(5).to_dict("records")
    else:
        gainers, losers = [], []

    with g_col:
        st.markdown("**🟢 Top Gainers**")
        for item in gainers:
            chg = item["change_pct"]
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'border-bottom:1px solid #222;">'
                f'<span><b>{item["ticker"].replace(".NS","")}</b></span>'
                f'<span><span style="color:#aaa;">₹{item["price"]:.2f}</span> '
                f'<span style="color:#26a69a;">▲ {chg:.2f}%</span></span></div>',
                unsafe_allow_html=True,
            )
    with l_col:
        st.markdown("**🔴 Top Losers**")
        for item in losers:
            chg = item["change_pct"]
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'border-bottom:1px solid #222;">'
                f'<span><b>{item["ticker"].replace(".NS","")}</b></span>'
                f'<span><span style="color:#aaa;">₹{item["price"]:.2f}</span> '
                f'<span style="color:#ef5350;">▼ {abs(chg):.2f}%</span></span></div>',
                unsafe_allow_html=True,
            )

    if _live:
        _ts = _dt.datetime.now(_IST).strftime("%H:%M:%S")
        st.caption(f"↻ {_ts} IST · sectors & movers update every 2 min")


_market_data()
