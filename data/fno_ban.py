"""
NSE F&O Ban List fetcher.
Stocks in the F&O ban cannot have fresh positions opened in their futures/options.
Fetched from NSE's daily ban file.
"""
import logging
import re
import datetime
import streamlit as st
import requests

logger = logging.getLogger(__name__)

_NSE_BAN_URL = "https://nsearchives.nseindia.com/web/sites/default/files/inline-files/fo_secban.csv"
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":    "https://www.nseindia.com/",
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_fno_ban_list() -> list[str]:
    """
    Returns list of NSE tickers currently in F&O ban (no .NS suffix).
    Falls back to empty list on any error.
    """
    try:
        r = requests.get(_NSE_BAN_URL, headers=_NSE_HEADERS, timeout=10)
        r.raise_for_status()
        tickers = []
        for line in r.text.strip().splitlines():
            parts = line.strip().split(",")
            for p in parts:
                sym = p.strip().upper()
                if re.match(r'^[A-Z]{2,20}$', sym) and sym not in ("SECURITY", "SYMBOL", "NAME", "SR", "NO"):
                    tickers.append(sym)
        return sorted(set(tickers))
    except Exception as exc:
        logger.debug("F&O ban list fetch failed: %s", exc)
        return []


def is_in_fno_ban(ticker: str, ban_list: list[str]) -> bool:
    """Check if a .NS ticker is in the F&O ban list."""
    sym = ticker.replace(".NS", "").upper()
    return sym in ban_list


def get_ban_display(ban_list: list[str]) -> str:
    """Return a formatted date string for the ban (today's date)."""
    return datetime.date.today().strftime("%d %b %Y")
