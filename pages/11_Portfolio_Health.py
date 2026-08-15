"""NiftyEdge — AI Portfolio Health Check"""
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from datetime import date, datetime, timedelta

st.set_page_config(
    page_title="Portfolio Health · NiftyEdge",
    page_icon="\U0001f4ca",
    layout="wide",
)

from ui.styles import inject_global_css, auth_guard, user_sidebar, render_ai_card
inject_global_css()
auth_guard()

with st.sidebar:
    user_sidebar()


# ── Sector fallback map ─────────────────────────────────────────────────────

_SECTOR = {
    "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Utilities",
    "POWERGRID": "Utilities", "COALINDIA": "Materials",
    "TCS": "Technology", "INFY": "Technology", "WIPRO": "Technology",
    "HCLTECH": "Technology", "TECHM": "Technology",
    "HDFCBANK": "Financials", "ICICIBANK": "Financials", "SBIN": "Financials",
    "KOTAKBANK": "Financials", "AXISBANK": "Financials",
    "BAJFINANCE": "Financials", "BAJAJFINSV": "Financials",
    "HINDUNILVR": "Consumer Staples", "ITC": "Consumer Staples",
    "NESTLEIND": "Consumer Staples", "BRITANNIA": "Consumer Staples",
    "MARUTI": "Consumer Discretionary", "TITAN": "Consumer Discretionary",
    "TATACONSUM": "Consumer Staples", "TATAMOTORS": "Consumer Discretionary",
    "M&M": "Consumer Discretionary", "HEROMOTOCO": "Consumer Discretionary",
    "EICHERMOT": "Consumer Discretionary",
    "ASIANPAINT": "Materials", "ULTRACEMCO": "Materials", "GRASIM": "Materials",
    "JSWSTEEL": "Materials", "TATASTEEL": "Materials", "HINDALCO": "Materials",
    "LT": "Industrials", "ADANIPORTS": "Industrials",
    "SUNPHARMA": "Healthcare", "DRREDDY": "Healthcare", "CIPLA": "Healthcare",
    "DIVISLAB": "Healthcare", "APOLLOHOSP": "Healthcare",
    "BHARTIARTL": "Communication", "INDUSINDBK": "Financials",
    "BPCL": "Energy", "SHREECEM": "Materials", "BAJAJ-AUTO": "Consumer Discretionary",
    "SBILIFE": "Financials", "HDFCLIFE": "Financials", "LTIM": "Technology",
}


# ── Cached helpers ──────────────────────────────────────────────────────────

@st.cache_resource
def _universe():
    stocks = {}
    try:
        from config.stock_universe import NIFTY_50
        stocks.update(NIFTY_50)
    except Exception:
        pass
    try:
        from config.stock_universe import NIFTY_200
        stocks.update(NIFTY_200)
    except Exception:
        pass
    return stocks


