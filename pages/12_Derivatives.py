"""
Page 12: Derivatives Hub — Nifty / BankNifty Options Chain, PCR, Max Pain, IV Rank, Greeks
"""
import datetime
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Derivatives Hub · NiftyEdge", layout="wide", page_icon="📐")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()

from analysis.options import (
    bs_greeks, compute_pcr, compute_max_pain,
    compute_iv_rank, suggest_options_strategy,
    find_atm_strike, days_to_expiry, RISK_FREE_RATE,
)

page_header("Derivatives Hub", "Nifty & BankNifty Options Chain · PCR · Max Pain · IV Rank")
user_sidebar()

# ── Index selector ────────────────────────────────────────────────────────────
INDEX_MAP = {
    "Nifty 50":    ("^NSEI",    "NIFTY",     50),
    "Bank Nifty":  ("^NSEBANK", "BANKNIFTY", 15),
}
col_sel, col_exp, col_info = st.columns([2, 2, 4])
with col_sel:
    idx_name = st.selectbox("Index", list(INDEX_MAP.keys()), key="deriv_idx")

ticker_sym, nse_sym, lot_size = INDEX_MAP[idx_name]

# ── Fetch spot price + VIX ────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _spot(sym: str) -> float:
    try:
        fi = yf.Ticker(sym).fast_info
        p  = fi.last_price
        if p and not pd.isna(p) and p > 0:
            return float(p)
        df = yf.Ticker(sym).history(period="2d", interval="1d", auto_adjust=True)
        return float(df["Close"].dropna().iloc[-1])
    except Exception:
        return 0.0


@st.cache_data(ttl=300)
def _vix_data() -> dict:
    try:
        df = yf.Ticker("^INDIAVIX").history(period="1y", interval="1d", auto_adjust=True)
        if df.empty:
            return {}
        closes = df["Close"].dropna().tolist()
        curr   = closes[-1]
        return {
            "current": round(curr, 2),
            "low_1y":  round(min(closes), 2),
            "high_1y": round(max(closes), 2),
            "hist":    closes,
            "rank":    round((curr - min(closes)) / (max(closes) - min(closes)) * 100, 1) if max(closes) != min(closes) else 50.0,
        }
    except Exception:
        return {}


@st.cache_data(ttl=60)
def _options_chain(sym: str, expiry: str):
    try:
        t = yf.Ticker(sym)
        chain = t.option_chain(expiry)
        return chain.calls.copy(), chain.puts.copy()
    except Exception as exc:
        logger.warning("options_chain error for %s %s: %s", sym, expiry, exc)
        return None, None


@st.cache_data(ttl=300)
def _expiries(sym: str):
    try:
        return yf.Ticker(sym).options
    except Exception:
        return ()


spot   = _spot(ticker_sym)
vix    = _vix_data()
expiry_list = _expiries(ticker_sym)

with col_exp:
    if expiry_list:
        selected_expiry = st.selectbox("Expiry", expiry_list, key="deriv_exp")
    else:
        st.warning("Could not fetch expiries.")
        selected_expiry = None

with col_info:
    if spot > 0 and vix:
        vi_col = "#ff4d6d" if vix.get("rank", 0) >= 70 else ("#f0b429" if vix.get("rank", 0) >= 40 else "#00c896")
        st.markdown(
            f'<div style="display:flex;gap:24px;align-items:center;padding-top:8px;">'
            f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Spot</span>'
            f'<div style="font-size:1.3rem;font-weight:800;color:#e2e8f0;">₹{spot:,.2f}</div></div>'
            f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">India VIX</span>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{vi_col};">{vix.get("current","—")}</div></div>'
            f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">VIX Rank (1Y)</span>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{vi_col};">{vix.get("rank","—")}%</div></div>'
            f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Lot Size</span>'
            f'<div style="font-size:1.3rem;font-weight:800;color:#94a3b8;">{lot_size}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.divider()

if not selected_expiry or spot <= 0:
    st.info("Select an index and expiry above to load the options chain.")
    st.stop()

dte   = days_to_expiry(selected_expiry)
T_yrs = max(dte, 1) / 365.0

calls, puts = _options_chain(ticker_sym, selected_expiry)

if calls is None or puts is None or calls.empty or puts.empty:
    st.error("Could not fetch options chain data. Markets may be closed or data unavailable.")
    st.stop()

# ── PCR & Max Pain ────────────────────────────────────────────────────────────
pcr_data  = compute_pcr(calls, puts)
max_pain_level = compute_max_pain(calls, puts)

# IV Rank using VIX as index IV proxy
iv_rank_data = {}
if vix and vix.get("current"):
    iv_rank_data = compute_iv_rank(vix["current"], vix.get("hist", []))

pcr_col = "#ff4d6d" if pcr_data["signal"] == "SHORT" else ("#00c896" if pcr_data["signal"] == "LONG" else "#f0b429")

st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Market Intelligence</div>',
    unsafe_allow_html=True,
)

