"""
Page 7: Signal Log & Backtesting Dashboard

Displays all historically logged signals with their outcomes, realistic
transaction costs, and aggregate performance metrics for strategy evaluation.
"""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from signals.signal_logger import (
        get_signal_logger,
        OUTCOME_OPEN,
        OUTCOME_TARGET1,
        OUTCOME_TARGET2,
        OUTCOME_STOPPED,
        OUTCOME_SQUARED_OFF,
        OUTCOME_EXPIRED,
    )
    from signals.trade_costs import DEFAULT_POSITION_SIZE_INR
    _import_error = None
except Exception as _exc:
    import traceback as _tb
    _import_error = _tb.format_exc()

st.set_page_config(page_title="Signal Log", layout="wide", page_icon="📋")
st.title("📋 Signal Log & Backtesting")

# Surface any import error with the full traceback so it is visible on screen
if _import_error:
    st.error("**Import failed — full traceback below (share this with support):**")
    st.code(_import_error, language="python")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    timeframe_opt = st.selectbox("Timeframe", ["All", "INTRADAY", "SWING"])
    timeframe = None if timeframe_opt == "All" else timeframe_opt

    strategy_opts = [
        "All",
        "Opening Range Breakout", "VWAP Bounce",
        "Trend Pullback", "Volume Breakout", "Oversold Reversal", "Bullish Setup",
    ]
    strategy_opt = st.selectbox("Strategy", strategy_opts)
    strategy = None if strategy_opt == "All" else strategy_opt

    outcome_opts = [
        "All",
        OUTCOME_OPEN, OUTCOME_TARGET1, OUTCOME_TARGET2,
        OUTCOME_STOPPED, OUTCOME_SQUARED_OFF, OUTCOME_EXPIRED,
    ]
    outcome_opt = st.selectbox("Outcome", outcome_opts)
    outcome_filter = None if outcome_opt == "All" else outcome_opt

    hide_squared_off = st.checkbox(
        "Hide Squared Off",
        value=True,
        help="Squared Off = intraday positions force-closed at 3:30 PM with no stop/target hit. "
             "Usually noise — hide to focus on meaningful trades.",
        disabled=(outcome_opt == OUTCOME_SQUARED_OFF),  # pointless to hide if explicitly filtering to it
    )

    days_back = st.slider("History (days)", 7, 180, 60)

    st.divider()
    st.subheader("Cost Settings")
    position_size = st.number_input(
        "Position Size (₹)", min_value=10_000, max_value=10_000_000,
        value=int(DEFAULT_POSITION_SIZE_INR), step=10_000,
        help="Capital per trade used to calculate realistic ₹ costs and P&L.",
    )

    st.divider()
    st.subheader("🔄 Resolve Outcomes")
    st.caption("Checks every open signal against price data and marks stop/target/expiry hits.")
    if st.button("Resolve Open Signals Now", type="primary", use_container_width=True,
                 help="Fetches latest prices and updates all OPEN signal outcomes"):
        with st.spinner("Fetching prices and resolving outcomes — may take 15–30 s…"):
            try:
                from signals.outcome_tracker import update_open_signal_outcomes
                n = update_open_signal_outcomes(position_size_inr=float(position_size))
                st.success(f"✅ Resolved {n} signal(s).")
            except Exception as _e:
                st.error(f"Error: {_e}")
            st.rerun()

    st.divider()
    st.subheader("📣 Telegram")
    if st.button("📊 Send Market Update Now", use_container_width=True):
        import requests as _req, html as _html
        try:
            token   = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
            channel = st.secrets.get("TELEGRAM_CHANNEL_ID", "")
        except Exception:
            import os
            token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
            channel = os.getenv("TELEGRAM_CHANNEL_ID", "")

        if not token or not channel:
            st.error("Secrets missing — check Streamlit Cloud → Settings → Secrets.")
        else:
            with st.spinner("Sending…"):
                from datetime import datetime
                import pytz
                now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y %H:%M IST")
                msg = f"📊 <b>NSE Live Market Update</b>\n🕐 {now}\n\n"

                try:
                    from data.fetcher import fetch_index_data
                    from config.settings import INDICES
                    for name, ticker in list(INDICES.items())[:3]:
                        df = fetch_index_data(ticker, period="5d", interval="1d")
                        if df is not None and len(df) >= 2:
                            price = float(df["Close"].iloc[-1])
                            chg   = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
                            arrow = "🟢" if chg >= 0 else "🔴"
                            msg  += f"{arrow} <b>{name}</b>: {price:,.0f} ({chg:+.2f}%)\n"
                except Exception:
                    pass

                try:
                    from data.news_fetcher import fetch_market_news
                    news = fetch_market_news(use_cache=True)
                    if news:
                        msg += "\n📰 <b>Latest News:</b>\n"
                        for n in news[:3]:
                            title = _html.unescape(n.get("title", ""))[:70]
                            msg  += f"• {title}\n"
                except Exception:
                    pass

                msg += "\n🔗 <a href='https://stockscreener4.streamlit.app'>Open Screener</a>"

                resp = _req.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": channel, "text": msg,
                          "parse_mode": "HTML",
                          "disable_web_page_preview": True},
                    timeout=15,
                )
                if resp.status_code == 200:
                    st.success("✅ Sent to @NSEStockSignals!")
                else:
                    st.error(f"Telegram error: {resp.text}")



