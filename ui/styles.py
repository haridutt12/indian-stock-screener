"""
Global CSS for the Indian Stock Screener.

Import and call inject_global_css() at the top of every page (after
st.set_page_config) to apply consistent styling across the entire app.
"""
import re
import html as _html
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400&display=swap');

/* ── CSS variables (dark theme defaults) ──────────────────────────────────────── */
:root {
    --bg-base:       #060b14;
    --bg-surface:    #0c1422;
    --bg-elevated:   #111d2e;
    --bg-highest:    #162236;
    --border:        rgba(255,255,255,0.07);
    --border-accent: rgba(59,130,246,0.25);
    --text-primary:  #e2e8f0;
    --text-secondary:#94a3b8;
    --text-muted:    #4b5a72;
    --blue:          #3b82f6;
    --blue-dim:      rgba(59,130,246,0.12);
    --green:         #22c55e;
    --green-dim:     rgba(34,197,94,0.12);
    --red:           #ef4444;
    --red-dim:       rgba(239,68,68,0.12);
    --gold:          #f59e0b;
    --gold-dim:      rgba(245,158,11,0.12);
    --purple:        #8b5cf6;
    --radius-sm:     8px;
    --radius-md:     12px;
    --radius-lg:     16px;
    --shadow-sm:     0 1px 8px rgba(0,0,0,0.3);
    --shadow-md:     0 4px 20px rgba(0,0,0,0.4);
    --shadow-lg:     0 8px 40px rgba(0,0,0,0.5);
}

/* ── Base ────────────────────────────────────────────────────────────────────────── */
html, body, [class*="css"], .stMarkdown, .stText, p {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
}
h1 { font-weight: 800 !important; letter-spacing: -0.04em !important; font-size: 1.8rem !important; color: var(--text-primary) !important; }
h2 { font-weight: 700 !important; letter-spacing: -0.025em !important; color: var(--text-primary) !important; }
h3 { font-weight: 600 !important; letter-spacing: -0.01em !important; color: var(--text-primary) !important; }
p  { color: var(--text-secondary) !important; line-height: 1.65 !important; font-size: 0.9rem !important; }

/* ── App background ──────────────────────────────────────────────────────────────── */
.stApp, [data-testid="stAppViewContainer"] {
    background: var(--bg-base) !important;
}
[data-testid="stHeader"] {
    background: rgba(6,11,20,0.85) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid var(--border) !important;
}

/* ── Layout ────────────────────────────────────────────────────────────────────────── */
.main .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1240px !important;
}
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

/* ── Metric cards ───────────────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 18px 22px !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s !important;
    position: relative !important;
    overflow: hidden !important;
}
[data-testid="metric-container"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--blue), transparent);
    opacity: 0;
    transition: opacity 0.2s;
}
[data-testid="metric-container"]:hover {
    border-color: var(--border-accent) !important;
    box-shadow: var(--shadow-md), 0 0 0 1px rgba(59,130,246,0.08) !important;
    transform: translateY(-1px) !important;
}
[data-testid="metric-container"]:hover::before { opacity: 1; }
[data-testid="metric-container"] > label {
    color: var(--text-muted) !important;
    font-size: 0.66rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.11em !important;
    text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.04em !important;
    color: var(--text-primary) !important;
}
[data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}

/* ── Sidebar ────────────────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] > div:first-child {
    background: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] label {
    font-size: 0.67rem !important;
    font-weight: 700 !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-size: 0.72rem !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] p {
    font-size: 0.84rem !important;
    color: var(--text-secondary) !important;
}

/* ── Sidebar nav links ──────────────────────────────────────────────────────────────────── */
[data-testid="stSidebarNavLink"] {
    border-radius: var(--radius-sm) !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    color: var(--text-secondary) !important;
    padding: 8px 12px !important;
    transition: background 0.15s, color 0.15s !important;
    margin-bottom: 2px !important;
}
[data-testid="stSidebarNavLink"]:hover {
    background: rgba(59,130,246,0.08) !important;
    color: var(--blue) !important;
}
[data-testid="stSidebarNavLink"][aria-selected="true"] {
    background: rgba(59,130,246,0.12) !important;
    color: var(--blue) !important;
    font-weight: 600 !important;
}

