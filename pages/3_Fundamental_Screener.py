"""
Page 3: Fundamental Screener
- Filter by PE, ROE, market cap, debt, dividend yield, sector
- Preset screeners (Value Picks, Quality Compounders, Dividend Stars)
- Sortable results table
"""
import streamlit as st
import pandas as pd
from data.fetcher import fetch_bulk_fundamentals
from analysis.fundamental import build_fundamental_df
from analysis.screener import StockScreener, PRESETS, build_screen_data
from ui.components import screener_result_table
from config.stock_universe import NIFTY_50, NIFTY_200, get_all_sectors, SECTOR_MAP

st.set_page_config(page_title="Fundamental Screener", layout="wide", page_icon="🔍")
from ui.styles import inject_global_css; inject_global_css()
st.title("🔍 Fundamental Screener")

# ── SIDEBAR FILTERS ────────────────────────────────────────────────────────────
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

    run_btn = st.button("🔍 Run Screener", type="primary", width="stretch")

# ── MAIN CONTENT ───────────────────────────────────────────────────────────────
if "fundamental_df" not in st.session_state:
    st.session_state.fundamental_df = None

if run_btn or st.session_state.fundamental_df is None:
    with st.spinner(f"Fetching fundamentals for {len(tickers)} stocks..."):
        fundamentals = fetch_bulk_fundamentals(tickers)
        fund_df = build_fundamental_df(fundamentals.to_dict("records"))
        st.session_state.fundamental_df = fund_df

fund_df = st.session_state.fundamental_df

if fund_df is None or fund_df.empty:
    st.error("No data available. Try running the screener.")
    st.stop()

# Filter by sector
if selected_sector != "All":
    fund_df = fund_df[fund_df["sector"] == selected_sector]

# Apply preset or custom filters
if preset_name != "Custom" and preset_name in PRESETS:
    result_df = PRESETS[preset_name](fund_df)
    st.info(f"Using preset: **{preset_name}**")
else:
    screener = StockScreener()
    if pe_min > 0:
        screener.add_filter("pe", "gte", pe_min)
    if pe_max > 0:
        screener.add_filter("pe", "lte", pe_max)
    if roe_min > 0:
        screener.add_filter("roe_pct", "gte", roe_min)
    if profit_margin_min > 0:
        screener.add_filter("profit_margin_pct", "gte", profit_margin_min)
    if de_max < 200:
        screener.add_filter("debt_equity", "lte", de_max)
    if div_min > 0:
        screener.add_filter("div_yield_pct", "gte", div_min)
    screener.set_sort(sort_col, ascending=sort_asc)
    result_df = screener.run(fund_df)

st.subheader(f"Results: {len(result_df)} stocks")

# Summary metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Stocks Found", len(result_df))
if not result_df.empty:
    m2.metric("Avg PE", f"{result_df['pe'].dropna().mean():.1f}" if "pe" in result_df else "N/A")
    m3.metric("Avg ROE %", f"{result_df['roe_pct'].dropna().mean():.1f}" if "roe_pct" in result_df else "N/A")
    m4.metric("Avg Div Yield %", f"{result_df['div_yield_pct'].dropna().mean():.2f}" if "div_yield_pct" in result_df else "N/A")

st.divider()

# Classification breakdown
if not result_df.empty and "classification" in result_df.columns:
    class_counts = result_df["classification"].value_counts()
    cols = st.columns(len(class_counts))
    for col, (cls, count) in zip(cols, class_counts.items()):
        col.metric(cls, count)
    st.divider()

screener_result_table(result_df)

# Detail view on selection
if not result_df.empty:
    st.subheader("Stock Detail")
    selected = st.selectbox("Select a stock for details:", result_df["ticker"].tolist())
    if selected:
        row = result_df[result_df["ticker"] == selected].iloc[0]
        d1, d2, d3 = st.columns(3)
        d1.metric("Price", f"₹{row.get('price', 0):.2f}" if row.get("price") else "N/A")
        d2.metric("PE Ratio", f"{row.get('pe', 0):.1f}" if row.get("pe") else "N/A")
        d3.metric("ROE %", f"{row.get('roe_pct', 0):.1f}%" if row.get("roe_pct") else "N/A")

        score_cols = ["valuation_score", "profitability_score", "growth_score", "health_score", "dividend_score"]
        available = [c for c in score_cols if c in result_df.columns]
        if available:
            import plotly.graph_objects as go
            scores = [float(row.get(c, 0)) for c in available]
            labels = [c.replace("_score", "").title() for c in available]
            fig = go.Figure(go.Scatterpolar(
                r=scores + [scores[0]], theta=labels + [labels[0]],
                fill="toself", line_color="#26a69a",
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                template="plotly_dark", height=300,
                margin=dict(l=30, r=30, t=30, b=30),
                title="Fundamental Score Radar",
            )
            st.plotly_chart(fig, width="stretch")
