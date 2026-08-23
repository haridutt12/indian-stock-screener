"""
Page 3: Fundamental Screener
"""
import streamlit as st
import pandas as pd
from data.fetcher import fetch_bulk_fundamentals
from analysis.fundamental import build_fundamental_df
from analysis.screener import StockScreener, PRESETS, build_screen_data
from config.stock_universe import NIFTY_50, NIFTY_200, get_all_sectors, SECTOR_MAP

st.set_page_config(page_title="Fundamental Screener · NiftyEdge", layout="wide", page_icon="🔍")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar; inject_global_css()
auth_guard()

# ── PAGE HEADER ───────────────────────────────────────────────────────────────────────────────
page_header("🔍 Fundamental Screener", subtitle="NSE · Equity · Fundamentals")

# ── SIDEBAR FILTERS ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"])
    universe = NIFTY_50 if universe_choice == "Nifty 50" else NIFTY_200
    tickers = list(universe.values())

    st.subheader("Preset Screeners")
    preset_name = st.selectbox("Quick Preset", ["Custom", *PRESETS.keys()])

    st.subheader("Valuation")
    pe_min = st.number_input("PE Min", value=0.0, min_value=0.0)
    pe_max = st.number_input("PE Max", value=50.0, min_value=0.0)

    st.subheader("Quality")
    roe_min = st.number_input("ROE Min (%)", value=0.0, min_value=0.0)
    profit_margin_min = st.number_input("Net Margin Min (%)", value=0.0)

    st.subheader("Balance Sheet")
    de_max = st.number_input("Debt/Equity Max", value=200.0)

    st.subheader("Dividend")
    div_min = st.number_input("Dividend Yield Min (%)", value=0.0)

    st.subheader("Sector")
    all_sectors = ["All"] + sorted(set(SECTOR_MAP.values()))
    selected_sector = st.selectbox("Sector", all_sectors)

    st.subheader("Sort By")
    sort_options = {
        "Composite Score": "composite_score",
        "PE Ratio": "pe",
        "ROE": "roe_pct",
        "Dividend Yield": "div_yield_pct",
        "Market Cap": "market_cap_cr",
        "Profit Margin": "profit_margin_pct",
    }
    sort_by_label = st.selectbox("Sort by", list(sort_options.keys()))
    sort_col = sort_options[sort_by_label]
    sort_asc = st.checkbox("Ascending", value=False)

    run_btn = st.button("🔍 Run Screener", type="primary", use_container_width=True)

    st.divider()
    user_sidebar()
# ── PRESET CARDS ─────────────────────────────────────────────────────────────────────────────
PRESET_CARDS = [
    {"key": "Value Picks",         "icon": "💎", "color": "#f0b429", "rgb": "240,180,41",
     "desc": "Low PE, high ROE, quality balance sheet"},
    {"key": "Quality Compounders", "icon": "📈", "color": "#00c896", "rgb": "0,200,150",
     "desc": "High margins, low debt, consistent growth"},
    {"key": "Dividend Stars",      "icon": "💰", "color": "#7c83fd", "rgb": "124,131,253",
     "desc": "High yield, stable payouts, low payout ratio"},
    {"key": "Custom",              "icon": "⚙️", "color": "#6b7a99", "rgb": "107,122,153",
     "desc": "Build your own filter from the sidebar"},
]

st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Quick Presets</div>',
    unsafe_allow_html=True,
)
preset_cols = st.columns(4)
for col, pc in zip(preset_cols, PRESET_CARDS):
    is_active = preset_name == pc["key"]
    border = f'border:2px solid {pc["color"]}60;' if is_active else 'border:1px solid rgba(255,255,255,0.06);'
    with col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
            f'{border}border-top:3px solid {pc["color"]};border-radius:14px;padding:16px;margin-bottom:4px;">'
            f'<div style="font-size:1.5rem;margin-bottom:8px;">{pc["icon"]}</div>'
            f'<div style="font-size:0.82rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;">{pc["key"]}</div>'
            f'<div style="font-size:0.7rem;color:#475569;line-height:1.4;">{pc["desc"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

