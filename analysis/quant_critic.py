"""
AI Quant Critic — deterministic metrics engine.

Computes a structured risk profile of a strategy's historical performance.
All numbers come from Python/pandas. The LLM receives the output and explains it —
it never calculates anything itself.

Public API
----------
compute_critic_metrics(signals) -> dict
    Main entry point. Returns the full metrics dict.
    Input: list of closed signal dicts from signal_logger.get_signals().

ai_critique(metrics) -> str
    Send metrics to Claude (or Groq fallback) and return a plain-text critique.
    Result should be cached by the caller.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Regime classification thresholds
_BULL_THRESHOLD  =  0.05   # Nifty 20-day return > 5%  → Bull
_BEAR_THRESHOLD  = -0.05   # Nifty 20-day return < -5% → Bear
# Between → Sideways

_MIN_SIGNIFICANT = 20      # Below this N, statistics are unreliable


# ── Nifty benchmark data ──────────────────────────────────────────────────────

def _fetch_nifty(days: int = 500) -> Optional[pd.Series]:
    """Return Nifty 50 adjusted daily close as a date-indexed Series."""
    try:
        import yfinance as yf
        df = yf.Ticker("^NSEI").history(period="2y", interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None
        s = df["Close"].copy()
        s.index = pd.to_datetime(s.index).normalize().tz_localize(None)
        return s
    except Exception as e:
        logger.debug("Nifty fetch failed: %s", e)
        return None


def _closest_price(series: pd.Series, target_date: date) -> Optional[float]:
    """Return the closest available price at or before target_date."""
    if series is None:
        return None
    ts = pd.Timestamp(target_date)
    subset = series[series.index <= ts]
    if subset.empty:
        return None
    return float(subset.iloc[-1])


# ── Regime classification ─────────────────────────────────────────────────────

def _classify_regime(nifty: pd.Series, signal_date: date, lookback: int = 20) -> str:
    ts = pd.Timestamp(signal_date)
    subset = nifty[nifty.index <= ts].tail(lookback + 1)
    if len(subset) < 2:
        return "Unknown"
    ret = (float(subset.iloc[-1]) - float(subset.iloc[0])) / float(subset.iloc[0])
    if ret > _BULL_THRESHOLD:
        return "Bull"
    if ret < _BEAR_THRESHOLD:
        return "Bear"
    return "Sideways"


# ── Individual metric blocks ──────────────────────────────────────────────────

def _sample_metrics(signals: list[dict]) -> dict:
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")]
    per_strategy: dict[str, int] = {}
    for s in closed:
        k = s.get("strategy", "Unknown")
        per_strategy[k] = per_strategy.get(k, 0) + 1

    n = len(closed)
    return {
        "n_total_closed":   n,
        "n_open":           len(signals) - n,
        "n_per_strategy":   per_strategy,
        "is_significant":   n >= _MIN_SIGNIFICANT,
        "significance_note": (
            f"Only {n} closed signals — statistics are unreliable below {_MIN_SIGNIFICANT}."
            if n < _MIN_SIGNIFICANT else
            f"{n} closed signals — borderline sample size." if n < 50 else
            f"{n} closed signals — reasonable sample."
        ),
    }


def _performance_metrics(signals: list[dict]) -> dict:
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")
              and s.get("net_pnl_r") is not None]
    if not closed:
        return {}

    r_net   = [float(s["net_pnl_r"]) for s in closed]
    r_gross = []
    for s in closed:
        # Approximate gross R from net + reconstruct cost delta
        gross = s.get("pnl_r") or s.get("net_pnl_r")
        r_gross.append(float(gross) if gross is not None else float(s["net_pnl_r"]))

    wins   = [r for r in r_net if r > 0]
    losses = [r for r in r_net if r <= 0]

    n = len(r_net)
    win_rate = len(wins) / n if n > 0 else 0
    exp_net  = float(np.mean(r_net)) if r_net else 0.0
    exp_gross = float(np.mean(r_gross)) if r_gross else 0.0

    # Rolling 10-trade win rate to detect regime shifts
    rolling_wr = []
    window = min(10, max(5, n // 4))
    for i in range(window - 1, n):
        chunk = r_net[i - window + 1 : i + 1]
        rolling_wr.append(round(len([x for x in chunk if x > 0]) / len(chunk), 3))

    # Profit factor
    gross_wins   = sum(wins) if wins else 0
    gross_losses = abs(sum(losses)) if losses else 0
    pf = round(gross_wins / gross_losses, 2) if gross_losses > 0 else None

    # Max drawdown in R
    equity = list(np.cumsum(r_net))
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    return {
        "n":              n,
        "win_rate":       round(win_rate, 3),
        "expectancy_net": round(exp_net, 3),
        "expectancy_gross": round(exp_gross, 3),
        "cost_drag":      round(exp_gross - exp_net, 3),
        "profit_factor":  pf,
        "max_drawdown_r": round(max_dd, 2),
        "avg_win_r":      round(float(np.mean(wins)), 2) if wins else 0.0,
        "avg_loss_r":     round(float(np.mean(losses)), 2) if losses else 0.0,
        "rolling_win_rate": rolling_wr,
        "equity_curve":   [round(v, 3) for v in equity],
    }


def _regime_metrics(signals: list[dict], nifty: Optional[pd.Series]) -> dict:
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")
              and s.get("net_pnl_r") is not None]
    if not closed or nifty is None:
        return {"available": False}

    by_regime: dict[str, list[float]] = {"Bull": [], "Bear": [], "Sideways": [], "Unknown": []}
    for s in closed:
        try:
            sd = date.fromisoformat(str(s["signal_date"])[:10])
        except Exception:
            continue
        regime = _classify_regime(nifty, sd)
        by_regime[regime].append(float(s["net_pnl_r"]))

    regime_stats = {}
    total_wins = 0
    dominant = "Unknown"
    dominant_n = 0
    for regime, rs in by_regime.items():
        if not rs:
            continue
        wins = [r for r in rs if r > 0]
        n = len(rs)
        if n > dominant_n:
            dominant_n = n
            dominant = regime
        total_wins += len(wins)
        regime_stats[regime] = {
            "n":         n,
            "win_rate":  round(len(wins) / n, 3) if n > 0 else 0,
            "avg_r":     round(float(np.mean(rs)), 3),
            "pct_trades": round(n / len(closed) * 100, 1),
        }

    # Regime concentration: does one regime drive the P&L?
    regime_r = {r: sum(by_regime[r]) for r in by_regime if by_regime[r]}
    total_r  = sum(regime_r.values())
    max_regime_name = max(regime_r, key=lambda k: abs(regime_r[k])) if regime_r else "Unknown"
    max_regime_pct  = round(abs(regime_r.get(max_regime_name, 0)) / abs(total_r) * 100, 1) if total_r != 0 else 0

    return {
        "available":         True,
        "by_regime":         regime_stats,
        "dominant_regime":   dominant,
        "p&l_regime":        max_regime_name,
        "p&l_regime_pct":    max_regime_pct,
        "regime_dependency_flag": max_regime_pct > 70,
    }


def _strategy_concentration(signals: list[dict]) -> dict:
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")]
    if not closed:
        return {}

    strat_wins: dict[str, int] = {}
    strat_n:    dict[str, int] = {}
    for s in closed:
        k = s.get("strategy", "Unknown")
        strat_n[k] = strat_n.get(k, 0) + 1
        r = s.get("net_pnl_r")
        if r is not None and float(r) > 0:
            strat_wins[k] = strat_wins.get(k, 0) + 1

    n_total = len(closed)
    # Herfindahl index of trade count (0=perfectly diverse, 1=one strategy)
    shares = [(v / n_total) ** 2 for v in strat_n.values()]
    hhi = round(sum(shares), 3)

    top_strategy = max(strat_n, key=strat_n.get) if strat_n else None
    top_pct = round(strat_n.get(top_strategy, 0) / n_total * 100, 1) if top_strategy else 0

    # P&L concentration: what fraction of winning trades come from one strategy?
    total_wins = sum(strat_wins.values())
    top_win_strat = max(strat_wins, key=strat_wins.get) if strat_wins else None
    top_win_pct = round(strat_wins.get(top_win_strat, 0) / total_wins * 100, 1) if total_wins > 0 else 0

    return {
        "n_strategies":        len(strat_n),
        "hhi":                 hhi,
        "top_strategy":        top_strategy,
        "top_strategy_pct":    top_pct,
        "top_win_strategy":    top_win_strat,
        "top_win_strategy_pct": top_win_pct,
        "concentration_flag":  top_win_pct > 60 or hhi > 0.4,
        "per_strategy": {
            k: {
                "n":       strat_n[k],
                "wins":    strat_wins.get(k, 0),
                "win_rate": round(strat_wins.get(k, 0) / strat_n[k], 3),
            }
            for k in strat_n
        },
    }


def _confidence_calibration(signals: list[dict]) -> dict:
    """Do higher-confidence signals actually outperform lower-confidence ones?"""
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")
              and s.get("net_pnl_r") is not None and s.get("confidence") is not None]
    if len(closed) < 10:
        return {"available": False}

    by_conf: dict[int, list[float]] = {}
    for s in closed:
        c = int(s["confidence"])
        by_conf.setdefault(c, []).append(float(s["net_pnl_r"]))

    calibration = {}
    for c in sorted(by_conf):
        rs = by_conf[c]
        calibration[c] = {
            "n":       len(rs),
            "avg_r":   round(float(np.mean(rs)), 3),
            "win_rate": round(len([r for r in rs if r > 0]) / len(rs), 3),
        }

    # Check monotonicity: does avg_r increase with confidence?
    avgs = [calibration[c]["avg_r"] for c in sorted(calibration)]
    is_monotone = all(avgs[i] <= avgs[i + 1] for i in range(len(avgs) - 1))

    return {
        "available":    True,
        "by_confidence": calibration,
        "is_well_calibrated": is_monotone,
        "calibration_note": (
            "Confidence scores appear to predict performance (higher conf → higher R)."
            if is_monotone else
            "Confidence scores are NOT monotone — higher-rated signals do not consistently outperform."
        ),
    }


def _benchmark_alpha(signals: list[dict], nifty: Optional[pd.Series]) -> dict:
    """Compare each signal's holding-period return against Nifty 50 buy-and-hold."""
    closed = [s for s in signals if s.get("outcome") not in (None, "OPEN")
              and s.get("signal_date") and s.get("outcome_at")]
    if not closed or nifty is None:
        return {"available": False}

    alphas = []
    for s in closed:
        try:
            sd = date.fromisoformat(str(s["signal_date"])[:10])
            ed = date.fromisoformat(str(s["outcome_at"])[:10])
        except Exception:
            continue

        p_start = _closest_price(nifty, sd)
        p_end   = _closest_price(nifty, ed)
        if p_start and p_end and p_start > 0:
            nifty_ret = (p_end - p_start) / p_start
            signal_ret = (float(s.get("net_pnl_pct", 0) or 0)) / 100
            alphas.append(signal_ret - nifty_ret)

    if not alphas:
        return {"available": False}

    avg_alpha = float(np.mean(alphas))
    positive_alpha_pct = round(len([a for a in alphas if a > 0]) / len(alphas) * 100, 1)

    return {
        "available":          True,
        "n_compared":         len(alphas),
        "avg_alpha_pct":      round(avg_alpha * 100, 2),
        "beat_benchmark_pct": positive_alpha_pct,
        "note": (
            f"Beats Nifty buy-and-hold on {positive_alpha_pct}% of trades "
            f"with avg alpha of {avg_alpha*100:+.2f}% per trade."
        ),
    }


