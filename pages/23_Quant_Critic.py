"""
Page 23: AI Quant Critic
Deterministic performance metrics + AI-powered critical assessment.
All numbers computed in Python; LLM receives the output and explains it.
"""
import datetime as _dt
import streamlit as st
import plotly.graph_objects as go

from signals.signal_logger import get_signal_logger
from analysis.quant_critic import (
    compute_critic_metrics,
    metrics_fingerprint,
    ai_critique,
)
from ui.styles import page_header, auth_guard, user_sidebar
from ui.components import research_disclaimer
from ui.llm_guard import llm_guard, record_llm_tokens

st.set_page_config(page_title="Quant Critic · NiftyEdge", layout="wide", page_icon="🔬")
from ui.styles import inject_global_css; inject_global_css()
auth_guard()

page_header("🔬 AI Quant Critic", subtitle="Systematic Performance Audit · Strategy Risk Profiling",
            badge="BETA", badge_color="#7c83fd")
research_disclaimer()

# ── SIDEBAR FILTERS ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    timeframe_opt = st.selectbox(
        "Timeframe", ["All", "SWING", "INTRADAY"], index=0
    )
    strategy_input = st.text_input(
        "Strategy (leave blank for all)", value=""
    )
    days_back = st.slider(
        "Look-back window (days)", min_value=30, max_value=730, value=180, step=30
    )
    min_n = st.number_input(
        "Minimum signals required", min_value=5, max_value=100, value=20, step=5
    )

    run_btn = st.button("▶ Run Analysis", type="primary", use_container_width=True)
    st.divider()
    user_sidebar()

# ── LOAD SIGNALS ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_signals(days_back: int, timeframe: str, strategy: str) -> list[dict]:
    tf  = None if timeframe == "All" else timeframe
    raw = get_signal_logger().get_signals(days_back=days_back, timeframe=tf)
    if strategy.strip():
        raw = [s for s in raw if strategy.strip().lower() in (s.get("strategy") or "").lower()]
    return raw

if not run_btn and not st.session_state.get("_qc_ran"):
    st.info("Configure filters in the sidebar and click **▶ Run Analysis** to generate the report.", icon="🔬")
    st.stop()

st.session_state["_qc_ran"] = True

with st.spinner("Loading signals…"):
    signals = _load_signals(days_back, timeframe_opt, strategy_input)

closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")]
n_closed = len(closed)

# ── SAMPLE SIZE GATE ──────────────────────────────────────────────────────────
if n_closed == 0:
    st.error("No closed signals match the selected filters. Adjust the look-back window or remove strategy filters.")
    st.stop()

if n_closed < int(min_n):
    st.warning(
        f"**Insufficient sample ({n_closed} closed signals).** "
        f"You set a minimum of {int(min_n)}. "
        f"Statistics below N≈20 are not statistically reliable — widen the date range or lower the threshold with caution.",
        icon="⚠️",
    )

# ── COMPUTE METRICS ───────────────────────────────────────────────────────────
with st.spinner("Computing performance metrics…"):
    metrics = compute_critic_metrics(signals)

sample  = metrics.get("sample", {})
perf    = metrics.get("performance", {})
regime  = metrics.get("regime", {})
conc    = metrics.get("concentration", {})
calib   = metrics.get("calibration", {})
bench   = metrics.get("benchmark", {})

# ── SUMMARY STRIP ─────────────────────────────────────────────────────────────
def _color(val, good_above=None, bad_below=None, neutral="#f1f5f9"):
    if good_above is not None and val is not None and val >= good_above:
        return "#00c896"
    if bad_below is not None and val is not None and val < bad_below:
        return "#ff4d6d"
    return neutral

win_rate = perf.get("win_rate")
exp_net  = perf.get("expectancy_net")
pf       = perf.get("profit_factor")
max_dd   = perf.get("max_drawdown_r")
avg_alpha = bench.get("avg_alpha_pct") if bench.get("available") else None