@st.cache_data(ttl=300, show_spinner=False)
def _price_data(ticker_ns: str) -> dict:
    tk   = yf.Ticker(ticker_ns)
    hist = tk.history(period="1y", interval="1d", auto_adjust=True)
    if hist.empty or len(hist) < 5:
        raise ValueError("No price data")
    c   = hist["Close"]
    p   = float(c.iloc[-1])
    sma50 = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else None
    sma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    chg_1m = (p / float(c.iloc[-22]) - 1) * 100 if len(c) >= 22 else 0.0
    high_52w = float(c.max())
    pct_from_high = (p / high_52w - 1) * 100

    sector = _SECTOR.get(ticker_ns.replace(".NS", ""))
    if not sector:
        try:
            info   = tk.info
            sector = info.get("sector") or info.get("industry") or "Unknown"
        except Exception:
            sector = "Unknown"

    return dict(
        price=p, sma50=sma50, sma200=sma200,
        chg_1m=chg_1m, high_52w=high_52w,
        pct_from_high=pct_from_high, sector=sector,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _risk_metrics(tickers_tuple: tuple, weights_tuple: tuple) -> dict:
    """Compute portfolio beta and max drawdown from 1-year daily prices."""
    tickers = list(tickers_tuple)
    weights = list(weights_tuple)
    try:
        all_tickers = tickers + ["^NSEI"]
        raw = yf.download(all_tickers, period="1y", interval="1d",
                          auto_adjust=True, progress=False)["Close"]
        raw = raw.dropna(how="all")
        if raw.empty:
            return {}

        # Portfolio daily value series
        port_val = None
        for tkr, wt in zip(tickers, weights):
            col = tkr if tkr in raw.columns else None
            if col is None:
                continue
            series = raw[col].dropna()
            if series.empty:
                continue
            normalised = wt * (series / series.iloc[0])
            port_val = normalised if port_val is None else port_val.add(normalised, fill_value=0)

        if port_val is None or port_val.empty:
            return {}

        # Max Drawdown
        roll_max = port_val.cummax()
        drawdown = (port_val - roll_max) / roll_max
        max_dd = float(drawdown.min()) * 100

        # Beta vs Nifty
        nifty_col = "^NSEI" if "^NSEI" in raw.columns else None
        beta = None
        if nifty_col:
            port_ret  = port_val.pct_change().dropna()
            nifty_ret = raw[nifty_col].pct_change().dropna()
            aligned   = pd.concat([port_ret, nifty_ret], axis=1).dropna()
            if len(aligned) > 20:
                cov   = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
                var_n = aligned.iloc[:, 1].var()
                beta  = round(cov / var_n, 2) if var_n else None

        return {"max_drawdown_pct": round(max_dd, 2), "beta": beta}
    except Exception:
        return {}


# ── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(holdings: list, prices: dict) -> str:
    rows = []
    total_invested = 0.0
    total_current  = 0.0
    sector_alloc: dict[str, float] = {}

    for h in holdings:
        name  = h["name"]
        qty   = h["qty"]
        avg   = h["avg_price"]
        pd_   = prices.get(name, {})
        curr  = pd_.get("price", avg)
        inv   = qty * avg
        cur   = qty * curr
        pnl   = cur - inv
        pnl_p = (pnl / inv) * 100 if inv else 0
        sec   = pd_.get("sector", "Unknown")
        sma50 = pd_.get("sma50")
        sma200= pd_.get("sma200")
        chg1m = pd_.get("chg_1m", 0)
        pfh   = pd_.get("pct_from_high", 0)

        sma_note = ""
        if sma50:
            rel = (curr / sma50 - 1) * 100
            sma_note += f" vs SMA50: {rel:+.1f}%"
        if sma200:
            rel = (curr / sma200 - 1) * 100
            sma_note += f" vs SMA200: {rel:+.1f}%"

        rows.append(
            f"- {name}: ₹{curr:,.0f} | Qty {qty} | Avg ₹{avg:,.0f} | "
            f"P&L ₹{pnl:+,.0f} ({pnl_p:+.1f}%) | Sector: {sec} | "
            f"1M: {chg1m:+.1f}% | From 52W high: {pfh:+.1f}%{sma_note}"
        )
        total_invested += inv
        total_current  += cur
        sector_alloc[sec] = sector_alloc.get(sec, 0) + cur

    total_pnl   = total_current - total_invested
    total_pnl_p = (total_pnl / total_invested * 100) if total_invested else 0

    sector_lines = []
    for sec, val in sorted(sector_alloc.items(), key=lambda x: -x[1]):
        pct = val / total_current * 100 if total_current else 0
        sector_lines.append(f"  - {sec}: {pct:.1f}% (₹{val:,.0f})")

    return f"""You are a senior portfolio manager specialising in Indian equity markets.
Analyse the portfolio below and provide a structured health check for a retail investor.

Date: {date.today():%d %b %Y}
Total Invested: ₹{total_invested:,.0f}
Current Value:  ₹{total_current:,.0f}
Total P&L:      ₹{total_pnl:+,.0f} ({total_pnl_p:+.1f}%)

Holdings ({len(holdings)} positions):
{chr(10).join(rows)}

Sector Allocation:
{chr(10).join(sector_lines)}

Respond with this exact structure (markdown):

## Portfolio Health Score
**X / 10** — one sentence explaining the overall health, citing diversification and P&L.

## Concentration Risk
Identify sectors or individual stocks that are over-weighted (>25% in one sector or >15% in one stock). Flag if the portfolio is too narrow or correlated. Be specific with percentages.

## Positions Requiring Attention
For each position that is: (a) below its SMA 50 or SMA 200, (b) down more than 10% from 52W high, or (c) showing negative 1M momentum — give a one-line note on what to watch for.

## What's Working
Highlight 1–2 positions with strong momentum or good P&L. Keep it short.

## Suggested Actions
3–4 concrete, actionable suggestions (e.g. trim X, add Y on dip, set SL at ₹Z for W). Reference actual numbers.

## Plain-English Summary
2 sentences. Tell a first-time investor how healthy this portfolio is right now and the single most important thing to do.

Use specific numbers from the data. Do not add generic disclaimers about seeking professional advice."""


# ── Page ───────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="margin-bottom:4px;">'
    '<span style="font-size:1.55rem;font-weight:900;color:#f1f5f9;letter-spacing:-0.03em;">'
    '\U0001f4ca Portfolio Health Check</span></div>'
    '<div style="font-size:0.8rem;color:#64748b;margin-bottom:16px;">'
    'Enter your holdings and get AI feedback — sector concentration, '
    'positions at risk &amp; a plain-English verdict on what to do next.</div>'
    '<div style="display:flex;gap:8px;margin-bottom:24px;">'
    '<a href="/AI_Analyst" style="flex:1;text-align:center;padding:9px 16px;'
    'background:rgba(255,255,255,0.05);color:#64748b;border-radius:8px;'
    'text-decoration:none;font-weight:700;font-size:0.78rem;letter-spacing:0.03em;'
    'border:1px solid rgba(255,255,255,0.07);">\U0001f916 AI Stock Analyst</a>'
    '<a href="/Portfolio_Health" style="flex:1;text-align:center;padding:9px 16px;'
    'background:#22c55e;color:#fff;border-radius:8px;text-decoration:none;'
    'font-weight:700;font-size:0.78rem;letter-spacing:0.03em;">\U0001f4ca Portfolio Health</a>'
    '</div>',
    unsafe_allow_html=True,
)

