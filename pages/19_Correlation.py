"""
Page 19: Correlation Matrix
Stock and sector correlation analysis for portfolio risk management.
Rolling correlations, hierarchical clustering, concentration risk detection.
"""
import logging
import numpy as np
import pandas as pd
import plotly.figure_factory as ff
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config.stock_universe import NIFTY_50, NIFTY_200

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Correlation Matrix · NiftyEdge", layout="wide", page_icon="🔗")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Correlation Matrix", "Portfolio concentration risk · Sector clustering · Diversification analysis")
user_sidebar()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _universe_choice = st.selectbox("Universe", ["Nifty 50", "Custom"], key="corr_uni")
    _period          = st.selectbox("Period", ["3mo", "6mo", "1y"], index=1, key="corr_per")
    _method          = st.selectbox("Correlation method", ["Pearson", "Spearman"], key="corr_meth")
    _min_abs_corr    = st.slider("Highlight |correlation| ≥", 0.3, 0.95, 0.7, 0.05, key="corr_thresh")
    _run             = st.button("🔗 Compute Correlations", type="primary", use_container_width=True)

    if _universe_choice == "Custom":
        _custom_input = st.text_area(
            "Enter tickers (comma-separated, without .NS)",
            "RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,SBIN,BHARTIARTL,ITC,LT,AXISBANK",
            key="corr_custom",
        )
    else:
        _custom_input = None

if not _run:
    st.info("Select universe and click **Compute Correlations** to build the matrix.")
    st.stop()

if _universe_choice == "Custom" and _custom_input:
    _tickers = [f"{t.strip()}.NS" for t in _custom_input.split(",") if t.strip()]
    _sym_map  = {t: t.replace(".NS", "") for t in _tickers}
