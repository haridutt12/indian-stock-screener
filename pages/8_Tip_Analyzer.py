"""
Page 8: Tip Analyzer
- Paste any WhatsApp/Telegram stock tip
- AI-powered credibility verdict: pump detector, technical check, R:R assessment
- Claude Haiku parses the tip → yfinance analysis → Claude Sonnet verdict
"""
import streamlit as st

st.set_page_config(page_title="Tip Analyzer", layout="wide", page_icon="🔍")
from ui.styles import inject_global_css; inject_global_css()

# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="
    background: linear-gradient(135deg, #0d1117 0%, #161b27 60%, #0d1117 100%);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
    padding: 32px 40px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
">
  <div style="
      position:absolute; top:-60px; right:-60px;
      width:240px; height:240px;
      background: radial-gradient(circle, rgba(255,77,109,0.12) 0%, transparent 70%);
      border-radius:50%; pointer-events:none;
  "></div>
  <div style="display:flex; align-items:center; gap:14px; margin-bottom:8px;">
    <span style="font-size:2.2rem;">🔍</span>
    <h1 style="margin:0; font-size:2rem; font-weight:800;
        background: linear-gradient(135deg, #ffffff 0%, #a0aec0 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
      Stock Tip Analyzer
    </h1>
  </div>
  <p style="margin:0; color:#6b7a99; font-size:0.95rem; max-width:600px;">
    Got a tip on WhatsApp or Telegram? Paste it below and get an instant credibility
    verdict — pump risk score, technical alignment, and a plain-English AI assessment.
  </p>
</div>
""", unsafe_allow_html=True)

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

with col_input:
    prefill = SAMPLE_TIPS.get(sample_choice, "")
    tip_text = st.text_area(
        "Paste your tip here",
        value=prefill,
        height=130,
        placeholder=(
            "Paste any WhatsApp / Telegram stock tip here…\n\n"
            "Example: 'Buy RELIANCE at 2800, SL 2750, target 2900. Strong breakout!'"
        ),
        key="tip_input",
    )

analyze_btn = st.button("🔍 Analyze This Tip", type="primary", disabled=not tip_text.strip())

if not tip_text.strip() and not analyze_btn:
    st.markdown("""
    <div style="
        border: 1px dashed rgba(255,255,255,0.1);
        border-radius: 14px;
        padding: 36px;
        text-align: center;
        color: #4a5568;
        margin-top: 12px;
    ">
      <div style="font-size:2.5rem; margin-bottom:10px;">📱</div>
      <div style="font-weight:600; font-size:1rem; margin-bottom:6px; color:#6b7a99;">
        Paste any tip to get started
      </div>
      <div style="font-size:0.85rem;">
        Works with WhatsApp forwards, Telegram tips, stock advisory messages,<br>
        and any format — our AI extracts the details automatically.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

if not analyze_btn:
    st.stop()

# ── Run the pipeline ───────────────────────────────────────────────────────────
from analysis.tip_analyzer import parse_tip, analyze_tip, get_ai_verdict

with st.spinner("Step 1/3 — Parsing tip with AI…"):
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

# ── Verdict banner ─────────────────────────────────────────────────────────────
verdict       = analysis["verdict"]
verdict_color = analysis["verdict_color"]
verdict_icon  = analysis["verdict_icon"]

verdict_bg = {
    "LIKELY PUMP": "linear-gradient(135deg, rgba(255,77,109,0.18) 0%, rgba(255,77,109,0.06) 100%)",
    "HIGH RISK":   "linear-gradient(135deg, rgba(255,152,0,0.18) 0%, rgba(255,152,0,0.06) 100%)",
    "MIXED":       "linear-gradient(135deg, rgba(240,180,41,0.18) 0%, rgba(240,180,41,0.06) 100%)",
    "CREDIBLE":    "linear-gradient(135deg, rgba(0,200,150,0.18) 0%, rgba(0,200,150,0.06) 100%)",
}.get(verdict, "")

st.markdown(f"""
<div style="
    background: {verdict_bg};
    border: 1px solid {verdict_color}55;
    border-left: 5px solid {verdict_color};
    border-radius: 16px;
    padding: 24px 28px;
    margin: 20px 0;
    display: flex;
    align-items: center;
    gap: 18px;
">
  <div style="font-size:3rem; line-height:1;">{verdict_icon}</div>
  <div>
    <div style="font-size:0.72rem; font-weight:700; letter-spacing:0.12em;
        text-transform:uppercase; color:#6b7a99; margin-bottom:4px;">
      Verdict
    </div>
    <div style="font-size:2rem; font-weight:800; color:{verdict_color}; letter-spacing:-0.02em;">
      {verdict}
    </div>
    <div style="font-size:0.88rem; color:#8892a4; margin-top:2px;">
      {analysis['company_name']} ({analysis['ticker']})
      {f" · {analysis['sector']}" if analysis.get('sector') else ""}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Three score columns ────────────────────────────────────────────────────────
pump_score = analysis["pump_score"]
tech_score = analysis["tech_score"]
rr         = analysis.get("rr")

pump_color = "#ff4d6d" if pump_score >= 55 else "#ff9800" if pump_score >= 35 else "#00c896"
tech_color = "#00c896" if tech_score >= 62 else "#ff9800" if tech_score < 40 else "#f0b429"
rr_color   = "#00c896" if rr and rr >= 2 else "#ff9800" if rr and rr >= 1.5 else "#ff4d6d"
rr_display = f"1:{rr:.1f}" if rr else "N/A"

def score_bar(score: int, color: str) -> str:
    """Return HTML for a thin progress bar."""
    return f"""
    <div style="background:rgba(255,255,255,0.07); border-radius:99px;
        height:6px; margin-top:10px; overflow:hidden;">
      <div style="width:{score}%; height:100%;
          background:{color}; border-radius:99px;
          transition: width 0.6s ease;"></div>
    </div>"""

sc1, sc2, sc3 = st.columns(3)

with sc1:
    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2235,#181c2e);
        border:1px solid rgba(255,255,255,0.06); border-radius:16px;
        padding:22px 24px; height:140px;">
      <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.1em;
          text-transform:uppercase; color:#6b7a99;">Pump Risk Score</div>
      <div style="font-size:2.2rem; font-weight:800; color:{pump_color};
          margin-top:6px; letter-spacing:-0.03em;">{pump_score}<span style="font-size:1rem;color:#6b7a99;">/100</span></div>
      {score_bar(pump_score, pump_color)}
    </div>
    """, unsafe_allow_html=True)

with sc2:
    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2235,#181c2e);
        border:1px solid rgba(255,255,255,0.06); border-radius:16px;
        padding:22px 24px; height:140px;">
      <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.1em;
          text-transform:uppercase; color:#6b7a99;">Technical Score</div>
      <div style="font-size:2.2rem; font-weight:800; color:{tech_color};
          margin-top:6px; letter-spacing:-0.03em;">{tech_score}<span style="font-size:1rem;color:#6b7a99;">/100</span></div>
      {score_bar(tech_score, tech_color)}
    </div>
    """, unsafe_allow_html=True)

with sc3:
    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2235,#181c2e);
        border:1px solid rgba(255,255,255,0.06); border-radius:16px;
        padding:22px 24px; height:140px;">
      <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.1em;
          text-transform:uppercase; color:#6b7a99;">Risk : Reward</div>
      <div style="font-size:2.2rem; font-weight:800; color:{rr_color};
          margin-top:6px; letter-spacing:-0.03em;">{rr_display}</div>
      <div style="font-size:0.78rem; color:#6b7a99; margin-top:10px; line-height:1.4;">
        {analysis.get('rr_flag', '').replace('✅','').replace('⚠️','').replace('❌','').strip()[:68]}
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

# ── Parsed tip details + live price ───────────────────────────────────────────
st.markdown("### Parsed Tip Details")

det1, det2 = st.columns([1, 1])

action      = parsed.get("action", "BUY")
action_color = "#00c896" if action == "BUY" else "#ff4d6d"
tip_price   = parsed.get("tip_price")
sl          = parsed.get("stop_loss")
t1          = parsed.get("target_1")
t2          = parsed.get("target_2")
timeframe   = parsed.get("timeframe", "unknown")
confidence  = parsed.get("parse_confidence", "MEDIUM")
claims      = parsed.get("claims", [])

with det1:
    def price_line(label: str, val, ref=None, positive_dir=True) -> str:
        if val is None:
            return f"""
            <div style="padding:10px 14px; border-radius:10px;
                background:rgba(255,255,255,0.03); margin-bottom:6px;">
              <span style="font-size:0.7rem; color:#6b7a99; text-transform:uppercase;
                  letter-spacing:0.08em; font-weight:700;">{label}</span>
              <span style="float:right; color:#4a5568; font-size:0.9rem;">—</span>
            </div>"""
        pct = ""
        if ref and ref != val:
            change = (val - ref) / ref * 100
            pct_color = "#00c896" if (change > 0) == positive_dir else "#ff4d6d"
            pct = f'<span style="float:right; font-size:0.75rem; color:{pct_color};">{change:+.1f}%</span>'
        return f"""
        <div style="padding:10px 14px; border-radius:10px;
            background:rgba(255,255,255,0.03); margin-bottom:6px;">
          <span style="font-size:0.7rem; color:#6b7a99; text-transform:uppercase;
              letter-spacing:0.08em; font-weight:700;">{label}</span>
          {pct}
          <div style="font-size:1.05rem; font-weight:700; color:#e2e8f0; margin-top:2px;">
            ₹{val:,.2f}
          </div>
        </div>"""

    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2235,#181c2e);
        border:1px solid rgba(255,255,255,0.07);
        border-left:4px solid {action_color};
        border-radius:14px; padding:18px 20px;">
      <div style="display:flex; justify-content:space-between; align-items:center;
          margin-bottom:14px;">
        <div>
          <span style="font-size:1.3rem; font-weight:800; color:#e2e8f0;">
            {analysis['ticker']}
          </span>
          <span style="font-size:0.82rem; color:#6b7a99; margin-left:8px;">
            {analysis.get('company_name', '')}
          </span>
        </div>
        <span style="background:{action_color}22; color:{action_color};
            border:1px solid {action_color}44; border-radius:8px;
            padding:3px 12px; font-size:0.78rem; font-weight:800; letter-spacing:0.06em;">
          {action}
        </span>
      </div>
      {price_line("Entry Price (Tip)", tip_price)}
      {price_line("Current Market Price", analysis['current_price'],
                  ref=tip_price, positive_dir=(action=="BUY"))}
      {price_line("Stop Loss", sl, ref=tip_price, positive_dir=False)}
      {price_line("Target 1", t1, ref=tip_price, positive_dir=True)}
      {price_line("Target 2", t2, ref=tip_price, positive_dir=True)}
      <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
        <span style="background:rgba(255,255,255,0.06); color:#a0aec0;
            border-radius:6px; padding:3px 10px; font-size:0.75rem; font-weight:600;">
          ⏱ {timeframe}
        </span>
        <span style="background:rgba(255,255,255,0.06); color:#a0aec0;
            border-radius:6px; padding:3px 10px; font-size:0.75rem; font-weight:600;">
          Parse: {confidence}
        </span>
        {"" if not analysis.get("market_cap_cr") else
         f'<span style="background:rgba(255,255,255,0.06); color:#a0aec0; border-radius:6px; padding:3px 10px; font-size:0.75rem; font-weight:600;">₹{analysis["market_cap_cr"]:,.0f} Cr</span>'}
      </div>
    </div>
    """, unsafe_allow_html=True)

with det2:
    # Live technical snapshot
    rsi      = analysis.get("rsi", 50)
    rsi_color = "#ff4d6d" if rsi > 70 else "#ff9800" if rsi > 60 else "#00c896" if rsi < 30 else "#e2e8f0"

    def indicator_row(label, value, badge_color="#e2e8f0") -> str:
        return f"""
        <div style="display:flex; justify-content:space-between; align-items:center;
            padding:9px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
          <span style="font-size:0.82rem; color:#8892a4;">{label}</span>
          <span style="font-weight:700; font-size:0.88rem; color:{badge_color};">{value}</span>
        </div>"""

    above200 = analysis.get("above_sma200", False)
    above50  = analysis.get("above_sma50", False)
    above20  = analysis.get("above_sma20", False)
    vol_ratio = analysis.get("vol_ratio", 1.0)
    vol_color = "#ff4d6d" if vol_ratio >= 3 else "#ff9800" if vol_ratio >= 2 else "#e2e8f0"

    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2235,#181c2e);
        border:1px solid rgba(255,255,255,0.07); border-radius:14px; padding:18px 20px;">
      <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.1em;
          text-transform:uppercase; color:#6b7a99; margin-bottom:10px;">
        Live Technical Snapshot
      </div>
      {indicator_row("RSI (14)", f"{rsi:.0f}", rsi_color)}
      {indicator_row("Volume", f"{vol_ratio:.1f}× avg", vol_color)}
      {indicator_row("vs SMA 20", "Above ✅" if above20 else "Below ❌",
                     "#00c896" if above20 else "#ff4d6d")}
      {indicator_row("vs SMA 50", "Above ✅" if above50 else "Below ❌",
                     "#00c896" if above50 else "#ff4d6d")}
      {indicator_row("vs SMA 200", "Above ✅" if above200 else "Below ❌",
                     "#00c896" if above200 else "#ff4d6d")}
      {indicator_row("Current Price", f"₹{analysis['current_price']:,.2f}")}
      {'' if analysis.get('pe') is None else indicator_row("P/E Ratio", f"{analysis['pe']:.1f}")}
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)