# ── Live intraday position monitor ────────────────────────────────────────────
from data.market_status import is_market_open
from datetime import date as _date

if is_market_open():
    today_str = _date.today().isoformat()
    log_live = get_signal_logger()
    open_intraday = [
        s for s in log_live.get_open_signals(timeframe="INTRADAY")
        if s.get("signal_date") == today_str
    ]

    if open_intraday:
        st.subheader("⚡ Live Intraday Positions")
        st.caption("Prices refresh on each page load. Use the button below to close positions that hit stop/target.")

        import yfinance as yf

        for sig in open_intraday:
            ticker   = sig["ticker"]
            entry    = sig["entry_price"]
            stop     = sig["stop_loss"]
            t1       = sig["target_1"]
            t2       = sig["target_2"]
            direction = sig["direction"]

            # Fetch latest price
            try:
                curr_price = float(yf.Ticker(ticker).fast_info.last_price)
            except Exception:
                curr_price = None

            col_name, col_entry, col_curr, col_pnl, col_sl, col_t1, col_status = st.columns([2,1,1,1,1,1,2])
            col_name.markdown(f"**{ticker.replace('.NS','')}**  \n{sig.get('strategy','')}")
            col_entry.metric("Entry", f"₹{entry:,.2f}")

            if curr_price is not None:
                pnl_pct = (curr_price - entry) / entry * 100 if direction == "LONG" else (entry - curr_price) / entry * 100
                col_curr.metric("Current", f"₹{curr_price:,.2f}", f"{pnl_pct:+.2f}%")
                col_pnl.metric("P&L", f"{pnl_pct:+.2f}%")

                # Distance to stop and T1
                dist_stop = abs(curr_price - stop) / entry * 100
                dist_t1   = abs(t1 - curr_price) / entry * 100

                col_sl.metric("SL", f"₹{stop:,.2f}", f"{dist_stop:.1f}% away", delta_color="inverse")
                col_t1.metric("T1", f"₹{t1:,.2f}", f"{dist_t1:.1f}% away")

                # Status badge
                if direction == "LONG":
                    if curr_price <= stop:
                        status_html = '<span style="color:#ef5350;font-weight:bold">🔴 STOPPED</span>'
                    elif curr_price >= t2:
                        status_html = '<span style="color:#26a69a;font-weight:bold">🎯 T2 HIT</span>'
                    elif curr_price >= t1:
                        status_html = '<span style="color:#26a69a;font-weight:bold">✅ T1 HIT</span>'
                    elif dist_stop < 0.5:
                        status_html = '<span style="color:#ff9800;font-weight:bold">⚠️ Near SL</span>'
                    else:
                        status_html = '<span style="color:#aaa">🟡 Active</span>'
                else:  # SHORT
                    if curr_price >= stop:
                        status_html = '<span style="color:#ef5350;font-weight:bold">🔴 STOPPED</span>'
                    elif curr_price <= t2:
                        status_html = '<span style="color:#26a69a;font-weight:bold">🎯 T2 HIT</span>'
                    elif curr_price <= t1:
                        status_html = '<span style="color:#26a69a;font-weight:bold">✅ T1 HIT</span>'
                    elif dist_stop < 0.5:
                        status_html = '<span style="color:#ff9800;font-weight:bold">⚠️ Near SL</span>'
                    else:
                        status_html = '<span style="color:#aaa">🟡 Active</span>'

                col_status.markdown(status_html, unsafe_allow_html=True)
            else:
                col_curr.metric("Current", "N/A")
                col_sl.metric("SL", f"₹{stop:,.2f}")
                col_t1.metric("T1", f"₹{t1:,.2f}")
                col_status.markdown("—")

            st.divider()

        if st.button("🔄 Resolve Closed Positions Now", type="primary"):
            from signals.outcome_tracker import update_open_signal_outcomes
            n = update_open_signal_outcomes(timeframe="INTRADAY", position_size_inr=float(position_size))
            st.success(f"Resolved {n} position(s).")
            st.rerun()

        st.markdown("---")