strip_items = [
    ("Closed Signals",  str(n_closed),                    "#f1f5f9"),
    ("Win Rate",        f"{win_rate*100:.1f}%" if win_rate is not None else "—",
     _color(win_rate, good_above=0.5, bad_below=0.35)),
    ("Expectancy (R)",  f"{exp_net:+.3f}" if exp_net is not None else "—",
     _color(exp_net, good_above=0.05, bad_below=0)),
    ("Profit Factor",   f"{pf:.2f}" if pf else "—",
     _color(pf, good_above=1.5, bad_below=1.0)),
    ("Max DD (R)",      f"{max_dd:.2f}R" if max_dd is not None else "—",
     "#ff4d6d" if max_dd and max_dd > 5 else "#f0b429" if max_dd and max_dd > 3 else "#00c896"),
    ("Avg Alpha",       f"{avg_alpha:+.2f}%" if avg_alpha is not None else "N/A",
     _color(avg_alpha, good_above=0, bad_below=-1) if avg_alpha is not None else "#475569"),
]

cols = st.columns(len(strip_items))
for col, (label, value, color) in zip(cols, strip_items):
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
            f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.09em;margin-bottom:6px;">{label}</div>'
            f'<div style="color:{color};font-size:1.4rem;font-weight:800;">{value}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── AI CRITIC VERDICT ─────────────────────────────────────────────────────────
fp = metrics_fingerprint(metrics)

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_critique(fp: str, _metrics: dict) -> str:
    return ai_critique(_metrics)

with st.expander("🤖 AI Critic Verdict", expanded=True):
    if n_closed < 10:
        st.warning("Fewer than 10 closed signals — AI critique skipped (not meaningful at this sample size).")
    elif not llm_guard(estimated_tokens=1100, label="AI Quant Critic"):
        pass  # guard rendered the blocked message
    else:
        with st.spinner("Asking the AI Critic…"):
            critique = _cached_critique(fp, metrics)
        # Only count tokens once per unique fingerprint (not on every page rerun)
        _counted_key = f"_llm_counted_{fp}"
        if not st.session_state.get(_counted_key):
            record_llm_tokens(1100)
            st.session_state[_counted_key] = True
        st.markdown(critique)
        st.caption(f"Cached verdict · fingerprint `{fp}` · refreshes every 30 min")

st.divider()

# ── DETAIL TABS ───────────────────────────────────────────────────────────────
tab_perf, tab_regime, tab_strat, tab_calib, tab_bench = st.tabs([
    "📈 Performance", "🌐 Regime", "📊 Strategy Mix", "🎯 Calibration", "📐 vs Nifty"
])

# ── TAB 1: PERFORMANCE ────────────────────────────────────────────────────────
with tab_perf:
    if not perf:
        st.info("No performance data available.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Core Stats")
            rows = [
                ("N (closed)",        perf.get("n")),
                ("Win Rate",          f"{perf['win_rate']*100:.1f}%" if perf.get("win_rate") is not None else "—"),
                ("Expectancy (net R)", f"{perf['expectancy_net']:+.3f}" if perf.get("expectancy_net") is not None else "—"),
                ("Expectancy (gross R)", f"{perf['expectancy_gross']:+.3f}" if perf.get("expectancy_gross") is not None else "—"),
                ("Cost drag (R)",     f"{perf['cost_drag']:.3f}" if perf.get("cost_drag") is not None else "—"),
                ("Profit Factor",     f"{perf['profit_factor']:.2f}" if perf.get("profit_factor") else "—"),
                ("Avg Win (R)",       f"{perf['avg_win_r']:+.2f}" if perf.get("avg_win_r") else "—"),
                ("Avg Loss (R)",      f"{perf['avg_loss_r']:+.2f}" if perf.get("avg_loss_r") else "—"),
                ("Max Drawdown (R)",  f"{perf['max_drawdown_r']:.2f}R" if perf.get("max_drawdown_r") is not None else "—"),
            ]
            for label, val in rows:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                    f'<span style="color:#64748b;font-size:0.82rem;">{label}</span>'
                    f'<span style="color:#f1f5f9;font-weight:600;font-size:0.82rem;">{val}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with col2:
            ec = perf.get("equity_curve", [])
            if ec:
                st.markdown("#### Equity Curve (R)")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=ec, mode="lines",
                    line=dict(color="#7c83fd", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(124,131,253,0.08)",
                ))
                fig.update_layout(
                    height=280, margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#64748b", size=11)),
                )
                st.plotly_chart(fig, use_container_width=True, key="equity_curve")

        rwr = perf.get("rolling_win_rate", [])
        if rwr:
            st.markdown("#### Rolling Win Rate")
            fig2 = go.Figure()
            fig2.add_hline(y=0.5, line_dash="dot", line_color="#475569", opacity=0.5)
            fig2.add_trace(go.Scatter(
                y=rwr, mode="lines+markers",
                line=dict(color="#00c896", width=2),
                marker=dict(size=4),
            ))
            fig2.update_layout(
                height=200, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, showticklabels=False, title="Trade #"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat=".0%",
                           range=[0, 1], tickfont=dict(color="#64748b", size=11)),
            )
            st.plotly_chart(fig2, use_container_width=True, key="rolling_wr")

