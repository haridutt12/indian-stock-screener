"""NiftyEdge — AI Stock Analyst"""
import os
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from datetime import date

st.set_page_config(
    page_title="AI Stock Analyst · NiftyEdge",
    page_icon="🤖",
    layout="wide",
)

from ui.styles import inject_global_css, auth_guard, user_sidebar, render_ai_card
inject_global_css()
auth_guard()

with st.sidebar:
    user_sidebar()


# ── Technical helpers ──────────────────────────────────────────────

def _rsi(prices: pd.Series, n: int = 14) -> float:
    d = prices.diff().dropna()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    rs = g / l.replace(0, np.nan)
    v = (100 - 100 / (1 + rs)).iloc[-1]
    return float(v) if not np.isnan(v) else 50.0


def _macd(prices: pd.Series):
    e12 = prices.ewm(span=12, adjust=False).mean()
    e26 = prices.ewm(span=26, adjust=False).mean()
    m   = e12 - e26
    s   = m.ewm(span=9, adjust=False).mean()
    return float(m.iloc[-1]), float(s.iloc[-1])


@st.cache_data(ttl=300, show_spinner=False)
def _fetch(ticker_ns: str) -> dict:
    tk   = yf.Ticker(ticker_ns)
    hist = tk.history(period="1y", interval="1d", auto_adjust=True)
    if hist.empty or len(hist) < 50:
        raise ValueError("Insufficient price history")
    c, v = hist["Close"], hist["Volume"]
    p    = float(c.iloc[-1])

    sma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    v_avg  = float(v.iloc[:-1].tail(20).mean()) or 1
    vol_r  = float(v.iloc[-1]) / v_avg

    pe, mcap_cr, sector = None, None, None
    try:
        info    = tk.info
        pe_raw  = info.get("trailingPE") or info.get("forwardPE")
        pe      = round(float(pe_raw), 1) if pe_raw else None
        mc      = info.get("marketCap")
        mcap_cr = round(mc / 1e7) if mc else None
        sector  = info.get("sector") or info.get("industry")
    except Exception:
        pass

    macd_v, macd_s = _macd(c)
    return dict(
        price=p,
        chg_1d  =(p / float(c.iloc[-2]) - 1) * 100 if len(c) >= 2  else 0,
        chg_5d  =(p / float(c.iloc[-6]) - 1) * 100 if len(c) >= 6  else 0,
        chg_1m  =(p / float(c.iloc[-22])- 1) * 100 if len(c) >= 22 else 0,
        chg_ytd =(p / float(c.iloc[0])  - 1) * 100,
        high_52w=float(c.max()), low_52w=float(c.min()),
        pct_from_high=(p / float(c.max()) - 1) * 100,
        pct_from_low =(p / float(c.min()) - 1) * 100,
        rsi=_rsi(c), macd=macd_v, macd_sig=macd_s,
        sma50 =float(c.rolling(50).mean().iloc[-1]),
        sma200=sma200,
        pct_vs_sma50 =(p / float(c.rolling(50).mean().iloc[-1]) - 1) * 100,
        pct_vs_sma200=(p / sma200 - 1) * 100 if sma200 else None,
        vol_ratio=vol_r, pe=pe, mcap_cr=mcap_cr, sector=sector,
    )


def _build_prompt(name: str, d: dict) -> str:
    fund = []
    if d["pe"]:      fund.append(f"- P/E: {d['pe']}")
    if d["mcap_cr"]: fund.append(f"- Market Cap: ₹{d['mcap_cr']:,} Cr")
    if d["sector"]:  fund.append(f"- Sector: {d['sector']}")
    sma200_line = (
        f"- SMA 200: ₹{d['sma200']:,.0f} | vs SMA200: {d['pct_vs_sma200']:+.1f}%"
        if d["sma200"] else "- SMA 200: Insufficient data (< 200 days)"
    )
    rsi_tag   = "overbought" if d["rsi"] > 70 else "oversold" if d["rsi"] < 30 else "neutral zone"
    macd_bias = "bullish crossover" if d["macd"] > d["macd_sig"] else "bearish crossover"

    return f"""You are a senior equity research analyst specialising in Indian markets (NSE/BSE).
Analyse the data below and produce a structured trade analysis for a retail investor.

Stock: {name} | Date: {date.today():%d %b %Y}
Current Price: ₹{d['price']:,.2f}

52-Week Range: Low ₹{d['low_52w']:,.0f} ── High ₹{d['high_52w']:,.0f}
  From low: {d['pct_from_low']:+.1f}% | From high: {d['pct_from_high']:+.1f}%

Returns: 1D {d['chg_1d']:+.2f}% | 5D {d['chg_5d']:+.2f}% | 1M {d['chg_1m']:+.2f}% | YTD {d['chg_ytd']:+.2f}%

Technical Indicators:
- RSI (14): {d['rsi']:.1f} ({rsi_tag})
- MACD: {d['macd']:+.4f} vs Signal {d['macd_sig']:+.4f} → {macd_bias}
- SMA 50: ₹{d['sma50']:,.0f} | vs SMA50: {d['pct_vs_sma50']:+.1f}%
{sma200_line}
- Volume: {d['vol_ratio']:.1f}× 20-day average

Fundamentals:
{chr(10).join(fund) if fund else "- Unavailable from data source"}

Respond with this exact structure (markdown):

## Overall Verdict
**STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL** — one sentence explaining why, referencing the actual data.

## Trend Analysis
Describe the current trend, momentum, and what the confluence of indicators says. Be specific with the numbers.

## Key Levels
- **Immediate Support:** ₹X (reason)
- **Immediate Resistance:** ₹X (reason)
- **Strong Support:** ₹X
- **Strong Resistance:** ₹X

## Trade Setup
| | |
|---|---|
| Entry Zone | ₹X – ₹Y |
| Stop Loss | ₹X (X% below entry) |
| Target 1 | ₹X (R:R X:1) |
| Target 2 | ₹X (R:R X:1) |
| Timeframe | X days / X weeks |

If the setup is not currently actionable, explain what condition to wait for instead.

## Risk Factors
2–3 specific risks with price levels that would invalidate this view.

## Plain-English Summary
2 sentences. Tell a first-time investor exactly what this stock is doing right now and what to do about it.

Use specific numbers from the data. Do not add generic disclaimers about seeking professional advice."""


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


