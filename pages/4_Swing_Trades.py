"""
Page 5: Swing Trade Recommendations (2-5 days)
"""
import time
import streamlit as st
from collections import Counter
from data.fetcher import fetch_single_stock
from data.news_fetcher import fetch_market_news, format_news_for_claude
from analysis.technical import compute_indicators
from analysis.sentiment import analyze_market_sentiment
from signals.swing_signals import generate_swing_signals
from ui.components import signal_card, research_disclaimer
from ui.styles import page_header, show_loading, auth_guard, user_sidebar
from ui.charts import candlestick_chart, rsi_macd_chart
from config.stock_universe import NIFTY_50, NIFTY_200

_STRATEGY_COLORS = {
    "Trend Pullback":         "#7c83fd",
    "Volume Breakout":        "#f0b429",
    "Oversold Reversal":      "#00c896",
    "Bullish Setup":          "#00c896",
    "Golden Cross":           "#f0b429",
    "Supertrend Reversal":    "#00c896",
    "Opening Range Breakout": "#f0b429",
    "VWAP Bounce":            "#7c83fd",
    "EMA Crossover":          "#7c83fd",
    "Supertrend Signal":      "#00c896",
}

st.set_page_config(page_title="Swing Trades · NiftyEdge", layout="wide", page_icon="💹")
from ui.styles import inject_global_css; inject_global_css()
auth_guard()

# ── PAGE HEADER ───────────────────────────────────────────────────────────────────────────────
page_header("💹 Swing Trade Ideas", subtitle="NSE · Equity · 2–5 Day Hold")
research_disclaimer()

# ── SIDEBAR ────────────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"])
    universe = NIFTY_50 if universe_choice == "Nifty 50" else NIFTY_200
    tickers  = list(universe.values())

    st.subheader("Filters")
    min_confidence = st.slider("Min Confidence", 1, 5, 2)

    all_strategies = [
        "Trend Pullback", "Volume Breakout", "Oversold Reversal",
        "Bullish Setup", "Golden Cross", "Supertrend Reversal",
    ]
    selected_strategies = st.multiselect("Strategy", all_strategies, default=all_strategies)
    run_btn = st.button("🔄 Generate Signals", type="primary", use_container_width=True)

    st.divider()
    with st.expander("📋 Strategy Criteria", expanded=False):
        st.markdown("""
**Trend Pullback** — Close > SMA50 > SMA200, price within 5% of EMA21, RSI 35–65

**Volume Breakout** — Above SMA200, RSI 50–75, volume ≥ 1.5× avg

**Oversold Reversal** — RSI < 40, fundamental score > 0.35

**Bullish Setup** — Above SMA200, MACD bullish, RSI < 70

**Golden Cross** — SMA50 crossed above SMA200 within 20 bars

**Supertrend Reversal** — Supertrend flipped bull within 5 bars, MACD bullish
""")

    st.divider()
    user_sidebar()

# ── SENTIMENT ──────────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_sentiment_score():
    news   = fetch_market_news()
    result = analyze_market_sentiment(
        format_news_for_claude(news, max_items=25),
        news_items=news,
    )
    return result.get("overall_sentiment", 5) / 10

_sent_slot = show_loading("Analysing latest market news for sentiment score…", "#7c83fd")
try:
    sentiment_score = get_sentiment_score()
except Exception:
    sentiment_score = 0.5
_sent_slot.empty()

# ── CACHED SCAN — cross-session 30-min TTL ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _cached_swing_scan(tickers_tuple: tuple, sentiment: float) -> dict:
    """Returns {signals: list[dict], scanned_at: float}. Cached 30 min."""
    sigs = generate_swing_signals(list(tickers_tuple), sentiment_score=sentiment)
    return {"signals": [s.to_dict() for s in sigs], "scanned_at": time.time()}

tickers_key       = tuple(sorted(tickers))
_universe_changed = st.session_state.get("swing_universe") != universe_choice

# ── SCAN FACTS (shown during manual refresh progress bar) ───────────────────────────────────────────────
_SCAN_FACTS = [
    ("📊 RSI & Momentum",      "RSI between 35–65 is the sweet spot for swing entries — not oversold, not overbought. We look for momentum without exhaustion."),
    ("📈 Trend Pullback",      "Best swing trades enter during a pullback within an uptrend. Price above SMA50 and SMA200 confirms the trend; EMA21 is our pullback target."),
    ("🕯️ Volume Confirmation", "Volume 1.5× average during a breakout signals institutional participation — not just retail noise. We require it for Volume Breakout signals."),
    ("✨ Golden Cross",        "SMA50 crossing above SMA200 is one of the most historically reliable long-term bullish signals in Indian equity markets."),
    ("🛡️ ATR-Based Stops",    "Stop-losses are set at 1.5× ATR from entry. ATR adapts to each stock's volatility so stops are neither too tight nor too wide."),
    ("⚡ Supertrend Reversal", "When Supertrend flips from bearish to bullish and MACD confirms, it often marks the start of a new swing leg — we catch it within 5 bars."),
]

