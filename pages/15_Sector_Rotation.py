"""
Page 15: Sector Rotation
Relative strength of Indian sector indices vs Nifty 50 benchmark.
Implements a JdK RS-Ratio / RS-Momentum style Relative Rotation Graph (RRG).
"""
import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Sector Rotation · NiftyEdge", layout="wide", page_icon="🔄")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Sector Rotation", "Relative Rotation Graph · Leading vs Lagging sectors · Momentum quadrants")
user_sidebar()

# ── Sector index tickers (NSE sector indices via yfinance) ────────────────────
SECTORS = {
    "IT":           "^CNXIT",
    "Bank":         "^NSEBANK",
    "FMCG":         "^CNXFMCG",
    "Pharma":       "^CNXPHARMA",
    "Auto":         "^CNXAUTO",
    "Metal":        "^CNXMETAL",
    "Realty":       "^CNXREALTY",
    "Energy":       "^CNXENERGY",
    "Infra":        "^CNXINFRA",
    "PSU Bank":     "^CNXPSUBANK",
    "Media":        "^CNXMEDIA",
    "Fin Services": "^CNXFINANCE",
}

BENCHMARK = "^NSEI"  # Nifty 50

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _period   = st.selectbox("Lookback", ["6mo", "1y", "3mo"], index=1, key="sr_period")
    _trail    = st.slider("Trail length (weeks)", 4, 16, 8, key="sr_trail")
    _run      = st.button("🔄 Compute Sector Rotation", type="primary", use_container_width=True)

if not _run:
    st.info("Click **Compute Sector Rotation** in the sidebar to generate the RRG chart.")
    st.stop()


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_sector_data(period: str) -> pd.DataFrame:
    """
    Fetch weekly closing prices for all sector indices + benchmark.
    Returns a DataFrame of weekly close prices (one column per ticker).
    """
    all_tickers = [BENCHMARK] + list(SECTORS.values())
    try:
        raw = yf.download(
            all_tickers, period=period, interval="1wk",
            auto_adjust=True, progress=False, timeout=30,
        )
        if raw is None or raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]] if "Close" in raw.columns else raw
        close = close.dropna(how="all")
        return close
    except Exception as exc:
        logger.error("sector fetch failed: %s", exc)
        return pd.DataFrame()


def _compute_rrg(close: pd.DataFrame, trail_weeks: int) -> pd.DataFrame:
    """
    Compute JdK RS-Ratio and RS-Momentum for each sector.
    - RS-Ratio:    smoothed ratio of sector return vs benchmark return (normalised to 100)
    - RS-Momentum: rate-of-change of RS-Ratio (normalised to 100)

    Returns a DataFrame with columns:
        sector, rs_ratio, rs_momentum, rs_ratio_trail, rs_momentum_trail
    where *_trail columns contain lists of historical values for the tail.
    """
    if close.empty or BENCHMARK not in close.columns:
        return pd.DataFrame()

    bench = close[BENCHMARK].dropna()
    results = []

    for name, ticker in SECTORS.items():
        if ticker not in close.columns:
            continue
        sector_close = close[ticker].dropna()
        # Align on common dates
        common = bench.index.intersection(sector_close.index)
        if len(common) < trail_weeks + 5:
            continue
        b = bench.loc[common]
        s = sector_close.loc[common]

        # Relative strength (price ratio)
        rs = s / b * 100  # rebased to 100 at inception

        # Normalise: JdK uses 10-period EWM smoothing, then z-score normalization
        rs_ema = rs.ewm(span=10, adjust=False).mean()

        # RS-Ratio: 100 + z-score of current vs 40-period mean
        window = min(40, len(rs_ema) - 1)
        rs_mean = rs_ema.rolling(window).mean()
        rs_std  = rs_ema.rolling(window).std().replace(0, np.nan)
        rs_ratio_raw = 100 + (rs_ema - rs_mean) / rs_std * 10  # scale to ±10 around 100

        # RS-Momentum: 1-period ROC of RS-Ratio, normalised similarly
        rs_mom_raw = rs_ratio_raw.pct_change(1) * 100  # percent change per week
        mom_mean = rs_mom_raw.rolling(window).mean()
        mom_std  = rs_mom_raw.rolling(window).std().replace(0, np.nan)
        rs_mom_norm = 100 + (rs_mom_raw - mom_mean) / mom_std * 10

        # Current and trail history
        rs_ratio_hist   = rs_ratio_raw.dropna()
        rs_mom_hist     = rs_mom_norm.dropna()

        if len(rs_ratio_hist) < 1 or len(rs_mom_hist) < 1:
            continue

        n = min(trail_weeks, len(rs_ratio_hist), len(rs_mom_hist))

        results.append({
            "Sector":         name,
            "rs_ratio":       float(rs_ratio_hist.iloc[-1]),
            "rs_momentum":    float(rs_mom_hist.iloc[-1]),
            "rs_ratio_trail": rs_ratio_hist.iloc[-n:].tolist(),
            "rs_mom_trail":   rs_mom_hist.iloc[-n:].tolist(),
            "current_rs":     float(rs.iloc[-1]),
            "rs_1w":          float(rs.iloc[-1] / rs.iloc[-2] - 1) * 100 if len(rs) >= 2 else None,
            "rs_4w":          float(rs.iloc[-1] / rs.iloc[-5] - 1) * 100 if len(rs) >= 5 else None,
            "rs_13w":         float(rs.iloc[-1] / rs.iloc[-14] - 1) * 100 if len(rs) >= 14 else None,
        })

    return pd.DataFrame(results) if results else pd.DataFrame()


