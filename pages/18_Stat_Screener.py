"""
Page 18: Statistical Screener
Z-score mean reversion, Bollinger Band squeeze, ATR regime detection.
Systematic quant screens for high-probability setups.
"""
import logging
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config.stock_universe import NIFTY_50, NIFTY_200

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Stat Screener · NiftyEdge", layout="wide", page_icon="📐")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Statistical Screener", "Z-score · Bollinger squeeze · ATR regime · Mean reversion setups")
user_sidebar()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"], key="ss_uni")
    _screen_type     = st.selectbox("Screen type", [
        "Mean Reversion (Z-score)",
        "Bollinger Squeeze",
        "ATR Expansion (Breakout Setup)",
        "All Screens Combined",
    ], key="ss_screen")
    _z_thresh        = st.slider("|Z-score| threshold", 1.0, 3.0, 1.5, 0.1, key="ss_z")
    _min_price       = st.number_input("Min price (₹)", 0, 10000, 50, key="ss_minp")
    _top_n           = st.slider("Show top N", 10, 50, 20, key="ss_n")
    _run             = st.button("📐 Run Statistical Screen", type="primary", use_container_width=True)

if not _run:
    st.info("Configure the screen and click **Run Statistical Screen**.")
    st.stop()

_universe = NIFTY_50 if _universe_choice == "Nifty 50" else NIFTY_200
_tickers  = list(_universe.values())


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_stats(tickers: tuple, min_price: float) -> pd.DataFrame:
    """
    Batch fetch 1Y daily data and compute statistical indicators.
    """
    try:
        raw = yf.download(
            list(tickers), period="1y", interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
    except Exception as exc:
        logger.error("stat screener fetch failed: %s", exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    top_lvl = (
        raw.columns.get_level_values(0).unique().tolist()
        if isinstance(raw.columns, pd.MultiIndex) else []
    )
    rows = []

    for t in tickers:
        try:
            if t not in top_lvl:
                continue
            close  = raw[t]["Close"].dropna()
            high   = raw[t]["High"].dropna()
            low    = raw[t]["Low"].dropna()
            volume = raw[t]["Volume"].dropna()

            if len(close) < 30:
                continue

            curr = float(close.iloc[-1])
            if curr < min_price:
                continue

            # ── Z-score (20-bar) ─────────────────────────────────────────────
            w = 20
            if len(close) >= w:
                roll_mean = float(close.rolling(w).mean().iloc[-1])
                roll_std  = float(close.rolling(w).std().iloc[-1])
                z_score   = (curr - roll_mean) / roll_std if roll_std > 0 else 0.0
            else:
                z_score = 0.0

            # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────
            bb_mean = close.rolling(20).mean()
            bb_std  = close.rolling(20).std()
            bb_upper = bb_mean + 2 * bb_std
            bb_lower = bb_mean - 2 * bb_std
            bb_width = (bb_upper - bb_lower) / bb_mean
            # BW squeeze: current BW vs 20-period min BW (last 6 months)
            bw_now = float(bb_width.iloc[-1]) if not bb_width.empty else None
            bw_min = float(bb_width.rolling(126).min().iloc[-1]) if len(bb_width) >= 126 else None
            bw_mean_hist = float(bb_width.rolling(126).mean().iloc[-1]) if len(bb_width) >= 126 else None
            squeeze_pct  = (
                (bw_now - bw_min) / (bw_mean_hist - bw_min)
                if bw_now is not None and bw_min is not None and bw_mean_hist and bw_mean_hist != bw_min
                else None
            )
            in_squeeze = bw_now is not None and bw_min is not None and bw_now <= bw_min * 1.15

            bb_pct = (
                (curr - float(bb_lower.iloc[-1])) / (float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1]))
                if float(bb_upper.iloc[-1]) != float(bb_lower.iloc[-1]) else 0.5
            )

            # ── ATR (14) ──────────────────────────────────────────────────────
            aligned = pd.DataFrame({"H": high, "L": low, "C": close}).dropna()
            if len(aligned) >= 15:
                prev_c = aligned["C"].shift(1)
                tr     = pd.concat([
                    aligned["H"] - aligned["L"],
                    (aligned["H"] - prev_c).abs(),
                    (aligned["L"] - prev_c).abs(),
                ], axis=1).max(axis=1)
                atr14 = float(tr.rolling(14).mean().iloc[-1])
                atr_pct = atr14 / curr * 100
                # ATR regime: compare current ATR to 3-month average ATR
                atr_hist_avg = float(tr.rolling(14).mean().rolling(63).mean().iloc[-1]) if len(tr) >= 77 else atr14
                atr_ratio    = atr14 / atr_hist_avg if atr_hist_avg > 0 else 1.0
                atr_expanding = atr_ratio > 1.2
            else:
                atr14 = atr_pct = atr_ratio = None
                atr_expanding = False

            # ── Volume surge ──────────────────────────────────────────────────
            vol_now  = float(volume.iloc[-1]) if not volume.empty else 0.0
            vol_avg  = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
            vol_surge = vol_now / vol_avg if vol_avg > 0 else 1.0

            # ── RSI (14) ──────────────────────────────────────────────────────
            delta = close.diff()
            up    = delta.clip(lower=0)
            dn    = (-delta).clip(lower=0)
            rs_   = up.rolling(14).mean() / dn.rolling(14).mean().replace(0, float("nan"))
            rsi   = float(100 - 100 / (1 + rs_.iloc[-1])) if not pd.isna(rs_.iloc[-1]) else None

            rows.append({
                "Ticker":         t.replace(".NS", ""),
                "Price":          round(curr, 2),
                "Z-Score":        round(z_score, 2),
                "BB%":            round(bb_pct * 100, 1),
                "In Squeeze":     in_squeeze,
                "Squeeze%":       round(squeeze_pct * 100, 1) if squeeze_pct is not None else None,
                "ATR%":           round(atr_pct, 2) if atr_pct else None,
                "ATR Expanding":  atr_expanding,
                "ATR Ratio":      round(atr_ratio, 2) if atr_ratio else None,
                "Vol Surge":      round(vol_surge, 2),
                "RSI":            round(rsi, 1) if rsi else None,
                # Composite scores
                "_z_abs":         abs(z_score),
                "_mean_rev_score": abs(z_score) * (1.5 if in_squeeze else 1.0),
                "_breakout_score": (vol_surge * (atr_ratio or 1.0)) if atr_expanding else 0.0,
            })
        except Exception:
            continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