# ── Fetch data ─────────────────────────────────────────────────────────────────
log  = get_signal_logger()
perf = log.get_performance_summary(timeframe=timeframe, days_back=days_back)
signals = log.get_signals(
    timeframe=timeframe, strategy=strategy,
    outcome=outcome_filter, days_back=days_back,
)

# ── Performance summary ────────────────────────────────────────────────────────
st.subheader("Performance Summary")

total_closed = perf["won"] + perf["lost"] + perf["squared_off"]

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
c1.metric("Total Signals",  perf["total"])
c2.metric("Open",           perf["open"])
c3.metric("Won (T1+T2)",    perf["won"])
c4.metric("Stopped",        perf["lost"])
c5.metric("Squared Off",    perf["squared_off"],
          help="Intraday positions closed at market end (3:30 PM)")
c6.metric("Win Rate",
          f"{perf['win_rate']}%" if total_closed > 0 else "—")
avg_r = perf.get("avg_r")
c7.metric("Avg R (gross)",
          f"{avg_r:+.2f}R" if avg_r is not None else "—",
          help="Average R-multiple before costs on all closed trades.")
net_pnl_total = perf.get("total_net_pnl_inr")
c8.metric("Total Net P&L",
          f"₹{net_pnl_total:+,.0f}" if net_pnl_total is not None else "—",
          help=f"After brokerage, STT, exchange, stamp, GST  (₹{position_size:,}/trade)")


if perf["total"] == 0:
    st.info(
        "No signals logged yet. Generate signals from the **Swing Trades** or "
        "**Intraday Ideas** pages — they are automatically saved here."
    )
    st.stop()

# ── Charts ─────────────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

OUTCOME_LABELS = {
    OUTCOME_TARGET2:     "Target 2 Hit",
    OUTCOME_TARGET1:     "Target 1 Hit",
    OUTCOME_STOPPED:     "Stopped Out",
    OUTCOME_SQUARED_OFF: "Squared Off",
    OUTCOME_EXPIRED:     "Expired",
    OUTCOME_OPEN:        "Still Open",
}
OUTCOME_COLORS = {
    OUTCOME_TARGET2:     "#00C896",
    OUTCOME_TARGET1:     "#5AD8A6",
    OUTCOME_STOPPED:     "#F4664A",
    OUTCOME_SQUARED_OFF: "#FAAD14",
    OUTCOME_EXPIRED:     "#9BA7B4",
    OUTCOME_OPEN:        "#D9D9D9",
}
OUTCOME_EMOJI = {
    OUTCOME_TARGET2:     "✅✅",
    OUTCOME_TARGET1:     "✅",
    OUTCOME_STOPPED:     "❌",
    OUTCOME_SQUARED_OFF: "🔔",
    OUTCOME_EXPIRED:     "⏳",
    OUTCOME_OPEN:        "🔵",
}

