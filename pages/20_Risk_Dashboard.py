"""
Page 20: Risk Dashboard
Professional risk management cockpit — VaR, CVaR, portfolio heat, position sizing.
Integrates open signals from Signal Log with risk analytics.
"""
import logging
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Risk Dashboard · NiftyEdge", layout="wide", page_icon="🛡️")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Risk Dashboard", "VaR · CVaR · Portfolio heat · Kelly sizing · Ruin probability")
user_sidebar()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _account_value   = st.number_input("Account value (₹)", 100_000, 100_000_000, 500_000, step=50_000, key="rd_acct")
    _position_size   = st.number_input("Position size per trade (₹)", 10_000, 10_000_000, 100_000, step=10_000, key="rd_pos")
    _max_risk_pct    = st.slider("Max risk per trade (%)", 0.5, 5.0, 1.5, 0.25, key="rd_maxr")
    _var_conf        = st.selectbox("VaR confidence level", [0.90, 0.95, 0.99], index=1, key="rd_conf")
    _var_period      = st.selectbox("VaR history period", ["3mo", "6mo", "1y"], index=1, key="rd_varper")
    _index_symbol    = st.selectbox("Benchmark for VaR", ["Nifty 50 (^NSEI)", "Bank Nifty (^NSEBANK)"], key="rd_bench")

_bench_ticker = "^NSEI" if "Nifty" in _index_symbol else "^NSEBANK"

# ── Load open signals from Signal Log ────────────────────────────────────────
_open_signals = []
try:
    from signals.signal_logger import get_signal_logger
    _open_signals = get_signal_logger().get_open_signals()