mi_cols = st.columns(5)
metrics = [
    ("DTE", f"{dte} days", "#94a3b8"),
    ("OI PCR", f"{pcr_data['pcr_oi'] or '—'}", pcr_col),
    ("PCR Signal", pcr_data["signal"], pcr_col),
    ("Max Pain", f"₹{max_pain_level:,.0f}" if max_pain_level else "—", "#f0b429"),
    ("IV Rank", f"{iv_rank_data.get('iv_rank','—')}%" if iv_rank_data else "—",
     "#ff4d6d" if (iv_rank_data.get("iv_rank") or 0) >= 70 else ("#00c896" if (iv_rank_data.get("iv_rank") or 0) < 30 else "#f0b429")),
]
for col, (label, val, c) in zip(mi_cols, metrics):
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-top:3px solid {c};'
            f'border-radius:12px;padding:14px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:1.05rem;font-weight:800;color:{c};">{val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

if iv_rank_data:
    st.caption(f"IV environment: **{iv_rank_data.get('label','')}** — VIX {vix.get('current','—')} "
               f"(52W range: {vix.get('low_1y','—')} – {vix.get('high_1y','—')})")

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── Options Strategy Suggester ────────────────────────────────────────────────
with st.expander("🎯 Options Strategy Suggester", expanded=True):
    osc1, osc2 = st.columns(2)
    with osc1:
        signal_dir = st.radio("Signal direction on underlying", ["LONG (Bullish)", "SHORT (Bearish)"], horizontal=True)
    direction = "LONG" if "LONG" in signal_dir else "SHORT"
    strat = suggest_options_strategy(direction, iv_rank_data.get("iv_rank"), spot, strike_step=50.0)

    leg_rows = "".join(
        f'<div style="display:flex;gap:16px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
        f'<span style="font-size:0.75rem;font-weight:700;color:{"#00c896" if leg["action"]=="BUY" else "#ff4d6d"};'
        f'min-width:40px;">{leg["action"]}</span>'
        f'<span style="font-size:0.75rem;color:#e2e8f0;">{leg["type"]} {leg["strike"]:,.0f}</span>'
        f'</div>'
        for leg in strat["legs"]
    )
    st.markdown(
        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);border:1px solid rgba(255,255,255,0.08);'
        f'border-radius:14px;padding:18px 20px;">'
        f'<div style="font-size:1rem;font-weight:800;color:#e2e8f0;margin-bottom:6px;">{strat["name"]}</div>'
        f'<div style="font-size:0.75rem;color:#94a3b8;margin-bottom:14px;">{strat["rationale"]}</div>'
        f'{leg_rows}'
        f'<div style="display:flex;gap:24px;margin-top:12px;">'
        f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Max Loss</span>'
        f'<div style="font-size:0.82rem;color:#ff4d6d;">{strat["max_loss"]}</div></div>'
        f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Max Gain</span>'
        f'<div style="font-size:0.82rem;color:#00c896;">{strat["max_gain"]}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── OI Bar Chart: Calls vs Puts by Strike ─────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Open Interest by Strike</div>',
    unsafe_allow_html=True,
)

