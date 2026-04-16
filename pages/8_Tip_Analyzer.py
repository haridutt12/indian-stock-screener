"""
Page 8: Tip Analyzer
- Paste any WhatsApp/Telegram stock tip
- AI-powered credibility verdict: pump detector, technical check, R:R assessment
- Claude Haiku parses the tip → yfinance analysis → Claude Sonnet verdict
"""
import hashlib
import streamlit as st

st.set_page_config(page_title="Tip Analyzer", layout="wide", page_icon="🔍")
from ui.styles import inject_global_css; inject_global_css()

# ── Page header (no <style> block — animations are in ui/styles.py) ────────────
st.markdown(
    '<div style="background:linear-gradient(135deg,#0d1117 0%,#161b27 60%,#0d1117 100%);'
    'border:1px solid rgba(255,255,255,0.07);border-radius:20px;'
    'padding:32px 40px;margin-bottom:28px;position:relative;overflow:hidden;">'
    '<div style="position:absolute;top:-60px;right:-60px;width:240px;height:240px;'
    'background:radial-gradient(circle,rgba(255,77,109,0.12),transparent 70%);'
    'border-radius:50%;pointer-events:none;"></div>'
    '<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">'
    '<span style="font-size:2.2rem;">🔍</span>'
    '<h1 style="margin:0;font-size:2rem;font-weight:800;'
    'background:linear-gradient(135deg,#ffffff 0%,#a0aec0 100%);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">'
    'Stock Tip Analyzer</h1></div>'
    '<p style="margin:0;color:#6b7a99;font-size:0.95rem;max-width:600px;">'
    'Got a tip on WhatsApp or Telegram? Paste it below and get an instant credibility '
    'verdict &mdash; pump risk score, technical alignment, and a plain-English AI assessment.'
    '</p></div>',
    unsafe_allow_html=True,
)

# ── Sample tips ────────────────────────────────────────────────────────────────
SAMPLE_TIPS = {
    "Select a sample…": "",
    "Suspicious pump tip": (
        "🚨 URGENT BUY IRFC NOW!! Operator backed, price will double in 2 days. "
        "Buy at 220, target 440, no stop loss needed. Limited time opportunity!! "
        "Sure shot 100% guaranteed returns. Share with everyone!!"
    ),
    "Decent swing trade tip": (
        "HDFC Bank – Buy above 1720, SL 1685, T1 1760, T2 1800. "
        "Strong breakout above resistance with good volumes. 2-3 day swing trade."
    ),
    "Vague intraday tip": (
        "Reliance Industries buy call for today. Target 2900. Strong momentum."
    ),
    "Well-structured positional tip": (
        "TCS positional buy. CMP 3850, add up to 3900. SL 3720. "
        "T1 4100, T2 4400. IT sector recovery play, strong Q3 results expected. "
        "Hold 3-4 weeks."
    ),
}

# ── Input area ─────────────────────────────────────────────────────────────────
col_input, col_sample = st.columns([3, 1])

with col_sample:
    sample_choice = st.selectbox("Try a sample tip", list(SAMPLE_TIPS.keys()), key="sample_sel")
    # When user picks a sample, push it into the text area's session-state key
    if sample_choice and sample_choice != "Select a sample…":
        new_val = SAMPLE_TIPS[sample_choice]
        if st.session_state.get("tip_input") != new_val:
            st.session_state["tip_input"] = new_val
            st.rerun()

with col_input:
    tip_text = st.text_area(
        "Paste your tip here",
        height=130,
        placeholder=(
            "Paste any WhatsApp / Telegram stock tip here…\n\n"
            "Example: 'Buy RELIANCE at 2800, SL 2750, target 2900. Strong breakout!'"
        ),
        key="tip_input",
    )

analyze_btn = st.button("🔍 Analyze This Tip", type="primary", disabled=not (tip_text or "").strip())

