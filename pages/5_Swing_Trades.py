"""
Page 5: Swing Trade Recommendations (2-5 days)
- Signal cards with entry/SL/targets
- Candlestick chart with signal lines overlaid
- Filter by confidence, sector, strategy
"""
import streamlit as st
from collections import Counter
from data.fetcher import fetch_single_stock
from data.news_fetcher import fetch_market_news, format_news_for_claude
from analysis.technical import compute_indicators
from analysis.sentiment import analyze_market_sentiment
from signals.swing_signals import generate_swing_signals
from ui.components import signal_card
from ui.charts import candlestick_chart, rsi_macd_chart
from config.stock_universe import NIFTY_50, NIFTY_200

st.set_page_config(page_title="Swing Trades", layout="wide", page_icon="💹")
from ui.styles import inject_global_css; inject_global_css()
st.title("💹 Swing Trade Ideas (2–5 Days)")

# ── STRATEGY CRITERIA ──────────────────────────────────────────────────────────
with st.expander("📋 Strategy Criteria — What each strategy looks for", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
**Trend Pullback**
- Stock in confirmed uptrend: Close > SMA50 > SMA200
- Price within 5% of EMA21 (healthy pullback)
- RSI between 35–65 (cooling but not broken)

**Volume Breakout**
- Price above SMA200 (uptrend confirmed)
- RSI between 50–75 (building momentum)
- Volume ≥ 1.5× 20-day average

**Oversold Reversal**
- RSI below 40 (heavily sold off)
- Composite fundamental score > 0.35
- Contrarian bounce setup
""")
    with col2:
        st.markdown("""
**Bullish Setup**
- Price above SMA200 (uptrend context)
- MACD line above signal line (positive momentum)
- RSI below 70 (not yet overbought)

**Golden Cross**
- SMA50 crossed above SMA200 within last 20 bars
- RSI between 45–72 (fresh uptrend momentum)
- Classic long-term bullish trend signal

**Supertrend Reversal**
- Supertrend indicator flipped from bear to bull within 5 bars
- MACD bullish confirmation + RSI below 70
- Early trend-change entry
""")

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"])
    universe = NIFTY_50 if universe_choice == "Nifty 50" else NIFTY_200
    tickers = list(universe.values())

    st.subheader("Filter Signals")
    min_confidence = st.slider("Min Confidence (stars)", 1, 5, 2)

    all_strategies = [
        "Trend Pullback", "Volume Breakout", "Oversold Reversal",
        "Bullish Setup", "Golden Cross", "Supertrend Reversal",
    ]
    selected_strategies = st.multiselect("Strategy", all_strategies, default=all_strategies)

    run_btn = st.button("🔄 Generate Signals", type="primary", width="stretch")

# ── SENTIMENT SCORE ────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_sentiment_score():
    news = fetch_market_news()
    result = analyze_market_sentiment(
        format_news_for_claude(news, max_items=25),
        news_items=news,
    )
    return result.get("overall_sentiment", 5) / 10

# ── GENERATE SIGNALS ───────────────────────────────────────────────────────────
if run_btn or "swing_signals" not in st.session_state:
    try:
        sentiment_score = get_sentiment_score()
    except Exception:
        sentiment_score = 0.5

    with st.spinner(f"Scanning {len(tickers)} stocks across 6 strategies..."):
        try:
            signals = generate_swing_signals(tickers, sentiment_score=sentiment_score)
            strategies_found = set(s.strategy for s in signals)
            st.success(f"Scan complete — {len(signals)} signals across {len(strategies_found)} strategies")
        except Exception as _e:
            st.error(f"Signal generation failed: {_e}. Please try again.")
            signals = []

    st.session_state.swing_signals = signals
    st.session_state.swing_sentiment_score = sentiment_score

signals = st.session_state.get("swing_signals", [])
sentiment_score = st.session_state.get("swing_sentiment_score", 0.5)

# ── MARKET CONTEXT ─────────────────────────────────────────────────────────────
strategies_active = len(set(s.strategy for s in signals))
m1, m2, m3, m4 = st.columns(4)
m1.metric("Signals Found", len(signals))
m2.metric("Market Sentiment", f"{sentiment_score * 10:.1f}/10")
m3.metric("Universe", f"{len(tickers)} stocks")
m4.metric("Strategies Active", strategies_active)

if signals:
    strategy_counts = Counter(s.strategy for s in signals)
    breakdown = " · ".join(f"{k}: {v}" for k, v in sorted(strategy_counts.items()))
    st.caption(f"Strategy breakdown: {breakdown}")

# Filter signals
filtered = [
    s for s in signals
    if s.confidence >= min_confidence
    and (not selected_strategies or s.strategy in selected_strategies)
]

st.subheader(f"Trade Signals: {len(filtered)} found")

if not filtered:
    st.caption("No signals match your criteria. Try lowering confidence or broadening the strategy filter.")
    st.stop()

# ── SIGNAL CARDS ───────────────────────────────────────────────────────────────
for signal in filtered:
    sd = signal.to_dict()
    signal_card(sd)

    with st.expander(f"📊 Chart: {signal.ticker}", expanded=False):
        df = fetch_single_stock(signal.ticker)
        if df is not None:
            df_ind = compute_indicators(df)
            fig = candlestick_chart(
                df_ind, signal.ticker,
                show_sma=True, show_volume=True,
                signal_lines={
                    "entry": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "target_1": signal.target_1,
                    "target_2": signal.target_2,
                },
            )
            st.plotly_chart(fig, width="stretch")
            fig2 = rsi_macd_chart(df_ind)
            st.plotly_chart(fig2, width="stretch")

st.divider()
st.caption(
    "⚠️ **Disclaimer**: These signals are generated algorithmically for educational purposes only. "
    "Do your own research. Past performance is not indicative of future results. "
    "Always use proper risk management."
)