# ── AI Verdict ─────────────────────────────────────────────────────────────────
st.markdown("### AI Verdict")
st.markdown(f"""
<div style="
    background: linear-gradient(145deg, #1e2235 0%, #181c2e 100%);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 24px 28px;
    font-size: 0.97rem;
    line-height: 1.75;
    color: #d1d9e6;
    font-style: italic;
">
  <div style="display:flex; gap:12px;">
    <span style="font-size:1.6rem; line-height:1; flex-shrink:0;">🤖</span>
    <div>{ai_verdict}</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

# ── Detailed flags ─────────────────────────────────────────────────────────────
col_flags1, col_flags2 = st.columns(2)

with col_flags1:
    pump_flags = analysis.get("pump_flags", [])
    with st.expander(f"🚨 Pump Risk Factors ({len(pump_flags)})", expanded=pump_score >= 35):
        for flag in pump_flags:
            st.markdown(f"- {flag}")

with col_flags2:
    tech_flags = analysis.get("tech_flags", [])
    with st.expander(f"📊 Technical Factors ({len(tech_flags)})", expanded=True):
        for flag in tech_flags:
            st.markdown(f"- {flag}")

# Claims from the tip
if claims:
    with st.expander(f"💬 Claims in the Tip ({len(claims)})"):
        for claim in claims:
            st.markdown(f"- {claim}")

# ── R:R section ────────────────────────────────────────────────────────────────
rr_flag = analysis.get("rr_flag", "")
if rr_flag:
    icon = "✅" if rr and rr >= 2 else "⚠️" if rr and rr >= 1.5 else "❌"
    st.info(f"**Risk:Reward** — {rr_flag}")

# ── Share card ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Share This Analysis")

drift_str = ""
if analysis.get("price_drift_pct") is not None:
    drift_str = f" (tip was at ₹{tip_price})" if tip_price else ""

share_text = f"""📊 Stock Tip Analysis — {analysis['ticker']} ({analysis.get('company_name','')})

{verdict_icon} Verdict: {verdict}

Pump Risk: {pump_score}/100
Technical Score: {tech_score}/100
R:R: {rr_display}
Current Price: ₹{analysis['current_price']:,.2f}{drift_str}
RSI: {rsi:.0f} | Vol: {vol_ratio:.1f}× avg

AI Summary:
{ai_verdict[:280]}{'…' if len(ai_verdict) > 280 else ''}

Analyzed with Indian Stock Screener"""

st.text_area(
    "Copy and share this summary:",
    value=share_text,
    height=200,
    key="share_text",
    help="Copy this text to share on WhatsApp or Telegram",
)

st.caption(
    "⚠️ **Disclaimer**: This analysis is AI-generated and for educational purposes only. "
    "It is NOT financial advice. Always do your own research before investing. "
    "Past performance is not indicative of future results."
)
