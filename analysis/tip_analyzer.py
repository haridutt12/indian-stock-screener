"""
Tip Analyzer — parses WhatsApp/Telegram stock tips and returns a credibility verdict.

Pipeline:
  1. Claude (Haiku) extracts structured fields from raw tip text
  2. yfinance fetches price, volume, and fundamentals
  3. Rule-based scoring: pump risk + technical alignment + risk:reward
  4. Claude (Sonnet) synthesizes a plain-English verdict
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
HAIKU_MODEL  = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"


# ── Client ─────────────────────────────────────────────────────────────────────

def _client():
    try:
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            try:
                import streamlit as st
                key = st.secrets.get("ANTHROPIC_API_KEY", "")
            except Exception:
                pass
        return anthropic.Anthropic(api_key=key) if key else None
    except ImportError:
        return None


# ── Step 1: Parse tip text ─────────────────────────────────────────────────────

PARSE_PROMPT = """Extract trade details from this Indian stock market tip message. Return valid JSON only — no extra text.

TIP:
{tip}

Return exactly this JSON structure (use null for unknown fields):
{{
  "ticker": "NSE symbol in uppercase (e.g. RELIANCE, TCS, IRFC). Strip .NS if present.",
  "company_name": "Full company name if mentioned",
  "action": "BUY or SELL",
  "tip_price": <number or null>,
  "stop_loss": <number or null>,
  "target_1": <number or null>,
  "target_2": <number or null>,
  "timeframe": "INTRADAY or SWING or POSITIONAL or unknown",
  "claims": ["list every claim made, e.g. 'operator backing', 'strong breakout', 'guaranteed returns', 'news catalyst'"],
  "parse_confidence": "HIGH or MEDIUM or LOW"
}}"""


def parse_tip(tip_text: str) -> dict:
    """Use Claude Haiku to extract structured fields from raw tip text."""
    c = _client()
    if not c:
        return {"error": "ANTHROPIC_API_KEY not configured"}
    try:
        resp = c.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": PARSE_PROMPT.format(tip=tip_text)}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        logger.error(f"Tip parse failed: {exc}")
        return {"error": str(exc)}


# ── Step 2: Fetch and score ────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def analyze_tip(parsed: dict) -> dict:
    """
    Run technical, volume, fundamental, and pump-risk analysis.
    Returns a flat dict of all scores, flags, and the preliminary verdict.
    """
    ticker = (parsed.get("ticker") or "").strip().upper().replace(".NS", "")
    if not ticker:
        return {"error": "Could not identify a stock ticker from the tip."}

    # ── Fetch data ──────────────────────────────────────────────────────────────
    ticker_ns = f"{ticker}.NS"
    stock = yf.Ticker(ticker_ns)
    df    = stock.history(period="6mo", interval="1d", auto_adjust=True)

    # Fallback: try BSE if NSE returns nothing
    if df.empty:
        stock     = yf.Ticker(f"{ticker}.BO")
        df        = stock.history(period="6mo", interval="1d", auto_adjust=True)
        ticker_ns = f"{ticker}.BO"

    if df.empty:
        return {"error": f"No price data found for '{ticker}'. Check the NSE symbol."}

    info = {}
    try:
        info = stock.fast_info.__dict__ if hasattr(stock, "fast_info") else {}
        # Supplement with slower info for fundamentals
        slow = stock.info
        info.update(slow)
    except Exception:
        pass

    df.index = pd.to_datetime(df.index)

    # ── Basic price ─────────────────────────────────────────────────────────────
    current_price = float(df["Close"].iloc[-1])
    tip_price     = parsed.get("tip_price")
    sl            = parsed.get("stop_loss")
    t1            = parsed.get("target_1")
    t2            = parsed.get("target_2")
    action        = (parsed.get("action") or "BUY").upper()

    price_drift_pct: Optional[float] = None
    if tip_price:
        price_drift_pct = (current_price - tip_price) / tip_price * 100

    # ── Volume ──────────────────────────────────────────────────────────────────
    avg_vol_20 = float(df["Volume"].rolling(20).mean().iloc[-1])
    today_vol  = float(df["Volume"].iloc[-1])
    vol_ratio  = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

    # ── Moving averages ─────────────────────────────────────────────────────────
    sma20  = float(df["Close"].rolling(20).mean().iloc[-1])
    sma50  = float(df["Close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else sma20
    sma200 = float(df["Close"].rolling(200).mean().iloc[-1]) if len(df) >= 200 else sma20
    above_sma20  = current_price > sma20
    above_sma50  = current_price > sma50
    above_sma200 = current_price > sma200
    pct_above_sma20 = (current_price - sma20) / sma20 * 100

    # ── RSI ─────────────────────────────────────────────────────────────────────
    rsi = _rsi(df["Close"]) if len(df) >= 16 else 50.0

    # ── Fundamentals ────────────────────────────────────────────────────────────
    market_cap    = info.get("marketCap") or 0
    market_cap_cr = market_cap / 1e7 if market_cap else 0
    pe            = info.get("trailingPE")
    sector        = info.get("sector", "")
    company_name  = info.get("longName", parsed.get("company_name", ticker))

    # ── Risk : Reward ───────────────────────────────────────────────────────────
    ref = tip_price or current_price
    rr, sl_pct, t1_pct = None, None, None
    if sl and t1 and ref and ref != sl:
        risk   = abs(ref - sl)
        reward = abs(t1 - ref)
        rr     = round(reward / risk, 2) if risk else None
    if sl and ref:
        sl_pct = round(abs(ref - sl) / ref * 100, 2)
    if t1 and ref:
        t1_pct = round(abs(t1 - ref) / ref * 100, 2)

    # ── Pump-risk score (0–100) ─────────────────────────────────────────────────
    pump_score = 0
    pump_flags = []

    if vol_ratio >= 5:
        pump_score += 35
        pump_flags.append(f"🚨 Volume {vol_ratio:.1f}× above 20-day average — extreme spike, classic pump signal")
    elif vol_ratio >= 3:
        pump_score += 22
        pump_flags.append(f"⚠️ Volume {vol_ratio:.1f}× above average — significant unusual activity")
    elif vol_ratio >= 2:
        pump_score += 10
        pump_flags.append(f"Volume {vol_ratio:.1f}× above average — elevated but not alarming")

    if 0 < market_cap_cr < 500:
        pump_score += 28
        pump_flags.append(f"🚨 Micro/small cap (₹{market_cap_cr:.0f} Cr) — easiest to manipulate")
    elif 0 < market_cap_cr < 2000:
        pump_score += 12
        pump_flags.append(f"Small-mid cap (₹{market_cap_cr:.0f} Cr) — moderate manipulation risk")

    if rsi > 78:
        pump_score += 22
        pump_flags.append(f"🚨 RSI {rsi:.0f} — severely overbought, likely already pumped; late entry")
    elif rsi > 68:
        pump_score += 12
        pump_flags.append(f"RSI {rsi:.0f} — overbought, chasing an extended move")

    if pct_above_sma20 > 12:
        pump_score += 15
        pump_flags.append(f"Price {pct_above_sma20:.1f}% above 20-day average — stretched, mean-reversion risk")

    claims_str = " ".join(c.lower() for c in parsed.get("claims", []))
    red_words  = ["operator", "guaranteed", "100%", "sure shot", "sureshot", "no risk",
                  "jackpot", "multibagger alert", "urgent", "limited time"]
    hit_words  = [w for w in red_words if w in claims_str]
    if hit_words:
        pump_score += 20
        pump_flags.append(f"🚨 Red-flag language detected: '{', '.join(hit_words)}' — common in pump-and-dump tips")

    pump_score = min(pump_score, 100)

    if not pump_flags:
        pump_flags.append("No obvious pump signals detected in this tip.")

    # ── Technical score (0–100, higher = more favourable for stated action) ─────
    tech_score = 50
    tech_flags = []

    if action == "BUY":
        if above_sma200:
            tech_score += 14
            tech_flags.append("✅ Price above 200-day MA — long-term uptrend intact")
        else:
            tech_score -= 16
            tech_flags.append("❌ Price below 200-day MA — buying against long-term trend")

        if above_sma50:
            tech_score += 10
            tech_flags.append("✅ Price above 50-day MA — medium-term trend supportive")
        else:
            tech_score -= 10
            tech_flags.append("❌ Price below 50-day MA — medium-term downtrend")

        if rsi < 30:
            tech_score += 18
            tech_flags.append(f"✅ RSI {rsi:.0f} — oversold, high probability bounce zone")
        elif rsi < 45:
            tech_score += 10
            tech_flags.append(f"✅ RSI {rsi:.0f} — healthy dip, good entry range")
        elif rsi <= 60:
            tech_score += 5
            tech_flags.append(f"RSI {rsi:.0f} — neutral, neither overbought nor oversold")
        elif rsi <= 70:
            tech_score -= 8
            tech_flags.append(f"⚠️ RSI {rsi:.0f} — approaching overbought territory")
        else:
            tech_score -= 18
            tech_flags.append(f"❌ RSI {rsi:.0f} — overbought; high risk of reversal at entry")

        if price_drift_pct is not None:
            if price_drift_pct > 8:
                tech_score -= 20
                tech_flags.append(f"❌ Current price already {price_drift_pct:.1f}% above tip price — tip is stale, you'd be buying the top")
            elif price_drift_pct > 3:
                tech_score -= 8
                tech_flags.append(f"⚠️ Price has moved {price_drift_pct:.1f}% since tip — entry is slightly late")
            elif price_drift_pct < -5:
                tech_score += 8
                tech_flags.append(f"✅ Price {abs(price_drift_pct):.1f}% below tip price — may be a better entry than suggested")

    else:  # SELL / SHORT
        if not above_sma200:
            tech_score += 14
            tech_flags.append("✅ Price below 200-day MA — downtrend supports short/sell")
        if rsi > 70:
            tech_score += 16
            tech_flags.append(f"✅ RSI {rsi:.0f} — overbought, good short entry zone")
        elif rsi > 60:
            tech_score += 8
            tech_flags.append(f"✅ RSI {rsi:.0f} — elevated, momentum may slow")

    tech_score = max(0, min(100, tech_score))

    if not tech_flags:
        tech_flags.append("Insufficient data for full technical assessment.")

    # ── R:R quality ─────────────────────────────────────────────────────────────
    rr_flag = ""
    if rr is None:
        rr_flag = "Risk:Reward cannot be calculated — stop loss or target not specified in tip"
    elif rr < 1:
        rr_flag = f"❌ R:R of 1:{rr:.1f} is below 1 — you risk more than you stand to gain"
    elif rr < 1.5:
        rr_flag = f"⚠️ R:R of 1:{rr:.1f} is below the recommended minimum of 1:1.5"
    elif rr < 2.5:
        rr_flag = f"✅ R:R of 1:{rr:.1f} — acceptable trade structure"
    else:
        rr_flag = f"✅ R:R of 1:{rr:.1f} — excellent trade structure"

    # ── Preliminary verdict ──────────────────────────────────────────────────────
    if pump_score >= 55:
        verdict, verdict_color, verdict_icon = "LIKELY PUMP", "#ff4d6d", "🚨"
    elif pump_score >= 35 or tech_score < 32:
        verdict, verdict_color, verdict_icon = "HIGH RISK",   "#ff9800", "⚠️"
    elif tech_score >= 62 and pump_score < 22 and (rr is None or rr >= 1.5):
        verdict, verdict_color, verdict_icon = "CREDIBLE",    "#00c896", "✅"
    else:
        verdict, verdict_color, verdict_icon = "MIXED",       "#f0b429", "🔶"

    return {
        "ticker":          ticker,
        "ticker_ns":       ticker_ns,
        "company_name":    company_name,
        "sector":          sector,
        "current_price":   round(current_price, 2),
        "tip_price":       tip_price,
        "price_drift_pct": round(price_drift_pct, 2) if price_drift_pct is not None else None,
        "vol_ratio":       round(vol_ratio, 2),
        "today_vol":       int(today_vol),
        "avg_vol_20":      int(avg_vol_20),
        "rsi":             round(rsi, 1),
        "above_sma20":     above_sma20,
        "above_sma50":     above_sma50,
        "above_sma200":    above_sma200,
        "pct_above_sma20": round(pct_above_sma20, 2),
        "market_cap_cr":   round(market_cap_cr, 0),
        "pe":              round(pe, 1) if pe else None,
        "rr":              rr,
        "sl_pct":          sl_pct,
        "t1_pct":          t1_pct,
        "pump_score":      pump_score,
        "pump_flags":      pump_flags,
        "tech_score":      tech_score,
        "tech_flags":      tech_flags,
        "rr_flag":         rr_flag,
        "verdict":         verdict,
        "verdict_color":   verdict_color,
        "verdict_icon":    verdict_icon,
    }


# ── Step 3: Claude AI synthesis ────────────────────────────────────────────────

VERDICT_PROMPT = """You are a straight-talking senior Indian market analyst. A retail investor just received this stock tip on WhatsApp and wants to know if they should act on it.

