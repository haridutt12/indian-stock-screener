"""
Page 21: Market Breadth Analytics
Advance/Decline ratio, McClellan Oscillator, McClellan Summation Index,
new 52W highs/lows, % above SMA, and Hindenburg Omen conditions.
Professional market breadth tools used by institutional traders.
"""
import logging
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

from config.stock_universe import NIFTY_50, NIFTY_200

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Breadth Analytics · NiftyEdge", layout="wide", page_icon="📡")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Breadth Analytics", "Advance/Decline · McClellan Oscillator · 52W Highs/Lows · Breadth thrust")
user_sidebar()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"], key="br_uni")
    _run             = st.button("📡 Compute Breadth", type="primary", use_container_width=True)

if not _run:
    st.info("Click **Compute Breadth** to analyse market internals.")
    st.stop()

_universe = NIFTY_50 if _universe_choice == "Nifty 50" else NIFTY_200
_tickers  = list(_universe.values())


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_breadth_data(tickers: tuple) -> dict:
    """
    Fetch 1Y daily data and compute breadth indicators.
    Returns dict with:
      - daily_ad: pd.Series of daily A-D values
      - daily_advances/declines: pd.Series
      - cum_ad: cumulative A-D line
      - pct_above_sma20/50/200: list of (date, pct) tuples
      - highs_52w / lows_52w: int counts today
      - stocks: list of per-stock dicts
    """
    try:
        raw = yf.download(
            list(tickers), period="1y", interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
    except Exception as exc:
        logger.error("breadth fetch failed: %s", exc)
        return {}

    if raw is None or raw.empty:
        return {}

    top_lvl = (
        raw.columns.get_level_values(0).unique().tolist()
        if isinstance(raw.columns, pd.MultiIndex) else []
    )

    closes_dict = {}
    for t in tickers:
        if t in top_lvl:
            c = raw[t]["Close"].dropna()
            if len(c) >= 30:
                closes_dict[t] = c

    if not closes_dict:
        return {}

    # Align all to common dates
    df = pd.DataFrame(closes_dict)
    df = df.dropna(how="all")
    returns = df.pct_change()

    # ── Daily A-D ────────────────────────────────────────────────────────────
    advances = (returns > 0).sum(axis=1)
    declines = (returns < 0).sum(axis=1)
    daily_ad = advances - declines
    cum_ad   = daily_ad.cumsum()

    # ── % above SMA20/50/200 ─────────────────────────────────────────────────
    def _pct_above_sma(window: int) -> pd.Series:
        above = pd.DataFrame({
            t: (df[t] > df[t].rolling(window).mean())
            for t in df.columns if len(df[t].dropna()) >= window
        })
        return above.mean(axis=1) * 100

    pct20  = _pct_above_sma(20)
    pct50  = _pct_above_sma(50)
    pct200 = _pct_above_sma(200)

    # ── 52W highs / lows (rolling 252 sessions) ───────────────────────────────
    highs_52w = lows_52w = 0
    stocks_today = []
    for t in df.columns:
        s = df[t].dropna()
        if len(s) < 30:
            continue
        curr = float(s.iloc[-1])
        h52  = float(s.rolling(252).max().iloc[-1]) if len(s) >= 252 else float(s.max())
        l52  = float(s.rolling(252).min().iloc[-1]) if len(s) >= 252 else float(s.min())
        pos  = (curr - l52) / (h52 - l52) * 100 if h52 != l52 else 50.0

        if pos >= 95: highs_52w += 1
        if pos <= 5:  lows_52w  += 1

        sma20  = float(s.rolling(20).mean().iloc[-1]) if len(s) >= 20 else None
        sma50  = float(s.rolling(50).mean().iloc[-1]) if len(s) >= 50 else None

        stocks_today.append({
            "sym":   t.replace(".NS", ""),
            "price": round(curr, 2),
            "pos52": round(pos, 1),
            "above_sma20": sma20 is not None and curr > sma20,
            "above_sma50": sma50 is not None and curr > sma50,
        })

    # ── McClellan Oscillator (19-day EMA − 39-day EMA of A-D) ────────────────
    ema19 = daily_ad.ewm(span=19, adjust=False).mean()
    ema39 = daily_ad.ewm(span=39, adjust=False).mean()
    mcl_osc = ema19 - ema39
    mcl_sum = mcl_osc.cumsum()

    total_stocks = len(df.columns)
    return {
        "daily_ad":    daily_ad,
        "advances":    advances,
        "declines":    declines,
        "cum_ad":      cum_ad,
        "pct20":       pct20,
        "pct50":       pct50,
        "pct200":      pct200,
        "mcl_osc":     mcl_osc,
        "mcl_sum":     mcl_sum,
        "highs_52w":   highs_52w,
        "lows_52w":    lows_52w,
        "total":       total_stocks,
        "stocks":      stocks_today,
        "dates":       df.index,
    }


with st.spinner(f"Computing breadth for {len(_tickers)} stocks…"):
    _bd = _fetch_breadth_data(tuple(_tickers))

if not _bd:
    st.error("Could not fetch data for breadth computation.")
    st.stop()

_total  = _bd["total"]
_dates  = _bd["dates"]
_pct20  = _bd["pct20"]
_pct50  = _bd["pct50"]
_pct200 = _bd["pct200"]

# Today's values
_adv_today  = int(_bd["advances"].iloc[-1])
_dec_today  = int(_bd["declines"].iloc[-1])
_flat_today = _total - _adv_today - _dec_today
_adr_today  = round(_adv_today / max(_dec_today, 1), 2)

_mcl_today  = float(_bd["mcl_osc"].iloc[-1])
_mclsum_today = float(_bd["mcl_sum"].iloc[-1])
_pct20_today  = float(_pct20.iloc[-1]) if not _pct20.empty else 0
_pct50_today  = float(_pct50.iloc[-1]) if not _pct50.empty else 0
_pct200_today = float(_pct200.iloc[-1]) if not _pct200.empty else 0

_highs = _bd["highs_52w"]
_lows  = _bd["lows_52w"]

# ── Hindenburg Omen check ─────────────────────────────────────────────────────
_ho_highs_pct = _highs / _total * 100
_ho_lows_pct  = _lows  / _total * 100
_hindenburg = (
    _ho_highs_pct >= 2.2 and _ho_lows_pct >= 2.2
    and _mcl_today < 0
    and _bd["cum_ad"].iloc[-1] > _bd["cum_ad"].iloc[-63] if len(_bd["cum_ad"]) >= 63 else False
)

# ── Summary strip ─────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Today\'s Market Breadth</div>',
    unsafe_allow_html=True,
)