# ── TAB 2: REGIME ─────────────────────────────────────────────────────────────
with tab_regime:
    if not regime.get("available"):
        st.info("Regime data unavailable (Nifty 50 price data could not be fetched).")
    else:
        by_regime = regime.get("by_regime", {})
        if by_regime:
            reg_names = list(by_regime.keys())
            reg_wr    = [by_regime[r]["win_rate"] * 100 for r in reg_names]
            reg_n     = [by_regime[r]["n"] for r in reg_names]
            reg_avgr  = [by_regime[r]["avg_r"] for r in reg_names]

            col1, col2 = st.columns(2)

            with col1:
                fig = go.Figure(go.Bar(
                    x=reg_names, y=reg_wr,
                    marker_color=["#00c896" if r == "Bull" else "#ff4d6d" if r == "Bear" else "#f0b429"
                                  for r in reg_names],
                    text=[f"{v:.0f}%" for v in reg_wr],
                    textposition="outside",
                ))
                fig.update_layout(
                    title="Win Rate by Regime (%)",
                    height=260, margin=dict(l=0, r=0, t=40, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", ticksuffix="%",
                               tickfont=dict(color="#64748b")),
                    xaxis=dict(tickfont=dict(color="#94a3b8")),
                    title_font=dict(color="#94a3b8", size=13),
                )
                st.plotly_chart(fig, use_container_width=True, key="regime_wr")

            with col2:
                fig2 = go.Figure(go.Bar(
                    x=reg_names, y=reg_avgr,
                    marker_color=["#7c83fd" if v >= 0 else "#ff4d6d" for v in reg_avgr],
                    text=[f"{v:+.2f}R" for v in reg_avgr],
                    textposition="outside",
                ))
                fig2.add_hline(y=0, line_color="#475569", line_width=1)
                fig2.update_layout(
                    title="Avg R by Regime",
                    height=260, margin=dict(l=0, r=0, t=40, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#64748b")),
                    xaxis=dict(tickfont=dict(color="#94a3b8")),
                    title_font=dict(color="#94a3b8", size=13),
                )
                st.plotly_chart(fig2, use_container_width=True, key="regime_avgr")

            if regime.get("regime_dependency_flag"):
                st.warning(
                    f"⚠️ **Regime dependency detected.** "
                    f"{regime.get('p&l_regime_pct', 0):.0f}% of P&L is concentrated "
                    f"in the **{regime.get('p&l_regime')}** regime. "
                    f"Performance may degrade materially when market conditions change.",
                    icon="⚠️",
                )

            st.markdown("#### Regime Breakdown Table")
            for r, stats in by_regime.items():
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:100px 1fr 1fr 1fr 1fr;'
                    f'padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);gap:8px;">'
                    f'<span style="color:#94a3b8;font-weight:700;">{r}</span>'
                    f'<span style="color:#64748b;font-size:0.8rem;">N={stats["n"]}</span>'
                    f'<span style="color:#64748b;font-size:0.8rem;">{stats["win_rate"]*100:.0f}% WR</span>'
                    f'<span style="color:#64748b;font-size:0.8rem;">{stats["avg_r"]:+.2f}R avg</span>'
                    f'<span style="color:#64748b;font-size:0.8rem;">{stats["pct_trades"]:.0f}% of trades</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

# ── TAB 3: STRATEGY MIX ──────────────────────────────────────────────────────
with tab_strat:
    if not conc:
        st.info("No strategy concentration data available.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            per = conc.get("per_strategy", {})
            if per:
                names = list(per.keys())
                ns    = [per[k]["n"] for k in names]
                fig = go.Figure(go.Pie(
                    labels=names, values=ns,
                    hole=0.45,
                    marker=dict(colors=["#7c83fd", "#00c896", "#f0b429", "#06b6d4", "#ff4d6d"]),
                    textfont=dict(color="#f1f5f9", size=12),
                ))
                fig.update_layout(
                    title="Trade Count Distribution",
                    height=280, margin=dict(l=0, r=0, t=40, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(font=dict(color="#94a3b8")),
                    title_font=dict(color="#94a3b8", size=13),
                )
                st.plotly_chart(fig, use_container_width=True, key="strat_pie")

        with col2:
            st.markdown("#### Strategy Stats")
            st.markdown(
                f'<div style="color:#64748b;font-size:0.8rem;margin-bottom:10px;">'
                f'HHI (concentration): <strong style="color:#f1f5f9;">{conc.get("hhi", 0):.3f}</strong>'
                f' &nbsp;·&nbsp; 1.0 = all one strategy · 0 = perfectly diverse'
                f'</div>',
                unsafe_allow_html=True,
            )
            for k, s in per.items():
                wr_color = "#00c896" if s["win_rate"] >= 0.5 else "#ff4d6d"
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.02);border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="color:#f1f5f9;font-weight:600;font-size:0.85rem;">{k}</span>'
                    f'<span style="color:{wr_color};font-weight:700;">{s["win_rate"]*100:.0f}% WR</span>'
                    f'</div>'
                    f'<span style="color:#475569;font-size:0.75rem;">{s["n"]} signals · {s["wins"]} wins</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if conc.get("concentration_flag"):
            st.warning(
                f"⚠️ **Strategy concentration risk.** "
                f"{conc.get('top_win_strategy_pct', 0):.0f}% of winning trades come from "
                f"**{conc.get('top_win_strategy')}**. HHI = {conc.get('hhi', 0):.3f}. "
                f"This portfolio is not diversified across strategies.",
                icon="⚠️",
            )

# ── TAB 4: CALIBRATION ───────────────────────────────────────────────────────
with tab_calib:
    if not calib.get("available"):
        st.info("Calibration data unavailable (fewer than 10 closed signals with confidence scores).")
    else:
        by_conf = calib.get("by_confidence", {})
        conf_levels = sorted(by_conf.keys())
        avg_rs = [by_conf[c]["avg_r"] for c in conf_levels]

        fig = go.Figure()
        fig.add_hline(y=0, line_color="#475569", line_width=1, line_dash="dot")
        fig.add_trace(go.Bar(
            x=[str(c) for c in conf_levels],
            y=avg_rs,
            marker_color=["#00c896" if v > 0 else "#ff4d6d" for v in avg_rs],
            text=[f"{v:+.2f}R" for v in avg_rs],
            textposition="outside",
        ))
        fig.update_layout(
            title="Avg R by Confidence Level (1-5)",
            height=260, margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="Confidence", tickfont=dict(color="#94a3b8")),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#64748b")),
            title_font=dict(color="#94a3b8", size=13),
        )
        st.plotly_chart(fig, use_container_width=True, key="calib_bar")

        if calib.get("is_well_calibrated"):
            st.success("✅ Confidence scores appear **well-calibrated** — higher confidence correlates with higher avg R.")
        else:
            st.error(
                "❌ Confidence scores are **not monotone** — higher-confidence signals do not consistently "
                "outperform lower ones. The scoring model may need re-evaluation."
            )
        st.caption(calib.get("calibration_note", ""))

# ── TAB 5: VS NIFTY ──────────────────────────────────────────────────────────
with tab_bench:
    if not bench.get("available"):
        st.info("Benchmark comparison unavailable — requires `outcome_at` timestamps and Nifty 50 price history.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Avg Alpha per Trade",
                f"{bench['avg_alpha_pct']:+.2f}%",
                help="Signal return minus Nifty 50 buy-and-hold over the same holding period",
            )
        with col2:
            st.metric(
                "Beat Benchmark",
                f"{bench['beat_benchmark_pct']:.0f}%",
                help="% of individual signals that outperformed Nifty over their holding period",
            )
        st.caption(bench.get("note", ""))
        st.markdown(
            f'<div style="color:#475569;font-size:0.75rem;margin-top:10px;">'
            f'Based on {bench.get("n_compared", 0)} signals with valid entry/exit dates. '
            f'Alpha = signal return − Nifty return over identical holding period.'
            f'</div>',
            unsafe_allow_html=True,
        )
