"""
Page 4: Technical Screener
- Filter by RSI, MACD, trend, volume, moving averages
- Preset buttons: Oversold, Breakout, Golden Cross
- Results with mini trend summaries
"""
import streamlit as st
import pandas as pd
from data.fetcher import fetch_stock_data
from analysis.technical import compute_indicators, get_technical_summary, detect_patterns
from config.stock_universe import NIFTY_50, NIFTY_200
from config.settings import RSI_PERIOD

st.set_page_config(page_title="Technical Screener", layout="wide", page_icon="📈")
from ui.styles import inject_global_css; inject_global_css()
st.title("📈 Technical Screener")

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Technical Filters")

    universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"])
    universe = NIFTY_50 if universe_choice == "Nifty 50" else NIFTY_200
    tickers = list(universe.values())

    st.subheader("RSI")
    rsi_min = st.slider("RSI Min", 0, 100, 0)
    rsi_max = st.slider("RSI Max", 0, 100, 100)

    st.subheader("Trend")
    trend_filter = st.multiselect(
        "Trend", ["Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"],
        default=[]
    )

    st.subheader("Moving Averages")
    above_sma200 = st.checkbox("Above SMA 200")
    above_sma50 = st.checkbox("Above SMA 50")
    golden_cross = st.checkbox("Golden Cross")

    st.subheader("MACD")
    macd_bullish = st.checkbox("MACD Bullish")

    st.subheader("Volume")
    vol_spike = st.checkbox("Volume Spike (>1.5x avg)")

    st.subheader("Sort By")
    sort_by = st.selectbox("Sort", ["tech_strength", "rsi", "volume_ratio"])
    sort_asc = st.checkbox("Ascending", value=False)

    run_btn = st.button("📈 Run Technical Scan", type="primary", width="stretch")

# Preset buttons
st.subheader("Quick Presets")
p1, p2, p3, p4 = st.columns(4)
run_oversold = p1.button("🔻 Oversold (RSI<35)")
run_breakout = p2.button("🚀 Breakout (Vol+SMA)")
run_golden = p3.button("✨ Golden Cross")
run_momentum = p4.button("💪 Momentum (RSI 50-70)")

# ── RUN SCAN ───────────────────────────────────────────────────────────────────
should_run = run_btn or run_oversold or run_breakout or run_golden or run_momentum

# ── Market insights shown during the scan ─────────────────────────────────────
SCAN_INSIGHTS = [
    ("📊 RSI Explained",
     "RSI (Relative Strength Index) measures momentum on a 0–100 scale. "
     "Below 30 = oversold (potential bounce zone). Above 70 = overbought (potential reversal). "
     "RSI 40–60 = neutral momentum."),
    ("✨ Golden Cross vs Death Cross",
     "A Golden Cross occurs when the 50-day MA crosses above the 200-day MA — "
     "historically one of the most reliable long-term bullish signals in markets. "
     "The opposite (Death Cross) signals long-term bearishness."),
    ("🚀 Volume Breakouts",
     "Price breakouts on 1.5× or higher average volume are far more reliable than "
     "low-volume breakouts. Smart money moves markets — high volume confirms conviction "
     "behind a move. Always check volume before entering a breakout trade."),
    ("💪 Momentum Trading",
     "Stocks with RSI between 50–70 are in a 'sweet spot' — trending up but not yet "
     "overbought. This zone often offers the best risk-reward for momentum plays "
     "as the stock has room to run before hitting resistance."),
    ("📈 The 200-Day Moving Average",
     "The 200-day MA is the most widely watched long-term trend indicator. "
     "Above it = bull territory. Below it = bear territory. "
     "FIIs and large funds use this level as a key filter for equity allocation decisions."),
    ("🔄 MACD Crossovers",
     "MACD (Moving Average Convergence Divergence) signals a buy when the MACD line "
     "crosses above its signal line. This works best when price is also above the "
     "200-day MA — trend confirmation + momentum = high-probability setup."),
    ("🏛️ Nifty 50 Composition",
     "The Nifty 50 represents the top 50 companies by free-float market cap on NSE. "
     "Financials (banks + NBFCs) make up ~35% of the index — so HDFC Bank, ICICI Bank, "
     "and Kotak Bank moves have an outsized effect on the overall index."),
    ("⚡ ATR & Position Sizing",
     "ATR (Average True Range) measures daily volatility. "
     "Smart traders size positions so that 1 ATR move = 1% of portfolio risk. "
     "This keeps every trade risk equal regardless of the stock's price."),
    ("🎯 Support & Resistance",
     "Support and resistance levels are where price has repeatedly bounced or reversed. "
     "The more times a level is tested and holds, the more significant it becomes. "
     "A break above resistance with volume often leads to a fast move to the next level."),
    ("📉 Bollinger Band Squeeze",
     "When Bollinger Bands narrow (squeeze), it signals that volatility is compressing — "
     "often a precursor to a big directional move. Watch which way price breaks out of "
     "the squeeze for the direction. This is one of the most reliable breakout setups."),
    ("🇮🇳 FII & DII Flows",
     "Foreign Institutional Investors (FIIs) and Domestic Institutional Investors (DIIs) "
     "are the biggest market movers. FII selling often creates oversold conditions in "
     "quality stocks — some of the best entry points in Nifty 50 history came during "
     "heavy FII outflow periods."),
    ("🔢 The Magic of Compounding",
     "A stock gaining 26% per year doubles every 3 years. "
     "Nifty 50 has delivered ~13% CAGR over the last 20 years. "
     "The key is staying invested through volatility — time in the market beats "
     "timing the market for most retail investors."),
]

