"""
Page 6: Intraday Trade Ideas
- Only active during NSE market hours (9:15–15:30 IST)
- Opening Range Breakout, VWAP Bounce, EMA Crossover, Supertrend Signal
- Signals cached for 5 minutes; refresh button forces rescan
"""
import time
import datetime as _dt
import streamlit as st
import pytz as _pytz

from data.fetcher import fetch_bulk_fundamentals, fetch_stock_data, fetch_single_stock
from data.market_status import market_status, is_market_open
from signals.intraday_signals import generate_intraday_signals
from ui.components import signal_card, research_disclaimer
from ui.styles import page_header, show_loading, auth_guard, user_sidebar
from ui.charts import candlestick_chart
from analysis.technical import compute_indicators
from config.stock_universe import NIFTY_50
from config.settings import (
    INTRADAY_LIQUID_STOCKS,
    YFINANCE_PERIOD_INTRADAY,
    YFINANCE_INTERVAL_INTRADAY,
)

_IST = _pytz.timezone("Asia/Kolkata")

st.set_page_config(page_title="Intraday Ideas · NiftyEdge", layout="wide", page_icon="⚡")
from ui.styles import inject_global_css; inject_global_css()
auth_guard()

# ── PAGE HEADER ───────────────────────────────────────────────────────────────────────────────
page_header("⚡ Intraday Trade Ideas", subtitle="NSE · Equity · Intraday",
            badge="LIVE", badge_color="#00c896")
research_disclaimer()

status = market_status()

# ── MARKET STATUS CARD ──────────────────────────────────────────────────────────────────────────────────
if status["is_market_open"]:
    dot_color, label_color, bg = "#00c896", "#00c896", "rgba(0,200,150,0.06)"
    border  = "rgba(0,200,150,0.2)"
    dot_anim = "animation:pulse 1.2s ease-in-out infinite;"
    label   = "Market Open"
elif status["is_pre_market"]:
    dot_color, label_color, bg = "#f0b429", "#f0b429", "rgba(240,180,41,0.06)"
    border  = "rgba(240,180,41,0.2)"
    dot_anim = "animation:pulse 1.5s ease-in-out infinite;"
    label   = "Pre-Market"
else:
    dot_color, label_color, bg = "#ff4d6d", "#ff4d6d", "rgba(255,77,109,0.05)"
    border  = "rgba(255,77,109,0.15)"
    dot_anim = ""
    label   = status["status_label"]

