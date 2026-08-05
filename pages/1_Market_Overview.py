"""
Page 1: Market Overview
Live prices update in-place via st.fragment — no full page refresh.
"""
import datetime as _dt
import math as _math
import streamlit as st
import pandas as pd
import pytz as _pytz
import yfinance as yf


def _sf(v):
    """Safe float: returns None for NaN/Inf/None/error."""
    try:
        f = float(v)
        return None if (_math.isnan(f) or _math.isinf(f)) else f
    except Exception:
        return None


def _pct(curr, prev):
    """Safe percentage change, or None on bad input."""
    c, p = _sf(curr), _sf(prev)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / p * 100

from data.fetcher import fetch_index_data, fetch_stock_data
from data.market_status import market_status, is_market_open
from ui.charts import (
    sector_heatmap, market_breadth_gauge, ytd_performance_chart,
    sector_rotation_chart, breadth_bar_chart,
)
from config.settings import INDICES
from config.stock_universe import NIFTY_50

_IST = _pytz.timezone("Asia/Kolkata")


def _live_quote(ticker: str) -> dict:
    """One fast_info call — returns {} on any failure or NaN."""
    try:
        fi    = yf.Ticker(ticker).fast_info
        price = _sf(fi.last_price)
        prev  = _sf(fi.previous_close)
        chg   = _pct(price, prev)
        if price is None or chg is None:
            return {}
        return {"price": price, "change_pct": chg}
    except Exception:
        return {}


# ── Page shell ────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Market Overview · NiftyEdge", layout="wide", page_icon="📊")
from ui.styles import inject_global_css, page_header, show_loading, auth_guard, user_sidebar; inject_global_css()
auth_guard()

page_header("📊 Market Overview", subtitle="NSE · BSE · Live", badge="LIVE", badge_color="#00c896")

status     = market_status()
is_holiday = not status["is_trading_day"]
_is_open   = status["is_market_open"]
_is_pre    = status["is_pre_market"]
_sc        = "#00c896" if _is_open else ("#f0b429" if _is_pre else "#ff4d6d")
_rgb       = "0,200,150" if _is_open else ("240,180,41" if _is_pre else "255,77,109")
_pulse     = "animation:pulse 1.4s ease-in-out infinite;" if (_is_open or _is_pre) else ""

