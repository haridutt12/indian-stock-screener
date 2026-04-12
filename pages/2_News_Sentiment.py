"""
Page 2: News & AI Sentiment Analysis
- Claude-powered market summary
- Sector sentiment breakdown
- Live news feed with sentiment tags
- Stock mentions from news
"""
import streamlit as st
from data.news_fetcher import fetch_market_news, format_news_for_claude
from analysis.sentiment import analyze_market_sentiment, has_api_key
from ui.components import news_item, sector_sentiment_bar

st.set_page_config(page_title="News & Sentiment", layout="wide", page_icon="📰")
st.title("📰 News & Market Sentiment")

if not has_api_key():
    st.warning(
        "⚠️ **ANTHROPIC_API_KEY not set.** AI analysis is unavailable. "
        "Add your key to the `.env` file to enable sentiment analysis."
    )

# ── FETCH NEWS ─────────────────────────────────────────────────────────────────
with st.spinner("Fetching latest market news..."):
    news_items = fetch_market_news()

if not news_items:
    st.error("Could not fetch news. Check your internet connection.")
    st.stop()

st.caption(f"Fetched {len(news_items)} news items from multiple sources.")

# ── AI SENTIMENT ANALYSIS ──────────────────────────────────────────────────────
if has_api_key():
    with st.spinner("Analyzing sentiment with Claude..."):
        news_text = format_news_for_claude(news_items, max_items=30)
        sentiment = analyze_market_sentiment(news_text)
else:
    from analysis.sentiment import _fallback_sentiment
    sentiment = _fallback_sentiment()

# Overall sentiment header
overall = sentiment.get("overall_sentiment", 5)
label = sentiment.get("sentiment_label", "Neutral")
sentiment_colors = {
    "Strongly Bullish": "#00897B", "Bullish": "#26a69a",
    "Neutral": "#888", "Bearish": "#ef5350", "Strongly Bearish": "#b71c1c",
}
color = sentiment_colors.get(label, "#888")

st.markdown(
    f'<div style="background:{color}22; border: 1px solid {color}; border-radius: 8px; padding: 16px; margin-bottom: 16px;">'
    f'<h3 style="color:{color}; margin:0;">Market Sentiment: {label} ({overall}/10)</h3>'
    f'</div>',
    unsafe_allow_html=True,
)

# Sentiment gauge
col1, col2 = st.columns([3, 1])
with col1:
    # Market Summary
    st.subheader("Market Summary")
    summary_text = sentiment.get("overnight_summary", "")
    if summary_text:
        st.markdown(summary_text)

    # Trade Implications
    implications = sentiment.get("trade_implications", "")
    if implications:
        st.subheader("Trade Implications")
        st.info(implications)

    # Key Themes
    themes = sentiment.get("key_themes", [])
    if themes:
        st.subheader("Key Themes")
        cols = st.columns(min(len(themes), 3))
        for i, theme in enumerate(themes):
            cols[i % 3].markdown(f"🔹 {theme}")

    # Catalysts & Risks
    row = st.columns(2)
    with row[0]:
        catalysts = sentiment.get("key_catalysts", [])
        if catalysts:
            st.subheader("Key Catalysts")
            for c in catalysts:
                st.markdown(f"✅ {c}")
    with row[1]:
        risks = sentiment.get("key_risks", [])
        if risks:
            st.subheader("Key Risks")
            for r in risks:
                st.markdown(f"⚠️ {r}")

with col2:
    # Sector Outlook
    st.subheader("Sector Outlook")
    sector_outlook = sentiment.get("sector_outlook", {})
    for sector, sent in sector_outlook.items():
        sector_sentiment_bar(sector, sent)

    # Stock Mentions
    mentions = sentiment.get("stock_mentions", [])
    if mentions:
        st.subheader("Stock Mentions")
        for mention in mentions[:8]:
            sym = mention.get("symbol", "")
            sent = mention.get("sentiment", "neutral")
            reason = mention.get("reason", "")
            tag_color = {"positive": "#26a69a", "negative": "#ef5350", "neutral": "#888"}.get(sent.lower(), "#888")
            st.markdown(
                f'<div style="padding:4px 0; border-bottom:1px solid #333;">'
                f'<b>{sym}</b> <span style="color:{tag_color}; font-size:0.8em;">● {sent}</span>'
                f'<br><small style="color:#aaa;">{reason[:100]}</small></div>',
                unsafe_allow_html=True,
            )

st.divider()

# ── NEWS FEED ──────────────────────────────────────────────────────────────────
st.subheader("News Feed")

# Build sentiment map for news items from stock_mentions
mention_map = {}
for m in sentiment.get("stock_mentions", []):
    sym = m.get("symbol", "").upper()
    if sym:
        mention_map[sym] = m.get("sentiment", "neutral")

# Source filter
all_sources = sorted(set(n["source"] for n in news_items))
selected_sources = st.multiselect("Filter by source:", all_sources, default=all_sources)
filtered_news = [n for n in news_items if n["source"] in selected_sources]

for item in filtered_news[:40]:
    # Try to tag news with sentiment from mention_map
    title_upper = item.get("title", "").upper()
    tag = None
    for sym, sent in mention_map.items():
        if sym in title_upper:
            tag = sent
            break
    news_item(item, sentiment_tag=tag)
