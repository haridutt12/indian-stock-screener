"""
Page 24: AI Backtest Builder
Describe a trading strategy in plain English → structured spec → backtest →
interactive results dashboard. Iterate conversationally.
"""
import json
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Backtest Builder · NiftyEdge", layout="wide", page_icon="🧪")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("AI Backtest Builder", "Describe a strategy in plain English · Backtest on real data · Iterate")
user_sidebar()

from analysis.strategy_spec import parse_strategy
from analysis.backtest_engine import run_backtest
from signals.backtest_store import save_run, get_runs, get_run

# ── Session state init ────────────────────────────────────────────────────────
for _k, _v in {
    "bt_spec":    None,
    "bt_results": None,
    "bt_history": [],
    "bt_run_id":  None,
    "bt_parsing": False,
    "bt_running": False,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _user_email() -> str:
    try:
        return (getattr(st.user, "email", "") or "").strip().lower() or "anonymous"
    except Exception:
        return "anonymous"


# ── Example strategies ────────────────────────────────────────────────────────
_EXAMPLES = [
    "Buy Nifty 50 stocks when RSI drops below 30 and the 20-day MA is rising. Exit with 5% stop loss and 12% take profit.",
    "MA crossover on RELIANCE.NS: buy when 20-day EMA crosses above 50-day EMA. Sell when it crosses back below. 7% stop loss.",
    "Buy HDFCBANK.NS when price closes above the 20-day Bollinger Band upper band on above-average volume. 4% stop loss, 8% take profit.",
    "MACD strategy on TCS.NS: buy when MACD crosses above signal line, sell when it crosses below. 6% stop loss.",
]

# ── Sidebar: history + examples ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📋 Examples")
    for ex in _EXAMPLES:
        if st.button(ex[:60] + "…", key=f"ex_{hash(ex)}", use_container_width=True):
            st.session_state["bt_prefill"] = ex

    st.divider()
    st.markdown("### 🕒 Run History")
    _history = get_runs(_user_email(), limit=15)
    if _history:
        for run in _history:
            _label = f"#{run['id']} {run['strategy_name'] or 'Unnamed'}  ({run['status']})"
            if st.button(_label[:50], key=f"hist_{run['id']}", use_container_width=True):
                _saved = get_run(run["id"])
                if _saved:
                    st.session_state["bt_spec"]    = _saved["spec"]
                    st.session_state["bt_results"] = _saved["results"]
                    st.session_state["bt_run_id"]  = _saved["id"]
    else:
        st.caption("No runs yet — describe a strategy below.")

# ── Main layout: input + results ──────────────────────────────────────────────
_input_col, _result_col = st.columns([1, 2], gap="large")

with _input_col:
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Strategy Description</div>',
        unsafe_allow_html=True,
    )

    _prefill = st.session_state.pop("bt_prefill", "")
    _default_text = _prefill or (
        json.dumps(st.session_state["bt_spec"], indent=2)
        if st.session_state["bt_spec"] and _prefill == ""
        else ""
    )
    _strategy_text = st.text_area(
        "Describe your strategy",
        value=_prefill,
        height=160,
        placeholder="e.g. Buy RELIANCE.NS when RSI < 30 and 20-day MA is rising. 5% stop loss, 10% take profit.",
        label_visibility="collapsed",
        key="bt_text_input",
    )

    _parse_btn = st.button("🔍 Parse Strategy", type="primary", use_container_width=True,
                           disabled=not _strategy_text.strip())

    # Show parsed spec if available
    if st.session_state["bt_spec"]:
        spec = st.session_state["bt_spec"]

        if spec.get("clarification_needed"):
            st.warning(f"**Clarification needed:** {spec['clarification_needed']}")

        elif spec.get("validation_errors"):
            st.error("**Validation errors:**\n" + "\n".join(f"- {e}" for e in spec["validation_errors"]))

        else:
            st.markdown(
                '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
                'text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 8px;">Parsed Strategy Spec</div>',
                unsafe_allow_html=True,
            )

            # Universe
            st.markdown(f"**Universe:** `{', '.join(spec.get('universe', []))}`")
            st.markdown(f"**Timeframe:** Daily · **Lookback:** {spec.get('lookback_years', 3)}Y · **Capital:** ₹{spec.get('initial_capital', 100000):,}")

            # Entry conditions
            with st.expander("Entry conditions", expanded=True):
                for c in spec.get("entry_conditions", []):
                    ind  = c.get("indicator", "")
                    per  = f"({c['period']})" if c.get("period") else ""
                    op   = c.get("operator", "").replace("_", " ")
                    val  = c.get("value", "")
                    ref  = c.get("reference", "")
                    rhs  = ref if ref else str(val)
                    st.markdown(f"- **{ind}{per}** {op} **{rhs}**")
                st.caption(f"Logic: {spec.get('entry_logic', 'AND')}")

            # Exit
            with st.expander("Exit rules", expanded=True):
                ex = spec.get("exit", {})
                if ex.get("stop_loss_pct"):
                    st.markdown(f"- Stop loss: **{ex['stop_loss_pct']}%**")
                if ex.get("take_profit_pct"):
                    st.markdown(f"- Take profit: **{ex['take_profit_pct']}%**")
                if ex.get("trailing_stop_pct"):
                    st.markdown(f"- Trailing stop: **{ex['trailing_stop_pct']}%**")
                if ex.get("max_holding_days"):
                    st.markdown(f"- Max holding: **{ex['max_holding_days']} days**")

            st.markdown(
                f"**Position sizing:** {spec.get('position_sizing', {}).get('pct_of_capital', 10)}% "
                f"per trade · max {spec.get('position_sizing', {}).get('max_positions', 5)} positions · "
                f"Commission {spec.get('commission_pct', 0.1)}%"
            )

            # Edit raw JSON
            with st.expander("Edit spec JSON"):
                _edited_json = st.text_area("Spec JSON", value=json.dumps(spec, indent=2),
                                            height=300, key="bt_json_edit")
                if st.button("Apply edits", key="bt_apply_edit"):
                    try:
                        st.session_state["bt_spec"] = json.loads(_edited_json)
                        st.rerun()
                    except json.JSONDecodeError as e:
                        st.error(f"Invalid JSON: {e}")

            st.divider()
            _run_btn = st.button("▶ Run Backtest", type="primary", use_container_width=True,
                                 key="bt_run_btn")
            if _run_btn:
                st.session_state["bt_running"] = True
                st.rerun()

