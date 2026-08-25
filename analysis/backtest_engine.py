"""
Vectorised backtest engine — daily bars, pandas-based.

Lookahead bias prevention:
  - Indicators computed on bar N are only used to enter on bar N+1's open
  - SL/TP checked intrabar against that bar's high/low

Survivorship bias note:
  - Universe is user-specified; historical data from yfinance includes
    delisted symbols only if still in the user's list — caveat documented.

yfinance known limitations (flagged as comments):
  - Adjusted close: yfinance returns adjusted OHLCV by default (auto_adjust=True).
    Split/dividend-adjusted data is correct for return calculations.
  - Rate limits: ~2k requests/hour. Batching via multi-ticker download.
  - Missing data: gaps exist for illiquid days; filled forward.
  - Max history: daily goes back to IPO for most NSE stocks.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str, years: int = 3) -> pd.DataFrame | None:
    """
    Download daily OHLCV. Returns None on failure.
    auto_adjust=True: prices are split & dividend adjusted (correct for returns).
    """
    end   = datetime.now()
    start = end - timedelta(days=int(years * 365.25))
    try:
        df = yf.download(
            ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
            interval="1d", auto_adjust=True, progress=False, timeout=20,
        )
        if df is None or df.empty:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(how="all", inplace=True)
        # Forward-fill intraday gaps (public holidays, illiquid days)
        df.ffill(inplace=True)
        df.dropna(inplace=True)
        return df
    except Exception as exc:
        logger.warning("fetch_ohlcv %s: %s", ticker, exc)
        return None


# ── Indicator computation ──────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame, conditions: list[dict]) -> pd.DataFrame:
    """Add indicator columns to df based on the conditions list. Returns df copy."""
    df = df.copy()
    close = df["Close"]
    vol   = df["Volume"]

    for cond in conditions:
        ind    = cond.get("indicator", "")
        period = int(cond.get("period") or 14)
        col    = f"{ind}_{period}" if cond.get("period") else ind

        if col in df.columns:
            continue

        if ind == "RSI":
            df[col] = _rsi(close, period)
        elif ind == "SMA":
            df[col] = close.rolling(period).mean()
        elif ind == "EMA":
            df[col] = close.ewm(span=period, adjust=False).mean()
        elif ind == "MACD":
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            df["MACD"] = macd_line
            df["MACD_signal"] = macd_line.ewm(span=9, adjust=False).mean()
            df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
        elif ind == "BB_UPPER":
            sma  = close.rolling(period).mean()
            std  = close.rolling(period).std()
            df[col] = sma + 2 * std
        elif ind == "BB_LOWER":
            sma  = close.rolling(period).mean()
            std  = close.rolling(period).std()
            df[col] = sma - 2 * std
        elif ind == "ATR":
            hl = df["High"] - df["Low"]
            hc = (df["High"] - close.shift(1)).abs()
            lc = (df["Low"]  - close.shift(1)).abs()
            tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            df[col] = tr.rolling(period).mean()
        elif ind == "VOLUME":
            df["VOLUME_avg20"] = vol.rolling(20).mean()
            df["VOLUME"] = vol
        elif ind == "PRICE":
            df["PRICE"] = close

    return df


# ── Signal generation ──────────────────────────────────────────────────────────

def _resolve_col(ind: str, period) -> str:
    return f"{ind}_{period}" if period else ind


def _apply_condition(df: pd.DataFrame, cond: dict) -> pd.Series:
    ind      = cond["indicator"]
    period   = cond.get("period")
    operator = cond["operator"]
    value    = cond.get("value")
    ref      = cond.get("reference")  # another indicator column

    col   = _resolve_col(ind, period)
    close = df["Close"]

    if col not in df.columns:
        logger.warning("Indicator column %s not found — condition skipped", col)
        return pd.Series(False, index=df.index)

    series = df[col]
    rhs    = df[ref] if ref and ref in df.columns else pd.Series(value, index=df.index)

    if operator == "lt":
        return series < rhs
    if operator == "gt":
        return series > rhs
    if operator == "lte":
        return series <= rhs
    if operator == "gte":
        return series >= rhs
    if operator == "crosses_above":
        return (series > rhs) & (series.shift(1) <= rhs.shift(1))
    if operator == "crosses_below":
        return (series < rhs) & (series.shift(1) >= rhs.shift(1))
    if operator == "rising":
        n = int(value or 1)
        return series.diff(n) > 0
    if operator == "falling":
        n = int(value or 1)
        return series.diff(n) < 0
    return pd.Series(False, index=df.index)


def generate_signals(df: pd.DataFrame, conditions: list[dict], logic: str = "AND") -> pd.Series:
    if not conditions:
        return pd.Series(False, index=df.index)
    masks = [_apply_condition(df, c) for c in conditions]
    if logic == "OR":
        combined = masks[0]
        for m in masks[1:]:
            combined = combined | m
    else:
        combined = masks[0]
        for m in masks[1:]:
            combined = combined & m
    return combined.fillna(False)


# ── Trade simulation ────────────────────────────────────────────────────────────

def simulate_trades(
    df: pd.DataFrame,
    ticker: str,
    entry_signals: pd.Series,
    exit_signals: pd.Series,
    sl_pct: float | None,
    tp_pct: float | None,
    trailing_pct: float | None,
    max_holding: int | None,
    pct_of_capital: float,
    commission_pct: float,
    initial_capital: float,
) -> list[dict]:
    """
    Event-driven daily loop.
    Entry: next bar open after signal.
    SL/TP: checked against intrabar high/low — no lookahead.
    Returns list of closed trade dicts.
    """
    closes  = df["Close"].values
    opens   = df["Open"].values
    highs   = df["High"].values
    lows    = df["Low"].values
    entries = entry_signals.values
    exits   = exit_signals.values
    dates   = df.index

    trades       = []
    in_trade     = False
    entry_price  = 0.0
    entry_date   = None
    shares       = 0.0
    trail_high   = 0.0
    holding_days = 0
    capital      = initial_capital

    for i in range(1, len(df)):
        if not in_trade:
            if entries[i - 1]:
                entry_price  = opens[i]
                shares       = (capital * pct_of_capital) / entry_price if entry_price > 0 else 0
                if shares <= 0:
                    continue
                entry_date   = dates[i]
                trail_high   = highs[i]
                in_trade     = True
                holding_days = 1
            continue

        # Update trailing stop reference
        trail_high = max(trail_high, highs[i])
        holding_days += 1
        exit_price = None
        exit_reason = ""

        sl_price  = entry_price * (1 - sl_pct / 100) if sl_pct else None
        tp_price  = entry_price * (1 + tp_pct / 100) if tp_pct else None
        tr_price  = trail_high * (1 - trailing_pct / 100) if trailing_pct else None

        # Intrabar stop/target checks (worst-case: SL before TP on same bar)
        if sl_price and lows[i] <= sl_price:
            exit_price  = sl_price
            exit_reason = "STOP_LOSS"
        elif tp_price and highs[i] >= tp_price:
            exit_price  = tp_price
            exit_reason = "TAKE_PROFIT"
        elif tr_price and lows[i] <= tr_price:
            exit_price  = tr_price
            exit_reason = "TRAILING_STOP"
        elif max_holding and holding_days >= max_holding:
            exit_price  = closes[i]
            exit_reason = "MAX_HOLDING"
        elif exits[i - 1]:
            exit_price  = closes[i]
            exit_reason = "EXIT_SIGNAL"

        if exit_price:
            commission = commission_pct / 100 * (entry_price + exit_price) * shares
            gross_pnl  = (exit_price - entry_price) * shares
            net_pnl    = gross_pnl - commission
            capital   += net_pnl

            trades.append({
                "ticker":      ticker,
                "entry_date":  str(entry_date.date() if hasattr(entry_date, "date") else entry_date),
                "exit_date":   str(dates[i].date() if hasattr(dates[i], "date") else dates[i]),
                "entry_price": round(entry_price, 2),
                "exit_price":  round(exit_price, 2),
                "shares":      round(shares, 2),
                "gross_pnl":   round(gross_pnl, 2),
                "net_pnl":     round(net_pnl, 2),
                "return_pct":  round((exit_price / entry_price - 1) * 100, 2),
                "holding_days": holding_days,
                "exit_reason": exit_reason,
                "capital_after": round(capital, 2),
            })
            in_trade = False
            shares   = 0

    return trades


# ── Equity curve ───────────────────────────────────────────────────────────────

def build_equity_curve(trades: list[dict], initial_capital: float) -> list[dict]:
    if not trades:
        return []
    equity = initial_capital
    peak   = initial_capital
    curve  = []
    for t in sorted(trades, key=lambda x: x["exit_date"]):
        equity = t["capital_after"]
        peak   = max(peak, equity)
        dd_pct = (peak - equity) / peak * 100 if peak > 0 else 0
        curve.append({
            "date":     t["exit_date"],
            "equity":   round(equity, 2),
            "drawdown": round(dd_pct, 2),
        })
    return curve


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_metrics(trades: list[dict], equity_curve: list[dict], initial_capital: float) -> dict:
    if not trades:
        return {}

    returns = [t["return_pct"] / 100 for t in trades]
    wins    = [r for r in returns if r > 0]
    losses  = [r for r in returns if r <= 0]

    final_equity  = equity_curve[-1]["equity"] if equity_curve else initial_capital
    first_date    = trades[0]["entry_date"]
    last_date     = trades[-1]["exit_date"]
    years         = (datetime.strptime(last_date, "%Y-%m-%d") -
                     datetime.strptime(first_date, "%Y-%m-%d")).days / 365.25
    years         = max(years, 0.01)

    cagr          = (final_equity / initial_capital) ** (1 / years) - 1
    win_rate      = len(wins) / len(trades)
    avg_win       = float(np.mean(wins)) if wins else 0
    avg_loss      = float(np.mean(losses)) if losses else 0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    max_dd        = max((p["drawdown"] for p in equity_curve), default=0)

    # Sharpe ratio (annualised, risk-free = 6% — approximate Indian Tbill rate)
    risk_free_daily = 0.06 / 252
    trade_returns   = np.array(returns)
    excess_returns  = trade_returns - risk_free_daily
    sharpe = (float(np.mean(excess_returns)) / float(np.std(excess_returns)) * math.sqrt(252)
              if len(excess_returns) > 1 and np.std(excess_returns) > 0 else 0)

    return {
        "total_trades":    len(trades),
        "win_rate":        round(win_rate * 100, 1),
        "avg_win_pct":     round(avg_win * 100, 2),
        "avg_loss_pct":    round(avg_loss * 100, 2),
        "profit_factor":   round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        "cagr_pct":        round(cagr * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio":    round(sharpe, 2),
        "initial_capital": round(initial_capital, 2),
        "final_equity":    round(final_equity, 2),
        "total_return_pct": round((final_equity / initial_capital - 1) * 100, 2),
        "backtest_years":  round(years, 1),
    }


# ── Main entry point ───────────────────────────────────────────────────────────

def run_backtest(spec: dict) -> dict:
    """
    Execute backtest for all tickers in spec["universe"].
    Returns dict: {trades, equity_curve, metrics, warnings, spec}.
    """
    all_trades: list[dict] = []
    warnings:   list[str]  = []

    initial_capital = float(spec.get("initial_capital", 100000))
    pct_of_capital  = float(spec["position_sizing"]["pct_of_capital"]) / 100
    max_positions   = int(spec["position_sizing"].get("max_positions", 5))
    commission_pct  = float(spec.get("commission_pct", 0.1))
    lookback_years  = int(spec.get("lookback_years", 3))
    sl_pct          = spec["exit"].get("stop_loss_pct")
    tp_pct          = spec["exit"].get("take_profit_pct")
    trailing_pct    = spec["exit"].get("trailing_stop_pct")
    max_holding     = spec["exit"].get("max_holding_days")
    entry_logic     = spec.get("entry_logic", "AND")

    for ticker in spec["universe"]:
        df = fetch_ohlcv(ticker, lookback_years)
        if df is None or df.empty:
            warnings.append(f"No data for {ticker} — skipped")
            continue
        if len(df) < 50:
            warnings.append(f"{ticker}: only {len(df)} bars — insufficient history")
            continue

        all_conditions = (spec.get("entry_conditions", []) +
                          spec["exit"].get("exit_conditions", []))
        df = compute_indicators(df, all_conditions)

        entry_sigs = generate_signals(df, spec.get("entry_conditions", []), entry_logic)
        exit_sigs  = generate_signals(df, spec["exit"].get("exit_conditions", []), "OR")

        trades = simulate_trades(
            df=df, ticker=ticker,
            entry_signals=entry_sigs, exit_signals=exit_sigs,
            sl_pct=sl_pct, tp_pct=tp_pct,
            trailing_pct=trailing_pct, max_holding=max_holding,
            pct_of_capital=min(pct_of_capital, 1.0 / max_positions),
            commission_pct=commission_pct,
            initial_capital=initial_capital,
        )
        all_trades.extend(trades)

    if not all_trades:
        return {
            "trades": [], "equity_curve": [], "metrics": {},
            "warnings": warnings or ["No trades were generated — check entry conditions"],
            "spec": spec,
        }

    all_trades.sort(key=lambda t: t["entry_date"])
    equity_curve = build_equity_curve(all_trades, initial_capital)
    metrics      = compute_metrics(all_trades, equity_curve, initial_capital)

    return {
        "trades":       all_trades,
        "equity_curve": equity_curve,
        "metrics":      metrics,
        "warnings":     warnings,
        "spec":         spec,
    }
