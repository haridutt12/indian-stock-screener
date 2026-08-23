"""
Natural Language → Structured Screener Query translator.

Takes a plain-English query ("show me oversold quality stocks above 200 SMA")
and returns a validated filter specification that can be applied to any
technical or fundamental screening DataFrame.

Public API
----------
parse_nl_query(text: str) -> dict
    Call the LLM. Returns {"filters": [...], "sort_by": str, "sort_ascending": bool,
    "summary": str, "error": str|None}.

apply_nl_filters(df: pd.DataFrame, query: dict) -> pd.DataFrame
    Apply the parsed query to a DataFrame. Safe — unknown columns are skipped.
"""
from __future__ import annotations

import json
import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column catalogue ──────────────────────────────────────────────────────────
# Each entry: description and valid operators for the LLM's reference.
COLUMNS: dict[str, dict] = {
    "rsi": {
        "desc": "RSI momentum oscillator (0–100). Below 30 = oversold, above 70 = overbought.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte", "between"],
        "example": {"column": "rsi", "operator": "lt", "value": 35},
    },
    "tech_strength": {
        "desc": "Overall technical strength score (0–100). Higher = stronger.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "tech_strength", "operator": "gt", "value": 60},
    },
    "volume_ratio": {
        "desc": "Today's volume relative to 20-day average (e.g. 1.5 = 50% above normal).",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "volume_ratio", "operator": "gte", "value": 1.5},
    },
    "above_sma200": {
        "desc": "True if price is above 200-day SMA (long-term uptrend).",
        "type": "boolean",
        "ops": ["eq"],
        "example": {"column": "above_sma200", "operator": "eq", "value": True},
    },
    "above_sma50": {
        "desc": "True if price is above 50-day SMA.",
        "type": "boolean",
        "ops": ["eq"],
        "example": {"column": "above_sma50", "operator": "eq", "value": True},
    },
    "golden_cross": {
        "desc": "True if SMA50 has recently crossed above SMA200 (strong bullish signal).",
        "type": "boolean",
        "ops": ["eq"],
        "example": {"column": "golden_cross", "operator": "eq", "value": True},
    },
    "macd_bullish": {
        "desc": "True if MACD line is above signal line (bullish momentum).",
        "type": "boolean",
        "ops": ["eq"],
        "example": {"column": "macd_bullish", "operator": "eq", "value": True},
    },
    "vol_spike": {
        "desc": "True if volume is more than 1.5× average (breakout confirmation).",
        "type": "boolean",
        "ops": ["eq"],
        "example": {"column": "vol_spike", "operator": "eq", "value": True},
    },
    # Fundamental columns (available when build_screen_data is used)
    "pe": {
        "desc": "Price-to-Earnings ratio. Lower = cheaper valuation.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "pe", "operator": "lt", "value": 20},
    },
    "roe_pct": {
        "desc": "Return on Equity in percent. Higher = more efficient capital use.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "roe_pct", "operator": "gt", "value": 15},
    },
    "div_yield_pct": {
        "desc": "Dividend yield in percent.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "div_yield_pct", "operator": "gt", "value": 2},
    },
    "debt_equity": {
        "desc": "Debt-to-Equity ratio. Lower = less leveraged.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "debt_equity", "operator": "lt", "value": 50},
    },
    "profit_margin_pct": {
        "desc": "Net profit margin in percent.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "profit_margin_pct", "operator": "gt", "value": 10},
    },
    "composite_score": {
        "desc": "Composite fundamental quality score (0–1). Higher = better quality.",
        "type": "numeric",
        "ops": ["gt", "lt", "gte", "lte"],
        "example": {"column": "composite_score", "operator": "gt", "value": 0.6},
    },
}

_VALID_COLUMNS = set(COLUMNS.keys())
_VALID_OPS     = {"gt", "lt", "gte", "lte", "eq", "between"}

