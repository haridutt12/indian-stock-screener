"""
Page 4: Technical Screener
"""
import datetime as _dt
import streamlit as st
import pandas as pd
from data.fetcher import fetch_stock_data
from analysis.technical import compute_indicators, get_technical_summary, detect_patterns
from config.stock_universe import NIFTY_50, NIFTY_200
from config.settings import RSI_PERIOD

st.set_page_config(page_title="Technical Screener · NiftyEdge", layout="wide", page_icon="📈")
from ui.styles import inject_global_css, page_header, show_loading, auth_guard, user_sidebar; inject_global_css()
auth_guard()

# ── PAGE HEADER ───────────────────────────────────────────────────────────────────────────────
page_header("📈 Technical Screener", subtitle="NSE · Equity · Technical Analysis")

# ── NL QUERY BAR ─────────────────────────────────────────────────────────────
from analysis.nl_screener import parse_nl_query, apply_nl_filters
from ui.llm_guard import llm_guard, record_llm_tokens

st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">Ask in Plain English</div>',
    unsafe_allow_html=True,
)
_nl_col, _nl_btn_col = st.columns([5, 1])
with _nl_col:
    nl_input = st.text_input(
        "nl_query",
        value=st.session_state.get("_nl_query_val", ""),
        placeholder='e.g. "show me oversold quality stocks above 200 SMA with volume spike"',
        label_visibility="collapsed",
        key="_nl_input_field",
    )
with _nl_btn_col:
    nl_run = st.button("✨ Ask AI", type="primary", use_container_width=True)

if nl_run and nl_input.strip():
    st.session_state["_nl_query_val"] = nl_input.strip()
    if llm_guard(estimated_tokens=600, label="NL Screener"):
        with st.spinner("Interpreting your query…"):
            _nl_parsed = parse_nl_query(nl_input.strip())
        record_llm_tokens(600)
        st.session_state["_nl_parsed"] = _nl_parsed

_nl_parsed = st.session_state.get("_nl_parsed")
if _nl_parsed:
    _err = _nl_parsed.get("error")
    _summary = _nl_parsed.get("summary", "")
    with st.expander("🔍 Interpreted as…", expanded=True):
        st.markdown(
            f'<div style="color:#00c896;font-size:0.85rem;font-weight:600;margin-bottom:8px;">'
            f'{_summary}</div>',
            unsafe_allow_html=True,
        )
        _flt_html = "".join([
            f'<span style="background:rgba(124,131,253,0.12);color:#7c83fd;'
            f'border-radius:5px;padding:2px 8px;font-size:0.72rem;font-weight:600;margin-right:4px;">'
            f'{f["column"]} {f["operator"]} {f["value"]}</span>'
            for f in _nl_parsed.get("filters", [])
        ])
        if _flt_html:
            st.markdown(_flt_html, unsafe_allow_html=True)
        if _err:
            st.warning(f"Some filters skipped: {_err}")

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── SIDEBAR ────────────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Technical Filters")
    universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"])
    universe = NIFTY_50 if universe_choice == "Nifty 50" else NIFTY_200
    tickers = list(universe.values())

    st.subheader("RSI")
    rsi_min = st.slider("RSI Min", 0, 100, 0)
    rsi_max = st.slider("RSI Max", 0, 100, 100)

    st.subheader("Trend")
    trend_filter = st.multiselect(
        "Trend", ["Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"], default=[]
    )

    st.subheader("Moving Averages")
    above_sma200 = st.checkbox("Above SMA 200")
    above_sma50  = st.checkbox("Above SMA 50")
    golden_cross = st.checkbox("Golden Cross")

    st.subheader("MACD")
    macd_bullish = st.checkbox("MACD Bullish")

    st.subheader("Volume")
    vol_spike = st.checkbox("Volume Spike (>1.5x avg)")

    st.subheader("Sort By")
    sort_by  = st.selectbox("Sort", ["tech_strength", "rsi", "volume_ratio"])
    sort_asc = st.checkbox("Ascending", value=False)

    run_btn = st.button("📈 Run Technical Scan", type="primary", use_container_width=True)

    st.divider()
    user_sidebar()
