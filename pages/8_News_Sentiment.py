"""
Page 2: News & AI Sentiment Analysis
"""
import streamlit as st
from data.news_fetcher import fetch_market_news, format_news_for_claude
from analysis.sentiment import analyze_market_sentiment, has_api_key, get_engine_name

st.set_page_config(page_title="News & Sentiment · NiftyEdge", layout="wide", page_icon="📰")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar; inject_global_css()
auth_guard()
with st.sidebar:
    user_sidebar()

# ── PAGE HEADER ─────────────────────────────────────────────────────────────────────────────
page_header("📰 News & Market Sentiment", subtitle="AI · Market Intelligence · Daily")


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_news_and_sentiment():
    """Cache news + LLM sentiment call for 30 min — prevents a Claude API call on every page visit."""
    items = fetch_market_news()
    if not items:
        return [], {}
    try:
        text = format_news_for_claude(items, max_items=30)
        sent = analyze_market_sentiment(text, news_items=items)
    except Exception:
        sent = {}
    return items, sent


# ── FETCH + ANALYSE (cached) ──────────────────────────────────────────────────
_loading = st.empty()
_loading.markdown(
    '<div style="background:rgba(124,131,253,0.06);border:1px solid rgba(124,131,253,0.2);'
    'border-radius:12px;padding:12px 18px;display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
    '<div style="width:8px;height:8px;border-radius:50%;background:#7c83fd;'
    'animation:pulse 1.2s ease-in-out infinite;flex-shrink:0;"></div>'
    '<div style="color:#7c83fd;font-weight:700;font-size:0.85rem;">'
    f'Fetching news &amp; analysing with {get_engine_name()}…</div>'
    '</div>',
    unsafe_allow_html=True,
)
news_items, sentiment = _fetch_news_and_sentiment()
_loading.empty()

if not news_items:
    st.error("Could not fetch news. Check your internet connection.")
    st.stop()

# Persist today's score for the 30-day trend chart (non-blocking)
try:
    from signals.signal_logger import get_signal_logger as _get_sl
    _get_sl().log_daily_sentiment(
        score=float(sentiment.get("overall_sentiment", 5)),
        label=sentiment.get("sentiment_label", "Neutral"),
        key_themes=sentiment.get("key_themes", []),
    )
except Exception:
    pass

# ── PARSE SENTIMENT DATA ─────────────────────────────────────────────────────────────────────
overall   = sentiment.get("overall_sentiment", 5)
label     = sentiment.get("sentiment_label", "Neutral")
summary   = sentiment.get("overnight_summary", "")
impl      = sentiment.get("trade_implications", "")
themes    = sentiment.get("key_themes", [])
catalysts = sentiment.get("key_catalysts", [])
risks     = sentiment.get("key_risks", [])
sectors   = sentiment.get("sector_outlook", {})
mentions  = sentiment.get("stock_mentions", [])

_SENT_META = {
    "Strongly Bullish": ("#00c896", "0,200,150",  "↑↑"),
    "Bullish":          ("#00c896", "0,200,150",  "↑"),
    "Neutral":          ("#f0b429", "240,180,41", "→"),
    "Bearish":          ("#ff4d6d", "255,77,109", "↓"),
    "Strongly Bearish": ("#ff4d6d", "255,77,109", "↓↓"),
}
s_color, s_rgb, s_arrow = _SENT_META.get(label, ("#f0b429", "240,180,41", "→"))
score_pct = int(overall * 10)  # 0-100