else:
    _sym_map  = {v: k for k, v in NIFTY_50.items()}
    _tickers  = list(_sym_map.keys())


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_returns(tickers: tuple, period: str) -> pd.DataFrame:
    """Fetch daily closes and compute daily returns. Returns DataFrame of returns."""
    try:
        raw = yf.download(
            list(tickers), period=period, interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
    except Exception as exc:
        logger.error("corr fetch failed: %s", exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    top_lvl = (
        raw.columns.get_level_values(0).unique().tolist()
        if isinstance(raw.columns, pd.MultiIndex) else []
    )

    closes = {}
    for t in tickers:
        if t in top_lvl:
            c = raw[t]["Close"].dropna()
            if len(c) >= 20:
                closes[t.replace(".NS", "")] = c

    if not closes:
        return pd.DataFrame()

    df = pd.DataFrame(closes)
    return df.pct_change().dropna()


with st.spinner(f"Fetching {len(_tickers)} stocks ({_period})…"):
    _returns = _fetch_returns(tuple(_tickers), _period)

if _returns.empty or _returns.shape[1] < 3:
    st.error("Not enough data to build a correlation matrix (need 3+ stocks with valid history).")
    st.stop()

# ── Compute correlation matrix ─────────────────────────────────────────────────
if _method == "Spearman":
    _corr = _returns.corr(method="spearman")
else:
    _corr = _returns.corr(method="pearson")

_cols = _corr.columns.tolist()
_n    = len(_cols)

# ── Summary strip ─────────────────────────────────────────────────────────────
_upper = [(i, j, _corr.iloc[i, j]) for i in range(_n) for j in range(i + 1, _n)]
_avg_corr    = float(np.mean([abs(v) for _, _, v in _upper]))
_high_corr   = [(c, r, v) for c, r, v in [(
    _cols[i], _cols[j], round(_corr.iloc[i, j], 3)) for i, j, _ in _upper
    ] if abs(v) >= _min_abs_corr]
_n_high      = len(_high_corr)
_most_corr   = max(_upper, key=lambda x: x[2]) if _upper else None
_most_discorr = min(_upper, key=lambda x: x[2]) if _upper else None

st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Portfolio Concentration Snapshot</div>',
    unsafe_allow_html=True,
)
_mc = st.columns(4)
for _col, (_lbl, _val, _cc) in zip(_mc, [
    ("Avg Abs Correlation", f"{_avg_corr:.3f}",
     "#ff4d6d" if _avg_corr > 0.6 else "#f0b429" if _avg_corr > 0.4 else "#00c896"),
    (f"High-corr pairs (≥{_min_abs_corr})", str(_n_high),
     "#ff4d6d" if _n_high > _n else "#f0b429" if _n_high > 0 else "#00c896"),
    ("Most correlated",
     f"{_cols[_most_corr[0]]} / {_cols[_most_corr[1]]} ({_most_corr[2]:.2f})" if _most_corr else "—",
     "#ff4d6d"),
    ("Least correlated",
     f"{_cols[_most_discorr[0]]} / {_cols[_most_discorr[1]]} ({_most_discorr[2]:.2f})" if _most_discorr else "—",
     "#00c896"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:0.85rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

# ── Correlation heatmap ───────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">'
    f'{_method} Correlation Matrix ({_period})</div>',
    unsafe_allow_html=True,
)

_z    = _corr.values.tolist()
_text = [[f"{v:.2f}" for v in row] for row in _z]

_fig_heat = go.Figure(go.Heatmap(
    z=_z, x=_cols, y=_cols,
    colorscale=[
        [0.0,  "#7f1734"],
        [0.25, "#ff4d6d"],
        [0.5,  "#1a1f35"],
        [0.75, "#00c896"],
        [1.0,  "#00523d"],
    ],
    zmin=-1, zmax=1, zmid=0,
    text=_text, texttemplate="%{text}",
    textfont=dict(size=max(6, min(10, 200 // _n)), color="#e2e8f0"),
    hovertemplate="%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>",
    showscale=True,
    colorbar=dict(
        title="ρ", tickfont=dict(size=9, color="#6b7a99"),
        bgcolor="rgba(0,0,0,0)",
        tickvals=[-1, -0.5, 0, 0.5, 1],
    ),
))
_fig_heat.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0),
    height=max(400, _n * 28),
    xaxis=dict(tickfont=dict(size=max(7, min(10, 200 // _n))), side="top"),
    yaxis=dict(tickfont=dict(size=max(7, min(10, 200 // _n))), autorange="reversed"),
)
st.plotly_chart(_fig_heat, use_container_width=True)

# ── High-correlation pairs table ──────────────────────────────────────────────
if _high_corr:
    st.markdown(
        f'<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        f'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
        f'Highly Correlated Pairs (|ρ| ≥ {_min_abs_corr})</div>',
        unsafe_allow_html=True,
    )
    _pair_rows = sorted(_high_corr, key=lambda x: abs(x[2]), reverse=True)
    _pair_df   = pd.DataFrame([
        {"Stock A": a, "Stock B": b, "ρ": v,
         "Risk": "High" if abs(v) > 0.8 else "Medium"}
        for a, b, v in _pair_rows
    ])

    def _rho_color(val):
        if not isinstance(val, (int, float)) or pd.isna(val):
            return ""
        return f"color: {'#ff4d6d' if abs(val) > 0.8 else '#f0b429'}; font-weight: 700;"

    def _risk_color(val):
        return f"color: {'#ff4d6d' if val == 'High' else '#f0b429'}; font-weight: 600;"

    styled_pairs = (
        _pair_df.style
        .applymap(_rho_color,  subset=["ρ"])
        .applymap(_risk_color, subset=["Risk"])
        .format({"ρ": "{:+.3f}"})
    )
    st.dataframe(styled_pairs, use_container_width=True, hide_index=True)

    _concentration_msg = ""
    if _avg_corr > 0.6:
        _concentration_msg = (
            f"⚠ **High concentration risk**: Average absolute correlation {_avg_corr:.2f} "
            f"means your portfolio moves as one bloc. Consider diversifying across sectors "
            f"or adding negatively-correlated assets."
        )
    elif _avg_corr > 0.4:
        _concentration_msg = (
            f"⚡ **Moderate concentration**: Average correlation {_avg_corr:.2f}. "
            f"Some diversification but stocks tend to move together in market stress."
        )
    else:
        _concentration_msg = (
            f"✅ **Well-diversified**: Average correlation {_avg_corr:.2f}. "
            f"Stocks show meaningful independence — good for portfolio risk management."
        )

    st.info(_concentration_msg)

# ── Rolling correlation (top 5 pairs) ─────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 8px;">'
    'Rolling 30-Day Correlation — Top 5 Pairs by Abs Value</div>',
    unsafe_allow_html=True,
)

_top5_pairs = sorted(_upper, key=lambda x: abs(x[2]), reverse=True)[:5]

_fig_roll = go.Figure()
_PALETTE  = ["#00c896", "#3b82f6", "#f0b429", "#a78bfa", "#fb923c"]

for i, (ai, bi, _) in enumerate(_top5_pairs):
    col_a = _cols[ai]
    col_b = _cols[bi]
    if col_a in _returns.columns and col_b in _returns.columns:
        rolling_corr = _returns[col_a].rolling(30).corr(_returns[col_b]).dropna()
        if len(rolling_corr) >= 10:
            _fig_roll.add_trace(go.Scatter(
                x=list(range(len(rolling_corr))),
                y=rolling_corr.tolist(),
                mode="lines",
                name=f"{col_a}/{col_b}",
                line=dict(color=_PALETTE[i % len(_PALETTE)], width=1.5),
                hovertemplate=f"{col_a}/{col_b}<br>Day %{{x}}<br>ρ=%{{y:.3f}}<extra></extra>",
            ))

_fig_roll.add_hline(y=0,  line_color="rgba(255,255,255,0.15)", line_width=1)
_fig_roll.add_hline(y=0.7,  line_color="#ff4d6d33", line_width=1, line_dash="dot")
_fig_roll.add_hline(y=-0.7, line_color="#00c89633", line_width=1, line_dash="dot")
_fig_roll.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=40),
    height=280,
    xaxis=dict(title="Trading days", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="Rolling 30d ρ", range=[-1, 1], gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    legend=dict(orientation="h", y=-0.25, x=0, font=dict(size=9)),
)
st.plotly_chart(_fig_roll, use_container_width=True)

# ── Average correlation per stock (diversification score) ─────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'Diversification Score per Stock (lower = better diversifier)</div>',
    unsafe_allow_html=True,
)

_avg_corr_per = {}
for sym in _cols:
    row = _corr[sym].drop(sym)
    _avg_corr_per[sym] = float(row.abs().mean())

_div_df = pd.DataFrame([
    {"Stock": sym, "Avg |ρ| with others": round(v, 3),
     "Role": "Diversifier" if v < 0.4 else "Neutral" if v < 0.6 else "Concentrated"}
    for sym, v in sorted(_avg_corr_per.items(), key=lambda x: x[1])
])

_fig_div = go.Figure(go.Bar(
    x=_div_df["Avg |ρ| with others"].tolist(),
    y=_div_df["Stock"].tolist(),
    orientation="h",
    marker_color=[
        "#00c896" if v < 0.4 else "#f0b429" if v < 0.6 else "#ff4d6d"
        for v in _div_df["Avg |ρ| with others"]
    ],
    text=[f"{v:.2f}" for v in _div_df["Avg |ρ| with others"]],
    textposition="outside",
    textfont=dict(size=9, color="#e2e8f0"),
    hovertemplate="%{y}<br>Avg |ρ|: %{x:.3f}<extra></extra>",
))
_fig_div.add_vline(x=0.4, line_color="#00c89644", line_width=1, line_dash="dot",
                   annotation_text="Diversifier threshold", annotation_font_color="#00c896",
                   annotation_font_size=9)
_fig_div.add_vline(x=0.6, line_color="#ff4d6d44", line_width=1, line_dash="dot",
                   annotation_text="Concentrated threshold", annotation_font_color="#ff4d6d",
                   annotation_font_size=9)
_fig_div.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=60, t=10, b=0),
    height=max(280, _n * 22),
    xaxis=dict(title="Avg |ρ| with portfolio", range=[0, 1], gridcolor="rgba(255,255,255,0.04)",
               tickfont=dict(size=9)),
    yaxis=dict(tickfont=dict(size=9)),
    showlegend=False,
)
st.plotly_chart(_fig_div, use_container_width=True)

st.caption(
    f"Universe: {_universe_choice} ({len(_cols)} stocks) · "
    f"{_method} correlation on daily returns · Period: {_period} · "
    f"Rolling window: 30 trading days"
)
