"""
Page 22: Options Strategy Builder
Multi-leg strategy constructor with live payoff diagrams.
Bull/Bear spreads, Straddle, Strangle, Iron Condor, Butterfly.
Uses Black-Scholes pricing when live premiums unavailable.
"""
import logging
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from analysis.options import bs_greeks, RISK_FREE_RATE

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Options Builder · NiftyEdge", layout="wide", page_icon="🏗️")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Options Strategy Builder", "Multi-leg strategies · Payoff at expiry · Break-even · Greeks summary")
user_sidebar()

# ── Constants ──────────────────────────────────────────────────────────────────
STRATEGIES = {
    "Bull Call Spread":  "Buy lower-strike call, sell higher-strike call. Profits if price rises moderately.",
    "Bear Put Spread":   "Buy higher-strike put, sell lower-strike put. Profits if price falls moderately.",
    "Long Straddle":     "Buy ATM call + ATM put. Profits on large move in either direction.",
    "Short Straddle":    "Sell ATM call + ATM put. Profits if price stays near ATM until expiry.",
    "Long Strangle":     "Buy OTM call + OTM put. Cheaper than straddle; needs larger move.",
    "Short Strangle":    "Sell OTM call + OTM put. Profits in range-bound market; limited premium.",
    "Iron Condor":       "Sell OTM call spread + sell OTM put spread. Profits in low-volatility sideways market.",
    "Long Butterfly":    "Buy 1 ITM call, sell 2 ATM calls, buy 1 OTM call. Low cost, profits near ATM expiry.",
    "Covered Call":      "Own stock + sell OTM call. Generates income; caps upside.",
    "Protective Put":    "Own stock + buy ATM put. Insurance against downside.",
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _strategy    = st.selectbox("Strategy", list(STRATEGIES.keys()), key="ob_strat")
    _spot_input  = st.number_input("Current spot price (₹)", 100.0, 100_000.0, 24000.0, step=50.0, key="ob_spot")
    _dte         = st.slider("Days to expiry (DTE)", 1, 90, 21, key="ob_dte")
    _iv          = st.slider("Implied Volatility (%)", 5, 80, 15, key="ob_iv") / 100.0
    _strike_step = st.number_input("Strike step (₹)", 10.0, 500.0, 50.0, step=10.0, key="ob_step")
    _lots        = st.number_input("Lots", 1, 100, 1, key="ob_lots")
    _lot_size    = st.number_input("Lot size (shares)", 1, 1000, 50, key="ob_ls")

spot  = _spot_input
step  = _strike_step
T     = max(_dte, 1) / 365.0
sigma = _iv

# ── ATM and wing strikes ───────────────────────────────────────────────────────
atm   = int(round(spot / step) * step)
otm1  = atm + step
otm2  = atm + 2 * step
itm1  = atm - step
itm2  = atm - 2 * step


def _bs_price(K: float, otype: str) -> float:
    g = bs_greeks(spot, K, T, sigma, RISK_FREE_RATE, option_type=otype)
    return round(float(g.get("price", 0)), 2)


def _bs_delta(K: float, otype: str) -> float:
    g = bs_greeks(spot, K, T, sigma, RISK_FREE_RATE, option_type=otype)
    return round(float(g.get("delta", 0)), 4)


def _bs_theta(K: float, otype: str) -> float:
    g = bs_greeks(spot, K, T, sigma, RISK_FREE_RATE, option_type=otype)
    return round(float(g.get("theta", 0)), 4)


def _bs_vega(K: float, otype: str) -> float:
    g = bs_greeks(spot, K, T, sigma, RISK_FREE_RATE, option_type=otype)
    return round(float(g.get("vega", 0)), 4)


# ── Build legs ─────────────────────────────────────────────────────────────────
def _make_legs(strategy: str) -> list[dict]:
    """
    Returns a list of leg dicts: {strike, type (CE/PE), action (BUY/SELL), premium, qty}
    """
    if strategy == "Bull Call Spread":
        return [
            {"strike": atm,  "type": "CE", "action": "BUY",  "premium": _bs_price(atm,  "call"), "qty": 1},
            {"strike": otm1, "type": "CE", "action": "SELL", "premium": _bs_price(otm1, "call"), "qty": 1},
        ]
    if strategy == "Bear Put Spread":
        return [
            {"strike": atm,  "type": "PE", "action": "BUY",  "premium": _bs_price(atm,  "put"), "qty": 1},
            {"strike": itm1, "type": "PE", "action": "SELL", "premium": _bs_price(itm1, "put"), "qty": 1},
        ]
    if strategy == "Long Straddle":
        return [
            {"strike": atm, "type": "CE", "action": "BUY", "premium": _bs_price(atm, "call"), "qty": 1},
            {"strike": atm, "type": "PE", "action": "BUY", "premium": _bs_price(atm, "put"),  "qty": 1},
        ]
    if strategy == "Short Straddle":
        return [
            {"strike": atm, "type": "CE", "action": "SELL", "premium": _bs_price(atm, "call"), "qty": 1},
            {"strike": atm, "type": "PE", "action": "SELL", "premium": _bs_price(atm, "put"),  "qty": 1},
        ]
    if strategy == "Long Strangle":
        return [
            {"strike": otm1, "type": "CE", "action": "BUY", "premium": _bs_price(otm1, "call"), "qty": 1},
            {"strike": itm1, "type": "PE", "action": "BUY", "premium": _bs_price(itm1, "put"),  "qty": 1},
        ]
    if strategy == "Short Strangle":
        return [
            {"strike": otm1, "type": "CE", "action": "SELL", "premium": _bs_price(otm1, "call"), "qty": 1},
            {"strike": itm1, "type": "PE", "action": "SELL", "premium": _bs_price(itm1, "put"),  "qty": 1},
        ]
    if strategy == "Iron Condor":
        return [
            {"strike": otm2, "type": "CE", "action": "BUY",  "premium": _bs_price(otm2, "call"), "qty": 1},
            {"strike": otm1, "type": "CE", "action": "SELL", "premium": _bs_price(otm1, "call"), "qty": 1},
            {"strike": itm1, "type": "PE", "action": "SELL", "premium": _bs_price(itm1, "put"),  "qty": 1},
            {"strike": itm2, "type": "PE", "action": "BUY",  "premium": _bs_price(itm2, "put"),  "qty": 1},
        ]
    if strategy == "Long Butterfly":
        return [
            {"strike": itm1, "type": "CE", "action": "BUY",  "premium": _bs_price(itm1, "call"), "qty": 1},
            {"strike": atm,  "type": "CE", "action": "SELL", "premium": _bs_price(atm,  "call"), "qty": 2},
            {"strike": otm1, "type": "CE", "action": "BUY",  "premium": _bs_price(otm1, "call"), "qty": 1},
        ]
    if strategy == "Covered Call":
        return [
            {"strike": atm,  "type": "STOCK", "action": "BUY",  "premium": spot, "qty": 1},
            {"strike": otm1, "type": "CE",    "action": "SELL", "premium": _bs_price(otm1, "call"), "qty": 1},
        ]
    if strategy == "Protective Put":
        return [
            {"strike": atm,  "type": "STOCK", "action": "BUY", "premium": spot, "qty": 1},
            {"strike": itm1, "type": "PE",    "action": "BUY", "premium": _bs_price(itm1, "put"), "qty": 1},
        ]
    return []


legs = _make_legs(_strategy)

if not legs:
    st.error("Could not build strategy legs.")
    st.stop()

# ── Net premium ────────────────────────────────────────────────────────────────
def _net_premium(legs: list[dict]) -> float:
    total = 0.0
    for leg in legs:
        if leg["type"] == "STOCK":
            continue
        mult = -1 if leg["action"] == "SELL" else 1
        total += mult * leg["premium"] * leg["qty"]
    return total


net_prem = _net_premium(legs)
debit    = net_prem > 0
position_cost = abs(net_prem) * _lots * _lot_size

# ── Strategy info ──────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="background:rgba(96,165,250,0.06);border:1px solid rgba(96,165,250,0.15);'
    f'border-left:4px solid #60a5fa;border-radius:10px;padding:12px 18px;margin-bottom:20px;">'
    f'<div style="font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;">{_strategy}</div>'
    f'<div style="font-size:0.78rem;color:#6b7a99;">{STRATEGIES[_strategy]}</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Legs table ─────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Strategy Legs</div>',
    unsafe_allow_html=True,
)