with st.spinner(f"Computing statistical indicators for {len(_tickers)} stocks…"):
    _df = _fetch_stats(tuple(_tickers), _min_price)

if _df.empty:
    st.error("No data returned.")
    st.stop()

# ── Screen application ────────────────────────────────────────────────────────
def _apply_screen(df: pd.DataFrame, screen: str, z_thresh: float, top_n: int) -> pd.DataFrame:
    if screen == "Mean Reversion (Z-score)":
        filtered = df[df["_z_abs"] >= z_thresh].copy()
        return filtered.sort_values("_z_abs", ascending=False).head(top_n)
    if screen == "Bollinger Squeeze":
        filtered = df[df["In Squeeze"] == True].copy()
        return filtered.sort_values("_z_abs", ascending=False).head(top_n)
    if screen == "ATR Expansion (Breakout Setup)":
        filtered = df[df["ATR Expanding"] == True].copy()
        return filtered.sort_values("_breakout_score", ascending=False).head(top_n)
    # All screens combined
    df2 = df.copy()
    df2["Composite"] = (
        df2["_z_abs"].fillna(0) * 0.4
        + df2["Vol Surge"].fillna(1) * 0.3
        + df2["ATR Ratio"].fillna(1) * 0.3
    )
    return df2.sort_values("Composite", ascending=False).head(top_n)


_result = _apply_screen(_df, _screen_type, _z_thresh, _top_n)

# ── Summary strip ─────────────────────────────────────────────────────────────
_n_oversold  = int((_df["Z-Score"] <= -_z_thresh).sum())
_n_overbought = int((_df["Z-Score"] >= _z_thresh).sum())
_n_squeeze   = int(_df["In Squeeze"].sum())
_n_expanding = int(_df["ATR Expanding"].sum())

st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Universe Statistics</div>',
    unsafe_allow_html=True,
)
_sc = st.columns(4)
for _col, (_lbl, _val, _cc) in zip(_sc, [
    ("Oversold (Z≤−threshold)",   str(_n_oversold),   "#00c896"),
    ("Overbought (Z≥+threshold)", str(_n_overbought), "#ff4d6d"),
    ("BB Squeeze",                str(_n_squeeze),     "#f0b429"),
    ("ATR Expanding",             str(_n_expanding),   "#60a5fa"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── Z-score distribution chart ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">'
    'Z-Score Distribution (Universe)</div>',
    unsafe_allow_html=True,
)

_z_vals = _df["Z-Score"].dropna().tolist()
_fig_hist = go.Figure()
_fig_hist.add_trace(go.Histogram(
    x=_z_vals, nbinsx=40,
    marker_color="#60a5fa", opacity=0.7,
    name="Z-Score",
    hovertemplate="Z-Score: %{x:.2f}<br>Count: %{y}<extra></extra>",
))
for _xv, _lbl, _col in [(-_z_thresh, f"Oversold −{_z_thresh}", "#00c896"),
                          (_z_thresh,  f"Overbought +{_z_thresh}", "#ff4d6d")]:
    _fig_hist.add_vline(
        x=_xv, line_color=_col, line_width=1.5, line_dash="dash",
        annotation_text=_lbl, annotation_font_color=_col, annotation_font_size=9,
    )
_fig_hist.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0), height=220,
    xaxis=dict(title="Z-Score (20-bar)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="Count", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    showlegend=False,
)
st.plotly_chart(_fig_hist, use_container_width=True)

# ── Screen results table ──────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 8px;">'
    f'{_screen_type} — Top {len(_result)}</div>',
    unsafe_allow_html=True,
)