uni = _universe()
if not uni:
    st.error("Stock universe unavailable.")
    st.stop()


def _portfolio_key() -> str:
    try:
        if st.user.is_logged_in:
            return st.user.email or "guest"
    except Exception:
        pass
    return "guest"


def _save_portfolio(holdings: list) -> None:
    try:
        from signals.signal_logger import get_signal_logger
        get_signal_logger().save_portfolio(_portfolio_key(), holdings)
    except Exception:
        pass


if "portfolio" not in st.session_state:
    try:
        from signals.signal_logger import get_signal_logger
        st.session_state["portfolio"] = get_signal_logger().load_portfolio(_portfolio_key())
    except Exception:
        st.session_state["portfolio"] = []

# ── Add position form ──────────────────────────────────────────────────────────────
with st.expander("➕ Add Position", expanded=not st.session_state["portfolio"]):
    fa, fb, fc, fd = st.columns([4, 1, 2, 1])
    with fa:
        sel_name = st.selectbox("Stock", sorted(uni.keys()), key="ph_stock",
                                label_visibility="collapsed")
    with fb:
        qty = st.number_input("Qty", min_value=1, value=1, step=1, key="ph_qty",
                              label_visibility="collapsed")
    with fc:
        avg_price = st.number_input("Avg Price (₹)", min_value=0.01, value=100.0,
                                    step=0.5, format="%.2f", key="ph_avg",
                                    label_visibility="collapsed")
    with fd:
        add_btn = st.button("Add", type="primary", use_container_width=True)

    if add_btn:
        ticker_ns = uni[sel_name]
        if not ticker_ns.endswith(".NS"):
            ticker_ns += ".NS"
        existing = [h["name"] for h in st.session_state["portfolio"]]
        if sel_name in existing:
            st.warning(f"{sel_name} is already in your portfolio. Remove it first to update.")
        else:
            st.session_state["portfolio"].append(
                {"name": sel_name, "ticker": ticker_ns, "qty": int(qty), "avg_price": float(avg_price)}
            )
            _save_portfolio(st.session_state["portfolio"])
            st.rerun()

