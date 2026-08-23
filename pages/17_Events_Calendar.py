"""
Page 17: Earnings & Events Calendar
Upcoming earnings, dividends, splits, and corporate actions for Nifty 50/200.
Helps swing traders avoid holding into binary events.
"""
import logging
import math
import datetime as dt
import pandas as pd
import streamlit as st
import yfinance as yf

from config.stock_universe import NIFTY_50, NIFTY_200

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Events Calendar · NiftyEdge", layout="wide", page_icon="📅")
from ui.styles import inject_global_css, page_header, auth_guard, user_sidebar
inject_global_css()
auth_guard()
page_header("Events Calendar", "Upcoming earnings · Dividends · Corporate actions · Binary event risk")
user_sidebar()

TODAY = dt.date.today()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _universe_choice = st.selectbox("Universe", ["Nifty 50", "Nifty 200"], key="ev_uni")
    _days_ahead      = st.slider("Days ahead", 7, 60, 30, key="ev_days")
    _event_types     = st.multiselect(
        "Event types",
        ["Earnings", "Dividends", "Splits", "Rights"],
        default=["Earnings", "Dividends"],
        key="ev_types",
    )
    _run = st.button("📅 Fetch Events", type="primary", use_container_width=True)

if not _run:
    st.info("Configure filters and click **Fetch Events** to load the calendar.")
    st.stop()

_universe  = NIFTY_50 if _universe_choice == "Nifty 50" else NIFTY_200
_tickers   = list(_universe.values())
_end_date  = TODAY + dt.timedelta(days=_days_ahead)


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_calendar_batch(tickers: tuple, days_ahead: int) -> list[dict]:
    """
    Fetch earnings calendar and dividends for each ticker.
    Returns a list of event dicts sorted by date.
    """
    today    = dt.date.today()
    end_date = today + dt.timedelta(days=days_ahead)
    events   = []

    for t in tickers:
        sym = t.replace(".NS", "")
        try:
            yft = yf.Ticker(t)

            # ── Earnings ────────────────────────────────────────────────────────
            cal = yft.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    dates = ed if isinstance(ed, list) else [ed]
                    for d in dates:
                        try:
                            if hasattr(d, "date"):
                                ev_date = d.date()
                            else:
                                ev_date = pd.Timestamp(d).date()
                            if today <= ev_date <= end_date:
                                eps_est  = _safe_float(cal.get("EPS Estimate"))
                                rev_est  = _safe_float(cal.get("Revenue Estimate"))
                                ev_est  = _safe_float(cal.get("Earnings Average"))
                                events.append({
                                    "Date":      ev_date,
                                    "Ticker":    sym,
                                    "Type":      "Earnings",
                                    "Detail":    (
                                        f"EPS est: ₹{eps_est:.1f}" if eps_est else
                                        f"Rev est: ₹{rev_est/1e7:.0f}Cr" if rev_est else
                                        "Date confirmed"
                                    ),
                                    "DTE":       (ev_date - today).days,
                                    "_icon":     "📋",
                                    "_color":    "#f0b429",
                                })
                        except Exception:
                            continue

            # ── Dividends (from actions) ─────────────────────────────────────
            try:
                actions = yft.actions
                if actions is not None and not actions.empty and "Dividends" in actions.columns:
                    div_rows = actions[actions["Dividends"] > 0]
                    for div_date, div_row in div_rows.iterrows():
                        try:
                            if hasattr(div_date, "date"):
                                d = div_date.date()
                            else:
                                d = pd.Timestamp(div_date).date()
                            if today <= d <= end_date:
                                amt = _safe_float(div_row["Dividends"])
                                events.append({
                                    "Date":   d,
                                    "Ticker": sym,
                                    "Type":   "Dividends",
                                    "Detail": f"₹{amt:.2f}/share" if amt else "",
                                    "DTE":    (d - today).days,
                                    "_icon":  "💰",
                                    "_color": "#00c896",
                                })
                        except Exception:
                            continue
            except Exception:
                pass

            # ── Splits ──────────────────────────────────────────────────────
            try:
                actions = yft.actions
                if actions is not None and not actions.empty and "Stock Splits" in actions.columns:
                    split_rows = actions[actions["Stock Splits"] > 0]
                    for split_date, split_row in split_rows.iterrows():
                        try:
                            if hasattr(split_date, "date"):
                                d = split_date.date()
                            else:
                                d = pd.Timestamp(split_date).date()
                            if today <= d <= end_date:
                                ratio = _safe_float(split_row["Stock Splits"])
                                events.append({
                                    "Date":   d,
                                    "Ticker": sym,
                                    "Type":   "Splits",
                                    "Detail": f"{ratio:.0f}:1 split" if ratio else "",
                                    "DTE":    (d - today).days,
                                    "_icon":  "✂️",
                                    "_color": "#60a5fa",
                                })
                        except Exception:
                            continue
            except Exception:
                pass

        except Exception as exc:
            logger.debug("event fetch failed for %s: %s", t, exc)
            continue

    return sorted(events, key=lambda x: x["Date"])