/* ── Buttons ────────────────────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    letter-spacing: 0.01em !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-elevated) !important;
    color: var(--text-secondary) !important;
    transition: all 0.15s ease !important;
    padding: 8px 16px !important;
}
.stButton > button:hover {
    border-color: rgba(59,130,246,0.35) !important;
    color: var(--blue) !important;
    background: var(--blue-dim) !important;
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-sm) !important;
}
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    color: #fff !important;
    border: none !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 14px rgba(37,99,235,0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    box-shadow: 0 6px 20px rgba(37,99,235,0.45) !important;
    transform: translateY(-1px) !important;
}

/* ── Inputs / Selects ─────────────────────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    border-radius: var(--radius-sm) !important;
    border-color: var(--border) !important;
    background: var(--bg-elevated) !important;
    font-size: 0.85rem !important;
}

/* ── Multiselect tags ─────────────────────────────────────────────────────────────────── */
[data-baseweb="tag"] {
    background: rgba(59,130,246,0.12) !important;
    border: 1px solid rgba(59,130,246,0.28) !important;
    border-radius: 6px !important;
    padding: 2px 8px !important;
}
[data-baseweb="tag"] span {
    color: #93c5fd !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}
[data-baseweb="tag"] [role="presentation"] svg {
    fill: rgba(147,197,253,0.7) !important;
}

/* ── Number / text inputs ───────────────────────────────────────────────────────────────── */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"]   input,
[data-testid="stTextArea"]    textarea {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
    font-size: 0.88rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextInput"]   input:focus,
[data-testid="stTextArea"]    textarea:focus {
    border-color: rgba(59,130,246,0.5) !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.1) !important;
}

/* ── Checkboxes ───────────────────────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] label span { color: var(--text-secondary) !important; font-size: 0.84rem !important; }
[data-testid="stCheckbox"] input:checked + div { background: var(--blue) !important; border-color: var(--blue) !important; }

/* ── Sliders ────────────────────────────────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {
    background: var(--blue) !important;
    box-shadow: 0 0 0 4px rgba(59,130,246,0.2) !important;
}

/* ── Download button ────────────────────────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-secondary) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.82rem !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: rgba(59,130,246,0.35) !important;
    color: var(--blue) !important;
}

/* ── Selectbox dropdown options ─────────────────────────────────────────────────────────────── */
[data-baseweb="popover"] [role="option"] { font-size: 0.84rem !important; color: var(--text-secondary) !important; }
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] {
    background: var(--blue-dim) !important;
    color: var(--blue) !important;
}

/* ── DataFrames ────────────────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    border: 1px solid var(--border) !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stDataFrame"] table thead th {
    background: var(--bg-elevated) !important;
    color: var(--text-muted) !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid var(--border) !important;
    padding: 10px 14px !important;
}
[data-testid="stDataFrame"] table tbody tr { transition: background 0.1s !important; }
[data-testid="stDataFrame"] table tbody tr:nth-child(even) { background: rgba(255,255,255,0.015) !important; }
[data-testid="stDataFrame"] table tbody tr:hover { background: rgba(59,130,246,0.06) !important; }
[data-testid="stDataFrame"] table tbody td { font-size: 0.84rem !important; padding: 9px 14px !important; }

/* ── Expanders ────────────────────────────────────────────────────────────────────────── */
details {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    background: var(--bg-surface) !important;
    transition: border-color 0.2s !important;
}
details:hover { border-color: rgba(59,130,246,0.2) !important; }
details summary {
    font-weight: 600 !important;
    font-size: 0.83rem !important;
    padding: 12px 16px !important;
    color: var(--text-secondary) !important;
    letter-spacing: 0.01em !important;
    cursor: pointer !important;
}
details summary:hover { color: var(--text-primary) !important; }

/* ── Tabs ───────────────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] {
    border-bottom: 1px solid var(--border) !important;
    margin-bottom: 4px !important;
}
[data-testid="stTabs"] [data-testid="stTab"] {
    font-weight: 600 !important;
    font-size: 0.83rem !important;
    color: var(--text-muted) !important;
    padding: 10px 18px !important;
    border-radius: 0 !important;
    transition: color 0.15s !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] [data-testid="stTab"]:hover { color: var(--text-secondary) !important; }
[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--text-primary) !important;
    border-bottom: 2px solid var(--blue) !important;
    background: transparent !important;
}

/* ── Alerts / banners ───────────────────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--border) !important;
    font-size: 0.86rem !important;
}

/* ── Status widget ───────────────────────────────────────────────────────────────────────── */
[data-testid="stStatus"] {
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-surface) !important;
}

/* ── Caption / small text ──────────────────────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--text-muted) !important;
    font-size: 0.78rem !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; margin: 1.25rem 0 !important; }

/* ── Progress bars ──────────────────────────────────────────────────────────────────────── */
[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(90deg, var(--blue), var(--green)) !important;
    border-radius: 4px !important;
}

