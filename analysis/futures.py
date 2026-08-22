"""
Futures basis analytics for Nifty/BankNifty.
Computes spot-futures premium, cost of carry, and fair value.
"""
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.065  # RBI repo rate


def fair_value(spot: float, days_to_expiry: int, r: float = RISK_FREE_RATE) -> float:
    """Theoretical futures fair value: F = S × e^(r × T)."""
    T = max(days_to_expiry, 0) / 365.0
    return round(spot * math.exp(r * T), 2)


def basis(spot: float, futures: float) -> float:
    """Basis = Futures − Spot (positive = contango, negative = backwardation)."""
    return round(futures - spot, 2)


def basis_pct(spot: float, futures: float) -> float:
    """Basis as % of spot."""
    if spot <= 0:
        return 0.0
    return round((futures - spot) / spot * 100, 3)


def annualised_carry(spot: float, futures: float, days_to_expiry: int) -> Optional[float]:
    """
    Annualised cost of carry from observed futures premium.
    Gives the implied risk-free rate embedded in the basis.
    """
    if spot <= 0 or days_to_expiry <= 0:
        return None
    T = days_to_expiry / 365.0
    try:
        return round(math.log(futures / spot) / T * 100, 2)
    except (ValueError, ZeroDivisionError):
        return None


def interpret_basis(basis_pct_val: float, carry: Optional[float]) -> dict:
    """
    Returns a dict with signal, color, and description for the current futures basis.
    """
    if basis_pct_val > 0.4:
        return {
            "signal":  "STRONG CONTANGO",
            "color":   "#00c896",
            "desc":    "Futures at significant premium — bullish institutional positioning.",
            "action":  "Bullish bias; futures buyers outnumber sellers.",
        }
    if basis_pct_val > 0.1:
        return {
            "signal":  "CONTANGO",
            "color":   "#5AD8A6",
            "desc":    "Normal positive basis — healthy bullish expectation.",
            "action":  "Normal market conditions.",
        }
    if basis_pct_val > -0.1:
        return {
            "signal":  "FLAT",
            "color":   "#f0b429",
            "desc":    "Futures near spot — market neutral / indecisive.",
            "action":  "Watch for breakout direction.",
        }
    if basis_pct_val > -0.4:
        return {
            "signal":  "BACKWARDATION",
            "color":   "#ff4d6d",
            "desc":    "Futures at discount to spot — bearish expectations / heavy short positions.",
            "action":  "Bearish bias; consider hedging longs.",
        }
    return {
        "signal":  "DEEP BACKWARDATION",
        "color":   "#ff1744",
        "desc":    "Sharp discount — potential panic selling in futures, or dividend adjustment.",
        "action":  "High caution — could be stress event. Check for corporate actions.",
    }


def rollover_cost_pct(near_futures: float, far_futures: float) -> float:
    """
    Cost of rolling from near month to far month.
    Positive = rolling costs money (carry to pay), negative = you receive credit.
    """
    if near_futures <= 0:
        return 0.0
    return round((far_futures - near_futures) / near_futures * 100, 3)
