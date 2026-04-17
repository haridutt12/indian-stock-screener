"""
Page 7: Signal Log & Performance Dashboard
"""
import json
import time
import datetime as _dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import pytz

try:
    from signals.signal_logger import (
        get_signal_logger,
        OUTCOME_OPEN, OUTCOME_TARGET1, OUTCOME_TARGET2,
        OUTCOME_STOPPED, OUTCOME_SQUARED_OFF, OUTCOME_EXPIRED,
    )
    from signals.trade_costs import DEFAULT_POSITION_SIZE_INR
    _import_error = None
except Exception as _exc:
    import traceback as _tb
    _import_error = _tb.format_exc()

st.set_page_config(page_title="Signal Log", layout="wide", page_icon="📋")
from ui.styles import inject_global_css; inject_global_css()

if _import_error:
    st.error("Import error — check logs.")
    st.code(_import_error, language="python")
    st.stop()

IST = pytz.timezone("Asia/Kolkata")

# ── Constants ──────────────────────────────────────────────────────────────────
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
    OUTCOME_STOPPED:     "#ff4d6d",
    OUTCOME_SQUARED_OFF: "#f0b429",
    OUTCOME_EXPIRED:     "#6b7a99",
    OUTCOME_OPEN:        "#7c83fd",
}
OUTCOME_BADGE = {
    OUTCOME_TARGET2:     ("T2 HIT",  "#00C896"),
    OUTCOME_TARGET1:     ("T1 HIT",  "#5AD8A6"),
    OUTCOME_STOPPED:     ("STOPPED", "#ff4d6d"),
    OUTCOME_SQUARED_OFF: ("SQ OFF",  "#f0b429"),
    OUTCOME_EXPIRED:     ("EXPIRED", "#6b7a99"),
    OUTCOME_OPEN:        ("OPEN",    "#7c83fd"),
}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    timeframe_opt = st.selectbox("Timeframe", ["All", "INTRADAY", "SWING"])
    timeframe     = None if timeframe_opt == "All" else timeframe_opt

    strategy_opts = ["All", "Opening Range Breakout", "VWAP Bounce",
                     "Trend Pullback", "Volume Breakout", "Oversold Reversal", "Bullish Setup"]
    strategy_opt = st.selectbox("Strategy", strategy_opts)
    strategy     = None if strategy_opt == "All" else strategy_opt

    days_back = st.slider("History (days)", 7, 180, 60)

    st.divider()
    st.subheader("Cost Settings")
    position_size = st.number_input(
        "Position Size (₹)", min_value=10_000, max_value=10_000_000,
        value=int(DEFAULT_POSITION_SIZE_INR), step=10_000,
        help="Capital per trade used to calculate ₹ costs and P&L.",
    )

    st.divider()
    st.subheader("📣 Telegram")
    if st.button("📊 Send Market Update", use_container_width=True):
        import requests as _req, html as _html
        try:
            token   = st.secrets["TELEGRAM_BOT_TOKEN"]
            channel = st.secrets["TELEGRAM_CHANNEL_ID"]
        except Exception:
            import os
            token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
            channel = os.getenv("TELEGRAM_CHANNEL_ID", "")

        if not token or not channel:
            st.error("Telegram secrets not set.")
        else:
            with st.spinner("Sending…"):
                now_str = _dt.datetime.now(IST).strftime("%d %b %Y %H:%M IST")
                msg = f"📊 <b>NSE Market Update</b>\n🕐 {now_str}\n\n"
                try:
                    from data.fetcher import fetch_index_data
                    from config.settings import INDICES
                    for iname, ticker in list(INDICES.items())[:3]:
                        df = fetch_index_data(ticker, period="5d", interval="1d")
                        if df is not None and len(df) >= 2:
                            price = float(df["Close"].iloc[-1])
                            chg   = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
                            arrow = "🟢" if chg >= 0 else "🔴"
                            msg  += f"{arrow} <b>{iname}</b>: {price:,.0f} ({chg:+.2f}%)\n"
                except Exception:
                    pass
                try:
                    from data.news_fetcher import fetch_market_news
                    news = fetch_market_news(use_cache=True)
                    if news:
                        msg += "\n📰 <b>Latest Headlines:</b>\n"
                        for n in news[:3]:
                            msg += f"• {_html.unescape(n.get('title',''))[:70]}\n"
                except Exception:
                    pass
                import os as _os
                app_url = _os.getenv("STREAMLIT_APP_URL", "https://stockscreener4.streamlit.app")
                msg += f"\n🔗 <a href='{app_url}'>Open Screener</a>"
                try:
                    resp = _req.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": channel, "text": msg,
                              "parse_mode": "HTML", "disable_web_page_preview": True},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        st.success("Sent!")
                    else:
                        st.error(f"Telegram error: {resp.text}")
                except Exception as _e:
                    st.error(str(_e))

