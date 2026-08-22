"""
Signal quality analytics module.
Computes advanced trade statistics from closed signal records.
All metrics operate on R-multiples (risk-normalised P&L).
"""
from __future__ import annotations
import math
from typing import Optional
import statistics


def _r_series(signals: list[dict]) -> list[float]:
    """Extract non-null net_pnl_r from closed signals."""
    return [
        float(s["net_pnl_r"])
        for s in signals
        if s.get("net_pnl_r") is not None and s.get("outcome") != "OPEN"
    ]


def win_loss_streaks(r_series: list[float]) -> dict:
    """Compute max winning and losing consecutive streaks."""
    if not r_series:
        return {"max_win_streak": 0, "max_loss_streak": 0, "current_streak": 0, "current_streak_type": None}
    max_w = max_l = cur = 0
    streak_type = "WIN" if r_series[0] > 0 else "LOSS"
    for r in r_series:
        is_win = r > 0
        if (is_win and streak_type == "WIN") or (not is_win and streak_type == "LOSS"):
            cur += 1
        else:
            streak_type = "WIN" if is_win else "LOSS"
            cur = 1
        if streak_type == "WIN":
            max_w = max(max_w, cur)
        else:
            max_l = max(max_l, cur)
    return {
        "max_win_streak":  max_w,
        "max_loss_streak": max_l,
        "current_streak":  cur,
        "current_streak_type": streak_type,
    }


def equity_curve(r_series: list[float]) -> list[float]:
    """Cumulative R-multiple equity curve (starting from 0)."""
    curve, running = [], 0.0
    for r in r_series:
        running += r
        curve.append(round(running, 4))
    return curve


def max_drawdown_r(r_series: list[float]) -> float:
    """Max peak-to-trough drawdown in R-multiples."""
    if not r_series:
        return 0.0
    curve = equity_curve(r_series)
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 3)


def calmar_ratio(r_series: list[float]) -> Optional[float]:
    """
    Calmar ratio: annualised return / max drawdown.
    Here annualised return = mean(R) * 252 / avg_bars_per_trade (default 5 trading days).
    """
    if not r_series:
        return None
    dd = max_drawdown_r(r_series)
    if dd <= 0:
        return None
    mean_r = sum(r_series) / len(r_series)
    annualised = mean_r * 50  # ~50 trades/year approximation
    return round(annualised / dd, 2)


def ulcer_index(r_series: list[float]) -> Optional[float]:
    """
    Ulcer Index: RMS of drawdowns from peak. Measures downside volatility severity.
    Low UI (< 0.5) = smooth equity curve; high UI (> 2) = painful drawdowns.
    """
    if len(r_series) < 3:
        return None
    curve = equity_curve(r_series)
    peak = curve[0]
    sq_dd = []
    for v in curve:
        if v > peak:
            peak = v
        pct_dd = ((v - peak) / abs(peak) * 100) if peak != 0 else 0.0
        sq_dd.append(pct_dd ** 2)
    return round(math.sqrt(sum(sq_dd) / len(sq_dd)), 3)


def recovery_factor(r_series: list[float]) -> Optional[float]:
    """Net profit / max drawdown. >3 is good, >5 is excellent."""
    if not r_series:
        return None
    dd = max_drawdown_r(r_series)
    if dd <= 0:
        return None
    net = sum(r_series)
    return round(net / dd, 2) if dd > 0 else None


def expectancy(r_series: list[float]) -> dict:
    """
    Van Tharp expectancy: E = (Win% × Avg Win) − (Loss% × Avg Loss).
    Measures expected R per trade.
    """
    if not r_series:
        return {"expectancy": 0.0, "win_rate": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0}
    wins   = [r for r in r_series if r > 0]
    losses = [r for r in r_series if r <= 0]
    total  = len(r_series)
    win_rate   = len(wins)   / total
    loss_rate  = len(losses) / total
    avg_win    = sum(wins)   / len(wins)   if wins   else 0.0
    avg_loss   = abs(sum(losses) / len(losses)) if losses else 0.0
    exp        = win_rate * avg_win - loss_rate * avg_loss
    return {
        "expectancy": round(exp, 3),
        "win_rate":   round(win_rate * 100, 1),
        "avg_win_r":  round(avg_win, 3),
        "avg_loss_r": round(avg_loss, 3),
    }


def sharpe_r(r_series: list[float]) -> Optional[float]:
    """
    Sharpe ratio in R-multiple space.
    Mean R / Std R — measures consistency of edge.
    >0.5 is acceptable; >1.0 is excellent for a discretionary system.
    """
    if len(r_series) < 4:
        return None
    mean = sum(r_series) / len(r_series)
    try:
        std = statistics.stdev(r_series)
    except Exception:
        return None
    return round(mean / std, 3) if std > 0 else None


def profit_factor(r_series: list[float]) -> Optional[float]:
    """Gross wins / |Gross losses|. >1.5 is good, >2.0 is excellent."""
    gross_win  = sum(r for r in r_series if r > 0)
    gross_loss = abs(sum(r for r in r_series if r < 0))
    return round(gross_win / gross_loss, 3) if gross_loss > 0 else None


def strategy_breakdown(signals: list[dict]) -> dict[str, dict]:
    """
    Per-strategy statistics: {strategy_name: {win_rate, expectancy, pf, n, total_r}}
    """
    by_strat: dict[str, list[float]] = {}
    for s in signals:
        if s.get("outcome") == "OPEN" or s.get("net_pnl_r") is None:
            continue
        strat = s.get("strategy") or "Unknown"
        by_strat.setdefault(strat, []).append(float(s["net_pnl_r"]))

    result = {}
    for strat, rs in by_strat.items():
        exp = expectancy(rs)
        result[strat] = {
            "n":          len(rs),
            "win_rate":   exp["win_rate"],
            "expectancy": exp["expectancy"],
            "pf":         profit_factor(rs),
            "sharpe_r":   sharpe_r(rs),
            "total_r":    round(sum(rs), 2),
            "max_dd_r":   max_drawdown_r(rs),
        }
    return dict(sorted(result.items(), key=lambda x: x[1]["total_r"], reverse=True))


def full_report(signals: list[dict]) -> dict:
    """
    Compute the complete quality report for a set of closed signals.
    Returns a flat dict suitable for display.
    """
    rs = _r_series(signals)
    if not rs:
        return {}

    exp  = expectancy(rs)
    stk  = win_loss_streaks(rs)
    dd   = max_drawdown_r(rs)
    ui   = ulcer_index(rs)
    cal  = calmar_ratio(rs)
    rf   = recovery_factor(rs)
    sh   = sharpe_r(rs)
    pf   = profit_factor(rs)

    return {
        # Core
        "n_trades":        len(rs),
        "total_r":         round(sum(rs), 2),
        "win_rate":        exp["win_rate"],
        "avg_win_r":       exp["avg_win_r"],
        "avg_loss_r":      exp["avg_loss_r"],
        "expectancy":      exp["expectancy"],
        # Risk metrics
        "max_drawdown_r":  dd,
        "ulcer_index":     ui,
        "calmar_ratio":    cal,
        "recovery_factor": rf,
        # Consistency
        "sharpe_r":        sh,
        "profit_factor":   pf,
        "max_win_streak":  stk["max_win_streak"],
        "max_loss_streak": stk["max_loss_streak"],
        "current_streak":  stk["current_streak"],
        "current_streak_type": stk["current_streak_type"],
        # Curve
        "equity_curve":    equity_curve(rs),
    }