def _quadrant(rs_ratio: float, rs_momentum: float) -> tuple[str, str]:
    """Map RS-Ratio/Momentum to a quadrant name and color."""
    if rs_ratio >= 100 and rs_momentum >= 100:
        return "Leading", "#00c896"
    if rs_ratio >= 100 and rs_momentum < 100:
        return "Weakening", "#f0b429"
    if rs_ratio < 100 and rs_momentum >= 100:
        return "Improving", "#60a5fa"
    return "Lagging", "#ff4d6d"


with st.spinner("Fetching sector data…"):
    _close = _fetch_sector_data(_period)

if _close.empty:
    st.error("Could not fetch sector data. Try again.")
    st.stop()

_rrg_df = _compute_rrg(_close, _trail)

if _rrg_df.empty:
    st.error("Insufficient data to compute RRG.")
    st.stop()

_rrg_df["Quadrant"], _rrg_df["Color"] = zip(*_rrg_df.apply(
    lambda r: _quadrant(r["rs_ratio"], r["rs_momentum"]), axis=1
))

# ── Summary strip ─────────────────────────────────────────────────────────────
_quad_counts = _rrg_df["Quadrant"].value_counts()
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Quadrant Summary</div>',
    unsafe_allow_html=True,
)
_sc = st.columns(4)
for _col, (_q, _c) in zip(_sc, [
    ("Leading",   "#00c896"),
    ("Weakening", "#f0b429"),
    ("Improving", "#60a5fa"),
    ("Lagging",   "#ff4d6d"),
]):
    with _col:
        _n = int(_quad_counts.get(_q, 0))
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_q}</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{_c};">{_n} sectors</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── RRG Chart ─────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    'Relative Rotation Graph (RRG)</div>',
    unsafe_allow_html=True,
)

_fig = go.Figure()

# Quadrant background shading
_fig.add_shape(type="rect", x0=100, x1=115, y0=100, y1=115,
    fillcolor="rgba(0,200,150,0.06)", line_width=0, layer="below")
_fig.add_shape(type="rect", x0=100, x1=115, y0=85, y1=100,
    fillcolor="rgba(240,180,41,0.06)", line_width=0, layer="below")
_fig.add_shape(type="rect", x0=85, x1=100, y0=100, y1=115,
    fillcolor="rgba(96,165,250,0.06)", line_width=0, layer="below")
_fig.add_shape(type="rect", x0=85, x1=100, y0=85, y1=100,
    fillcolor="rgba(255,77,109,0.06)", line_width=0, layer="below")

# Quadrant labels
for _lbl, _lx, _ly, _lc in [
    ("LEADING",   112, 113, "#00c896"),
    ("WEAKENING", 112, 87,  "#f0b429"),
    ("IMPROVING", 88,  113, "#60a5fa"),
    ("LAGGING",   88,  87,  "#ff4d6d"),
]:
    _fig.add_annotation(
        x=_lx, y=_ly, text=_lbl,
        font=dict(size=9, color=_lc, family="Inter, sans-serif"),
        showarrow=False, opacity=0.6,
    )

# Trail lines
for _, row in _rrg_df.iterrows():
    xtrail = row["rs_ratio_trail"]
    ytrail = row["rs_mom_trail"]
    if len(xtrail) > 1:
        _fig.add_trace(go.Scatter(
            x=xtrail, y=ytrail,
            mode="lines",
            line=dict(color=row["Color"], width=1.5, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
            opacity=0.5,
        ))

# Current position dots + labels
_fig.add_trace(go.Scatter(
    x=_rrg_df["rs_ratio"].tolist(),
    y=_rrg_df["rs_momentum"].tolist(),
    mode="markers+text",
    marker=dict(
        size=14,
        color=_rrg_df["Color"].tolist(),
        line=dict(width=1.5, color="rgba(255,255,255,0.3)"),
        symbol="circle",
    ),
    text=_rrg_df["Sector"].tolist(),
    textposition="top center",
    textfont=dict(size=10, color="#e2e8f0", family="Inter, sans-serif"),
    hovertemplate=(
        "<b>%{text}</b><br>"
        "RS-Ratio: %{x:.1f}<br>"
        "RS-Momentum: %{y:.1f}<extra></extra>"
    ),
    showlegend=False,
))

# Center crosshair
_fig.add_hline(y=100, line_color="rgba(255,255,255,0.15)", line_width=1)
_fig.add_vline(x=100, line_color="rgba(255,255,255,0.15)", line_width=1)

_all_x = _rrg_df["rs_ratio"].tolist()
_all_y = _rrg_df["rs_momentum"].tolist()
_pad = 8
_xmin = min(min(_all_x) - _pad, 84)
_xmax = max(max(_all_x) + _pad, 116)
_ymin = min(min(_all_y) - _pad, 84)
_ymax = max(max(_all_y) + _pad, 116)

_fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=20, r=20, t=30, b=30),
    height=560,
    xaxis=dict(
        title="RS-Ratio (Relative Strength vs Nifty)",
        range=[_xmin, _xmax],
        gridcolor="rgba(255,255,255,0.04)",
        tickfont=dict(size=9),
        zeroline=False,
    ),
    yaxis=dict(
        title="RS-Momentum (Rate of Change of RS-Ratio)",
        range=[_ymin, _ymax],
        gridcolor="rgba(255,255,255,0.04)",
        tickfont=dict(size=9),
        zeroline=False,
    ),
)
st.plotly_chart(_fig, use_container_width=True)

