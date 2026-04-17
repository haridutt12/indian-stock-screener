"""
Reusable Streamlit UI components.
"""
import streamlit as st
from ui.formatters import format_inr, format_pct, color_for_change, confidence_stars


def index_metric_card(name: str, value: float, change_pct: float, prev_close: float = None):
    """Display an index metric card with colored change."""
    arrow = "▲" if change_pct >= 0 else "▼"
    st.metric(
        label=name,
        value=f"{value:,.2f}",
        delta=f"{arrow} {abs(change_pct):.2f}%",
    )


def signal_card(signal_dict: dict):
    """Display a premium trade signal card."""
    direction  = signal_dict.get("direction", "LONG")
    is_long    = direction == "LONG"
    dir_color  = "#00c896" if is_long else "#ff4d6d"
    dir_bg     = "rgba(0,200,150,0.10)" if is_long else "rgba(255,77,109,0.10)"
    dir_border = "rgba(0,200,150,0.25)" if is_long else "rgba(255,77,109,0.25)"
    dir_emoji  = "↑" if is_long else "↓"

    confidence   = signal_dict.get("confidence", 1)
    stars_filled = "★" * confidence
    stars_empty  = "☆" * (5 - confidence)

    entry  = float(signal_dict.get("entry",    0))
    stop   = float(signal_dict.get("stop_loss",0))
    t1     = float(signal_dict.get("target_1", 0))
    t2     = float(signal_dict.get("target_2", 0))
    sl_pct = float(signal_dict.get("sl_pct",  0))
    t1_pct = float(signal_dict.get("t1_pct",  0))
    t2_pct = float(signal_dict.get("t2_pct",  0))
    rr     = float(signal_dict.get("risk_reward", 0))

    ticker_short = signal_dict.get("ticker", "").replace(".NS", "")
    name         = signal_dict.get("name", ticker_short)
    strategy     = signal_dict.get("strategy", "")
    sector       = signal_dict.get("sector", "")
    timeframe    = signal_dict.get("timeframe", "")

    rr_color      = "#00c896" if rr >= 2 else "#f0b429"
    rr_rgb        = "0,200,150" if rr >= 2 else "240,180,41"
    glow_color    = f"{dir_color}66"

    html = (
        f'<div style="background:linear-gradient(145deg,#1e2235 0%,#181c2e 100%);'
        f'border:1px solid rgba(255,255,255,0.07);border-left:4px solid {dir_color};'
        f'border-radius:14px;padding:20px 22px 16px;margin:10px 0;'
        f'box-shadow:0 6px 28px rgba(0,0,0,0.3),inset 0 1px 0 rgba(255,255,255,0.04);'
        f'position:relative;overflow:hidden;">'

        f'<div style="position:absolute;top:0;left:0;right:0;height:1px;'
        f'background:linear-gradient(90deg,{glow_color},transparent 60%);"></div>'

        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;">'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-size:1.3rem;font-weight:800;color:#e8eaf0;letter-spacing:-0.02em;">{ticker_short}</span>'
        f'<span style="background:{dir_bg};color:{dir_color};border:1px solid {dir_border};'
        f'border-radius:6px;padding:3px 10px;font-size:0.75rem;font-weight:700;letter-spacing:0.07em;">'
        f'{dir_emoji} {direction}</span>'
        f'<span style="background:rgba(255,255,255,0.05);color:#6b7a99;'
        f'border-radius:6px;padding:3px 10px;font-size:0.72rem;font-weight:600;">{timeframe}</span>'
        f'</div>'
        f'<div style="text-align:right;flex-shrink:0;">'
        f'<div style="font-size:1rem;letter-spacing:3px;line-height:1;">'
        f'<span style="color:#f0b429;">{stars_filled}</span>'
        f'<span style="color:#2a3050;">{stars_empty}</span>'
        f'</div>'
        f'<div style="color:#6b7a99;font-size:0.7rem;margin-top:4px;font-weight:600;letter-spacing:0.04em;">{strategy}</div>'
        f'</div>'
        f'</div>'

        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">'
        f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="color:#6b7a99;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.09em;margin-bottom:6px;">Entry</div>'
        f'<div style="color:#e8eaf0;font-weight:700;font-size:1.05rem;">₹{entry:,.2f}</div>'
        f'</div>'

        f'<div style="background:rgba(255,77,109,0.07);border:1px solid rgba(255,77,109,0.2);'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="color:#6b7a99;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.09em;margin-bottom:6px;">Stop Loss</div>'
        f'<div style="color:#ff4d6d;font-weight:700;font-size:1.05rem;">₹{stop:,.2f}</div>'
        f'<div style="color:rgba(255,77,109,0.7);font-size:0.72rem;margin-top:3px;">−{sl_pct:.1f}%</div>'
        f'</div>'

        f'<div style="background:rgba(0,200,150,0.07);border:1px solid rgba(0,200,150,0.2);'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="color:#6b7a99;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.09em;margin-bottom:6px;">Target 1</div>'
        f'<div style="color:#00c896;font-weight:700;font-size:1.05rem;">₹{t1:,.2f}</div>'
        f'<div style="color:rgba(0,200,150,0.7);font-size:0.72rem;margin-top:3px;">+{t1_pct:.1f}%</div>'
        f'</div>'

        f'<div style="background:rgba(74,222,128,0.07);border:1px solid rgba(74,222,128,0.2);'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="color:#6b7a99;font-size:0.62rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.09em;margin-bottom:6px;">Target 2</div>'
        f'<div style="color:#4ade80;font-weight:700;font-size:1.05rem;">₹{t2:,.2f}</div>'
        f'<div style="color:rgba(74,222,128,0.7);font-size:0.72rem;margin-top:3px;">+{t2_pct:.1f}%</div>'
        f'</div>'
        f'</div>'

        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding-top:12px;border-top:1px solid rgba(255,255,255,0.06);">'
        f'<span style="color:#6b7a99;font-size:0.78rem;">{name}'
        f'<span style="color:#3a4a62;margin:0 4px;">·</span>'
        f'<span style="color:#8a9ab8;">{sector}</span></span>'
        f'<span style="background:rgba({rr_rgb},0.12);color:{rr_color};'
        f'border:1px solid rgba({rr_rgb},0.25);'
        f'border-radius:6px;padding:3px 10px;font-size:0.8rem;font-weight:700;">'
        f'R:R 1:{rr:.1f}</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    with st.expander("View reasoning & chart"):
        st.write(signal_dict.get("reasoning", ""))
        patterns = signal_dict.get("patterns", [])
        if patterns:
            st.write("**Patterns detected:**", ", ".join(patterns))


def news_item(item: dict, sentiment_tag: str = None):
    """Render a single news item."""
    title   = item.get("title", "")
    source  = item.get("source", "")
    pub     = item.get("published_str", "")
    url     = item.get("url", "#")
    summary = item.get("summary", "")

    tag_colors = {"positive": "#00c896", "negative": "#ff4d6d", "neutral": "#6b7a99"}
    tag_html = ""
    if sentiment_tag:
        color = tag_colors.get(sentiment_tag.lower(), "#6b7a99")
        tag_html = (
            f'<span style="background:{color}22;color:{color};border:1px solid {color}44;'
            f'border-radius:5px;padding:2px 8px;font-size:0.7rem;font-weight:700;'
            f'letter-spacing:0.05em;margin-left:6px;">{sentiment_tag.upper()}</span>'
        )

    st.markdown(
        f"""
        <div style="
            border-bottom:1px solid rgba(255,255,255,0.06);
            padding:12px 0;
        ">
            <a href="{url}" target="_blank" style="color:#90caf9;text-decoration:none;font-weight:600;font-size:0.9rem;">
                {title}
            </a>{tag_html}
            <br><small style="color:#6b7a99;font-size:0.75rem;">{source} · {pub}</small>
            <br><small style="color:#8a9ab8;font-size:0.78rem;line-height:1.5;">{summary[:200]}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sector_sentiment_bar(sector: str, sentiment: str):
    """Display a sector with a colored sentiment indicator."""
    colors = {"bullish": "#00c896", "neutral": "#6b7a99", "bearish": "#ff4d6d"}
    color  = colors.get(sentiment.lower(), "#6b7a99")
    bg     = f"{color}18"
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:7px 10px;margin:3px 0;background:{bg};border-radius:7px;">'
        f'<span style="color:#c8d0e0;font-size:0.85rem;">{sector}</span>'
        f'<span style="color:{color};font-weight:700;font-size:0.78rem;'
        f'letter-spacing:0.06em;">{sentiment.upper()}</span>'
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
        display_df["composite_score"] = display_df["composite_score"].apply(
            lambda x: f"{x:.2f}" if x else "N/A"
        )

    st.dataframe(display_df, hide_index=True, use_container_width=True)
