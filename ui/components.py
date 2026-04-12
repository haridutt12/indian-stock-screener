"""
Reusable Streamlit UI components.
"""
import streamlit as st
from ui.formatters import format_inr, format_pct, color_for_change, confidence_stars


def index_metric_card(name: str, value: float, change_pct: float, prev_close: float = None):
    """Display an index metric card with colored change."""
    arrow = "▲" if change_pct >= 0 else "▼"
    color = "green" if change_pct >= 0 else "red"
    st.metric(
        label=name,
        value=f"{value:,.2f}",
        delta=f"{arrow} {abs(change_pct):.2f}%",
    )


def signal_card(signal_dict: dict):
    """Display a trade signal card."""
    direction = signal_dict.get("direction", "LONG")
    dir_color = "#26a69a" if direction == "LONG" else "#ef5350"
    dir_emoji = "📈" if direction == "LONG" else "📉"
    stars = confidence_stars(signal_dict.get("confidence", 1))

    with st.container():
        st.markdown(
            f"""
            <div style="border: 1px solid {dir_color}; border-radius: 8px; padding: 12px; margin: 8px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; color: {dir_color};">{dir_emoji} {signal_dict.get('ticker')} — {direction}</h4>
                    <span style="font-size: 1.1em;" title="Confidence">{stars}</span>
                </div>
                <p style="margin: 4px 0; color: #aaa; font-size: 0.85em;">{signal_dict.get('name', '')} · {signal_dict.get('strategy', '')} · {signal_dict.get('sector', '')}</p>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px;">
                    <div><small>Entry</small><br><b>₹{signal_dict.get('entry', 0):.2f}</b></div>
                    <div><small>Stop Loss</small><br><b style="color: #ef5350;">₹{signal_dict.get('stop_loss', 0):.2f} ({signal_dict.get('sl_pct', 0):.1f}%)</b></div>
                    <div><small>Target 1</small><br><b style="color: #26a69a;">₹{signal_dict.get('target_1', 0):.2f} ({signal_dict.get('t1_pct', 0):.1f}%)</b></div>
                    <div><small>Target 2</small><br><b style="color: #26a69a;">₹{signal_dict.get('target_2', 0):.2f} ({signal_dict.get('t2_pct', 0):.1f}%)</b></div>
                </div>
                <p style="margin: 8px 0 0 0; font-size: 0.85em; color: #ccc;">R:R = 1:{signal_dict.get('risk_reward', 0):.1f}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("View reasoning & chart"):
        st.write(signal_dict.get("reasoning", ""))
        patterns = signal_dict.get("patterns", [])
        if patterns:
            st.write("**Patterns detected:**", ", ".join(patterns))


def news_item(item: dict, sentiment_tag: str = None):
    """Render a single news item."""
    title = item.get("title", "")
    source = item.get("source", "")
    pub = item.get("published_str", "")
    url = item.get("url", "#")
    summary = item.get("summary", "")

    tag_colors = {"positive": "#26a69a", "negative": "#ef5350", "neutral": "#888"}
    tag_html = ""
    if sentiment_tag:
        color = tag_colors.get(sentiment_tag.lower(), "#888")
        tag_html = f'<span style="background:{color}; color:white; border-radius:4px; padding:2px 6px; font-size:0.75em;">{sentiment_tag}</span>'

    st.markdown(
        f"""
        <div style="border-bottom: 1px solid #333; padding: 8px 0;">
            <a href="{url}" target="_blank" style="color: #90caf9; text-decoration: none;">
                <b>{title}</b>
            </a> {tag_html}
            <br><small style="color: #888;">{source} · {pub}</small>
            <br><small style="color: #aaa;">{summary[:200]}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sector_sentiment_bar(sector: str, sentiment: str):
    """Display a sector with a colored sentiment indicator."""
    colors = {"bullish": "#26a69a", "neutral": "#888", "bearish": "#ef5350"}
    color = colors.get(sentiment.lower(), "#888")
    st.markdown(
        f'<div style="display:flex; justify-content:space-between; padding:4px 0;">'
        f'<span>{sector}</span>'
        f'<span style="color:{color}; font-weight:bold;">{sentiment.upper()}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def screener_result_table(df, highlight_col: str = "composite_score"):
    """Display screener results with color coding."""
    if df is None or df.empty:
        st.info("No stocks match your criteria.")
        return

    display_cols = [c for c in [
        "ticker", "name", "sector", "price", "pe", "roe_pct",
        "profit_margin_pct", "debt_equity", "div_yield_pct",
        "rsi", "trend", "composite_score", "classification"
    ] if c in df.columns]

    display_df = df[display_cols].copy()
    if "composite_score" in display_df.columns:
        display_df["composite_score"] = display_df["composite_score"].apply(lambda x: f"{x:.2f}" if x else "N/A")

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
    )