atm = find_atm_strike(spot, sorted(set(calls["strike"]).union(set(puts["strike"]))))
n_strikes = st.slider("Strikes around ATM to show", 5, 20, 10, key="oi_slider")

call_filt = calls[abs(calls["strike"] - atm) <= n_strikes * 50].copy()
put_filt  = puts[abs(puts["strike"]  - atm) <= n_strikes * 50].copy()

fig_oi = go.Figure()
fig_oi.add_trace(go.Bar(
    x=call_filt["strike"], y=call_filt["openInterest"],
    name="Call OI", marker_color="#00c896", opacity=0.85,
    hovertemplate="Strike ₹%{x}<br>Call OI: %{y:,}<extra></extra>",
))
fig_oi.add_trace(go.Bar(
    x=put_filt["strike"], y=put_filt["openInterest"],
    name="Put OI", marker_color="#ff4d6d", opacity=0.85,
    hovertemplate="Strike ₹%{x}<br>Put OI: %{y:,}<extra></extra>",
))
fig_oi.add_vline(x=spot, line_dash="dash", line_color="#f0b429", line_width=2,
                 annotation_text=f"Spot {spot:,.0f}", annotation_font_color="#f0b429",
                 annotation_position="top left")
if max_pain_level:
    fig_oi.add_vline(x=max_pain_level, line_dash="dot", line_color="#a78bfa", line_width=2,
                     annotation_text=f"Max Pain {max_pain_level:,.0f}",
                     annotation_font_color="#a78bfa", annotation_position="top right")
fig_oi.update_layout(
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
    margin=dict(l=0, r=0, t=10, b=0), height=340,
    legend=dict(orientation="h", yanchor="top", y=-0.12, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.04)", tickprefix="₹", tickfont=dict(size=10)),
    yaxis=dict(title="Open Interest", gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=10)),
    hovermode="x unified",
)
st.plotly_chart(fig_oi, use_container_width=True)

# ── IV Smile ──────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 12px;">IV Smile</div>',
    unsafe_allow_html=True,
)

call_iv = call_filt[call_filt["impliedVolatility"] > 0.01][["strike", "impliedVolatility"]].dropna()
put_iv  = put_filt[put_filt["impliedVolatility"]   > 0.01][["strike", "impliedVolatility"]].dropna()

fig_iv = go.Figure()
fig_iv.add_trace(go.Scatter(
    x=call_iv["strike"], y=(call_iv["impliedVolatility"] * 100).round(1),
    mode="lines+markers", name="Call IV",
    line=dict(color="#00c896", width=2), marker=dict(size=5),
    hovertemplate="Strike ₹%{x}<br>Call IV: %{y:.1f}%<extra></extra>",
))
fig_iv.add_trace(go.Scatter(
    x=put_iv["strike"], y=(put_iv["impliedVolatility"] * 100).round(1),
    mode="lines+markers", name="Put IV",
    line=dict(color="#ff4d6d", width=2), marker=dict(size=5),
    hovertemplate="Strike ₹%{x}<br>Put IV: %{y:.1f}%<extra></extra>",
))
fig_iv.add_vline(x=spot, line_dash="dash", line_color="#f0b429", line_width=1,
                 annotation_text="Spot", annotation_font_color="#f0b429")
fig_iv.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
    margin=dict(l=0, r=0, t=10, b=0), height=280,
    legend=dict(orientation="h", yanchor="top", y=-0.14, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.04)", tickprefix="₹", tickfont=dict(size=10)),
    yaxis=dict(title="IV (%)", gridcolor="rgba(255,255,255,0.06)", ticksuffix="%", tickfont=dict(size=10)),
    hovermode="x unified",
)
st.plotly_chart(fig_iv, use_container_width=True)

# ── Options Chain Table with computed Greeks ──────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 12px;">Full Options Chain</div>',
    unsafe_allow_html=True,
)

tab_calls, tab_puts = st.tabs(["Calls (CE)", "Puts (PE)"])