/* ── Page nav links ──────────────────────────────────────────────────────────────────────── */
a[data-testid="stPageLink-NavLink"] {
    display: inline-flex !important;
    align-items: center !important;
    width: auto !important;
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border) !important;
    border-radius: 20px !important;
    padding: 5px 14px !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.02em !important;
    transition: all 0.15s ease !important;
    margin-bottom: 10px !important;
    box-shadow: none !important;
}
a[data-testid="stPageLink-NavLink"]:hover {
    color: var(--blue) !important;
    border-color: rgba(59,130,246,0.35) !important;
    background: var(--blue-dim) !important;
}

/* ── Scrollbar ────────────────────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

/* ── Animations ────────────────────────────────────────────────────────────────────────── */
@keyframes pulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.3; }
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes slideIn {
    from { opacity: 0; transform: translateX(-10px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes glow-blue {
    0%,100% { box-shadow: 0 0 8px rgba(59,130,246,0.2); }
    50%      { box-shadow: 0 0 20px rgba(59,130,246,0.4); }
}

/* ── Scroll-reveal utility ───────────────────────────────────────────────────────────────── */
.ne-reveal {
    opacity: 0;
    transform: translateY(18px);
    transition: opacity 0.5s ease, transform 0.5s ease;
}
.ne-reveal.visible {
    opacity: 1;
    transform: translateY(0);
}

/* ── Branded spinner ──────────────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div { text-align: center; }
[data-testid="stSpinner"] svg circle { stroke: rgba(59,130,246,0.15) !important; }
[data-testid="stSpinner"] svg path,
[data-testid="stSpinner"] svg circle + circle {
    stroke: var(--blue) !important;
    filter: drop-shadow(0 0 4px rgba(59,130,246,0.5));
}
[data-testid="stSpinner"] p, [data-testid="stSpinner"] span {
    color: var(--text-muted) !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}

/* ── Top-bar loading indicator ──────────────────────────────────────────────────────────────── */
[data-testid="stStatusWidget"] svg { display: none !important; }
[data-testid="stStatusWidget"] { background: transparent !important; border: none !important; }
[data-testid="stStatusWidget"]::before {
    content: '';
    display: block;
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--blue), var(--green), var(--blue));
    background-size: 300% 100%;
    animation: ss-topbar 1.6s linear infinite;
    z-index: 9999;
}
@keyframes ss-topbar {
    0%   { background-position: 100% 0; }
    100% { background-position: -200% 0; }
}

/* ── Shimmer skeleton ─────────────────────────────────────────────────────────────────────── */
.ss-skeleton {
    background: linear-gradient(90deg,
        rgba(255,255,255,0.03) 25%,
        rgba(255,255,255,0.07) 50%,
        rgba(255,255,255,0.03) 75%
    );
    background-size: 200% 100%;
    animation: ss-shimmer 1.8s ease-in-out infinite;
    border-radius: var(--radius-sm);
}
@keyframes ss-shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* ── NiftyEdge card utility ───────────────────────────────────────────────────────────────────── */
.ne-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px 24px;
    box-shadow: var(--shadow-sm);
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
}
.ne-card:hover {
    border-color: var(--border-accent);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}
