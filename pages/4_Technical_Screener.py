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
run_oversold = p1.button("🔻 Oversold (RSI<30)")
run_breakout = p2.button("🚀 Breakout (Vol+SMA)")
run_golden = p3.button("✨ Golden Cross")
run_momentum = p4.button("💪 Momentum (RSI 50-70)")

# ── RUN SCAN ───────────────────────────────────────────────────────────────────
should_run = run_btn or run_oversold or run_breakout or run_golden or run_momentum

if should_run:
    with st.spinner(f"Scanning {len(tickers)} stocks..."):
        price_data = fetch_stock_data(tickers)
        rows = []
        for ticker, df in price_data.items():
            if df is None or df.empty:
                continue
            df_ind = compute_indicators(df)
            summary = get_technical_summary(df_ind)
            if not summary:
                continue
            rows.append({
                "ticker": ticker.replace(".NS", ""),
                "ticker_yf": ticker,
                "close": summary.get("close"),
                "rsi": summary.get("rsi"),
                "trend": summary.get("trend"),
                "tech_strength": summary.get("strength"),
                "atr": summary.get("atr"),
                "volume_ratio": summary.get("volume_ratio"),
                "macd_bullish": summary.get("macd_bullish"),
                "patterns": ", ".join(summary.get("patterns", [])),
                "support": summary.get("support"),
                "resistance": summary.get("resistance"),
                "above_sma200": "Above SMA200" in summary.get("patterns", []),
                "above_sma50": "Above SMA50" in summary.get("patterns", []),
                "golden_cross": "Golden Cross" in summary.get("patterns", []),
                "vol_spike": summary.get("volume_ratio", 1) >= 1.5,
            })
        result_df = pd.DataFrame(rows)
        st.session_state.tech_result_df = result_df

if "tech_result_df" not in st.session_state:
    st.info("Configure filters in the sidebar and click **Run Technical Scan**, or use a preset button above.")
    st.stop()

result_df = st.session_state.tech_result_df.copy()

# Apply preset logic
if run_oversold:
    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] < 30)]
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
    st.info("No stocks match your criteria.")
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
