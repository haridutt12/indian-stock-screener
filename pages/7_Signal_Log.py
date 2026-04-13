"""
Page 7: Signal Log & Backtesting Dashboard

Displays all historically logged signals with their outcomes and provides
aggregate performance metrics to evaluate strategy quality over time.
"""
import json

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from signals.signal_logger import (
    get_signal_logger,
    OUTCOME_OPEN,
    OUTCOME_TARGET1,
    OUTCOME_TARGET2,
    OUTCOME_STOPPED,
    OUTCOME_EXPIRED,
)

st.set_page_config(page_title="Signal Log", layout="wide", page_icon="📋")
st.title("📋 Signal Log & Backtesting")

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    timeframe_opt = st.selectbox("Timeframe", ["All", "INTRADAY", "SWING"])
    timeframe = None if timeframe_opt == "All" else timeframe_opt

    strategy_opts = [
        "All",
        "Opening Range Breakout",
        "VWAP Bounce",
        "Trend Pullback",
        "Volume Breakout",
        "Oversold Reversal",
        "Bullish Setup",
    ]
    strategy_opt = st.selectbox("Strategy", strategy_opts)
    strategy = None if strategy_opt == "All" else strategy_opt

    outcome_opts = ["All", OUTCOME_OPEN, OUTCOME_TARGET1, OUTCOME_TARGET2, OUTCOME_STOPPED, OUTCOME_EXPIRED]
    outcome_opt = st.selectbox("Outcome", outcome_opts)
    outcome_filter = None if outcome_opt == "All" else outcome_opt

    days_back = st.slider("History (days)", 7, 180, 60)

    st.divider()
    if st.button("Force Resolve Open Signals", help="Run the outcome tracker now"):
        with st.spinner("Resolving outcomes..."):
            from signals.outcome_tracker import update_open_signal_outcomes
            n = update_open_signal_outcomes()
            st.success(f"Resolved {n} signal(s).")
            st.rerun()

# ── Fetch data ─────────────────────────────────────────────────────────────────
log = get_signal_logger()

perf = log.get_performance_summary(timeframe=timeframe, days_back=days_back)
signals = log.get_signals(
    timeframe=timeframe,
    strategy=strategy,
    outcome=outcome_filter,
    days_back=days_back,
)

# ── Performance summary metrics ────────────────────────────────────────────────
st.subheader("Performance Summary")

total_closed = perf["won"] + perf["lost"]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Signals", perf["total"])
col2.metric("Open", perf["open"])
col3.metric("Won (T1+T2)", perf["won"])
col4.metric("Stopped", perf["lost"])
col5.metric(
    "Win Rate",
    f"{perf['win_rate']}%" if total_closed > 0 else "—",
)
avg_r = perf.get("avg_r")
col6.metric(
    "Avg R (closed)",
    f"{avg_r:+.2f}R" if avg_r is not None else "—",
    help="Average risk-multiple on resolved (non-expired) trades. >0 = profitable.",
)

if perf["total"] == 0:
    st.info(
        "No signals logged yet. Generate signals from the **Swing Trades** or "
        "**Intraday Ideas** pages — they are automatically saved here."
    )
    st.stop()

# ── Charts row ─────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Outcome Distribution")
    outcome_labels = {
        OUTCOME_TARGET2:  "Target 2 Hit",
        OUTCOME_TARGET1:  "Target 1 Hit",
        OUTCOME_STOPPED:  "Stopped Out",
        OUTCOME_EXPIRED:  "Expired",
        OUTCOME_OPEN:     "Still Open",
    }
    outcome_colors = {
        OUTCOME_TARGET2:  "#00C896",
        OUTCOME_TARGET1:  "#5AD8A6",
        OUTCOME_STOPPED:  "#F4664A",
        OUTCOME_EXPIRED:  "#FAAD14",
        OUTCOME_OPEN:     "#9BA7B4",
    }
    by_outcome = perf.get("by_outcome", {})
    if by_outcome:
        labels = [outcome_labels.get(k, k) for k in by_outcome]
        values = list(by_outcome.values())
        colors = [outcome_colors.get(k, "#cccccc") for k in by_outcome]
        fig_pie = go.Figure(go.Pie(
            labels=labels,
            values=values,
            marker=dict(colors=colors),
            hole=0.4,
            textinfo="label+percent",
        ))
        fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280, showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No outcome data yet.")