if is_holiday:
    st.markdown(
        '<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.2);'
        'border-left:4px solid #f0b429;border-radius:12px;padding:12px 18px;margin-bottom:20px;">'
        '<span style="color:#f0b429;font-weight:700;font-size:0.85rem;">🏖️ Market Holiday</span>'
        '<span style="color:#64748b;font-size:0.8rem;margin-left:10px;">'
        'All figures reflect the previous trading day\'s close.</span>'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div style="background:rgba({_rgb},0.06);border:1px solid rgba({_rgb},0.2);'
        f'border-radius:12px;padding:12px 18px;display:flex;align-items:center;'
        f'justify-content:space-between;margin-bottom:20px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="width:9px;height:9px;border-radius:50%;background:{_sc};flex-shrink:0;{_pulse}"></div>'
        f'<span style="color:{_sc};font-weight:700;font-size:0.9rem;">{status["status_label"]}</span>'
        f'<span style="color:#475569;font-size:0.8rem;">{status["datetime_ist"]}</span>'
        f'</div>'
        f'<span style="color:#374151;font-size:0.75rem;">'
        f'{status["market_open_time"]} – {status["market_close_time"]} IST</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Load 1Y daily history once (used for intelligence strip + YTD chart) ──────
main_indices   = {k: v for k, v in INDICES.items() if k in ["Nifty 50", "Bank Nifty", "Sensex"]}
_vix_ticker    = "^INDIAVIX"
sector_indices = {k: v for k, v in INDICES.items() if k not in main_indices}

hist_1y: dict = {}
for _name, _ticker in main_indices.items():
    _df = fetch_index_data(_ticker, period="1y", interval="1d")
    if _df is not None and not _df.empty:
        hist_1y[_name] = _df


with st.sidebar:
    user_sidebar()

# ── Global Markets (cached, refreshes every 5 min) ──────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _global_markets_data():
    items = [
        ("S&P 500",   "^GSPC",    False),
        ("Dow Jones", "^DJI",     False),
        ("Nasdaq",    "^IXIC",    False),
        ("Crude Oil", "CL=F",     True),
        ("Gold",      "GC=F",     True),
        ("USD/INR",   "USDINR=X", True),
    ]
    results = []
    for label, ticker, is_commodity in items:
        try:
            df = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
            if df is None or len(df) < 2:
                continue
            price = _sf(df["Close"].iloc[-1])
            prev  = _sf(df["Close"].iloc[-2])
            chg   = _pct(price, prev)
            if price is None or chg is None:
                continue
            results.append({"label": label, "price": price, "chg": chg, "is_commodity": is_commodity})
        except Exception:
            continue
    return results

_gm_slot = show_loading("Fetching global markets — S&amp;P 500, Dow, Nasdaq, Crude, Gold, USD/INR…", "#7c83fd")
_gm = _global_markets_data()
_gm_slot.empty()
if _gm:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">Global Markets</div>',
        unsafe_allow_html=True,
    )
    gm_html = '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:20px;">'
    for item in _gm:
        chg   = item["chg"]
        c     = "#00c896" if chg >= 0 else "#ff4d6d"
        rgb   = "0,200,150" if chg >= 0 else "255,77,109"
        arrow = "▲" if chg >= 0 else "▼"
        price = item["price"]
        price_fmt = f"${price:,.0f}" if not item["is_commodity"] else f"{price:,.2f}"
        gm_html += (
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba({rgb},0.15);border-radius:12px;padding:12px 14px;">'
            f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:6px;">{item["label"]}</div>'
            f'<div style="font-size:1rem;font-weight:700;color:#e2e8f0;">{price_fmt}</div>'
            f'<div style="font-size:0.75rem;font-weight:700;color:{c};margin-top:3px;">'
            f'{arrow} {abs(chg):.2f}%</div>'
            f'</div>'
        )
    gm_html += '</div>'
    st.markdown(gm_html, unsafe_allow_html=True)

st.divider()

# ── Fragment 1: major index cards — refreshes every 2 min during market ──────────
_fast_interval = 120 if status["is_market_open"] else None