# ── Auto-resolve open signals ──────────────────────────────────────────────────
log       = get_signal_logger()
today_str = _dt.date.today().isoformat()
now_ist   = _dt.datetime.now(IST)
market_closed = now_ist.hour > 15 or (now_ist.hour == 15 and now_ist.minute >= 31)

_last_resolve   = st.session_state.get("_last_resolve_ts", 0)
_should_resolve = (time.time() - _last_resolve) > 300  # throttle to once every 5 min

if _should_resolve:
    open_all = log.get_open_signals()
    st.session_state["_last_resolve_ts"] = time.time()
    if open_all:
        try:
            from signals.outcome_tracker import update_open_signal_outcomes
            n = update_open_signal_outcomes(position_size_inr=float(position_size))
            if n:
                st.rerun()
        except Exception as _e:
            st.warning(f"Auto-resolve error: {_e}")

# ── Data ───────────────────────────────────────────────────────────────────────
perf    = log.get_performance_summary(timeframe=timeframe, days_back=days_back)
signals = log.get_signals(timeframe=timeframe, strategy=strategy, days_back=days_back)

open_signals   = [s for s in signals if s["outcome"] == OUTCOME_OPEN]
closed_signals = [s for s in signals if s["outcome"] != OUTCOME_OPEN]

# ── Page header ────────────────────────────────────────────────────────────────
st.title("📋 Signal Log & Performance")

# ── KPI row ────────────────────────────────────────────────────────────────────
total_closed = perf["won"] + perf["lost"] + perf["squared_off"]
win_rate_str = f"{perf['win_rate']}%" if total_closed > 0 else "—"
net_pnl      = perf.get("total_net_pnl_inr")
net_pnl_str  = f"₹{net_pnl:+,.0f}" if net_pnl is not None else "—"
avg_r        = perf.get("avg_r")
avg_r_str    = f"{avg_r:+.2f}R" if avg_r is not None else "—"

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Signals",   perf["total"])
k2.metric("Open",            perf["open"])
k3.metric("Won (T1+T2)",     perf["won"])
k4.metric("Stopped",         perf["lost"])
k5.metric("Win Rate",        win_rate_str)
k6.metric("Net P&L",         net_pnl_str,
          help=f"After all transaction costs · ₹{position_size:,}/trade")

if perf["total"] == 0:
    st.info(
        "No signals yet. Generate signals from **Swing Trades** or **Intraday Ideas** "
        "— they are automatically saved here."
    )
    st.stop()

# ── Charts ─────────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

with ch1:
    st.subheader("Outcome Distribution")
    by_outcome = perf.get("by_outcome", {})
    if by_outcome:
        labels = [OUTCOME_LABELS.get(k, k) for k in by_outcome]
        values = list(by_outcome.values())
        colors = [OUTCOME_COLORS.get(k, "#ccc") for k in by_outcome]
        fig = go.Figure(go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            hole=0.45, textinfo="label+percent",
        ))
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=260,
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

