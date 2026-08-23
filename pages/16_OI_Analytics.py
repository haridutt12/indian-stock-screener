"""
Page 16: Options OI Analytics
Strike-wise OI changes, OI build-up/unwinding, support/resistance via PCR.
Real-time options open interest analysis for Nifty and Bank Nifty.
"""
import logging
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

st.set_page_config(page_title="OI Analytics · NiftyEdge", layout="wide", page_icon="📊")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("OI Analytics", "Open Interest · Strike-wise buildup · Support & Resistance · PCR heatmap")
user_sidebar()

# ── Constants ──────────────────────────────────────────────────────────────────
INDEX_CONFIG = {
    "Nifty 50":   {"ticker": "^NSEI",    "yf_ticker": "NIFTY50",   "lot": 50,  "step": 50},
    "Bank Nifty": {"ticker": "^NSEBANK", "yf_ticker": "BANKNIFTY", "lot": 15,  "step": 100},
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _index_name = st.selectbox("Index", list(INDEX_CONFIG.keys()), key="oi_idx")
    _strikes_shown = st.slider("Strikes around ATM", 5, 20, 10, key="oi_strikes")
    _run = st.button("📊 Load OI Data", type="primary", use_container_width=True)

if not _run:
    st.info("Select an index and click **Load OI Data** to analyse open interest.")
    st.stop()

cfg = INDEX_CONFIG[_index_name]


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_spot(ticker: str) -> float | None:
    try:
        fi = yf.Ticker(ticker).fast_info
        v  = fi.last_price
        return float(v) if v and not math.isnan(float(v)) else None
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_options(index_name: str) -> dict | None:
    """
    Fetch options chain for the nearest expiry.
    Returns dict: {expiry, calls, puts, spot} or None on failure.
    """
    _cfg = INDEX_CONFIG[index_name]
    ticker_sym = _cfg["yf_ticker"]
    yf_sym     = f"{ticker_sym}.NS"
    spot       = _fetch_spot(_cfg["ticker"])
    if spot is None:
        return None
    try:
        yfobj   = yf.Ticker(yf_sym)
        expiries = yfobj.options
        if not expiries:
            yfobj = yf.Ticker(f"^NS{ticker_sym[:4]}")
            expiries = yfobj.options
        if not expiries:
            return None
        expiry = expiries[0]
        chain  = yfobj.option_chain(expiry)
        return {"expiry": expiry, "calls": chain.calls, "puts": chain.puts, "spot": spot}
    except Exception as exc:
        logger.warning("OI fetch failed for %s: %s", index_name, exc)
        return None


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_nifty_options_fallback(spot: float, step: int, n_strikes: int) -> dict | None:
    """
    Try fetching Nifty options directly via ^NSEI or NIFTY50.NS.
    Falls back through multiple ticker variants.
    """
    candidates = ["^NSEI", "NIFTY.NS", "NIFTY50.NS"]
    for sym in candidates:
        try:
            obj = yf.Ticker(sym)
            if obj.options:
                exp = obj.options[0]
                chain = obj.option_chain(exp)
                return {"expiry": exp, "calls": chain.calls, "puts": chain.puts, "spot": spot}
        except Exception:
            continue
    return None


def _atm_strike(spot: float, step: int) -> int:
    return int(round(spot / step) * step)


def _filter_strikes(df: pd.DataFrame, atm: int, step: int, n: int) -> pd.DataFrame:
    strikes = [atm + (i - n) * step for i in range(2 * n + 1)]
    return df[df["strike"].isin(strikes)].copy()


def _oi_signal(call_oi: float, put_oi: float) -> tuple[str, str]:
    pcr = put_oi / call_oi if call_oi > 0 else 1.0
    if pcr > 1.5:
        return "STRONG SUPPORT", "#00c896"
    if pcr > 1.1:
        return "SUPPORT", "#5AD8A6"
    if pcr < 0.5:
        return "STRONG RESISTANCE", "#ff4d6d"
    if pcr < 0.9:
        return "RESISTANCE", "#f97316"
    return "NEUTRAL", "#94a3b8"


def _compute_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    try:
        strikes = sorted(set(calls["strike"]).union(set(puts["strike"])))
        c_map = dict(zip(calls["strike"], calls["openInterest"].fillna(0)))
        p_map = dict(zip(puts["strike"], puts["openInterest"].fillna(0)))
        min_pain = None
        pain_strike = None
        for s in strikes:
            pain = sum(max(0, s - k) * c_map.get(k, 0) for k in strikes)
            pain += sum(max(0, k - s) * p_map.get(k, 0) for k in strikes)
            if min_pain is None or pain < min_pain:
                min_pain = pain
                pain_strike = s
        return float(pain_strike) if pain_strike is not None else None
    except Exception:
        return None


with st.spinner(f"Fetching {_index_name} options chain…"):
    spot = _fetch_spot(cfg["ticker"])
    data = _fetch_options(_index_name) if spot else None

# ── Fallback: if fetch fails, build synthetic OI demonstration from spot ─────
_synthetic = False
if data is None and spot is not None:
    data = _fetch_nifty_options_fallback(spot, cfg["step"], _strikes_shown)

if data is None or spot is None:
    st.warning(
        "Options data unavailable via yfinance in this environment "
        "(NSE options require direct internet — available on Streamlit Cloud). "
        "Showing a synthetic demonstration based on current spot price."
    )
    _synthetic = True
    if spot is None:
        spot = 24000.0

    atm = _atm_strike(spot, cfg["step"])
    _n  = _strikes_shown
    strikes_list = [atm + (i - _n) * cfg["step"] for i in range(2 * _n + 1)]

    rng = np.random.default_rng(int(spot))
    c_oi = [int(max(0, rng.normal(100_000 * max(0, (atm - k) / atm + 0.5), 30_000))) for k in strikes_list]
    p_oi = [int(max(0, rng.normal(100_000 * max(0, (k - atm) / atm + 0.5), 30_000))) for k in strikes_list]
    c_vol = [int(max(0, rng.normal(c * 0.1, c * 0.05))) for c in c_oi]
    p_vol = [int(max(0, rng.normal(p * 0.1, p * 0.05))) for p in p_oi]
    iv_c = [max(0.1, 0.15 + abs(k - atm) / atm * 2) for k in strikes_list]
    iv_p = [max(0.1, 0.16 + abs(k - atm) / atm * 2.2) for k in strikes_list]

    calls = pd.DataFrame({"strike": strikes_list, "openInterest": c_oi, "volume": c_vol, "impliedVolatility": iv_c})
    puts  = pd.DataFrame({"strike": strikes_list, "openInterest": p_oi, "volume": p_vol, "impliedVolatility": iv_p})
    data  = {"expiry": "DEMO", "calls": calls, "puts": puts, "spot": spot}

spot   = data["spot"]
calls  = data["calls"].copy()
puts   = data["puts"].copy()
expiry = data["expiry"]
atm    = _atm_strike(spot, cfg["step"])

for df in [calls, puts]:
    for col in ["openInterest", "volume", "impliedVolatility"]:
        if col not in df.columns:
            df[col] = 0.0

calls_f = _filter_strikes(calls, atm, cfg["step"], _strikes_shown)
puts_f  = _filter_strikes(puts,  atm, cfg["step"], _strikes_shown)

max_pain = _compute_max_pain(calls, puts)

# ── Summary metric strip ──────────────────────────────────────────────────────
total_call_oi = int(calls_f["openInterest"].sum())
total_put_oi  = int(puts_f["openInterest"].sum())
pcr_oi        = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None
total_call_vol = int(calls_f["volume"].sum())
total_put_vol  = int(puts_f["volume"].sum())
pcr_vol        = round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else None

if pcr_oi and pcr_oi > 1.3:
    pcr_signal, pcr_color = "BULLISH", "#00c896"
elif pcr_oi and pcr_oi < 0.55:
    pcr_signal, pcr_color = "BEARISH", "#ff4d6d"
else:
    pcr_signal, pcr_color = "NEUTRAL", "#f0b429"

st.markdown(
    f'<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    f'{_index_name} · Expiry: {expiry}{"  ·  DEMO DATA" if _synthetic else ""}</div>',
    unsafe_allow_html=True,
)

_mc = st.columns(5)
for _col, (_lbl, _val, _cc) in zip(_mc, [
    ("Spot",           f"₹{spot:,.0f}",                              "#e2e8f0"),
    ("ATM Strike",     f"₹{atm:,}",                                  "#f0b429"),
    ("PCR (OI)",       f"{pcr_oi:.3f}" if pcr_oi else "—",           pcr_color),
    ("PCR Signal",     pcr_signal,                                    pcr_color),
    ("Max Pain",       f"₹{max_pain:,.0f}" if max_pain else "—",     "#60a5fa"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── OI Bar chart (calls vs puts by strike) ────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    'Open Interest by Strike</div>',
    unsafe_allow_html=True,
)

_merged = pd.merge(
    calls_f[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
        columns={"openInterest": "call_oi", "volume": "call_vol", "impliedVolatility": "call_iv"}),
    puts_f[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
        columns={"openInterest": "put_oi", "volume": "put_vol", "impliedVolatility": "put_iv"}),
    on="strike", how="outer"
).fillna(0).sort_values("strike")

_strikes = _merged["strike"].tolist()
_c_oi    = (_merged["call_oi"] / 1000).tolist()
_p_oi    = (_merged["put_oi"]  / 1000).tolist()

_fig_oi = go.Figure()
_fig_oi.add_trace(go.Bar(
    name="Call OI", x=_strikes, y=_c_oi,
    marker_color="#ff4d6d", opacity=0.85,
    hovertemplate="Strike ₹%{x:,}<br>Call OI: %{y:.1f}K lots<extra></extra>",
))
_fig_oi.add_trace(go.Bar(
    name="Put OI", x=_strikes, y=_p_oi,
    marker_color="#00c896", opacity=0.85,
    hovertemplate="Strike ₹%{x:,}<br>Put OI: %{y:.1f}K lots<extra></extra>",
))
_fig_oi.add_vline(x=spot, line_color="#f0b429", line_width=2, line_dash="dash",
                  annotation_text=f"Spot ₹{spot:,.0f}", annotation_font_color="#f0b429",
                  annotation_font_size=10)
if max_pain:
    _fig_oi.add_vline(x=max_pain, line_color="#60a5fa", line_width=1.5, line_dash="dot",
                      annotation_text=f"Max Pain ₹{max_pain:,.0f}", annotation_font_color="#60a5fa",
                      annotation_font_size=10, annotation_position="bottom right")
_fig_oi.update_layout(
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0), height=350,
    xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="OI (000 contracts)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    legend=dict(orientation="h", y=1.05, x=0, font=dict(size=10)),
)
st.plotly_chart(_fig_oi, use_container_width=True)

# ── OI Ratio (PCR per strike) + volume ───────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'PCR per Strike & Volume Heatmap</div>',
    unsafe_allow_html=True,
)

_fig2 = make_subplots(
    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
    subplot_titles=["Put-Call Ratio (OI) by Strike", "Volume by Strike"],
)

_pcr_by_strike = [
    (p / c if c > 0 else 0.0)
    for c, p in zip(_merged["call_oi"].tolist(), _merged["put_oi"].tolist())
]
_pcr_colors = [
    "#00c896" if v > 1.3 else "#5AD8A6" if v > 1.0 else "#f0b429" if v > 0.7 else "#ff4d6d"
    for v in _pcr_by_strike
]
_fig2.add_trace(go.Bar(
    x=_strikes, y=_pcr_by_strike, marker_color=_pcr_colors,
    hovertemplate="Strike ₹%{x:,}<br>PCR: %{y:.2f}<extra></extra>",
    showlegend=False,
), row=1, col=1)
_fig2.add_hline(y=1.0, line_color="rgba(255,255,255,0.2)", line_width=1, row=1, col=1)
_fig2.add_vline(x=spot, line_color="#f0b429", line_width=1.5, line_dash="dash", row=1, col=1)

_fig2.add_trace(go.Bar(
    name="Call Vol", x=_strikes, y=(_merged["call_vol"] / 1000).tolist(),
    marker_color="#ff4d6d", opacity=0.7,
    hovertemplate="Strike ₹%{x:,}<br>Call Vol: %{y:.1f}K<extra></extra>",
), row=2, col=1)
_fig2.add_trace(go.Bar(
    name="Put Vol", x=_strikes, y=(_merged["put_vol"] / 1000).tolist(),
    marker_color="#00c896", opacity=0.7,
    hovertemplate="Strike ₹%{x:,}<br>Put Vol: %{y:.1f}K<extra></extra>",
), row=2, col=1)
_fig2.add_vline(x=spot, line_color="#f0b429", line_width=1.5, line_dash="dash", row=2, col=1)

_fig2.update_layout(
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=30, b=0), height=420,
    xaxis2=dict(title="Strike", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="PCR", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis2=dict(title="Volume (000)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    legend=dict(orientation="h", y=-0.08, x=0, font=dict(size=10)),
)
for ann in _fig2.layout.annotations:
    ann.font.color = "#94a3b8"
    ann.font.size  = 10
st.plotly_chart(_fig2, use_container_width=True)

# ── IV Smile ──────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'IV Smile</div>',
    unsafe_allow_html=True,
)

_iv_c = (_merged["call_iv"] * 100).tolist()
_iv_p = (_merged["put_iv"]  * 100).tolist()

_fig_iv = go.Figure()
_fig_iv.add_trace(go.Scatter(
    x=_strikes, y=_iv_c, mode="lines+markers",
    name="Call IV", line=dict(color="#ff4d6d", width=2),
    marker=dict(size=6),
    hovertemplate="Strike ₹%{x:,}<br>Call IV: %{y:.1f}%<extra></extra>",
))
_fig_iv.add_trace(go.Scatter(
    x=_strikes, y=_iv_p, mode="lines+markers",
    name="Put IV", line=dict(color="#00c896", width=2),
    marker=dict(size=6),
    hovertemplate="Strike ₹%{x:,}<br>Put IV: %{y:.1f}%<extra></extra>",
))
_fig_iv.add_vline(x=spot, line_color="#f0b429", line_width=1.5, line_dash="dash",
                  annotation_text="ATM", annotation_font_color="#f0b429", annotation_font_size=9)
_fig_iv.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=10, b=0), height=280,
    xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    yaxis=dict(title="IV (%)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
    legend=dict(orientation="h", y=1.05, x=0, font=dict(size=10)),
)
st.plotly_chart(_fig_iv, use_container_width=True)

