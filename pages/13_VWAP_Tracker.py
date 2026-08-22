"""
Page 13: Intraday VWAP Tracker
Live VWAP + upper/lower VWAP bands (±1σ, ±2σ) for watchlist stocks.
Auto-refreshes every 60s during market hours.
"""
import datetime
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

st.set_page_config(page_title="VWAP Tracker · NiftyEdge", layout="wide", page_icon="📡")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()

from data.market_status import is_market_open
from config.stock_universe import NIFTY_50

page_header("VWAP Tracker", "Intraday VWAP · Bands · Position relative to VWAP")
user_sidebar()

# ── Sidebar: ticker selection ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Watchlist")
    _default_tickers = ["RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS"]
    _preset = st.selectbox(
        "Quick preset",
        ["Custom", "Nifty 50 Heavy", "Bank Nifty"],
        key="vwap_preset",
    )
    if _preset == "Nifty 50 Heavy":
        _default_tickers = list(NIFTY_50.values())[:10]
    elif _preset == "Bank Nifty":
        _default_tickers = ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS",
                             "AXISBANK.NS", "SBIN.NS", "INDUSINDBK.NS"]

    _custom_raw = st.text_area(
        "Tickers (one per line, .NS suffix)",
        value="\n".join(_default_tickers),
        height=200,
        key="vwap_tickers",
    )
    _tickers = [t.strip().upper() for t in _custom_raw.strip().splitlines() if t.strip()]
    if not _tickers:
        st.warning("Add at least one ticker.")
        st.stop()

_is_live = is_market_open()
_refresh  = 60 if _is_live else None
_status_c = "#00c896" if _is_live else "#ff4d6d"
st.markdown(
    f'<div style="font-size:0.72rem;color:{_status_c};font-weight:700;margin-bottom:16px;">'
    f'{"● Market live — auto-refresh every 60s" if _is_live else "● Market closed — showing last session data"}'
    f'</div>',
    unsafe_allow_html=True,
)


# ── VWAP computation ──────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _fetch_intraday(ticker: str) -> pd.DataFrame:
    try:
        df = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[df["Volume"] > 0].copy()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