_SYSTEM = """You are a stock screener query parser for the Indian equity market (NSE).
Convert the user's natural-language request into a structured JSON filter specification.

Available columns and their meanings:
""" + "\n".join(
    f'  "{k}": {v["desc"]} (type: {v["type"]}, valid ops: {", ".join(v["ops"])})'
    for k, v in COLUMNS.items()
) + """

Valid operators: gt (>), lt (<), gte (>=), lte (<=), eq (==), between ([low, high]).

Rules:
- Only use columns from the list above. Do NOT invent new column names.
- For boolean columns, use operator "eq" with value true or false.
- For "between", value must be a JSON array [min, max].
- Keep filter values realistic (RSI is 0-100; volume_ratio around 1-3).
- If the user asks for "oversold", use RSI < 35.
- If the user asks for "overbought", use RSI > 70.
- If the user asks for "momentum" without a range, use RSI between 50 and 70.
- If the user says "quality" or "fundamentals", add composite_score > 0.5 and roe_pct > 15.
- If the user says "above 200 SMA" / "in uptrend" / "bullish long-term", set above_sma200 = true.
- If the user says "volume spike" / "high volume", use volume_ratio >= 1.5.
- sort_by must be one of the column names above, or null.
- summary: one sentence explaining what the filter does in plain English.

Respond with ONLY valid JSON, no explanation, no markdown fences. Schema:
{
  "filters": [{"column": "...", "operator": "...", "value": <number|bool|[n,n]>}],
  "sort_by": "<column>" or null,
  "sort_ascending": true or false,
  "summary": "..."
}"""


def parse_nl_query(text: str) -> dict:
    """
    Parse a plain-English screening query into a structured filter spec.
    Returns dict with keys: filters, sort_by, sort_ascending, summary, error.
    """
    prompt = f'Screen for: "{text}"'

    raw_json = _call_llm(prompt)
    if raw_json is None:
        return {"filters": [], "sort_by": None, "sort_ascending": False,
                "summary": text, "error": "LLM unavailable — no API key configured."}

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.warning("NL screener JSON parse error: %s | raw: %s", e, raw_json[:200])
        return {"filters": [], "sort_by": None, "sort_ascending": False,
                "summary": text, "error": f"Could not parse LLM response: {e}"}

    # Validate and sanitise filters
    validated = []
    errors = []
    for f in parsed.get("filters", []):
        col = f.get("column", "")
        op  = f.get("operator", "")
        val = f.get("value")

        if col not in _VALID_COLUMNS:
            errors.append(f"Unknown column '{col}' — skipped.")
            continue
        if op not in _VALID_OPS:
            errors.append(f"Invalid operator '{op}' for '{col}' — skipped.")
            continue
        if op == "between" and not (isinstance(val, list) and len(val) == 2):
            errors.append(f"'between' requires [min, max] array for '{col}' — skipped.")
            continue
        validated.append({"column": col, "operator": op, "value": val})

    sort_by = parsed.get("sort_by")
    if sort_by and sort_by not in _VALID_COLUMNS:
        sort_by = None

    return {
        "filters":       validated,
        "sort_by":       sort_by,
        "sort_ascending": bool(parsed.get("sort_ascending", False)),
        "summary":       parsed.get("summary", text),
        "error":         "; ".join(errors) if errors else None,
    }


def apply_nl_filters(df: pd.DataFrame, query: dict) -> pd.DataFrame:
    """Apply a parsed NL query to a DataFrame. Unknown columns are silently skipped."""
    result = df.copy()

    for f in query.get("filters", []):
        col = f["column"]
        op  = f["operator"]
        val = f["value"]

        if col not in result.columns:
            continue

        col_series = result[col]

        # Boolean columns — compare directly without numeric coercion
        if COLUMNS.get(col, {}).get("type") == "boolean":
            if op == "eq":
                result = result[col_series == val]
            continue

        numeric = pd.to_numeric(col_series, errors="coerce")
        if op == "gt":
            result = result[numeric > val]
        elif op == "lt":
            result = result[numeric < val]
        elif op == "gte":
            result = result[numeric >= val]
        elif op == "lte":
            result = result[numeric <= val]
        elif op == "eq":
            result = result[numeric == val]
        elif op == "between" and isinstance(val, list) and len(val) == 2:
            result = result[numeric.between(val[0], val[1])]

    sort_by = query.get("sort_by")
    if sort_by and sort_by in result.columns:
        result = result.sort_values(sort_by, ascending=bool(query.get("sort_ascending", False)))

    return result.reset_index(drop=True)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt: str) -> str | None:
    """Try Claude Haiku then Groq. Returns raw JSON string or None."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass

    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            logger.warning("Claude NL parse failed, trying Groq: %s", e)

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
                max_tokens=512,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error("Groq NL parse failed: %s", e)

    return None