@st.fragment(run_every=_fast_interval)
def _index_metrics():
    _live = is_market_open()
    st.subheader("Major Indices")
    cols = st.columns(len(main_indices) + 1)  # +1 for VIX

    for col, (name, ticker) in zip(cols, main_indices.items()):
        df = hist_1y.get(name)
        if df is None or len(df) < 2:
            with col:
                st.warning(f"{name}: No data")
            continue

        if _live:
            q       = _live_quote(ticker)
            curr    = _sf(q.get("price")) or _sf(df["Close"].iloc[-1])
            day_chg = _sf(q.get("change_pct"))
            as_of   = "Live"
        else:
            curr    = _sf(df["Close"].iloc[-1])
            day_chg = _pct(curr, df["Close"].iloc[-2])
            as_of   = str(df.index[-1])[:10]

        if curr is None:
            continue
        if day_chg is None:
            day_chg = 0.0

        jan1    = _dt.date(df.index[-1].year, 1, 1)
        ytd_df  = df[df.index.date >= jan1]
        ytd_base = _sf(ytd_df["Close"].iloc[0]) if not ytd_df.empty else None
        ytd_pct  = _pct(curr, ytd_base) if ytd_base else None

        day_arrow = "▲" if day_chg >= 0 else "▼"
        day_color = "#00c896" if day_chg >= 0 else "#ff4d6d"
        ytd_color = "#00c896" if (ytd_pct is None or ytd_pct >= 0) else "#ff4d6d"
        ytd_label = f"YTD {ytd_pct:+.2f}%" if ytd_pct is not None else ""

        with col:
            st.markdown(
                f'<div style="background:#1e2235;border-radius:12px;padding:16px 20px;'
                f'border:1px solid rgba(255,255,255,0.07);margin-bottom:8px;">'
                f'<div style="font-size:0.75rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{name}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;'
                f'letter-spacing:-0.02em;">{curr:,.2f}</div>'
                f'<div style="display:flex;gap:12px;margin-top:6px;align-items:center;">'
                f'<span style="font-size:0.9rem;font-weight:700;color:{day_color};">'
                f'{day_arrow} {abs(day_chg):.2f}% today</span>'
                + (f'<span style="font-size:0.8rem;color:{ytd_color};opacity:0.85;">'
                   f'{ytd_label}</span>' if ytd_label else '')
                + f'</div>'
                f'<div style="font-size:0.72rem;color:#6b7a99;margin-top:4px;">{as_of}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # VIX card (last column)
    with cols[-1]:
        try:
            vix_df = fetch_index_data(_vix_ticker, period="5d", interval="1d")
            if vix_df is not None and len(vix_df) >= 2:
                v      = _sf(vix_df["Close"].iloc[-1])
                v_prev = _sf(vix_df["Close"].iloc[-2])
                v_chg  = _pct(v, v_prev)
                if v is None or v_chg is None:
                    raise ValueError("VIX NaN")
                v_arr  = "▲" if v_chg >= 0 else "▼"
                if v < 12:   sent, s_col = "VERY CALM", "#00c896"
                elif v < 15: sent, s_col = "CALM",      "#5AD8A6"
                elif v < 20: sent, s_col = "NEUTRAL",   "#f0b429"
                elif v < 25: sent, s_col = "ELEVATED",  "#f97316"
                else:        sent, s_col = "FEAR",      "#ff4d6d"
                st.markdown(
                    f'<div style="background:#1e2235;border-radius:12px;padding:16px 20px;'
                    f'border:1px solid rgba(255,255,255,0.07);border-top:3px solid {s_col};'
                    f'margin-bottom:8px;">'
                    f'<div style="font-size:0.75rem;color:#6b7a99;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">India VIX</div>'
                    f'<div style="font-size:1.6rem;font-weight:800;color:#e2e8f0;'
                    f'letter-spacing:-0.02em;">{v:.2f}</div>'
                    f'<div style="margin-top:6px;">'
                    f'<span style="background:{s_col}22;color:{s_col};border:1px solid {s_col}44;'
                    f'border-radius:5px;padding:2px 10px;font-size:0.72rem;font-weight:700;">'
                    f'{sent}</span>'
                    f'<span style="font-size:0.8rem;color:{"#00c896" if v_chg>=0 else "#ff4d6d"};'
                    f'font-weight:700;margin-left:8px;">{v_arr} {abs(v_chg):.2f}%</span>'
                    f'</div>'
                    f'<div style="font-size:0.72rem;color:#6b7a99;margin-top:4px;">'
                    f'{"Live" if _live else str(vix_df.index[-1])[:10]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="background:#1e2235;border-radius:12px;padding:16px 20px;'
                    'border:1px solid rgba(255,255,255,0.07);margin-bottom:8px;">'
                    '<div style="font-size:0.75rem;color:#6b7a99;font-weight:700;'
                    'text-transform:uppercase;letter-spacing:0.08em;">India VIX</div>'
                    '<div style="color:#374151;margin-top:12px;">Unavailable</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

    if _live:
        _ts = _dt.datetime.now(_IST).strftime("%H:%M:%S")
        st.caption(f"↻ {_ts} IST · updates every 2 min")


_index_metrics()

# ── Market Intelligence Strip — derived from hist_1y + _gm (no extra fetches) ──
def _intel_card(label: str, value: str, sub: str, color: str) -> str:
    _rgb_map = {
        "#00c896": "0,200,150",   "#ff4d6d": "255,77,109",
        "#f0b429": "240,180,41",  "#f97316": "249,115,22",
        "#94a3b8": "148,163,184",
    }
    rgb = _rgb_map.get(color, "148,163,184")
    return (
        f'<div style="background:rgba({rgb},0.06);border:1px solid rgba({rgb},0.15);'
        f'border-top:2px solid {color};border-radius:10px;padding:10px 14px;">'
        f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:5px;">{label}</div>'
        f'<div style="font-size:0.92rem;font-weight:800;color:{color};">{value}</div>'
        f'<div style="font-size:0.65rem;color:#475569;margin-top:2px;">{sub}</div>'
        f'</div>'
    )

_cards = []
_n50 = hist_1y.get("Nifty 50")
_bnk = hist_1y.get("Bank Nifty")

if _n50 is not None and len(_n50) >= 50:
    _c   = _sf(_n50["Close"].iloc[-1])
    _s20 = _sf(_n50["Close"].rolling(20).mean().iloc[-1])
    _s50 = _sf(_n50["Close"].rolling(50).mean().iloc[-1])
    if _c and _s20 and _s50:
        _col = "#00c896" if _c > _s20 else "#ff4d6d"
        _s20_pct = _pct(_c, _s20)
        _s50_pct = _pct(_c, _s50)
        _sub = ""
        if _s20_pct is not None:
            _sub += f"vs SMA20 {_s20_pct:+.1f}%"
        if _s50_pct is not None:
            _sub += f" · SMA50 {_s50_pct:+.1f}%"
        _cards.append(_intel_card(
            "Nifty Trend",
            "BULLISH" if _c > _s20 else "BEARISH",
            _sub or "SMA data unavailable",
            _col,
        ))
    if _c:
        _h52 = _sf(_n50["Close"].max())
        _l52 = _sf(_n50["Close"].min())
        if _h52 and _l52 and _h52 != _l52:
            _pos  = (_c - _l52) / (_h52 - _l52) * 100
            _pc   = "#00c896" if _pos > 65 else "#f0b429" if _pos > 40 else "#ff4d6d"
            _from_high = _pct(_c, _h52)
            _fh_str = f"From 52W high: {_from_high:.1f}%" if _from_high is not None else ""
            _cards.append(_intel_card("Nifty 52W Range", f"{_pos:.0f}% of range", _fh_str, _pc))
    if _c and len(_n50) >= 22:
        _ret1m = _pct(_c, _n50["Close"].iloc[-22])
        if _ret1m is not None:
            _cards.append(_intel_card(
                "Nifty 1M Return", f"{_ret1m:+.2f}%", "rolling 1-month return",
                "#00c896" if _ret1m >= 0 else "#ff4d6d",
            ))

if _bnk is not None and len(_bnk) >= 20:
    _bc   = _sf(_bnk["Close"].iloc[-1])
    _bs20 = _sf(_bnk["Close"].rolling(20).mean().iloc[-1])
    if _bc and _bs20:
        _bdc   = "#00c896" if _bc > _bs20 else "#ff4d6d"
        _bs_pct = _pct(_bc, _bs20)
        _bsub   = f"vs SMA20 {_bs_pct:+.1f}%" if _bs_pct is not None else ""
        _cards.append(_intel_card(
            "Bank Nifty", "BULLISH" if _bc > _bs20 else "BEARISH",
            _bsub, _bdc,
        ))

_sp = next((x for x in _gm if x["label"] == "S&P 500"), None)
if _sp and _sf(_sp.get("chg")) is not None:
    _sp_chg = _sf(_sp["chg"])
    _cards.append(_intel_card(
        "S&P 500 Cue", f"{_sp_chg:+.2f}%", "yesterday's US close",
        "#00c896" if _sp_chg >= 0 else "#ff4d6d",
    ))

_crude = next((x for x in _gm if x["label"] == "Crude Oil"), None)
if _crude and _sf(_crude.get("chg")) is not None:
    _cr_chg = _sf(_crude["chg"])
    _crc = "#ff4d6d" if _cr_chg > 1 else "#00c896" if _cr_chg < -1 else "#f0b429"
    _cards.append(_intel_card(
        "Crude Oil", f"${_crude['price']:.0f}",
        f"{_cr_chg:+.2f}% · {'↑ cost pressure' if _cr_chg > 0 else '↓ relief'}",
        _crc,
    ))

if _cards:
    st.markdown(
        f'<div style="font-size:0.7rem;font-weight:700;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin:16px 0 8px;">Market Intelligence</div>'
        f'<div style="display:grid;grid-template-columns:repeat({len(_cards)},1fr);'
        f'gap:10px;margin-bottom:20px;">'
        + "".join(_cards)
        + '</div>',
        unsafe_allow_html=True,
    )

# ── Static: YTD chart ────────────────────────────────────────────────────────────────────────────
if hist_1y:
    st.markdown("#### Index Performance Comparison")
    try:
        st.plotly_chart(ytd_performance_chart(hist_1y), use_container_width=True, key="ytd_chart")
    except Exception:
        st.info("Chart temporarily unavailable.")

st.divider()

# ── Cached helpers for breadth + rotation (expensive — TTL keeps them fresh) ──

@st.cache_data(ttl=3600, show_spinner=False)
def _nifty_breadth_range_data():
    """Batch-fetch 1Y daily for Nifty 50; compute 52W ranges, SMA%, volume ratios."""
    tickers = list(NIFTY_50.values())
    try:
        raw = yf.download(
            tickers, period="1y", interval="1d",
            auto_adjust=True, progress=False, timeout=30, group_by="ticker",
        )
    except Exception:
        return None
    if raw is None or raw.empty:
        return None

    sma20_n = sma50_n = sma200_n = total_n = highs_52w = lows_52w = 0
    stocks = []
    top_lvl = raw.columns.get_level_values(0).unique().tolist() if isinstance(raw.columns, pd.MultiIndex) else []

    for t in tickers:
        try:
            if t in top_lvl:
                close  = raw[t]["Close"].dropna()
                volume = raw[t]["Volume"].dropna()
            else:
                continue
            if len(close) < 20:
                continue
            curr  = float(close.iloc[-1])
            h52   = float(close.max())
            l52   = float(close.min())
            pos   = (curr - l52) / (h52 - l52) * 100 if h52 != l52 else 50.0
            from_h = (curr - h52) / h52 * 100

            sma20  = float(close.rolling(20).mean().iloc[-1])  if len(close) >= 20  else None
            sma50  = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50  else None
            sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

            total_n += 1
            if sma20  and curr > sma20:  sma20_n  += 1
            if sma50  and curr > sma50:  sma50_n  += 1
            if sma200 and curr > sma200: sma200_n += 1
            if pos >= 90: highs_52w += 1
            if pos <= 10: lows_52w  += 1

            vol_now = float(volume.iloc[-1]) if not volume.empty else 0.0
            vol_avg = (
                float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20
                else float(volume.mean()) if not volume.empty else 1.0
            )
            vol_r = vol_now / vol_avg if vol_avg > 0 else 1.0

            stocks.append({
                "sym": t.replace(".NS", ""), "ticker": t,
                "price": round(curr, 2), "h52": round(h52, 2), "l52": round(l52, 2),
                "pos": round(pos, 1), "from_h": round(from_h, 1),
                "vol_ratio": round(vol_r, 2),
            })
        except Exception:
            continue

    if not stocks:
        return None
    return {
        "stocks": sorted(stocks, key=lambda x: x["pos"], reverse=True),
        "sma_pcts": {
            "sma20":  sma20_n  / total_n * 100 if total_n else 0.0,
            "sma50":  sma50_n  / total_n * 100 if total_n else 0.0,
            "sma200": sma200_n / total_n * 100 if total_n else 0.0,
        },
        "highs_52w": highs_52w,
        "lows_52w":  lows_52w,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def _sector_rotation_data():
    """Compute relative strength + momentum for each sector vs Nifty 50 (3M window)."""
    _main = {"Nifty 50", "Bank Nifty", "Sensex"}
    _sectors = {k: v for k, v in INDICES.items() if k not in _main}
    try:
        n_df = yf.Ticker("^NSEI").history(period="3mo", interval="1d", auto_adjust=True)
        if n_df is None or len(n_df) < 22:
            return []
        n_curr  = float(n_df["Close"].iloc[-1])
        n_1m    = (n_curr / float(n_df["Close"].iloc[-22]) - 1) * 100
        n_3m    = (n_curr / float(n_df["Close"].iloc[0])   - 1) * 100
        n_3m_avg = n_3m / 3
    except Exception:
        return []

    results = []
    for name, ticker in _sectors.items():
        try:
            df = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=True)
            if df is None or len(df) < 22:
                continue
            s_curr   = float(df["Close"].iloc[-1])
            s_1m     = (s_curr / float(df["Close"].iloc[-22]) - 1) * 100
            s_3m     = (s_curr / float(df["Close"].iloc[0])   - 1) * 100
            s_3m_avg = s_3m / max(len(df) / 22, 1)
            results.append({
                "sector":   name,
                "rs":       round(s_1m - n_1m, 2),
                "momentum": round(s_1m - s_3m_avg, 2),
            })
        except Exception:
            continue
    return results


# ── Fragment 2: sector tiles + heatmap + breadth + rotation + movers ────────────
_slow_interval = 120 if status["is_market_open"] else None


@st.fragment(run_every=_slow_interval)
def _market_data():
    _live = is_market_open()

    # ── Sector tiles ───────────────────────────────────────────────────────────────────────
    st.subheader("Sector Performance")
    sector_data = []
    s_cols = st.columns(min(len(sector_indices), 4))

    for i, (name, ticker) in enumerate(sector_indices.items()):
        df = fetch_index_data(ticker, period="5d", interval="1d")
        if df is None or len(df) < 2:
            continue
        if _live:
            q    = _live_quote(ticker)
            curr = _sf(q.get("price")) or _sf(df["Close"].iloc[-1])
            chg  = _sf(q.get("change_pct")) or 0.0
        else:
            curr = _sf(df["Close"].iloc[-1])
            chg  = _pct(curr, df["Close"].iloc[-2]) or 0.0
        if curr is None:
            continue
        sector_data.append({"sector": name, "change_pct": chg, "market_cap": abs(curr)})
        arrow  = "▲" if chg >= 0 else "▼"
        color  = "#00c896" if chg >= 0 else "#ff4d6d"
        bg     = "rgba(0,200,150,0.07)" if chg >= 0 else "rgba(255,77,109,0.07)"
        border = "rgba(0,200,150,0.2)"  if chg >= 0 else "rgba(255,77,109,0.2)"
        short  = name.replace("Nifty ", "").replace("Nifty", "")
        with s_cols[i % 4]:
            st.markdown(
                f'<div style="background:{bg};border:1px solid {border};border-radius:12px;'
                f'padding:12px 14px;margin:4px 0;border-top:3px solid {color};">'
                f'<div style="color:#64748b;font-size:0.67rem;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:6px;">{short}</div>'
                f'<div style="color:#e2e8f0;font-size:1rem;font-weight:700;'
                f'letter-spacing:-0.01em;margin-bottom:4px;">{curr:,.0f}</div>'
                f'<div style="color:{color};font-size:0.82rem;font-weight:700;">'
                f'{arrow} {abs(chg):.2f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if not sector_data:
        return

    st.divider()

    # ── Fetch Nifty 50 prices (reused for breadth AND movers) ─────────────────────
    nifty_tickers = list(NIFTY_50.values())
    if _live:
        price_data = fetch_stock_data(nifty_tickers, period="2d", interval="5m", use_cache=True)
    else:
        price_data = fetch_stock_data(nifty_tickers, period="5d", interval="1d")

    # ── Compute advances / declines + changes list ─────────────────────────────
    advances = declines = 0
    changes  = []
    for t, df in price_data.items():
        if df is None or df.empty:
            continue
        try:
            if _live:
                df       = df.dropna(subset=["Close"])
                today    = df.index[-1].date()
                today_df = df[df.index.date == today]
                prev_df  = df[df.index.date < today]
                if today_df.empty or prev_df.empty:
                    continue
                curr_p = _sf(today_df["Close"].iloc[-1])
                prev_p = _sf(prev_df["Close"].iloc[-1])
            else:
                if len(df) < 2:
                    continue
                curr_p = _sf(df["Close"].iloc[-1])
                prev_p = _sf(df["Close"].iloc[-2])
            if curr_p is None or prev_p is None:
                continue
            chg_pct = _pct(curr_p, prev_p)
            if chg_pct is None:
                continue
            chg = curr_p - prev_p
            advances += (1 if chg > 0 else 0)
            declines += (1 if chg < 0 else 0)
            changes.append({"ticker": t, "price": curr_p, "change_pct": chg_pct})
        except Exception:
            continue

    # ── Heatmap + Breadth ────────────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Sector Heatmap")
        try:
            st.plotly_chart(sector_heatmap(sector_data), use_container_width=True, key="sector_heatmap")
        except Exception:
            pass

    with c2:
        st.subheader("Market Breadth")
        _bd = _nifty_breadth_range_data()
        if _bd:
            sp = _bd["sma_pcts"]
            try:
                st.plotly_chart(
                    breadth_bar_chart(
                        sp["sma20"], sp["sma50"], sp["sma200"],
                        _bd["highs_52w"], _bd["lows_52w"],
                    ),
                    use_container_width=True, key="breadth_bar",
                )
            except Exception:
                try:
                    st.plotly_chart(
                        market_breadth_gauge(advances, declines),
                        use_container_width=True, key="breadth_gauge_fb",
                    )
                except Exception:
                    pass
        else:
            try:
                st.plotly_chart(
                    market_breadth_gauge(advances, declines),
                    use_container_width=True, key="breadth_gauge",
                )
            except Exception:
                pass
        st.caption(f"A/D: {advances} advancing · {declines} declining (today)")

    st.divider()

    # ── Sector Rotation Quadrant ──────────────────────────────────────────────────────────────
    rot_data = _sector_rotation_data()
    if rot_data:
        st.subheader("Sector Rotation")
        st.caption(
            "X-axis: sector 1M return vs Nifty (positive = outperforming) · "
            "Y-axis: 1M return vs 3M monthly avg (positive = accelerating momentum)"
        )
        try:
            st.plotly_chart(
                sector_rotation_chart(rot_data),
                use_container_width=True, key="sector_rotation",
            )
        except Exception:
            pass
        st.divider()

    # ── Top Gainers / Losers ─────────────────────────────────────────────────────────────────
    st.subheader("Top Gainers & Losers (Nifty 50)")

    def _mover_row(ticker, price, chg, is_gain):
        sym   = ticker.replace(".NS", "")
        color = "#00c896" if is_gain else "#ff4d6d"
        bg    = "rgba(0,200,150,0.06)" if is_gain else "rgba(255,77,109,0.06)"
        arrow = "▲" if is_gain else "▼"
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:9px 12px;margin:4px 0;background:{bg};border-radius:8px;">'
            f'<span style="font-weight:700;color:#e2e8f0;font-size:0.9rem;">{sym}</span>'
            f'<div style="text-align:right;">'
            f'<div style="color:#94a3b8;font-size:0.78rem;font-weight:500;">₹{price:,.2f}</div>'
            f'<div style="color:{color};font-size:0.8rem;font-weight:700;">{arrow} {abs(chg):.2f}%</div>'
            f'</div>'
            f'</div>'
        )

    g_col, l_col = st.columns(2)
    if changes:
        df_ch   = pd.DataFrame(changes).sort_values("change_pct", ascending=False)
        gainers = df_ch.head(5).to_dict("records")
        losers  = df_ch.tail(5).to_dict("records")
    else:
        gainers, losers = [], []

    with g_col:
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
            'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">▲ Top Gainers</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(_mover_row(i["ticker"], i["price"], i["change_pct"], True) for i in gainers),
            unsafe_allow_html=True,
        )

    with l_col:
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
            'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">▼ Top Losers</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(_mover_row(i["ticker"], i["price"], i["change_pct"], False) for i in losers),
            unsafe_allow_html=True,
        )

    if _live:
        _ts = _dt.datetime.now(_IST).strftime("%H:%M:%S")
        st.caption(f"↻ {_ts} IST · updates every 2 min")


