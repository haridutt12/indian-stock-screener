"""
Page 7: Signal Log & Performance Dashboard
"""
import logging
import time
import datetime as _dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import pytz

logger = logging.getLogger(__name__)

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

st.set_page_config(page_title="Signal Log · NiftyEdge", layout="wide", page_icon="📋")
from ui.styles import inject_global_css, page_header, show_loading, auth_guard, user_sidebar; inject_global_css()
auth_guard()

# ── Module-level helpers ────────────────────────────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def _market_regime():
    """Detect current Nifty trend, daily volatility, and India VIX fear level."""
    result = {"trend": "UNKNOWN", "volatility": "UNKNOWN", "vix": None, "fear": "UNKNOWN", "nifty": None}
    try:
        df = yf.Ticker("^NSEI").history(period="60d", interval="1d", auto_adjust=True)
        if df is not None and len(df) >= 20:
            close = df["Close"]
            curr  = float(close.iloc[-1])
            sma20 = float(close.rolling(20).mean().iloc[-1])
            result["nifty"] = curr
            result["trend"] = "BULLISH" if curr > sma20 else "BEARISH"
            daily_vol = float(close.pct_change().dropna().tail(10).std() * 100)
            if daily_vol < 0.7:   result["volatility"] = "LOW"
            elif daily_vol < 1.2: result["volatility"] = "NORMAL"
            else:                 result["volatility"] = "HIGH"
    except Exception:
        pass
    try:
        vdf = yf.Ticker("^INDIAVIX").history(period="5d", interval="1d", auto_adjust=True)
        if vdf is not None and not vdf.empty:
            v = float(vdf["Close"].iloc[-1])
            result["vix"]  = v
            result["fear"] = "CALM" if v < 15 else ("NEUTRAL" if v < 20 else "FEARFUL")
    except Exception:
        pass
    return result


_STRATEGY_TYPE = {
    "Trend Pullback":         "TREND",
    "Volume Breakout":        "BREAKOUT",
    "Oversold Reversal":      "REVERSAL",
    "Bullish Setup":          "TREND",
    "Golden Cross":           "MOMENTUM",
    "Supertrend Reversal":    "REVERSAL",
    "Opening Range Breakout": "BREAKOUT",
    "VWAP Bounce":            "MEAN_REVERT",
    "EMA Crossover":          "MOMENTUM",
    "Supertrend Signal":      "TREND",
    # New swing LONG
    "52W High Breakout":      "MOMENTUM",
    "BB Squeeze Breakout":    "BREAKOUT",
    "EMA Stack Pullback":     "TREND",
    # SHORT strategies
    "Death Cross":            "MOMENTUM",
    "Overbought Reversal":    "REVERSAL",
    "Trend Breakdown":        "BREAKOUT",
    "52W Low Breakdown":      "MOMENTUM",
    # New intraday
    "Gap and Go":             "BREAKOUT",
    "VWAP Reclaim":           "MEAN_REVERT",
    # New swing REVERSAL / intraday pivot
    "RSI Divergence":         "REVERSAL",
    "Camarilla Pivot":        "MEAN_REVERT",
}


def _regime_fit(stype: str, trend: str, volatility: str, fear: str) -> int:
    """Return 0-100 fit score for a strategy type in the current regime."""
    s = 50
    if stype == "TREND":
        s += 25 if trend == "BULLISH" else -25
        s += 10 if volatility == "LOW" else (-15 if volatility == "HIGH" else 0)
    elif stype == "MOMENTUM":
        s += 20 if trend == "BULLISH" else -20
        s += -20 if volatility == "HIGH" else 0
        s += -15 if fear == "FEARFUL" else 0
    elif stype == "BREAKOUT":
        s += 25 if volatility == "HIGH" else (-20 if volatility == "LOW" else 0)
    elif stype == "REVERSAL":
        s += 20 if trend == "BEARISH" else -10
        s += 15 if fear == "FEARFUL" else 0
        s += 10 if volatility in ("NORMAL", "HIGH") else 0
    elif stype == "MEAN_REVERT":
        s += 10 if volatility == "LOW" else (-10 if volatility == "HIGH" else 5)
    return max(0, min(100, s))


if _import_error:
    st.error("Import error — check logs.")
    st.code(_import_error, language="python")
    st.stop()

IST = pytz.timezone("Asia/Kolkata")

