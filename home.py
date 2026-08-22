"""
NiftyEdge — Home page
Tabs: Home · Signals · News · Screener · Tools
"""
import logging
import math as _math
import datetime as _dt
import streamlit as st
import pytz as _pytz

from signals.signal_logger import get_signal_logger
from ui.styles import inject_global_css, auth_guard, user_sidebar

logger = logging.getLogger(__name__)
_IST   = _pytz.timezone("Asia/Kolkata")


def _sf(v):
    """Safe float: returns None for NaN/Inf/None/error."""
    try:
        f = float(v)
        return None if (_math.isnan(f) or _math.isinf(f)) else f
    except Exception:
        return None


def _pct(curr, prev):
    """Safe percentage change: (curr-prev)/prev*100, or None on bad input."""
    c, p = _sf(curr), _sf(prev)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / p * 100

inject_global_css()
auth_guard()


# ── Cached data helpers (module-level so @st.cache_data hashes reliably) ───────

@st.cache_data(ttl=300, show_spinner=False)
def _quick_stats():
    try:
        log     = get_signal_logger()
        perf    = log.get_performance_summary(days_back=30)
        today   = _dt.date.today().isoformat()
        today_s = log.get_signals(days_back=1)
        today_count = sum(1 for s in today_s if s.get("signal_date") == today)
        return {"today": today_count, "open": perf.get("open", 0),
                "wr": perf.get("win_rate", 0), "total": perf.get("total", 0)}
    except Exception:
        return {"today": 0, "open": 0, "wr": 0, "total": 0}


@st.cache_data(ttl=180, show_spinner=False)
def _today_signals():
    try:
        log   = get_signal_logger()
        today = _dt.date.today().isoformat()
        return [s for s in log.get_signals(days_back=1) if s.get("signal_date") == today]
    except Exception:
        return []


@st.cache_data(ttl=120, show_spinner=False)
def _hero_indices():
    from data.fetcher import fetch_index_data
    from data.market_status import market_status as _ms_fn
    from config.settings import INDICES
    import yfinance as yf
    _ms      = _ms_fn()
    _is_open = _ms["is_market_open"]
    results  = {}
    for name in ["Nifty 50", "Bank Nifty", "Sensex"]:
        ticker = INDICES.get(name)
        if not ticker:
            continue
        df = fetch_index_data(ticker, period="5d", interval="1d")
        if df is None or len(df) < 2:
            continue
        try:
            if _is_open:
                fi    = yf.Ticker(ticker).fast_info
                price = _sf(fi.last_price)
                prev  = _sf(fi.previous_close)
            else:
                price = _sf(df["Close"].iloc[-1])
                prev  = _sf(df["Close"].iloc[-2])
            if price is None or prev is None:
                continue
            chg = _pct(price, prev)
            if chg is None:
                continue
            jan1    = _dt.date(df.index[-1].year, 1, 1)
            ytd_df  = df[df.index.date >= jan1]
            ytd_base = _sf(ytd_df["Close"].iloc[0]) if not ytd_df.empty else None
            ytd_pct  = _pct(price, ytd_base) if ytd_base else None
            results[name] = {"price": price, "chg": chg, "ytd": ytd_pct}
        except Exception:
            pass
    try:
        vix_df = fetch_index_data("^INDIAVIX", period="5d", interval="1d")
        if vix_df is not None and len(vix_df) >= 2:
            v_price = _sf(vix_df["Close"].iloc[-1])
            v_prev  = _sf(vix_df["Close"].iloc[-2])
            v_chg   = _pct(v_price, v_prev)
            if v_price is not None and v_chg is not None:
                results["VIX"] = {"price": v_price, "chg": v_chg, "ytd": None}
    except Exception:
        pass
    return results


@st.cache_data(ttl=300, show_spinner=False)
def _movers():
    try:
        from data.fetcher import fetch_stock_data
        from config.stock_universe import NIFTY_50
        tickers    = list(NIFTY_50.values())
        price_data = fetch_stock_data(tickers, period="5d", interval="1d")
        changes    = []
        for t, df in price_data.items():
            if df is None or len(df) < 2:
                continue
            curr = _sf(df["Close"].iloc[-1])
            prev = _sf(df["Close"].iloc[-2])
            chg  = _pct(curr, prev)
            if curr is None or chg is None:
                continue
            changes.append({"ticker": t.replace(".NS", ""), "price": curr, "chg": chg})
        changes.sort(key=lambda x: x["chg"], reverse=True)
        return changes[:5], changes[-5:][::-1]
    except Exception:
        return [], []


@st.cache_data(ttl=300, show_spinner=False)
def _home_top3():
    try:
        from signals.signal_ranker import rank_signals
        _log   = get_signal_logger()
        _opens = _log.get_open_signals()
        return rank_signals(_opens)[:3]
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _volume_anomalies():
    try:
        from data.fetcher import fetch_stock_data
        from config.stock_universe import NIFTY_50
        tickers = list(NIFTY_50.values())
        df_map  = fetch_stock_data(tickers, period="25d", interval="1d")
        anomalies = []
        for t, df in df_map.items():
            if df is None or len(df) < 8:
                continue
            vol     = _sf(df["Volume"].iloc[-1])
            avg_vol = _sf(df["Volume"].iloc[:-1].mean())
            if not vol or not avg_vol or avg_vol <= 0:
                continue
            ratio = vol / avg_vol
            if ratio < 1.5:
                continue
            close = _sf(df["Close"].iloc[-1])
            prev  = _sf(df["Close"].iloc[-2])
            chg   = _pct(close, prev)
            if close is None or chg is None:
                continue
            anomalies.append({
                "ticker": t.replace(".NS", ""),
                "ratio":  ratio,
                "price":  close,
                "chg":    chg,
                "vol":    int(vol),
            })
        anomalies.sort(key=lambda x: x["ratio"], reverse=True)
        return anomalies[:8]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def _top_news():
    try:
        from data.news_fetcher import fetch_market_news
        return fetch_market_news()[:4]
    except Exception:
        return []



# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.h-scroll {
    display:flex !important; overflow-x:auto !important; gap:12px !important;
    padding-bottom:6px !important; -webkit-overflow-scrolling:touch !important;
    scrollbar-width:none !important;
}
.h-scroll::-webkit-scrollbar { display:none !important; }
.feed-card {
    background:linear-gradient(145deg,#131929,#0f1420);
    border:1px solid rgba(255,255,255,0.06);border-radius:16px;
    padding:18px 20px;margin-bottom:10px;
}
.nav-card { text-decoration:none !important; display:block; margin-bottom:6px; }
.nav-card-inner {
    background:linear-gradient(145deg,#141828,#0f1420);
    border:1px solid rgba(255,255,255,0.07);border-radius:14px;
    display:flex;align-items:center;gap:14px;padding:14px 18px;
    transition:border-color 0.2s ease,background 0.2s ease,transform 0.15s ease;
    cursor:pointer;
}
.nav-card:hover .nav-card-inner {
    border-color:rgba(240,180,41,0.22);
    background:linear-gradient(145deg,#191f35,#141828);
    transform:translateX(2px);
}
.nav-icon {
    width:40px;height:40px;min-width:40px;
    border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
</style>
""", unsafe_allow_html=True)

# ── Market status ──────────────────────────────────────────────────────────────
from data.market_status import market_status
status  = market_status()
is_open = status["is_market_open"]
is_pre  = status["is_pre_market"]

_sc    = "#00c896" if is_open else ("#f0b429" if is_pre else "#ff4d6d")
_rgb   = "0,200,150" if is_open else ("240,180,41" if is_pre else "255,77,109")
_pulse = "animation:pulse 1.4s ease-in-out infinite;" if (is_open or is_pre) else ""
_now   = _dt.datetime.now(_IST).strftime("%H:%M IST")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="display:flex;align-items:center;justify-content:space-between;'
    f'padding:8px 0 16px;">'
    f'<div>'
    f'<div style="font-size:1.65rem;font-weight:900;letter-spacing:-0.045em;color:#e2e8f0;">'
    f'Nifty<span style="background:linear-gradient(135deg,#3b82f6,#22c55e);'
    f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;">Edge</span></div>'
    f'<div style="font-size:0.7rem;color:#4b5a72;margin-top:2px;letter-spacing:0.04em;">'
    f'AI-POWERED NSE/BSE ANALYSIS</div>'
    f'</div>'
    f'<div style="display:flex;align-items:center;gap:8px;">'
    f'<div style="display:inline-flex;align-items:center;gap:6px;'
    f'background:rgba({_rgb},0.08);border:1px solid rgba({_rgb},0.22);'
    f'border-radius:20px;padding:5px 12px;">'
    f'<div style="width:7px;height:7px;border-radius:50%;background:{_sc};{_pulse}flex-shrink:0;"></div>'
    f'<span style="color:{_sc};font-size:0.7rem;font-weight:700;">'
    f'{status["status_label"].split("(")[0].strip()}</span>'
    f'</div>'
    f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);'
    f'border-radius:20px;padding:5px 12px;font-size:0.7rem;color:#4b5a72;">{_now}</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Personalized welcome ───────────────────────────────────────────────────────
try:
    _uname  = (getattr(st.user, "name",    "") or "").strip()
    _uemail = (getattr(st.user, "email",   "") or "").strip()
    _uavatar= (getattr(st.user, "picture", "") or "").strip()
    _fname  = _uname.split()[0] if _uname else (_uemail.split("@")[0] if _uemail else "")
    if _fname:
        _hour  = _dt.datetime.now(_IST).hour
        _greet = "Good morning" if _hour < 12 else ("Good afternoon" if _hour < 17 else "Good evening")
        _avatar_html = (
            f'<img src="{_uavatar}" style="width:36px;height:36px;border-radius:50%;'
            f'object-fit:cover;border:2px solid rgba(59,130,246,0.35);flex-shrink:0;" />'
            if _uavatar else
            f'<div style="width:36px;height:36px;border-radius:50%;flex-shrink:0;'
            f'background:linear-gradient(135deg,#3b82f6,#22c55e);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:0.9rem;font-weight:700;color:#fff;">'
            f'{_fname[0].upper()}</div>'
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;'
            f'margin:-8px 0 20px;padding:12px 18px;'
            f'background:linear-gradient(90deg,rgba(59,130,246,0.08),rgba(34,197,94,0.04),transparent);'
            f'border:1px solid rgba(59,130,246,0.12);border-radius:12px;">'
            f'{_avatar_html}'
            f'<div>'
            f'<div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;">'
            f'{_greet}, {_fname}! 👋</div>'
            f'<div style="font-size:0.72rem;color:#4b5a72;margin-top:1px;">'
            f'Here\'s your personalised market snapshot for today.</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

# ── SVG icon library ───────────────────────────────────────────────────────────
_SVG = {
    "swing":  '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="6" width="4" height="8" rx="1" fill="rgba(255,255,255,0.1)"/><line x1="5" y1="3" x2="5" y2="6"/><line x1="5" y1="14" x2="5" y2="17"/><rect x="13" y="9" width="4" height="5" rx="1" fill="rgba(255,255,255,0.05)"/><line x1="15" y1="6" x2="15" y2="9"/><line x1="15" y1="14" x2="15" y2="17"/></svg>',
    "intra":  '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="1,15 6,8 10,12 15,5"/><polyline points="13,5 15,5 15,7"/></svg>',
    "log":    '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="2" width="14" height="16" rx="2"/><line x1="7" y1="7" x2="13" y2="7"/><line x1="7" y1="10" x2="13" y2="10"/><line x1="7" y1="13" x2="10" y2="13"/></svg>',
    "shield": '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 2L3 5v5c0 4.4 3 8.2 7 9 4-.8 7-4.6 7-9V5z"/><polyline points="7,10 9,12 13,8"/></svg>',
    "fund":   '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="12" width="4" height="6" rx="1"/><rect x="8" y="7" width="4" height="11" rx="1"/><rect x="14" y="3" width="4" height="15" rx="1"/></svg>',
    "tech":   '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="2,14 6,8 10,11 15,5"/><circle cx="15" cy="5" r="1.5" fill="currentColor"/></svg>',
    "globe":  '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="10" cy="10" r="7"/><line x1="3" y1="10" x2="17" y2="10"/><path d="M10 3c-2.5 2.5-3 4.5-3 7s.5 4.5 3 7c2.5-2.5 3-4.5 3-7s-.5-4.5-3-7z"/></svg>',
    "news":   '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="4" width="16" height="13" rx="2"/><line x1="6" y1="8" x2="14" y2="8"/><line x1="6" y1="11" x2="14" y2="11"/><line x1="6" y1="14" x2="10" y2="14"/></svg>',
    "money":  '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="5" width="16" height="11" rx="2"/><circle cx="10" cy="10" r="2.5"/><line x1="5" y1="5" x2="5" y2="16"/><line x1="15" y1="5" x2="15" y2="16"/></svg>',
}


def _nav_card(slug: str, ico: str, title: str, desc: str, col: str, rgb: str) -> str:
    return (
        f'<a href="/{slug}" class="nav-card">'
        f'<div class="nav-card-inner">'
        f'<div class="nav-icon" style="background:rgba({rgb},0.1);color:{col};">{ico}</div>'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-weight:700;color:#e2e8f0;font-size:0.88rem;letter-spacing:-0.01em;">{title}</div>'
        f'<div style="color:#4b5563;font-size:0.72rem;margin-top:2px;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{desc}</div>'
        f'</div>'
        f'<svg width="16" height="16" viewBox="0 0 20 20" fill="none" style="flex-shrink:0;'
        f'color:#374151;" stroke="currentColor" stroke-width="2" stroke-linecap="round">'
        f'<polyline points="7,4 13,10 7,16"/></svg>'
        f'</div></a>'
    )


with st.sidebar:
    user_sidebar()

# ── Tabs ───────────────────────────────────────────────────────────────────────
t_home, t_signals, t_news, t_screener, t_tools = st.tabs([
    "🏠 Home", "💹 Signals", "📰 News", "🔍 Screener", "🛠️ Tools"
])

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — HOME                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with t_home:

    # ── AI Features Strip ──────────────────────────────────────────────────────
    ai_c1, ai_c2 = st.columns(2)
    with ai_c1:
        st.markdown(
            '<div style="background:linear-gradient(145deg,#150d2a,#0f1420);'
            'border:1px solid rgba(139,92,246,0.25);border-left:4px solid #8b5cf6;'
            'border-radius:14px;padding:22px 24px;">'
            '<div style="font-size:0.58rem;font-weight:700;color:#8b5cf6;'
            'text-transform:uppercase;letter-spacing:0.14em;margin-bottom:10px;">'
            '✦ AI-Powered</div>'
            '<div style="font-size:1.2rem;font-weight:800;color:#f1f5f9;'
            'line-height:1.3;margin-bottom:10px;">Ask AI About Any Stock</div>'
            '<div style="font-size:0.75rem;color:#64748b;line-height:1.7;margin-bottom:18px;">'
            'Instant trade analysis — trend direction, key support &amp; resistance, '
            'entry zone, stop loss &amp; targets. Like a research analyst on demand, '
            'free and available 24/7.</div>'
            '<a href="/AI_Analyst" style="display:inline-flex;align-items:center;gap:6px;'
            'font-size:0.78rem;font-weight:700;color:#8b5cf6;text-decoration:none;">'
            'Analyse a Stock'
            '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"'
            ' stroke-width="2.5" stroke-linecap="round"><polyline points="7,4 13,10 7,16"/></svg>'
            '</a>'
            '</div>',
            unsafe_allow_html=True,
        )
    with ai_c2:
        st.markdown(
            '<div style="background:linear-gradient(145deg,#0d1f18,#0f1420);'
            'border:1px solid rgba(34,197,94,0.25);border-left:4px solid #22c55e;'
            'border-radius:14px;padding:22px 24px;">'
            '<div style="font-size:0.58rem;font-weight:700;color:#22c55e;'
            'text-transform:uppercase;letter-spacing:0.14em;margin-bottom:10px;">'
            '✦ AI-Powered</div>'
            '<div style="font-size:1.2rem;font-weight:800;color:#f1f5f9;'
            'line-height:1.3;margin-bottom:10px;">Portfolio Health Check</div>'
            '<div style="font-size:0.75rem;color:#64748b;line-height:1.7;margin-bottom:18px;">'
            'Enter your holdings and get AI feedback — sector concentration, '
            'positions breaching key levels, P&amp;L breakdown &amp; '
            'a plain-English verdict on what to do next.</div>'
            '<a href="/Portfolio_Health" style="display:inline-flex;align-items:center;gap:6px;'
            'font-size:0.78rem;font-weight:700;color:#22c55e;text-decoration:none;">'
            'Check My Portfolio'
            '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"'
            ' stroke-width="2.5" stroke-linecap="round"><polyline points="7,4 13,10 7,16"/></svg>'
            '</a>'
            '</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

    # ── Best Trades Right Now ───────────────────────────────────────────────────
    _h3 = _home_top3()
    if _h3:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#f0b429;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">'
            '⭐ Best Trades Right Now</div>',
            unsafe_allow_html=True,
        )
        _rank_colors  = ["#f0b429", "#94a3b8", "#cd7f32"]
        _rank_borders = ["rgba(240,180,41,0.45)", "rgba(148,163,184,0.35)", "rgba(205,127,50,0.35)"]
        _rank_bgs     = ["rgba(240,180,41,0.05)", "rgba(148,163,184,0.03)", "rgba(205,127,50,0.04)"]
        _rank_medals  = ["🥇", "🥈", "🥉"]
        _h3_cols = st.columns(len(_h3))
        for _hi, (_hsc, _hbd, _hsig, _hcp) in enumerate(_h3):
            _hrc    = _rank_colors[_hi]
            _htick  = _hsig["ticker"].replace(".NS", "")
            _hdir   = _hsig.get("direction", "LONG")
            _hdc    = "#00c896" if _hdir == "LONG" else "#ff4d6d"
            _hda    = "↑ L" if _hdir == "LONG" else "↓ S"
            _he     = float(_hsig.get("entry_price") or 0)
            _hsl    = float(_hsig.get("stop_loss")   or 0)
            _ht1    = float(_hsig.get("target_1")    or 0)
            _hrr    = float(_hsig.get("risk_reward")  or 0)
            _hstrat = _hsig.get("strategy", "")
            _hprox  = _hbd.get("_prox_label", "")
            _hcp_fmt = f"₹{_hcp:,.1f}" if _hcp else "—"
            _hbar = "".join([
                f'<div style="height:3px;flex:0 0 {fm}%;background:{fc};'
                f'opacity:0.85;border-radius:2px;"></div>'
                for _, fv, fm, fc in [
                    ("C",  _hbd.get("Confidence",   0), 25, "#7c83fd"),
                    ("T",  _hbd.get("Technical",    0), 20, "#60a5fa"),
                    ("F",  _hbd.get("Fundamental",  0), 15, "#34d399"),
                    ("RR", _hbd.get("Risk/Reward",  0), 20, "#f97316"),
                    ("E",  _hbd.get("Entry Timing", 0), 20, "#f0b429"),
                ]
            ])
            _prox_c = (
                "#00c896" if ("✓" in _hprox or "below" in _hprox)
                else "#f0b429" if ("missed" not in _hprox and "late" not in _hprox)
                else "#ff4d6d"
            )
            with _h3_cols[_hi]:
                st.markdown(
                    f'<div style="background:{_rank_bgs[_hi]};border:1px solid {_rank_borders[_hi]};'
                    f'border-top:3px solid {_hrc};border-radius:14px;padding:14px 16px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                    f'<div style="display:flex;align-items:center;gap:7px;">'
                    f'<span style="font-size:1rem;">{_rank_medals[_hi]}</span>'
                    f'<span style="font-size:1rem;font-weight:800;color:#e2e8f0;">{_htick}</span>'
                    f'<span style="background:{_hdc}22;color:{_hdc};border:1px solid {_hdc}33;'
                    f'border-radius:4px;padding:1px 6px;font-size:0.62rem;font-weight:700;">{_hda}</span>'
                    f'</div>'
                    f'<div style="text-align:right;">'
                    f'<div style="font-size:1.1rem;font-weight:900;color:{_hrc};line-height:1;">{_hsc:.0f}</div>'
                    f'<div style="font-size:0.55rem;color:#475569;">/100</div>'
                    f'</div></div>'
                    f'<div style="display:flex;gap:2px;margin-bottom:8px;">{_hbar}</div>'
                    f'<div style="color:#64748b;font-size:0.65rem;margin-bottom:8px;">{_hstrat}</div>'
                    f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px;">'
                    f'<div style="text-align:center;background:rgba(255,255,255,0.04);border-radius:5px;padding:4px;">'
                    f'<div style="font-size:0.52rem;color:#374151;">Entry</div>'
                    f'<div style="font-size:0.78rem;font-weight:700;color:#e2e8f0;">₹{_he:,.0f}</div></div>'
                    f'<div style="text-align:center;background:rgba(255,77,109,0.07);border-radius:5px;padding:4px;">'
                    f'<div style="font-size:0.52rem;color:#374151;">SL</div>'
                    f'<div style="font-size:0.78rem;font-weight:700;color:#ff4d6d;">₹{_hsl:,.0f}</div></div>'
                    f'<div style="text-align:center;background:rgba(0,200,150,0.06);border-radius:5px;padding:4px;">'
                    f'<div style="font-size:0.52rem;color:#374151;">T1</div>'
                    f'<div style="font-size:0.78rem;font-weight:700;color:#00c896;">₹{_ht1:,.0f}</div></div>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="font-size:0.65rem;color:#475569;">{_hcp_fmt} now · R:R {_hrr:.1f}×</span>'
                    f'<span style="color:{_prox_c};font-size:0.62rem;font-weight:600;">{_hprox}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
        st.markdown(
            '<a href="/Signal_Log" style="display:inline-flex;align-items:center;gap:5px;'
            'margin-top:8px;text-decoration:none;color:#f0b429;font-size:0.75rem;font-weight:600;">'
            'See all ranked signals →</a>',
            unsafe_allow_html=True,
        )
        st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Multi-Timeframe Confluence ─────────────────────────────────────────────
    try:
        from signals.signal_logger import get_signal_logger as _gsl_h
        _confluences = _gsl_h().get_confluence_signals()
        if _confluences:
            st.markdown(
                '<div style="font-size:0.68rem;font-weight:700;color:#a78bfa;'
                'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
                '⚡ Multi-Timeframe Confluence</div>',
                unsafe_allow_html=True,
            )
            _cf_html = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">'
            for _cf in _confluences[:6]:
                _cdir = _cf["direction"]
                _cc   = "#00c896" if _cdir == "LONG" else "#ff4d6d"
                _carr = "↑" if _cdir == "LONG" else "↓"
                _cf_html += (
                    f'<div style="background:rgba(167,139,250,0.05);border:1px solid rgba(167,139,250,0.2);'
                    f'border-left:3px solid #a78bfa;border-radius:10px;padding:10px 14px;min-width:180px;">'
                    f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">'
                    f'<span style="font-size:0.88rem;font-weight:800;color:#e2e8f0;">'
                    f'{_cf["ticker"].replace(".NS","")}</span>'
                    f'<span style="font-size:0.7rem;font-weight:700;color:{_cc};">{_carr} {_cdir}</span>'
                    f'</div>'
                    f'<div style="font-size:0.65rem;color:#475569;line-height:1.5;">'
                    f'Swing: {_cf["swing_strategy"]}<br>'
                    f'Intraday: {_cf["intra_strategy"]}</div>'
                    f'<div style="font-size:0.68rem;color:#a78bfa;font-weight:600;margin-top:4px;">'
                    f'R:R {_cf["risk_reward"]:.1f}× · Conf {_cf["confidence"]}★</div>'
                    f'</div>'
                )
            _cf_html += '</div>'
            st.markdown(_cf_html, unsafe_allow_html=True)
    except Exception:
        pass

    # ── System Quality Strip ───────────────────────────────────────────────────
    try:
        from analysis.signal_quality import full_report
        from signals.signal_logger import get_signal_logger as _get_sq_sl
        _sq_signals = _get_sq_sl().get_signals(days_back=30)
        _sq_closed  = [s for s in _sq_signals if s.get("outcome") not in (None, "OPEN")]
        if len(_sq_closed) >= 5:
            _sqr = full_report(_sq_closed)
            _exp   = _sqr.get("expectancy", 0)
            _wr    = _sqr.get("win_rate", 0)
            _mdd   = _sqr.get("max_drawdown_r", 0)
            _streak = _sqr.get("current_streak", 0)
            _stype  = _sqr.get("current_streak_type", "")
            _exp_c  = "#00c896" if _exp > 0 else "#ff4d6d"
            _wr_c   = "#00c896" if _wr >= 0.5 else ("#f0b429" if _wr >= 0.4 else "#ff4d6d")
            _mdd_c  = "#ff4d6d" if abs(_mdd) > 3 else ("#f0b429" if abs(_mdd) > 1.5 else "#00c896")
            _sk_c   = "#00c896" if _stype == "win" else "#ff4d6d"
            _sk_label = f"{'W' if _stype=='win' else 'L'}{abs(int(_streak))}"
            st.markdown(
                f'<div style="display:flex;gap:16px;align-items:center;'
                f'background:linear-gradient(90deg,rgba(139,92,246,0.08),rgba(16,185,129,0.05));'
                f'border:1px solid rgba(139,92,246,0.15);border-radius:8px;padding:8px 14px;'
                f'margin-bottom:12px;flex-wrap:wrap;">'
                f'<span style="font-size:0.58rem;font-weight:700;color:#6366f1;text-transform:uppercase;'
                f'letter-spacing:0.08em;white-space:nowrap;">30-Day System</span>'
                f'<span style="font-size:0.7rem;color:#94a3b8;">Expectancy: '
                f'<b style="color:{_exp_c};">{_exp:+.2f}R</b></span>'
                f'<span style="font-size:0.7rem;color:#94a3b8;">Win Rate: '
                f'<b style="color:{_wr_c};">{_wr*100:.0f}%</b></span>'
                f'<span style="font-size:0.7rem;color:#94a3b8;">Max DD: '
                f'<b style="color:{_mdd_c};">{_mdd:.1f}R</b></span>'
                f'<span style="font-size:0.7rem;color:#94a3b8;">Streak: '
                f'<b style="color:{_sk_c};">{_sk_label}</b></span>'
                f'<span style="font-size:0.62rem;color:#475569;">{len(_sq_closed)} trades</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    # ── Market Pulse ───────────────────────────────────────────────────────────
    indices = _hero_indices()

    def _vix_sentiment(v):
        if v < 12: return "VERY CALM", "#00c896", "0,200,150"
        if v < 15: return "CALM",      "#5AD8A6", "90,216,166"
        if v < 20: return "NEUTRAL",   "#f0b429", "240,180,41"
        if v < 25: return "ELEVATED",  "#f97316", "249,115,22"
        return           "FEAR",      "#ff4d6d", "255,77,109"

    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Market Pulse</div>',
        unsafe_allow_html=True,
    )

    _pulse_items = [
        ("Nifty 50",   indices.get("Nifty 50",  {}), False),
        ("Bank Nifty", indices.get("Bank Nifty", {}), False),
        ("Sensex",     indices.get("Sensex",     {}), False),
        ("India VIX",  indices.get("VIX",        {}), True),
    ]
    pulse_cols = st.columns(4)
    for col, (label, data, is_vix) in zip(pulse_cols, _pulse_items):
        if not data:
            with col:
                st.markdown(
                    f'<div style="background:#1a1f35;border:1px solid rgba(255,255,255,0.06);'
                    f'border-radius:14px;padding:16px 18px;min-height:100px;">'
                    f'<div style="font-size:0.6rem;color:#475569;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.08em;">{label}</div>'
                    f'<div style="color:#374151;margin-top:12px;font-size:0.8rem;">—</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            continue
        price = data["price"]
        chg   = data["chg"]
        ytd   = data.get("ytd")
        arrow = "▲" if chg >= 0 else "▼"
        if is_vix:
            sent_l, sent_c, sent_rgb = _vix_sentiment(price)
            c_col = sent_c
            c_rgb = sent_rgb
            sub_html = (
                f'<div style="display:inline-block;background:{sent_c}22;color:{sent_c};'
                f'border:1px solid {sent_c}44;border-radius:5px;'
                f'padding:2px 10px;font-size:0.68rem;font-weight:700;margin-top:6px;">'
                f'{sent_l}</div>'
                f'<div style="font-size:0.67rem;color:#475569;margin-top:4px;">'
                f'{arrow} {abs(chg):.2f}% today</div>'
            )
            price_fmt = f"{price:.2f}"
        else:
            c_col = "#00c896" if chg >= 0 else "#ff4d6d"
            c_rgb = "0,200,150" if chg >= 0 else "255,77,109"
            ytd_html = ""
            if ytd is not None:
                ytd_col  = "#00c896" if ytd >= 0 else "#ff4d6d"
                ytd_html = (f'<div style="font-size:0.67rem;color:{ytd_col};margin-top:2px;">'
                            f'YTD {ytd:+.1f}%</div>')
            sub_html = (
                f'<div style="font-size:0.82rem;font-weight:700;color:{c_col};margin-top:5px;">'
                f'{arrow} {abs(chg):.2f}%</div>' + ytd_html
            )
            price_fmt = f"{price:,.0f}"
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba({c_rgb},0.2);border-top:3px solid {c_col};'
                f'border-radius:14px;padding:16px 18px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">{label}</div>'
                f'<div style="font-size:1.5rem;font-weight:800;color:#f1f5f9;'
                f'letter-spacing:-0.02em;">{price_fmt}</div>'
                + sub_html +
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Top 4 Market Catalysts ─────────────────────────────────────────────────
    _news_items = _top_news()
    if _news_items:
        st.markdown(
            '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
            '📰 Market Catalysts</div>',
            unsafe_allow_html=True,
        )
        _news_cols = st.columns(2)
        for _ni, _nitem in enumerate(_news_items):
            _ntitle   = _nitem.get("title", "")
            _nsource  = _nitem.get("source", "")
            _npub     = _nitem.get("published_str", "")
            _nurl     = _nitem.get("url", "#")
            _nsummary = _nitem.get("summary", "")[:120]
            with _news_cols[_ni % 2]:
                st.markdown(
                    f'<div style="background:linear-gradient(145deg,#131929,#0f1420);'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:12px;'
                    f'padding:12px 14px;margin-bottom:8px;">'
                    f'<a href="{_nurl}" target="_blank" style="color:#93c5fd;text-decoration:none;'
                    f'font-weight:600;font-size:0.8rem;line-height:1.45;display:block;margin-bottom:6px;">'
                    f'{_ntitle}</a>'
                    f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;">'
                    f'<span style="background:rgba(255,255,255,0.05);color:#475569;'
                    f'border-radius:4px;padding:1px 6px;font-size:0.6rem;font-weight:600;">'
                    f'{_nsource}</span>'
                    f'<span style="color:#374151;font-size:0.62rem;">{_npub}</span>'
                    f'</div>'
                    f'<div style="color:#4b5563;font-size:0.72rem;line-height:1.45;">'
                    f'{_nsummary}{"…" if len(_nitem.get("summary","")) > 120 else ""}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown(
            '<a href="/News_Sentiment" style="display:inline-flex;align-items:center;gap:5px;'
            'margin-top:4px;text-decoration:none;color:#60a5fa;font-size:0.72rem;font-weight:600;">'
            'Full AI Sentiment Analysis →</a>',
            unsafe_allow_html=True,
        )
        st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Today's Signals Feed ───────────────────────────────────────────────────
    today_sigs = _today_signals()
    _STRAT_COLORS = {
        "Trend Pullback":        "#7c83fd",
        "Volume Breakout":       "#f0b429",
        "Oversold Reversal":     "#a855f7",
        "Bullish Setup":         "#00c896",
        "Golden Cross":          "#fbbf24",
        "Supertrend Reversal":   "#06b6d4",
        "Opening Range Breakout":"#10b981",
        "VWAP Bounce":           "#f472b6",
        "EMA Crossover":         "#60a5fa",
        "Supertrend Signal":     "#8b5cf6",
    }

    if today_sigs:
        st.markdown(
            f'<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">'
            f"Today's Signals — {len(today_sigs)} ideas</div>",
            unsafe_allow_html=True,
        )
        sig_cards_html = "".join([
            f'<div style="flex-shrink:0;width:190px;background:linear-gradient(145deg,#131929,#0f1420);'
            f'border:1px solid rgba(255,255,255,0.06);'
            f'border-left:3px solid {"#00c896" if s.get("direction")=="LONG" else "#ff4d6d"};'
            f'border-radius:14px;padding:14px 16px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<span style="font-size:0.95rem;font-weight:800;color:#f1f5f9;">'
            f'{s["ticker"].replace(".NS","")}</span>'
            f'<span style="font-size:0.6rem;font-weight:700;'
            f'color:{"#00c896" if s.get("direction")=="LONG" else "#ff4d6d"};">'  
            f'{"↑ LONG" if s.get("direction")=="LONG" else "↓ SHORT"}</span>'
            f'</div>'
            f'<div style="font-size:0.65rem;color:{_STRAT_COLORS.get(s.get("strategy",""),"#6b7a99")};'
            f'font-weight:600;margin-bottom:8px;">{s.get("strategy","")}</div>'
            f'<div style="display:flex;justify-content:space-between;">'
            f'<div><div style="font-size:0.58rem;color:#374151;">Entry</div>'
            f'<div style="font-size:0.78rem;font-weight:700;color:#e2e8f0;">₹{s.get("entry_price",0):,.0f}</div></div>'
            f'<div><div style="font-size:0.58rem;color:#374151;">T1</div>'
            f'<div style="font-size:0.78rem;font-weight:700;color:#00c896;">₹{s.get("target_1",0):,.0f}</div></div>'
            f'<div><div style="font-size:0.58rem;color:#374151;">SL</div>'
            f'<div style="font-size:0.78rem;font-weight:700;color:#ff4d6d;">₹{s.get("stop_loss",0):,.0f}</div></div>'
            f'</div></div>'
            for s in today_sigs[:8]
        ])
        st.markdown(f'<div class="h-scroll">{sig_cards_html}</div>', unsafe_allow_html=True)
        st.markdown('<div style="margin-bottom:4px;"></div>', unsafe_allow_html=True)
        st.markdown(
            '<a href="/Signal_Log" style="display:inline-flex;align-items:center;gap:6px;'
            'margin-top:8px;text-decoration:none;color:#7c83fd;font-size:0.78rem;font-weight:600;">'
            'View full journal'
            '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"'
            ' stroke-width="2" stroke-linecap="round"><polyline points="7,4 13,10 7,16"/></svg>'
            '</a>',
            unsafe_allow_html=True,
        )
        st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Volume Anomalies ───────────────────────────────────────────────────────
    _va = _volume_anomalies()
    if _va:
        st.markdown(
            '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
            '⚡ Volume Anomalies — Unusual Activity</div>',
            unsafe_allow_html=True,
        )
        va_html = "".join([
            f'<div style="flex-shrink:0;width:160px;'
            f'background:linear-gradient(145deg,#131929,#0f1420);'
            f'border:1px solid rgba(255,255,255,0.06);'
            f'border-top:3px solid {"#00c896" if v["chg"] >= 0 else "#ff4d6d"};'
            f'border-radius:12px;padding:12px 14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">'
            f'<span style="font-size:0.9rem;font-weight:800;color:#f1f5f9;">{v["ticker"]}</span>'
            f'<span style="font-size:0.62rem;font-weight:700;'
            f'color:{"#00c896" if v["chg"] >= 0 else "#ff4d6d"};">'  
            f'{"▲" if v["chg"] >= 0 else "▼"} {abs(v["chg"]):.2f}%</span>'
            f'</div>'
            f'<div style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.25);'
            f'border-radius:6px;padding:4px 8px;margin-bottom:8px;text-align:center;">'
            f'<span style="color:#fbbf24;font-size:0.8rem;font-weight:800;">{v["ratio"]:.1f}×</span>'
            f'<span style="color:#92400e;font-size:0.6rem;"> avg vol</span>'
            f'</div>'
            f'<div style="color:#64748b;font-size:0.68rem;">₹{v["price"]:,.1f}</div>'
            f'</div>'
            for v in _va
        ])
        st.markdown(f'<div class="h-scroll">{va_html}</div>', unsafe_allow_html=True)
        st.markdown('<div style="margin-bottom:16px;"></div>', unsafe_allow_html=True)

    # ── Market Movers ──────────────────────────────────────────────────────────
    gainers, losers = _movers()
    if gainers or losers:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin:4px 0 12px;">Market Movers</div>',
            unsafe_allow_html=True,
        )
        g_col, l_col = st.columns(2)

        def _mover_card(items, is_gain):
            color = "#00c896" if is_gain else "#ff4d6d"
            rgb   = "0,200,150" if is_gain else "255,77,109"
            arrow = "▲" if is_gain else "▼"
            html  = (
                f'<div style="font-size:0.62rem;font-weight:700;color:{color};'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">'
                f'{arrow} {"Gainers" if is_gain else "Losers"}</div>'
            )
            for item in items:
                html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'background:rgba({rgb},0.05);border-radius:8px;padding:8px 12px;margin-bottom:5px;">'
                    f'<span style="font-weight:700;color:#e2e8f0;font-size:0.85rem;">{item["ticker"]}</span>'
                    f'<div style="text-align:right;">'
                    f'<div style="color:#64748b;font-size:0.72rem;">₹{item["price"]:,.1f}</div>'
                    f'<div style="color:{color};font-size:0.78rem;font-weight:700;">'
                    f'{arrow} {abs(item["chg"]):.2f}%</div>'
                    f'</div></div>'
                )
            return html

        with g_col:
            st.markdown(_mover_card(gainers, True), unsafe_allow_html=True)
        with l_col:
            st.markdown(_mover_card(losers, False), unsafe_allow_html=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — SIGNALS                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with t_signals:
    _qs = _quick_stats()
    _sig_items = [
        ("Today's Signals", str(_qs["today"]),  "new ideas",        "#f0b429", "240,180,41"),
        ("Open Positions",  str(_qs["open"]),   "being tracked",    "#7c83fd", "124,131,253"),
        ("Win Rate (30d)",  f'{_qs["wr"]}%',    "of closed trades", "#00c896", "0,200,150"),
        ("Total (30d)",     str(_qs["total"]),  "all signals",      "#06b6d4", "6,182,212"),
    ]
    _sc2 = st.columns(4)
    for _col2, (_lbl, _val, _sub, _c, _rgb) in zip(_sc2, _sig_items):
        with _col2:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba({_rgb},0.12);border-radius:14px;padding:16px 18px;margin-bottom:16px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">{_lbl}</div>'
                f'<div style="font-size:1.8rem;font-weight:800;color:{_c};letter-spacing:-0.03em;">{_val}</div>'
                f'<div style="font-size:0.67rem;color:#374151;margin-top:4px;">{_sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div style="font-size:0.65rem;font-weight:700;color:#374151;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">Trade Signal Tools</div>',
        unsafe_allow_html=True,
    )
    for _slug, _ico, _title, _desc, _col, _rgb in [
        ("Smart_Money",    _SVG["money"], "Smart Money",   "FII/DII flows · Bulk & block deals · Insider trades", "#f59e0b","245,158,11"),
        ("Swing_Trades",   _SVG["swing"], "Swing Trades",  "2–5 day setups · 6 strategies · entry, SL & targets","#22c55e","34,197,94"),
        ("Intraday_Ideas", _SVG["intra"], "Intraday Ideas","ORB · VWAP · EMA crossover · live during market hours","#60a5fa","96,165,250"),
        ("Signal_Log",     _SVG["log"],   "Signal Journal","Trade log · win rate · P&L · strategy performance",  "#8b5cf6","139,92,246"),
    ]:
        st.markdown(_nav_card(_slug, _ico, _title, _desc, _col, _rgb), unsafe_allow_html=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 3 — NEWS                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with t_news:
    @st.cache_data(ttl=1800, show_spinner=False)
    def _home_news():
        try:
            from data.news_fetcher import fetch_market_news
            return fetch_market_news()[:12]
        except Exception:
            return []

    st.markdown(
        '<div style="font-size:0.68rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">Latest Market News</div>',
        unsafe_allow_html=True,
    )
    headlines = _home_news()
    if headlines:
        for item in headlines:
            title   = item.get("title", "")
            source  = item.get("source", "")
            pub     = item.get("published_str", "")
            url     = item.get("url", "#")
            summary = item.get("summary", "")
            st.markdown(
                f'<div class="feed-card">'
                f'<a href="{url}" target="_blank" style="color:#93c5fd;text-decoration:none;'
                f'font-weight:600;font-size:0.875rem;line-height:1.45;">{title}</a>'
                f'<div style="display:flex;gap:8px;align-items:center;margin-top:6px;">'
                f'<span style="background:rgba(255,255,255,0.05);color:#475569;'
                f'border-radius:4px;padding:2px 8px;font-size:0.62rem;font-weight:600;">{source}</span>'
                f'<span style="color:#374151;font-size:0.68rem;">{pub}</span>'
                f'</div>'
                f'<div style="color:#374151;font-size:0.77rem;line-height:1.5;margin-top:6px;">'
                f'{summary[:160]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("News unavailable — check connection.")
    st.markdown(
        '<a href="/News_Sentiment" style="display:inline-flex;align-items:center;gap:6px;'
        'margin-top:8px;text-decoration:none;color:#60a5fa;font-size:0.78rem;font-weight:600;">'
        'Full AI Sentiment Analysis'
        '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round"><polyline points="7,4 13,10 7,16"/></svg>'
        '</a>',
        unsafe_allow_html=True,
    )

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 4 — SCREENER                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with t_screener:
    st.markdown(
        '<div style="font-size:0.65rem;font-weight:700;color:#374151;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">Stock Screeners</div>',
        unsafe_allow_html=True,
    )
    for _slug, _ico, _title, _desc, _col, _rgb in [
        ("Technical_Screener",   _SVG["tech"],  "Technical Screener",  "RSI · MACD · Golden Cross · Volume Breakout",        "#3b82f6","59,130,246"),
        ("Fundamental_Screener", _SVG["fund"],  "Fundamental Screener","PE · ROE · Debt/Equity · Dividend Yield · Margins",  "#f59e0b","245,158,11"),
        ("Market_Overview",      _SVG["globe"], "Market Overview",     "Live indices · Sector heatmap · Breadth · Movers",   "#22c55e","34,197,94"),
    ]:
        st.markdown(_nav_card(_slug, _ico, _title, _desc, _col, _rgb), unsafe_allow_html=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 5 — TOOLS                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with t_tools:
    st.markdown(
        '<div style="font-size:0.65rem;font-weight:700;color:#374151;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;">Utility Tools</div>',
        unsafe_allow_html=True,
    )
    for _slug, _ico, _title, _desc, _col, _rgb in [
        ("Tip_Analyzer",   _SVG["shield"], "Tip Analyzer",    "Score any WhatsApp/Telegram tip for pump-and-dump risk", "#ff4d6d","255,77,109"),
        ("Signal_Log",     _SVG["log"],    "Signal Journal",  "Trade log with P&L, win rate, strategy breakdown & CSV",  "#7c83fd","124,131,253"),
        ("News_Sentiment", _SVG["news"],   "News & Sentiment","AI analysis of market news, sector outlook & catalysts",  "#60a5fa","96,165,250"),
    ]:
        st.markdown(_nav_card(_slug, _ico, _title, _desc, _col, _rgb), unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="margin-top:32px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);">'
    '<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
    '<span style="color:#374151;font-size:0.72rem;">⚠️ Educational purposes only · Not financial advice</span>'
    '<span style="color:#1e2535;font-size:0.7rem;">NiftyEdge · yfinance · Claude AI · Streamlit</span>'
    '</div></div>',
    unsafe_allow_html=True,
)