PARSED TIP:
Stock: {ticker} ({company_name})
Action: {action} at ₹{tip_price}
Stop Loss: ₹{sl}  |  Target 1: ₹{t1}  |  Target 2: ₹{t2}
Claims in tip: {claims}

ANALYSIS RESULTS:
Current market price: ₹{current_price} ({drift})
Volume: {vol_ratio:.1f}× above 20-day average
RSI: {rsi:.0f}
Trend: {sma50_trend} 50-day MA, {sma200_trend} 200-day MA
Market cap: {mcap}
Risk:Reward: {rr}
Pump risk score: {pump_score}/100
Technical score: {tech_score}/100
System verdict: {verdict}

In 4–5 sentences of plain English (no bullet points, no markdown):
1. Give a clear verdict on whether this tip is credible, risky, or a likely pump-and-dump
2. Name the 2 most important factors driving your assessment
3. State one specific, actionable thing the retail investor should do or check before placing any order
4. If the tip looks dangerous, say so bluntly — being diplomatic here costs people money

Write as if you're a trusted friend who happens to be an expert, not a formal report."""


def get_ai_verdict(parsed: dict, analysis: dict) -> str:
    """Return Claude's plain-English synthesis of the tip analysis."""
    c = _client()
    if not c:
        return "AI verdict unavailable — ANTHROPIC_API_KEY not configured."

    sl  = parsed.get("stop_loss")
    t1  = parsed.get("target_1")
    t2  = parsed.get("target_2")
    rr  = analysis.get("rr")
    mcap_cr = analysis.get("market_cap_cr", 0)

    try:
        resp = c.messages.create(
            model=SONNET_MODEL,
            max_tokens=350,
            messages=[{
                "role": "user",
                "content": VERDICT_PROMPT.format(
                    ticker       = analysis.get("ticker"),
                    company_name = analysis.get("company_name", ""),
                    action       = parsed.get("action", "BUY"),
                    tip_price    = parsed.get("tip_price", "not stated"),
                    sl           = f"₹{sl}" if sl else "not stated",
                    t1           = f"₹{t1}" if t1 else "not stated",
                    t2           = f"₹{t2}" if t2 else "not stated",
                    claims       = ", ".join(parsed.get("claims", [])) or "none stated",
                    current_price= analysis.get("current_price"),
                    drift        = (f"{analysis['price_drift_pct']:+.1f}% vs tip price"
                                    if analysis.get("price_drift_pct") is not None else "tip price not given"),
                    vol_ratio    = analysis.get("vol_ratio", 1),
                    rsi          = analysis.get("rsi", 50),
                    sma50_trend  = "Above" if analysis.get("above_sma50") else "Below",
                    sma200_trend = "Above" if analysis.get("above_sma200") else "Below",
                    mcap         = f"₹{mcap_cr:,.0f} Cr" if mcap_cr else "unknown",
                    rr           = f"1:{rr:.1f}" if rr else "not calculable",
                    pump_score   = analysis.get("pump_score", 0),
                    tech_score   = analysis.get("tech_score", 50),
                    verdict      = analysis.get("verdict"),
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        logger.error(f"AI verdict failed: {exc}")
        return f"AI verdict unavailable: {exc}"