st.markdown(
    f'<div style="background:{bg};border:1px solid {border};border-radius:12px;'
    f'padding:12px 18px;display:flex;align-items:center;justify-content:space-between;'
    f'margin-bottom:20px;">'
    f'<div style="display:flex;align-items:center;gap:10px;">'
    f'<div style="width:9px;height:9px;border-radius:50%;background:{dot_color};'
    f'flex-shrink:0;{dot_anim}"></div>'
    f'<span style="color:{label_color};font-weight:700;font-size:0.9rem;">{label}</span>'
    f'<span style="color:#475569;font-size:0.8rem;">{status["datetime_ist"]}</span>'
    f'</div>'
    f'<span style="color:#374151;font-size:0.75rem;">'
    f'{status["market_open_time"]} – {status["market_close_time"]} IST'
    f'</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── MARKET CLOSED STATE ─────────────────────────────────────────────────────────────────────────────────
if not status["is_market_open"] and not status["is_pre_market"]:

    now_ist   = _dt.datetime.now(_IST)
    next_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    if now_ist >= next_open:
        next_open += _dt.timedelta(days=1)
    diff      = next_open - now_ist
    hrs, rem  = divmod(int(diff.total_seconds()), 3600)
    mins      = rem // 60

    st.markdown(
        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
        f'border:1px solid rgba(255,255,255,0.06);border-radius:16px;'
        f'padding:24px 28px;margin-bottom:24px;display:flex;'
        f'align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;">'
        f'<div>'
        f'<div style="color:#64748b;font-size:0.7rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">'
        f'Next Market Open</div>'
        f'<div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;letter-spacing:-0.02em;">'
        f'{hrs}h {mins}m</div>'
        f'<div style="color:#475569;font-size:0.78rem;margin-top:4px;">'
        f'Tomorrow at 09:15 IST</div>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div style="color:#64748b;font-size:0.7rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">'
        f'Scanning</div>'
        f'<div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;">30 stocks</div>'
        f'<div style="color:#475569;font-size:0.78rem;margin-top:4px;">Top Nifty 50 by volume</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    strategies = [
        {
            "icon": "📊",
            "name": "Opening Range Breakout",
            "short": "ORB",
            "color": "#f0b429",
            "desc": "Price breaks the first 15-min high/low with 1.5× volume surge",
            "tags": ["Volume", "Breakout", "15-min range"],
        },
        {
            "icon": "📈",
            "name": "VWAP Bounce",
            "short": "VWAP",
            "color": "#00c896",
            "desc": "Price bounces off VWAP support with RSI between 40–60",
            "tags": ["VWAP", "RSI confirm", "Mean reversion"],
        },
        {
            "icon": "⚡",
            "name": "EMA Crossover",
            "short": "EMA",
            "color": "#7c83fd",
            "desc": "EMA9 crosses above EMA21 on 5-min chart with volume and VWAP confirmation",
            "tags": ["EMA9 × EMA21", "Volume", "5-min"],
        },
        {
            "icon": "🔄",
            "name": "Supertrend Signal",
            "short": "ST",
            "color": "#06b6d4",
            "desc": "Supertrend flips bullish on 5-min chart while price trades above VWAP",
            "tags": ["Supertrend", "VWAP", "Trend flip"],
        },
    ]

    st.markdown(
        '<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
        'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:12px;">'
        'Active Strategies — Live during market hours</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for i, s in enumerate(strategies):
        tags_html = " ".join([
            f'<span style="background:{s["color"]}15;color:{s["color"]};'
            f'border-radius:4px;padding:2px 7px;font-size:0.65rem;font-weight:600;">{t}</span>'
            for t in s["tags"]
        ])
        with cols[i % 2]:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.06);border-top:3px solid {s["color"]};'
                f'border-radius:14px;padding:18px;margin-bottom:10px;">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
                f'<span style="font-size:1.4rem;">{s["icon"]}</span>'
                f'<div>'
                f'<div style="color:#f1f5f9;font-weight:700;font-size:0.9rem;">{s["name"]}</div>'
                f'<div style="color:{s["color"]};font-size:0.7rem;font-weight:700;'
                f'letter-spacing:0.05em;">{s["short"]}</div>'
                f'</div>'
                f'</div>'
                f'<div style="color:#64748b;font-size:0.78rem;line-height:1.5;margin-bottom:10px;">'
                f'{s["desc"]}</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{tags_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.stop()

# ── SELECT LIQUID STOCKS ──────────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_liquid_tickers(n: int = INTRADAY_LIQUID_STOCKS) -> list[str]:
    tickers    = list(NIFTY_50.values())
    price_data = fetch_stock_data(tickers, period="5d", interval="1d")
    volumes    = []
    for ticker, df in price_data.items():
        if df is not None and not df.empty:
            volumes.append((ticker, df["Volume"].mean()))
    volumes.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in volumes[:n]]

_liq_slot = show_loading("Identifying the most liquid F&amp;O stocks by 5-day average volume…", "#7c83fd")
liquid_tickers = get_liquid_tickers()
_liq_slot.empty()

@st.cache_data(ttl=3600, show_spinner=False)
def get_fund_map(tickers):
    fund_df = fetch_bulk_fundamentals(tickers)
    if fund_df.empty:
        return {}
    return {row["ticker"]: row.to_dict() for _, row in fund_df.iterrows()}