_leg_rows = []
for leg in legs:
    if leg["type"] == "STOCK":
        _leg_rows.append({
            "Action": leg["action"], "Type": "STOCK", "Strike": "N/A",
            "Premium": f"₹{leg['premium']:,.2f}", "Qty": leg["qty"],
            "Net": f"−₹{leg['premium']:,.2f}" if leg["action"] == "BUY" else f"+₹{leg['premium']:,.2f}",
        })
        continue
    mult = -1 if leg["action"] == "SELL" else 1
    net  = mult * leg["premium"] * leg["qty"]
    _leg_rows.append({
        "Action":  leg["action"],
        "Type":    leg["type"],
        "Strike":  f"₹{leg['strike']:,}",
        "Premium": f"₹{leg['premium']:.2f}",
        "Qty":     leg["qty"],
        "Net":     f"+₹{abs(net):.2f}" if net > 0 else f"−₹{abs(net):.2f}",
    })

def _action_color(val):
    return "color: #00c896; font-weight: 700;" if val == "BUY" else "color: #ff4d6d; font-weight: 700;"

def _type_color(val):
    c = {"CE": "#60a5fa", "PE": "#f0b429", "STOCK": "#94a3b8"}
    return f"color: {c.get(val, '#94a3b8')}; font-weight: 600;"