def _enrich_chain(df: pd.DataFrame, opt_type: str, spot: float, T: float) -> pd.DataFrame:
    """Add Black-Scholes Greeks to the options chain."""
    records = []
    for _, row in df.iterrows():
        K     = float(row.get("strike", 0))
        sigma = float(row.get("impliedVolatility", 0)) or 0.15
        g     = bs_greeks(spot, K, T, sigma, option_type=opt_type)
        records.append({
            "Strike":      K,
            "Last":        row.get("lastPrice", 0),
            "Bid":         row.get("bid", 0),
            "Ask":         row.get("ask", 0),
            "Volume":      int(row.get("volume", 0) or 0),
            "OI":          int(row.get("openInterest", 0) or 0),
            "IV (%)":      round(sigma * 100, 1),
            "Delta":       g["delta"],
            "Gamma":       g["gamma"],
            "Theta (₹/d)": g["theta"],
            "Vega (₹/1%)": g["vega"],
        })
    out = pd.DataFrame(records)
    if not out.empty:
        out = out.sort_values("Strike")
    return out


with tab_calls:
    c_table = _enrich_chain(call_filt, "call", spot, T_yrs)
    if not c_table.empty:
        # Highlight ATM row
        def _style_calls(row):
            if abs(row["Strike"] - atm) < 26:
                return ["background-color: rgba(0,200,150,0.08)"] * len(row)
            return [""] * len(row)
        st.dataframe(
            c_table.style.apply(_style_calls, axis=1).format({
                "Strike": "₹{:,.0f}", "Last": "₹{:.2f}", "Bid": "₹{:.2f}", "Ask": "₹{:.2f}",
                "Volume": "{:,}", "OI": "{:,}", "IV (%)": "{:.1f}%",
                "Delta": "{:.4f}", "Gamma": "{:.6f}", "Theta (₹/d)": "₹{:.2f}", "Vega (₹/1%)": "₹{:.2f}",
            }),
            use_container_width=True, hide_index=True,
        )

with tab_puts:
    p_table = _enrich_chain(put_filt, "put", spot, T_yrs)
    if not p_table.empty:
        def _style_puts(row):
            if abs(row["Strike"] - atm) < 26:
                return ["background-color: rgba(255,77,109,0.08)"] * len(row)
            return [""] * len(row)
        st.dataframe(
            p_table.style.apply(_style_puts, axis=1).format({
                "Strike": "₹{:,.0f}", "Last": "₹{:.2f}", "Bid": "₹{:.2f}", "Ask": "₹{:.2f}",
                "Volume": "{:,}", "OI": "{:,}", "IV (%)": "{:.1f}%",
                "Delta": "{:.4f}", "Gamma": "{:.6f}", "Theta (₹/d)": "₹{:.2f}", "Vega (₹/1%)": "₹{:.2f}",
            }),
            use_container_width=True, hide_index=True,
        )

# ── Greeks at-a-glance for ATM ────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 12px;">ATM Greeks Snapshot</div>',
    unsafe_allow_html=True,
)

atm_iv_call = float(calls[calls["strike"] == atm]["impliedVolatility"].values[0]) if len(calls[calls["strike"] == atm]) > 0 else 0.15
atm_iv_put  = float(puts[puts["strike"]   == atm]["impliedVolatility"].values[0]) if len(puts[puts["strike"]   == atm]) > 0 else 0.15
atm_c = bs_greeks(spot, atm, T_yrs, atm_iv_call or 0.15, option_type="call")
atm_p = bs_greeks(spot, atm, T_yrs, atm_iv_put  or 0.15, option_type="put")