holdings = st.session_state["portfolio"]

if not holdings:
    st.info("Add at least one position above to get started.")
    st.stop()

# ── Fetch live prices ───────────────────────────────────────────────────────────
prices = {}
failed = []
with st.spinner("Fetching live prices…"):
    for h in holdings:
        try:
            prices[h["name"]] = _price_data(h["ticker"])
        except Exception:
            failed.append(h["name"])
            prices[h["name"]] = {"price": h["avg_price"], "sector": "Unknown",
                                  "sma50": None, "sma200": None,
                                  "chg_1m": 0.0, "pct_from_high": 0.0}

if failed:
    st.warning(f"Could not fetch live price for: {', '.join(failed)}. Using avg price.")

# ── Summary metrics ─────────────────────────────────────────────────────────────
total_inv = sum(h["qty"] * h["avg_price"] for h in holdings)
total_cur = sum(h["qty"] * prices[h["name"]]["price"] for h in holdings)
total_pnl = total_cur - total_inv
total_pnl_p = (total_pnl / total_inv * 100) if total_inv else 0

pnl_color = "#00c896" if total_pnl >= 0 else "#ff4d6d"

m1, m2, m3, m4 = st.columns(4)
for col, lbl, val, sub, clr in [
    (m1, "Invested",      f"₹{total_inv:,.0f}",  f"{len(holdings)} position{'s' if len(holdings)!=1 else ''}", "#f1f5f9"),
    (m2, "Current Value", f"₹{total_cur:,.0f}",  "Live prices",                                               "#f1f5f9"),
    (m3, "Total P&L",     f"₹{total_pnl:+,.0f}", f"{total_pnl_p:+.2f}%",                                     pnl_color),
    (m4, "Return",        f"{total_pnl_p:+.2f}%","vs cost basis",                                             pnl_color),
]:
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px 16px;">'
            f'<div style="font-size:0.58rem;color:#475569;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;">{lbl}</div>'
            f'<div style="font-size:1.25rem;font-weight:800;color:{clr};margin:4px 0 2px;">{val}</div>'
            f'<div style="font-size:0.65rem;color:#374151;">{sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin:16px 0 8px;"></div>', unsafe_allow_html=True)

# ── Holdings table ─────────────────────────────────────────────────────────────────
rows = []
for h in holdings:
    pd_  = prices[h["name"]]
    curr = pd_["price"]
    inv  = h["qty"] * h["avg_price"]
    cur  = h["qty"] * curr
    pnl  = cur - inv
    pnl_p = (pnl / inv * 100) if inv else 0
    rows.append({
        "Stock":      h["name"],
        "Qty":        h["qty"],
        "Avg (₹)":    round(h["avg_price"], 2),
        "CMP (₹)":    round(curr, 2),
        "Value (₹)":  round(cur, 0),
        "P&L (₹)":    round(pnl, 0),
        "P&L %":      round(pnl_p, 2),
        "Sector":     pd_["sector"],
        "1M %":       round(pd_["chg_1m"], 2),
        "From 52W H": round(pd_["pct_from_high"], 2),
    })

df = pd.DataFrame(rows)
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "P&L %":      st.column_config.NumberColumn(format="%.2f %%"),
        "1M %":       st.column_config.NumberColumn(format="%.2f %%"),
        "From 52W H": st.column_config.NumberColumn(format="%.2f %%"),
    },
)
st.download_button(
    "⬇ Export Holdings CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name=f"portfolio_{date.today().isoformat()}.csv",
    mime="text/csv",
)