# ── Support / Resistance interpretation ───────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'Strike-Level Support & Resistance</div>',
    unsafe_allow_html=True,
)

_sr_rows = []
for _, row in _merged.iterrows():
    strike = int(row["strike"])
    c_oi   = int(row["call_oi"])
    p_oi   = int(row["put_oi"])
    sig, col = _oi_signal(c_oi, p_oi)
    pcr_s  = round(p_oi / c_oi, 2) if c_oi > 0 else None
    _sr_rows.append({
        "Strike": f"₹{strike:,}",
        "Distance": f"{((strike - spot) / spot * 100):+.1f}%",
        "Call OI": f"{c_oi/1000:.1f}K",
        "Put OI":  f"{p_oi/1000:.1f}K",
        "PCR":     f"{pcr_s:.2f}" if pcr_s is not None else "—",
        "Signal":  sig,
        "_color":  col,
        "_strike": strike,
    })

_sr_df = pd.DataFrame(_sr_rows)

# Highlight the ATM row
def _sig_style(val):
    c_map = {"STRONG SUPPORT": "#00c896", "SUPPORT": "#5AD8A6",
              "STRONG RESISTANCE": "#ff4d6d", "RESISTANCE": "#f97316", "NEUTRAL": "#94a3b8"}
    c = c_map.get(val, "#94a3b8")
    return f"color: {c}; font-weight: 700;"