# ── PRESET CARDS ─────────────────────────────────────────────────────────────────────────────
PRESETS_UI = [
    {"label": "Oversold",     "icon": "🔻", "sub": "RSI < 35",        "color": "#ff4d6d", "rgb": "255,77,109",
     "desc": "Potential bounce candidates near support"},
    {"label": "Breakout",     "icon": "🚀", "sub": "Vol + SMA200",    "color": "#f0b429", "rgb": "240,180,41",
     "desc": "Above SMA200 with 1.5× volume confirmation"},
    {"label": "Golden Cross", "icon": "✨", "sub": "SMA50 > SMA200",  "color": "#00c896", "rgb": "0,200,150",
     "desc": "Long-term bullish crossover signal"},
    {"label": "Momentum",     "icon": "💪", "sub": "RSI 50–70",       "color": "#7c83fd", "rgb": "124,131,253",
     "desc": "Trending stocks not yet overbought"},
]

st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Quick Presets</div>',
    unsafe_allow_html=True,
)

p_cols = st.columns(4)
_preset_btns = {}
for col, p, key in zip(p_cols, PRESETS_UI, ["run_os", "run_bo", "run_gc", "run_mo"]):
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
            f'border:1px solid rgba(255,255,255,0.06);border-top:3px solid {p["color"]};'
            f'border-radius:14px;padding:16px;margin-bottom:6px;">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<div style="width:32px;height:32px;border-radius:8px;'
            f'background:rgba({p["rgb"]},0.12);display:flex;align-items:center;'
            f'justify-content:center;font-size:1.1rem;flex-shrink:0;">{p["icon"]}</div>'
            f'<div>'
            f'<div style="font-size:0.82rem;font-weight:700;color:#e2e8f0;">{p["label"]}</div>'
            f'<div style="font-size:0.65rem;font-weight:700;color:{p["color"]};letter-spacing:0.04em;">{p["sub"]}</div>'
            f'</div></div>'
            f'<div style="font-size:0.72rem;color:#475569;line-height:1.45;margin-bottom:12px;">{p["desc"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _preset_btns[key] = st.button(f"Run {p['label']}", key=key, use_container_width=True)

run_oversold = _preset_btns["run_os"]
run_breakout = _preset_btns["run_bo"]
run_golden   = _preset_btns["run_gc"]
run_momentum = _preset_btns["run_mo"]

st.markdown('<div style="margin-bottom:8px;"></div>', unsafe_allow_html=True)

# ── SCAN INSIGHTS ──────────────────────────────────────────────────────────────────────────────────
SCAN_INSIGHTS = [
    ("📊 RSI Explained",
     "RSI measures momentum on a 0–100 scale. Below 30 = oversold. Above 70 = overbought. RSI 40–60 = neutral momentum."),
    ("✨ Golden Cross",
     "Occurs when SMA50 crosses above SMA200 — historically one of the most reliable long-term bullish signals."),
    ("🚀 Volume Breakouts",
     "Price breakouts on 1.5× or higher average volume are far more reliable. High volume confirms conviction behind a move."),
    ("💪 Momentum Zone",
     "RSI 50–70 is the sweet spot — trending up but not yet overbought. Often offers the best risk-reward for momentum plays."),
    ("📈 200-Day MA",
     "The most widely watched long-term trend indicator. Above = bull territory. FIIs use this as a key allocation filter."),
    ("🔄 MACD Crossovers",
     "MACD signals a buy when it crosses above its signal line. Works best when price is also above SMA200."),
]

should_run = run_btn or run_oversold or run_breakout or run_golden or run_momentum