st.dataframe(
    pd.DataFrame(_leg_rows).style
    .applymap(_action_color, subset=["Action"])
    .applymap(_type_color,   subset=["Type"]),
    use_container_width=True, hide_index=True,
)

# ── Summary metrics ────────────────────────────────────────────────────────────
def _payoff_at_expiry(S: float, legs: list[dict], lots: int, lot_size: int) -> float:
    pnl = 0.0
    for leg in legs:
        mult = -1 if leg["action"] == "SELL" else 1
        if leg["type"] == "CE":
            intrinsic = max(0.0, S - leg["strike"])
        elif leg["type"] == "PE":
            intrinsic = max(0.0, leg["strike"] - S)
        elif leg["type"] == "STOCK":
            intrinsic = S - leg["premium"]
        else:
            intrinsic = 0.0
        pnl += mult * (intrinsic - leg["premium"]) * leg["qty"] * lots * lot_size
    return pnl


_spot_range = np.linspace(spot * 0.8, spot * 1.2, 300)
_payoffs    = [_payoff_at_expiry(s, legs, _lots, _lot_size) for s in _spot_range]

_max_profit = max(_payoffs)
_max_loss   = min(_payoffs)

# Break-even points (sign changes)
_be_points = []
for i in range(len(_payoffs) - 1):
    if (_payoffs[i] < 0) != (_payoffs[i + 1] < 0):
        frac = -_payoffs[i] / (_payoffs[i + 1] - _payoffs[i])
        _be_points.append(round(_spot_range[i] + frac * (_spot_range[i + 1] - _spot_range[i]), 1))

st.markdown('<div style="margin-bottom:12px;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Strategy Summary</div>',
    unsafe_allow_html=True,
)

_sm = st.columns(5)
for _col, (_lbl, _val, _cc) in zip(_sm, [
    ("Net Premium",  f"{'Debit' if debit else 'Credit'} ₹{abs(net_prem):.2f}/share",
     "#ff4d6d" if debit else "#00c896"),
    ("Position Cost", f"₹{position_cost:,.0f}",
     "#94a3b8"),
    ("Max Profit",   f"₹{_max_profit:,.0f}" if _max_profit < 1e9 else "Unlimited",
     "#00c896"),
    ("Max Loss",     f"₹{abs(_max_loss):,.0f}" if _max_loss > -1e9 else "Unlimited",
     "#ff4d6d"),
    ("Break-even",
     " / ".join(f"₹{b:,.0f}" for b in _be_points[:3]) if _be_points else "N/A",
     "#f0b429"),
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

# ── Payoff diagram ─────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'Payoff at Expiry</div>',
    unsafe_allow_html=True,
)

_payoff_colors = ["#00c896" if p >= 0 else "#ff4d6d" for p in _payoffs]
_fig = go.Figure()

# Fill profit zone
_fig.add_trace(go.Scatter(
    x=list(_spot_range), y=[max(0, p) for p in _payoffs],
    fill="tozeroy", fillcolor="rgba(0,200,150,0.08)",
    line=dict(width=0), showlegend=False, hoverinfo="skip",
))
# Fill loss zone
_fig.add_trace(go.Scatter(
    x=list(_spot_range), y=[min(0, p) for p in _payoffs],
    fill="tozeroy", fillcolor="rgba(255,77,109,0.08)",
    line=dict(width=0), showlegend=False, hoverinfo="skip",
))
# Payoff line
_fig.add_trace(go.Scatter(
    x=list(_spot_range), y=_payoffs,
    mode="lines",
    line=dict(color="#e2e8f0", width=2.5),
    name="P&L at expiry",
    hovertemplate="Spot ₹%{x:,.0f}<br>P&L: ₹%{y:,.0f}<extra></extra>",
))

# Reference lines
_fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
_fig.add_vline(x=spot, line_color="#f0b429", line_width=1.5, line_dash="dash",
               annotation_text=f"Spot ₹{spot:,.0f}", annotation_font_color="#f0b429",
               annotation_font_size=9)
for be in _be_points[:3]:
    _fig.add_vline(x=be, line_color="rgba(240,180,41,0.4)", line_width=1, line_dash="dot",
                   annotation_text=f"BE ₹{be:,.0f}", annotation_font_color="#f0b429",
                   annotation_font_size=9)

_fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
    margin=dict(l=0, r=0, t=20, b=0), height=360,
    xaxis=dict(title="Spot at expiry (₹)", gridcolor="rgba(255,255,255,0.04)",
               tickfont=dict(size=9), tickformat=",.0f"),
    yaxis=dict(title="P&L (₹)", gridcolor="rgba(255,255,255,0.04)",
               tickfont=dict(size=9), tickformat=",.0f"),
    showlegend=False,
)
st.plotly_chart(_fig, use_container_width=True)