</style>
"""


_SCROLL_REVEAL_JS = """
<script>
(function() {
    function revealOnScroll() {
        var els = document.querySelectorAll('.ne-reveal:not(.visible)');
        els.forEach(function(el) {
            var rect = el.getBoundingClientRect();
            if (rect.top < window.innerHeight - 40) {
                el.classList.add('visible');
            }
        });
    }
    window.addEventListener('scroll', revealOnScroll, { passive: true });
    setTimeout(revealOnScroll, 300);
    var obs = new MutationObserver(function() { setTimeout(revealOnScroll, 150); });
    obs.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""


def _ai_inline(text: str) -> str:
    """Escape HTML entities then convert inline markdown to styled HTML."""
    text = _html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#f1f5f9;">\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',     r'<em style="color:#e2e8f0;">\1</em>', text)
    text = re.sub(r'`(.+?)`',
                  r'<code style="background:rgba(255,255,255,0.08);padding:2px 5px;'
                  r'border-radius:4px;font-family:monospace;font-size:0.82em;">\1</code>', text)
    return text


def render_ai_card(text: str, accent: str = "#8b5cf6") -> None:
    """Render an LLM markdown response inside a styled dark card."""
    parts: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith("## "):
            parts.append(
                f'<div style="font-size:0.7rem;font-weight:800;color:{accent};'
                f'text-transform:uppercase;letter-spacing:0.1em;'
                f'border-bottom:1px solid {accent}40;padding-bottom:5px;'
                f'margin:22px 0 10px;">{_html.escape(stripped[3:])}</div>'
            )
            i += 1

        elif stripped.startswith("# "):
            parts.append(
                f'<div style="font-size:1rem;font-weight:800;color:#f1f5f9;'
                f'margin:12px 0 6px;">{_html.escape(stripped[2:])}</div>'
            )
            i += 1

        elif stripped.startswith("|"):
            rows: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            trows: list[str] = ['<table style="width:100%;border-collapse:collapse;margin:8px 0 16px;">']
            first = True
            for row in rows:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                if all(set(c) <= {"-", " ", ":"} for c in cells):
                    first = False
                    continue
                tag = "th" if first else "td"
                style = (
                    f'border:1px solid rgba(255,255,255,0.1);padding:7px 12px;'
                    f'font-size:0.82rem;color:{accent};font-weight:700;'
                    f'text-align:left;background:rgba(255,255,255,0.03);'
                ) if first else (
                    'border:1px solid rgba(255,255,255,0.07);padding:7px 12px;'
                    'font-size:0.85rem;color:#cbd5e1;'
                )
                trows.append('<tr>' + ''.join(
                    f'<{tag} style="{style}">{_ai_inline(c)}</{tag}>' for c in cells
                ) + '</tr>')
                first = False
            trows.append('</table>')
            parts.append('\n'.join(trows))

        elif stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            li = ''.join(
                f'<li style="color:#cbd5e1;line-height:1.75;margin-bottom:3px;">'
                f'{_ai_inline(item)}</li>' for item in items
            )
            parts.append(f'<ul style="margin:6px 0 10px;padding-left:22px;">{li}</ul>')

        elif stripped in ("", "---"):
            i += 1

        else:
            parts.append(
                f'<p style="color:#cbd5e1;line-height:1.75;margin:4px 0 6px;'
                f'font-size:0.88rem;">{_ai_inline(stripped)}</p>'
            )
            i += 1

    inner = "\n".join(parts)
    st.markdown(
        f'<div style="background:linear-gradient(145deg,#111d2e,#0c1422);'
        f'border:1px solid rgba(255,255,255,0.08);border-radius:14px;'
        f'padding:22px 26px;margin-top:8px;">'
        f'{inner}'
        f'</div>',
        unsafe_allow_html=True,
    )


def inject_global_css() -> None:
    """Inject shared CSS + scroll-reveal JS. Call once per page after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.components.v1.html(_SCROLL_REVEAL_JS, height=0)


def show_loading(message: str, color: str = "#3b82f6"):
    """Show an animated pulsing loading banner. Call .empty() on the returned slot to dismiss."""
    slot = st.empty()
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    slot.markdown(
        f'<div style="background:rgba({r},{g},{b},0.07);'
        f'border:1px solid rgba({r},{g},{b},0.22);'
        f'border-radius:12px;padding:13px 18px;'
        f'display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
        f'<div style="width:7px;height:7px;border-radius:50%;background:{color};'
        f'animation:pulse 1.2s ease-in-out infinite;flex-shrink:0;"></div>'
        f'<div style="color:{color};font-weight:600;font-size:0.84rem;letter-spacing:0.01em;">{message}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    return slot


def page_header(
    title: str,
    subtitle: str = "",
    badge: str = "",
    badge_color: str = "#3b82f6",
) -> None:
    """Consistent page header with eyebrow, title, badge and accent divider."""
    badge_html = (
        f'<span style="display:inline-block;background:rgba(59,130,246,0.1);'
        f'color:{badge_color};border:1px solid rgba(59,130,246,0.28);'
        f'border-radius:20px;padding:3px 12px;font-size:0.63rem;'
        f'font-weight:700;letter-spacing:0.1em;vertical-align:middle;'
        f'margin-left:12px;text-transform:uppercase;">{badge}</span>'
        if badge else ""
    )
    sub_html = (
        f'<div style="font-size:0.66rem;font-weight:700;color:#4b5a72;'
        f'text-transform:uppercase;letter-spacing:0.13em;margin-bottom:6px;">'
        f'{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'{sub_html}'
        f'<div style="display:flex;align-items:center;margin-bottom:6px;">'
        f'<span style="font-size:1.75rem;font-weight:800;color:#e2e8f0;'
        f'letter-spacing:-0.04em;line-height:1.15;">{title}</span>'
        f'{badge_html}'
        f'</div>'
        f'<div style="height:1px;background:linear-gradient(90deg,'
        f'rgba(59,130,246,0.5),rgba(34,197,94,0.2),transparent);'
        f'margin-bottom:24px;border-radius:1px;margin-top:10px;"></div>',
        unsafe_allow_html=True,
    )


def auth_guard() -> None:
    """Show login wall if not authenticated. No-op when auth is not configured (local dev)."""
    try:
        _auth_on = bool(st.secrets.get("auth"))
    except Exception:
        _auth_on = False

    if not _auth_on or st.user.is_logged_in:
        return

    # ── Show OAuth error if the callback failed ───────────────────────────────
    _oauth_err = (
        st.query_params.get("error")
        or st.session_state.get("oauth_error")
        or st.session_state.get("_oauth_error")
    )
    if _oauth_err:
        st.error(
            f"Sign-in failed: `{_oauth_err}`. "
            "Please clear cookies, try a different browser, or contact the app owner.",
            icon="🔒",
        )

    # ── Login wall ────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="min-height:60vh;display:flex;align-items:center;justify-content:center;">'
        '<div style="text-align:center;max-width:420px;width:100%;padding:0 16px;">'

        # Logo
        '<div style="font-size:2.6rem;font-weight:900;letter-spacing:-0.05em;'
        'color:#e2e8f0;margin-bottom:4px;">'
        'Nifty<span style="background:linear-gradient(135deg,#3b82f6,#22c55e);'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">Edge</span></div>'
        '<div style="color:#4b5a72;font-size:0.68rem;font-weight:700;'
        'letter-spacing:0.13em;margin-bottom:40px;">AI-POWERED NSE / BSE ANALYSIS</div>'

        # Card
        '<div style="background:linear-gradient(145deg,#0c1422,#111d2e);'
        'border:1px solid rgba(255,255,255,0.08);border-radius:20px;'
        'padding:36px 32px;box-shadow:0 24px 64px rgba(0,0,0,0.5);">'

        '<div style="font-size:1.1rem;font-weight:700;color:#e2e8f0;margin-bottom:8px;">'
        'Welcome back \U0001f44b</div>'
        '<div style="color:#4b5a72;font-size:0.82rem;line-height:1.75;margin-bottom:28px;">'
        'Sign in with your Google account to access your personalised '
        'signals dashboard, trade journal, and market intelligence.</div>'

        # Feature pills
        '<div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:28px;">'
        + "".join([
            f'<span style="background:rgba(59,130,246,0.08);color:#64748b;'
            f'border:1px solid rgba(59,130,246,0.15);border-radius:20px;'
            f'padding:3px 10px;font-size:0.65rem;font-weight:600;">{t}</span>'
            for t in ["Swing Signals", "Intraday Ideas", "Trade Journal",
                      "AI Analyst", "Portfolio Health", "Market Overview"]
        ])
        + '</div>'

        '</div></div></div>',
        unsafe_allow_html=True,
    )

    _, _btn_col, _ = st.columns([1, 1.4, 1])
    with _btn_col:
        if st.button(
            "Continue with Google →",
            type="primary",
            use_container_width=True,
            key="ne_login_btn",
        ):
            st.login("google")
        st.markdown(
            '<p style="color:#374151;font-size:0.65rem;text-align:center;margin-top:4px;">'
            'Secure · Google OAuth 2.0 · No password needed</p>',
            unsafe_allow_html=True,
        )
    st.stop()


def user_sidebar() -> None:
    """Compact user profile card + logout button. Call inside a sidebar block."""
    try:
        if not st.user.is_logged_in:
            return
    except Exception:
        return

    name   = getattr(st.user, "name",    "") or ""
    email  = getattr(st.user, "email",   "") or ""
    avatar = getattr(st.user, "picture", "") or ""

    if avatar:
        avatar_html = (
            f'<img src="{avatar}" style="width:34px;height:34px;border-radius:50%;'
            f'object-fit:cover;border:2px solid rgba(59,130,246,0.3);flex-shrink:0;" />'
        )
    else:
        initial = (name[:1] or email[:1] or "U").upper()
        avatar_html = (
            f'<div style="width:34px;height:34px;border-radius:50%;flex-shrink:0;'
            f'background:linear-gradient(135deg,#3b82f6,#22c55e);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:0.85rem;font-weight:700;color:#fff;">{initial}</div>'
        )

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:9px;'
        f'background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.14);'
        f'border-radius:12px;padding:9px 11px;margin-bottom:6px;">'
        f'{avatar_html}'
        f'<div style="min-width:0;flex:1;">'
        f'<div style="font-size:0.8rem;font-weight:700;color:#e2e8f0;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{name or "User"}</div>'
        f'<div style="font-size:0.62rem;color:#4b5a72;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{email}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Sign out", key="ne_signout"):
        st.logout()