if should_run:
    # ── Phase 1: Fetch data with insight card ──────────────────────────────────
    fetch_slot  = st.empty()
    insight_idx = 0

    def _show_insight(idx: int, status: str, pct: float):
        fact = SCAN_INSIGHTS[idx % len(SCAN_INSIGHTS)]
        fetch_slot.markdown(
            f'<div style="background:linear-gradient(145deg,#1e2235,#181c2e);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:16px;'
            f'padding:22px 26px;margin:8px 0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:14px;">'
            f'<span style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:#6b7a99;">{status}</span>'
            f'<span style="font-size:0.72rem;color:#f0b429;font-weight:700;">{pct:.0f}%</span>'
            f'</div>'
            f'<div style="background:rgba(255,255,255,0.06);border-radius:99px;'
            f'height:4px;margin-bottom:18px;overflow:hidden;">'
            f'<div style="width:{pct}%;height:100%;'
            f'background:linear-gradient(90deg,#f0b429,#00c896);'
            f'border-radius:99px;transition:width 0.3s;"></div></div>'
            f'<div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;">'
            f'{fact[0]}</div>'
            f'<div style="font-size:0.85rem;color:#8892a4;line-height:1.65;">'
            f'{fact[1]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _show_insight(0, f"Fetching 1-year data for {len(tickers)} stocks…", 5)

    price_data = fetch_stock_data(tickers, period="1y")

    # ── Phase 2: Compute indicators with live progress ─────────────────────────
    rows    = []
    total   = len(price_data)
    signals = 0

    for i, (ticker, df) in enumerate(price_data.items()):
        pct    = 10 + (i + 1) / total * 88
        label  = ticker.replace(".NS", "").replace(".BO", "")
        status = f"Scanning {label}… ({i+1}/{total})"
        _show_insight(i, status, pct)

        if df is None or df.empty:
            continue
        try:
            df_ind  = compute_indicators(df)
            summary = get_technical_summary(df_ind)
        except Exception:
            continue
        if not summary:
            continue

        signals += 1
        rows.append({
            "ticker":       label,
            "ticker_yf":    ticker,
            "close":        summary.get("close"),
            "rsi":          summary.get("rsi"),
            "trend":        summary.get("trend"),
            "tech_strength":summary.get("strength"),
            "atr":          summary.get("atr"),
            "volume_ratio": summary.get("volume_ratio"),
            "macd_bullish": summary.get("macd_bullish"),
            "patterns":     ", ".join(summary.get("patterns", [])),
            "support":      summary.get("support"),
            "resistance":   summary.get("resistance"),
            "above_sma200": "Above SMA200" in summary.get("patterns", []),
            "above_sma50":  "Above SMA50"  in summary.get("patterns", []),
            "golden_cross": "Golden Cross" in summary.get("patterns", []),
            "vol_spike":    summary.get("volume_ratio", 1) >= 1.5,
        })

    fetch_slot.empty()

    result_df = pd.DataFrame(rows)
    st.session_state.tech_result_df = result_df

if "tech_result_df" not in st.session_state:
    st.stop()

result_df = st.session_state.tech_result_df.copy()

# Apply preset logic
if run_oversold:
    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] < 35)]
