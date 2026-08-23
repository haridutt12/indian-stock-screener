"""
Page 14: Momentum Screener
Multi-period return rankings for Nifty 50/200.
Shows which stocks have the strongest momentum across 1W, 1M, 3M, 6M, 1Y.
"""
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config.stock_universe import NIFTY_50, NIFTY_200

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Momentum Screener · NiftyEdge", layout="wide", page_icon="🏎️")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()

page_header("Momentum Screener", "Multi-period return rankings · Relative strength · Trend quality")
user_sidebar()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"], key="mom_uni")
    _min_price       = st.number_input("Min price (₹)", 0, 10000, 50, key="mom_minp")
    _sort_period     = st.selectbox("Rank by", ["1M", "3M", "6M", "1Y", "1W"], key="mom_sort")
    _direction       = st.radio("Filter", ["All", "Only positive", "Only negative"], horizontal=True, key="mom_dir")
    _top_n           = st.slider("Show top N", 10, 50, 20, key="mom_n")
    _run             = st.button("🏎️ Run Momentum Scan", type="primary", use_container_width=True)

if not _run:
    st.info("Configure filters in the sidebar and click **Run Momentum Scan** to start.")
    st.stop()

_universe = NIFTY_50 if _universe_choice == "Nifty 50" else NIFTY_200
_tickers  = list(_universe.values())


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_momentum(tickers: tuple, min_price: float) -> pd.DataFrame:
    """
    Batch-fetch 1Y daily close for all tickers and compute multi-period returns.
    Returns a DataFrame with one row per ticker.
    """
    try:
        raw = yf.download(
            list(tickers), period="1y", interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
    except Exception as exc:
        logger.error("momentum fetch failed: %s", exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    top_lvl = raw.columns.get_level_values(0).unique().tolist() if isinstance(raw.columns, pd.MultiIndex) else []
    rows = []
    for t in tickers:
        try:
            if t not in top_lvl:
                continue
            close = raw[t]["Close"].dropna()
            if len(close) < 5:
                continue
            curr = float(close.iloc[-1])
            if curr < min_price:
                continue

            def _ret(n_bars: int) -> float | None:
                if len(close) < n_bars + 1:
                    return None
                past = float(close.iloc[-n_bars - 1])
                return round((curr / past - 1) * 100, 2) if past > 0 else None

            # Approximate trading days: 1W≈5, 1M≈21, 3M≈63, 6M≈126, 1Y≈252
            r1w  = _ret(5)
            r1m  = _ret(21)
            r3m  = _ret(63)
            r6m  = _ret(126)
            r1y  = _ret(252)

            # 52W metrics
            h52 = float(close.max())
            l52 = float(close.min())
            pos = round((curr - l52) / (h52 - l52) * 100, 1) if h52 != l52 else 50.0
            from_h = round((curr - h52) / h52 * 100, 2)

            # Trend quality: Callaghan "Trend Score" — fraction of last 20 closes above 20-bar SMA
            sma20 = close.rolling(20).mean()
            trend_score = int(round(
                sum(1 for c, s in zip(close.tail(20).values, sma20.tail(20).values) if c > s) / 20 * 100
            ))

            # RSI (last value)
            delta = close.diff()
            up    = delta.clip(lower=0)
            dn    = (-delta).clip(lower=0)
            rs    = up.rolling(14).mean() / dn.rolling(14).mean().replace(0, float("nan"))
            rsi   = round(float(100 - 100 / (1 + rs.iloc[-1])), 1) if not pd.isna(rs.iloc[-1]) else None

            rows.append({
                "Ticker":    t.replace(".NS", ""),
                "Price":     round(curr, 2),
                "1W %":      r1w,
                "1M %":      r1m,
                "3M %":      r3m,
                "6M %":      r6m,
                "1Y %":      r1y,
                "52W Pos %": pos,
                "From 52H %": from_h,
                "Trend Score": trend_score,
                "RSI":        rsi,
                "_ticker":    t,
            })
        except Exception:
            continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


with st.spinner(f"Fetching 1Y daily data for {len(_tickers)} stocks…"):
    _df = _fetch_momentum(tuple(_tickers), _min_price)

if _df.empty:
    st.error("No data returned. Try again.")
    st.stop()

# Filter and sort
_sort_col = f"{_sort_period} %"
_df_valid = _df[_df[_sort_col].notna()].copy()

if _direction == "Only positive":
    _df_valid = _df_valid[_df_valid[_sort_col] > 0]
elif _direction == "Only negative":
    _df_valid = _df_valid[_df_valid[_sort_col] < 0]

_df_sorted = _df_valid.sort_values(_sort_col, ascending=False).head(_top_n)

# ── Summary metric strip ──────────────────────────────────────────────────────
_pct_pos_1m = round((_df["1M %"] > 0).sum() / len(_df["1M %"].dropna()) * 100, 0) if not _df.empty else 0
_median_1m  = round(float(_df["1M %"].median()), 1) if not _df.empty else 0
_median_3m  = round(float(_df["3M %"].median()), 1) if not _df.empty else 0

st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Universe Summary</div>',
    unsafe_allow_html=True,
)
_sm_cols = st.columns(4)
for _sc, (_sl, _sv, _scc) in zip(_sm_cols, [
    ("Stocks positive 1M",  f"{int(_pct_pos_1m)}% of {_universe_choice}", "#00c896" if _pct_pos_1m >= 60 else ("#f0b429" if _pct_pos_1m >= 40 else "#ff4d6d")),
    ("Median 1M return",    f"{_median_1m:+.1f}%",                        "#00c896" if _median_1m >= 0 else "#ff4d6d"),
    ("Median 3M return",    f"{_median_3m:+.1f}%",                        "#00c896" if _median_3m >= 0 else "#ff4d6d"),
    ("Ranked by",           _sort_period,                                  "#f0b429"),
]):
    with _sc:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_sl}</div>'
            f'<div style="font-size:1rem;font-weight:800;color:{_scc};">{_sv}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