OUTCOME_LABELS = {
    OUTCOME_TARGET2:     "Target 2 Hit",
    OUTCOME_TARGET1:     "Target 1 Hit",
    OUTCOME_STOPPED:     "Stopped Out",
    OUTCOME_SQUARED_OFF: "Squared Off",
    OUTCOME_EXPIRED:     "Expired",
    OUTCOME_OPEN:        "Open",
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

# ── Sidebar ──────────────────────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    timeframe_opt = st.selectbox("Timeframe", ["All", "SWING", "INTRADAY"])
    timeframe     = None if timeframe_opt == "All" else timeframe_opt

    period_opt = st.selectbox("Period", ["Last 7 days", "Last 30 days", "Last 60 days", "Last 90 days", "All time"])
    _period_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 60 days": 60, "Last 90 days": 90, "All time": 365}
    days_back   = _period_map[period_opt]

    st.divider()
    st.subheader("Cost Settings")
    position_size = st.number_input(
        "Position Size (₹)", min_value=10_000, max_value=10_000_000,
        value=int(DEFAULT_POSITION_SIZE_INR), step=10_000,
        help="Capital per trade used to calculate costs and P&L.",
    )

    st.divider()
    st.subheader("🔔 Price Alerts")
    try:
        from config.stock_universe import NIFTY_50, NIFTY_200
        _alert_universe = {**NIFTY_50, **NIFTY_200}
    except Exception:
        _alert_universe = {}
    with st.form("price_alert_form", clear_on_submit=True):
        _al_stock = st.selectbox("Stock", sorted(_alert_universe.keys()), key="pa_stock")
        _al_price = st.number_input("Alert Price (₹)", min_value=0.01, value=100.0,
                                     step=0.5, format="%.2f", key="pa_price")
        _al_cond  = st.radio("Trigger when price", ["above", "below"], horizontal=True, key="pa_cond")
        _al_label = st.text_input("Label (optional)", key="pa_label", max_chars=60)
        _al_submit = st.form_submit_button("Set Alert", type="primary", use_container_width=True)

    if _al_submit and _alert_universe:
        _al_ticker = _alert_universe.get(_al_stock, _al_stock)
        if not _al_ticker.endswith(".NS"):
            _al_ticker += ".NS"
        _al_id = get_signal_logger().add_price_alert(
            ticker=_al_ticker,
            alert_price=float(_al_price),
            condition=_al_cond,
            label=_al_label.strip(),
        )
        if _al_id > 0:
            st.success(f"Alert set: {_al_stock} {_al_cond} ₹{_al_price:,.2f}")
        else:
            st.error("Failed to save alert. Check logs.")

    # Show active alerts
    try:
        _active_alerts = get_signal_logger().get_active_alerts()
        if _active_alerts:
            st.caption(f"{len(_active_alerts)} active alert{'s' if len(_active_alerts)!=1 else ''}")
            for _pal in _active_alerts:
                _pa_ticker_disp = _pal["ticker"].replace(".NS", "")
                _pa_col1, _pa_col2 = st.columns([4, 1])
                with _pa_col1:
                    _pa_cond_arrow = "↑" if _pal["condition"] == "above" else "↓"
                    st.markdown(
                        f'<div style="font-size:0.72rem;color:#e2e8f0;padding:2px 0;">'
                        f'<b>{_pa_ticker_disp}</b> {_pa_cond_arrow} ₹{_pal["alert_price"]:,.2f}'
                        + (f'<br><span style="color:#64748b;font-size:0.62rem;">{_pal["label"]}</span>' if _pal.get("label") else "")
                        + '</div>',
                        unsafe_allow_html=True,
                    )
                with _pa_col2:
                    if st.button("✕", key=f"del_alert_{_pal['id']}", help="Remove alert"):
                        get_signal_logger().delete_price_alert(_pal["id"])
                        st.rerun()
    except Exception:
        pass

    st.divider()
    user_sidebar()
# ── Core data ─────────────────────────────────────────────────────────────────────────────────────────────
log       = get_signal_logger()
today_str = _dt.date.today().isoformat()
now_ist   = _dt.datetime.now(IST)

# Run dedup on every page load — no session-state guard.
# Step 1: expire all but the latest OPEN per ticker (one open position rule).
# Step 2: purge exact row-level duplicates (same ticker+strategy+timeframe+date).
try:
    log.close_duplicate_open_positions()
except Exception:
    pass
try:
    _dup_n = log.get_duplicate_count()
    if _dup_n and _dup_n > 0:
        log.purge_duplicates()
        logger.info("Signal Log: purged %d duplicate row(s) on page load.", _dup_n)
except Exception:
    pass

# Auto-resolve: always run when market is open or signals are stale; throttle to 5 min otherwise
from data.market_status import is_market_open as _is_mkt_open
_mkt_live   = _is_mkt_open()
_open_all   = log.get_open_signals()
_last_res   = st.session_state.get("_last_resolve_ts", 0)
_has_stale  = any(s["signal_date"] < today_str for s in _open_all)
_should_res = _has_stale or _mkt_live or (time.time() - _last_res) > 300

if _should_res and _open_all:
    try:
        from signals.outcome_tracker import update_open_signal_outcomes
        _n = update_open_signal_outcomes(position_size_inr=float(position_size))
        st.session_state["_last_resolve_ts"] = time.time()
        if _n:
            st.rerun()
    except Exception as _resolve_err:
        st.session_state["_resolve_error"] = str(_resolve_err)
    if not _has_stale:
        st.session_state["_last_resolve_ts"] = time.time()

if st.session_state.get("_resolve_error"):
    st.warning(f"Outcome resolver error: {st.session_state['_resolve_error']}")
    st.session_state.pop("_resolve_error", None)

perf    = log.get_performance_summary(timeframe=timeframe, days_back=days_back)
signals = log.get_signals(timeframe=timeframe, days_back=days_back)
# Use get_open_signals() for open positions — it enforces one per ticker via GROUP BY.
# Never derive open positions from get_signals() which can contain historical duplicates.
open_signals   = _open_all
closed_signals = [s for s in signals if s["outcome"] != OUTCOME_OPEN]

# ── Page header ──────────────────────────────────────────────────────────────────────────────────────────────
_mkt_live = _is_mkt_open()  # re-check after data load (may have crossed market open)
_dot_col  = "#00c896" if _mkt_live else "#f0b429"
_dot_rgb  = "0,200,150" if _mkt_live else "240,180,41"
_pulse    = "animation:pulse 1.4s ease-in-out infinite;" if _mkt_live else ""

hcol1, hcol2 = st.columns([3, 1])
with hcol1:
    page_header("📋 Signal Log", subtitle="NSE · Trade Journal · Forward Test")
with hcol2:
    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
    _run_scan = st.button("▶ Run Scan Now", type="primary", use_container_width=True)

# ── Run Scan ────────────────────────────────────────────────────────────────────────────────────────────────
if _run_scan:
    _gen_slot = show_loading("Running full Nifty 50 technical scan — RSI, MACD, Supertrend, volume anomalies…", "#f0b429")
    try:
        from signals.swing_signals import generate_swing_signals
        from config.stock_universe import NIFTY_50
        tickers = list(NIFTY_50.values())
        new_sigs = generate_swing_signals(tickers, use_cache=False)
        n_new    = sum(1 for s in new_sigs)
        _gen_slot.empty()
        st.success(f"Scan complete — {len(new_sigs)} swing signal(s) generated, {n_new} logged.")
    except Exception as _e:
        _gen_slot.empty()
        st.error(f"Scan error: {_e}")

        if _mkt_live:
            try:
                from signals.intraday_signals import generate_intraday_signals
                from config.stock_universe import NIFTY_50
                i_sigs = generate_intraday_signals(list(NIFTY_50.values()))
                if i_sigs:
                    st.info(f"{len(i_sigs)} intraday signal(s) also generated.")
            except Exception:
                pass
        st.rerun()

# ── Signal Ranker ───────────────────────────────────────────────────────────────────────────────────────────────────
from signals.signal_ranker import rank_signals as _rank_signals

_top3 = _rank_signals(open_signals)[:3]

# ── TOP 3 PANEL ───────────────────────────────────────────────────────────────────────────────────────────────
if _top3:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:700;color:#f0b429;'
        'text-transform:uppercase;letter-spacing:0.1em;margin:4px 0 10px;">'
        '⭐ Best Trades Right Now — Top 3 Ranked Signals</div>',
        unsafe_allow_html=True,
    )

    _rank_colors  = ["#f0b429", "#94a3b8", "#cd7f32"]
    _rank_labels  = ["#1 Best Setup", "#2 Strong Setup", "#3 Good Setup"]
    _rank_borders = ["rgba(240,180,41,0.5)", "rgba(148,163,184,0.4)", "rgba(205,127,50,0.4)"]
    _rank_bgs     = ["rgba(240,180,41,0.06)", "rgba(148,163,184,0.04)", "rgba(205,127,50,0.04)"]

    top3_cols = st.columns(3)
    for _rank_i, (_score, _bd, _sig, _cp) in enumerate(_top3):
        _rc   = _rank_colors[_rank_i]
        _rb   = _rank_borders[_rank_i]
        _rbg  = _rank_bgs[_rank_i]
        _rl   = _rank_labels[_rank_i]
        _tick = _sig["ticker"].replace(".NS", "")
        _dir  = _sig.get("direction", "LONG")
        _dc   = "#00c896" if _dir == "LONG" else "#ff4d6d"
        _da   = "↑ LONG" if _dir == "LONG" else "↓ SHORT"
        _entry = float(_sig.get("entry_price") or 0)
        _sl    = float(_sig.get("stop_loss")   or 0)
        _t1    = float(_sig.get("target_1")    or 0)
        _t2    = float(_sig.get("target_2")    or 0)
        _rr    = float(_sig.get("risk_reward") or 0)
        _strat = _sig.get("strategy", "")
        _conf  = _sig.get("confidence", 0)
        _prox  = _bd.get("_prox_label", "")
        _cp_fmt = f"₹{_cp:,.2f}" if _cp else "—"

        # Score bar segments (widths proportional to max possible per factor)
        _factors = [
            ("Conf",   _bd.get("Confidence",   0), 25, "#7c83fd"),
            ("Tech",   _bd.get("Technical",    0), 20, "#a5b4fc"),
            ("Fund",   _bd.get("Fundamental",  0), 15, "#00c896"),
            ("R:R",    _bd.get("Risk/Reward",  0), 20, "#f0b429"),
            ("Entry",  _bd.get("Entry Timing", 0), 20, "#34d399"),
        ]
        bar_segs = "".join([
            f'<div title="{fn}: {fv:.0f}/{fm}" style="height:4px;width:{fv/100*100:.0f}%;'
            f'background:{fc};border-radius:2px;flex:0 0 {fm}%;"></div>'
            for fn, fv, fm, fc in _factors
        ])

        with top3_cols[_rank_i]:
            st.markdown(
                f'<div style="background:{_rbg};border:1px solid {_rb};'
                f'border-top:3px solid {_rc};border-radius:14px;padding:16px 18px;">'

                # Rank badge + ticker
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">'
                f'<div>'
                f'<div style="font-size:0.6rem;font-weight:700;color:{_rc};text-transform:uppercase;'
                f'letter-spacing:0.1em;margin-bottom:4px;">{_rl}</div>'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:1.15rem;font-weight:800;color:#e2e8f0;">{_tick}</span>'
                f'<span style="background:{_dc}22;color:{_dc};border:1px solid {_dc}44;'
                f'border-radius:4px;padding:1px 7px;font-size:0.68rem;font-weight:700;">{_da}</span>'
                f'</div>'
                f'<div style="color:#64748b;font-size:0.7rem;margin-top:3px;">{_strat}</div>'
                f'</div>'
                # Score circle
                f'<div style="text-align:center;">'
                f'<div style="font-size:1.4rem;font-weight:900;color:{_rc};line-height:1;">{_score:.0f}</div>'
                f'<div style="font-size:0.58rem;color:#475569;font-weight:600;">/ 100</div>'
                f'</div>'
                f'</div>'

                # Score breakdown bar
                f'<div style="display:flex;gap:2px;margin-bottom:10px;height:4px;">{bar_segs}</div>'

                # Price grid
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px;">'
                f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:6px 8px;">'
                f'<div style="font-size:0.55rem;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:2px;">Entry</div>'
                f'<div style="font-size:0.85rem;font-weight:700;color:#e2e8f0;">₹{_entry:,.2f}</div>'
                f'</div>'
                f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:6px 8px;">'
                f'<div style="font-size:0.55rem;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:2px;">Now</div>'
                f'<div style="font-size:0.85rem;font-weight:700;color:#f1f5f9;">{_cp_fmt}</div>'
                f'</div>'
                f'<div style="background:rgba(255,77,109,0.08);border-radius:6px;padding:6px 8px;">'
                f'<div style="font-size:0.55rem;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:2px;">Stop Loss</div>'
                f'<div style="font-size:0.85rem;font-weight:700;color:#ff4d6d;">₹{_sl:,.2f}</div>'
                f'</div>'
                f'<div style="background:rgba(0,200,150,0.06);border-radius:6px;padding:6px 8px;">'
                f'<div style="font-size:0.55rem;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:2px;">Target 1</div>'
                f'<div style="font-size:0.85rem;font-weight:700;color:#00c896;">₹{_t1:,.2f}</div>'
                f'</div>'
                f'</div>'

                # R:R + Entry timing + Stars
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="background:rgba(124,131,253,0.12);color:#7c83fd;border-radius:4px;'
                f'padding:2px 8px;font-size:0.68rem;font-weight:700;">R:R {_rr:.1f}×</span>'
                f'<span style="margin-left:6px;color:{"#00c896" if "✓" in _prox or "below" in _prox else "#f0b429" if "missed" not in _prox and "late" not in _prox else "#ff4d6d"};'
                f'font-size:0.68rem;font-weight:600;">{_prox}</span>'
                f'</div>'
                f'<div>{"★" * _conf}<span style="color:#374151;">{"★" * (5-_conf)}</span></div>'
                f'</div>'

                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)
    st.caption(
        "Score = Confidence (25) + Technical (20) + Fundamental (15) + Risk/Reward (20) + Entry Timing (20). "
        "Entry Timing drops to 0 when price has moved >5% past your entry."
    )
    st.divider()

elif open_signals:
    pass  # signals exist but prices not fetched yet — tabs show them normally

# ── Tabs ───────────────────────────────────────────────────────────────────────────────────────────────────
tab_live, tab_perf, tab_hist, tab_insights = st.tabs(["📍 Live Positions", "📊 Performance", "📜 History", "🧠 Insights"])

