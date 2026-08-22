"""
Signal ranking — composite 0-100 score for open trade signals.

Five factors (weights add to 100):
  Confidence   25 — user-visible 1-5 star confidence
  Technical    20 — RSI/MACD/SMA alignment score
  Fundamental  15 — valuation/profitability composite
  Risk/Reward  20 — R:R ratio normalised (cap at 5×)
  Entry Timing 20 — exponential decay from entry; also penalises stale signals

Entry Timing uses exponential decay: 20 pts at/below entry, decays toward 0 as
price moves further past entry. An additional age penalty applies: SWING signals
lose 1pt/day after 3 days; INTRADAY signals lose 2pts after 1 day.
"""
from __future__ import annotations
import math
import datetime
from typing import Optional
import yfinance as yf


def _entry_timing_score(moved_pct: float) -> float:
    """
    Exponential decay: 20 pts at moved_pct ≤ 0, decays to 0 at ~7%.
    f(x) = 20 × e^(−0.55 × max(0, x))
    """
    if moved_pct <= 0:
        return 20.0
    return round(20.0 * math.exp(-0.55 * moved_pct), 1)


def _age_penalty(sig: dict) -> float:
    """
    Penalise signals that are too old to act on.
    SWING:    −1 pt per day after 3 days (max −10 pts)
    INTRADAY: −2 pts per day after 1 day  (max −10 pts)
    """
    signal_date = sig.get("signal_date") or sig.get("created_at")
    if not signal_date:
        return 0.0
    try:
        if isinstance(signal_date, str):
            sd = datetime.date.fromisoformat(signal_date[:10])
        elif hasattr(signal_date, "date"):
            sd = signal_date.date()
        else:
            sd = datetime.date.fromisoformat(str(signal_date)[:10])
        age_days = (datetime.date.today() - sd).days
    except Exception:
        return 0.0

    tf = (sig.get("timeframe") or "SWING").upper()
    if tf == "INTRADAY":
        grace = 1
        rate  = 2.0
    else:
        grace = 3
        rate  = 1.0

    excess = max(0, age_days - grace)
    return min(excess * rate, 10.0)


def score_signal(sig: dict, curr_price: Optional[float]) -> tuple[float, dict]:
    """
    Returns (total_score, breakdown_dict).
    breakdown keys: Confidence, Technical, Fundamental, Risk/Reward, Entry Timing, _prox_label
    """
    bd: dict = {}

    # 1. Confidence  (0–25 pts)
    conf = sig.get("confidence") or 1
    bd["Confidence"] = round((conf / 5) * 25, 1)

    # 2. Technical score  (0–20 pts)
    tech = float(sig.get("technical_score") or 0.5)
    bd["Technical"] = round(tech * 20, 1)

    # 3. Fundamental score  (0–15 pts)
    fund = float(sig.get("fundamental_score") or 0.5)
    bd["Fundamental"] = round(fund * 15, 1)

    # 4. Risk / Reward  (0–20 pts) — RR 2× = 5 pts, RR 5× = 20 pts
    rr = min(float(sig.get("risk_reward") or 2.0), 5.0)
    bd["Risk/Reward"] = round(max(0.0, ((rr - 1.0) / 4.0) * 20), 1)

    # 5. Entry proximity  (0–20 pts, exponential decay + age penalty)
    pts_prox, prox_label = 10.0, "Price unavailable"
    if curr_price is not None:
        entry   = float(sig.get("entry_price") or 0)
        is_long = (sig.get("direction") or "LONG") == "LONG"
        if entry > 0:
            moved_pct = ((curr_price - entry) / entry * 100) if is_long \
                        else ((entry - curr_price) / entry * 100)
            pts_prox = _entry_timing_score(moved_pct)
            if moved_pct <= 0:
                prox_label = "At / below entry ✓"
            elif moved_pct <= 2:
                prox_label = f"+{moved_pct:.2f}% from entry"
            elif moved_pct <= 5:
                prox_label = f"+{moved_pct:.1f}% — entry missed"
            else:
                prox_label = f"+{moved_pct:.1f}% — too late"

    age_pen = _age_penalty(sig)
    pts_prox = max(0.0, pts_prox - age_pen)
    if age_pen > 0:
        prox_label = f"{prox_label} (−{age_pen:.0f}pt age)"

    bd["Entry Timing"]  = round(pts_prox, 1)
    bd["_prox_label"]   = prox_label

    total = sum(bd[k] for k in ("Confidence", "Technical", "Fundamental", "Risk/Reward", "Entry Timing"))
    return round(total, 1), bd


def fetch_prices(sigs: list[dict]) -> dict[str, Optional[float]]:
    """
    Fetch the most current price for each unique ticker.
    Uses fast_info.last_price (live/last-traded) as the primary source so
    intraday movement is captured — not just yesterday's close, which would
    equal the entry price and show 0% movement in the Top 3 message.
    Falls back to the last daily close if fast_info fails.
    """
    prices: dict[str, Optional[float]] = {}
    for sig in sigs:
        ticker = sig["ticker"]
        if ticker in prices:
            continue
        try:
            lp = float(yf.Ticker(ticker).fast_info.last_price)
            if lp > 0:
                prices[ticker] = lp
                continue
        except Exception:
            pass
        try:
            df = yf.Ticker(ticker).history(period="2d", interval="1d", auto_adjust=True)
            prices[ticker] = float(df["Close"].iloc[-1]) if df is not None and not df.empty else None
        except Exception:
            prices[ticker] = None
    return prices


def _sl_breached(sig: dict, curr_price: Optional[float]) -> bool:
    """Return True if the current price has already hit or crossed the stop loss."""
    if curr_price is None:
        return False
    sl = float(sig.get("stop_loss") or 0)
    if sl <= 0:
        return False
    is_long = (sig.get("direction") or "LONG") == "LONG"
    return curr_price <= sl if is_long else curr_price >= sl


def rank_signals(open_sigs: list[dict]) -> list[tuple[float, dict, dict, Optional[float]]]:
    """
    Score and rank all open signals.
    Returns list of (score, breakdown, signal_dict, curr_price) sorted descending.
    Each ticker appears at most once (highest-scored entry wins).
    Signals whose current price has already breached stop loss are excluded.
    """
    if not open_sigs:
        return []
    prices = fetch_prices(open_sigs)
    scored = []
    for sig in open_sigs:
        cp = prices.get(sig["ticker"])
        if _sl_breached(sig, cp):
            continue
        sc, bd = score_signal(sig, cp)
        scored.append((sc, bd, sig, cp))
    scored.sort(key=lambda x: x[0], reverse=True)

    # One entry per ticker — highest score already at the front after sort.
    seen: set[str] = set()
    deduped = []
    for item in scored:
        ticker = item[2]["ticker"]
        if ticker not in seen:
            seen.add(ticker)
            deduped.append(item)
    return deduped