_mc = st.columns(5)
for _col, (_lbl, _val, _cc) in zip(_mc, [
    ("Advances",        str(_adv_today),                                            "#00c896"),
    ("Declines",        str(_dec_today),                                            "#ff4d6d"),
    ("A/D Ratio",       f"{_adr_today:.2f}×",
     "#00c896" if _adr_today > 1.5 else "#f0b429" if _adr_today > 0.8 else "#ff4d6d"),
    ("52W Highs / Lows", f"{_highs} / {_lows}",
     "#00c896" if _highs > _lows * 2 else "#f0b429" if _highs >= _lows else "#ff4d6d"),
    ("McClellan Osc",   f"{_mcl_today:+.1f}",
     "#00c896" if _mcl_today > 50 else "#f0b429" if _mcl_today > -50 else "#ff4d6d"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1.1rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:10px;"></div>', unsafe_allow_html=True)

# SMA breadth row
_sma_mc = st.columns(4)
for _col, (_lbl, _val, _cc) in zip(_sma_mc, [
    ("% Above SMA20",  f"{_pct20_today:.0f}%",
     "#00c896" if _pct20_today >= 60 else "#f0b429" if _pct20_today >= 40 else "#ff4d6d"),
    ("% Above SMA50",  f"{_pct50_today:.0f}%",
     "#00c896" if _pct50_today >= 60 else "#f0b429" if _pct50_today >= 40 else "#ff4d6d"),
    ("% Above SMA200", f"{_pct200_today:.0f}%",
     "#00c896" if _pct200_today >= 60 else "#f0b429" if _pct200_today >= 40 else "#ff4d6d"),
    ("Hindenburg Omen", "⚠ SIGNAL" if _hindenburg else "✅ Clear",
     "#ff1744" if _hindenburg else "#00c896"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1.1rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

if _hindenburg:
    st.error(
        "**⚠ Hindenburg Omen conditions met**: "
        f"≥2.2% of stocks at 52W highs ({_ho_highs_pct:.1f}%) AND 52W lows ({_ho_lows_pct:.1f}%), "
        "McClellan Oscillator negative. This is a potential market stress signal — "
        "historically precedes elevated volatility within 30 days."
    )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── Charts ─────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">'
    'Cumulative A-D Line & McClellan Oscillator</div>',
    unsafe_allow_html=True,
)

_fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
    row_heights=[0.45, 0.3, 0.25],
    subplot_titles=["Cumulative A-D Line", "McClellan Oscillator", "McClellan Summation Index"],
)

# ── Row 1: Cumulative A-D Line ────────────────────────────────────────────────
_x = list(range(len(_bd["cum_ad"])))
_cum_vals = _bd["cum_ad"].tolist()
_fig.add_trace(go.Scatter(
    x=_x, y=_cum_vals, mode="lines",
    line=dict(color="#3b82f6", width=2),
    fill="tozeroy", fillcolor="rgba(59,130,246,0.06)",
    name="Cumulative A-D",
    hovertemplate="Bar %{x}<br>Cum A-D: %{y:.0f}<extra></extra>",
), row=1, col=1)

# ── Row 2: McClellan Oscillator ───────────────────────────────────────────────
_mcl_vals = _bd["mcl_osc"].tolist()
_mcl_colors = ["#00c896" if v >= 0 else "#ff4d6d" for v in _mcl_vals]
_fig.add_trace(go.Bar(
    x=_x, y=_mcl_vals, marker_color=_mcl_colors, opacity=0.8,
    name="McClellan Osc",
    hovertemplate="Bar %{x}<br>Oscillator: %{y:.1f}<extra></extra>",
), row=2, col=1)
_fig.add_hline(y=0,   line_color="rgba(255,255,255,0.15)", line_width=1, row=2, col=1)
_fig.add_hline(y=100, line_color="#00c89633", line_width=1, line_dash="dot", row=2, col=1)
_fig.add_hline(y=-100, line_color="#ff4d6d33", line_width=1, line_dash="dot", row=2, col=1)

# ── Row 3: McClellan Summation ────────────────────────────────────────────────
_mclsum_vals = _bd["mcl_sum"].tolist()
_fig.add_trace(go.Scatter(
    x=_x, y=_mclsum_vals, mode="lines",
    line=dict(color="#f0b429", width=1.5),
    fill="tozeroy", fillcolor="rgba(240,180,41,0.05)",
    name="Summation",
    hovertemplate="Bar %{x}<br>Summation: %{y:.0f}<extra></extra>",
), row=3, col=1)
_fig.add_hline(y=0, line_color="rgba(255,255,255,0.15)", line_width=1, row=3, col=1)

_fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=30, b=0), height=520,
    showlegend=False,
    xaxis3=dict(title="Trading days (past 1Y)", tickfont=dict(size=9)),
)
for ann in _fig.layout.annotations:
    ann.font.color = "#94a3b8"
    ann.font.size  = 10
for axis_key in ["yaxis", "yaxis2", "yaxis3", "xaxis", "xaxis2", "xaxis3"]:
    axis = getattr(_fig.layout, axis_key, None)
    if axis:
        axis.gridcolor = "rgba(255,255,255,0.04)"
        axis.zeroline  = False
        axis.tickfont  = dict(size=9)
st.plotly_chart(_fig, use_container_width=True)

# ── % Above SMA chart ─────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    '% of Stocks Above Key SMAs</div>',
    unsafe_allow_html=True,
)

_fig_sma = go.Figure()
for _s, _c, _lbl in [(_pct20, "#00c896", "Above SMA20"), (_pct50, "#3b82f6", "Above SMA50"), (_pct200, "#f0b429", "Above SMA200")]:
    _x2 = list(range(len(_s)))
    _fig_sma.add_trace(go.Scatter(
        x=_x2, y=_s.tolist(), mode="lines", name=_lbl,
        line=dict(color=_c, width=1.5),
        hovertemplate=f"{_lbl}<br>Bar %{{x}}<br>%{{y:.1f}}%<extra></extra>",
    ))

_fig_sma.add_hline(y=80, line_color="#00c89633", line_width=1, line_dash="dot",
                   annotation_text="Overbought (80%)", annotation_font_color="#00c896", annotation_font_size=9)
_fig_sma.add_hline(y=20, line_color="#ff4d6d33", line_width=1, line_dash="dot",
                   annotation_text="Oversold (20%)", annotation_font_color="#ff4d6d", annotation_font_size=9)
_fig_sma.add_hline(y=50, line_color="rgba(255,255,255,0.1)", line_width=1)
_fig_sma.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=40),
    height=260,
    xaxis=dict(title="Trading days", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="%", range=[0, 100], gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9), ticksuffix="%"),
    legend=dict(orientation="h", y=-0.25, x=0, font=dict(size=10)),
)
st.plotly_chart(_fig_sma, use_container_width=True)

