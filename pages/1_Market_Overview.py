"""
Page 1: Market Overview — rebuilt with 52W ranges, sector rotation, breadth bars, volume anomalies.
"""
import datetime as _dt
import streamlit as st
import pandas as pd
import pytz as _pytz
import yfinance as yf

from data.fetcher import fetch_index_data, fetch_stock_data
from data.market_status import market_status, is_market_open
from ui.charts import (
    sector_heatmap, market_breadth_gauge, ytd_performance_chart,
    sector_rotation_chart, breadth_bar_chart,
)
from config.settings import INDICES
from config.stock_universe import NIFTY_50

_IST = _pytz.timezone("Asia/Kolkata")

st.set_page_config(page_title="Market Overview · ShareSaathi", layout="wide", page_icon="📊")
from ui.styles import inject_global_css; inject_global_css()

status     = market_status()
_is_open   = status["is_market_open"]
_is_pre    = status["is_pre_market"]
is_holiday = not status["is_trading_day"]
_sc        = "#00c896" if _is_open else ("#f0b429" if _is_pre else "#ff4d6d")
_rgb       = "0,200,150" if _is_open else ("240,180,41" if _is_pre else "255,77,109")
_pulse     = "animation:pulse 1.4s ease-in-out infinite;" if (_is_open or _is_pre) else ""
_now       = _dt.datetime.now(_IST).strftime("%H:%M IST")

st.markdown(
    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0 18px;">'
    f'<div><div style="font-size:1.4rem;font-weight:900;letter-spacing:-0.03em;color:#f1f5f9;">Market Overview</div>'
    f'<div style="font-size:0.72rem;color:#475569;margin-top:2px;">NSE · BSE · Nifty 50</div></div>'
    f'<div style="display:flex;align-items:center;gap:8px;">'
    f'<div style="display:inline-flex;align-items:center;gap:6px;background:rgba({_rgb},0.1);'
    f'border:1px solid rgba({_rgb},0.25);border-radius:20px;padding:5px 12px;">'
    f'<div style="width:7px;height:7px;border-radius:50%;background:{_sc};{_pulse}flex-shrink:0;"></div>'
    f'<span style="color:{_sc};font-size:0.72rem;font-weight:700;">'
    f'{status["status_label"].split("(")[0].strip()}</span></div>'
    f'<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);'
    f'border-radius:20px;padding:5px 12px;font-size:0.72rem;color:#475569;">{_now}</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)

if is_holiday:
    st.markdown(
        '<div style="background:rgba(240,180,41,0.06);border:1px solid rgba(240,180,41,0.2);'
        'border-left:4px solid #f0b429;border-radius:12px;padding:10px 16px;margin-bottom:16px;">'
        '<span style="color:#f0b429;font-weight:700;font-size:0.82rem;">🏖️ Market Holiday</span>'
        '<span style="color:#64748b;font-size:0.78rem;margin-left:10px;">'
        "Figures reflect the previous trading day's close.</span></div>",
        unsafe_allow_html=True,
    )

_main_indices   = {k: v for k, v in INDICES.items() if k in ["Nifty 50", "Bank Nifty", "Sensex"]}
_sector_indices = {k: v for k, v in INDICES.items() if k not in _main_indices}
_vix_ticker     = "^INDIAVIX"

hist_1y: dict = {}
for _name, _ticker in _main_indices.items():
    _df = fetch_index_data(_ticker, period="1y", interval="1d")
    if _df is not None and not _df.empty:
        hist_1y[_name] = _df

# ── Global Markets ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _global_markets():
    items = [
        ("S&P 500",   "^GSPC",    "$"), ("Nasdaq",    "^IXIC",    "$"),
        ("Dow Jones", "^DJI",     "$"), ("Crude Oil", "CL=F",     "$"),
        ("Gold",      "GC=F",     "$"), ("USD/INR",   "USDINR=X", "₹"),
    ]
    out = []
    for label, ticker, sym in items:
        try:
            df = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
            if df is None or len(df) < 2:
                continue
            price = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2])
            out.append({"label": label, "price": price, "chg": (price-prev)/prev*100, "sym": sym})
        except Exception:
            continue
    return out

