"""NiftyEdge — AI Portfolio Health Check"""
import os
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from datetime import date

st.set_page_config(
    page_title="Portfolio Health · NiftyEdge",
    page_icon="📊",
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
    '📊 Portfolio Health Check</span></div>'
    '<div style="font-size:0.8rem;color:#64748b;margin-bottom:16px;">'
    'Enter your holdings and get AI feedback — sector concentration, '
    'positions at risk &amp; a plain-English verdict on what to do next.</div>'
    '<div style="display:flex;gap:8px;margin-bottom:24px;">'
    '<a href="/AI_Analyst" style="flex:1;text-align:center;padding:9px 16px;'
    'background:rgba(255,255,255,0.05);color:#64748b;border-radius:8px;'
    'text-decoration:none;font-weight:700;font-size:0.78rem;letter-spacing:0.03em;'
    'border:1px solid rgba(255,255,255,0.07);">🤖 AI Stock Analyst</a>'
    '<a href="/Portfolio_Health" style="flex:1;text-align:center;padding:9px 16px;'
    'background:#22c55e;color:#fff;border-radius:8px;text-decoration:none;'
    'font-weight:700;font-size:0.78rem;letter-spacing:0.03em;">📊 Portfolio Health</a>'
    '</div>',
    unsafe_allow_html=True,
)

uni = _universe()
if not uni:
    st.error("Stock universe unavailable.")
    st.stop()

if "portfolio" not in st.session_state:
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

# ── Remove positions ─────────────────────────────────────────────────────────────
with st.expander("\U0001f5d1️ Remove Positions"):
    to_remove = st.multiselect("Select stocks to remove",
                               [h["name"] for h in holdings],
                               key="ph_remove")
    if st.button("Remove Selected", disabled=not to_remove):
        st.session_state["portfolio"] = [
            h for h in holdings if h["name"] not in to_remove
        ]
        st.rerun()

st.markdown(
    '<div style="margin:16px 0 12px;border-top:1px solid rgba(255,255,255,0.06);"></div>'
    '<div style="font-size:0.65rem;font-weight:700;color:#22c55e;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">🤖 AI Analysis</div>',
    unsafe_allow_html=True,
)

run_btn = st.button("🤖 Run AI Portfolio Analysis", type="primary")

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
        with st.spinner("Generating analysis…"):
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt_text}],
            )
        render_ai_card(response.choices[0].message.content, accent="#22c55e")
    except Exception as exc:
        st.error(f"AI analysis failed: {exc}")