# ── Parse strategy ─────────────────────────────────────────────────────────────
if _parse_btn and _strategy_text.strip():
    with st.spinner("Parsing strategy with AI…"):
        parsed = parse_strategy(_strategy_text.strip())
    st.session_state["bt_spec"]    = parsed
    st.session_state["bt_results"] = None
    st.session_state["bt_run_id"]  = None
    st.rerun()

# ── Run backtest ───────────────────────────────────────────────────────────────
if st.session_state.get("bt_running") and st.session_state["bt_spec"]:
    st.session_state["bt_running"] = False
    spec = st.session_state["bt_spec"]

    if spec.get("clarification_needed") or spec.get("validation_errors"):
        st.warning("Fix the spec issues before running.")
    else:
        with _result_col:
            with st.spinner(f"Running backtest on {spec.get('universe', [])} — fetching data…"):
                try:
                    results = run_backtest(spec)
                    st.session_state["bt_results"] = results
                    run_id = save_run(
                        user_email=_user_email(),
                        strategy_name=spec.get("strategy_name", "Unnamed"),
                        spec=spec,
                        results={
                            "metrics":     results["metrics"],
                            "equity_curve": results["equity_curve"],
                            "trade_count": len(results["trades"]),
                            "warnings":    results["warnings"],
                        },
                        status="done",
                    )
                    st.session_state["bt_run_id"] = run_id
                except Exception as exc:
                    st.error(f"Backtest failed: {exc}")
                    logger.exception("Backtest error")