# ── SENTIMENT HERO CARD ────────────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="background:linear-gradient(145deg,#111827,#0d1117);'
    f'border:1px solid rgba({s_rgb},0.2);border-radius:20px;'
    f'padding:28px 32px;margin-bottom:20px;position:relative;overflow:hidden;">'

    f'<div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;'
    f'background:radial-gradient(circle,rgba({s_rgb},0.08),transparent 65%);pointer-events:none;"></div>'

    f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:20px;">'

    f'<div style="display:flex;align-items:center;gap:24px;">'
    f'<div style="text-align:center;">'
    f'<div style="font-size:3.5rem;font-weight:900;color:{s_color};line-height:1;letter-spacing:-0.04em;">{overall}<span style="font-size:1.4rem;color:rgba({s_rgb},0.5);">/10</span></div>'
    f'<div style="font-size:0.65rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.1em;margin-top:4px;">Sentiment Score</div>'
    f'</div>'
    f'<div>'
    f'<div style="display:inline-flex;align-items:center;gap:8px;'
    f'background:rgba({s_rgb},0.12);border:1px solid rgba({s_rgb},0.3);'
    f'border-radius:10px;padding:8px 16px;margin-bottom:10px;">'
    f'<span style="font-size:1.1rem;font-weight:800;color:{s_color};">{s_arrow} {label}</span>'
    f'</div>'
    f'<div style="width:200px;height:6px;background:rgba(255,255,255,0.07);border-radius:3px;overflow:hidden;">'
    f'<div style="width:{score_pct}%;height:100%;'
    f'background:linear-gradient(90deg,rgba({s_rgb},0.4),{s_color});border-radius:3px;"></div>'
    f'</div>'
    f'<div style="color:#475569;font-size:0.7rem;margin-top:4px;">{engine} · {len(news_items)} articles analysed</div>'
    f'</div>'
    f'</div>'

    f'<div style="display:flex;gap:12px;flex-wrap:wrap;">'
    f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);'
    f'border-radius:12px;padding:12px 16px;min-width:70px;text-align:center;">'
    f'<div style="font-size:1.4rem;font-weight:800;color:#f1f5f9;">{len(news_items)}</div>'
    f'<div style="font-size:0.6rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;margin-top:2px;">Articles</div>'
    f'</div>'
    f'<div style="background:rgba(0,200,150,0.06);border:1px solid rgba(0,200,150,0.15);'
    f'border-radius:12px;padding:12px 16px;min-width:70px;text-align:center;">'
    f'<div style="font-size:1.4rem;font-weight:800;color:#00c896;">{len(catalysts)}</div>'
    f'<div style="font-size:0.6rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;margin-top:2px;">Catalysts</div>'
    f'</div>'
    f'<div style="background:rgba(255,77,109,0.06);border:1px solid rgba(255,77,109,0.15);'
    f'border-radius:12px;padding:12px 16px;min-width:70px;text-align:center;">'
    f'<div style="font-size:1.4rem;font-weight:800;color:#ff4d6d;">{len(risks)}</div>'
    f'<div style="font-size:0.6rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;margin-top:2px;">Risks</div>'
    f'</div>'
    f'</div>'

    f'</div></div>',
    unsafe_allow_html=True,
)

