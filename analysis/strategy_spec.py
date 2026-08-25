"""
Strategy spec: converts plain-English strategy descriptions to structured JSON.
LLM call → strict schema → validation → clarification if ambiguous.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

SUPPORTED_INDICATORS = {
    "RSI":      {"needs_period": True,  "default_period": 14},
    "SMA":      {"needs_period": True,  "default_period": 20},
    "EMA":      {"needs_period": True,  "default_period": 20},
    "MACD":     {"needs_period": False, "default_period": None},
    "BB_UPPER": {"needs_period": True,  "default_period": 20},
    "BB_LOWER": {"needs_period": True,  "default_period": 20},
    "VOLUME":   {"needs_period": False, "default_period": None},
    "PRICE":    {"needs_period": False, "default_period": None},
    "ATR":      {"needs_period": True,  "default_period": 14},
}

_OPERATORS = ["lt", "gt", "lte", "gte", "crosses_above", "crosses_below", "rising", "falling"]

_SYSTEM_PROMPT = """You are a quantitative trading strategy parser for Indian markets.
Convert the user's plain-English strategy into a strict JSON object.

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:
{
  "strategy_name": "Short descriptive name",
  "universe": ["TICKER.NS"],
  "entry_conditions": [
    {
      "indicator": "RSI|SMA|EMA|MACD|BB_UPPER|BB_LOWER|VOLUME|PRICE|ATR",
      "period": 14,
      "operator": "lt|gt|lte|gte|crosses_above|crosses_below|rising|falling",
      "value": 30.0,
      "reference": null
    }
  ],
  "entry_logic": "AND",
  "exit": {
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "trailing_stop_pct": null,
    "max_holding_days": null,
    "exit_conditions": []
  },
  "position_sizing": {
    "pct_of_capital": 10.0,
    "max_positions": 5
  },
  "initial_capital": 100000,
  "commission_pct": 0.1,
  "lookback_years": 3,
  "direction": "LONG",
  "clarification_needed": null
}

Rules:
- NSE stocks: add .NS suffix (RELIANCE → RELIANCE.NS)
- Nifty 50 index: ^NSEI, Bank Nifty: ^NSEBANK
- "Nifty 50 stocks" → use ["RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS"]
- For MACD: value is signal_line value (0 for crosses_above/below zero line)
- For VOLUME: value is multiplier of average (e.g. 1.5 = 50% above avg volume)
- For PRICE: reference is another indicator (e.g. "SMA_20") or value is a price level
- For "rising" / "falling" operators: value = number of consecutive periods (default 1)
- commission_pct: 0.1 for delivery, 0.02 for intraday
- If ambiguous (missing universe, unclear exits), set clarification_needed to a SPECIFIC question
- direction: always "LONG" unless user explicitly mentions shorting
- max_positions: how many stocks to hold simultaneously; default 5 for a universe, 1 for single ticker"""


def _call_llm(prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    try:
        if api_key:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("Claude call failed: %s", e)

    groq_key = os.environ.get("GROQ_API_KEY", "")
    try:
        if groq_key:
            import streamlit as st
            groq_key = groq_key or st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        pass
    try:
        if groq_key:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Groq call failed: %s", e)

    raise RuntimeError("No LLM available (set ANTHROPIC_API_KEY or GROQ_API_KEY)")


def _validate_spec(spec: dict) -> list[str]:
    """Returns list of validation errors."""
    errors = []
    if not spec.get("universe"):
        errors.append("universe: must contain at least one ticker")
    for i, cond in enumerate(spec.get("entry_conditions", [])):
        if cond.get("indicator") not in SUPPORTED_INDICATORS:
            errors.append(f"entry_conditions[{i}].indicator: '{cond.get('indicator')}' not supported")
        if cond.get("operator") not in _OPERATORS:
            errors.append(f"entry_conditions[{i}].operator: '{cond.get('operator')}' not supported")
    exit_ = spec.get("exit", {})
    sl = exit_.get("stop_loss_pct")
    tp = exit_.get("take_profit_pct")
    if sl is not None and sl <= 0:
        errors.append("exit.stop_loss_pct must be > 0")
    if tp is not None and tp <= 0:
        errors.append("exit.take_profit_pct must be > 0")
    if not exit_.get("exit_conditions") and sl is None and tp is None and not exit_.get("max_holding_days"):
        errors.append("exit: at least one exit rule required (stop_loss_pct, take_profit_pct, max_holding_days, or exit_conditions)")
    ps = spec.get("position_sizing", {})
    if not (0 < ps.get("pct_of_capital", 0) <= 100):
        errors.append("position_sizing.pct_of_capital must be between 0 and 100")
    return errors


def parse_strategy(text: str) -> dict:
    """
    Convert plain-English strategy to validated spec dict.
    Returns spec with 'clarification_needed' set if input is ambiguous,
    or 'validation_errors' list if spec is structurally invalid.
    """
    try:
        raw = _call_llm(text)
        # Strip markdown fences if LLM adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        spec = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s", e)
        return {"clarification_needed": "Could not parse your strategy. Please rephrase with explicit entry and exit rules."}
    except RuntimeError as e:
        return {"error": str(e)}

    errors = _validate_spec(spec)
    if errors:
        spec["validation_errors"] = errors

    # Ensure required keys exist with defaults
    spec.setdefault("initial_capital", 100000)
    spec.setdefault("commission_pct", 0.1)
    spec.setdefault("lookback_years", 3)
    spec.setdefault("direction", "LONG")
    spec.setdefault("entry_logic", "AND")
    spec.setdefault("position_sizing", {"pct_of_capital": 10.0, "max_positions": 5})

    return spec