with st.spinner(f"Scanning {len(_tickers)} stocks for events in the next {_days_ahead} days…"):
    _events = _fetch_calendar_batch(tuple(_tickers), _days_ahead)

# Filter by selected event types
_events = [e for e in _events if e["Type"] in _event_types]

if not _events:
    st.info(
        f"No {', '.join(_event_types)} events found for {_universe_choice} "
        f"in the next {_days_ahead} days.\n\n"
        "Note: yfinance earnings calendars are US-centric; Indian company dates may be sparse. "
        "Try extending the days-ahead window."
    )
    st.stop()

_ev_df = pd.DataFrame(_events)

# ── Summary strip ─────────────────────────────────────────────────────────────
_n_earnings  = int((_ev_df["Type"] == "Earnings").sum())
_n_dividends = int((_ev_df["Type"] == "Dividends").sum())
_n_splits    = int((_ev_df["Type"] == "Splits").sum())
_n_this_week = int((_ev_df["DTE"] <= 7).sum())

st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Event Summary</div>',
    unsafe_allow_html=True,
)
_sc = st.columns(4)
for _col, (_lbl, _val, _cc) in zip(_sc, [
    ("Earnings",         str(_n_earnings),  "#f0b429"),
    ("Dividends",        str(_n_dividends), "#00c896"),
    ("Splits",           str(_n_splits),    "#60a5fa"),
    ("This week (≤7d)",  str(_n_this_week), "#ff4d6d" if _n_this_week > 0 else "#94a3b8"),
]):
    with _col:
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a1f35,#141828);'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 16px;">'
            f'<div style="font-size:0.58rem;color:#6b7a99;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;">{_lbl}</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{_cc};">{_val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

# ── Urgent: events within 7 days ─────────────────────────────────────────────
_urgent = _ev_df[_ev_df["DTE"] <= 7].sort_values("DTE")
if not _urgent.empty:
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#ff4d6d;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">'
        '⚠ Imminent Events (≤ 7 days)</div>',
        unsafe_allow_html=True,
    )
    _cards_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px;">'
    for _, ev in _urgent.iterrows():
        _dte_str = "Today" if ev["DTE"] == 0 else f"in {ev['DTE']}d"
        _cards_html += (
            f'<div style="background:rgba(255,77,109,0.06);border:1px solid rgba(255,77,109,0.2);'
            f'border-left:3px solid {ev["_color"]};border-radius:10px;padding:10px 14px;min-width:160px;">'
            f'<div style="font-size:0.65rem;color:#6b7a99;margin-bottom:4px;">{ev["_icon"]} {ev["Type"]} · {_dte_str}</div>'
            f'<div style="font-size:0.95rem;font-weight:800;color:#e2e8f0;">{ev["Ticker"]}</div>'
            f'<div style="font-size:0.7rem;color:{ev["_color"]};margin-top:3px;">{ev["Detail"]}</div>'
            f'<div style="font-size:0.6rem;color:#475569;margin-top:3px;">{ev["Date"].strftime("%d %b %Y")}</div>'
            f'</div>'
        )
    _cards_html += '</div>'
    st.markdown(_cards_html, unsafe_allow_html=True)