# ── FETCH DATA ────────────────────────────────────────────────────────────────────────────────
if "fundamental_df" not in st.session_state:
    st.session_state.fundamental_df = None

if run_btn or st.session_state.fundamental_df is None:
    scan_banner = st.empty()
    scan_banner.markdown(
        f'<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.2);'
        f'border-radius:12px;padding:14px 18px;display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:#f0b429;'
        f'animation:pulse 1.2s ease-in-out infinite;flex-shrink:0;"></div>'
        f'<div style="color:#f0b429;font-weight:700;font-size:0.85rem;">'
        f'Fetching fundamentals for {len(tickers)} stocks…</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    fundamentals = fetch_bulk_fundamentals(tickers)
    fund_df = build_fundamental_df(fundamentals.to_dict("records"))
    st.session_state.fundamental_df = fund_df
    scan_banner.empty()

fund_df = st.session_state.fundamental_df

if fund_df is None or fund_df.empty:
    st.error("No data available. Try running the screener.")
    st.stop()

# ── APPLY FILTERS ─────────────────────────────────────────────────────────────────────────────
if selected_sector != "All":
    fund_df = fund_df[fund_df["sector"] == selected_sector]

if preset_name != "Custom" and preset_name in PRESETS:
    result_df = PRESETS[preset_name](fund_df)
else:
    screener = StockScreener()
    if pe_min > 0:   screener.add_filter("pe", "gte", pe_min)
    if pe_max > 0:   screener.add_filter("pe", "lte", pe_max)
    if roe_min > 0:  screener.add_filter("roe_pct", "gte", roe_min)
    if profit_margin_min > 0: screener.add_filter("profit_margin_pct", "gte", profit_margin_min)
    if de_max < 200: screener.add_filter("debt_equity", "lte", de_max)
    if div_min > 0:  screener.add_filter("div_yield_pct", "gte", div_min)
    screener.set_sort(sort_col, ascending=sort_asc)
    result_df = screener.run(fund_df)

# ── STATS STRIP ─────────────────────────────────────────────────────────────────────────────
avg_pe  = result_df["pe"].dropna().mean()       if "pe"           in result_df.columns else None
avg_roe = result_df["roe_pct"].dropna().mean()  if "roe_pct"      in result_df.columns else None
avg_div = result_df["div_yield_pct"].dropna().mean() if "div_yield_pct" in result_df.columns else None

st.markdown(
    f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Stocks Found</div>'
    f'<div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;">{len(result_df)}</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg PE</div>'
    f'<div style="color:#f0b429;font-size:1.5rem;font-weight:800;">'
    f'{avg_pe:.1f}x</div>' if avg_pe else '<div style="color:#374151;font-size:1.5rem;font-weight:800;">—</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg ROE</div>'
    f'<div style="color:#00c896;font-size:1.5rem;font-weight:800;">'
    f'{avg_roe:.1f}%</div>' if avg_roe else '<div style="color:#374151;font-size:1.5rem;font-weight:800;">—</div>'
    f'</div>'

    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
    f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
    f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
    f'letter-spacing:0.09em;margin-bottom:6px;">Avg Div Yield</div>'
    f'<div style="color:#7c83fd;font-size:1.5rem;font-weight:800;">'
    f'{avg_div:.2f}%</div>' if avg_div else '<div style="color:#374151;font-size:1.5rem;font-weight:800;">—</div>'
    f'</div>'

    f'</div>',
    unsafe_allow_html=True,
)

# ── CLASSIFICATION CHIPS ─────────────────────────────────────────────────────────────────────────────────
if not result_df.empty and "classification" in result_df.columns:
    _CLS_COLORS = {
        "Fairly Valued": "#f0b429", "Undervalued": "#00c896",
        "Overvalued": "#ff4d6d", "Unknown": "#6b7a99",
    }
    class_counts = result_df["classification"].value_counts()
    chips = " ".join([
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'background:{_CLS_COLORS.get(k,"#6b7a99")}15;'
        f'color:{_CLS_COLORS.get(k,"#6b7a99")};'
        f'border:1px solid {_CLS_COLORS.get(k,"#6b7a99")}30;'
        f'border-radius:20px;padding:4px 12px;font-size:0.72rem;font-weight:700;margin:2px;">'
        f'{k} <span style="background:{_CLS_COLORS.get(k,"#6b7a99")}25;'
        f'border-radius:10px;padding:0 6px;font-size:0.68rem;">{v}</span></span>'
        for k, v in class_counts.items()
    ])
    st.markdown(f'<div style="margin-bottom:16px;line-height:2;">{chips}</div>', unsafe_allow_html=True)

if result_df.empty:
    st.markdown(
        '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);'
        'border-radius:14px;padding:32px;text-align:center;margin:8px 0;">'
        '<div style="font-size:1.5rem;margin-bottom:8px;">🔍</div>'
        '<div style="color:#475569;font-weight:600;">No stocks match your criteria</div>'
        '<div style="color:#374151;font-size:0.8rem;margin-top:4px;">Adjust filters or try a preset</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── RESULTS TABLE ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
    f'Results — {len(result_df)} stocks</div>',
    unsafe_allow_html=True,
)

display_cols = [c for c in [
    "ticker", "name", "sector", "price", "pe", "roe_pct",
    "profit_margin_pct", "debt_equity", "div_yield_pct",
    "rsi", "trend", "composite_score", "classification",
] if c in result_df.columns]
st.dataframe(result_df[display_cols], hide_index=True, use_container_width=True)

# ── STOCK DETAIL ────────────────────────────────────────────────────────────────────────────────
st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Stock Detail</div>',
    unsafe_allow_html=True,
)
selected = st.selectbox("Select a stock:", result_df["ticker"].tolist(), label_visibility="collapsed")
if selected:
    row = result_df[result_df["ticker"] == selected].iloc[0]

    price = row.get("price"); pe = row.get("pe"); roe = row.get("roe_pct")
    div   = row.get("div_yield_pct"); de = row.get("debt_equity"); marg = row.get("profit_margin_pct")

    detail_items = [
        ("Price",        f'₹{price:.2f}' if price else "—", "#f1f5f9"),
        ("PE Ratio",     f'{pe:.1f}x'    if pe    else "—", "#f0b429"),
        ("ROE",          f'{roe:.1f}%'   if roe   else "—", "#00c896"),
        ("Div Yield",    f'{div:.2f}%'   if div   else "—", "#7c83fd"),
        ("Debt/Equity",  f'{de:.2f}'     if de    else "—", "#f0b429"),
        ("Net Margin",   f'{marg:.1f}%'  if marg  else "—", "#00c896"),
    ]
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;">'
        + "".join([
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px 16px;">'
            f'<div style="color:#64748b;font-size:0.65rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:6px;">{lbl}</div>'
            f'<div style="color:{col};font-size:1.4rem;font-weight:800;">{val}</div>'
            f'</div>'
            for lbl, val, col in detail_items
        ])
        + f'</div>',
        unsafe_allow_html=True,
    )

    score_cols = ["valuation_score", "profitability_score", "growth_score", "health_score", "dividend_score"]
    available  = [c for c in score_cols if c in result_df.columns]
    if available:
        import plotly.graph_objects as go
        scores = [float(row.get(c, 0)) for c in available]
        labels = [c.replace("_score", "").title() for c in available]
        fig = go.Figure(go.Scatterpolar(
            r=scores + [scores[0]], theta=labels + [labels[0]],
            fill="toself", fillcolor="rgba(0,200,150,0.1)",
            line=dict(color="#00c896", width=2),
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0,1], gridcolor="rgba(255,255,255,0.08)", tickfont=dict(color="#475569")),
                angularaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
                bgcolor="rgba(0,0,0,0)",
            ),
            template="plotly_dark", height=320,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, key="fund_chart")
