"""
Global CSS for the Indian Stock Screener.

Import and call inject_global_css() at the top of every page (after
st.set_page_config) to apply consistent styling across the entire app.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Base typography ─────────────────────────────────────────────────────── */
html, body, [class*="css"], .stMarkdown, .stText {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
h1 { font-weight: 800 !important; letter-spacing: -0.03em !important; }
h2 { font-weight: 700 !important; letter-spacing: -0.02em !important; }
h3 { font-weight: 700 !important; letter-spacing: -0.01em !important; }

/* ── Layout ──────────────────────────────────────────────────────────────── */
.main .block-container {
    padding-top: 1.4rem !important;
    padding-bottom: 2rem !important;
}
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: linear-gradient(145deg, #1e2235 0%, #181c2e 100%);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 18px 22px !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.28),
                inset 0 1px 0 rgba(255,255,255,0.04);
}
[data-testid="metric-container"] > label {
    color: #6b7a99 !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
}
[data-testid="stMetricDelta"] {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] > div:first-child {
    background: #111827 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] label {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    color: #6b7a99 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.01em !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.3) !important;
}
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #f0b429 0%, #d9971a 100%) !important;
    color: #000 !important;
    border: none !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 14px rgba(240,180,41,0.25) !important;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
    box-shadow: 0 8px 24px rgba(240,180,41,0.4) !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 14px !important;
    overflow: hidden !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
}

/* ── Expanders ───────────────────────────────────────────────────────────── */
details {
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
details summary {
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 10px 14px !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── Alerts / banners ────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: none !important;
}

/* ── Page nav links (home page tiles) ────────────────────────────────────── */
a[data-testid="stPageLink-NavLink"] {
    background: linear-gradient(145deg, #1e2235, #181c2e) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
    margin-bottom: 6px !important;
    font-weight: 600 !important;
    transition: all 0.18s ease !important;
}
a[data-testid="stPageLink-NavLink"]:hover {
    border-color: rgba(240,180,41,0.45) !important;
    transform: translateX(3px) !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25) !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.22); }
</style>
"""


def inject_global_css() -> None:
    """Inject shared CSS into the current Streamlit page. Call once, right after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)