# ── Horizontal bar chart: top performers ─────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    f'Top {len(_df_sorted)} by {_sort_period} Return</div>',
    unsafe_allow_html=True,
)

_bar_colors = ["#00c896" if v >= 0 else "#ff4d6d" for v in _df_sorted[_sort_col].tolist()]
_fig_bar = go.Figure()
_fig_bar.add_trace(go.Bar(
    x=_df_sorted[_sort_col].tolist(),
    y=_df_sorted["Ticker"].tolist(),
    orientation="h",
    marker_color=_bar_colors,
    text=[f"{v:+.1f}%" for v in _df_sorted[_sort_col].tolist()],
    textposition="outside",
    textfont=dict(size=10, color="#e2e8f0"),
    hovertemplate="%{y}<br>" + _sort_col + ": %{x:+.1f}%<extra></extra>",
))
_fig_bar.add_vline(x=0, line_color="rgba(255,255,255,0.2)", line_width=1)
_fig_bar.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=60, t=10, b=0), height=max(300, len(_df_sorted) * 22),
    xaxis=dict(title=f"{_sort_period} Return (%)", gridcolor="rgba(255,255,255,0.04)",
               ticksuffix="%", tickfont=dict(size=10)),
    yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
    showlegend=False,
)
st.plotly_chart(_fig_bar, use_container_width=True)

# ── Full data table ───────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">Full Rankings Table</div>',
    unsafe_allow_html=True,
)

_tbl = _df_sorted[[
    "Ticker", "Price", "1W %", "1M %", "3M %", "6M %", "1Y %",
    "52W Pos %", "From 52H %", "Trend Score", "RSI"
]].copy()


def _pct_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#00c896' if val >= 0 else '#ff4d6d'}; font-weight: 600;"


def _trend_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#00c896' if val >= 60 else ('#f0b429' if val >= 40 else '#ff4d6d')};"


def _rsi_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#ff4d6d' if val > 70 else ('#00c896' if val < 30 else '#94a3b8')};"


styled = (
    _tbl.style
    .map(_pct_color, subset=["1W %", "1M %", "3M %", "6M %", "1Y %", "From 52H %"])
    .map(_trend_color, subset=["Trend Score"])
    .map(_rsi_color, subset=["RSI"])
    .format({
        "Price": "₹{:,.2f}",
        "1W %":  "{:+.1f}%", "1M %": "{:+.1f}%", "3M %": "{:+.1f}%",
        "6M %":  "{:+.1f}%", "1Y %": "{:+.1f}%",
        "52W Pos %": "{:.0f}%", "From 52H %": "{:+.1f}%",
        "Trend Score": "{:.0f}%",
        "RSI": "{:.0f}",
    }, na_rep="—")
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Return heatmap: all stocks, all periods ───────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 8px;">Return Heatmap</div>',
    unsafe_allow_html=True,
)

_heat_cols = ["1W %", "1M %", "3M %", "6M %", "1Y %"]
_heat_data  = _df_sorted[["Ticker"] + _heat_cols].set_index("Ticker")
_z          = _heat_data.values.tolist()
_x          = _heat_cols
_y          = _heat_data.index.tolist()

_fig_heat = go.Figure(go.Heatmap(
    z=_z, x=_x, y=_y,
    colorscale=[
        [0.0, "#7f1734"], [0.35, "#ff4d6d"],
        [0.5, "#1a1f35"],
        [0.65, "#00c896"], [1.0, "#00523d"],
    ],
    zmid=0,
    text=[[f"{v:+.1f}%" if v is not None and not pd.isna(v) else "—" for v in row] for row in _z],
    texttemplate="%{text}",
    textfont=dict(size=9, color="#e2e8f0"),
    hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
    showscale=True,
    colorbar=dict(
        title="Return %", ticksuffix="%",
        tickfont=dict(size=9, color="#6b7a99"),
        bgcolor="rgba(0,0,0,0)",
    ),
))
_fig_heat.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0),
    height=max(300, len(_df_sorted) * 22),
    xaxis=dict(tickfont=dict(size=10), side="top"),
    yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
)
st.plotly_chart(_fig_heat, use_container_width=True)

# ── CSV export ────────────────────────────────────────────────────────────────
st.download_button(
    "⬇ Export to CSV",
    _tbl.to_csv(index=False),
    file_name=f"momentum_scan_{_universe_choice.replace(' ','_')}.csv",
    mime="text/csv",
)

st.caption(
    f"Universe: {_universe_choice} ({len(_tickers)} stocks) · "
    f"Returns computed from daily close prices (yfinance, 1Y history) · "
    f"Trend Score = % of last 20 days above 20-bar SMA."
)