# ── Edit positions ─────────────────────────────────────────────────────────────
with st.expander("✏️ Edit Positions"):
    for _h in holdings:
        _ec1, _ec2, _ec3, _ec4 = st.columns([3, 1.2, 2, 1])
        with _ec1:
            st.markdown(
                f'<div style="padding-top:6px;font-size:0.88rem;font-weight:600;color:#e2e8f0;">{_h["name"]}</div>',
                unsafe_allow_html=True,
            )
        with _ec2:
            _new_qty = st.number_input("Qty", value=_h["qty"], min_value=1, step=1,
                                       key=f"eq_{_h['name']}", label_visibility="collapsed")
        with _ec3:
            _new_avg = st.number_input("Avg Price (₹)", value=float(_h["avg_price"]),
                                       min_value=0.01, format="%.2f",
                                       key=f"ea_{_h['name']}", label_visibility="collapsed")
        with _ec4:
            if st.button("Update", key=f"eu_{_h['name']}", use_container_width=True):
                _h["qty"] = int(_new_qty)
                _h["avg_price"] = float(_new_avg)
                _save_portfolio(st.session_state["portfolio"])
                st.rerun()

# ── Remove positions ─────────────────────────────────────────────────────────────
with st.expander("\U0001f5d1️ Remove Positions"):
    to_remove = st.multiselect("Select stocks to remove",
                               [h["name"] for h in holdings],
                               key="ph_remove")
    if st.button("Remove Selected", disabled=not to_remove):
        st.session_state["portfolio"] = [
            h for h in holdings if h["name"] not in to_remove
        ]
        _save_portfolio(st.session_state["portfolio"])
        st.rerun()

# ── Sector Allocation + Risk Metrics ──────────────────────────────────────────
st.markdown('<div style="margin:20px 0 10px;border-top:1px solid rgba(255,255,255,0.06);"></div>', unsafe_allow_html=True)

_ch1, _ch2 = st.columns([1, 1])

with _ch1:
    # Sector allocation donut
    _sector_vals: dict[str, float] = {}
    for _hr in holdings:
        _pd = prices[_hr["name"]]
        _sec = _pd.get("sector") or "Unknown"
        _val = _hr["qty"] * _pd.get("price", _hr["avg_price"])
        _sector_vals[_sec] = _sector_vals.get(_sec, 0) + _val

    _sec_labels = list(_sector_vals.keys())
    _sec_values = [_sector_vals[s] for s in _sec_labels]
    _sec_colors = [
        "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
        "#06b6d4", "#f97316", "#ec4899", "#10b981", "#6366f1",
    ]

    _donut_fig = go.Figure(go.Pie(
        labels=_sec_labels,
        values=_sec_values,
        hole=0.55,
        marker=dict(colors=_sec_colors[:len(_sec_labels)], line=dict(color="#0f172a", width=2)),
        textinfo="label+percent",
        textfont=dict(size=10, color="#e2e8f0"),
        hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    _top_sec = max(_sector_vals, key=_sector_vals.get) if _sector_vals else ""
    _top_pct = _sector_vals.get(_top_sec, 0) / total_cur * 100 if total_cur else 0
    _donut_fig.add_annotation(
        text=f"<b>{_top_sec}</b><br>{_top_pct:.0f}%",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=11, color="#f1f5f9"),
        xanchor="center",
    )
    _donut_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=28, b=0), height=280,
        title=dict(text="Sector Allocation", font=dict(color="#94a3b8", size=12)),
        showlegend=False,
    )
    st.plotly_chart(_donut_fig, use_container_width=True)