with chart_col1:
    st.subheader("Outcome Distribution")
    by_outcome = perf.get("by_outcome", {})
    if by_outcome:
        labels = [OUTCOME_LABELS.get(k, k) for k in by_outcome]
        values = list(by_outcome.values())
        colors = [OUTCOME_COLORS.get(k, "#cccccc") for k in by_outcome]
        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            hole=0.4, textinfo="label+percent",
        ))
        fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280, showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

with chart_col2:
    st.subheader("Cumulative Net P&L (₹)")
    # Use net_pnl_inr when available, else gross R proxy
    # Respect the hide-squared-off setting for the equity curve too
    _chart_signals = journal_signals if hide_squared_off else signals
    closed = [
        s for s in _chart_signals
        if s["outcome"] not in (OUTCOME_OPEN,)
        and s.get("outcome_at")
    ]
    if closed:
        closed_sorted = sorted(closed, key=lambda x: x["outcome_at"])
        dates, cum_pnl = [], []
        running = 0.0
        for s in closed_sorted:
            val = s.get("net_pnl_inr")
            if val is None:
                # fallback: gross pnl_r scaled to risk amount
                r = s.get("pnl_r") or 0.0
                sl_pct = (s.get("sl_pct") or 2.0) / 100
                val = r * sl_pct * position_size
            running += val
            dates.append(s["outcome_at"][:10])
            cum_pnl.append(running)

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=dates, y=cum_pnl,
            mode="lines+markers",
            line=dict(color="#1890FF" if running >= 0 else "#F4664A", width=2),
            marker=dict(size=5),
            fill="tozeroy",
            fillcolor="rgba(24,144,255,0.1)" if running >= 0 else "rgba(244,100,74,0.1)",
            hovertemplate="Date: %{x}<br>Cumulative P&L: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_eq.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig_eq.update_layout(
            yaxis_title="Net P&L (₹)", xaxis_title="",
            margin=dict(t=10, b=40, l=60, r=10), height=280,
        )
        st.plotly_chart(fig_eq, use_container_width=True)
    else:
        st.info("No resolved trades yet for equity curve.")

# ── Strategy breakdown ─────────────────────────────────────────────────────────
by_strat = perf.get("by_strategy", {})
if by_strat:
    st.subheader("Strategy Breakdown")
    strat_rows = []
    for name, s in by_strat.items():
        strat_rows.append({
            "Strategy":       name,
            "Total":          s["total"],
            "Won":            s["wins"],
            "Stopped":        s["losses"],
            "Win Rate":       f"{s['win_rate']}%" if (s["wins"] + s["losses"]) > 0 else "—",
            "Avg R (gross)":  f"{s['avg_r']:+.2f}" if s.get("avg_r") is not None else "—",
            "Net P&L (₹)":    f"₹{s['net_pnl_inr']:+,.0f}" if s.get("net_pnl_inr") is not None else "—",
            "Avg Net P&L":    f"₹{s['avg_net_pnl']:+,.0f}" if s.get("avg_net_pnl") is not None else "—",
        })
    st.dataframe(pd.DataFrame(strat_rows).set_index("Strategy"), use_container_width=True)

# ── Stale-open signal banner ──────────────────────────────────────────────────
_today_iso = _date.today().isoformat()
_stale_open = [
    s for s in signals
    if s["outcome"] == OUTCOME_OPEN and s["signal_date"] < _today_iso
]
if _stale_open:
    st.warning(
        f"⚠️ **{len(_stale_open)} signal(s) are still marked OPEN from past dates.** "
        "Click **Resolve Open Signals Now** in the sidebar to fetch latest prices and update outcomes.",
        icon="⚠️",
    )

# ── Apply hide-squared-off filter to the journal (not the perf summary) ───────
journal_signals = signals
if hide_squared_off and outcome_opt != OUTCOME_SQUARED_OFF:
    journal_signals = [s for s in signals if s["outcome"] != OUTCOME_SQUARED_OFF]