_gm = _global_markets()
if _gm:
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Global Markets</div>',
        unsafe_allow_html=True,
    )
    for col, item in zip(st.columns(len(_gm)), _gm):
        chg = item["chg"]
        c   = "#00c896" if chg >= 0 else "#ff4d6d"
        rgb = "0,200,150" if chg >= 0 else "255,77,109"
        p   = item["price"]
        fmt = f"{item['sym']}{p:,.0f}" if item["sym"] == "$" else f"{item['sym']}{p:,.2f}"
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba({rgb},0.12);border-radius:12px;padding:12px 14px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{item["label"]}</div>'
                f'<div style="font-size:0.95rem;font-weight:700;color:#e2e8f0;">{fmt}</div>'
                f'<div style="font-size:0.72rem;font-weight:700;color:{c};margin-top:3px;">'
                f'{"▲" if chg>=0 else "▼"} {abs(chg):.2f}%</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── Fragment 1: Major indices + VIX ───────────────────────────────────────────
_fast_iv = 120 if _is_open else None

def _live_q(ticker):
    try:
        fi = yf.Ticker(ticker).fast_info
        p  = float(fi.last_price); pc = float(fi.previous_close)
        return {"price": p, "chg": (p-pc)/pc*100}
    except Exception:
        return {}

