"""
Portfolio risk analytics module.
Value at Risk (VaR), Conditional VaR (CVaR), portfolio heat, position sizing.
All computations are purely mathematical — no external API calls.
"""
from __future__ import annotations
import math
import statistics
from typing import Optional


def historical_var(returns: list[float], confidence: float = 0.95) -> float:
    """
    Historical VaR at given confidence level.
    Returns the loss (positive number) at the confidence percentile.
    """
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1.0 - confidence) * len(sorted_r))
    idx = max(0, min(idx, len(sorted_r) - 1))
    return abs(sorted_r[idx])


def parametric_var(returns: list[float], confidence: float = 0.95) -> float:
    """
    Parametric (Gaussian) VaR.
    VaR = −(μ + z_α × σ), z_α for 95% ≈ 1.645, for 99% ≈ 2.326.
    """
    if len(returns) < 4:
        return 0.0
    mu  = sum(returns) / len(returns)
    sig = statistics.stdev(returns)
    # z-scores for common confidence levels
    z_map = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z = z_map.get(round(confidence, 2), 1.645)
    return max(0.0, -(mu - z * sig))


def conditional_var(returns: list[float], confidence: float = 0.95) -> float:
    """
    CVaR (Expected Shortfall): average of losses beyond VaR.
    More conservative and coherent than VaR alone.
    """
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    cut = int((1.0 - confidence) * len(sorted_r))
    tail = sorted_r[:max(1, cut)]
    return abs(sum(tail) / len(tail))


def portfolio_heat(
    open_signals: list[dict],
    position_size_inr: float,
    portfolio_value_inr: float = 1_000_000.0,
) -> dict:
    """
    Compute aggregate portfolio risk from open signals.
    Returns: total_at_risk_inr, portfolio_heat_pct, n_long, n_short, per_signal
    """
    if not open_signals or portfolio_value_inr <= 0:
        return {}

    total_risk   = 0.0
    n_long = n_short = 0
    per_signal = []

    for sig in open_signals:
        entry = float(sig.get("entry_price") or 0)
        sl    = float(sig.get("stop_loss")   or 0)
        if entry <= 0 or sl <= 0:
            continue
        risk_pct = abs(entry - sl) / entry
        risk_inr = position_size_inr * risk_pct
        total_risk += risk_inr

        direction = (sig.get("direction") or "LONG").upper()
        if direction == "LONG":
            n_long += 1
        else:
            n_short += 1

        per_signal.append({
            "ticker":     sig.get("ticker", ""),
            "direction":  direction,
            "risk_inr":   round(risk_inr, 0),
            "risk_pct":   round(risk_pct * 100, 2),
        })

    heat_pct = total_risk / portfolio_value_inr * 100

    return {
        "total_at_risk_inr": round(total_risk, 0),
        "portfolio_heat_pct": round(heat_pct, 2),
        "n_signals":  len(per_signal),
        "n_long":     n_long,
        "n_short":    n_short,
        "per_signal": sorted(per_signal, key=lambda x: x["risk_inr"], reverse=True),
    }


def fixed_fractional_size(
    account_value: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> dict:
    """
    Fixed-fractional position sizing.
    risk_pct = fraction of account to risk (e.g. 0.01 = 1%).
    Returns: shares, position_value, risk_per_trade.
    """
    if entry_price <= 0 or stop_loss <= 0 or risk_pct <= 0:
        return {}
    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit <= 0:
        return {}
    risk_amount = account_value * risk_pct
    shares = math.floor(risk_amount / risk_per_unit)
    return {
        "shares":          shares,
        "position_value":  round(shares * entry_price, 0),
        "risk_per_trade":  round(shares * risk_per_unit, 0),
        "risk_pct_actual": round(shares * risk_per_unit / account_value * 100, 3),
        "risk_per_unit":   round(risk_per_unit, 2),
    }


def kelly_size(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
    account_value: float,
    entry_price: float,
    stop_loss: float,
    half_kelly: bool = True,
    max_risk_pct: float = 0.05,
) -> dict:
    """
    Kelly Criterion position sizing.
    f* = p/|loss_r| - (1-p)/win_r
    Half-Kelly and max_risk_pct cap are applied for safety.
    """
    if avg_win_r <= 0 or avg_loss_r <= 0:
        return {}
    p = win_rate / 100.0
    q = 1.0 - p
    b = avg_win_r / avg_loss_r  # win/loss ratio
    kelly_f = p - q / b
    if kelly_f <= 0:
        return {"kelly_f": 0.0, "note": "Negative Kelly — system has no edge"}
    if half_kelly:
        kelly_f /= 2.0
    risk_pct = min(kelly_f, max_risk_pct)
    sizing   = fixed_fractional_size(account_value, risk_pct, entry_price, stop_loss)
    return {
        "kelly_f":     round(kelly_f, 4),
        "risk_pct":    round(risk_pct * 100, 2),
        **sizing,
    }


def ruin_probability(
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
    risk_pct: float,
    ruin_level: float = 0.5,
    n_sims: int = 0,
) -> dict:
    """
    Analytical ruin probability using the gambler's ruin formula.
    ruin_level: fraction of account lost to constitute ruin (e.g. 0.5 = 50% drawdown).
    Approximation: P(ruin) ≈ ((1-p)/p)^(capital/bet) for p > 0.5, else approaches 1.

    Returns probability of ruin and expected trades to ruin.
    """
    p = win_rate / 100.0
    q = 1.0 - p
    if p <= 0 or q <= 0 or risk_pct <= 0:
        return {}

    # Simplified: capital units = ruin_level / risk_pct
    capital_units = int(ruin_level / risk_pct)
    if p > 0.5:
        ratio = q / p
        p_ruin = (ratio ** capital_units) if ratio < 1 else 1.0
    else:
        p_ruin = 1.0

    # Expected trades to terminal ruin (approximate)
    edge = p * avg_win_r - q * avg_loss_r
    expected_trades = capital_units / max(abs(edge), 0.001) if edge < 0 else None

    return {
        "p_ruin":          round(min(p_ruin, 1.0) * 100, 2),
        "capital_units":   capital_units,
        "edge_per_trade":  round(edge, 3),
        "expected_trades_to_ruin": int(expected_trades) if expected_trades else None,
    }


def position_risk_summary(
    entry_price: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    shares: int,
    direction: str = "LONG",
) -> dict:
    """
    Compute risk/reward metrics for a single position.
    """
    is_long = direction.upper() == "LONG"
    if entry_price <= 0 or shares <= 0:
        return {}

    risk     = abs(entry_price - stop_loss) * shares if stop_loss > 0 else None
    profit_1 = abs(target_1 - entry_price) * shares if target_1 > 0 else None
    profit_2 = abs(target_2 - entry_price) * shares if target_2 > 0 else None
    rr_1     = round(profit_1 / risk, 2) if (risk and profit_1) else None
    rr_2     = round(profit_2 / risk, 2) if (risk and profit_2) else None

    return {
        "position_value": round(entry_price * shares, 0),
        "max_loss":       round(risk, 0) if risk else None,
        "profit_at_t1":   round(profit_1, 0) if profit_1 else None,
        "profit_at_t2":   round(profit_2, 0) if profit_2 else None,
        "rr_t1":          rr_1,
        "rr_t2":          rr_2,
        "break_even":     round(entry_price, 2),
    }