# ── Main public function ──────────────────────────────────────────────────────

def compute_critic_metrics(signals: list[dict]) -> dict:
    """
    Compute all deterministic critic metrics from a list of signal dicts.
    Only closed signals are used for performance metrics.
    Fetches Nifty 50 data once for regime/benchmark calculations.
    """
    if not signals:
        return {"error": "No signals provided"}

    nifty = _fetch_nifty()

    return {
        "sample":         _sample_metrics(signals),
        "performance":    _performance_metrics(signals),
        "regime":         _regime_metrics(signals, nifty),
        "concentration":  _strategy_concentration(signals),
        "calibration":    _confidence_calibration(signals),
        "benchmark":      _benchmark_alpha(signals, nifty),
    }


def metrics_fingerprint(metrics: dict) -> str:
    """Stable hash of the metrics dict — use as cache key for the LLM call."""
    canonical = json.dumps(metrics, sort_keys=True, default=str)
    return hashlib.md5(canonical.encode()).hexdigest()[:16]


# ── AI critique ───────────────────────────────────────────────────────────────

_CRITIC_SYSTEM = """You are a rigorous, skeptical quantitative researcher reviewing a systematic trading strategy's historical performance data.

Your role is to identify weaknesses and risks, not to praise results.

Rules:
- Use ONLY the metrics provided in the JSON. Never invent numbers.
- Be specific — name the actual figures, not vague concerns.
- If sample size is below 20, lead with that. Statistics below N=20 are not meaningful.
- Be honest about what cannot be known from this data (survivorship bias, out-of-sample, parameter sensitivity).
- Do NOT give trading advice. Do NOT recommend buying or selling.

Respond in exactly this structure (use these exact markdown headers):

## Verdict
One sentence maximum. Include confidence level: High / Medium / Low.

## What the data shows
3-5 bullet points on observable facts from the metrics.

## Key risks
3-5 bullet points on specific concerns. Be concrete — cite actual numbers.

## What would change this view
1-2 sentences: what additional evidence would increase or decrease confidence."""

_CRITIC_USER_TEMPLATE = """Here are the performance metrics for this strategy:

```json
{metrics_json}
```

Provide your critical assessment."""


def ai_critique(metrics: dict) -> str:
    """
    Send computed metrics to Claude (or Groq fallback) and return the critique text.
    This function should be called with a cached wrapper in the UI.
    """
    metrics_json = json.dumps(metrics, indent=2, default=str)
    user_msg = _CRITIC_USER_TEMPLATE.format(metrics_json=metrics_json)

    # Try Claude first
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        try:
            import streamlit as st
            anthropic_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass

    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",   # fast + cheap for this structured task
                max_tokens=1024,
                system=_CRITIC_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            return msg.content[0].text
        except Exception as e:
            logger.warning("Claude critique failed, trying Groq: %s", e)

    # Groq fallback
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        try:
            import streamlit as st
            groq_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass

    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": _CRITIC_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error("Groq critique failed: %s", e)

    return (
        "⚠️ AI critique unavailable — no API key configured. "
        "Set ANTHROPIC_API_KEY or GROQ_API_KEY to enable the AI Critic."
    )