# ╔═══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — LIVE POSITIONS                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════════╝
with tab_live:

    # Status bar
    _last_ts   = st.session_state.get("_last_resolve_ts", 0)
    _mins_ago  = int((time.time() - _last_ts) / 60) if _last_ts else None
    st.markdown(
        f'<div style="background:rgba({_dot_rgb},0.05);border:1px solid rgba({_dot_rgb},0.15);'
        f'border-radius:10px;padding:10px 16px;display:flex;align-items:center;'
        f'justify-content:space-between;margin-bottom:16px;">'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="width:7px;height:7px;border-radius:50%;background:{_dot_col};{_pulse}"></div>'
        f'<span style="color:{_dot_col};font-weight:700;font-size:0.8rem;">'
        f'{"Market Live" if _mkt_live else "Market Closed"}</span>'
        f'<span style="color:#475569;font-size:0.75rem;margin-left:4px;">'
        f'{"· prices updating live" if _mkt_live else "· showing last close"}</span>'
        f'</div>'
        f'<span style="color:#475569;font-size:0.72rem;">'
        f'{len(_open_all)} open · checked {f"{_mins_ago}m ago" if _mins_ago else "on load"}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _check_col, _dedup_col, _ = st.columns([1, 1, 2])
    with _check_col:
        if st.button("🔄 Check Outcomes Now", use_container_width=True):
            _res_slot = show_loading("Fetching live prices and checking SL/T1/T2 hits for all open signals…", "#00c896")
            try:
                from signals.outcome_tracker import update_open_signal_outcomes
                _n = update_open_signal_outcomes(position_size_inr=float(position_size))
                _res_slot.empty()
                st.session_state["_last_resolve_ts"] = time.time()
                if _n:
                    st.success(f"Resolved {_n} signal(s).")
                    st.rerun()
                else:
                    st.info("Nothing resolved — all signals still active.")
            except Exception as _e:
                _res_slot.empty()
                st.error(str(_e))

    with _dedup_col:
        _dup_count = log.get_duplicate_count()
        _btn_label = f"🧹 Fix Duplicates ({_dup_count} extra rows)" if _dup_count > 0 else "✅ No Duplicates"
        if st.button(_btn_label, use_container_width=True, disabled=(_dup_count == 0)):
            _dup_slot = show_loading("Removing duplicate open positions, keeping the most recent per ticker…", "#7c83fd")
            _removed = log.purge_duplicates()
            _dup_slot.empty()
            if _removed > 0:
                st.success(f"Removed {_removed} duplicate row(s). Refreshing…")
                st.rerun()
            elif _removed == 0:
                st.info("No duplicates found.")
            else:
                st.error("Dedup failed — check logs.")

    # Filter open signals by sidebar timeframe AND period
    _cutoff_date = (_dt.date.today() - _dt.timedelta(days=days_back)).isoformat()
    _open_filtered = [
        s for s in _open_all
        if (timeframe is None or s["timeframe"] == timeframe)
        and (days_back >= 365 or s["signal_date"] >= _cutoff_date)
    ]

    if not _open_filtered:
        st.markdown(
            '<div style="background:rgba(124,131,253,0.06);border:1px solid rgba(124,131,253,0.12);'
            'border-radius:14px;padding:32px;text-align:center;margin:16px 0;">'
            '<div style="font-size:1.8rem;margin-bottom:10px;">💭</div>'
            '<div style="color:#e2e8f0;font-weight:700;margin-bottom:6px;">No open positions</div>'
            '<div style="color:#475569;font-size:0.82rem;line-height:1.6;">'
            'Run a scan to generate signals — they appear here automatically as open trades.'
            '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        # ── Market context bar: VIX + F&O ban list ──────────────────────────
        try:
            from data.fno_ban import get_fno_ban_list
            _fno_ban = get_fno_ban_list()
        except Exception:
            _fno_ban = []

        try:
            import yfinance as _yf_ctx
            _vdf = _yf_ctx.Ticker("^INDIAVIX").history(period="1y", interval="1d", auto_adjust=True)
            _vix_curr = float(_vdf["Close"].iloc[-1]) if not _vdf.empty else None
            _vix_hist = _vdf["Close"].dropna().tolist() if not _vdf.empty else []
            _vix_rank = None
            if _vix_curr and _vix_hist:
                _vh, _vl = max(_vix_hist), min(_vix_hist)
                _vix_rank = round((_vix_curr - _vl) / (_vh - _vl) * 100, 0) if _vh != _vl else 50.0
        except Exception:
            _vix_curr = _vix_rank = None

        if _vix_curr:
            _vix_col = "#ff4d6d" if (_vix_rank or 0) >= 70 else ("#f0b429" if (_vix_rank or 0) >= 40 else "#00c896")
            _vix_label = "FEAR — hedge or reduce size" if (_vix_rank or 0) >= 70 else ("ELEVATED — trade smaller" if (_vix_rank or 0) >= 40 else "CALM — normal sizing ok")
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                f'border-radius:10px;padding:10px 16px;margin-bottom:12px;'
                f'display:flex;align-items:center;gap:20px;">'
                f'<span style="font-size:0.62rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">India VIX</span>'
                f'<span style="font-size:0.9rem;font-weight:800;color:{_vix_col};">{_vix_curr:.1f}</span>'
                f'<span style="font-size:0.7rem;color:#475569;">Rank {_vix_rank:.0f}% (1Y)</span>'
                f'<span style="font-size:0.72rem;color:{_vix_col};font-weight:600;">→ {_vix_label}</span>'
                + (f'<span style="margin-left:auto;font-size:0.68rem;color:#f0b429;">⚠ F&O Ban: {", ".join(_fno_ban[:8])}{"…" if len(_fno_ban)>8 else ""}</span>'
                   if _fno_ban else '')
                + f'</div>',
                unsafe_allow_html=True,
            )

        @st.fragment(run_every=60 if _mkt_live else None)
        def _live_positions():
            _is_live = _is_mkt_open()
            _auto_resolve_ids = []  # signal_ids where price has hit SL or T2 (terminal)
            _t1_hit_ids = []        # signal_ids where price is at T1 (offer trail/book choice)

            # "Last updated" strip
            _now_fmt = _dt.datetime.now(IST).strftime("%H:%M:%S IST")
            _upd_parts = [f"Last updated: {_now_fmt}"]
            if _is_live:
                # Countdown to 3:30 PM IST square-off
                _sq_time = _dt.datetime.now(IST).replace(hour=15, minute=30, second=0, microsecond=0)
                _secs_left = int((_sq_time - _dt.datetime.now(IST)).total_seconds())
                if _secs_left > 0:
                    _h, _rem = divmod(_secs_left, 3600)
                    _m, _s   = divmod(_rem, 60)
                    _cdown   = f"{_h:02d}:{_m:02d}:{_s:02d}"
                    _cdown_col = "#ff4d6d" if _secs_left < 900 else ("#f0b429" if _secs_left < 3600 else "#00c896")
                    _upd_parts.append(
                        f'<span style="color:{_cdown_col};font-weight:700;">'
                        f'⏱ Intraday SQ-OFF in {_cdown}</span>'
                    )
            st.markdown(
                f'<div style="font-size:0.72rem;color:#475569;margin-bottom:10px;">'
                f'{"  ·  ".join(_upd_parts)}</div>',
                unsafe_allow_html=True,
            )

            for sig in _open_filtered:
                ticker    = sig["ticker"]
                entry     = sig["entry_price"]
                stop      = sig["stop_loss"]
                t1        = sig["target_1"]
                t2        = sig["target_2"]
                direction = sig["direction"]
                is_long   = direction == "LONG"
                label     = ticker.replace(".NS", "")
                dir_col   = "#00c896" if is_long else "#ff4d6d"
                dir_arr   = "↑ LONG" if is_long else "↓ SHORT"
                _ban_badge = (
                    '<span style="background:rgba(240,180,41,0.15);color:#f0b429;'
                    'border:1px solid rgba(240,180,41,0.3);border-radius:5px;'
                    'padding:2px 8px;font-size:0.65rem;font-weight:700;">⚠ F&O BAN</span>'
                    if label in (_fno_ban or []) else ""
                )

                curr_price = None
                # Always try fast_info first — returns last trade price
                # (live during market hours, last close when market is shut)
                try:
                    _lp = yf.Ticker(ticker).fast_info.last_price
                    if _lp is not None and not pd.isna(_lp) and float(_lp) > 0:
                        curr_price = float(_lp)
                except Exception:
                    pass
                # Fallback: last daily close from 5-day window (always available for .NS)
                if curr_price is None:
                    try:
                        _df = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
                        if not _df.empty:
                            _lc = _df["Close"].dropna().iloc[-1]
                            if not pd.isna(_lc) and float(_lc) > 0:
                                curr_price = float(_lc)
                    except Exception:
                        pass

                # Format entry and exit datetimes
                _raw_entry = sig.get("logged_at") or sig.get("signal_date", "")
                try:
                    _entry_dt  = _dt.datetime.strptime(_raw_entry[:19], "%Y-%m-%d %H:%M:%S")
                    _entry_fmt = _entry_dt.strftime("%d %b %Y · %H:%M IST")
                except Exception:
                    _entry_fmt = _raw_entry[:16] or "—"

                _raw_exit  = sig.get("outcome_at") or ""
                if _raw_exit:
                    try:
                        _exit_dt  = _dt.datetime.strptime(_raw_exit[:19], "%Y-%m-%d %H:%M:%S")
                        _exit_fmt = _exit_dt.strftime("%d %b %Y · %H:%M IST")
                    except Exception:
                        _exit_fmt = _raw_exit[:16]
                else:
                    _exit_fmt = "Active"

                if curr_price is not None:
                    days_held = (_dt.date.today() - _dt.date.fromisoformat(sig["signal_date"])).days

                    # Determine status first (based on current price vs levels)
                    if is_long:
                        if curr_price <= stop:                                  status_l, status_c = "STOPPED",    "#ff4d6d"
                        elif curr_price >= t2:                                  status_l, status_c = "T2 HIT",     "#00c896"
                        elif curr_price >= t1:                                  status_l, status_c = "T1 HIT",     "#5AD8A6"
                        elif (entry - curr_price) / abs(entry - stop) > 0.6:   status_l, status_c = "NEAR SL",    "#f0b429"
                        elif days_held >= 3 and abs((curr_price - entry) / entry * 100) < 1.5:
                                                                                status_l, status_c = "STALE",      "#64748b"
                        else:                                                   status_l, status_c = "ACTIVE",     "#7c83fd"
                    else:
                        if curr_price >= stop:                                  status_l, status_c = "STOPPED",    "#ff4d6d"
                        elif curr_price <= t2:                                  status_l, status_c = "T2 HIT",     "#00c896"
                        elif curr_price <= t1:                                  status_l, status_c = "T1 HIT",     "#5AD8A6"
                        elif (curr_price - entry) / abs(stop - entry) > 0.6:   status_l, status_c = "NEAR SL",    "#f0b429"
                        elif days_held >= 3 and abs((entry - curr_price) / entry * 100) < 1.5:
                                                                                status_l, status_c = "STALE",      "#64748b"
                        else:                                                   status_l, status_c = "ACTIVE",     "#7c83fd"

                    # Queue auto-resolution: only terminal levels
                    if status_l in ("STOPPED", "T2 HIT"):
                        _auto_resolve_ids.append(sig["signal_id"])
                    elif status_l == "T1 HIT":
                        _t1_hit_ids.append(sig["signal_id"])

                    # P&L shown at trigger price when a level is hit — not at current drifted price
                    if status_l == "STOPPED":
                        display_price = stop
                    elif status_l == "T1 HIT":
                        display_price = t1
                    elif status_l == "T2 HIT":
                        display_price = t2
                    else:
                        display_price = curr_price

                    pnl_pct = ((display_price - entry) / entry * 100) if is_long else ((entry - display_price) / entry * 100)
                    pnl_inr = pnl_pct / 100 * float(position_size)
                    pnl_col = "#00c896" if pnl_pct >= 0 else "#ff4d6d"

                    # Progress bar: entry=0%, T2=100%, SL=negative
                    total_range = t2 - entry if is_long else entry - t2
                    if total_range > 0:
                        progress = ((curr_price - entry) / total_range * 100) if is_long else ((entry - curr_price) / total_range * 100)
                        progress = max(-50, min(110, progress))
                    else:
                        progress = 0

                    bar_fill_w = max(0, min(100, progress))
                    bar_color  = "#00c896" if progress >= 50 else "#f0b429" if progress >= 0 else "#ff4d6d"
                    days_str   = f"{days_held}d" if days_held > 0 else "today"

                    html = (
                        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                        f'border:1px solid rgba(255,255,255,0.07);border-left:4px solid {dir_col};'
                        f'border-radius:14px;padding:16px 18px;margin:8px 0;">'

                        # Header row
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
                        f'<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.05rem;font-weight:800;color:#e2e8f0;">{label}</span>'
                        f'<span style="background:{dir_col}22;color:{dir_col};border:1px solid {dir_col}44;'
                        f'border-radius:5px;padding:2px 8px;font-size:0.7rem;font-weight:700;">{dir_arr}</span>'
                        f'<span style="color:#475569;font-size:0.72rem;">{sig.get("strategy","")} · {sig.get("timeframe","")} · held {days_str}</span>'
                        f'{_ban_badge}'
                        f'</div>'
                        f'<span style="background:{status_c}22;color:{status_c};border:1px solid {status_c}44;'
                        f'border-radius:6px;padding:3px 12px;font-size:0.78rem;font-weight:700;">{status_l}</span>'
                        f'</div>'

                        # Entry / Exit datetime strip
                        f'<div style="display:flex;gap:20px;margin-bottom:12px;">'
                        f'<span style="font-size:0.68rem;color:#475569;">'
                        f'<span style="color:#6b7a99;font-weight:600;">Entry</span> {_entry_fmt}</span>'
                        f'<span style="font-size:0.68rem;color:#475569;">'
                        f'<span style="color:#6b7a99;font-weight:600;">Exit</span> '
                        f'<span style="color:{"#94a3b8" if _exit_fmt == "Active" else "#e2e8f0"}">{_exit_fmt}</span>'
                        f'</span>'
                        f'</div>'

                        # Price grid
                        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:14px;">'

                        f'<div style="text-align:center;">'
                        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px;">Entry</div>'
                        f'<div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;">₹{entry:,.2f}</div></div>'

                        f'<div style="text-align:center;">'
                        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px;">{"At "+status_l if status_l in ("T1 HIT","T2 HIT","STOPPED") else "Current"}</div>'
                        f'<div style="font-size:0.95rem;font-weight:800;color:#f1f5f9;">₹{display_price:,.2f}</div>'
                        f'<div style="font-size:0.78rem;font-weight:700;color:{pnl_col};">{pnl_pct:+.2f}% · ₹{pnl_inr:+,.0f}</div></div>'

                        f'<div style="text-align:center;">'
                        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px;">Stop Loss</div>'
                        f'<div style="font-size:0.95rem;font-weight:700;color:#ff4d6d;">₹{stop:,.2f}</div>'
                        f'<div style="font-size:0.72rem;color:#475569;">{abs(entry-stop)/entry*100:.1f}% away</div></div>'

                        f'<div style="text-align:center;">'
                        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px;">Target 1</div>'
                        f'<div style="font-size:0.95rem;font-weight:700;color:#5AD8A6;">₹{t1:,.2f}</div>'
                        f'<div style="font-size:0.72rem;color:#475569;">{abs(t1-entry)/entry*100:.1f}% away</div></div>'

                        f'<div style="text-align:center;">'
                        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px;">Target 2</div>'
                        f'<div style="font-size:0.95rem;font-weight:700;color:#00c896;">₹{t2:,.2f}</div>'
                        f'<div style="font-size:0.72rem;color:#475569;">{abs(t2-entry)/entry*100:.1f}% away</div></div>'

                        f'</div>'

                        # Progress bar: SL ──── entry ──── T1 ──── T2
                        f'<div style="margin-top:4px;">'
                        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                        f'<span style="font-size:0.62rem;color:#ff4d6d;">◄ SL</span>'
                        f'<span style="font-size:0.62rem;color:#6b7a99;">Entry</span>'
                        f'<span style="font-size:0.62rem;color:#5AD8A6;">T1</span>'
                        f'<span style="font-size:0.62rem;color:#00c896;">T2 ►</span>'
                        f'</div>'
                        f'<div style="background:rgba(255,255,255,0.06);border-radius:4px;height:6px;overflow:hidden;">'
                        f'<div style="width:{bar_fill_w}%;height:100%;background:{bar_color};border-radius:4px;'
                        f'transition:width 0.3s ease;"></div></div>'
                        f'</div>'
                        f'</div>'
                    )
                    st.markdown(html, unsafe_allow_html=True)

                    # ── Options Strategy Suggestion ───────────────────────────────────────
                    try:
                        from analysis.options import suggest_options_strategy
                        _iv_rank_pos = _vix_rank if "_vix_rank" in dir() else None
                        _opt_strat = suggest_options_strategy(direction, _iv_rank_pos, entry, strike_step=50.0)
                        with st.expander(f"📐 Options hedge for {label} — {_opt_strat['name']}", expanded=False):
                            _leg_html = " · ".join(
                                f'<b style="color:{"#00c896" if l["action"]=="BUY" else "#ff4d6d"};">'
                                f'{l["action"]} {l["type"]} {l["strike"]:,.0f}</b>'
                                for l in _opt_strat["legs"]
                            )
                            st.markdown(
                                f'<div style="font-size:0.78rem;color:#94a3b8;margin-bottom:8px;">'
                                f'{_leg_html}</div>'
                                f'<div style="font-size:0.72rem;color:#475569;">{_opt_strat["rationale"]}</div>'
                                f'<div style="display:flex;gap:24px;margin-top:8px;">'
                                f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Max Loss</span>'
                                f'<div style="font-size:0.75rem;color:#ff4d6d;">{_opt_strat["max_loss"]}</div></div>'
                                f'<div><span style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;">Max Gain</span>'
                                f'<div style="font-size:0.75rem;color:#00c896;">{_opt_strat["max_gain"]}</div></div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                    except Exception:
                        pass

                    # ── T1 Hit: trail or book panel ──────────────────────────────────────
                    if sig["signal_id"] in _t1_hit_ids:
                        st.markdown(
                            '<div style="background:rgba(90,216,166,0.08);border:1px solid rgba(90,216,166,0.25);'
                            'border-radius:10px;padding:10px 14px;margin:4px 0 8px;">'
                            '<span style="color:#5AD8A6;font-weight:700;font-size:0.82rem;">🎯 Target 1 Reached</span>'
                            '<span style="color:#94a3b8;font-size:0.75rem;margin-left:8px;">'
                            'Book profit now or trail stop to breakeven to chase T2.</span>'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        _t1a, _t1b, _ = st.columns([1, 1, 2])
                        with _t1a:
                            if st.button(
                                "🏃 Trail SL to Entry",
                                key=f"trail_{sig['signal_id']}",
                                use_container_width=True,
                                help="Move stop loss to entry price (breakeven). Keep position open for T2.",
                            ):
                                log.update_stop_loss(sig["signal_id"], entry)
                                st.success(f"Stop loss moved to ₹{entry:,.2f} (breakeven) — chasing T2.")
                                st.rerun()
                        with _t1b:
                            if st.button(
                                "📥 Book T1 Profit",
                                key=f"bookt1_{sig['signal_id']}",
                                use_container_width=True,
                                type="primary",
                                help="Close position at T1 price.",
                            ):
                                from signals.trade_costs import compute_trade_cost as _ctc
                                _costs = _ctc(
                                    entry_price=entry, exit_price=t1,
                                    direction=direction, timeframe=sig.get("timeframe", "SWING"),
                                    position_size_inr=float(position_size), stop_loss=stop,
                                )
                                log.update_outcome(
                                    signal_id=sig["signal_id"], outcome=OUTCOME_TARGET1,
                                    outcome_price=t1,
                                    outcome_at=_dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                                    pnl_r=_costs.get("net_pnl_r"), cost_breakdown=_costs,
                                )
                                try:
                                    from notifications.telegram import notify_trade_resolved
                                    _ep = t1
                                    _pp = (((_ep - entry) / entry * 100) if is_long
                                           else ((entry - _ep) / entry * 100))
                                    notify_trade_resolved(sig, OUTCOME_TARGET1, _ep, _pp)
                                except Exception:
                                    pass
                                st.rerun(scope="app")

                    # ── Mini candlestick chart (in expander) ─────────────────────────────
                    _chart_lbl = "📊 5-min Chart" if sig.get("timeframe") == "INTRADAY" else "📊 Daily Chart"
                    with st.expander(_chart_lbl, expanded=False):
                        try:
                            import plotly.graph_objects as _go
                            if sig.get("timeframe") == "INTRADAY":
                                _cdf = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=True)
                            else:
                                _cdf = yf.Ticker(ticker).history(period="30d", interval="1d", auto_adjust=True)
                            if _cdf is not None and not _cdf.empty:
                                _cfig = _go.Figure(data=[_go.Candlestick(
                                    x=_cdf.index,
                                    open=_cdf["Open"], high=_cdf["High"],
                                    low=_cdf["Low"],   close=_cdf["Close"],
                                    name=label,
                                    increasing_line_color="#00c896",
                                    decreasing_line_color="#ff4d6d",
                                    showlegend=False,
                                )])
                                # Key levels as horizontal lines
                                for _lv, _lc, _ln in [
                                    (entry, "#7c83fd", "Entry"),
                                    (stop,  "#ff4d6d", "SL"),
                                    (t1,    "#5AD8A6", "T1"),
                                    (t2,    "#00c896", "T2"),
                                ]:
                                    _cfig.add_hline(
                                        y=_lv, line_color=_lc, line_width=1.5,
                                        line_dash="dot", annotation_text=_ln,
                                        annotation_position="right",
                                        annotation_font_color=_lc,
                                    )
                                _cfig.update_layout(
                                    height=220, margin=dict(l=0, r=40, t=10, b=0),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
                                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                                )
                                st.plotly_chart(_cfig, use_container_width=True, config={"displayModeBar": False})
                            else:
                                st.caption("Chart data unavailable.")
                        except Exception as _ce:
                            st.caption(f"Chart error: {_ce}")

                else:
                    st.markdown(
                        f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                        f'border-left:4px solid {dir_col};border-radius:14px;padding:14px 18px;margin:8px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<div>'
                        f'<span style="font-size:1rem;font-weight:800;color:#e2e8f0;">{label}</span>'
                        f'<span style="color:#6b7a99;font-size:0.75rem;margin-left:10px;">{sig.get("strategy","")} · {sig.get("timeframe","")}</span>'
                        f'</div>'
                        f'<span style="color:#6b7a99;font-size:0.78rem;">Price unavailable</span>'
                        f'</div>'
                        f'<div style="display:flex;gap:20px;margin:6px 0;">'
                        f'<span style="font-size:0.68rem;color:#475569;">'
                        f'<span style="color:#6b7a99;font-weight:600;">Entry</span> {_entry_fmt}</span>'
                        f'<span style="font-size:0.68rem;color:#475569;">'
                        f'<span style="color:#6b7a99;font-weight:600;">Exit</span> '
                        f'<span style="color:#94a3b8;">{_exit_fmt}</span>'
                        f'</span>'
                        f'</div>'
                        f'<div style="color:#475569;font-size:0.75rem;">'
                        f'Entry ₹{entry:,.2f} · SL ₹{stop:,.2f} · T1 ₹{t1:,.2f} · T2 ₹{t2:,.2f}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

                # ── Square Off ───────────────────────────────────────────────────────────
                _sqkey = f"_sqf_{sig['signal_id']}"
                _sqbcol, _ = st.columns([1, 3])
                with _sqbcol:
                    if st.button(
                        "⎋ Square Off",
                        key=f"sqbtn_{sig['signal_id']}",
                        use_container_width=True,
                        help="Manually close this trade at a custom price",
                    ):
                        st.session_state[_sqkey] = not st.session_state.get(_sqkey, False)
                        st.rerun()
                if st.session_state.get(_sqkey, False):
                    _def_sq_p = round(float(curr_price if curr_price is not None else entry), 2)
                    _sqa, _sqb, _sqc, _sqd = st.columns([2, 1.8, 1, 0.8])
                    with _sqa:
                        _sq_price = st.number_input(
                            "Exit price",
                            min_value=0.01,
                            value=_def_sq_p,
                            format="%.2f",
                            key=f"sqprice_{sig['signal_id']}",
                            label_visibility="collapsed",
                        )
                    with _sqb:
                        _sq_pnl = ((_sq_price - entry) / entry * 100) if is_long else ((entry - _sq_price) / entry * 100)
                        _sq_pcol = "#00c896" if _sq_pnl >= 0 else "#ff4d6d"
                        st.markdown(
                            f'<div style="padding-top:28px;font-size:0.85rem;font-weight:700;color:{_sq_pcol};">'
                            f'P&L: {_sq_pnl:+.2f}% · ₹{_sq_pnl/100*float(position_size):+,.0f}</div>',
                            unsafe_allow_html=True,
                        )
                    with _sqc:
                        if st.button("✓ Confirm", key=f"sqconf_{sig['signal_id']}", type="primary", use_container_width=True):
                            from signals.trade_costs import compute_trade_cost as _ctc
                            _costs = _ctc(
                                entry_price=entry, exit_price=float(_sq_price),
                                direction=direction, timeframe=sig.get("timeframe", "SWING"),
                                position_size_inr=float(position_size), stop_loss=stop,
                            )
                            log.update_outcome(
                                signal_id=sig["signal_id"], outcome=OUTCOME_SQUARED_OFF,
                                outcome_price=float(_sq_price),
                                outcome_at=_dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                                pnl_r=_costs.get("net_pnl_r"), cost_breakdown=_costs,
                            )
                            st.session_state.pop(_sqkey, None)
                            st.rerun(scope="app")
                    with _sqd:
                        if st.button("✗", key=f"sqcancel_{sig['signal_id']}", use_container_width=True):
                            st.session_state.pop(_sqkey, None)
                            st.rerun()

            # Auto-resolve signals where price has crossed SL or T2 (terminal)
            if _auto_resolve_ids and not st.session_state.get("_auto_resolving"):
                st.session_state["_auto_resolving"] = True
                try:
                    from signals.outcome_tracker import update_open_signal_outcomes
                    _n = update_open_signal_outcomes(
                        position_size_inr=float(position_size),
                        notify_on_resolve=_is_live,
                    )
                    st.session_state["_last_resolve_ts"] = time.time()
                    st.session_state["_auto_resolving"] = False
                    if _n:
                        st.rerun()
                except Exception:
                    st.session_state["_auto_resolving"] = False

            # Check price alerts every fragment cycle
            if _is_live:
                try:
                    _active_alerts = log.get_active_alerts()
                    _triggered_count = 0
                    for _pal in _active_alerts:
                        _pa_ticker = _pal["ticker"]
                        _pa_price  = float(_pal["alert_price"])
                        _pa_cond   = _pal["condition"]
                        try:
                            _pa_lp = yf.Ticker(_pa_ticker).fast_info.last_price
                            if _pa_lp is None or pd.isna(_pa_lp) or float(_pa_lp) <= 0:
                                continue
                            _pa_curr = float(_pa_lp)
                        except Exception:
                            continue
                        _triggered = (
                            (_pa_cond == "above" and _pa_curr >= _pa_price) or
                            (_pa_cond == "below" and _pa_curr <= _pa_price)
                        )
                        if _triggered:
                            log.mark_alert_triggered(_pal["id"])
                            _triggered_count += 1
                            try:
                                from notifications.telegram import notify_price_alert
                                notify_price_alert(
                                    ticker=_pa_ticker.replace(".NS", ""),
                                    condition=_pa_cond,
                                    alert_price=_pa_price,
                                    current_price=_pa_curr,
                                    label=_pal.get("label", ""),
                                )
                            except Exception:
                                pass
                    if _triggered_count:
                        st.toast(f"🔔 {_triggered_count} price alert(s) triggered!", icon="🔔")
                        st.rerun()
                except Exception:
                    pass

        _live_positions()


# ╔═══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — PERFORMANCE                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════════╝
with tab_perf:
    _target_wins = perf.get("target_wins", perf["won"])
    _sq_prof     = perf.get("sq_profitable", 0)
    _sq_lose     = perf.get("sq_losing", 0)
    _stops       = perf.get("stops", perf["lost"])
    total_closed = perf["won"] + perf["lost"]
    net_pnl      = perf.get("total_net_pnl_inr")
    avg_r        = perf.get("avg_r")

    # ── KPIs ─────────────────────────────────────────────────────────────────────────────────────────────
    wr_col  = "#00c896" if total_closed > 0 and perf["win_rate"] >= 50 else "#ff4d6d" if total_closed > 0 else "#475569"
    pnl_col = "#00c896" if (net_pnl or 0) >= 0 else "#ff4d6d"
    r_col   = "#00c896" if (avg_r or 0) >= 0 else "#ff4d6d"

    # Win breakdown sub-label: "12W (8T+4SQ) · 9L (7Stop+2SQ)"
    _w_parts = []
    if _target_wins: _w_parts.append(f"{_target_wins}T")
    if _sq_prof:     _w_parts.append(f"{_sq_prof}SQ")
    _l_parts = []
    if _stops:   _l_parts.append(f"{_stops}Stop")
    if _sq_lose: _l_parts.append(f"{_sq_lose}SQ")
    _wl_sub = f'{perf["won"]}W ({"+".join(_w_parts) or "—"}) · {perf["lost"]}L ({"+".join(_l_parts) or "—"})' if total_closed else "No closed trades yet"

    avg_pnl = perf.get("avg_net_pnl_inr")

    # Portfolio return relative to per-trade position size
    _BASE_CAPITAL    = float(position_size)
    _portfolio_pnl   = net_pnl if net_pnl is not None else 0.0
    _portfolio_ret   = _portfolio_pnl / _BASE_CAPITAL * 100 if _BASE_CAPITAL else 0.0
    _port_col        = "#00c896" if _portfolio_pnl >= 0 else "#ff4d6d"
    _port_val_str    = f"₹{_BASE_CAPITAL + _portfolio_pnl:,.0f}"
    _port_ret_str    = f"{_portfolio_ret:+.1f}%"

    kpi_html = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'

        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px;">'
        f'<div style="color:#64748b;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">Win Rate</div>'
        f'<div style="color:{wr_col};font-size:1.6rem;font-weight:800;">{perf["win_rate"]}%</div>'
        f'<div style="color:#475569;font-size:0.68rem;margin-top:3px;line-height:1.5;">{_wl_sub}</div>'
        f'</div>'

        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px;">'
        f'<div style="color:#64748b;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">Net P&L</div>'
        f'<div style="color:{pnl_col};font-size:1.6rem;font-weight:800;">{"₹{:+,.0f}".format(net_pnl) if net_pnl is not None else "—"}</div>'
        f'<div style="color:#475569;font-size:0.72rem;margin-top:3px;">After costs · {"₹{:+,.0f}/trade avg".format(avg_pnl) if avg_pnl is not None else "₹{:,}/trade size".format(int(position_size))}</div>'
        f'</div>'

        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px;">'
        f'<div style="color:#64748b;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">Expectancy (Avg R)</div>'
        f'<div style="color:{r_col};font-size:1.6rem;font-weight:800;">{f"{avg_r:+.2f}R" if avg_r is not None else "—"}</div>'
        f'<div style="color:#475569;font-size:0.72rem;margin-top:3px;">{"Positive edge — system works" if (avg_r or 0) > 0 else ("Negative expectancy — review setups" if (avg_r or 0) < 0 else "Break-even")}</div>'
        f'</div>'

        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);border:1px solid rgba(255,255,255,0.06);'
        f'border-top:2px solid {_port_col}44;border-radius:14px;padding:16px;">'
        f'<div style="color:#64748b;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">Portfolio</div>'
        f'<div style="color:{_port_col};font-size:1.6rem;font-weight:800;">{_port_val_str}</div>'
        f'<div style="color:#475569;font-size:0.72rem;margin-top:3px;">'
        f'<span style="color:{_port_col};font-weight:700;">{_port_ret_str}</span>'
        f' on ₹{int(position_size):,}/trade · {perf["total"]} signals</div>'
        f'</div>'

        f'</div>'
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # Data quality notice
    _expired_n = perf.get("expired", 0)
    if _expired_n > 0:
        st.markdown(
            f'<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.15);'
            f'border-left:3px solid #f0b429;border-radius:10px;padding:10px 16px;'
            f'margin-bottom:12px;font-size:0.75rem;color:#94a3b8;">'
            f'<span style="color:#f0b429;font-weight:700;">ℹ Data note · </span>'
            f'{_expired_n} expired signal(s) in this period are excluded from all P&L metrics. '
            f'A high expired count usually reflects historical duplicate OPEN signals that were '
            f'cleaned up — it does not affect win rate or net P&L, which only count resolved trades. '
            f'Portfolio return shown as % of a single ₹{int(position_size):,} position.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif total_closed > 0:
        st.markdown(
            f'<div style="font-size:0.67rem;color:#374151;margin-bottom:10px;">'
            f'Portfolio return shown as % of ₹{int(position_size):,} position size · '
            f'P&L excludes {_expired_n} expired signal(s)</div>',
            unsafe_allow_html=True,
        )

    if perf["total"] == 0:
        st.markdown(
            '<div style="background:rgba(124,131,253,0.06);border:1px solid rgba(124,131,253,0.12);'
            'border-radius:14px;padding:32px;text-align:center;margin:16px 0;">'
            '<div style="font-size:1.8rem;margin-bottom:10px;">📊</div>'
            '<div style="color:#e2e8f0;font-weight:700;margin-bottom:6px;">No signals in this period</div>'
            '<div style="color:#475569;font-size:0.82rem;line-height:1.6;">'
            'Use <b style="color:#f0b429;">▶ Run Scan Now</b> above to generate signals, '
            'or change the Period filter in the sidebar.'
            '</div></div>',
            unsafe_allow_html=True,
        )
    elif total_closed == 0 and perf["open"] > 0:
        _oldest = min((s["signal_date"] for s in open_signals), default=today_str)
        try:
            _days_open = (_dt.date.today() - _dt.date.fromisoformat(_oldest)).days
            from signals.signal_logger import SWING_EXPIRY_DAYS
            _days_left = max(0, SWING_EXPIRY_DAYS - _days_open)
            _expiry_note = (
                f"Oldest signal is {_days_open}d old — "
                f"{'expiring soon' if _days_left <= 1 else f'expires in ~{_days_left}d'} "
                f"if no SL/target is hit first."
            )
        except Exception:
            _expiry_note = "Signals close when SL or a target is hit, or after the expiry window."
        st.markdown(
            f'<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.15);'
            f'border-radius:14px;padding:24px 28px;margin:16px 0;">'
            f'<div style="color:#f0b429;font-weight:700;margin-bottom:6px;">⏳ {perf["open"]} open signal(s) — no closed trades yet</div>'
            f'<div style="color:#64748b;font-size:0.82rem;line-height:1.7;">'
            f'{_expiry_note}<br>'
            f'Click <b style="color:#f1f5f9;">🔄 Check Outcomes Now</b> in the Live Positions tab to force-resolve any that have hit their levels.'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    else:
        cc1, cc2 = st.columns(2)

        with cc1:
            st.markdown('<div style="font-size:0.78rem;font-weight:700;color:#94a3b8;margin-bottom:6px;">Outcome Distribution</div>', unsafe_allow_html=True)
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
                    margin=dict(t=10, b=10, l=10, r=10), height=240,
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

        with cc2:
            st.markdown('<div style="font-size:0.78rem;font-weight:700;color:#94a3b8;margin-bottom:6px;">Cumulative Net P&L (₹)</div>', unsafe_allow_html=True)
            _closed_dated = sorted(
                [s for s in closed_signals if s.get("outcome_at")],
                key=lambda x: x["outcome_at"],
            )
            if _closed_dated:
                dates, cum = [], []
                running = 0.0
                for s in _closed_dated:
                    val = s.get("net_pnl_inr")
                    if val is None:
                        r    = s.get("pnl_r") or 0.0
                        risk_pct = (abs(s["entry_price"] - s["stop_loss"]) / s["entry_price"]
                                    if s.get("entry_price") and s.get("stop_loss") else 0.02)
                        val  = r * risk_pct * float(position_size)
                    running += val
                    dates.append(s["outcome_at"][:10])
                    cum.append(running)

                lc = "#00C896" if running >= 0 else "#ff4d6d"
                fc = "rgba(0,200,150,0.08)" if running >= 0 else "rgba(255,77,109,0.08)"
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=dates, y=cum, mode="lines+markers",
                    line=dict(color=lc, width=2), marker=dict(size=4),
                    fill="tozeroy", fillcolor=fc,
                    hovertemplate="Date: %{x}<br>Net P&L: ₹%{y:+,.0f}<extra></extra>",
                ))
                fig2.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.15)")
                fig2.update_layout(
                    yaxis_title="₹", margin=dict(t=10, b=30, l=50, r=10), height=240,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.caption("No closed trades yet.")

        by_strat = perf.get("by_strategy", {})
        if by_strat:
            st.markdown(
                '<div style="font-size:0.78rem;font-weight:700;color:#94a3b8;margin:16px 0 4px;">By Strategy</div>'
                '<div style="font-size:0.68rem;color:#475569;margin-bottom:8px;">'
                'Wins = Target hits + profitable squared-off exits &nbsp;·&nbsp; Losses = Stopped out + unprofitable squared-off exits'
                '</div>',
                unsafe_allow_html=True,
            )
            s_rows = []
            for sname, s in by_strat.items():
                s_closed = s["wins"] + s["losses"]
                s_rows.append({
                    "Strategy":   sname,
                    "Total":      s["total"],
                    "Wins":       s["wins"],
                    "Losses":     s["losses"],
                    "Open":       s.get("open_count", 0),
                    "Expired":    s.get("expired_count", 0),
                    "Win Rate":   f"{s['win_rate']}%" if s_closed >= 3 else ("—" if s_closed < 3 else f"{s['win_rate']}%*"),
                    "Avg R (net)": f"{s['avg_r']:+.2f}R" if s.get("avg_r") is not None else "—",
                    "Net P&L ₹":  f"₹{s['net_pnl_inr']:+,.0f}" if s.get("net_pnl_inr") is not None else "—",
                })
            _df_s = pd.DataFrame(s_rows).set_index("Strategy")
            st.dataframe(_df_s, use_container_width=True)
            if any(s["wins"] + s["losses"] < 3 for s in by_strat.values()):
                st.caption("Win Rate shows — for strategies with fewer than 3 closed trades (too small a sample).")

        # ── Sector Allocation + Nifty 50 Benchmark ────────────────────────────
        _perf_c1, _perf_c2 = st.columns(2)

        with _perf_c1:
            st.markdown(
                '<div style="font-size:0.78rem;font-weight:700;color:#94a3b8;margin:16px 0 6px;">'
                'Open Positions — Sector Allocation</div>',
                unsafe_allow_html=True,
            )
            if open_signals:
                _sec_count: dict = {}
                for _s in open_signals:
                    _sec = (_s.get("sector") or "Unknown").strip() or "Unknown"
                    _sec_count[_sec] = _sec_count.get(_sec, 0) + 1
                _sec_labels = list(_sec_count.keys())
                _sec_vals   = list(_sec_count.values())
                _sec_colors = [
                    "#7c83fd", "#00c896", "#f0b429", "#ff4d6d",
                    "#5AD8A6", "#ff8c42", "#a78bfa", "#34d399",
                ][:len(_sec_labels)]
                _sfig = go.Figure(go.Pie(
                    labels=_sec_labels, values=_sec_vals,
                    marker=dict(colors=_sec_colors),
                    hole=0.45,
                    textinfo="label+percent",
                    textfont=dict(size=11),
                ))
                _sfig.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10), height=240,
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_sfig, use_container_width=True)
            else:
                st.caption("No open positions.")

        with _perf_c2:
            st.markdown(
                '<div style="font-size:0.78rem;font-weight:700;color:#94a3b8;margin:16px 0 6px;">'
                'Portfolio Return vs Nifty 50</div>',
                unsafe_allow_html=True,
            )
            if total_closed > 0 and _closed_dated:
                _first_date = _closed_dated[0]["outcome_at"][:10]
                try:
                    _nifty_df = yf.Ticker("^NSEI").history(
                        start=_first_date, end=today_str, interval="1d", auto_adjust=True
                    )
                    if _nifty_df is not None and len(_nifty_df) >= 2:
                        _nifty_start = float(_nifty_df["Close"].iloc[0])
                        _nifty_end   = float(_nifty_df["Close"].iloc[-1])
                        _nifty_ret   = (_nifty_end - _nifty_start) / _nifty_start * 100
                    else:
                        _nifty_ret = None
                except Exception:
                    _nifty_ret = None

                _port_ret_pct = _portfolio_ret
                _bfig = go.Figure()
                _b_labels = ["My Portfolio"]
                _b_values = [_port_ret_pct]
                _b_colors = ["#00c896" if _port_ret_pct >= 0 else "#ff4d6d"]
                if _nifty_ret is not None:
                    _b_labels.append("Nifty 50")
                    _b_values.append(_nifty_ret)
                    _b_colors.append("#7c83fd")

                _bfig.add_trace(go.Bar(
                    x=_b_labels, y=_b_values,
                    marker_color=_b_colors,
                    text=[f"{v:+.1f}%" for v in _b_values],
                    textposition="outside",
                    textfont=dict(size=13, color="#e2e8f0"),
                ))
                _bfig.add_hline(y=0, line_color="rgba(255,255,255,0.15)", line_width=1)
                _bfig.update_layout(
                    margin=dict(t=30, b=20, l=30, r=30), height=240,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(
                        title="Return (%)",
                        gridcolor="rgba(255,255,255,0.04)",
                        ticksuffix="%",
                    ),
                    xaxis=dict(showgrid=False),
                    showlegend=False,
                )
                st.plotly_chart(_bfig, use_container_width=True)
                if _nifty_ret is not None:
                    _alpha = _port_ret_pct - _nifty_ret
                    _alpha_col = "#00c896" if _alpha >= 0 else "#ff4d6d"
                    st.markdown(
                        f'<div style="font-size:0.72rem;color:#475569;text-align:center;margin-top:-8px;">'
                        f'Alpha vs Nifty: <span style="color:{_alpha_col};font-weight:700;">'
                        f'{_alpha:+.1f}%</span> · since {_first_date}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Close trades to see benchmark comparison.")


# ╔═══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 3 — HISTORY                                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════════╝
with tab_hist:
    if not signals:
        st.caption("No signals in the selected period. Change the Period filter or run a scan.")
    else:
        _hist_n_open   = sum(1 for s in signals if s["outcome"] == OUTCOME_OPEN)
        _hist_n_closed = sum(1 for s in signals if s["outcome"] != OUTCOME_OPEN)
        _hist_view = st.radio(
            "Show",
            [f"All ({len(signals)})", f"Open ({_hist_n_open})", f"Closed ({_hist_n_closed})"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if "Open" in _hist_view and "All" not in _hist_view:
            _hist_signals = [s for s in signals if s["outcome"] == OUTCOME_OPEN]
        elif "Closed" in _hist_view:
            _hist_signals = [s for s in signals if s["outcome"] != OUTCOME_OPEN]
        else:
            _hist_signals = signals

        rows = []
        for s in sorted(_hist_signals, key=lambda x: (x["signal_date"], x.get("logged_at", "")), reverse=True):
            _outcome_lbl = OUTCOME_LABELS.get(s["outcome"], s["outcome"])
            _risk_pct    = (abs(s["entry_price"] - s["stop_loss"]) / s["entry_price"] * 100
                            if s.get("entry_price") and s.get("stop_loss") else None)
            rows.append({
                "Date":      s["signal_date"],
                "Ticker":    s["ticker"].replace(".NS", ""),
                "TF":        s["timeframe"],
                "Dir":       s["direction"],
                "Strategy":  s["strategy"],
                "Entry ₹":   round(s["entry_price"], 2),
                "SL ₹":      round(s["stop_loss"], 2),
                "SL %":      round(_risk_pct, 1) if _risk_pct else None,
                "T1 ₹":      round(s["target_1"], 2),
                "T2 ₹":      round(s["target_2"], 2),
                "Exit ₹":    round(s["outcome_price"], 2) if s.get("outcome_price") else None,
                "Outcome":   _outcome_lbl,
                "R":         round(s["pnl_r"], 2) if s.get("pnl_r") is not None else None,
                "Net P&L ₹": round(s["net_pnl_inr"], 2) if s.get("net_pnl_inr") is not None else None,
                "Exit Time": (s.get("outcome_at") or "")[:16],
            })

        df_j = pd.DataFrame(rows)

        _OUTCOME_STYLE = {
            "Target 2 Hit": "color:#00C896;font-weight:700",
            "Target 1 Hit": "color:#5AD8A6;font-weight:700",
            "Stopped Out":  "color:#ff4d6d;font-weight:700",
            "Squared Off":  "color:#f0b429;font-weight:600",
            "Expired":      "color:#6b7a99",
            "Open":         "color:#7c83fd;font-weight:700",
        }

        def _pnl_style(v):
            if v is None or v == "": return ""
            try:
                f = float(v)
                return "color:#00C896;font-weight:600" if f > 0 else ("color:#ff4d6d;font-weight:600" if f < 0 else "")
            except (TypeError, ValueError):
                return ""

        def _outcome_style(v):
            return _OUTCOME_STYLE.get(str(v), "")

        styled = (
            df_j.style
            .map(_pnl_style, subset=["R", "Net P&L ₹"])
            .map(_outcome_style, subset=["Outcome"])
            .format({
                "Entry ₹":   lambda v: f"₹{v:,.2f}" if v else "",
                "SL ₹":      lambda v: f"₹{v:,.2f}" if v else "",
                "SL %":      lambda v: f"{v:.1f}%" if v is not None else "—",
                "T1 ₹":      lambda v: f"₹{v:,.2f}" if v else "",
                "T2 ₹":      lambda v: f"₹{v:,.2f}" if v else "",
                "Exit ₹":    lambda v: f"₹{v:,.2f}" if v is not None else "—",
                "R":         lambda v: f"{v:+.2f}R" if v is not None else "—",
                "Net P&L ₹": lambda v: f"₹{v:+,.0f}" if v is not None else "—",
            }, na_rep="—")
        )
        st.dataframe(styled, use_container_width=True, height=500, hide_index=True)

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
| GST | 18% on charges | 18% on charges |

*Position size: ₹{int(position_size):,} · figures scale linearly*
""")

# ╔═══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 4 — INSIGHTS                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════════╝
with tab_insights:

    regime = _market_regime()
    trend      = regime["trend"]
    volatility = regime["volatility"]
    fear       = regime["fear"]
    vix_val    = regime["vix"]

    trend_col  = "#00c896" if trend == "BULLISH" else ("#ff4d6d" if trend == "BEARISH" else "#6b7a99")
    vol_col    = "#f0b429" if volatility == "HIGH" else ("#00c896" if volatility == "LOW" else "#94a3b8")
    fear_col   = "#ff4d6d" if fear == "FEARFUL" else ("#f0b429" if fear == "NEUTRAL" else "#00c896")

    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Current Market Regime</div>',
        unsafe_allow_html=True,
    )
    rc1, rc2, rc3 = st.columns(3)
    for col, label, val, c in [
        (rc1, "Nifty Trend",  trend,      trend_col),
        (rc2, "Volatility",   volatility, vol_col),
        (rc3, "Fear (VIX)",   f'{fear}{f"  {vix_val:.1f}" if vix_val else ""}', fear_col),
    ]:
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-top:3px solid {c};'
                f'border-radius:14px;padding:14px 18px;margin-bottom:4px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{label}</div>'
                f'<div style="font-size:1.1rem;font-weight:800;color:{c};">{val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Strategy Suitability Right Now</div>',
        unsafe_allow_html=True,
    )

    _all_sigs   = log.get_signals(timeframe=timeframe, days_back=days_back)
    _closed_90  = [s for s in _all_sigs if s["outcome"] not in (OUTCOME_OPEN, OUTCOME_EXPIRED)]
    _strat_stats: dict = {}
    for s in _closed_90:
        st_ = s["strategy"]
        if st_ not in _strat_stats:
            _strat_stats[st_] = {"wins": 0, "total": 0}
        _strat_stats[st_]["total"] += 1
        _is_win = s["outcome"] in (OUTCOME_TARGET1, OUTCOME_TARGET2) or (
            s["outcome"] == OUTCOME_SQUARED_OFF and (s.get("net_pnl_inr") or 0) > 0
        )
        if _is_win:
            _strat_stats[st_]["wins"] += 1

    _matcher_rows = []
    for strat, stype in _STRATEGY_TYPE.items():
        fit   = _regime_fit(stype, trend, volatility, fear)
        stats = _strat_stats.get(strat, {})
        total = stats.get("total", 0)
        wr    = round(stats["wins"] / total * 100) if total >= 3 else None
        if fit >= 70:
            rec, rec_c = "IDEAL",  "#00c896"
        elif fit >= 45:
            rec, rec_c = "OK",     "#f0b429"
        else:
            rec, rec_c = "AVOID",  "#ff4d6d"
        _matcher_rows.append({
            "strat": strat, "stype": stype, "fit": fit,
            "wr": wr, "total": total, "rec": rec, "rec_c": rec_c,
        })

    _matcher_rows.sort(key=lambda x: x["fit"], reverse=True)

    for row in _matcher_rows:
        bar_w   = row["fit"]
        bar_col = "#00c896" if bar_w >= 70 else ("#f0b429" if bar_w >= 45 else "#ff4d6d")
        wr_str  = f'{row["wr"]}% ({row["total"]} trades)' if row["wr"] is not None else f'No data ({row["total"]} trades)'
        wr_col  = "#00c896" if (row["wr"] or 0) >= 50 else ("#f0b429" if (row["wr"] or 0) >= 35 else "#6b7a99")
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.06);border-radius:12px;'
            f'padding:12px 16px;margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<div>'
            f'<span style="font-size:0.88rem;font-weight:700;color:#e2e8f0;">{row["strat"]}</span>'
            f'<span style="font-size:0.65rem;color:#475569;margin-left:8px;">{row["stype"]}</span>'
            f'</div>'
            f'<div style="display:flex;gap:10px;align-items:center;">'
            f'<span style="font-size:0.7rem;color:{wr_col};font-weight:600;">Win rate: {wr_str}</span>'
            f'<span style="background:{row["rec_c"]}22;color:{row["rec_c"]};'
            f'border:1px solid {row["rec_c"]}44;border-radius:5px;'
            f'padding:2px 10px;font-size:0.7rem;font-weight:700;">{row["rec"]}</span>'
            f'</div>'
            f'</div>'
            f'<div style="background:rgba(255,255,255,0.05);border-radius:4px;height:4px;">'
            f'<div style="width:{bar_w}%;height:100%;background:{bar_col};border-radius:4px;"></div>'
            f'</div>'
            f'<div style="font-size:0.62rem;color:#374151;margin-top:4px;">Regime fit: {bar_w}/100</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Your Trading Patterns</div>',
        unsafe_allow_html=True,
    )

    _all_90  = log.get_signals(timeframe=timeframe, days_back=days_back)
    _closed  = [s for s in _all_90 if s["outcome"] not in (OUTCOME_OPEN, OUTCOME_EXPIRED)]

    if len(_all_90) < 5:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
            'border-radius:12px;padding:24px;text-align:center;color:#475569;font-size:0.85rem;">'
            'Not enough signals yet (need 5+) — run more scans to unlock bias analysis.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        _long_all   = [s for s in _all_90 if s["direction"] == "LONG"]
        _short_all  = [s for s in _all_90 if s["direction"] == "SHORT"]
        _long_wins  = sum(
            1 for s in _closed
            if s["direction"] == "LONG"
            and (s["outcome"] in (OUTCOME_TARGET1, OUTCOME_TARGET2)
                 or (s["outcome"] == OUTCOME_SQUARED_OFF and (s.get("net_pnl_inr") or 0) > 0))
        )
        _short_wins = sum(
            1 for s in _closed
            if s["direction"] == "SHORT"
            and (s["outcome"] in (OUTCOME_TARGET1, OUTCOME_TARGET2)
                 or (s["outcome"] == OUTCOME_SQUARED_OFF and (s.get("net_pnl_inr") or 0) > 0))
        )
        _long_cl    = sum(1 for s in _closed if s["direction"] == "LONG")
        _short_cl   = sum(1 for s in _closed if s["direction"] == "SHORT")
        _lwr = round(_long_wins  / _long_cl  * 100) if _long_cl  > 0 else None
        _swr = round(_short_wins / _short_cl * 100) if _short_cl > 0 else None

        _hold_days = []
        for s in _closed:
            try:
                _ed = _dt.date.fromisoformat(s["signal_date"])
                _xd = _dt.date.fromisoformat(s["outcome_at"][:10])
                _hold_days.append((_xd - _ed).days)
            except Exception:
                pass
        _avg_hold = round(sum(_hold_days) / len(_hold_days), 1) if _hold_days else None

        _sec_cnt: dict = {}
        for s in _all_90:
            sec = s.get("sector") or "Unknown"
            _sec_cnt[sec] = _sec_cnt.get(sec, 0) + 1
        _top_sec = sorted(_sec_cnt.items(), key=lambda x: x[1], reverse=True)[:3]

        _st_wr = {}
        for s in _closed:
            st_ = s["strategy"]
            if st_ not in _st_wr:
                _st_wr[st_] = {"w": 0, "n": 0}
            _st_wr[st_]["n"] += 1
            _is_w = s["outcome"] in (OUTCOME_TARGET1, OUTCOME_TARGET2) or (
                s["outcome"] == OUTCOME_SQUARED_OFF and (s.get("net_pnl_inr") or 0) > 0
            )
            if _is_w:
                _st_wr[st_]["w"] += 1
        _st_ranked = sorted(
            [(k, round(v["w"] / v["n"] * 100), v["n"]) for k, v in _st_wr.items() if v["n"] >= 3],
            key=lambda x: x[1], reverse=True,
        )
        _best_strat = _st_ranked[0]  if _st_ranked else None
        _worst_strat = _st_ranked[-1] if len(_st_ranked) > 1 else None

        bc1, bc2, bc3 = st.columns(3)

        with bc1:
            _bias_arrow = "↑" if len(_long_all) > len(_short_all) * 1.5 else ("↓" if len(_short_all) > len(_long_all) * 1.5 else "↕")
            _bias_label = "LONG-BIASED" if len(_long_all) > len(_short_all) else ("SHORT-BIASED" if len(_short_all) > len(_long_all) else "BALANCED")
            _bias_col   = "#f0b429" if _bias_label != "BALANCED" else "#00c896"
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px 18px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Direction Bias</div>'
                f'<div style="font-size:1rem;font-weight:800;color:{_bias_col};margin-bottom:8px;">'
                f'{_bias_arrow} {_bias_label}</div>'
                f'<div style="font-size:0.75rem;color:#475569;line-height:1.7;">'
                f'LONG: {len(_long_all)} signals'
                f'{f" · {_lwr}% WR" if _lwr is not None else ""}<br>'
                f'SHORT: {len(_short_all)} signals'
                f'{f" · {_swr}% WR" if _swr is not None else ""}'
                f'</div>'
                + (f'<div style="margin-top:8px;font-size:0.72rem;color:#f0b429;">'
                   f'⚠ Your SHORT win rate is higher — consider more short setups.</div>'
                   if (_lwr is not None and _swr is not None and _swr > _lwr + 15) else '')
                + f'</div>',
                unsafe_allow_html=True,
            )

        with bc2:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px 18px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Best Strategy</div>'
                + (f'<div style="font-size:0.9rem;font-weight:700;color:#00c896;margin-bottom:4px;">'
                   f'{_best_strat[0]}</div>'
                   f'<div style="font-size:0.78rem;color:#475569;">{_best_strat[1]}% win rate · {_best_strat[2]} trades</div>'
                   if _best_strat else
                   f'<div style="color:#374151;font-size:0.8rem;">Need 3+ closed trades per strategy.</div>')
                + (f'<div style="margin-top:8px;border-top:1px solid rgba(255,255,255,0.05);padding-top:8px;">'
                   f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                   f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Weakest</div>'
                   f'<div style="font-size:0.82rem;color:#ff4d6d;font-weight:600;">{_worst_strat[0]}</div>'
                   f'<div style="font-size:0.72rem;color:#475569;">{_worst_strat[1]}% WR · {_worst_strat[2]} trades</div>'
                   f'</div>'
                   if _worst_strat else '')
                + f'</div>',
                unsafe_allow_html=True,
            )

        with bc3:
            _sec_html = "".join(
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:0.75rem;padding:3px 0;">'
                f'<span style="color:#94a3b8;">{sec}</span>'
                f'<span style="color:#475569;">{cnt}</span></div>'
                for sec, cnt in _top_sec
            )
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px 18px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Top Sectors Traded</div>'
                + _sec_html
                + (f'<div style="margin-top:10px;border-top:1px solid rgba(255,255,255,0.05);padding-top:8px;">'
                   f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                   f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Avg Hold Time</div>'
                   f'<div style="font-size:1rem;font-weight:700;color:#94a3b8;">'
                   f'{_avg_hold}d</div>'
                   f'</div>'
                   if _avg_hold is not None else '')
                + f'</div>',
                unsafe_allow_html=True,
            )

    # ── Strategy Equity Curves ──────────────────────────────────────────────
    st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Strategy Equity Curves</div>',
        unsafe_allow_html=True,
    )

    _all_sigs_eq = log.get_signals(timeframe=timeframe, days_back=days_back)
    _eq_closed = [
        s for s in _all_sigs_eq
        if s["outcome"] not in (OUTCOME_OPEN, OUTCOME_EXPIRED)
        and s.get("outcome_at")
        and s.get("net_pnl_inr") is not None
    ]

    if len(_eq_closed) < 3:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
            'border-radius:12px;padding:24px;text-align:center;color:#475569;font-size:0.85rem;">'
            'Not enough closed trades yet to draw equity curves.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        _eq_by_strat: dict = {}
        for s in sorted(_eq_closed, key=lambda x: x["outcome_at"]):
            _eq_by_strat.setdefault(s["strategy"], []).append(float(s["net_pnl_inr"] or 0))

        _PALETTE = [
            "#00c896", "#3b82f6", "#f0b429", "#a78bfa",
            "#fb923c", "#f472b6", "#34d399", "#60a5fa",
        ]

        fig_eq = go.Figure()
        for i, (strat, pnls) in enumerate(_eq_by_strat.items()):
            if len(pnls) < 2:
                continue
            cumsum = []
            _acc = 0.0
            for p in pnls:
                _acc += p
                cumsum.append(round(_acc))
            col = _PALETTE[i % len(_PALETTE)]
            fig_eq.add_trace(go.Scatter(
                x=list(range(1, len(cumsum) + 1)),
                y=cumsum,
                mode="lines+markers",
                name=strat,
                line=dict(color=col, width=2),
                marker=dict(size=4, color=col),
                hovertemplate=f"<b>{strat}</b><br>Trade #%{{x}}<br>Cumulative: ₹%{{y:,.0f}}<extra></extra>",
            ))

        fig_eq.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.15)", line_width=1)
        fig_eq.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
            margin=dict(l=0, r=0, t=10, b=40),
            height=320,
            legend=dict(
                orientation="h", yanchor="top", y=-0.18,
                bgcolor="rgba(0,0,0,0)", font=dict(size=10),
            ),
            xaxis=dict(
                title="Trade #",
                gridcolor="rgba(255,255,255,0.04)", zeroline=False,
                showline=False, tickfont=dict(size=10),
            ),
            yaxis=dict(
                title="Cumulative P&L",
                gridcolor="rgba(255,255,255,0.06)", zeroline=False,
                showline=False, tickprefix="₹", tickfont=dict(size=10),
            ),
            hovermode="x unified",
        )
        st.plotly_chart(fig_eq, use_container_width=True)