_market_data()

# ── Nifty 50 — 52-Week Range Map + Volume Anomalies ──────────────────────────────
_bd_slot = show_loading("Computing 52-week ranges and SMA positions for all Nifty 50 stocks…", "#f0b429")
_bd_data = _nifty_breadth_range_data()
_bd_slot.empty()
if _bd_data and _bd_data.get("stocks"):
    st.divider()
    st.subheader("Nifty 50 — 52-Week Range Map")
    st.caption(
        "Each bar shows where the current price sits between the 52W low (left) "
        "and 52W high (right). Sorted strongest → weakest."
    )

    stocks  = _bd_data["stocks"]
    N_COLS  = 5
    for row_start in range(0, len(stocks), N_COLS):
        row_stocks = stocks[row_start: row_start + N_COLS]
        rcols = st.columns(N_COLS)
        for col, s in zip(rcols, row_stocks):
            pos     = s["pos"]
            bar_col = "#00c896" if pos > 65 else "#f0b429" if pos > 40 else "#ff4d6d"
            with col:
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.02);'
                    f'border:1px solid rgba(255,255,255,0.06);border-radius:8px;'
                    f'padding:8px 10px;margin:2px 0;">'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;margin-bottom:4px;">'
                    f'<span style="font-size:0.75rem;font-weight:700;color:#e2e8f0;">{s["sym"]}</span>'
                    f'<span style="font-size:0.65rem;color:{bar_col};font-weight:700;">{pos:.0f}%</span>'
                    f'</div>'
                    f'<div style="background:rgba(255,255,255,0.07);border-radius:3px;'
                    f'height:5px;margin-bottom:4px;">'
                    f'<div style="width:{pos:.0f}%;height:100%;background:{bar_col};'
                    f'border-radius:3px;"></div></div>'
                    f'<div style="display:flex;justify-content:space-between;">'
                    f'<span style="font-size:0.58rem;color:#374151;">₹{s["l52"]:,.0f}</span>'
                    f'<span style="font-size:0.58rem;color:#374151;">₹{s["h52"]:,.0f}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Volume Anomalies ───────────────────────────────────────────────────────────────────────
    anomalies = sorted(
        [s for s in stocks if s["vol_ratio"] >= 2.0],
        key=lambda x: x["vol_ratio"], reverse=True,
    )[:12]

    if anomalies:
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;color:#64748b;'
            'text-transform:uppercase;letter-spacing:0.08em;margin:20px 0 6px;">'
            '🔊 Volume Anomalies</div>'
            '<div style="font-size:0.7rem;color:#475569;margin-bottom:10px;">'
            'Stocks at ≥ 2× their 20-day average volume — potential breakout or breakdown</div>',
            unsafe_allow_html=True,
        )
        va_html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">'
        for s in anomalies:
            pos = s["pos"]
            vc  = "#00c896" if pos > 65 else "#f0b429" if pos > 40 else "#ff4d6d"
            va_html += (
                f'<div style="background:rgba(240,180,41,0.04);'
                f'border:1px solid rgba(240,180,41,0.12);border-left:3px solid #f0b429;'
                f'border-radius:8px;padding:10px 12px;">'
                f'<div style="font-size:0.82rem;font-weight:700;color:#e2e8f0;margin-bottom:4px;">'
                f'{s["sym"]}</div>'
                f'<div style="font-size:0.75rem;color:#f0b429;font-weight:600;">'
                f'↑ {s["vol_ratio"]:.1f}× avg volume</div>'
                f'<div style="font-size:0.65rem;color:{vc};margin-top:2px;">'
                f'{pos:.0f}% of 52W range</div>'
                f'</div>'
            )
        va_html += '</div>'
        st.markdown(va_html, unsafe_allow_html=True)
    else:
        st.caption("No unusual volume spikes — all stocks within 2× their 20-day average.")