greek_cols = st.columns(5)
greek_defs = [
    ("Delta", f"{atm_c['delta']:.3f} / {atm_p['delta']:.3f}", "CE / PE sensitivity to ₹1 move in spot"),
    ("Gamma", f"{atm_c['gamma']:.5f}", "Rate of Delta change per ₹1 spot move"),
    ("Theta", f"₹{atm_c['theta']:.1f} / ₹{atm_p['theta']:.1f}/d", "Daily time decay for ATM CE / PE"),
    ("Vega",  f"₹{atm_c['vega']:.1f} / ₹{atm_p['vega']:.1f}/1%", "P&L per 1% move in IV"),
    ("ATM Strike", f"₹{atm:,.0f}", f"Spot ₹{spot:,.0f} | DTE {dte}d"),
]
for col, (label, val, desc) in zip(greek_cols, greek_defs):
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px 16px;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:0.92rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;">{val}</div>'
            f'<div style="font-size:0.65rem;color:#374151;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── PCR Historical context ────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-top:28px;background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.07);border-left:4px solid {pcr_col};'
    f'border-radius:12px;padding:16px 20px;">'
    f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.08em;margin-bottom:8px;">PCR Interpretation</div>'
    f'<div style="font-size:0.88rem;color:#e2e8f0;font-weight:600;margin-bottom:4px;">'
    f'OI PCR: {pcr_data["pcr_oi"] or "—"} · Volume PCR: {pcr_data["pcr_volume"] or "—"}</div>'
    f'<div style="font-size:0.78rem;color:#94a3b8;">{pcr_data["sentiment"]}</div>'
    f'<div style="font-size:0.7rem;color:#475569;margin-top:8px;">'
    f'PCR &gt; 1.3 → contrarian LONG setup (market too bearish) · '
    f'PCR &lt; 0.55 → contrarian SHORT (market too bullish)</div>'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True)

# ── Strategy Payoff Diagram ───────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Strategy Payoff at Expiry</div>',
    unsafe_allow_html=True,
)

with st.expander("📈 View Payoff Diagram", expanded=True):
    pd_col1, pd_col2 = st.columns([1, 2])
    with pd_col1:
        _pd_direction = st.radio("Payoff for", ["LONG signal", "SHORT signal"], horizontal=False, key="pd_dir")
        _pd_lots      = st.number_input("Lots", min_value=1, max_value=50, value=1, key="pd_lots")
        _pd_premium   = st.number_input("Estimated premium (₹ per unit)", min_value=0.0, value=50.0, step=5.0, key="pd_prem")

    _pd_strat = suggest_options_strategy(
        "LONG" if "LONG" in _pd_direction else "SHORT",
        iv_rank_data.get("iv_rank"), spot, strike_step=50.0,
    )
    _strikes_range = [spot * f / 100 for f in range(85, 116)]

    def _payoff_at(underlying: float, legs: list, premium: float, lots: int, ls: int) -> float:
        """P&L at expiry for a multi-leg strategy. ls=lot_size."""
        pnl = 0.0
        for leg in legs:
            K       = leg["strike"]
            otype   = leg["type"]   # CE or PE
            action  = leg["action"] # BUY or SELL
            mult    = 1 if action == "BUY" else -1
            if otype == "CE":
                intrinsic = max(0, underlying - K)
            else:
                intrinsic = max(0, K - underlying)
            pnl += mult * intrinsic * lots * ls
        # deduct/credit premium for all legs (simplified: one debit/credit)
        net_debit = premium * lots * ls
        return pnl - net_debit

    payoffs = [_payoff_at(s, _pd_strat["legs"], _pd_premium, _pd_lots, lot_size) for s in _strikes_range]

    with pd_col2:
        fig_pay = go.Figure()
        pay_cols = ["#ff4d6d" if p < 0 else "#00c896" for p in payoffs]
        fig_pay.add_trace(go.Scatter(
            x=_strikes_range, y=payoffs,
            mode="lines",
            line=dict(color="#3b82f6", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(59,130,246,0.08)",
            hovertemplate="Spot ₹%{x:,.0f}<br>P&L: ₹%{y:,.0f}<extra></extra>",
            name="P&L at expiry",
        ))
        fig_pay.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.2)", line_width=1)
        fig_pay.add_vline(x=spot, line_dash="dash", line_color="#f0b429", line_width=1.5,
                          annotation_text=f"Spot {spot:,.0f}", annotation_font_color="#f0b429")
        if max_pain_level:
            fig_pay.add_vline(x=max_pain_level, line_dash="dot", line_color="#a78bfa", line_width=1,
                              annotation_text="Max Pain", annotation_font_color="#a78bfa")
        fig_pay.update_layout(
            title=dict(text=f"{_pd_strat['name']} · {_pd_lots} lot(s) · Expiry {selected_expiry}",
                       font=dict(size=12, color="#94a3b8")),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
            margin=dict(l=0, r=0, t=36, b=0), height=300,
            xaxis=dict(title="Spot at expiry", gridcolor="rgba(255,255,255,0.04)",
                       tickprefix="₹", tickfont=dict(size=10)),
            yaxis=dict(title="P&L (₹)", gridcolor="rgba(255,255,255,0.06)",
                       tickprefix="₹", tickfont=dict(size=10)),
            hovermode="x",
        )
        st.plotly_chart(fig_pay, use_container_width=True)