# ── Page ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="margin-bottom:4px;">'
    '<span style="font-size:1.55rem;font-weight:900;color:#f1f5f9;letter-spacing:-0.03em;">'
    '🤖 AI Stock Analyst</span></div>'
    '<div style="font-size:0.8rem;color:#64748b;margin-bottom:16px;">'
    'Instant AI trade analysis — trend, key levels, entry/SL/target &amp; risk factors '
    'for any Nifty 50/200 stock.</div>'
    '<div style="display:flex;gap:8px;margin-bottom:24px;">'
    '<a href="/AI_Analyst" style="flex:1;text-align:center;padding:9px 16px;'
    'background:#8b5cf6;color:#fff;border-radius:8px;text-decoration:none;'
    'font-weight:700;font-size:0.78rem;letter-spacing:0.03em;">🤖 AI Stock Analyst</a>'
    '<a href="/Portfolio_Health" style="flex:1;text-align:center;padding:9px 16px;'
    'background:rgba(255,255,255,0.05);color:#64748b;border-radius:8px;'
    'text-decoration:none;font-weight:700;font-size:0.78rem;letter-spacing:0.03em;'
    'border:1px solid rgba(255,255,255,0.07);">📊 Portfolio Health</a>'
    '</div>',
    unsafe_allow_html=True,
)

uni = _universe()
if not uni:
    st.error("Stock universe unavailable.")
    st.stop()

ic, bc = st.columns([5, 1])
with ic:
    chosen = st.selectbox("Stock", sorted(uni.keys()), label_visibility="collapsed")
with bc:
    go = st.button("Analyse →", type="primary", use_container_width=True)

if go and chosen:
    ticker_ns = uni[chosen]
    if not ticker_ns.endswith(".NS"):
        ticker_ns += ".NS"

    api_key = (os.environ.get("GROQ_API_KEY") or
               st.secrets.get("GROQ_API_KEY", ""))
    if not api_key:
        st.error("GROQ_API_KEY not set — add it to Streamlit Cloud → App Settings → Secrets. Get a free key at console.groq.com")
        st.stop()

    with st.spinner(f"Fetching data for {chosen}…"):
        try:
            d = _fetch(ticker_ns)
        except Exception as exc:
            st.error(f"Could not fetch data: {exc}")
            st.stop()

    # ── Metrics strip ────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1d_c = "#00c896" if d["chg_1d"] >= 0 else "#ff4d6d"
    rsi_c = "#ff4d6d" if d["rsi"] > 70 else "#00c896" if d["rsi"] < 30 else "#f0b429"
    s50_c = "#00c896" if d["pct_vs_sma50"] >= 0 else "#ff4d6d"
    vol_c = "#f0b429" if d["vol_ratio"] > 1.5 else "#64748b"
    h52_c = "#ff4d6d" if d["pct_from_high"] < -20 else "#f0b429" if d["pct_from_high"] < -10 else "#00c896"

    for col, lbl, val, sub, clr in [
        (c1, "Price",     f"₹{d['price']:,.1f}",         f"{'▲' if d['chg_1d']>=0 else '▼'} {abs(d['chg_1d']):.2f}% today", c1d_c),
        (c2, "RSI (14)",  f"{d['rsi']:.0f}",             "Overbought" if d["rsi"]>70 else "Oversold" if d["rsi"]<30 else "Neutral", rsi_c),
        (c3, "vs SMA 50", f"{d['pct_vs_sma50']:+.1f}%",  f"SMA50 ₹{d['sma50']:,.0f}", s50_c),
        (c4, "Volume",    f"{d['vol_ratio']:.1f}×",      "vs 20-day avg", vol_c),
        (c5, "52W High",  f"{d['pct_from_high']:+.1f}%", f"High ₹{d['high_52w']:,.0f}", h52_c),
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

    st.markdown(
        '<div style="margin:16px 0 12px;border-top:1px solid rgba(255,255,255,0.06);"></div>'
        '<div style="font-size:0.65rem;font-weight:700;color:#8b5cf6;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">🤖 AI Analysis</div>',
        unsafe_allow_html=True,
    )

    from groq import Groq
    client = Groq(api_key=api_key)
    prompt_text = _build_prompt(chosen, d)

    try:
        with st.spinner("Generating analysis…"):
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt_text}],
            )
        render_ai_card(response.choices[0].message.content, accent="#8b5cf6")
    except Exception as exc:
        st.error(f"AI analysis failed: {exc}")