with chart_col2:
    st.subheader("Cumulative R (Equity Curve)")
    closed = [s for s in signals if s["outcome"] not in (OUTCOME_OPEN, OUTCOME_EXPIRED) and s.get("pnl_r") is not None]
    if closed:
        closed_sorted = sorted(closed, key=lambda x: x["outcome_at"] or x["signal_date"])
        pnl_series = [s["pnl_r"] for s in closed_sorted]
        dates = [s.get("outcome_at") or s["signal_date"] for s in closed_sorted]
        cumulative = [sum(pnl_series[: i + 1]) for i in range(len(pnl_series))]
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(
            x=dates,
            y=cumulative,
            mode="lines+markers",
            line=dict(color="#1890FF", width=2),
            marker=dict(size=5),
            hovertemplate="Trade %{pointNumber+1}<br>Cumulative R: %{y:.2f}<extra></extra>",
        ))
        fig_equity.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig_equity.update_layout(
            yaxis_title="Cumulative R",
            xaxis_title="",
            margin=dict(t=10, b=40, l=40, r=10),
            height=280,
        )
        st.plotly_chart(fig_equity, use_container_width=True)
    else:
        st.info("No resolved trades yet for equity curve.")

# ── Per-strategy breakdown ─────────────────────────────────────────────────────
by_strat = perf.get("by_strategy", {})
if by_strat:
    st.subheader("Strategy Breakdown")
    strat_rows = []
    for name, stats in by_strat.items():
        closed_n = stats["wins"] + stats["losses"]
        strat_rows.append({
            "Strategy":  name,
            "Total":     stats["total"],
            "Won":       stats["wins"],
            "Stopped":   stats["losses"],
            "Win Rate":  f"{stats['win_rate']}%" if closed_n else "—",
            "Avg R":     f"{stats['avg_r']:+.2f}" if stats.get("avg_r") is not None else "—",
        })
    st.dataframe(pd.DataFrame(strat_rows).set_index("Strategy"), use_container_width=True)

# ── Signal history table ───────────────────────────────────────────────────────
st.subheader(f"Signal History ({len(signals)} records)")

if not signals:
    st.info("No signals match the current filters.")
    st.stop()

OUTCOME_EMOJI = {
    OUTCOME_TARGET2: "✅✅",
    OUTCOME_TARGET1: "✅",
    OUTCOME_STOPPED: "❌",
    OUTCOME_EXPIRED: "⏳",
    OUTCOME_OPEN:    "🔵",
}

rows = []
for s in signals:
    patterns = s.get("patterns", "[]")
    if isinstance(patterns, str):
        try:
            patterns = json.loads(patterns)
        except Exception:
            patterns = []
    rows.append({
        "Date":      s["signal_date"],
        "Ticker":    s["ticker"],
        "TF":        s["timeframe"],
        "Strategy":  s["strategy"],
        "Dir":       s["direction"],
        "Entry":     s["entry_price"],
        "SL":        s["stop_loss"],
        "T1":        s["target_1"],
        "T2":        s["target_2"],
        "R:R":       s["risk_reward"],
        "Conf":      "★" * (s["confidence"] or 1),
        "Outcome":   OUTCOME_EMOJI.get(s["outcome"], s["outcome"]) + " " + s["outcome"],
        "Exit":      s.get("outcome_price", ""),
        "pnl_r":     s.get("pnl_r", ""),
        "Sector":    s.get("sector", ""),
    })

df_display = pd.DataFrame(rows)

# Colour-code pnl_r column
def _color_pnl(val):
    if val == "" or val is None:
        return ""
    try:
        v = float(val)
        if v > 0:
            return "color: #00C896"
        if v < 0:
            return "color: #F4664A"
    except (TypeError, ValueError):
        pass
    return ""

styled = (
    df_display.style
    .map(_color_pnl, subset=["pnl_r"])
    .format(
        {
            "Entry": "{:.2f}",
            "SL":    "{:.2f}",
            "T1":    "{:.2f}",
            "T2":    "{:.2f}",
            "R:R":   "{:.2f}",
            "Exit":  lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else v,
            "pnl_r": lambda v: f"{v:+.2f}R" if isinstance(v, (int, float)) else v,
        }
    )
)
st.dataframe(styled, use_container_width=True, height=500)

# ── Download ───────────────────────────────────────────────────────────────────
csv = df_display.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download CSV",
    data=csv,
    file_name=f"signal_log_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)

st.divider()
st.caption(
    "Outcomes are resolved automatically at 4:30 PM IST each trading day. "
    "Use **Force Resolve** in the sidebar to refresh manually at any time."
)