with _ch2:
    # Risk metrics: Beta + Max Drawdown
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:700;color:#94a3b8;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;">Risk Metrics</div>',
        unsafe_allow_html=True,
    )
    with st.spinner("Computing risk metrics…"):
        _tickers_tuple = tuple(h["ticker"] for h in holdings)
        _weights_tuple = tuple(
            h["qty"] * prices[h["name"]].get("price", h["avg_price"])
            for h in holdings
        )
        _w_total = sum(_weights_tuple) or 1.0
        _weights_norm = tuple(w / _w_total for w in _weights_tuple)
        _risk = _risk_metrics(_tickers_tuple, _weights_norm)

    _beta = _risk.get("beta")
    _mdd  = _risk.get("max_drawdown_pct")
    _concentration = max(_sector_vals.values()) / total_cur * 100 if total_cur else 0
    _top_stock_pct = (
        max(h["qty"] * prices[h["name"]].get("price", h["avg_price"])
            for h in holdings) / total_cur * 100
        if holdings and total_cur else 0
    )

    for _lbl, _val, _sub, _clr in [
        ("Portfolio Beta",
         f"{_beta:.2f}" if _beta is not None else "—",
         "vs Nifty 50 (1Y)",
         "#f0b429" if _beta is not None and _beta > 1.3 else "#00c896"),
        ("Max Drawdown",
         f"{_mdd:.1f}%" if _mdd is not None else "—",
         "Worst peak-to-trough (1Y)",
         "#ff4d6d" if _mdd is not None and _mdd < -20 else "#f0b429" if _mdd is not None and _mdd < -10 else "#00c896"),
        ("Top Sector",
         f"{_top_pct:.0f}%",
         _top_sec,
         "#ff4d6d" if _top_pct > 40 else "#f0b429" if _top_pct > 25 else "#00c896"),
        ("Largest Position",
         f"{_top_stock_pct:.0f}%",
         "of portfolio value",
         "#ff4d6d" if _top_stock_pct > 20 else "#f0b429" if _top_stock_pct > 15 else "#00c896"),
    ]:
        st.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border-radius:10px;'
            f'padding:10px 14px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.06);">'
            f'<div style="font-size:0.6rem;color:#475569;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;">{_lbl}</div>'
            f'<div style="font-size:1.15rem;font-weight:800;color:{_clr};margin:2px 0 1px;">{_val}</div>'
            f'<div style="font-size:0.6rem;color:#374151;">{_sub}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin:16px 0 12px;border-top:1px solid rgba(255,255,255,0.06);"></div>', unsafe_allow_html=True)

st.markdown(
    '<div style="font-size:0.65rem;font-weight:700;color:#22c55e;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">\U0001f916 AI Analysis</div>',
    unsafe_allow_html=True,
)

_ai_col1, _ai_col2 = st.columns([3, 1])
with _ai_col1:
    run_btn = st.button("\U0001f916 Run AI Portfolio Analysis", type="primary")
with _ai_col2:
    if st.button("🗑 Clear Cache", help="Re-run analysis fresh"):
        st.session_state.pop("_portfolio_ai_result", None)
        st.rerun()

if st.session_state.get("_portfolio_ai_result"):
    render_ai_card(st.session_state["_portfolio_ai_result"], accent="#22c55e")

if run_btn:
    api_key = (os.environ.get("GROQ_API_KEY") or
               st.secrets.get("GROQ_API_KEY", ""))
    if not api_key:
        st.error("GROQ_API_KEY not set — add it to Streamlit Cloud → App Settings → Secrets. Get a free key at console.groq.com")
        st.stop()

    from groq import Groq
    client = Groq(api_key=api_key)
    prompt_text = _build_prompt(holdings, prices)

    try:
        stream = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt_text}],
            stream=True,
        )
        _ai_placeholder = st.empty()
        _full_text = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            _full_text += delta
            _ai_placeholder.markdown(
                f'<div style="background:linear-gradient(145deg,#0d1b2a,#0a1628);'
                f'border:1px solid rgba(34,197,94,0.25);border-radius:14px;'
                f'padding:20px 24px;margin-top:8px;font-size:0.88rem;color:#e2e8f0;'
                f'line-height:1.7;">{_full_text.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )
        _ai_placeholder.empty()
        st.session_state["_portfolio_ai_result"] = _full_text
        render_ai_card(_full_text, accent="#22c55e")
    except Exception as exc:
        st.error(f"AI analysis failed: {exc}")