_tbl_cols = ["Ticker", "Price", "Z-Score", "BB%", "In Squeeze", "ATR%", "ATR Ratio", "Vol Surge", "RSI"]
_tbl = _result[[c for c in _tbl_cols if c in _result.columns]].copy()


def _z_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    if val <= -1.5:
        return "color: #00c896; font-weight: 700;"
    if val >= 1.5:
        return "color: #ff4d6d; font-weight: 700;"
    return "color: #94a3b8;"


def _bb_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    if val <= 10:
        return "color: #00c896; font-weight: 700;"
    if val >= 90:
        return "color: #ff4d6d; font-weight: 700;"
    return "color: #94a3b8;"


def _bool_color(val):
    if val is True:
        return "color: #f0b429; font-weight: 700;"
    return "color: #374151;"


def _vol_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#f0b429' if val >= 2.0 else '#00c896' if val >= 1.2 else '#94a3b8'};"


def _rsi_color(val):
    if not isinstance(val, (int, float)) or pd.isna(val):
        return ""
    return f"color: {'#ff4d6d' if val > 70 else '#00c896' if val < 30 else '#94a3b8'};"


styled = (
    _tbl.style
    .applymap(_z_color,    subset=["Z-Score"])
    .applymap(_bb_color,   subset=["BB%"])
    .applymap(_bool_color, subset=["In Squeeze"] if "In Squeeze" in _tbl.columns else [])
    .applymap(_vol_color,  subset=["Vol Surge"] if "Vol Surge" in _tbl.columns else [])
    .applymap(_rsi_color,  subset=["RSI"] if "RSI" in _tbl.columns else [])
    .format({
        "Price":     "₹{:,.2f}",
        "Z-Score":   "{:+.2f}",
        "BB%":       "{:.1f}%",
        "ATR%":      "{:.2f}%",
        "ATR Ratio": "{:.2f}×",
        "Vol Surge": "{:.2f}×",
        "RSI":       "{:.0f}",
    }, na_rep="—")
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Z-score bar chart (top results) ──────────────────────────────────────────
if "Z-Score" in _result.columns and not _result.empty:
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
        'Z-Score Profile</div>',
        unsafe_allow_html=True,
    )
    _bar_r = _result.sort_values("Z-Score")
    _bar_colors = ["#00c896" if v <= 0 else "#ff4d6d" for v in _bar_r["Z-Score"].tolist()]
    _fig_bar = go.Figure(go.Bar(
        x=_bar_r["Z-Score"].tolist(), y=_bar_r["Ticker"].tolist(),
        orientation="h", marker_color=_bar_colors,
        text=[f"{v:+.2f}σ" for v in _bar_r["Z-Score"].tolist()],
        textposition="outside", textfont=dict(size=9, color="#e2e8f0"),
        hovertemplate="%{y}<br>Z-Score: %{x:+.2f}σ<extra></extra>",
    ))
    _fig_bar.add_vline(x=0, line_color="rgba(255,255,255,0.2)", line_width=1)
    _fig_bar.add_vline(x=_z_thresh,  line_color="#ff4d6d33", line_width=1, line_dash="dot")
    _fig_bar.add_vline(x=-_z_thresh, line_color="#00c89633", line_width=1, line_dash="dot")
    _fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
        margin=dict(l=0, r=60, t=10, b=0), height=max(280, len(_result) * 22),
        xaxis=dict(title="Z-Score (σ)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=10)),
        showlegend=False,
    )
    st.plotly_chart(_fig_bar, use_container_width=True)

# ── CSV export ────────────────────────────────────────────────────────────────
st.download_button(
    "⬇ Export to CSV",
    _tbl.to_csv(index=False),
    file_name=f"stat_screen_{_universe_choice.replace(' ','_')}.csv",
    mime="text/csv",
)

with st.expander("📖 Statistical Screener Guide"):
    st.markdown("""
**Z-Score (20-bar)**
Measures how many standard deviations the current price is from its 20-day mean.
- Z ≤ −1.5: Price statistically oversold → mean reversion LONG opportunity
- Z ≥ +1.5: Price statistically overbought → mean reversion SHORT opportunity
- Z near 0: Price near fair value, no statistical edge

**Bollinger Band %B**
Position within Bollinger Bands: 0% = at lower band, 100% = at upper band.
- %B < 10%: Deep lower band → potential reversal
- %B > 90%: Deep upper band → potential reversal or strong trend continuation

**Bollinger Squeeze**
Occurs when BB width is near its 6-month minimum. Signals low volatility compression — typically
precedes a large directional move. Combine with volume/price direction to pick the breakout side.

**ATR Expansion**
ATR is expanding when current 14-day ATR > 120% of its 3-month average.
Rising ATR + volume surge = institutional accumulation / distribution in progress → momentum follow-through.

**Volume Surge**
Today's volume vs 20-day average. >2× is significant; >3× is exceptional.
Combine with Z-score or squeeze for high-conviction setups.
""")

st.caption(
    f"Universe: {_universe_choice} ({len(_tickers)} stocks) · "
    f"Screen: {_screen_type} · Z-threshold: {_z_thresh}σ · Indicators computed from 1Y daily data"
)