if should_run:
    fetch_slot = st.empty()

    def _show_insight(idx: int, status: str, pct: float):
        fact = SCAN_INSIGHTS[idx % len(SCAN_INSIGHTS)]
        fetch_slot.markdown(
            f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:22px 26px;margin:8px 0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
            f'<span style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:#475569;">{status}</span>'
            f'<span style="font-size:0.72rem;color:#f0b429;font-weight:700;">{pct:.0f}%</span>'
            f'</div>'
            f'<div style="background:rgba(255,255,255,0.06);border-radius:99px;'
            f'height:4px;margin-bottom:18px;overflow:hidden;">'
            f'<div style="width:{pct}%;height:100%;'
            f'background:linear-gradient(90deg,#f0b429,#00c896);border-radius:99px;"></div></div>'
            f'<div style="font-size:0.9rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;">{fact[0]}</div>'
            f'<div style="font-size:0.82rem;color:#64748b;line-height:1.65;">{fact[1]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _show_insight(0, f"Fetching data for {len(tickers)} stocks…", 5)
    price_data = fetch_stock_data(tickers, period="1y")

    rows  = []
    total = len(price_data)
    for i, (ticker, df) in enumerate(price_data.items()):
        pct   = 10 + (i + 1) / total * 88
        label = ticker.replace(".NS", "").replace(".BO", "")
        _show_insight(i, f"Scanning {label}… ({i+1}/{total})", pct)

        if df is None or df.empty:
            continue
        try:
            df_ind  = compute_indicators(df)
            summary = get_technical_summary(df_ind)
        except Exception:
            continue
        if not summary:
            continue
        rows.append({
            "ticker":        label,
            "ticker_yf":     ticker,
            "close":         summary.get("close"),
            "rsi":           summary.get("rsi"),
            "trend":         summary.get("trend"),
            "tech_strength": summary.get("strength"),
            "atr":           summary.get("atr"),
            "volume_ratio":  summary.get("volume_ratio"),
            "macd_bullish":  summary.get("macd_bullish"),
            "patterns":      ", ".join(summary.get("patterns", [])),
            "support":       summary.get("support"),
            "resistance":    summary.get("resistance"),
            "above_sma200":  "Above SMA200" in summary.get("patterns", []),
            "above_sma50":   "Above SMA50"  in summary.get("patterns", []),
            "golden_cross":  "Golden Cross" in summary.get("patterns", []),
            "vol_spike":     summary.get("volume_ratio", 1) >= 1.5,
        })

    fetch_slot.empty()
    st.session_state.tech_result_df = pd.DataFrame(rows)

if "tech_result_df" not in st.session_state:
    if _nl_parsed and _nl_parsed.get("filters"):
        st.info("Query interpreted. Now click **Run Technical Scan** (or a preset) to apply it to live data.", icon="ℹ️")
    st.stop()

result_df = st.session_state.tech_result_df.copy()

# Apply NL filters if present (takes precedence over preset buttons)
_nl_active = bool(_nl_parsed and _nl_parsed.get("filters") and not run_btn
                  and not run_oversold and not run_breakout
                  and not run_golden and not run_momentum)
if _nl_active:
    result_df = apply_nl_filters(result_df, _nl_parsed)
elif run_oversold:
    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] < 35)]
elif run_breakout:
    result_df = result_df[result_df["above_sma200"] & result_df["vol_spike"]]
elif run_golden:
    result_df = result_df[result_df["golden_cross"]]
elif run_momentum:
    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] >= 50) & (result_df["rsi"] <= 70)]
else:
    if rsi_min > 0:    result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] >= rsi_min)]
    if rsi_max < 100:  result_df = result_df[result_df["rsi"].notna() & (result_df["rsi"] <= rsi_max)]
    if trend_filter:   result_df = result_df[result_df["trend"].isin(trend_filter)]
    if above_sma200:   result_df = result_df[result_df["above_sma200"]]
    if above_sma50:    result_df = result_df[result_df["above_sma50"]]
    if golden_cross:   result_df = result_df[result_df["golden_cross"]]
    if macd_bullish:   result_df = result_df[result_df["macd_bullish"] == True]
    if vol_spike:      result_df = result_df[result_df["vol_spike"]]

if sort_by in result_df.columns:
    result_df = result_df.sort_values(sort_by, ascending=sort_asc)

# ── STATS STRIP ────────────────────────────────────────────────────────────────────────────────────
avg_rsi   = result_df["rsi"].dropna().mean()          if "rsi"           in result_df.columns else None
avg_str   = result_df["tech_strength"].dropna().mean() if "tech_strength" in result_df.columns else None
avg_vol   = result_df["volume_ratio"].dropna().mean()  if "volume_ratio"  in result_df.columns else None