def _compute_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Compute VWAP and ±1σ/±2σ bands using cumulative method."""
    if df.empty:
        return df
    df = df.copy()
    df["TP"]      = (df["High"] + df["Low"] + df["Close"]) / 3
    df["TPV"]     = df["TP"] * df["Volume"]
    df["cumTPV"]  = df["TPV"].cumsum()
    df["cumVol"]  = df["Volume"].cumsum()
    df["VWAP"]    = df["cumTPV"] / df["cumVol"]

    # VWAP deviation bands (cumulative std of TP weighted by volume)
    df["TP_sq"]   = df["TP"] ** 2
    df["TP_sqV"]  = df["TP_sq"] * df["Volume"]
    df["cumTP2V"] = df["TP_sqV"].cumsum()
    df["variance"]= (df["cumTP2V"] / df["cumVol"]) - df["VWAP"] ** 2
    df["variance"] = df["variance"].clip(lower=0)
    df["sigma"]   = df["variance"] ** 0.5

    df["VWAP+1"]  = df["VWAP"] + df["sigma"]
    df["VWAP-1"]  = df["VWAP"] - df["sigma"]
    df["VWAP+2"]  = df["VWAP"] + 2 * df["sigma"]
    df["VWAP-2"]  = df["VWAP"] - 2 * df["sigma"]
    return df


# ── Render in a fragment that auto-refreshes ──────────────────────────────────
@st.fragment(run_every=_refresh)
def _render_vwap():
    now = datetime.datetime.now().strftime("%H:%M:%S")
    st.caption(f"Last updated: {now}")

    # Summary row: all tickers at a glance
    _summary_items = []
    _ticker_data   = {}

    for ticker in _tickers:
        df = _fetch_intraday(ticker)
        if df.empty:
            _summary_items.append({"ticker": ticker, "price": None, "vwap": None, "pos": None})
            continue
        df = _compute_vwap(df)
        _ticker_data[ticker] = df
        last = df.iloc[-1]
        price  = float(last["Close"])
        vwap   = float(last["VWAP"])
        _summary_items.append({
            "ticker": ticker,
            "label":  ticker.replace(".NS", ""),
            "price":  price,
            "vwap":   vwap,
            "pos":    "ABOVE" if price > vwap else "BELOW",
            "pct":    (price - vwap) / vwap * 100,
            "sigma":  float(last["sigma"]),
            "s1up":   float(last["VWAP+1"]),
            "s1dn":   float(last["VWAP-1"]),
            "s2up":   float(last["VWAP+2"]),
            "s2dn":   float(last["VWAP-2"]),
        })

    # Summary strip
    n_above = sum(1 for s in _summary_items if s.get("pos") == "ABOVE")
    n_below = sum(1 for s in _summary_items if s.get("pos") == "BELOW")
    st.markdown(
        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        f'border-radius:10px;padding:10px 16px;margin-bottom:16px;'
        f'display:flex;gap:24px;align-items:center;">'
        f'<span style="font-size:0.62rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Watchlist ({len(_tickers)})</span>'
        f'<span style="font-size:0.85rem;font-weight:700;color:#00c896;">▲ {n_above} above VWAP</span>'
        f'<span style="font-size:0.85rem;font-weight:700;color:#ff4d6d;">▼ {n_below} below VWAP</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Ticker cards — 2 per row
    for i in range(0, len(_summary_items), 2):
        row = _summary_items[i: i + 2]
        cols = st.columns(len(row))
        for col, item in zip(cols, row):
            with col:
                if item.get("price") is None:
                    st.markdown(
                        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                        f'border-radius:12px;padding:14px 16px;margin-bottom:10px;">'
                        f'<div style="font-size:0.9rem;color:#475569;">{item["ticker"]} — no data</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    continue

                c    = "#00c896" if item["pos"] == "ABOVE" else "#ff4d6d"
                pct  = item["pct"]
                sdist = item["pct"] / (item["sigma"] / item["vwap"] * 100) if item["sigma"] > 0 else 0

                # Determine signal label
                if pct >= 0 and abs(sdist) <= 0.3:
                    sig_label, sig_col = "VWAP support hold", "#00c896"
                elif pct < 0 and abs(sdist) <= 0.3:
                    sig_label, sig_col = "VWAP rejection test", "#f0b429"
                elif sdist >= 2:
                    sig_label, sig_col = "Extended (>2σ above)", "#f0b429"
                elif sdist <= -2:
                    sig_label, sig_col = "Oversold (>2σ below)", "#00c896"
                elif sdist >= 1:
                    sig_label, sig_col = "Strong above VWAP", "#00c896"
                elif sdist <= -1:
                    sig_label, sig_col = "Below VWAP (bearish)", "#ff4d6d"
                else:
                    sig_label, sig_col = item["pos"] + " VWAP", c

                st.markdown(
                    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                    f'border:1px solid rgba(255,255,255,0.07);border-left:4px solid {c};'
                    f'border-radius:12px;padding:14px 16px;margin-bottom:10px;">'

                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                    f'<span style="font-size:1rem;font-weight:800;color:#e2e8f0;">{item["label"]}</span>'
                    f'<span style="font-size:0.78rem;font-weight:700;color:{sig_col};">{sig_label}</span>'
                    f'</div>'

                    f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:10px;">'

                    f'<div><div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.07em;">Price</div>'
                    f'<div style="font-size:0.95rem;font-weight:700;color:#f1f5f9;">₹{item["price"]:,.2f}</div></div>'

                    f'<div><div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.07em;">VWAP</div>'
                    f'<div style="font-size:0.95rem;font-weight:700;color:#3b82f6;">₹{item["vwap"]:,.2f}</div></div>'

                    f'<div><div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.07em;">vs VWAP</div>'
                    f'<div style="font-size:0.95rem;font-weight:700;color:{c};">{pct:+.2f}%</div></div>'

                    f'</div>'

                    f'<div style="font-size:0.67rem;color:#475569;">'
                    f'σ bands: ₹{item["s1dn"]:,.1f} / <b style="color:#3b82f6;">VWAP</b> / ₹{item["s1up"]:,.1f}  '
                    f'· 2σ: ₹{item["s2dn"]:,.1f} — ₹{item["s2up"]:,.1f}</div>'

                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Individual VWAP chart in expander
                with st.expander(f"📈 {item['label']} intraday chart", expanded=False):
                    df_t = _ticker_data.get(item["ticker"])
                    if df_t is not None and not df_t.empty:
                        times = df_t.index.strftime("%H:%M").tolist()
                        fig_v = go.Figure()

                        # Price candles (OHLC line)
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["Close"].tolist(),
                            mode="lines", name="Price",
                            line=dict(color="#e2e8f0", width=1.5),
                            hovertemplate="%{x}<br>₹%{y:,.2f}<extra>Price</extra>",
                        ))
                        # VWAP
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["VWAP"].tolist(),
                            mode="lines", name="VWAP",
                            line=dict(color="#3b82f6", width=2, dash="solid"),
                            hovertemplate="%{x}<br>₹%{y:,.2f}<extra>VWAP</extra>",
                        ))
                        # ±1σ bands
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["VWAP+1"].tolist(),
                            mode="lines", name="+1σ",
                            line=dict(color="rgba(0,200,150,0.6)", width=1, dash="dot"),
                            hovertemplate="+1σ: ₹%{y:,.2f}<extra></extra>",
                        ))
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["VWAP-1"].tolist(),
                            mode="lines", name="-1σ",
                            line=dict(color="rgba(255,77,109,0.6)", width=1, dash="dot"),
                            fill="tonexty", fillcolor="rgba(59,130,246,0.04)",
                            hovertemplate="-1σ: ₹%{y:,.2f}<extra></extra>",
                        ))
                        # ±2σ bands
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["VWAP+2"].tolist(),
                            mode="lines", name="+2σ",
                            line=dict(color="rgba(0,200,150,0.3)", width=1, dash="dash"),
                            hovertemplate="+2σ: ₹%{y:,.2f}<extra></extra>",
                        ))
                        fig_v.add_trace(go.Scatter(
                            x=times, y=df_t["VWAP-2"].tolist(),
                            mode="lines", name="-2σ",
                            line=dict(color="rgba(255,77,109,0.3)", width=1, dash="dash"),
                            hovertemplate="-2σ: ₹%{y:,.2f}<extra></extra>",
                        ))

                        fig_v.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
                            margin=dict(l=0, r=0, t=10, b=0), height=260,
                            legend=dict(orientation="h", yanchor="top", y=-0.18,
                                        bgcolor="rgba(0,0,0,0)", font=dict(size=9)),
                            xaxis=dict(gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
                            yaxis=dict(gridcolor="rgba(255,255,255,0.06)",
                                       tickprefix="₹", tickfont=dict(size=9)),
                            hovermode="x unified",
                        )
                        st.plotly_chart(fig_v, use_container_width=True)


_render_vwap()

st.caption(
    "VWAP = Volume Weighted Average Price (cumulative from session open). "
    "σ bands = 1× and 2× standard deviation of TP. "
    "Intraday data: 5-min candles via yfinance."
)
