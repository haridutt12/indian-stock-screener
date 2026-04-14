"""
Indian market status detection — IST time, market state, holiday calendar.
"""
from datetime import datetime, date, time as dtime
import pytz
from config.settings import (
    IST,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    PRE_MARKET_OPEN_HOUR, PRE_MARKET_OPEN_MINUTE,
)

# NSE holidays 2025 (add/update as needed)
NSE_HOLIDAYS_2025 = {
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr (Ramadan Eid)
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti / Ram Navami
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Ganesh Chaturthi
    date(2025, 10, 2),   # Gandhi Jayanti / Dussehra
    date(2025, 10, 20),  # Diwali Laxmi Puja
    date(2025, 10, 21),  # Diwali Balipratipada
    date(2025, 11, 5),   # Prakash Gurpurb Sri Guru Nanak Dev Ji
    date(2025, 12, 25),  # Christmas
}

NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 26),   # Mahashivratri
    date(2026, 3, 19),   # Holi
    date(2026, 3, 31),   # Id-Ul-Fitr (Ramadan Eid)
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 23),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 20),  # Diwali Laxmi Puja (tentative)
    date(2026, 10, 21),  # Diwali Balipratipada (tentative)
    date(2026, 11, 5),   # Guru Nanak Jayanti (tentative)
    date(2026, 12, 25),  # Christmas
}

ALL_HOLIDAYS = NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


def now_ist() -> datetime:
    return datetime.now(IST)


def is_trading_day(dt: datetime = None) -> bool:
    if dt is None:
        dt = now_ist()
    d = dt.date()
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return d not in ALL_HOLIDAYS


def is_market_open(dt: datetime = None) -> bool:
    if dt is None:
        dt = now_ist()
    if not is_trading_day(dt):
        return False
    market_open = dtime(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    market_close = dtime(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
    current_time = dt.time().replace(second=0, microsecond=0)
    return market_open <= current_time <= market_close


def is_pre_market(dt: datetime = None) -> bool:
    if dt is None:
        dt = now_ist()
    if not is_trading_day(dt):
        return False
    pre_open = dtime(PRE_MARKET_OPEN_HOUR, PRE_MARKET_OPEN_MINUTE)
    market_open = dtime(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    current_time = dt.time().replace(second=0, microsecond=0)
    return pre_open <= current_time < market_open


def market_status() -> dict:
    """Returns current market state info."""
    dt = now_ist()
    return {
        "datetime_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        "is_trading_day": is_trading_day(dt),
        "is_market_open": is_market_open(dt),
        "is_pre_market": is_pre_market(dt),
        "market_open_time": f"{MARKET_OPEN_HOUR:02d}:{MARKET_OPEN_MINUTE:02d} IST",
        "market_close_time": f"{MARKET_CLOSE_HOUR:02d}:{MARKET_CLOSE_MINUTE:02d} IST",
        "status_label": _status_label(dt),
    }


def _status_label(dt: datetime) -> str:
    if not is_trading_day(dt):
        return "Market Closed (Holiday/Weekend)"
    if is_pre_market(dt):
        return "Pre-Market Session"
    if is_market_open(dt):
        return "Market Open"
    after_close = dtime(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
    if dt.time() > after_close:
        return "After Market Hours"
    return "Market Closed"
