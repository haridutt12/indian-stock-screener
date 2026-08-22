"""
Options analytics: Black-Scholes Greeks, PCR, Max Pain, IV Rank.
Pure numpy — no scipy dependency.
"""
import math
import numpy as np
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.065  # RBI repo rate approximation


# ── Normal CDF (Abramowitz & Stegun, error < 7.5e-8) ─────────────────────────
def _norm_cdf(x: float) -> float:
    a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    _b = 0.2316419
    t = 1.0 / (1.0 + _b * abs(x))
    poly = t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))))
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if x >= 0 else 1.0 - cdf


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


# ── Black-Scholes price & Greeks ──────────────────────────────────────────────
def bs_greeks(
    S: float, K: float, T: float, sigma: float,
    r: float = RISK_FREE_RATE, option_type: str = "call",
) -> dict:
    """
    Returns price and Greeks for a European option.
    T  = time to expiry in years
    S  = spot price
    K  = strike
    sigma = annualised IV (e.g. 0.18 for 18%)
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    disc = math.exp(-r * T)

    if option_type == "call":
        Nd1, Nd2 = _norm_cdf(d1), _norm_cdf(d2)
        price = S * Nd1 - K * disc * Nd2
        delta = Nd1
        rho   = K * T * disc * Nd2 / 100
    else:
        Nd1, Nd2 = _norm_cdf(-d1), _norm_cdf(-d2)
        price = K * disc * Nd2 - S * Nd1
        delta = Nd1 - 1.0
        rho   = -K * T * disc * Nd2 / 100

    npd1  = _norm_pdf(d1)
    gamma = npd1 / (S * sigma * sqrtT)
    vega  = S * npd1 * sqrtT / 100
    theta = (-(S * npd1 * sigma) / (2 * sqrtT) - r * K * disc * (Nd2 if option_type == "call" else -Nd2)) / 365

    return {
        "price": round(price, 2),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 2),
        "vega":  round(vega,  2),
        "rho":   round(rho,   4),
    }


# ── PCR (Put-Call Ratio) ──────────────────────────────────────────────────────
def compute_pcr(calls: pd.DataFrame, puts: pd.DataFrame) -> dict:
    """Volume PCR and OI PCR. Returns sentiment label."""
    vol_c = calls["volume"].fillna(0).sum()
    vol_p = puts["volume"].fillna(0).sum()
    oi_c  = calls["openInterest"].fillna(0).sum()
    oi_p  = puts["openInterest"].fillna(0).sum()

    pcr_vol = round(vol_p / vol_c, 3) if vol_c > 0 else None
    pcr_oi  = round(oi_p  / oi_c,  3) if oi_c  > 0 else None

    def _label(pcr):
        if pcr is None:
            return "—"
        if pcr > 1.3:
            return "OVERSOLD (contrarian LONG)"
        if pcr > 1.0:
            return "BEARISH"
        if pcr > 0.7:
            return "NEUTRAL"
        if pcr > 0.5:
            return "BULLISH"
        return "OVERBOUGHT (contrarian SHORT)"

    return {
        "pcr_volume": pcr_vol,
        "pcr_oi":     pcr_oi,
        "sentiment":  _label(pcr_oi),
        "signal":     "LONG" if (pcr_oi or 0) > 1.25 else ("SHORT" if (pcr_oi or 0) < 0.55 else "NEUTRAL"),
    }


# ── Max Pain ─────────────────────────────────────────────────────────────────
def compute_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    """
    Strike at which total option seller pain is minimised (i.e. most options expire worthless).
    This is where large OI writers want the market to expire.
    """
    try:
        c = calls[["strike", "openInterest"]].dropna().copy()
        p = puts[["strike", "openInterest"]].dropna().copy()
        c["openInterest"] = c["openInterest"].fillna(0)
        p["openInterest"] = p["openInterest"].fillna(0)

        strikes = sorted(set(c["strike"]).union(set(p["strike"])))
        if not strikes:
            return None

        c_oi = dict(zip(c["strike"], c["openInterest"]))
        p_oi = dict(zip(p["strike"], p["openInterest"]))

        pain = {}
        for s in strikes:
            call_pain = sum(max(0, s - k) * oi for k, oi in c_oi.items())
            put_pain  = sum(max(0, k - s) * oi for k, oi in p_oi.items())
            pain[s]   = call_pain + put_pain

        return float(min(pain, key=pain.get))
    except Exception as exc:
        logger.debug("max_pain error: %s", exc)
        return None


# ── IV Rank / IV Percentile ───────────────────────────────────────────────────
def compute_iv_rank(current_iv: float, historical_ivs: "list[float]") -> dict:
    """
    IV Rank  = (current - 52W low) / (52W high - 52W low) * 100
    IV Percentile = % of days in past year where IV was below current
    """
    if not historical_ivs or current_iv <= 0:
        return {"iv_rank": None, "iv_percentile": None, "label": "—"}

    low  = min(historical_ivs)
    high = max(historical_ivs)
    rank = round((current_iv - low) / (high - low) * 100, 1) if high != low else 50.0
    pct  = round(sum(1 for v in historical_ivs if v < current_iv) / len(historical_ivs) * 100, 1)

    if rank >= 80:
        label = "EXPENSIVE (sell premium)"
    elif rank >= 50:
        label = "MODERATE"
    elif rank >= 25:
        label = "CHEAP (buy options)"
    else:
        label = "VERY CHEAP (buy premium)"

    return {"iv_rank": rank, "iv_percentile": pct, "label": label}


# ── ATM strike finder ─────────────────────────────────────────────────────────
def find_atm_strike(spot: float, strikes: "list[float]") -> float:
    """Return the strike closest to spot."""
    return min(strikes, key=lambda k: abs(k - spot))


# ── Days to expiry (calendar days) ───────────────────────────────────────────
def days_to_expiry(expiry_str: str) -> int:
    import datetime
    try:
        exp = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return max(0, (exp - datetime.date.today()).days)
    except Exception:
        return 0


# ── Options strategy suggester ────────────────────────────────────────────────
def suggest_options_strategy(
    direction: str,
    iv_rank: Optional[float],
    spot: float,
    strike_step: float = 50.0,
) -> dict:
    """
    Given signal direction and IV environment, suggest an options strategy.
    Returns a dict with strategy name, legs, and rationale.
    """
    high_iv = iv_rank is not None and iv_rank >= 60
    atm = round(spot / strike_step) * strike_step
    otm_offset = strike_step * 2

    if direction == "LONG":
        if high_iv:
            return {
                "name":      "Bull Call Spread",
                "legs":      [
                    {"action": "BUY",  "type": "CE", "strike": atm},
                    {"action": "SELL", "type": "CE", "strike": atm + otm_offset},
                ],
                "rationale": f"IV Rank {iv_rank:.0f}% — high IV makes naked calls expensive; spread limits debit.",
                "max_loss":  "Limited to net debit",
                "max_gain":  f"Spread width minus debit (i.e. {otm_offset:.0f} pts × lot size)",
            }
        else:
            return {
                "name":      "ATM Call Buy",
                "legs":      [{"action": "BUY", "type": "CE", "strike": atm}],
                "rationale": f"IV Rank {(f'{iv_rank:.0f}' if iv_rank is not None else '—')}% — cheap IV; outright call captures full upside.",
                "max_loss":  "Premium paid",
                "max_gain":  "Unlimited",
            }
    else:  # SHORT signal
        if high_iv:
            return {
                "name":      "Bear Put Spread",
                "legs":      [
                    {"action": "BUY",  "type": "PE", "strike": atm},
                    {"action": "SELL", "type": "PE", "strike": atm - otm_offset},
                ],
                "rationale": f"IV Rank {iv_rank:.0f}% — high IV; spread reduces net debit significantly.",
                "max_loss":  "Limited to net debit",
                "max_gain":  f"Spread width minus debit ({otm_offset:.0f} pts × lot size)",
            }
        else:
            return {
                "name":      "ATM Put Buy",
                "legs":      [{"action": "BUY", "type": "PE", "strike": atm}],
                "rationale": f"IV Rank {(f'{iv_rank:.0f}' if iv_rank is not None else '—')}% — IV cheap; buy outright put.",
                "max_loss":  "Premium paid",
                "max_gain":  f"Strike minus zero (max {atm:.0f} pts)",
            }