# ── 52W range distribution ─────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    '52W Range Position Distribution</div>',
    unsafe_allow_html=True,
)

_pos_vals = [s["pos52"] for s in _bd["stocks"]]
_fig_range = go.Figure()
_fig_range.add_trace(go.Histogram(
    x=_pos_vals, nbinsx=20,
    marker_color=[
        "#00c896" if p >= 70 else "#f0b429" if p >= 40 else "#ff4d6d"
        for p in _pos_vals
    ],
    opacity=0.8,
    hovertemplate="52W position: %{x:.0f}%<br>Stocks: %{y}<extra></extra>",
))
_fig_range.add_vline(x=50, line_color="rgba(255,255,255,0.2)", line_width=1)
_fig_range.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0), height=220,
    xaxis=dict(title="52W range position (%)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="# Stocks", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    showlegend=False,
)
st.plotly_chart(_fig_range, use_container_width=True)

# ── Breadth thrust check ──────────────────────────────────────────────────────
with st.expander("🚀 Breadth Thrust Detector (Zweig)"):
    _thresh_advances = 0.615
    _thresh_window = 10
    if len(_bd["advances"]) >= _thresh_window:
        _advances_s = _bd["advances"]
        _total_s    = _advances_s + _bd["declines"]
        _adv_ratio  = (_advances_s / _total_s.replace(0, 1)).rolling(_thresh_window).mean()
        _thrust_now = float(_adv_ratio.iloc[-1])
        _thrust_hit = any(v >= _thresh_advances for v in _adv_ratio.tail(20).dropna().tolist())
        _tc = "#00c896" if _thrust_now >= 0.55 else "#f0b429" if _thrust_now >= 0.4 else "#ff4d6d"
        st.markdown(
            f'**Zweig Breadth Thrust** — {_thresh_window}-day rolling % of advancing stocks\n\n'
            f'Current: **{_thrust_now*100:.1f}%** | Threshold: 61.5%\n\n'
            f'{"✅ Thrust condition met in the last 20 days — strong bull signal" if _thrust_hit else "No recent thrust."}'
        )
    else:
        st.info("Not enough data for breadth thrust calculation.")