# ── 30-DAY SENTIMENT TREND SPARKLINE ──────────────────────────────────────────────────────────────
try:
    import plotly.graph_objects as _go
    from signals.signal_logger import get_signal_logger as _get_sl

    _hist = _get_sl().get_sentiment_history(days=30)

    if len(_hist) >= 2:
        _dates  = [r["date"]  for r in _hist]
        _scores = [r["score"] for r in _hist]
        _labels = [r["label"] for r in _hist]

        _bar_colors = [
            "#00c896" if s >= 6 else ("#f0b429" if s >= 4 else "#ff4d6d")
            for s in _scores
        ]

        _trend_fig = _go.Figure()

        # Shaded bands for bearish / neutral / bullish zones
        for _y0, _y1, _fc in [(1, 3.5, "rgba(255,77,109,0.05)"),
                               (3.5, 6.5, "rgba(240,180,41,0.04)"),
                               (6.5, 10, "rgba(0,200,150,0.05)")]:
            _trend_fig.add_hrect(
                y0=_y0, y1=_y1,
                fillcolor=_fc, layer="below", line_width=0,
            )

        # Reference lines
        for _yref, _ycol, _ytxt in [(3.5, "#ff4d6d", "Bearish"), (6.5, "#00c896", "Bullish")]:
            _trend_fig.add_hline(
                y=_yref,
                line=dict(color=_ycol, width=1, dash="dot"),
                annotation_text=_ytxt,
                annotation_position="right",
                annotation_font=dict(color=_ycol, size=10),
            )

        # Score bars
        _trend_fig.add_trace(_go.Bar(
            x=_dates,
            y=_scores,
            marker_color=_bar_colors,
            marker_line_width=0,
            customdata=[[_l] for _l in _labels],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Score: <b>%{y}/10</b><br>"
                "%{customdata[0]}<extra></extra>"
            ),
        ))

        # Trend line overlay
        _trend_fig.add_trace(_go.Scatter(
            x=_dates,
            y=_scores,
            mode="lines",
            line=dict(color="rgba(255,255,255,0.25)", width=1.5, dash="solid"),
            showlegend=False,
            hoverinfo="skip",
        ))

        _trend_fig.update_layout(
            height=160,
            margin=dict(t=24, b=20, l=40, r=70),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(
                range=[1, 10],
                tickvals=[1, 3.5, 6.5, 10],
                ticktext=["1", "Bearish", "Bullish", "10"],
                gridcolor="rgba(255,255,255,0.04)",
                color="#475569",
                tickfont=dict(size=10),
            ),
            xaxis=dict(
                showgrid=False,
                color="#475569",
                tickfont=dict(size=10),
            ),
            showlegend=False,
            bargap=0.25,
            title=dict(
                text="30-Day Sentiment Trend",
                font=dict(size=11, color="#64748b"),
                x=0,
                xanchor="left",
            ),
        )

        st.plotly_chart(_trend_fig, use_container_width=True, config={"displayModeBar": False})
    elif _hist:
        # Only one data point — show a nudge
        st.markdown(
            f'<div style="font-size:0.72rem;color:#475569;margin-bottom:12px;">'
            f'Sentiment history will grow as the app runs daily. '
            f'{len(_hist)} day recorded so far.</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

# ── SUMMARY + SECTOR OUTLOOK ───────────────────────────────────────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    if summary:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Market Summary</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
            f'border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:20px 22px;'
            f'color:#94a3b8;font-size:0.88rem;line-height:1.75;margin-bottom:16px;">'
            f'{summary}</div>',
            unsafe_allow_html=True,
        )

    if impl:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Trade Implication</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.18);'
            f'border-left:4px solid #f0b429;border-radius:12px;padding:16px 18px;'
            f'color:#94a3b8;font-size:0.85rem;line-height:1.7;margin-bottom:16px;">'
            f'💡 {impl}</div>',
            unsafe_allow_html=True,
        )

    if themes:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Key Themes</div>',
            unsafe_allow_html=True,
        )
        chips = " ".join([
            f'<span style="display:inline-block;background:rgba(124,131,253,0.1);'
            f'color:#7c83fd;border:1px solid rgba(124,131,253,0.25);'
            f'border-radius:20px;padding:5px 14px;font-size:0.75rem;font-weight:600;margin:3px 2px;">'
            f'# {t}</span>'
            for t in themes
        ])
        st.markdown(f'<div style="line-height:2.2;margin-bottom:16px;">{chips}</div>', unsafe_allow_html=True)

    if catalysts or risks:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                '<div style="font-size:0.68rem;font-weight:700;color:#00c896;'
                'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">↑ Catalysts</div>',
                unsafe_allow_html=True,
            )
            for item in catalysts:
                st.markdown(
                    f'<div style="background:rgba(0,200,150,0.06);border:1px solid rgba(0,200,150,0.15);'
                    f'border-radius:10px;padding:10px 14px;margin-bottom:6px;'
                    f'color:#94a3b8;font-size:0.8rem;line-height:1.5;">'
                    f'<span style="color:#00c896;font-weight:700;margin-right:6px;">✓</span>{item}</div>',
                    unsafe_allow_html=True,
                )
        with c2:
            st.markdown(
                '<div style="font-size:0.68rem;font-weight:700;color:#ff4d6d;'
                'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">↓ Risks</div>',
                unsafe_allow_html=True,
            )
            for item in risks:
                st.markdown(
                    f'<div style="background:rgba(255,77,109,0.06);border:1px solid rgba(255,77,109,0.15);'
                    f'border-radius:10px;padding:10px 14px;margin-bottom:6px;'
                    f'color:#94a3b8;font-size:0.8rem;line-height:1.5;">'
                    f'<span style="color:#ff4d6d;font-weight:700;margin-right:6px;">⚠</span>{item}</div>',
                    unsafe_allow_html=True,
                )