st.caption(
    "RRG quadrants: **Leading** (strong RS, gaining momentum) · "
    "**Weakening** (strong RS, losing momentum) · "
    "**Improving** (weak RS, gaining momentum) · "
    "**Lagging** (weak RS, losing momentum). "
    "Dotted trails show the past N weeks of rotation."
)

# ── Sector RS Table ───────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 8px;">Sector RS Rankings</div>',
    unsafe_allow_html=True,
)

_tbl = _rrg_df[["Sector", "Quadrant", "rs_ratio", "rs_momentum", "rs_1w", "rs_4w", "rs_13w"]].copy()
_tbl.columns = ["Sector", "Quadrant", "RS-Ratio", "RS-Momentum", "RS 1W %", "RS 4W %", "RS 13W %"]
_tbl = _tbl.sort_values("RS-Ratio", ascending=False).reset_index(drop=True)


def _q_color(val):
    m = {"Leading": "#00c896", "Weakening": "#f0b429", "Improving": "#60a5fa", "Lagging": "#ff4d6d"}
    c = m.get(val, "#94a3b8")
    return f"color: {c}; font-weight: 700;"


def _rs_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#00c896' if val >= 0 else '#ff4d6d'};"


def _ratio_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#00c896' if val >= 100 else '#ff4d6d'}; font-weight: 600;"


styled = (
    _tbl.style
    .map(_q_color, subset=["Quadrant"])
    .map(_ratio_color, subset=["RS-Ratio", "RS-Momentum"])
    .map(_rs_color, subset=["RS 1W %", "RS 4W %", "RS 13W %"])
    .format({
        "RS-Ratio":    "{:.1f}",
        "RS-Momentum": "{:.1f}",
        "RS 1W %":     "{:+.2f}%",
        "RS 4W %":     "{:+.2f}%",
        "RS 13W %":    "{:+.2f}%",
    }, na_rep="—")
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Sector strength bar chart ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 8px;">RS-Ratio vs Benchmark</div>',
    unsafe_allow_html=True,
)

_bar_df = _tbl.sort_values("RS-Ratio")
_bar_colors = [
    "#00c896" if q == "Leading" else "#f0b429" if q == "Weakening"
    else "#60a5fa" if q == "Improving" else "#ff4d6d"
    for q in _bar_df["Quadrant"]
]
_fig_bar = go.Figure(go.Bar(
    x=(_bar_df["RS-Ratio"] - 100).tolist(),
    y=_bar_df["Sector"].tolist(),
    orientation="h",
    marker_color=_bar_colors,
    text=[f"{v-100:+.1f}" for v in _bar_df["RS-Ratio"]],
    textposition="outside",
    textfont=dict(size=9, color="#e2e8f0"),
    hovertemplate="%{y}<br>RS-Ratio: 100%{x:+.1f}<extra></extra>",
))
_fig_bar.add_vline(x=0, line_color="rgba(255,255,255,0.2)", line_width=1)
_fig_bar.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=60, t=10, b=0),
    height=max(280, len(_bar_df) * 28),
    xaxis=dict(title="RS-Ratio deviation from 100", gridcolor="rgba(255,255,255,0.04)",
               tickfont=dict(size=9)),
    yaxis=dict(tickfont=dict(size=10)),
    showlegend=False,
)
st.plotly_chart(_fig_bar, use_container_width=True)

# ── Rotation clock annotation ─────────────────────────────────────────────────
with st.expander("📖 How to read the RRG"):
    st.markdown("""
**Relative Rotation Graph (RRG)** plots sectors on two axes:
- **X-axis (RS-Ratio)**: How strong a sector is relative to Nifty 50. >100 = outperforming.
- **Y-axis (RS-Momentum)**: Whether the RS-Ratio is improving or deteriorating. >100 = accelerating.

**Rotation cycle** (clockwise):
1. **Improving** → Sector starts to outperform, momentum building
2. **Leading** → Strongest sectors: outperforming + momentum rising
3. **Weakening** → Still outperforming but momentum rolling over
4. **Lagging** → Underperforming + losing momentum (avoid or short)

**Dotted trails** show the past N weeks, revealing rotation speed and direction.

**Trading implication**: Buy sectors rotating from *Improving → Leading*. Exit sectors rotating *Leading → Weakening*. Avoid or fade *Lagging* sectors.
""")