elif run_breakout:
    result_df = result_df[result_df["above_sma200"] & result_df["vol_spike"]]
elif run_golden:
    result_df = result_df[result_df["golden_cross"]]
elif run_momentum:
    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] >= 50) & (result_df["rsi"] <= 70)]
else:
    # Custom filters
    if rsi_min > 0:
        result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] >= rsi_min)]
    if rsi_max < 100:
        result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] <= rsi_max)]
    if trend_filter:
        result_df = result_df[result_df["trend"].isin(trend_filter)]
    if above_sma200:
        result_df = result_df[result_df["above_sma200"]]
    if above_sma50:
        result_df = result_df[result_df["above_sma50"]]
    if golden_cross:
        result_df = result_df[result_df["golden_cross"]]
    if macd_bullish:
        result_df = result_df[result_df["macd_bullish"] == True]
    if vol_spike:
        result_df = result_df[result_df["vol_spike"]]

if sort_by in result_df.columns:
    result_df = result_df.sort_values(sort_by, ascending=sort_asc)

# ── DISPLAY RESULTS ────────────────────────────────────────────────────────────
st.subheader(f"Results: {len(result_df)} stocks")

if result_df.empty:
    st.warning("No stocks match your criteria.")
    st.stop()

# Display columns
display_cols = ["ticker", "close", "rsi", "trend", "tech_strength", "volume_ratio", "macd_bullish", "patterns", "support", "resistance"]
display_df = result_df[[c for c in display_cols if c in result_df.columns]].copy()

def color_rsi(val):
    if pd.isna(val):
        return ""
    if val < 30:
        return "color: #ef5350"
    if val > 70:
        return "color: #FF9800"
    return "color: #26a69a"

st.dataframe(display_df, width="stretch", hide_index=True)

# ── CANDLESTICK DETAIL ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Chart Detail")
from data.fetcher import fetch_single_stock
from ui.charts import candlestick_chart, rsi_macd_chart

selected = st.selectbox("Select stock for chart:", result_df["ticker"].tolist())
if selected:
    ticker_yf = result_df[result_df["ticker"] == selected]["ticker_yf"].iloc[0]
    with st.spinner("Loading chart..."):
        df = fetch_single_stock(ticker_yf)
        if df is not None:
            df_ind = compute_indicators(df)
            c1, c2 = st.columns([3, 1])
            with c1:
                fig = candlestick_chart(df_ind, selected, show_volume=True, show_sma=True)
                st.plotly_chart(fig, width="stretch")
                fig2 = rsi_macd_chart(df_ind)
                st.plotly_chart(fig2, width="stretch")
            with c2:
                summary = get_technical_summary(df_ind)
                st.metric("RSI", f"{summary.get('rsi', 'N/A')}")
                st.metric("Trend", summary.get("trend", "N/A"))
                st.metric("Tech Strength", f"{summary.get('strength', 0)}/100")
                st.metric("Volume Ratio", f"{summary.get('volume_ratio', 1):.2f}x")
                st.metric("Support", f"₹{summary.get('support', 0):.2f}")
                st.metric("Resistance", f"₹{summary.get('resistance', 0):.2f}")
                pats = summary.get("patterns", [])
                if pats:
                    st.markdown("**Patterns:**")
                    for p in pats:
                        st.markdown(f"- {p}")