if not (tip_text or "").strip():
    st.markdown(
        '<div style="border:1px dashed rgba(255,255,255,0.1);border-radius:14px;'
        'padding:36px;text-align:center;color:#4a5568;margin-top:12px;">'
        '<div style="font-size:2.5rem;margin-bottom:10px;">📱</div>'
        '<div style="font-weight:600;font-size:1rem;margin-bottom:6px;color:#6b7a99;">'
        'Paste any tip to get started</div>'
        '<div style="font-size:0.85rem;">'
        'Works with WhatsApp forwards, Telegram tips, stock advisory messages,'
        '<br>and any format &mdash; our AI extracts the details automatically.'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()

if not analyze_btn:
    st.stop()

# ── Run pipeline (cached in session_state by tip hash) ─────────────────────────
from analysis.tip_analyzer import parse_tip, analyze_tip, get_ai_verdict

tip_hash = hashlib.md5((tip_text or "").strip().encode()).hexdigest()
cache_key = f"tip_result_{tip_hash}"

if cache_key not in st.session_state:
    with st.spinner("Step 1/3 — Parsing tip…"):
        parsed = parse_tip(tip_text.strip())

    if "error" in parsed:
        st.error(f"Could not parse tip: {parsed['error']}")
        st.stop()

    with st.spinner("Step 2/3 — Fetching market data and scoring…"):
        analysis = analyze_tip(parsed)

    if "error" in analysis:
        st.error(f"Analysis failed: {analysis['error']}")
        st.stop()

    with st.spinner("Step 3/3 — Getting AI verdict…"):
        ai_verdict = get_ai_verdict(parsed, analysis)

    st.session_state[cache_key] = {
        "parsed": parsed,
        "analysis": analysis,
        "ai_verdict": ai_verdict,
    }

cached      = st.session_state[cache_key]
parsed      = cached["parsed"]
analysis    = cached["analysis"]
ai_verdict  = cached["ai_verdict"]

# ── Verdict banner ─────────────────────────────────────────────────────────────
verdict       = analysis["verdict"]
verdict_color = analysis["verdict_color"]
verdict_icon  = analysis["verdict_icon"]
pump_score    = analysis["pump_score"]
tech_score    = analysis["tech_score"]
rr            = analysis.get("rr")

VERDICT_BG = {
    "LIKELY PUMP": "rgba(255,77,109,0.12)",
    "HIGH RISK":   "rgba(255,152,0,0.12)",
    "MIXED":       "rgba(240,180,41,0.12)",
    "CREDIBLE":    "rgba(0,200,150,0.12)",
}
vbg = VERDICT_BG.get(verdict, "rgba(255,255,255,0.04)")

company   = analysis.get("company_name", "")
ticker    = analysis["ticker"]
sector    = analysis.get("sector", "")
sector_str = f" &middot; {sector}" if sector else ""

st.markdown(
    f'<div style="background:{vbg};border:1px solid {verdict_color}55;'
    f'border-left:5px solid {verdict_color};border-radius:16px;'
    f'padding:24px 28px;margin:20px 0;display:flex;align-items:center;gap:18px;">'
    f'<div style="font-size:3rem;line-height:1;">{verdict_icon}</div>'
    f'<div>'
    f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.12em;'
    f'text-transform:uppercase;color:#6b7a99;margin-bottom:4px;">Verdict</div>'
    f'<div style="font-size:2rem;font-weight:800;color:{verdict_color};letter-spacing:-0.02em;">{verdict}</div>'
    f'<div style="font-size:0.88rem;color:#8892a4;margin-top:2px;">'
    f'{company} ({ticker}){sector_str}</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)

# Show a subtle note when running without Claude API (regex mode)
if parsed.get("_parsed_by") == "regex":
    st.caption("ℹ️ Running in offline mode — tip parsed with regex, verdict generated from rules. "
               "Add an `ANTHROPIC_API_KEY` for deeper AI analysis.")

# ── Three score cards ──────────────────────────────────────────────────────────
pump_color = "#ff4d6d" if pump_score >= 55 else "#ff9800" if pump_score >= 35 else "#00c896"
tech_color = "#00c896" if tech_score >= 62 else "#ff9800" if tech_score < 40 else "#f0b429"
rr_display = f"1:{rr:.1f}" if rr else "N/A"
rr_color   = "#6b7a99" if rr is None else ("#00c896" if rr >= 2 else "#ff9800" if rr >= 1.5 else "#ff4d6d")

def _bar(score: int, color: str) -> str:
    return (
        f'<div style="background:rgba(255,255,255,0.07);border-radius:99px;'
        f'height:6px;margin-top:10px;overflow:hidden;">'
        f'<div style="width:{score}%;height:100%;background:{color};border-radius:99px;"></div>'
        f'</div>'
    )

rr_flag_short = (analysis.get("rr_flag", "")
                 .replace("✅", "").replace("⚠️", "").replace("❌", "").strip()[:72])

sc1, sc2, sc3 = st.columns(3)

CARD = (
    'background:linear-gradient(145deg,#1e2235,#181c2e);'
    'border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:22px 24px;min-height:130px;'
)
LABEL = 'font-size:0.68rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#6b7a99;'
VAL   = 'font-size:2.2rem;font-weight:800;letter-spacing:-0.03em;margin-top:6px;'

with sc1:
    st.markdown(
        f'<div style="{CARD}">'
        f'<div style="{LABEL}">Pump Risk Score</div>'
        f'<div style="{VAL}color:{pump_color};">{pump_score}'
        f'<span style="font-size:1rem;color:#6b7a99;">/100</span></div>'
        f'{_bar(pump_score, pump_color)}</div>',
        unsafe_allow_html=True,
    )

with sc2:
    st.markdown(
        f'<div style="{CARD}">'
        f'<div style="{LABEL}">Technical Score</div>'
        f'<div style="{VAL}color:{tech_color};">{tech_score}'
        f'<span style="font-size:1rem;color:#6b7a99;">/100</span></div>'
        f'{_bar(tech_score, tech_color)}</div>',
        unsafe_allow_html=True,
    )

with sc3:
    st.markdown(
        f'<div style="{CARD}">'
        f'<div style="{LABEL}">Risk : Reward</div>'
        f'<div style="{VAL}color:{rr_color};">{rr_display}</div>'
        f'<div style="font-size:0.78rem;color:#6b7a99;margin-top:8px;line-height:1.4;">'
        f'{rr_flag_short}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

# ── Parsed tip card + live technical snapshot ──────────────────────────────────
st.markdown("### Parsed Tip Details")

action       = (parsed.get("action") or "BUY").upper()
action_color = "#00c896" if action == "BUY" else "#ff4d6d"
tip_price    = parsed.get("tip_price")
sl           = parsed.get("stop_loss")
t1           = parsed.get("target_1")
t2           = parsed.get("target_2")
timeframe    = parsed.get("timeframe", "unknown")
confidence   = parsed.get("parse_confidence", "MEDIUM")
claims       = parsed.get("claims", [])
rsi          = analysis.get("rsi", 50)
vol_ratio    = analysis.get("vol_ratio", 1.0)

def _price_row(label: str, val, ref=None, up_is_good=True) -> str:
    if val is None:
        return (
            f'<div style="padding:9px 14px;border-radius:10px;'
            f'background:rgba(255,255,255,0.03);margin-bottom:5px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:0.7rem;color:#6b7a99;text-transform:uppercase;'
            f'letter-spacing:0.08em;font-weight:700;">{label}</span>'
            f'<span style="color:#4a5568;">—</span></div>'
        )
    pct_html = ""
    if ref and ref != val:
        chg = (val - ref) / ref * 100
        good = (chg > 0) == up_is_good
        c = "#00c896" if good else "#ff4d6d"
        pct_html = f'<span style="font-size:0.74rem;color:{c};margin-left:8px;">{chg:+.1f}%</span>'
    return (
        f'<div style="padding:9px 14px;border-radius:10px;'
        f'background:rgba(255,255,255,0.03);margin-bottom:5px;">'
        f'<div style="display:flex;justify-content:space-between;">'
        f'<span style="font-size:0.7rem;color:#6b7a99;text-transform:uppercase;'
        f'letter-spacing:0.08em;font-weight:700;">{label}</span>'
        f'{pct_html}</div>'
        f'<div style="font-size:1.05rem;font-weight:700;color:#e2e8f0;margin-top:2px;">'
        f'&#8377;{val:,.2f}</div></div>'
    )

def _ind_row(label: str, value: str, color: str = "#e2e8f0") -> str:
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
        f'<span style="font-size:0.82rem;color:#8892a4;">{label}</span>'
        f'<span style="font-weight:700;font-size:0.88rem;color:{color};">{value}</span></div>'
    )

mcap_badge = ""
if analysis.get("market_cap_cr"):
    mcap_badge = (
        f'<span style="background:rgba(255,255,255,0.06);color:#a0aec0;'
        f'border-radius:6px;padding:3px 10px;font-size:0.75rem;font-weight:600;">'
        f'&#8377;{analysis["market_cap_cr"]:,.0f}&nbsp;Cr</span>'
    )

rsi_color  = "#ff4d6d" if rsi > 70 else "#ff9800" if rsi > 60 else "#00c896" if rsi < 30 else "#e2e8f0"
vol_color  = "#ff4d6d" if vol_ratio >= 3 else "#ff9800" if vol_ratio >= 2 else "#e2e8f0"
a200       = analysis.get("above_sma200", False)
a50        = analysis.get("above_sma50", False)
a20        = analysis.get("above_sma20", False)

det1, det2 = st.columns([1, 1])

with det1:
    st.markdown(
        f'<div style="background:linear-gradient(145deg,#1e2235,#181c2e);'
        f'border:1px solid rgba(255,255,255,0.07);'
        f'border-left:4px solid {action_color};border-radius:14px;padding:18px 20px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">'
        f'<div><span style="font-size:1.3rem;font-weight:800;color:#e2e8f0;">{ticker}</span>'
        f'<span style="font-size:0.82rem;color:#6b7a99;margin-left:8px;">{company}</span></div>'
        f'<span style="background:{action_color}22;color:{action_color};'
        f'border:1px solid {action_color}44;border-radius:8px;'
        f'padding:3px 12px;font-size:0.78rem;font-weight:800;letter-spacing:0.06em;">{action}</span>'
        f'</div>'
        + _price_row("Entry Price (Tip)", tip_price)
        + _price_row("Current Market Price", analysis["current_price"],
                     ref=tip_price, up_is_good=(action == "BUY"))
        + _price_row("Stop Loss", sl, ref=tip_price, up_is_good=False)
        + _price_row("Target 1", t1, ref=tip_price, up_is_good=True)
        + _price_row("Target 2", t2, ref=tip_price, up_is_good=True)
        + f'<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">'
        f'<span style="background:rgba(255,255,255,0.06);color:#a0aec0;'
        f'border-radius:6px;padding:3px 10px;font-size:0.75rem;font-weight:600;">'
        f'&#9201; {timeframe}</span>'
        f'<span style="background:rgba(255,255,255,0.06);color:#a0aec0;'
        f'border-radius:6px;padding:3px 10px;font-size:0.75rem;font-weight:600;">'
        f'Parse: {confidence}</span>'
        + mcap_badge
        + '</div></div>',
        unsafe_allow_html=True,
    )

with det2:
    pe_row = ("" if analysis.get("pe") is None
              else _ind_row("P/E Ratio", f"{analysis['pe']:.1f}"))
    st.markdown(
        '<div style="background:linear-gradient(145deg,#1e2235,#181c2e);'
        'border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:18px 20px;">'
        '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#6b7a99;margin-bottom:10px;">'
        'Live Technical Snapshot</div>'
        + _ind_row("RSI (14)", f"{rsi:.0f}", rsi_color)
        + _ind_row("Volume", f"{vol_ratio:.1f}&times; avg", vol_color)
        + _ind_row("vs SMA 20",  "Above ✅" if a20  else "Below ❌", "#00c896" if a20  else "#ff4d6d")
        + _ind_row("vs SMA 50",  "Above ✅" if a50  else "Below ❌", "#00c896" if a50  else "#ff4d6d")
        + _ind_row("vs SMA 200", "Above ✅" if a200 else "Below ❌", "#00c896" if a200 else "#ff4d6d")
        + _ind_row("Current Price", f"&#8377;{analysis['current_price']:,.2f}")
        + pe_row
        + '</div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)

# ── Price chart ────────────────────────────────────────────────────────────────
with st.expander(f"📊 3-Month Price Chart: {ticker}", expanded=False):
    try:
        import yfinance as yf
        import plotly.graph_objects as go
        import pandas as pd

        ticker_ns = analysis.get("ticker_ns", f"{ticker}.NS")
        df_chart = yf.Ticker(ticker_ns).history(period="3mo", interval="1d", auto_adjust=True)

        if df_chart is not None and not df_chart.empty:
            df_chart.index = pd.to_datetime(df_chart.index)
            fig = go.Figure()

            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df_chart.index,
                open=df_chart["Open"], high=df_chart["High"],
                low=df_chart["Low"],  close=df_chart["Close"],
                name=ticker,
                increasing_line_color="#00c896", decreasing_line_color="#ff4d6d",
                increasing_fillcolor="#00c89666", decreasing_fillcolor="#ff4d6d66",
            ))

            # Overlay tip levels
            ref = tip_price or df_chart["Close"].iloc[-1]
            levels = {
                "Entry": (tip_price, "#f0b429", "dash"),
                "Stop Loss": (sl, "#ff4d6d", "dot"),
                "Target 1": (t1, "#00c896", "dashdot"),
                "Target 2": (t2, "#26a69a", "dashdot"),
            }
            for name, (price, color, dash) in levels.items():
                if price:
                    fig.add_hline(
                        y=price, line_color=color, line_dash=dash, line_width=1.5,
                        annotation_text=f"{name} ₹{price:,.0f}",
                        annotation_font_color=color,
                        annotation_position="right",
                    )

            fig.update_layout(
                paper_bgcolor="#181c2e", plot_bgcolor="#181c2e",
                font_color="#a0aec0", font_family="Inter",
                xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=30, b=10),
                height=340,
                xaxis=dict(showgrid=False, color="#4a5568"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4a5568"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chart data not available.")
    except Exception as e:
        st.info(f"Chart unavailable: {e}")

# ── AI Verdict ─────────────────────────────────────────────────────────────────
st.markdown("### AI Verdict")
st.markdown(
    '<div style="background:linear-gradient(145deg,#1e2235,#181c2e);'
    'border:1px solid rgba(255,255,255,0.07);border-radius:16px;'
    'padding:24px 28px;font-size:0.97rem;line-height:1.75;color:#d1d9e6;">'
    '<div style="display:flex;gap:12px;">'
    '<span style="font-size:1.6rem;line-height:1;flex-shrink:0;">🤖</span>'
    f'<div style="font-style:italic;">{ai_verdict}</div>'
    '</div></div>',
    unsafe_allow_html=True,
)

st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

# ── Detailed flags ─────────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns(2)

with col_f1:
    pump_flags = analysis.get("pump_flags", [])
    with st.expander(f"🚨 Pump Risk Factors ({len(pump_flags)})", expanded=pump_score >= 35):
        for flag in pump_flags:
            st.markdown(f"- {flag}")

with col_f2:
    tech_flags = analysis.get("tech_flags", [])
    with st.expander(f"📊 Technical Factors ({len(tech_flags)})", expanded=True):
        for flag in tech_flags:
            st.markdown(f"- {flag}")

if claims:
    with st.expander(f"💬 Claims in the Tip ({len(claims)})"):
        for claim in claims:
            st.markdown(f"- {claim}")

rr_flag = analysis.get("rr_flag", "")
if rr_flag:
    st.info(f"**Risk:Reward** — {rr_flag}")

# ── Share card ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Share This Analysis")

drift_note = ""
if analysis.get("price_drift_pct") is not None and tip_price:
    drift_note = f" (tip was at ₹{tip_price:,.2f})"

share_text = (
    f"📊 Stock Tip Analysis — {ticker} ({company})\n\n"
    f"{verdict_icon} Verdict: {verdict}\n\n"
    f"Pump Risk: {pump_score}/100\n"
    f"Technical Score: {tech_score}/100\n"
    f"R:R: {rr_display}\n"
    f"Current Price: ₹{analysis['current_price']:,.2f}{drift_note}\n"
    f"RSI: {rsi:.0f} | Vol: {vol_ratio:.1f}× avg\n\n"
    f"AI Summary:\n"
    f"{ai_verdict[:280]}{'…' if len(ai_verdict) > 280 else ''}\n\n"
    "Analyzed with Indian Stock Screener"
)

st.text_area(
    "Copy and share on WhatsApp / Telegram:",
    value=share_text,
    height=200,
    key="share_text",
)

st.caption(
    "⚠️ **Disclaimer**: This analysis is AI-generated and for educational purposes only. "
    "It is NOT financial advice. Always do your own research before investing. "
    "Past performance is not indicative of future results."
)