with right:
    if sectors:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Sector Outlook</div>',
            unsafe_allow_html=True,
        )
        _SC = {"bullish": ("#00c896", "0,200,150"), "bearish": ("#ff4d6d", "255,77,109"), "neutral": ("#f0b429", "240,180,41")}
        for sector, sent in sectors.items():
            c, rgb = _SC.get(sent.lower(), ("#6b7a99", "107,122,153"))
            arrow = "↑" if sent.lower() == "bullish" else ("↓" if sent.lower() == "bearish" else "→")
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'background:rgba({rgb},0.06);border:1px solid rgba({rgb},0.15);'
                f'border-radius:10px;padding:10px 14px;margin-bottom:6px;">'
                f'<span style="color:#94a3b8;font-size:0.82rem;font-weight:500;">{sector}</span>'
                f'<span style="color:{c};font-size:0.72rem;font-weight:700;'
                f'background:rgba({rgb},0.12);border-radius:5px;padding:2px 8px;">'
                f'{arrow} {sent.capitalize()}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if mentions:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 10px;">Stock Mentions</div>',
            unsafe_allow_html=True,
        )
        _MC = {"positive": ("#00c896", "0,200,150"), "negative": ("#ff4d6d", "255,77,109"), "neutral": ("#6b7a99", "107,122,153")}
        for m in mentions[:8]:
            sym  = m.get("symbol", "")
            sent = m.get("sentiment", "neutral").lower()
            reason = m.get("reason", "")
            c, rgb = _MC.get(sent, ("#6b7a99", "107,122,153"))
            st.markdown(
                f'<div style="background:rgba({rgb},0.05);border:1px solid rgba({rgb},0.15);'
                f'border-radius:10px;padding:10px 14px;margin-bottom:6px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
                f'<span style="font-weight:800;color:#e2e8f0;font-size:0.9rem;">{sym}</span>'
                f'<span style="color:{c};font-size:0.65rem;font-weight:700;'
                f'background:rgba({rgb},0.12);border-radius:4px;padding:2px 7px;">'
                f'{sent.upper()}</span>'
                f'</div>'
                f'<div style="color:#475569;font-size:0.75rem;line-height:1.5;">{reason[:120]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── NEWS FEED ────────────────────────────────────────────────────────────────────────────────
st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">Live News Feed</div>',
    unsafe_allow_html=True,
)

all_sources      = sorted(set(n["source"] for n in news_items))
selected_sources = st.multiselect("Filter by source", all_sources, default=all_sources, label_visibility="collapsed")
filtered_news    = [n for n in news_items if n["source"] in selected_sources]

mention_map = {m.get("symbol", "").upper(): m.get("sentiment", "neutral") for m in mentions}

_TAG_META = {
    "positive": ("#00c896", "0,200,150"),
    "negative": ("#ff4d6d", "255,77,109"),
    "neutral":  ("#6b7a99", "107,122,153"),
}

for item in filtered_news[:40]:
    title   = item.get("title", "")
    source  = item.get("source", "")
    pub     = item.get("published_str", "")
    url     = item.get("url", "#")
    summary_txt = item.get("summary", "")

    tag = None
    for sym, sent in mention_map.items():
        if sym in title.upper():
            tag = sent
            break

    tag_html = ""
    if tag:
        tc, trgb = _TAG_META.get(tag.lower(), ("#6b7a99", "107,122,153"))
        tag_html = (
            f'<span style="background:rgba({trgb},0.12);color:{tc};'
            f'border:1px solid rgba({trgb},0.25);border-radius:4px;'
            f'padding:1px 7px;font-size:0.62rem;font-weight:700;'
            f'letter-spacing:0.05em;margin-left:8px;">{tag.upper()}</span>'
        )

    st.markdown(
        f'<div style="background:linear-gradient(145deg,#0f1420,#0d1117);'
        f'border:1px solid rgba(255,255,255,0.05);border-radius:12px;'
        f'padding:14px 18px;margin-bottom:8px;">'
        f'<div style="margin-bottom:6px;">'
        f'<a href="{url}" target="_blank" '
        f'style="color:#93c5fd;text-decoration:none;font-weight:600;font-size:0.875rem;'
        f'line-height:1.45;">{title}</a>{tag_html}'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
        f'<span style="background:rgba(255,255,255,0.05);color:#475569;'
        f'border-radius:4px;padding:2px 8px;font-size:0.65rem;font-weight:600;">{source}</span>'
        f'<span style="color:#374151;font-size:0.7rem;">{pub}</span>'
        f'</div>'
        f'<div style="color:#374151;font-size:0.78rem;line-height:1.55;">{summary_txt[:180]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div style="margin-top:24px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);">'
    '<span style="color:#374151;font-size:0.72rem;">⚠️ For educational purposes only. Not financial advice.</span>'
    '</div>',
    unsafe_allow_html=True,
)