with st.expander("📖 Breadth Analytics Guide"):
    st.markdown("""
**Advance/Decline (A-D) Line**: Running sum of daily (advances − declines).
Rising A-D with rising index = healthy trend. Diverging (index up, A-D down) = breadth deteriorating.

**McClellan Oscillator**: 19-day EMA minus 39-day EMA of A-D. Like MACD for breadth.
- >+100: overbought (potential short-term pullback, but confirms bull)
- <−100: oversold (potential rally)
- Zero crossing: trend change signal

**McClellan Summation Index**: Cumulative sum of Oscillator.
- Positive + rising: bull market internal
- Negative + falling: bear market internal

**% Above SMA**: Measures broad participation.
- >80% above SMA20: overbought breadth
- <20% above SMA200: deeply oversold market, often at major lows

**52W Highs vs Lows**: Healthy market sees far more highs than lows.

**Hindenburg Omen**: Potential crash warning when:
- ≥2.2% of stocks at 52W highs AND ≥2.2% at 52W lows simultaneously
- McClellan Oscillator is negative
- Cumulative A-D is trending up (not at historical lows)
Signals internal divergence — market is bifurcating between leaders and laggards.

**Zweig Breadth Thrust**: 10-day MA of advances/(advances+declines) crosses 61.5%.
Very rare, very bullish — historically signals the start of major bull markets.
""")

st.caption(
    f"Universe: {_universe_choice} ({_total} stocks) · "
    f"1Y daily history · A-D computed from all stocks with ≥30 days of data"
)