@st.fragment(run_every=_fast_iv)
def _index_section():
    _live = is_market_open()
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Major Indices</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    for col, (name, ticker) in zip(cols[:3], _main_indices.items()):
        df = hist_1y.get(name)
        if df is None or len(df) < 2:
            continue
        if _live:
            q = _live_q(ticker); curr = q.get("price", float(df["Close"].iloc[-1])); day_chg = q.get("chg", 0.0); as_of = "Live"
        else:
            curr = float(df["Close"].iloc[-1]); day_chg = (curr - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100; as_of = str(df.index[-1])[:10]
        jan1 = _dt.date(df.index[-1].year, 1, 1)
        ytd_df = df[df.index.date >= jan1]
        ytd_pct = ((curr - float(ytd_df["Close"].iloc[0])) / float(ytd_df["Close"].iloc[0]) * 100) if not ytd_df.empty else None
        c = "#00c896" if day_chg >= 0 else "#ff4d6d"; rgb = "0,200,150" if day_chg >= 0 else "255,77,109"
        ytd_c = "#00c896" if (ytd_pct is None or ytd_pct >= 0) else "#ff4d6d"
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba({rgb},0.18);border-top:3px solid {c};border-radius:14px;padding:16px 18px;">'
                f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.08em;margin-bottom:8px;">{name}</div>'
                f'<div style="font-size:1.6rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">{curr:,.0f}</div>'
                f'<div style="font-size:0.82rem;font-weight:700;color:{c};margin-top:5px;">{"▲" if day_chg>=0 else "▼"} {abs(day_chg):.2f}%</div>'
                + (f'<div style="font-size:0.68rem;color:{ytd_c};margin-top:2px;">YTD {ytd_pct:+.1f}%</div>' if ytd_pct is not None else '')
                + f'<div style="font-size:0.62rem;color:#374151;margin-top:4px;">{as_of}</div></div>',
                unsafe_allow_html=True,
            )
    with cols[3]:
        try:
            vix_df = fetch_index_data(_vix_ticker, period="5d", interval="1d")
            if vix_df is not None and len(vix_df) >= 2:
                v = float(vix_df["Close"].iloc[-1]); vp = float(vix_df["Close"].iloc[-2])
                vc = (v-vp)/vp*100
                if v < 12:   sent, sc = "VERY CALM", "#00c896"
                elif v < 15: sent, sc = "CALM",      "#5AD8A6"
                elif v < 20: sent, sc = "NEUTRAL",   "#f0b429"
                elif v < 25: sent, sc = "ELEVATED",  "#f97316"
                else:        sent, sc = "FEAR",      "#ff4d6d"
                st.markdown(
                    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                    f'border:1px solid rgba(255,255,255,0.07);border-top:3px solid {sc};border-radius:14px;padding:16px 18px;">'
                    f'<div style="font-size:0.6rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
                    f'letter-spacing:0.08em;margin-bottom:8px;">India VIX</div>'
                    f'<div style="font-size:1.6rem;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">{v:.2f}</div>'
                    f'<div style="margin-top:5px;"><span style="background:{sc}22;color:{sc};border:1px solid {sc}44;'
                    f'border-radius:5px;padding:2px 8px;font-size:0.68rem;font-weight:700;">{sent}</span>'
                    f'<span style="font-size:0.78rem;color:{"#ff4d6d" if vc>=0 else "#00c896"};'
                    f'font-weight:700;margin-left:8px;">{"▲" if vc>=0 else "▼"} {abs(vc):.2f}%</span></div></div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass
    if _live:
        st.caption(f"↻ {_dt.datetime.now(_IST).strftime('%H:%M:%S')} IST · auto-updates every 2 min")

_index_section()

if hist_1y:
    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
    try:
        st.plotly_chart(ytd_performance_chart(hist_1y), use_container_width=True, key="ytd_chart")
    except Exception:
        pass

st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

# ── Fragment 2: Nifty 50 deep-dive ────────────────────────────────────────────
_slow_iv = 120 if _is_open else None

@st.fragment(run_every=_slow_iv)
def _nifty50_section():
    _live = is_market_open()
    nifty_tickers = list(NIFTY_50.values())

    @st.cache_data(ttl=3600)
    def _nifty50_1y():
        return fetch_stock_data(nifty_tickers, period="1y", interval="1d")

    hist = _nifty50_1y()
    live_data = fetch_stock_data(nifty_tickers, period="2d", interval="5m", use_cache=True) if _live else hist

    stocks = []
    for t in nifty_tickers:
        df1y = hist.get(t)
        if df1y is None or len(df1y) < 20:
            continue
        try:
            hi52      = float(df1y["High"].max())
            lo52      = float(df1y["Low"].min())
            vol_avg20 = float(df1y["Volume"].tail(20).mean())
            if _live:
                ldf = live_data.get(t)
                if ldf is not None and not ldf.empty:
                    ldf = ldf.dropna(subset=["Close"])
                    tday = ldf[ldf.index.date == ldf.index[-1].date()]
                    pday = ldf[ldf.index.date < ldf.index[-1].date()]
                    curr = float(tday["Close"].iloc[-1]) if not tday.empty else float(df1y["Close"].iloc[-1])
                    prev = float(pday["Close"].iloc[-1]) if not pday.empty else float(df1y["Close"].iloc[-2])
                    vol_today = float(tday["Volume"].sum()) if not tday.empty else 0.0
                else:
                    curr = float(df1y["Close"].iloc[-1]); prev = float(df1y["Close"].iloc[-2]); vol_today = float(df1y["Volume"].iloc[-1])
            else:
                curr = float(df1y["Close"].iloc[-1]); prev = float(df1y["Close"].iloc[-2]) if len(df1y) > 1 else curr
                vol_today = float(df1y["Volume"].iloc[-1])
            chg_pct      = (curr - prev) / prev * 100 if prev else 0.0
            rng52        = hi52 - lo52
            pos52        = (curr - lo52) / rng52 * 100 if rng52 > 0 else 50.0
            vol_ratio    = vol_today / vol_avg20 if vol_avg20 > 0 else 1.0
            above_sma20  = curr > float(df1y["Close"].rolling(20).mean().iloc[-1])
            above_sma50  = curr > float(df1y["Close"].rolling(50).mean().iloc[-1]) if len(df1y) >= 50 else False
            above_sma200 = curr > float(df1y["Close"].rolling(200).mean().iloc[-1]) if len(df1y) >= 200 else False
            stocks.append({
                "ticker": t, "sym": t.replace(".NS",""), "curr": curr, "chg_pct": chg_pct,
                "hi52": hi52, "lo52": lo52, "pos52": pos52, "vol_ratio": vol_ratio,
                "above_sma20": above_sma20, "above_sma50": above_sma50, "above_sma200": above_sma200,
                "new_hi52": curr >= hi52 * 0.99, "new_lo52": curr <= lo52 * 1.01,
            })
        except Exception:
            continue

    if not stocks:
        st.info("Price data loading…")
        return

    df_st = pd.DataFrame(stocks)

    # ── Market Intelligence Strip ──────────────────────────────────────────────
    advances   = int((df_st["chg_pct"] > 0).sum())
    declines   = int((df_st["chg_pct"] < 0).sum())
    pct_sma20  = round(df_st["above_sma20"].mean()  * 100, 1)
    pct_sma50  = round(df_st["above_sma50"].mean()  * 100, 1)
    pct_sma200 = round(df_st["above_sma200"].mean() * 100, 1)
    hi52_cnt   = int(df_st["new_hi52"].sum())
    lo52_cnt   = int(df_st["new_lo52"].sum())
    vol_spikes = int((df_st["vol_ratio"] >= 2.0).sum())

    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
        'Market Intelligence · Nifty 50</div>',
        unsafe_allow_html=True,
    )
    kpis = [
        ("Advancing",    str(advances),          "#00c896"),
        ("Declining",    str(declines),           "#ff4d6d"),
        ("Above SMA200", f"{pct_sma200:.0f}%",   "#8b5cf6"),
        ("52W Highs",    str(hi52_cnt),           "#f0b429"),
        ("52W Lows",     str(lo52_cnt),           "#ff4d6d"),
        ("Vol Spikes 2×",str(vol_spikes),         "#06b6d4"),
    ]
    for col, (label, val, color) in zip(st.columns(6), kpis):
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                f'border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:12px 14px;">'
                f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.07em;margin-bottom:6px;">{label}</div>'
                f'<div style="font-size:1.4rem;font-weight:800;color:{color};letter-spacing:-0.02em;">{val}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── 52-Week Range Bars ─────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">'
        '52-Week Range — Where each stock trades in its annual range</div>',
        unsafe_allow_html=True,
    )
    df_52 = df_st.sort_values("pos52", ascending=False)
    html  = '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;">'
    for _, row in df_52.iterrows():
        pos = row["pos52"]; chg = row["chg_pct"]
        c     = "#00c896" if chg >= 0 else "#ff4d6d"
        bar_c = "#00c896" if pos >= 75 else ("#f0b429" if pos >= 40 else "#ff4d6d")
        tag   = ('<span style="background:#f0b42922;color:#f0b429;border:1px solid #f0b42944;'
                 'border-radius:4px;padding:1px 5px;font-size:0.55rem;font-weight:700;margin-left:4px;">52W H</span>'
                 if row["new_hi52"] else
                 '<span style="background:#ff4d6d22;color:#ff4d6d;border:1px solid #ff4d6d44;'
                 'border-radius:4px;padding:1px 5px;font-size:0.55rem;font-weight:700;margin-left:4px;">52W L</span>'
                 if row["new_lo52"] else "")
        html += (
            f'<div style="background:#131929;border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:8px 12px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">'
            f'<div style="display:flex;align-items:center;"><span style="font-size:0.78rem;font-weight:700;color:#e2e8f0;">{row["sym"]}</span>{tag}</div>'
            f'<div style="text-align:right;">'
            f'<span style="font-size:0.72rem;color:#64748b;">₹{row["curr"]:,.0f}</span>'
            f'<span style="font-size:0.68rem;font-weight:700;color:{c};margin-left:6px;">{"▲" if chg>=0 else "▼"}{abs(chg):.1f}%</span>'
            f'</div></div>'
            f'<div style="position:relative;height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">'
            f'<div style="position:absolute;left:0;top:0;height:100%;width:{min(pos,100):.1f}%;background:{bar_c};border-radius:3px;opacity:0.85;"></div>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;margin-top:3px;">'
            f'<span style="font-size:0.55rem;color:#374151;">₹{row["lo52"]:,.0f}</span>'
            f'<span style="font-size:0.58rem;color:#475569;">{pos:.0f}%</span>'
            f'<span style="font-size:0.55rem;color:#374151;">₹{row["hi52"]:,.0f}</span>'
            f'</div></div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)
    st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)

    # ── Breadth charts ─────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Market Breadth</div>',
        unsafe_allow_html=True,
    )
    bc1, bc2 = st.columns([1, 2])
    with bc1:
        try:
            st.plotly_chart(market_breadth_gauge(advances, declines), use_container_width=True, key="breadth_gauge")
        except Exception:
            pass
    with bc2:
        try:
            st.plotly_chart(breadth_bar_chart(pct_sma20, pct_sma50, pct_sma200, hi52_cnt, lo52_cnt), use_container_width=True, key="breadth_bars")
        except Exception:
            pass

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Sector tiles + Heatmap + Rotation Quadrant ────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">Sector Performance</div>',
        unsafe_allow_html=True,
    )
    sector_data   = []
    rotation_data = []
    nifty_1y      = hist_1y.get("Nifty 50")
    s_cols        = st.columns(min(len(_sector_indices), 5))

    for i, (name, ticker) in enumerate(_sector_indices.items()):
        df5d = fetch_index_data(ticker, period="5d",  interval="1d")
        df3m = fetch_index_data(ticker, period="3mo", interval="1d")
        if df5d is None or len(df5d) < 2:
            continue
        if _live:
            q = _live_q(ticker); curr = q.get("price", float(df5d["Close"].iloc[-1])); chg = q.get("chg", 0.0)
        else:
            curr = float(df5d["Close"].iloc[-1]); chg = (curr - float(df5d["Close"].iloc[-2])) / float(df5d["Close"].iloc[-2]) * 100
        sector_data.append({"sector": name, "change_pct": chg, "market_cap": abs(curr)})

        if df3m is not None and len(df3m) >= 20 and nifty_1y is not None and len(nifty_1y) >= 20:
            try:
                s1m = (float(df3m["Close"].iloc[-1]) - float(df3m["Close"].iloc[-20])) / float(df3m["Close"].iloc[-20]) * 100
                n1m = (float(nifty_1y["Close"].iloc[-1]) - float(nifty_1y["Close"].iloc[-20])) / float(nifty_1y["Close"].iloc[-20]) * 100
                s3m = float(df3m["Close"].pct_change().tail(60).mean() * 100 * 20)
                rotation_data.append({"sector": name, "rs": s1m - n1m, "momentum": s1m - s3m})
            except Exception:
                pass

        short = name.replace("Nifty ", "")
        c = "#00c896" if chg >= 0 else "#ff4d6d"; bg = "rgba(0,200,150,0.07)" if chg >= 0 else "rgba(255,77,109,0.07)"; border = "rgba(0,200,150,0.2)" if chg >= 0 else "rgba(255,77,109,0.2)"
        with s_cols[i % 5]:
            st.markdown(
                f'<div style="background:{bg};border:1px solid {border};border-top:3px solid {c};'
                f'border-radius:12px;padding:12px 14px;margin:4px 0;">'
                f'<div style="color:#64748b;font-size:0.6rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.07em;margin-bottom:5px;">{short}</div>'
                f'<div style="color:#e2e8f0;font-size:0.95rem;font-weight:700;">{curr:,.0f}</div>'
                f'<div style="color:{c};font-size:0.78rem;font-weight:700;margin-top:4px;">{"▲" if chg>=0 else "▼"} {abs(chg):.2f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    hm_col, rot_col = st.columns(2)
    with hm_col:
        st.markdown('<div style="font-size:0.62rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 8px;">Sector Heatmap</div>', unsafe_allow_html=True)
        if sector_data:
            try:
                st.plotly_chart(sector_heatmap(sector_data), use_container_width=True, key="sector_heatmap")
            except Exception:
                pass
    with rot_col:
        st.markdown('<div style="font-size:0.62rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.1em;margin:16px 0 8px;">Sector Rotation Quadrant</div>', unsafe_allow_html=True)
        if rotation_data:
            try:
                st.plotly_chart(sector_rotation_chart(rotation_data), use_container_width=True, key="sector_rotation")
            except Exception:
                pass
        else:
            st.caption("Rotation data unavailable")

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Volume Anomalies ───────────────────────────────────────────────────────
    va_df = df_st[df_st["vol_ratio"] >= 1.5].sort_values("vol_ratio", ascending=False).head(5)
    if not va_df.empty:
        st.markdown(
            '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">'
            '⚡ Volume Anomalies — Unusual activity vs 20-day average</div>',
            unsafe_allow_html=True,
        )
        for col, (_, row) in zip(st.columns(len(va_df)), va_df.iterrows()):
            ratio = row["vol_ratio"]; chg = row["chg_pct"]
            c     = "#00c896" if chg >= 0 else "#ff4d6d"
            intensity = "#f0b429" if ratio < 3 else ("#f97316" if ratio < 5 else "#ff4d6d")
            with col:
                st.markdown(
                    f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
                    f'border:1px solid rgba(240,180,41,0.15);border-top:3px solid {intensity};'
                    f'border-radius:12px;padding:12px 14px;">'
                    f'<div style="font-size:0.88rem;font-weight:800;color:#e2e8f0;">{row["sym"]}</div>'
                    f'<div style="font-size:0.72rem;color:{intensity};font-weight:700;margin-top:4px;">Vol {ratio:.1f}× avg</div>'
                    f'<div style="font-size:0.68rem;color:{c};margin-top:3px;">{"▲" if chg>=0 else "▼"} {abs(chg):.2f}%</div>'
                    f'<div style="font-size:0.6rem;color:#374151;margin-top:2px;">₹{row["curr"]:,.0f}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Top Gainers / Losers ───────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;">'
        'Top Gainers & Losers · Nifty 50</div>',
        unsafe_allow_html=True,
    )
    df_sorted = df_st.sort_values("chg_pct", ascending=False)
    gainers   = df_sorted.head(5).to_dict("records")
    losers    = df_sorted.tail(5).iloc[::-1].to_dict("records")

    def _mover_row(row, is_gain):
        c = "#00c896" if is_gain else "#ff4d6d"; bg = "rgba(0,200,150,0.06)" if is_gain else "rgba(255,77,109,0.06)"
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:9px 12px;margin:4px 0;background:{bg};border-radius:8px;">'
            f'<div><span style="font-weight:700;color:#e2e8f0;font-size:0.88rem;">{row["sym"]}</span>'
            f'<span style="font-size:0.62rem;color:#475569;margin-left:6px;">Vol {row["vol_ratio"]:.1f}×</span></div>'
            f'<div style="text-align:right;">'
            f'<div style="color:#94a3b8;font-size:0.75rem;">₹{row["curr"]:,.1f}</div>'
            f'<div style="color:{c};font-size:0.78rem;font-weight:700;">{"▲" if is_gain else "▼"} {abs(row["chg_pct"]):.2f}%</div>'
            f'</div></div>'
        )

    g_col, l_col = st.columns(2)
    with g_col:
        st.markdown(
            '<div style="font-size:0.65rem;font-weight:700;color:#00c896;margin-bottom:6px;">▲ Top Gainers</div>'
            + "".join(_mover_row(r, True) for r in gainers), unsafe_allow_html=True)
    with l_col:
        st.markdown(
            '<div style="font-size:0.65rem;font-weight:700;color:#ff4d6d;margin-bottom:6px;">▼ Top Losers</div>'
            + "".join(_mover_row(r, False) for r in losers), unsafe_allow_html=True)

    if _live:
        st.caption(f"↻ {_dt.datetime.now(_IST).strftime('%H:%M:%S')} IST · auto-updates every 2 min")

_nifty50_section()
