"""
Reusable Streamlit UI components.
"""
import streamlit as st
from ui.formatters import format_inr, format_pct, color_for_change, confidence_stars

# Per-strategy accent colours — used for the strategy badge
_STRATEGY_COLORS = {
    "Trend Pullback":         "#7c83fd",
    "Volume Breakout":        "#f0b429",
    "Oversold Reversal":      "#a855f7",
    "Bullish Setup":          "#00c896",
    "Golden Cross":           "#fbbf24",
    "Supertrend Reversal":    "#06b6d4",
    "Opening Range Breakout": "#10b981",
    "VWAP Bounce":            "#f472b6",
    "EMA Crossover":          "#60a5fa",
    "Supertrend Signal":      "#8b5cf6",
}


def index_metric_card(name: str, value: float, change_pct: float, prev_close: float = None):
    arrow = "▲" if change_pct >= 0 else "▼"
    st.metric(
        label=name,
        value=f"{value:,.2f}",
        delta=f"{arrow} {abs(change_pct):.2f}%",
    )


def signal_card(signal_dict: dict):
    """Compact visual trade signal card — price ladder + strategy badge."""
    direction  = signal_dict.get("direction", "LONG")
    is_long    = direction == "LONG"
    dir_color  = "#00c896" if is_long else "#ff4d6d"
    dir_bg     = "rgba(0,200,150,0.12)" if is_long else "rgba(255,77,109,0.12)"
    dir_border = "rgba(0,200,150,0.3)"  if is_long else "rgba(255,77,109,0.3)"
    dir_emoji  = "↑" if is_long else "↓"

    confidence = min(int(signal_dict.get("confidence", 1) or 1), 5)
    entry  = float(signal_dict.get("entry",     0) or 0)
    stop   = float(signal_dict.get("stop_loss", 0) or 0)
    t1     = float(signal_dict.get("target_1",  0) or 0)
    t2     = float(signal_dict.get("target_2",  0) or 0)
    sl_pct = float(signal_dict.get("sl_pct",   0) or 0)
    t1_pct = float(signal_dict.get("t1_pct",   0) or 0)
    t2_pct = float(signal_dict.get("t2_pct",   0) or 0)
    rr     = float(signal_dict.get("risk_reward", 0) or 0)

    ticker_short = signal_dict.get("ticker", "").replace(".NS", "")
    name         = signal_dict.get("name", ticker_short)
    strategy     = signal_dict.get("strategy", "")
    sector       = signal_dict.get("sector", "")
    timeframe    = signal_dict.get("timeframe", "")

    strat_color = _STRATEGY_COLORS.get(strategy, "#6b7a99")
    rr_color    = "#00c896" if rr >= 2 else "#f0b429"
    rr_rgb      = "0,200,150" if rr >= 2 else "240,180,41"

    # Confidence dots
    dots = "".join([
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        f'background:{"#f0b429" if i < confidence else "rgba(255,255,255,0.1)"};'
        f'margin:0 2px;"></span>'
        for i in range(5)
    ])

    # Price ladder bar — proportional positions SL → Entry → T1 → T2
    bar_html = ""
    if t2 > stop and entry > stop and t2 > entry:
        total = t2 - stop
        ep   = max(8,  min(85, (entry - stop) / total * 100))
        tp1  = max(ep + 8, min(93, (t1 - stop) / total * 100))

        bar_html = (
            f'<div style="margin:16px 0 6px;position:relative;">'
            # Coloured track
            f'<div style="height:5px;border-radius:3px;overflow:hidden;">'
            f'<div style="height:100%;background:linear-gradient(90deg,'
            f'rgba(255,77,109,0.55) 0%,rgba(255,77,109,0.55) {ep:.1f}%,'
            f'rgba(240,180,41,0.50) {ep:.1f}%,rgba(240,180,41,0.50) {tp1:.1f}%,'
            f'rgba(0,200,150,0.55) {tp1:.1f}%,rgba(0,200,150,0.55) 100%);"></div>'
            f'</div>'
            # Entry marker tick
            f'<div style="position:absolute;top:-3px;left:{ep:.1f}%;width:3px;height:11px;'
            f'background:#f1f5f9;border-radius:2px;transform:translateX(-50%);'
            f'box-shadow:0 0 4px rgba(255,255,255,0.4);"></div>'
            # Label row
            f'<div style="position:relative;height:34px;margin-top:6px;">'
            f'<div style="position:absolute;left:0;text-align:left;">'
            f'<div style="font-size:0.6rem;color:#ff4d6d;font-weight:700;letter-spacing:0.05em;">SL</div>'
            f'<div style="font-size:0.72rem;color:#ff4d6d;font-weight:600;">₹{stop:,.0f}</div>'
            f'<div style="font-size:0.62rem;color:rgba(255,77,109,0.65);">−{sl_pct:.1f}%</div>'
            f'</div>'
            f'<div style="position:absolute;left:{ep:.1f}%;transform:translateX(-50%);text-align:center;">'
            f'<div style="font-size:0.6rem;color:#94a3b8;font-weight:700;letter-spacing:0.05em;">ENTRY</div>'
            f'<div style="font-size:0.72rem;color:#e2e8f0;font-weight:700;">₹{entry:,.0f}</div>'
            f'</div>'
            f'<div style="position:absolute;left:{tp1:.1f}%;transform:translateX(-50%);text-align:center;">'
            f'<div style="font-size:0.6rem;color:#00c896;font-weight:700;letter-spacing:0.05em;">T1</div>'
            f'<div style="font-size:0.72rem;color:#00c896;font-weight:600;">₹{t1:,.0f}</div>'
            f'<div style="font-size:0.62rem;color:rgba(0,200,150,0.65);">+{t1_pct:.1f}%</div>'
            f'</div>'
            f'<div style="position:absolute;right:0;text-align:right;">'
            f'<div style="font-size:0.6rem;color:#4ade80;font-weight:700;letter-spacing:0.05em;">T2</div>'
            f'<div style="font-size:0.72rem;color:#4ade80;font-weight:600;">₹{t2:,.0f}</div>'
            f'<div style="font-size:0.62rem;color:rgba(74,222,128,0.65);">+{t2_pct:.1f}%</div>'
            f'</div>'
            f'</div>'
            f'</div>'
        )

    html = (
        f'<div style="background:linear-gradient(160deg,#1a1f35 0%,#141828 100%);'
        f'border:1px solid rgba(255,255,255,0.06);border-left:4px solid {dir_color};'
        f'border-radius:16px;padding:18px 20px 14px;margin:8px 0;'
        f'box-shadow:0 2px 16px rgba(0,0,0,0.2);">'

        # ── Header ─────────────────────────────────────────────────
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div style="flex:1;min-width:0;">'
        # Ticker + badges row
        f'<div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:3px;">'
        f'<span style="font-size:1.2rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">{ticker_short}</span>'
        f'<span style="background:{dir_bg};color:{dir_color};border:1px solid {dir_border};'
        f'border-radius:5px;padding:2px 8px;font-size:0.7rem;font-weight:700;">{dir_emoji} {direction}</span>'
        f'<span style="background:rgba(255,255,255,0.05);color:#64748b;'
        f'border-radius:5px;padding:2px 8px;font-size:0.68rem;font-weight:600;">{timeframe}</span>'
        f'</div>'
        # Company + sector
        f'<div style="font-size:0.75rem;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{name}<span style="color:#2d3748;margin:0 5px;">·</span>{sector}'
        f'</div>'
        f'</div>'
        # Strategy badge + confidence dots
        f'<div style="text-align:right;flex-shrink:0;margin-left:12px;">'
        f'<div style="background:{strat_color}15;color:{strat_color};border:1px solid {strat_color}30;'
        f'border-radius:5px;padding:3px 9px;font-size:0.67rem;font-weight:700;letter-spacing:0.04em;'
        f'margin-bottom:6px;white-space:nowrap;">{strategy}</div>'
        f'<div style="display:flex;gap:2px;justify-content:flex-end;">{dots}</div>'
        f'</div>'
        f'</div>'

        # ── Price Ladder Bar ────────────────────────────────────────
        + bar_html +

        # ── Footer ─────────────────────────────────────────────────
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding-top:10px;border-top:1px solid rgba(255,255,255,0.05);margin-top:4px;">'
        f'<span style="background:rgba({rr_rgb},0.1);color:{rr_color};'
        f'border:1px solid rgba({rr_rgb},0.22);border-radius:5px;'
        f'padding:3px 10px;font-size:0.78rem;font-weight:700;">R:R  1:{rr:.1f}</span>'
        f'<span style="color:#374151;font-size:0.7rem;">'
        f'Risk −{sl_pct:.1f}%  ·  T1 +{t1_pct:.1f}%  ·  T2 +{t2_pct:.1f}%'
        f'</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    reasoning = signal_dict.get("reasoning", "")
    patterns  = signal_dict.get("patterns", [])
    with st.expander("Analysis & Chart"):
        if patterns:
            chips = " ".join([
                f'<span style="display:inline-block;background:{strat_color}12;color:{strat_color};'
                f'border:1px solid {strat_color}28;border-radius:4px;'
                f'padding:2px 8px;font-size:0.7rem;font-weight:600;margin:2px;">{p}</span>'
                for p in patterns
            ])
            st.markdown(f'<div style="margin-bottom:10px;">{chips}</div>', unsafe_allow_html=True)
        if reasoning:
            parts = [p.strip() for p in reasoning.replace("Strategy:", "\nStrategy:").split(".") if len(p.strip()) > 6]
            for part in parts:
                st.caption(f"• {part.strip()}")


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
            f'<span style="background:{color}18;color:{color};border:1px solid {color}30;'
            f'border-radius:4px;padding:1px 7px;font-size:0.67rem;font-weight:700;'
            f'letter-spacing:0.05em;margin-left:6px;">{sentiment_tag.upper()}</span>'
        )

    st.markdown(
        f'<div style="border-bottom:1px solid rgba(255,255,255,0.05);padding:11px 0;">'
        f'<a href="{url}" target="_blank" '
        f'style="color:#93c5fd;text-decoration:none;font-weight:600;font-size:0.875rem;'
        f'line-height:1.4;">{title}</a>{tag_html}'
        f'<div style="color:#4b5563;font-size:0.72rem;margin-top:3px;">{source} · {pub}</div>'
        f'<div style="color:#6b7a8a;font-size:0.77rem;line-height:1.5;margin-top:2px;">{summary[:180]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def sector_sentiment_bar(sector: str, sentiment: str):
    """Display a sector row with a coloured sentiment pill."""
    colors = {"bullish": "#00c896", "neutral": "#6b7a99", "bearish": "#ff4d6d"}
    color  = colors.get(sentiment.lower(), "#6b7a99")
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:7px 12px;margin:3px 0;background:{color}0f;'
        f'border-radius:8px;border-left:3px solid {color};">'
        f'<span style="color:#cbd5e1;font-size:0.85rem;">{sector}</span>'
        f'<span style="background:{color}20;color:{color};border-radius:4px;'
        f'padding:2px 8px;font-size:0.7rem;font-weight:700;letter-spacing:0.06em;">'
        f'{sentiment.upper()}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def screener_result_table(df, highlight_col: str = "composite_score"):
    """Display screener results with colour coding."""
    if df is None or df.empty:
        st.info("No stocks match your criteria.")
        return

    display_cols = [c for c in [
        "ticker", "name", "sector", "price", "pe", "roe_pct",
        "profit_margin_pct", "debt_equity", "div_yield_pct",
        "rsi", "trend", "composite_score", "classification",
    ] if c in df.columns]

    display_df = df[display_cols].copy()
    if "composite_score" in display_df.columns:
        display_df["composite_score"] = display_df["composite_score"].apply(
            lambda x: f"{x:.2f}" if x else "N/A"
        )

    st.dataframe(display_df, hide_index=True, use_container_width=True)