# ── Position Size Calculator (Kelly + VIX adjustment) ────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 12px;">Position Size Calculator</div>',
    unsafe_allow_html=True,
)

with st.expander("🎯 Kelly Criterion + VIX-Adjusted Sizing", expanded=False):
    ps_col1, ps_col2, ps_col3 = st.columns(3)
    with ps_col1:
        ps_capital    = st.number_input("Total capital (₹)", min_value=10000, max_value=10000000,
                                        value=500000, step=10000, key="ps_cap")
    with ps_col2:
        ps_win_rate   = st.number_input("Historical win rate (%)", min_value=10, max_value=90,
                                        value=55, key="ps_wr")
    with ps_col3:
        ps_rr         = st.number_input("Risk:Reward ratio", min_value=0.5, max_value=10.0,
                                        value=2.0, step=0.1, key="ps_rr")

    # Kelly fraction: f* = p - q/b  where p=win rate, q=1-p, b=R:R
    p = ps_win_rate / 100
    q = 1 - p
    b = ps_rr
    kelly_f = max(0.0, p - q / b)

    # Half-Kelly (standard practice)
    half_kelly = kelly_f / 2

    # VIX adjustment: reduce by up to 50% when VIX rank > 70
    vix_mult = 1.0
    if vix and vix.get("rank"):
        vr = vix["rank"]
        if vr >= 70:
            vix_mult = 0.5
        elif vr >= 50:
            vix_mult = 0.75
        elif vr <= 20:
            vix_mult = 1.1  # low vol — can size up slightly

    adjusted_f = min(half_kelly * vix_mult, 0.20)  # hard cap at 20% of capital
    position_inr = round(ps_capital * adjusted_f / 100) * 100

    # Max risk per trade
    max_risk_inr = round(ps_capital * 0.02 / 100) * 100

    kc1, kc2, kc3, kc4 = st.columns(4)
    for col, label, val, c in [
        (kc1, "Kelly Fraction",  f"{kelly_f*100:.1f}%",         "#94a3b8"),
        (kc2, "Half-Kelly",      f"{half_kelly*100:.1f}%",      "#94a3b8"),
        (kc3, "VIX Multiplier",  f"×{vix_mult:.2f}",           "#f0b429" if vix_mult < 1 else "#00c896"),
        (kc4, "Recommended Size", f"₹{position_inr:,}",        "#00c896" if position_inr > 0 else "#ff4d6d"),
    ]:
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px 16px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{label}</div>'
                f'<div style="font-size:1.05rem;font-weight:800;color:{c};">{val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.caption(
        f"Half-Kelly × VIX multiplier ({vix_mult:.2f}) = {adjusted_f*100:.1f}% of capital. "
        f"VIX rank {vix.get('rank','—')}% → {'reduce size (high fear)' if vix_mult < 1 else 'normal sizing'}. "
        f"Max risk 2%/trade = ₹{max_risk_inr:,}."
    )

st.caption(
    f"Data via yfinance · Expiry: {selected_expiry} · "
    f"Greeks computed using Black-Scholes (risk-free: {RISK_FREE_RATE*100:.1f}%) · "
    f"Refresh to get latest chain."
)