st.markdown(
    f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Matched</div>'
    f'<div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;">{len(result_df)}'
    f'<span style="font-size:0.8rem;color:#475569;"> stocks</span></div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg RSI</div>'
    f'<div style="color:#f0b429;font-size:1.5rem;font-weight:800;">'
    + (f'{avg_rsi:.1f}' if avg_rsi else "—") +
    f'</div></div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg Strength</div>'
    f'<div style="color:#00c896;font-size:1.5rem;font-weight:800;">'
    + (f'{avg_str:.0f}/100' if avg_str else "—") +
    f'</div></div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg Vol Ratio</div>'
    f'<div style="color:#7c83fd;font-size:1.5rem;font-weight:800;">'
    + (f'{avg_vol:.2f}x' if avg_vol else "—") +
    f'</div></div>'

    f'</div>',
    unsafe_allow_html=True,
)

if result_df.empty:
    st.markdown(
        '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);'
        'border-radius:14px;padding:32px;text-align:center;">'
        '<div style="font-size:1.5rem;margin-bottom:8px;">💭</div>'
        '<div style="color:#475569;font-weight:600;">No stocks match your criteria</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── RESULTS TABLE ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    f'Scan Results — {len(result_df)} stocks</div>',
    unsafe_allow_html=True,
)
display_cols = ["ticker", "close", "rsi", "trend", "tech_strength", "volume_ratio", "macd_bullish", "patterns", "support", "resistance"]
_show_df = result_df[[c for c in display_cols if c in result_df.columns]]
st.dataframe(_show_df, use_container_width=True, hide_index=True)

_csv_col, _ = st.columns([1, 4])
with _csv_col:
    st.download_button(
        "⬇ Export CSV",
        data=_show_df.to_csv(index=False).encode("utf-8"),
        file_name=f"niftyedge_screener_{_dt.date.today().isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── CHART DETAIL ──────────────────────────────────────────────────────────────────────────────
st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Chart Detail</div>',
    unsafe_allow_html=True,
)
from data.fetcher import fetch_single_stock
from ui.charts import candlestick_chart, rsi_macd_chart

selected = st.selectbox("Select stock for chart:", result_df["ticker"].tolist(), label_visibility="collapsed")
if selected:
    ticker_yf = result_df[result_df["ticker"] == selected]["ticker_yf"].iloc[0]
    _chart_slot = show_loading(f"Fetching 1-year OHLCV data for {selected}…", "#00c896")
    df = fetch_single_stock(ticker_yf)
    _chart_slot.empty()
    if df is not None:
            df_ind  = compute_indicators(df)
            summary = get_technical_summary(df_ind)

            c1, c2 = st.columns([3, 1])
            with c1:
                st.plotly_chart(candlestick_chart(df_ind, selected, show_volume=True, show_sma=True), use_container_width=True, key="tech_candle")
                st.plotly_chart(rsi_macd_chart(df_ind), use_container_width=True, key="tech_rsi")
            with c2:
                detail_items = [
                    ("RSI",        f'{summary.get("rsi", 0):.1f}',          "#f0b429"),
                    ("Trend",      summary.get("trend", "—"),                "#e2e8f0"),
                    ("Strength",   f'{summary.get("strength", 0):.0f}/100', "#00c896"),
                    ("Vol Ratio",  f'{summary.get("volume_ratio", 1):.2f}x', "#7c83fd"),
                    ("Support",    f'₹{summary.get("support", 0):.2f}',     "#ff4d6d"),
                    ("Resistance", f'₹{summary.get("resistance", 0):.2f}',  "#f0b429"),
                ]
                st.markdown(
                    '<div style="display:flex;flex-direction:column;gap:8px;">'
                    + "".join([
                        f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                        f'border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:12px 14px;">'
                        f'<div style="color:#475569;font-size:0.62rem;font-weight:700;'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">{lbl}</div>'
                        f'<div style="color:{col};font-size:1rem;font-weight:800;">{val}</div>'
                        f'</div>'
                        for lbl, val, col in detail_items
                    ])
                    + '</div>',
                    unsafe_allow_html=True,
                )
                pats = summary.get("patterns", [])
                if pats:
                    st.markdown('<div style="margin-top:10px;"></div>', unsafe_allow_html=True)
                    chips = " ".join([
                        f'<span style="display:inline-block;background:rgba(0,200,150,0.1);'
                        f'color:#00c896;border:1px solid rgba(0,200,150,0.25);'
                        f'border-radius:4px;padding:2px 8px;font-size:0.68rem;font-weight:600;margin:2px;">{p}</span>'
                        for p in pats
                    ])
                    st.markdown(f'<div style="line-height:1.8;">{chips}</div>', unsafe_allow_html=True)