def _dist_style(val):
    try:
        v = float(val.replace("%", "").replace("+", ""))
        return f"color: {'#00c896' if v >= 0 else '#ff4d6d'};"
    except Exception:
        return ""

_display = _sr_df[["Strike", "Distance", "Call OI", "Put OI", "PCR", "Signal"]].copy()
styled = (
    _display.style
    .map(_sig_style, subset=["Signal"])
    .map(_dist_style, subset=["Distance"])
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Key levels callout ────────────────────────────────────────────────────────
_high_put_strike = _merged.loc[_merged["put_oi"].idxmax(), "strike"] if not _merged.empty else None
_high_call_strike = _merged.loc[_merged["call_oi"].idxmax(), "strike"] if not _merged.empty else None

_kl_cols = st.columns(3)
for _kl_col, (_lbl, _val, _cc) in zip(_kl_cols, [
    ("Highest Call OI (Resistance)", f"₹{int(_high_call_strike):,}" if _high_call_strike else "—", "#ff4d6d"),
    ("Highest Put OI (Support)",     f"₹{int(_high_put_strike):,}" if _high_put_strike else "—",  "#00c896"),
    ("Max Pain (Gravity Level)",     f"₹{max_pain:,.0f}" if max_pain else "—",                     "#60a5fa"),
]):
    with _kl_col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-left:3px solid {_cc};'
            f'border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1.1rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)

with st.expander("📖 OI Analytics Guide"):
    st.markdown("""
**Open Interest (OI)** = total outstanding contracts. Rising OI with rising price = bullish confirmation.

**Put-Call Ratio (PCR)**
- PCR > 1.3: More puts than calls → contrarian bullish (hedging complete, market may rise)
- PCR < 0.55: More calls than puts → contrarian bearish (retail euphoria, market may fall)
- PCR 0.7–1.3: Neutral

**Key Levels from OI**
- **Max Call OI strike** = strong resistance (call sellers defend this level)
- **Max Put OI strike** = strong support (put sellers defend this level)
- **Max Pain** = strike at which option sellers lose the least; market tends to gravitate here near expiry

**IV Smile**: Normally U-shaped — higher IV for OTM puts (fear premium) vs OTM calls.
A skewed smile reveals directional bias; steep put skew = protective demand = bearish fear.

**PCR per strike**: Strike-level PCR > 1 → put sellers defending that level as support.
Strike-level PCR < 0.7 → call sellers defending as resistance.
""")

st.caption(
    f"Universe: {_index_name} · Expiry: {expiry} · "
    f"{'DEMO data (NSE options require live deployment)' if _synthetic else 'Data via yfinance · 15-min cache'}"
)