# ── Greeks summary ─────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:20px 0 8px;">'
    'Portfolio Greeks (per lot)</div>',
    unsafe_allow_html=True,
)

_net_delta = _net_theta = _net_vega = 0.0
for leg in legs:
    if leg["type"] == "STOCK":
        _net_delta += (1 if leg["action"] == "BUY" else -1) * leg["qty"]
        continue
    mult = -1 if leg["action"] == "SELL" else 1
    otype = "call" if leg["type"] == "CE" else "put"
    _net_delta += mult * _bs_delta(leg["strike"], otype) * leg["qty"]
    _net_theta += mult * _bs_theta(leg["strike"], otype) * leg["qty"]
    _net_vega  += mult * _bs_vega(leg["strike"], otype)  * leg["qty"]

_gc = st.columns(4)
for _col, (_lbl, _val, _cc, _sub) in zip(_gc, [
    ("Net Delta",
     f"{_net_delta:+.4f}",
     "#00c896" if _net_delta > 0 else "#ff4d6d" if _net_delta < 0 else "#94a3b8",
     "₹ P&L per ₹1 move"),
    ("Net Theta",
     f"{_net_theta:+.4f}",
     "#00c896" if _net_theta > 0 else "#ff4d6d",
     "₹/day time decay"),
    ("Net Vega",
     f"{_net_vega:+.4f}",
     "#00c896" if _net_vega > 0 else "#ff4d6d",
     "₹ P&L per 1% IV change"),
    ("IV (%)",
     f"{sigma*100:.1f}%",
     "#f0b429",
     f"DTE: {_dte} days"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:0.95rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'<div style="font-size:0.62rem;color:#374151;margin-top:3px;">{_sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── IV impact analysis ─────────────────────────────────────────────────────────
with st.expander("📊 IV Sensitivity — P&L if IV changes at current spot"):
    _iv_shifts = [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3]
    _iv_pnl = []
    for dv in _iv_shifts:
        new_iv = max(0.01, sigma + dv)
        _shifted_legs = []
        for leg in legs:
            if leg["type"] == "STOCK":
                _shifted_legs.append(leg)
                continue
            otype = "call" if leg["type"] == "CE" else "put"
            new_prem = float(bs_greeks(spot, leg["strike"], T, new_iv, RISK_FREE_RATE, otype).get("price", 0))
            mult = -1 if leg["action"] == "SELL" else 1
            _iv_pnl.append(mult * (new_prem - leg["premium"]) * leg["qty"] * _lots * _lot_size)

    _iv_labels = [f"{int(dv*100):+d}%" for dv in _iv_shifts]
    _cum_pnl   = []
    _per_shift = [0.0] * len(_iv_shifts)
    idx = 0
    for leg in legs:
        if leg["type"] == "STOCK":
            continue
        otype = "call" if leg["type"] == "CE" else "put"
        mult  = -1 if leg["action"] == "SELL" else 1
        for i, dv in enumerate(_iv_shifts):
            new_iv   = max(0.01, sigma + dv)
            new_prem = float(bs_greeks(spot, leg["strike"], T, new_iv, RISK_FREE_RATE, otype).get("price", 0))
            _per_shift[i] += mult * (new_prem - leg["premium"]) * leg["qty"] * _lots * _lot_size
        idx += 1

    _fig_iv = go.Figure(go.Bar(
        x=_iv_labels, y=_per_shift,
        marker_color=["#00c896" if v >= 0 else "#ff4d6d" for v in _per_shift],
        text=[f"₹{v:,.0f}" for v in _per_shift],
        textposition="outside",
        hovertemplate="IV shift %{x}<br>P&L: ₹%{y:,.0f}<extra></extra>",
    ))
    _fig_iv.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
    _fig_iv.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
        margin=dict(l=0, r=0, t=10, b=0), height=200,
        xaxis=dict(title="IV change", tickfont=dict(size=9)),
        yaxis=dict(title="P&L (₹)", tickfont=dict(size=9), tickformat=",.0f"),
        showlegend=False,
    )
    st.plotly_chart(_fig_iv, use_container_width=True)

st.caption(
    f"Strategy: {_strategy} · Spot: ₹{spot:,.0f} · DTE: {_dte} · IV: {sigma*100:.1f}% · "
    f"Premiums computed via Black-Scholes (RFR: {RISK_FREE_RATE*100:.1f}%)"
)