except Exception as _e:
    logger.warning("Could not load open signals: %s", _e)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_benchmark_returns(ticker: str, period: str) -> list[float]:
    """Fetch daily returns for benchmark index."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        if df is None or len(df) < 20:
            return []
        returns = df["Close"].pct_change().dropna().tolist()
        return [r for r in returns if math.isfinite(r)]
    except Exception as exc:
        logger.error("benchmark fetch failed: %s", exc)
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_stock_returns_batch(tickers: tuple, period: str) -> dict[str, list[float]]:
    """Batch fetch daily returns for multiple stocks."""
    if not tickers:
        return {}
    try:
        raw = yf.download(
            list(tickers), period=period, interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
        if raw is None or raw.empty:
            return {}
        top_lvl = (
            raw.columns.get_level_values(0).unique().tolist()
            if isinstance(raw.columns, pd.MultiIndex) else []
        )
        result = {}
        for t in tickers:
            if t in top_lvl:
                c = raw[t]["Close"].dropna().pct_change().dropna()
                result[t] = [r for r in c.tolist() if math.isfinite(r)]
        return result
    except Exception:
        return {}


with st.spinner("Loading risk data…"):
    _bench_returns = _fetch_benchmark_returns(_bench_ticker, _var_period)

# ── Import risk analytics ──────────────────────────────────────────────────────
from analysis.risk import (
    historical_var, parametric_var, conditional_var,
    portfolio_heat, fixed_fractional_size, kelly_size, ruin_probability,
)

# ── Section 1: Benchmark VaR ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Benchmark Risk</div>',
    unsafe_allow_html=True,
)

if _bench_returns:
    _conf = float(_var_conf)
    _hvar   = historical_var(_bench_returns, _conf)
    _pvar   = parametric_var(_bench_returns, _conf)
    _cvar   = conditional_var(_bench_returns, _conf)
    _daily_vol = float(np.std(_bench_returns)) * 100

    _var_risk_inr_h = _position_size * _hvar
    _var_risk_inr_p = _position_size * _pvar
    _cvar_risk_inr  = _position_size * _cvar

    _mc = st.columns(5)
    for _col, (_lbl, _val, _sub, _cc) in zip(_mc, [
        ("Daily Volatility",       f"{_daily_vol:.2f}%",      "1-day σ of returns",    "#f0b429"),
        (f"Hist VaR ({int(_conf*100)}%)",    f"{_hvar*100:.2f}%",  f"₹{_var_risk_inr_h:,.0f} at risk",  "#ff4d6d"),
        (f"Param VaR ({int(_conf*100)}%)",   f"{_pvar*100:.2f}%",  f"₹{_var_risk_inr_p:,.0f} at risk",  "#f97316"),
        (f"CVaR / ES ({int(_conf*100)}%)",   f"{_cvar*100:.2f}%",  f"₹{_cvar_risk_inr:,.0f} expected",  "#ff1744"),
        ("VaR Period",             _var_period,                "History used",          "#6b7a99"),
    ]):
        with _col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:{_cc};">{_val}</div>'
                f'<div style="font-size:0.65rem;color:#475569;margin-top:3px;">{_sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Return distribution histogram
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 6px;">'
        'Return Distribution</div>',
        unsafe_allow_html=True,
    )
    _fig_dist = go.Figure()
    _fig_dist.add_trace(go.Histogram(
        x=[r * 100 for r in _bench_returns], nbinsx=60,
        marker_color="#3b82f6", opacity=0.7,
        hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra></extra>",
    ))
    _fig_dist.add_vline(x=-_hvar * 100, line_color="#ff4d6d", line_width=2, line_dash="dash",
                        annotation_text=f"Hist VaR −{_hvar*100:.2f}%", annotation_font_color="#ff4d6d",
                        annotation_font_size=9)
    _fig_dist.add_vline(x=-_cvar * 100, line_color="#ff1744", line_width=1.5, line_dash="dot",
                        annotation_text=f"CVaR −{_cvar*100:.2f}%", annotation_font_color="#ff1744",
                        annotation_font_size=9, annotation_position="bottom right")
    _fig_dist.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
        margin=dict(l=0, r=0, t=10, b=0), height=220,
        xaxis=dict(title="Daily Return (%)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
        yaxis=dict(title="Days", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
        showlegend=False,
    )
    st.plotly_chart(_fig_dist, use_container_width=True)
else:
    st.warning("Could not fetch benchmark data.")

st.divider()

# ── Section 2: Portfolio Heat ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Portfolio Heat (Open Signals)</div>',
    unsafe_allow_html=True,
)

_heat = portfolio_heat(_open_signals, _position_size, _account_value)

if _heat:
    _heat_pct = _heat["portfolio_heat_pct"]
    _heat_color = "#ff4d6d" if _heat_pct > 5 else "#f0b429" if _heat_pct > 2.5 else "#00c896"
    _heat_label = "DANGER" if _heat_pct > 5 else "WARNING" if _heat_pct > 2.5 else "SAFE"

    _hc = st.columns(4)
    for _col, (_lbl, _val, _cc) in zip(_hc, [
        ("Total at Risk",     f"₹{_heat['total_at_risk_inr']:,.0f}", _heat_color),
        ("Portfolio Heat",    f"{_heat_pct:.2f}%",                   _heat_color),
        ("Risk Status",       _heat_label,                           _heat_color),
        ("Positions (L/S)",   f"{_heat['n_long']}L / {_heat['n_short']}S", "#94a3b8"),
    ]):
        with _col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
                f'<div style="font-size:0.95rem;font-weight:800;color:{_cc};">{_val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if _heat.get("per_signal"):
        _ps_df = pd.DataFrame(_heat["per_signal"])
        _ps_df["risk_inr"] = _ps_df["risk_inr"].apply(lambda x: f"₹{x:,.0f}")
        _ps_df["risk_pct"] = _ps_df["risk_pct"].apply(lambda x: f"{x:.2f}%")
        _ps_df.columns = ["Ticker", "Direction", "Risk (₹)", "Risk (% of position)"]

        def _dir_col(val):
            return "color: #00c896; font-weight: 700;" if val == "LONG" else "color: #ff4d6d; font-weight: 700;"

        st.dataframe(
            _ps_df.style.applymap(_dir_col, subset=["Direction"]),
            use_container_width=True, hide_index=True,
        )

    if _heat_pct > 5:
        st.error(
            f"**Portfolio heat {_heat_pct:.1f}% is dangerously high.** "
            f"Rule of thumb: total portfolio risk should not exceed 5% at any time. "
            f"Consider closing lower-conviction positions or reducing position size."
        )
    elif _heat_pct > 2.5:
        st.warning(
            f"**Portfolio heat {_heat_pct:.1f}% is elevated.** "
            f"Be selective — avoid adding new positions until some close."
        )
else:
    st.info("No open signals found. Heat calculation requires open positions from the Signal Log.")

st.divider()

# ── Section 3: Position Sizer ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Position Size Calculator</div>',
    unsafe_allow_html=True,
)

with st.expander("⚖ Enter trade parameters", expanded=True):
    _sz_cols = st.columns(3)
    with _sz_cols[0]:
        _entry_p = st.number_input("Entry price (₹)", 1.0, 100_000.0, 500.0, step=5.0, key="sz_entry")
    with _sz_cols[1]:
        _sl_p    = st.number_input("Stop loss (₹)", 1.0, 100_000.0, 480.0, step=5.0, key="sz_sl")
    with _sz_cols[2]:
        _t1_p    = st.number_input("Target 1 (₹)", 1.0, 100_000.0, 530.0, step=5.0, key="sz_t1")

    _sz_cols2 = st.columns(3)
    with _sz_cols2[0]:
        _t2_p    = st.number_input("Target 2 (₹)", 1.0, 100_000.0, 560.0, step=5.0, key="sz_t2")
    with _sz_cols2[1]:
        _dir_p   = st.radio("Direction", ["LONG", "SHORT"], horizontal=True, key="sz_dir")
    with _sz_cols2[2]:
        _win_r   = st.number_input("Win rate (%) for Kelly", 10.0, 90.0, 55.0, step=1.0, key="sz_wr")

    _compute = st.button("Calculate Position Size", type="primary", key="sz_calc")

if _compute or True:  # always show if params are set
    _risk_pct_dec = _max_risk_pct / 100.0
    _ff = fixed_fractional_size(_account_value, _risk_pct_dec, _entry_p, _sl_p)

    _avg_win_est  = abs(_t1_p - _entry_p) / abs(_entry_p - _sl_p) if abs(_entry_p - _sl_p) > 0 else 1.5
    _avg_loss_est = 1.0
    _kl = kelly_size(_win_r, _avg_win_est, _avg_loss_est, _account_value, _entry_p, _sl_p,
                     half_kelly=True, max_risk_pct=_risk_pct_dec)
    _ruin = ruin_probability(_win_r, _avg_win_est, _avg_loss_est, _risk_pct_dec)

    _sz_res = st.columns(3)
    with _sz_res[0]:
        st.markdown("**Fixed Fractional Sizing**")
        if _ff:
            st.metric("Shares", f"{_ff['shares']:,}")
            st.metric("Position value", f"₹{_ff['position_value']:,.0f}")
            st.metric("Risk per trade", f"₹{_ff['risk_per_trade']:,.0f}")
            st.metric("Actual risk %", f"{_ff['risk_pct_actual']:.3f}%")
        else:
            st.warning("Check entry/SL prices.")

    with _sz_res[1]:
        st.markdown("**Half-Kelly Sizing**")
        if _kl and "shares" in _kl:
            st.metric("Kelly f*", f"{_kl['kelly_f']*100:.2f}%")
            st.metric("Risk %", f"{_kl['risk_pct']:.2f}%")
            st.metric("Shares", f"{_kl['shares']:,}")
            st.metric("Position value", f"₹{_kl['position_value']:,.0f}")
        elif _kl:
            st.warning(_kl.get("note", "Kelly not available"))
        else:
            st.warning("Check win rate / RR inputs.")

    with _sz_res[2]:
        st.markdown("**Ruin Analysis**")
        if _ruin:
            _ruin_pct = _ruin["p_ruin"]
            _ruin_col = "#ff4d6d" if _ruin_pct > 10 else "#f0b429" if _ruin_pct > 2 else "#00c896"
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:16px;">'
                f'<div style="font-size:0.8rem;color:#6b7a99;margin-bottom:8px;">P(ruin 50% DD)</div>'
                f'<div style="font-size:1.8rem;font-weight:800;color:{_ruin_col};">{_ruin_pct:.1f}%</div>'
                f'<div style="font-size:0.72rem;color:#475569;margin-top:8px;">'
                f'Edge/trade: {_ruin["edge_per_trade"]:+.3f}R<br>'
                f'Capital units to ruin: {_ruin["capital_units"]}'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # R:R visualisation
    if _ff and _ff.get("shares", 0) > 0:
        shares = _ff["shares"]
        is_long = _dir_p == "LONG"
        _risk_amt   = abs(_entry_p - _sl_p) * shares
        _profit_t1  = abs(_t1_p - _entry_p) * shares if _t1_p > 0 else 0
        _profit_t2  = abs(_t2_p - _entry_p) * shares if _t2_p > 0 else 0
        _rr1 = round(_profit_t1 / _risk_amt, 2) if _risk_amt > 0 else None
        _rr2 = round(_profit_t2 / _risk_amt, 2) if _risk_amt > 0 else None

        st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)
        _rr_cols = st.columns(4)
        for _rc, (_rl, _rv, _rcc) in zip(_rr_cols, [
            ("Max Loss",     f"₹{_risk_amt:,.0f}",  "#ff4d6d"),
            ("Profit at T1", f"₹{_profit_t1:,.0f}", "#00c896"),
            ("Profit at T2", f"₹{_profit_t2:,.0f}", "#00c896"),
            ("R:R (T1/T2)",  f"{_rr1}× / {_rr2}×" if _rr1 else "—", "#f0b429"),
        ]):
            with _rc:
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                    f'border-left:3px solid {_rcc};border-radius:8px;padding:10px 14px;">'
                    f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">{_rl}</div>'
                    f'<div style="font-size:0.9rem;font-weight:800;color:{_rcc};">{_rv}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

st.divider()

# ── Section 4: Risk rules ─────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Risk Rules (Your Setup)</div>',
    unsafe_allow_html=True,
)

_n_max_positions = max(1, int(5.0 / _max_risk_pct))  # 5% total heat / risk per trade
_daily_loss_limit = _account_value * 0.02
_weekly_loss_limit = _account_value * 0.05

_rules = [
    ("Max concurrent positions", str(_n_max_positions),
     f"At {_max_risk_pct}% risk/trade, 5% total heat = {_n_max_positions} max", "#94a3b8"),
    ("Daily loss limit (2%)", f"₹{_daily_loss_limit:,.0f}", "Stop trading for the day if hit", "#ff4d6d"),
    ("Weekly loss limit (5%)", f"₹{_weekly_loss_limit:,.0f}", "Review system if hit", "#f0b429"),
    ("Position size", f"₹{_position_size:,.0f}", "Per-trade allocation", "#60a5fa"),
]

_rl_cols = st.columns(4)
for _rc, (_rl, _rv, _rsub, _rcc) in zip(_rl_cols, _rules):
    with _rc:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_rl}</div>'
            f'<div style="font-size:0.95rem;font-weight:800;color:{_rcc};">{_rv}</div>'
            f'<div style="font-size:0.62rem;color:#374151;margin-top:3px;">{_rsub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.caption(
    f"Account: ₹{_account_value:,.0f} · Position size: ₹{_position_size:,.0f} · "
    f"Max risk/trade: {_max_risk_pct}% · VaR at {int(_var_conf*100)}% confidence · {_var_period} history"
)