# ── Results dashboard ──────────────────────────────────────────────────────────
with _result_col:
    results = st.session_state.get("bt_results")

    if not results:
        st.markdown(
            '<div style="text-align:center;padding:80px 20px;">'
            '<div style="font-size:2.5rem;margin-bottom:12px;">🧪</div>'
            '<div style="font-size:1rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;">'
            'No results yet</div>'
            '<div style="color:#4b5a72;font-size:0.82rem;">'
            'Describe a strategy on the left, parse it, then hit Run Backtest.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    metrics      = results.get("metrics", {})
    equity_curve = results.get("equity_curve", [])
    trades       = results.get("trades", [])
    warnings     = results.get("warnings", [])

    # Warnings
    for w in warnings:
        st.warning(w)

    if not trades:
        st.info("No trades were generated. Try loosening entry conditions.")
        st.stop()

    # ── Metric strip ──────────────────────────────────────────────────────────
    _mc = st.columns(4)
    for _col, (_lbl, _val, _cc) in zip(_mc, [
        ("Total Return",
         f"{metrics.get('total_return_pct', 0):+.1f}%",
         "#00c896" if metrics.get("total_return_pct", 0) >= 0 else "#ff4d6d"),
        ("CAGR",
         f"{metrics.get('cagr_pct', 0):+.1f}%",
         "#00c896" if metrics.get("cagr_pct", 0) >= 10 else "#f0b429" if metrics.get("cagr_pct", 0) >= 0 else "#ff4d6d"),
        ("Sharpe Ratio",
         f"{metrics.get('sharpe_ratio', 0):.2f}",
         "#00c896" if metrics.get("sharpe_ratio", 0) >= 1 else "#f0b429" if metrics.get("sharpe_ratio", 0) >= 0 else "#ff4d6d"),
        ("Max Drawdown",
         f"{metrics.get('max_drawdown_pct', 0):.1f}%",
         "#ff4d6d" if metrics.get("max_drawdown_pct", 0) > 20 else "#f0b429" if metrics.get("max_drawdown_pct", 0) > 10 else "#00c896"),
    ]):
        with _col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
                f'<div style="font-size:1.1rem;font-weight:800;color:{_cc};">{_val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    _mc2 = st.columns(4)
    for _col, (_lbl, _val, _cc) in zip(_mc2, [
        ("Win Rate",     f"{metrics.get('win_rate', 0):.1f}%",
         "#00c896" if metrics.get("win_rate", 0) >= 50 else "#ff4d6d"),
        ("Total Trades", str(metrics.get("total_trades", 0)), "#94a3b8"),
        ("Profit Factor",
         str(metrics.get("profit_factor", 0)),
         "#00c896" if str(metrics.get("profit_factor", 0)) == "∞" or float(str(metrics.get("profit_factor", 0)).replace("∞","999")) >= 1.5
         else "#f0b429" if float(str(metrics.get("profit_factor", 0)).replace("∞","999")) >= 1 else "#ff4d6d"),
        ("Final Capital",
         f"₹{metrics.get('final_equity', 0):,.0f}",
         "#00c896" if metrics.get("final_equity", 0) >= metrics.get("initial_capital", 0) else "#ff4d6d"),
    ]):
        with _col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
                f'<div style="font-size:1rem;font-weight:800;color:{_cc};">{_val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Equity + Drawdown chart ────────────────────────────────────────────────
    _tab_chart, _tab_trades, _tab_dist = st.tabs(["📈 Equity Curve", "📋 Trade Log", "📊 Distribution"])

    with _tab_chart:
        if equity_curve:
            _ec_df = pd.DataFrame(equity_curve)
            _fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                row_heights=[0.65, 0.35],
                subplot_titles=["Portfolio Equity (₹)", "Drawdown (%)"],
            )

            _fig.add_trace(go.Scatter(
                x=_ec_df["date"], y=_ec_df["equity"],
                mode="lines", name="Equity",
                line=dict(color="#3b82f6", width=2),
                fill="tozeroy", fillcolor="rgba(59,130,246,0.07)",
                hovertemplate="%{x}<br>₹%{y:,.0f}<extra>Equity</extra>",
            ), row=1, col=1)

            _fig.add_hline(
                y=metrics.get("initial_capital", 100000),
                line_color="rgba(255,255,255,0.15)", line_width=1, row=1, col=1,
            )

            _fig.add_trace(go.Scatter(
                x=_ec_df["date"], y=_ec_df["drawdown"],
                mode="lines", name="Drawdown",
                line=dict(color="#ff4d6d", width=1.5),
                fill="tozeroy", fillcolor="rgba(255,77,109,0.1)",
                hovertemplate="%{x}<br>%{y:.1f}%<extra>Drawdown</extra>",
            ), row=2, col=1)

            _fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
                margin=dict(l=0, r=0, t=30, b=0), height=420,
                showlegend=False,
                xaxis2=dict(title="Trade exit date", tickfont=dict(size=9)),
            )
            for _ax in ["yaxis", "yaxis2", "xaxis", "xaxis2"]:
                _a = getattr(_fig.layout, _ax, None)
                if _a:
                    _a.gridcolor = "rgba(255,255,255,0.04)"
                    _a.zeroline  = False
                    _a.tickfont  = dict(size=9)
            for _ann in _fig.layout.annotations:
                _ann.font.color = "#94a3b8"
                _ann.font.size  = 9

            st.plotly_chart(_fig, use_container_width=True)
        else:
            st.info("No equity curve data.")

    with _tab_trades:
        if trades:
            _tdf = pd.DataFrame(trades)
            _show_cols = ["ticker", "entry_date", "exit_date", "entry_price", "exit_price",
                          "shares", "return_pct", "net_pnl", "holding_days", "exit_reason"]
            _show_cols = [c for c in _show_cols if c in _tdf.columns]

            def _colour_return(val):
                try:
                    v = float(val)
                    return "color: #00c896; font-weight:700;" if v > 0 else "color: #ff4d6d; font-weight:700;"
                except Exception:
                    return ""

            st.dataframe(
                _tdf[_show_cols].sort_values("entry_date", ascending=False)
                .style.map(_colour_return, subset=["return_pct"] if "return_pct" in _show_cols else []),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"{len(trades)} trades · avg hold {_tdf['holding_days'].mean():.1f} days")
        else:
            st.info("No trades.")

    with _tab_dist:
        if trades:
            _tdf = pd.DataFrame(trades)
            _returns = _tdf["return_pct"].tolist()

            _fig_d = go.Figure()
            _fig_d.add_trace(go.Histogram(
                x=_returns, nbinsx=30,
                marker_color=["#00c896" if r >= 0 else "#ff4d6d" for r in _returns],
                opacity=0.8,
                hovertemplate="Return: %{x:.1f}%<br>Trades: %{y}<extra></extra>",
            ))
            _fig_d.add_vline(x=0, line_color="rgba(255,255,255,0.2)", line_width=1)
            _avg = float(np.mean(_returns))
            _fig_d.add_vline(
                x=_avg, line_color="#f0b429", line_width=1.5, line_dash="dash",
                annotation_text=f"Avg {_avg:+.1f}%",
                annotation_font_color="#f0b429", annotation_font_size=9,
            )
            _fig_d.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
                margin=dict(l=0, r=0, t=10, b=0), height=280,
                xaxis=dict(title="Trade return (%)", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
                yaxis=dict(title="# Trades", gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9)),
                showlegend=False,
            )
            st.plotly_chart(_fig_d, use_container_width=True)

            # Win/loss breakdown
            _wl = st.columns(2)
            with _wl[0]:
                _wins = [r for r in _returns if r > 0]
                st.metric("Avg Win", f"{np.mean(_wins):.2f}%" if _wins else "—",
                          delta=f"{len(_wins)} trades")
            with _wl[1]:
                _loss = [r for r in _returns if r <= 0]
                st.metric("Avg Loss", f"{np.mean(_loss):.2f}%" if _loss else "—",
                          delta=f"{len(_loss)} trades")

    # ── Iterate / revise ──────────────────────────────────────────────────────
    st.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">'
        'Iterate: describe a change</div>',
        unsafe_allow_html=True,
    )
    _revise_text = st.text_input(
        "Revision",
        placeholder='e.g. "add a 3% trailing stop" · "test on Bank Nifty instead" · "change take profit to 15%"',
        label_visibility="collapsed",
        key="bt_revise_input",
    )
    if st.button("🔄 Apply Revision", key="bt_revise_btn", disabled=not _revise_text.strip()):
        _revision_prompt = (
            f"Current strategy spec:\n{json.dumps(st.session_state['bt_spec'], indent=2)}\n\n"
            f"User revision request: {_revise_text.strip()}\n\n"
            "Apply the revision and return the updated spec JSON."
        )
        with st.spinner("Applying revision…"):
            _new_spec = parse_strategy(_revision_prompt)
        if _new_spec and not _new_spec.get("clarification_needed"):
            st.session_state["bt_spec"]    = _new_spec
            st.session_state["bt_results"] = None
            st.session_state["bt_running"] = True
            st.rerun()
        else:
            st.warning(_new_spec.get("clarification_needed", "Could not apply revision."))

    if st.session_state.get("bt_run_id"):
        st.caption(f"Run #{st.session_state['bt_run_id']} saved · {metrics.get('backtest_years', '?')}Y backtest")

st.caption(
    "Data: Yahoo Finance (daily, adjusted close) · No lookahead bias · "
    "Commission included · Past performance does not guarantee future results."
)