_fund_slot = show_loading("Loading fundamental data — PE, ROE, debt ratios for quality filters…", "#7c83fd")
fund_map = get_fund_map(tuple(liquid_tickers))
_fund_slot.empty()

# ── CACHED SIGNAL SCAN — 5-min TTL ────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _cached_intraday_scan(tickers_tuple: tuple, _fund_map: dict) -> dict:
    """Returns {signals: list[dict], scanned_at: float}. Cached 5 min."""
    sigs = generate_intraday_signals(list(tickers_tuple), fund_map=_fund_map)
    return {"signals": [s.to_dict() for s in sigs], "scanned_at": time.time()}

# Sidebar refresh button
with st.sidebar:
    st.header("Controls")
    refresh_btn = st.button("🔄 Refresh Signals", type="primary", use_container_width=True)

    st.divider()
    user_sidebar()
if refresh_btn:
    _cached_intraday_scan.clear()

_scan_slot = show_loading(f"Scanning {len(liquid_tickers)} liquid stocks for intraday breakouts, momentum, and VWAP setups…", "#f0b429")
result = _cached_intraday_scan(tuple(liquid_tickers), fund_map)
_scan_slot.empty()
signals     = result["signals"]
scanned_at  = result.get("scanned_at", time.time())

# ── LAST SCANNED BADGE ──────────────────────────────────────────────────────────────────────────────────
_time_str = _dt.datetime.fromtimestamp(scanned_at, _IST).strftime("%H:%M IST")
_elapsed  = int(time.time() - scanned_at)
_from_cache = "· from cache" if _elapsed > 30 else ""
st.markdown(
    f'<div style="margin-bottom:6px;">'
    f'<span style="font-size:0.68rem;color:#374151;">🕐 Scanned at {_time_str} {_from_cache}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── STATS STRIP ────────────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;">'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Scanned</div>'
    f'<div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;">{len(liquid_tickers)}'
    f'<span style="font-size:0.85rem;color:#475569;"> stocks</span></div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Signals</div>'
    f'<div style="color:{"#00c896" if signals else "#f1f5f9"};font-size:1.5rem;font-weight:800;">'
    f'{len(signals)}</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Strategies</div>'
    f'<div style="color:#f1f5f9;font-size:0.85rem;font-weight:700;line-height:1.4;">'
    f'ORB · VWAP<br>EMA · ST</div>'
    f'</div>'

    f'</div>',
    unsafe_allow_html=True,
)

# ── SIGNALS OR EMPTY STATE ─────────────────────────────────────────────────────────────────────────────────
if not signals:
    st.markdown(
        '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);'
        'border-radius:14px;padding:32px;text-align:center;margin:8px 0;">'
        '<div style="font-size:1.5rem;margin-bottom:8px;">🔍</div>'
        '<div style="color:#475569;font-weight:600;margin-bottom:4px;">No setups detected yet</div>'
        '<div style="color:#374151;font-size:0.8rem;">'
        'Signals appear when ORB, VWAP, EMA or Supertrend conditions trigger with volume'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
        f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:8px;">'
        f'Live Signals — {len(signals)} found</div>',
        unsafe_allow_html=True,
    )
    for i, sig in enumerate(signals):
        signal_card(sig)
        ticker = sig.get("ticker", "")
        with st.expander(f"📊 5-min Chart · {ticker.replace('.NS', '')}", expanded=False):
            df = fetch_single_stock(
                ticker,
                period=YFINANCE_PERIOD_INTRADAY,
                interval=YFINANCE_INTERVAL_INTRADAY,
            )
            if df is not None and not df.empty:
                df_ind = compute_indicators(df)
                fig    = candlestick_chart(
                    df_ind, ticker,
                    show_sma=False, show_volume=True,
                    signal_lines={
                        "entry":     sig.get("entry", 0),
                        "stop_loss": sig.get("stop_loss", 0),
                        "target_1":  sig.get("target_1", 0),
                    },
                )
                st.plotly_chart(fig, use_container_width=True, key=f"intra_candle_{i}_{ticker}")