with ch2:
    st.subheader("Cumulative Net P&L (₹)")
    closed_with_date = [
        s for s in closed_signals
        if s["outcome"] not in (OUTCOME_OPEN,) and s.get("outcome_at")
    ]
    if closed_with_date:
        closed_sorted = sorted(closed_with_date, key=lambda x: x["outcome_at"])
        dates, cum_pnl = [], []
        running = 0.0
        for s in closed_sorted:
            val = s.get("net_pnl_inr")
            if val is None:
                r      = s.get("pnl_r") or 0.0
                sl_frac = (s.get("sl_pct") or 2.0) / 100
                val    = r * sl_frac * position_size
            running += val
            dates.append(s["outcome_at"][:10])
            cum_pnl.append(running)

        line_color = "#00C896" if running >= 0 else "#ff4d6d"
        fill_color = "rgba(0,200,150,0.08)" if running >= 0 else "rgba(255,77,109,0.08)"
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=dates, y=cum_pnl, mode="lines+markers",
            line=dict(color=line_color, width=2),
            marker=dict(size=4),
            fill="tozeroy", fillcolor=fill_color,
            hovertemplate="Date: %{x}<br>Net P&L: ₹%{y:,.0f}<extra></extra>",
        ))
        fig2.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.15)")
        fig2.update_layout(
            yaxis_title="₹", margin=dict(t=10, b=30, l=50, r=10), height=260,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No closed trades yet.")

# ── Strategy breakdown ─────────────────────────────────────────────────────────
by_strat = perf.get("by_strategy", {})
if by_strat:
    with st.expander("Strategy Breakdown", expanded=False):
        rows = []
        for sname, s in by_strat.items():
            rows.append({
                "Strategy":    sname,
                "Total":       s["total"],
                "Won":         s["wins"],
                "Stopped":     s["losses"],
                "Win Rate":    f"{s['win_rate']}%" if (s["wins"] + s["losses"]) > 0 else "—",
                "Avg R":       f"{s['avg_r']:+.2f}" if s.get("avg_r") is not None else "—",
                "Net P&L ₹":  f"₹{s['net_pnl_inr']:+,.0f}" if s.get("net_pnl_inr") is not None else "—",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Strategy"), use_container_width=True)

st.divider()

# ── Open Positions — live fragment (no full-page refresh) ──────────────────────
from data.market_status import is_market_open

is_live = is_market_open()
_pos_interval = 300 if is_live else None


@st.fragment(run_every=_pos_interval)
def _open_positions_panel():
    _is_live = is_market_open()
    _now     = _dt.datetime.now(IST)

    # Re-fetch from DB on every tick — resolved positions disappear automatically
    _open = [
        s for s in log.get_open_signals()
        if (timeframe is None or s["timeframe"] == timeframe)
        and (strategy is None or s["strategy"] == strategy)
    ]
    if not _open:
        return

    st.subheader(f"Open Positions ({len(_open)})")
    if _is_live:
        _ts = _now.strftime("%H:%M:%S")
        st.caption(f"↻ {_ts} IST · updates every 5 min")

    _triggered_any = False   # tracks whether any position hit target/stop (needs resolve)

    for sig in _open:
        ticker    = sig["ticker"]
        entry     = sig["entry_price"]
        stop      = sig["stop_loss"]
        t1        = sig["target_1"]
        t2        = sig["target_2"]
        direction = sig["direction"]
        label     = ticker.replace(".NS", "")
        is_long   = direction == "LONG"
        dir_color = "#00c896" if is_long else "#ff4d6d"
        dir_arrow = "↑" if is_long else "↓"
        sl_dist   = abs(entry - stop)   # total SL distance

        curr_price = None
        if _is_live:
            try:
                curr_price = float(yf.Ticker(ticker).fast_info.last_price)
            except Exception:
                pass

        if curr_price is not None:
            pnl_pct   = (
                (curr_price - entry) / entry * 100 if is_long
                else (entry - curr_price) / entry * 100
            )
            pnl_color = "#00c896" if pnl_pct >= 0 else "#ff4d6d"

            # SL-distance-relative consumption (0 = at entry, 1 = at stop)
            if sl_dist > 0:
                sl_consumed = (
                    (entry - curr_price) / sl_dist if is_long
                    else (curr_price - entry) / sl_dist
                )
            else:
                sl_consumed = 0.0

            if is_long:
                if curr_price <= stop:
                    sl, sc = "STOPPED", "#ff4d6d"; _triggered_any = True
                elif curr_price >= t2:
                    sl, sc = "T2 HIT",  "#00c896"; _triggered_any = True
                elif curr_price >= t1:
                    sl, sc = "T1 HIT",  "#5AD8A6"; _triggered_any = True
                elif sl_consumed > 0.65:       # >65% of SL distance consumed
                    sl, sc = "NEAR SL", "#f0b429"
                else:
                    sl, sc = "ACTIVE",  "#7c83fd"
            else:
                if curr_price >= stop:
                    sl, sc = "STOPPED", "#ff4d6d"; _triggered_any = True
                elif curr_price <= t2:
                    sl, sc = "T2 HIT",  "#00c896"; _triggered_any = True
                elif curr_price <= t1:
                    sl, sc = "T1 HIT",  "#5AD8A6"; _triggered_any = True
                elif sl_consumed > 0.65:
                    sl, sc = "NEAR SL", "#f0b429"
                else:
                    sl, sc = "ACTIVE",  "#7c83fd"

            curr_block   = (
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:4px;">Current</div>'
                f'<div style="font-size:1rem;font-weight:800;color:#e2e8f0;">₹{curr_price:,.2f}</div>'
                f'<div style="font-size:0.8rem;font-weight:700;color:{pnl_color};margin-top:2px;">'
                f'{pnl_pct:+.2f}%</div></div>'
            )
            status_block = (
                f'<span style="background:{sc}22;color:{sc};border:1px solid {sc}44;'
                f'border-radius:6px;padding:4px 12px;font-size:0.78rem;font-weight:700;">{sl}</span>'
            )
        else:
            curr_block   = (
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:4px;">Current</div>'
                f'<div style="font-size:0.85rem;color:#6b7a99;">Market closed</div></div>'
            )
            status_block = (
                f'<span style="background:#7c83fd22;color:#7c83fd;border:1px solid #7c83fd44;'
                f'border-radius:6px;padding:4px 12px;font-size:0.78rem;font-weight:700;">OPEN</span>'
            )

        days_held = (_dt.date.today() - _dt.date.fromisoformat(sig["signal_date"])).days
        days_str  = f"{days_held}d held" if days_held > 0 else "today"
        strat_str = f'{sig.get("strategy","")} · {sig.get("timeframe","")} · {days_str}'

        html = (
            f'<div style="background:linear-gradient(145deg,#1e2235,#181c2e);'
            f'border:1px solid rgba(255,255,255,0.07);border-left:4px solid {dir_color};'
            f'border-radius:14px;padding:16px 20px;margin:8px 0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="font-size:1.1rem;font-weight:800;color:#e2e8f0;">{label}</span>'
            f'<span style="background:{dir_color}18;color:{dir_color};border:1px solid {dir_color}44;'
            f'border-radius:6px;padding:2px 8px;font-size:0.72rem;font-weight:700;">'
            f'{dir_arrow} {direction}</span>'
            f'<span style="color:#6b7a99;font-size:0.75rem;">{strat_str}</span>'
            f'</div>{status_block}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;">'
            f'<div style="text-align:center;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:4px;">Entry</div>'
            f'<div style="font-size:1rem;font-weight:700;color:#e2e8f0;">₹{entry:,.2f}</div></div>'
            + curr_block
            + f'<div style="text-align:center;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:4px;">Stop Loss</div>'
            f'<div style="font-size:1rem;font-weight:700;color:#ff4d6d;">₹{stop:,.2f}</div></div>'
            f'<div style="text-align:center;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:4px;">Target 1</div>'
            f'<div style="font-size:1rem;font-weight:700;color:#00c896;">₹{t1:,.2f}</div></div>'
            f'<div style="text-align:center;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:4px;">Target 2</div>'
            f'<div style="font-size:1rem;font-weight:700;color:#4ade80;">₹{t2:,.2f}</div></div>'
            f'</div></div>'
        )
        st.markdown(html, unsafe_allow_html=True)

    # If any live price shows a trigger, resolve immediately so Trade Journal updates
    if _triggered_any:
        _tkey  = "_trigger_resolve_ts"
        _tlast = st.session_state.get(_tkey, 0)
        if time.time() - _tlast > 60:   # at most once per minute
            try:
                from signals.outcome_tracker import update_open_signal_outcomes
                n = update_open_signal_outcomes(position_size_inr=float(position_size))
                st.session_state[_tkey] = time.time()
                st.session_state["_last_resolve_ts"] = time.time()
                if n:
                    st.rerun()          # full page rerun → Trade Journal refreshes
            except Exception:
                pass

    st.divider()


_open_positions_panel()

# ── Closed Trade Journal ───────────────────────────────────────────────────────
st.subheader(f"Trade Journal — {len(closed_signals)} closed trades")

if not closed_signals:
    st.info("No closed trades yet for the selected filters.")
    st.stop()

rows = []
for s in closed_signals:
    outcome_label, outcome_color = OUTCOME_BADGE.get(s["outcome"], (s["outcome"], "#6b7a99"))
    net_pnl_val = s.get("net_pnl_inr")
    pnl_r_val   = s.get("pnl_r")

    rows.append({
        "Date":       s["signal_date"],
        "Ticker":     s["ticker"].replace(".NS", ""),
        "TF":         s["timeframe"],
        "Dir":        s["direction"],
        "Strategy":   s["strategy"],
        "Entry ₹":    round(s["entry_price"], 2),
        "Exit ₹":     round(s.get("outcome_price") or 0, 2) or "",
        "SL ₹":       round(s["stop_loss"], 2),
        "T1 ₹":       round(s["target_1"], 2),
        "T2 ₹":       round(s["target_2"], 2),
        "Outcome":    s["outcome"],
        "Gross R":    round(pnl_r_val, 2) if pnl_r_val is not None else "",
        "Net P&L ₹":  round(net_pnl_val, 2) if net_pnl_val is not None else "",
        "Conf":       "★" * (s.get("confidence") or 1),
        "Sector":     s.get("sector", ""),
        "Exit Time":  (s.get("outcome_at") or "")[:16],
    })

df_j = pd.DataFrame(rows)


def _badge_outcome(val):
    label, color = OUTCOME_BADGE.get(val, (val, "#6b7a99"))
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}44;'
        f'border-radius:4px;padding:2px 7px;font-size:0.72rem;font-weight:700;">'
        f'{label}</span>'
    )


def _color_pnl(val):
    if val == "" or val is None:
        return ""
    try:
        v = float(val)
        if v > 0: return "color:#00C896;font-weight:600"
        if v < 0: return "color:#ff4d6d;font-weight:600"
    except (TypeError, ValueError):
        pass
    return ""


styled = (
    df_j.style
    .map(_color_pnl, subset=["Gross R", "Net P&L ₹"])
    .format({
        "Entry ₹": lambda v: f"₹{v:,.2f}" if v != "" else "",
        "Exit ₹":  lambda v: f"₹{float(v):,.2f}" if v != "" else "—",
        "SL ₹":    lambda v: f"₹{v:,.2f}" if v != "" else "",
        "T1 ₹":    lambda v: f"₹{v:,.2f}" if v != "" else "",
        "T2 ₹":    lambda v: f"₹{v:,.2f}" if v != "" else "",
        "Gross R":    lambda v: f"{float(v):+.2f}R" if v != "" else "—",
        "Net P&L ₹":  lambda v: f"₹{float(v):+,.0f}" if v != "" else "—",
    })
)
st.dataframe(styled, use_container_width=True, height=480, hide_index=True)

# Download
csv = df_j.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇ Download CSV",
    data=csv,
    file_name=f"signal_log_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)

with st.expander("Transaction Cost Model"):
    st.markdown(f"""
| Charge | Intraday | Swing |
|--------|----------|-------|
| Brokerage | ₹20/order × 2 | ₹20/order × 2 |
| STT | 0.025% sell-side | 0.1% turnover |
| Exchange (NSE) | 0.00345% | 0.00345% |
| Stamp Duty | 0.003% buy | 0.015% buy |
| SEBI | 0.0001% | 0.0001% |
| GST | 18% on above | 18% on above |

*Position size: ₹{position_size:,} · figures scale linearly*
""")