# ── Signal history table ───────────────────────────────────────────────────────
_sq_hidden = len(signals) - len(journal_signals)
_hidden_note = f" — {_sq_hidden} Squared Off hidden" if _sq_hidden else ""
st.subheader(f"Trade Journal ({len(journal_signals)} records{_hidden_note})")

if not journal_signals:
    st.info("No signals match the current filters.")
    st.stop()

rows = []
for s in journal_signals:
    patterns = s.get("patterns", "[]")
    if isinstance(patterns, str):
        try:
            patterns = json.loads(patterns)
        except Exception:
            patterns = []

    outcome_str = OUTCOME_EMOJI.get(s["outcome"], "") + " " + s["outcome"]

    # Cost and net P&L display
    cost_total = s.get("cost_total_inr")
    net_pnl    = s.get("net_pnl_inr")
    net_pnl_r  = s.get("net_pnl_r")

    rows.append({
        "Date":          s["signal_date"],
        "Entry Time":    (s.get("logged_at") or "")[:16],
        "Exit Time":     (s.get("outcome_at") or "—")[:16],
        "Ticker":        s["ticker"],
        "TF":            s["timeframe"],
        "Strategy":      s["strategy"],
        "Dir":           s["direction"],
        "Entry ₹":       s["entry_price"],
        "SL ₹":          s["stop_loss"],
        "T1 ₹":          s["target_1"],
        "T2 ₹":          s["target_2"],
        "R:R":           s["risk_reward"],
        "Conf":          "★" * (s["confidence"] or 1),
        "Outcome":       outcome_str,
        "Exit ₹":        s.get("outcome_price") or "",
        "Gross R":       s.get("pnl_r") or "",
        "Cost ₹":        cost_total if cost_total is not None else "",
        "Net P&L ₹":     net_pnl   if net_pnl   is not None else "",
        "Net R":         net_pnl_r if net_pnl_r is not None else "",
        "Sector":        s.get("sector", ""),
    })

df_display = pd.DataFrame(rows)


def _color_money(val):
    if val == "" or val is None:
        return ""
    try:
        v = float(val)
        if v > 0:  return "color: #00C896; font-weight:600"
        if v < 0:  return "color: #F4664A; font-weight:600"
    except (TypeError, ValueError):
        pass
    return ""


def _fmt(v, decimals=2):
    if v == "" or v is None:
        return ""
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


styled = (
    df_display.style
    .map(_color_money, subset=["Gross R", "Net P&L ₹", "Net R"])
    .format({
        "Entry ₹": "{:.2f}", "SL ₹": "{:.2f}", "T1 ₹": "{:.2f}",
        "T2 ₹":   "{:.2f}", "R:R":  "{:.2f}",
        "Exit ₹":    lambda v: _fmt(v),
        "Gross R":   lambda v: f"{float(v):+.2f}R" if v != "" else "",
        "Cost ₹":    lambda v: f"₹{float(v):.2f}" if v != "" else "",
        "Net P&L ₹": lambda v: f"₹{float(v):+,.2f}" if v != "" else "",
        "Net R":     lambda v: f"{float(v):+.2f}R" if v != "" else "",
    })
)
st.dataframe(styled, use_container_width=True, height=520)

# ── Cost breakdown expander ────────────────────────────────────────────────────
with st.expander("Cost Methodology"):
    st.markdown(f"""
**Transaction cost model** *(NSE equity, discount broker — ₹{position_size:,} position)*

| Charge | Intraday | Swing/Delivery |
|--------|----------|----------------|
| Brokerage | ₹20/order × 2 legs | ₹20/order × 2 legs |
| STT | 0.025% of sell value | 0.1% of total turnover |
| Exchange (NSE) | 0.00345% of turnover | 0.00345% of turnover |
| Stamp Duty | 0.003% of buy value | 0.015% of buy value |
| SEBI Charges | 0.0001% of turnover | 0.0001% of turnover |
| GST | 18% on broker+exchange+SEBI | 18% on broker+exchange+SEBI |

*All cost figures scale linearly with position size. Adjust in the sidebar.*
""")

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
    "Intraday positions are always squared off at 3:30 PM close if no target/stop fires. "
    "Use **Force Resolve** in the sidebar to refresh manually."
)