# ── SCAN TRIGGER ───────────────────────────────────────────────────────────────────────────────────
if run_btn or "swing_signals" not in st.session_state or _universe_changed:
    if run_btn:
        # Manual refresh: show animated progress bar, clear cross-session cache
        _cached_swing_scan.clear()
        scan_slot = st.empty()

        def _on_tick(ticker, strategies, done, total):
            label   = ticker.replace(".NS", "")
            pct     = max(4, done / total * 96)
            fact    = _SCAN_FACTS[(done - 1) % len(_SCAN_FACTS)]
            found   = f" · {len(strategies)} signal{'s' if len(strategies) != 1 else ''}" if strategies else ""
            scan_slot.markdown(
                f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:22px 26px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
                f'<span style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;'
                f'text-transform:uppercase;color:#475569;">Scanning {label}{found}</span>'
                f'<span style="font-size:0.72rem;color:#f0b429;font-weight:700;">{done} / {total}</span>'
                f'</div>'
                f'<div style="background:rgba(255,255,255,0.06);border-radius:99px;'
                f'height:4px;margin-bottom:18px;overflow:hidden;">'
                f'<div style="width:{pct:.1f}%;height:100%;'
                f'background:linear-gradient(90deg,#f0b429,#00c896);border-radius:99px;"></div></div>'
                f'<div style="font-size:0.88rem;font-weight:700;color:#e2e8f0;margin-bottom:5px;">{fact[0]}</div>'
                f'<div style="font-size:0.8rem;color:#64748b;line-height:1.6;">{fact[1]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        try:
            sigs_raw = generate_swing_signals(
                tickers, sentiment_score=sentiment_score, on_tick=_on_tick
            )
            signals = [s.to_dict() for s in sigs_raw]
        except Exception as _e:
            st.error(f"Signal generation failed: {_e}. Please try again.")
            signals = []
        scan_slot.empty()
    else:
        # Cold session start or universe change — try cross-session cache first
        _scan_slot = show_loading(f"Running swing signal scan across {len(tickers)} stocks — checking RSI, MACD, Supertrend, volume…", "#f0b429")
        result = _cached_swing_scan(tickers_key, round(sentiment_score, 2))
        _scan_slot.empty()
        signals = result["signals"]
        st.session_state.swing_scan_ts = result.get("scanned_at", time.time())

    st.session_state.swing_signals  = signals
    st.session_state.swing_universe = universe_choice
    if run_btn:
        st.session_state.swing_scan_ts = time.time()

signals = st.session_state.get("swing_signals", [])

# ── LAST SCANNED BADGE ──────────────────────────────────────────────────────────────────────────────────
_ts = st.session_state.get("swing_scan_ts")
if _ts:
    import pytz as _tz
    from datetime import datetime as _dt
    _ist = _tz.timezone("Asia/Kolkata")
    _time_str = _dt.fromtimestamp(_ts, _ist).strftime("%H:%M IST")
    _elapsed  = int(time.time() - _ts)
    _from_cache = "· from cache" if _elapsed > 90 else ""
    st.markdown(
        f'<div style="margin-bottom:6px;">'
        f'<span style="font-size:0.68rem;color:#374151;">🕐 Scanned at {_time_str} {_from_cache}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── STATS STRIP ────────────────────────────────────────────────────────────────────────────────────
strategies_active = len(set(s.get("strategy", "") for s in signals))
sentiment_label   = (
    "Very Bullish" if sentiment_score >= 0.8 else
    "Bullish"      if sentiment_score >= 0.6 else
    "Neutral"      if sentiment_score >= 0.4 else
    "Bearish"
)
sentiment_color = (
    "#00c896" if sentiment_score >= 0.6 else
    "#f0b429" if sentiment_score >= 0.4 else
    "#ff4d6d"
)

st.markdown(
    f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0;">'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Signals Found</div>'
    f'<div style="color:#f1f5f9;font-size:1.6rem;font-weight:800;letter-spacing:-0.03em;">'
    f'{len(signals)}</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Sentiment</div>'
    f'<div style="color:{sentiment_color};font-size:1.6rem;font-weight:800;letter-spacing:-0.03em;">'
    f'{sentiment_score * 10:.1f}<span style="font-size:0.9rem;color:#475569;">/10</span></div>'
    f'<div style="color:{sentiment_color};font-size:0.7rem;font-weight:600;margin-top:2px;">'
    f'{sentiment_label}</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Universe</div>'
    f'<div style="color:#f1f5f9;font-size:1.6rem;font-weight:800;letter-spacing:-0.03em;">'
    f'{len(tickers)}<span style="font-size:0.9rem;color:#475569;"> stocks</span></div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Strategies Active</div>'
    f'<div style="color:#f1f5f9;font-size:1.6rem;font-weight:800;letter-spacing:-0.03em;">'
    f'{strategies_active}<span style="font-size:0.9rem;color:#475569;">/6</span></div>'
    f'</div>'

    f'</div>',
    unsafe_allow_html=True,
)

# ── STRATEGY BREAKDOWN CHIPS ───────────────────────────────────────────────────────────────────────────────────
if signals:
    strategy_counts = Counter(s.get("strategy", "") for s in signals)
    chips = " ".join([
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:{_STRATEGY_COLORS.get(k, "#6b7a99")}15;'
        f'color:{_STRATEGY_COLORS.get(k, "#6b7a99")};'
        f'border:1px solid {_STRATEGY_COLORS.get(k, "#6b7a99")}30;'
        f'border-radius:20px;padding:4px 12px;font-size:0.72rem;font-weight:700;'
        f'letter-spacing:0.03em;margin:3px 2px;">'
        f'{k} <span style="background:{_STRATEGY_COLORS.get(k,"#6b7a99")}25;'
        f'border-radius:10px;padding:0 6px;font-size:0.68rem;">{v}</span>'
        f'</span>'
        for k, v in sorted(strategy_counts.items(), key=lambda x: -x[1])
    ])
    st.markdown(
        f'<div style="margin:4px 0 20px;line-height:2;">{chips}</div>',
        unsafe_allow_html=True,
    )

# ── FILTERED SIGNALS ───────────────────────────────────────────────────────────────────────────────────
filtered = [
    s for s in signals
    if (s.get("confidence") or 0) >= min_confidence
    and (not selected_strategies or s.get("strategy") in selected_strategies)
]

if not filtered:
    st.markdown(
        '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
        'border-radius:14px;padding:32px;text-align:center;margin:16px 0;">'
        '<div style="color:#475569;font-size:1rem;font-weight:600;margin-bottom:6px;">'
        'No signals match your filters</div>'
        '<div style="color:#374151;font-size:0.82rem;">'
        'Try lowering the confidence threshold or selecting more strategies</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown(
    f'<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
    f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:8px;">'
    f'Trade Signals — {len(filtered)} results</div>',
    unsafe_allow_html=True,
)

# ── SIGNAL CARDS ───────────────────────────────────────────────────────────────────────────────────
for i, sig in enumerate(filtered):
    signal_card(sig)
    strat_color  = _STRATEGY_COLORS.get(sig.get("strategy", ""), "#6b7a99")
    ticker       = sig.get("ticker", "")
    ticker_short = ticker.replace(".NS", "")
    tech_score   = float(sig.get("technical_score", 0.5) or 0.5)
    fund_score   = float(sig.get("fundamental_score", 0.5) or 0.5)

    with st.expander(f"📊 {ticker_short} — Analysis & Chart", expanded=False):

        # ── Score bars ───────────────────────────────────────────────────────────────────────
        st.markdown(
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;">'

            f'<div style="background:rgba(124,131,253,0.05);border:1px solid rgba(124,131,253,0.15);'
            f'border-radius:10px;padding:12px 14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;">'
            f'<span style="font-size:0.65rem;font-weight:700;color:#64748b;'
            f'text-transform:uppercase;letter-spacing:0.09em;">Technical</span>'
            f'<span style="font-size:0.78rem;font-weight:700;color:#a5b4fc;">'
            f'{tech_score * 10:.1f}<span style="color:#475569;font-size:0.65rem;">/10</span></span>'
            f'</div>'
            f'<div style="background:rgba(255,255,255,0.06);border-radius:3px;height:4px;overflow:hidden;">'
            f'<div style="width:{tech_score*100:.0f}%;height:100%;'
            f'background:linear-gradient(90deg,#7c83fd,#a5b4fc);border-radius:3px;"></div></div>'
            f'</div>'

            f'<div style="background:rgba(0,200,150,0.05);border:1px solid rgba(0,200,150,0.15);'
            f'border-radius:10px;padding:12px 14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;">'
            f'<span style="font-size:0.65rem;font-weight:700;color:#64748b;'
            f'text-transform:uppercase;letter-spacing:0.09em;">Fundamental</span>'
            f'<span style="font-size:0.78rem;font-weight:700;color:#00c896;">'
            f'{fund_score * 10:.1f}<span style="color:#475569;font-size:0.65rem;">/10</span></span>'
            f'</div>'
            f'<div style="background:rgba(255,255,255,0.06);border-radius:3px;height:4px;overflow:hidden;">'
            f'<div style="width:{fund_score*100:.0f}%;height:100%;'
            f'background:linear-gradient(90deg,#00c896,#34d399);border-radius:3px;"></div></div>'
            f'</div>'

            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Pattern chips ─────────────────────────────────────────────────────────────────────────────
        patterns = sig.get("patterns", [])
        if patterns:
            chips_html = " ".join([
                f'<span style="display:inline-block;background:{strat_color}10;color:{strat_color};'
                f'border:1px solid {strat_color}25;border-radius:5px;'
                f'padding:2px 9px;font-size:0.68rem;font-weight:600;margin:2px;">{p}</span>'
                for p in patterns
            ])
            st.markdown(
                f'<div style="margin-bottom:12px;line-height:1.9;">{chips_html}</div>',
                unsafe_allow_html=True,
            )

        # ── Analysis bullets ──────────────────────────────────────────────────────────────────────────────
        reasoning = sig.get("reasoning", "")
        if reasoning:
            parts = [
                p.strip() for p in
                reasoning.replace("Strategy:", "\nStrategy:").split(".")
                if len(p.strip()) > 8
            ]
            bullets_html = "".join([
                f'<div style="display:flex;align-items:flex-start;gap:9px;'
                f'padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<span style="color:{strat_color};font-size:0.7rem;margin-top:2px;'
                f'flex-shrink:0;">◆</span>'
                f'<span style="color:#94a3b8;font-size:0.81rem;line-height:1.55;">'
                f'{p}</span>'
                f'</div>'
                for p in parts[:5]
            ])
            st.markdown(
                f'<div style="margin-bottom:14px;">{bullets_html}</div>',
                unsafe_allow_html=True,
            )

        # ── Live indicator mini-grid + charts ─────────────────────────────────────────────────────────────────
        df = fetch_single_stock(ticker)
        if df is not None:
            df_ind   = compute_indicators(df)
            latest   = df_ind.iloc[-1]

            def _f(v):
                try: return float(v) if v == v else None
                except: return None

            rsi       = _f(latest.get("RSI_14"))
            vol_ratio = _f(latest.get("Volume_ratio"))

            sma50  = _f(latest.get("SMA_50"))
            sma200 = _f(latest.get("SMA_200"))
            close  = _f(latest.get("Close"))

            trend_lbl  = "Uptrend" if (close and sma50 and sma200 and close > sma50 > sma200) \
                         else "Mixed" if (close and sma50 and close > sma50) \
                         else "Downtrend" if close else "—"
            trend_col  = "#00c896" if trend_lbl == "Uptrend" else "#f0b429" if trend_lbl == "Mixed" else "#ff4d6d"

            rsi_lbl = f"{rsi:.0f}" if rsi is not None else "—"
            rsi_col = "#00c896" if rsi and rsi < 60 else "#f0b429" if rsi and rsi < 70 else "#ff4d6d" if rsi else "#64748b"

            vol_lbl = f"{vol_ratio}×" if vol_ratio else "—"
            vol_col = "#00c896" if vol_ratio and vol_ratio >= 1.5 else "#f0b429" if vol_ratio else "#64748b"

            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);'
                f'gap:6px;margin-bottom:14px;">'

                + "".join([
                    f'<div style="background:rgba(255,255,255,0.03);'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:9px 10px;">'
                    f'<div style="font-size:0.6rem;font-weight:700;color:#475569;'
                    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">{lbl}</div>'
                    f'<div style="font-size:0.88rem;font-weight:700;color:{col};">{val}</div>'
                    f'</div>'
                    for lbl, val, col in [
                        ("RSI",    rsi_lbl,  rsi_col),
                        ("Volume", vol_lbl,  vol_col),
                        ("Trend",  trend_lbl, trend_col),
                        ("Score",  f"{round((tech_score + fund_score) / 2 * 10, 1)}/10", strat_color),
                    ]
                ])

                + f'</div>',
                unsafe_allow_html=True,
            )

            fig = candlestick_chart(
                df_ind, ticker,
                show_sma=True, show_volume=True,
                signal_lines={
                    "entry":     sig.get("entry", 0),
                    "stop_loss": sig.get("stop_loss", 0),
                    "target_1":  sig.get("target_1", 0),
                    "target_2":  sig.get("target_2", 0),
                },
            )
            st.plotly_chart(fig, use_container_width=True, key=f"candle_{i}_{ticker}")
            st.plotly_chart(rsi_macd_chart(df_ind), use_container_width=True, key=f"rsi_{i}_{ticker}")

st.divider()
st.caption(
    "⚠️ For educational purposes only. Do your own research. "
    "Past performance is not indicative of future results."
)