# ── Week-by-week calendar view ─────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px;">Calendar View</div>',
    unsafe_allow_html=True,
)

_ev_df["Week"] = _ev_df["Date"].apply(lambda d: d.isocalendar()[1])
_ev_df["WeekStart"] = _ev_df["Date"].apply(
    lambda d: (d - dt.timedelta(days=d.weekday())).strftime("Week of %d %b")
)

for _week_label, _week_group in _ev_df.groupby("WeekStart"):
    with st.expander(f"📅 {_week_label} — {len(_week_group)} events", expanded=(_week_group["DTE"].min() <= 7)):
        for _evt_type in ["Earnings", "Dividends", "Splits", "Rights"]:
            _sub = _week_group[_week_group["Type"] == _evt_type]
            if _sub.empty:
                continue
            st.markdown(
                f'<div style="font-size:0.65rem;font-weight:700;color:#6b7a99;'
                f'text-transform:uppercase;margin:8px 0 4px;">{_evt_type}</div>',
                unsafe_allow_html=True,
            )
            _rows_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;">'
            for _, ev in _sub.iterrows():
                _color = ev["_color"]
                _rows_html += (
                    f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                    f'border-left:2px solid {_color};border-radius:8px;padding:8px 12px;min-width:140px;">'
                    f'<div style="font-size:0.85rem;font-weight:700;color:#e2e8f0;">{ev["Ticker"]}</div>'
                    f'<div style="font-size:0.65rem;color:#6b7a99;">{ev["Date"].strftime("%a %d %b")}</div>'
                    f'<div style="font-size:0.65rem;color:{_color};margin-top:2px;">{ev["Detail"]}</div>'
                    f'</div>'
                )
            _rows_html += '</div>'
            st.markdown(_rows_html, unsafe_allow_html=True)

# ── Full table ────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#475569;'
    'text-transform:uppercase;letter-spacing:0.1em;margin:24px 0 8px;">Full Events Table</div>',
    unsafe_allow_html=True,
)

_tbl = _ev_df[["Date", "Ticker", "Type", "Detail", "DTE"]].copy()
_tbl["Date"] = _tbl["Date"].apply(lambda d: d.strftime("%d %b %Y"))


def _type_style(val):
    c = {"Earnings": "#f0b429", "Dividends": "#00c896", "Splits": "#60a5fa", "Rights": "#a78bfa"}
    return f"color: {c.get(val, '#94a3b8')}; font-weight: 700;"


def _dte_style(val):
    v = int(val) if str(val).isdigit() or (str(val).lstrip("-").isdigit()) else None
    if v is None:
        return ""
    return f"color: {'#ff4d6d' if v <= 7 else '#f0b429' if v <= 14 else '#94a3b8'}; font-weight: {'700' if v <= 7 else '400'};"


styled = (
    _tbl.style
    .map(_type_style, subset=["Type"])
    .map(_dte_style,  subset=["DTE"])
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Export ────────────────────────────────────────────────────────────────────
st.download_button(
    "⬇ Export to CSV",
    _ev_df[["Date", "Ticker", "Type", "Detail", "DTE"]].to_csv(index=False),
    file_name=f"events_calendar_{_universe_choice.replace(' ','_')}_{TODAY.isoformat()}.csv",
    mime="text/csv",
)

st.caption(
    f"Universe: {_universe_choice} ({len(_tickers)} stocks) · "
    f"Events from {TODAY.strftime('%d %b')} to {_end_date.strftime('%d %b %Y')} · "
    f"Data via yfinance (earnings calendar availability varies for Indian stocks)"
)
