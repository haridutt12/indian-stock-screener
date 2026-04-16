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

def _get_api_key() -> str:
    """Return ANTHROPIC_API_KEY from env or Streamlit secrets."""
    # 1. OS environment (works locally via .env / Streamlit Cloud secrets inject)
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        return key
    # 2. Streamlit secrets (TOML secrets panel on Streamlit Cloud)
    try:
        import streamlit as st
        key = st.secrets["ANTHROPIC_API_KEY"]
        if key:
            return key
    except Exception:
        pass
    return ""


def _client():
    try:
        import anthropic
        key = _get_api_key()
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
    """Extract structured fields from raw tip text.
    Uses Claude Haiku when API key is available, otherwise falls back to regex."""
    c = _client()
    if c:
        try:
            resp = c.messages.create(
                model=HAIKU_MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": PARSE_PROMPT.format(tip=tip_text)}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as exc:
            logger.warning(f"Claude parse failed, falling back to regex: {exc}")

    return _parse_tip_regex(tip_text)


# ── Regex-based tip parser (no API required) ───────────────────────────────────

# Nifty 200 tickers for recognition (subset of common ones)
_KNOWN_TICKERS = {
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","TITAN",
    "SUNPHARMA","ULTRACEMCO","WIPRO","HCLTECH","NTPC","POWERGRID","ONGC",
    "TATAMOTORS","TATASTEEL","JSWSTEEL","GRASIM","TECHM","BAJFINANCE",
    "BAJAJFINSV","NESTLEIND","ADANIENT","ADANIPORTS","DIVISLAB","DRREDDY",
    "EICHERMOT","CIPLA","HEROMOTOCO","HINDALCO","INDUSINDBK","COALINDIA",
    "BRITANNIA","BPCL","TATACONSUM","APOLLOHOSP","BAJAJ-AUTO","LTIM",
    "SBILIFE","HDFCLIFE","UPL","M&M",
    # Popular mid/small caps frequently tipped
    "IRFC","IRCTC","ZOMATO","PAYTM","NYKAA","POLICYBZR","DMART","ADANIGREEN",
    "ADANIPOWER","ADANITRANS","TRENT","VEDL","SAIL","NMDC","RECLTD","PFC",
    "CANBK","BANKBARODA","UNIONBANK","IDFCFIRSTB","FEDERALBNK","RBLBANK",
    "JUBLFOOD","MUTHOOTFIN","CHOLAFIN","MANAPPURAM","LTTS","MPHASIS","COFORGE",
    "PERSISTENT","TATAPOWER","TORNTPOWER","HAVELLS","VOLTAS","GODREJCP",
    "PIDILITIND","BERGEPAINT","ATUL","DEEPAKNTR","AARTIIND","ALKYLAMINE",
    "LALPATHLAB","METROPOLIS","THYROCARE","FORTIS","MAXHEALTH","NH",
    "PAGEIND","RELAXO","BATAINDIA","VMART","ABFRL","MANYAVAR","VBL",
    "MARICO","DABUR","GODREJIND","COLPAL","EMAMILTD","GILLETTE",
    "YESBANK","BANDHANBNK","UJJIVAN","EQUITASBNK","SURYAROSNI","CGPOWER",
    "BEL","HAL","BHEL","BEML","MAZAGON","COCHINSHIP","GRSE","MIDHANI",
    "CONCOR","TIINDIA","ASTRAL","SUPREMEIND","APLAPOLLO","JINDALSAW",
}

# Company name → ticker mapping for common names people type out
_NAME_TO_TICKER = {
    "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
    "reliance": "RELIANCE", "reliance industries": "RELIANCE",
    "tcs": "TCS", "tata consultancy": "TCS",
    "infosys": "INFY", "infy": "INFY",
    "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "sbi": "SBIN", "state bank": "SBIN",
    "axis bank": "AXISBANK", "axis": "AXISBANK",
    "kotak bank": "KOTAKBANK", "kotak": "KOTAKBANK",
    "bajaj finance": "BAJFINANCE",
    "larsen": "LT", "l&t": "LT",
    "wipro": "WIPRO", "hcl": "HCLTECH", "hcl tech": "HCLTECH",
    "tech mahindra": "TECHM", "tech m": "TECHM",
    "asian paints": "ASIANPAINT",
    "titan": "TITAN", "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "sun pharma": "SUNPHARMA", "sun pharmaceutical": "SUNPHARMA",
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL",
    "adani": "ADANIENT", "adani enterprises": "ADANIENT",
    "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
    "ongc": "ONGC", "ntpc": "NTPC",
    "irfc": "IRFC", "irctc": "IRCTC",
    "zomato": "ZOMATO", "paytm": "PAYTM",
}

_RED_FLAG_WORDS = [
    "operator", "guaranteed", "100%", "sure shot", "sureshot", "no risk",
    "jackpot", "multibagger alert", "urgent", "limited time", "double",
    "triple", "circle", "syndicate", "tip from",
]


def _first_number(pattern: str, text: str) -> Optional[float]:
    """Return the first number matching pattern in text, else None."""
    import re
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        # grab the first capture group that contains a number
        for g in m.groups():
            if g:
                try:
                    return float(g.replace(",", ""))
                except ValueError:
                    pass
    return None


def _parse_tip_regex(tip_text: str) -> dict:
    """Rule-based parser: extracts trade details using regex. No API needed."""
    import re
    text = tip_text.strip()
    upper = text.upper()

    # ── Ticker ──────────────────────────────────────────────────────────────────
    ticker = None

    # 1. Check known company names (longest match first)
    for name in sorted(_NAME_TO_TICKER, key=len, reverse=True):
        if name in text.lower():
            ticker = _NAME_TO_TICKER[name]
            break

    # 2. Check known tickers as whole words
    if not ticker:
        for t in _KNOWN_TICKERS:
            if re.search(rf'\b{re.escape(t)}\b', upper):
                ticker = t
                break

    # 3. Fall back: first standalone ALL-CAPS word (2-12 chars, not common English)
    _SKIP = {"BUY","SELL","SL","CMP","AT","T1","T2","TGT","NSE","BSE","NOW",
             "FOR","THE","AND","OR","WITH","ADD","UP","TO","IN","ON","IS","IT",
             "A","AN","TARGET","STOP","LOSS","URGENT","SURE","SHOT","100"}
    if not ticker:
        for m in re.finditer(r'\b([A-Z][A-Z0-9&\-]{1,11})\b', upper):
            cand = m.group(1)
            if cand not in _SKIP and not cand.isdigit():
                ticker = cand
                break

    # ── Action ──────────────────────────────────────────────────────────────────
    action = "SELL" if re.search(r'\bsell\b|\bshort\b', text, re.IGNORECASE) else "BUY"

    # ── Prices — try several common formats ─────────────────────────────────────
    # Entry: "at 2800", "buy at 2800", "above 1720", "cmp 3850", "@ 2800"
    tip_price = (
        _first_number(r'(?:buy|entry|cmp|at|above|@)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)', text)
        or _first_number(r'(?:buy|entry)\s+([\d,]+(?:\.\d+)?)', text)
    )

    # Stop loss: "sl 1685", "stop loss 1685", "stop 1685", "sl: 1685"
    stop_loss = _first_number(
        r'(?:sl|stop\s*loss|stoploss|stop)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)', text
    )

    # Targets
    target_1 = (
        _first_number(r'(?:t1|tgt\s*1|target\s*1|first\s*target)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)', text)
        or _first_number(r'(?:target|tgt|tp)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)', text)
    )
    target_2 = _first_number(
        r'(?:t2|tgt\s*2|target\s*2|second\s*target)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)', text
    )

    # ── Timeframe ────────────────────────────────────────────────────────────────
    timeframe = "unknown"
    if re.search(r'\bintraday\b|\btoday\b|\bbtst\b|\bsame day\b', text, re.IGNORECASE):
        timeframe = "INTRADAY"
    elif re.search(r'\bpositional\b|\blong.?term\b|\b[3-9]\s*(?:weeks?|months?)\b', text, re.IGNORECASE):
        timeframe = "POSITIONAL"
    elif re.search(r'\bswing\b|\b[2-9]\s*(?:-\s*)?[2-9]?\s*days?\b|\bshort.?term\b', text, re.IGNORECASE):
        timeframe = "SWING"

    # ── Claims ───────────────────────────────────────────────────────────────────
    low = text.lower()
    claims = []
    claim_patterns = [
        (r'operator',          "operator backing"),
        (r'guaranteed?|sure\s*shot|100\s*%', "guaranteed returns"),
        (r'breakout',          "breakout signal"),
        (r'volume',            "volume confirmation"),
        (r'news|catalyst|result', "news/catalyst driven"),
        (r'support|resistance', "key level support/resistance"),
        (r'multi.?bagger',     "multibagger potential"),
        (r'urgent|limited\s*time', "urgency/FOMO language"),
        (r'double|triple|2x|3x', "extreme return claims"),
        (r'no\s*(?:stop|risk|sl)', "no stop loss suggested"),
    ]
    for pattern, label in claim_patterns:
        if re.search(pattern, low):
            claims.append(label)

    # ── Parse confidence ─────────────────────────────────────────────────────────
    filled = sum(x is not None for x in [ticker, tip_price, stop_loss, target_1])
    confidence = "HIGH" if filled >= 3 else "MEDIUM" if filled >= 2 else "LOW"

    return {
        "ticker":           ticker or "",
        "company_name":     ticker or "",
        "action":           action,
        "tip_price":        tip_price,
        "stop_loss":        stop_loss,
        "target_1":         target_1,
        "target_2":         target_2,
        "timeframe":        timeframe,
        "claims":           claims,
        "parse_confidence": confidence,
        "_parsed_by":       "regex",
    }


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
    """Return a plain-English synthesis of the tip analysis.
    Uses Claude Sonnet when API key is available, otherwise generates a template verdict."""
    c = _client()
    if not c:
        return _template_verdict(parsed, analysis)

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
        return _template_verdict(parsed, analysis)


# ── Template verdict (no API required) ────────────────────────────────────────

def _template_verdict(parsed: dict, analysis: dict) -> str:
    """Generate a rule-based plain-English verdict from scores. No API needed."""
    verdict     = analysis.get("verdict", "MIXED")
    pump_score  = analysis.get("pump_score", 0)
    tech_score  = analysis.get("tech_score", 50)
    rr          = analysis.get("rr")
    ticker      = analysis.get("ticker", "this stock")
    rsi         = analysis.get("rsi", 50)
    vol_ratio   = analysis.get("vol_ratio", 1.0)
    above_200   = analysis.get("above_sma200", False)
    above_50    = analysis.get("above_sma50", False)
    action      = (parsed.get("action") or "BUY").upper()
    claims      = parsed.get("claims", [])
    mcap_cr     = analysis.get("market_cap_cr", 0)
    drift       = analysis.get("price_drift_pct")

    sentences = []

    # ── Sentence 1: headline verdict ────────────────────────────────────────────
    if verdict == "LIKELY PUMP":
        sentences.append(
            f"This tip on {ticker} shows multiple hallmarks of a pump-and-dump scheme "
            f"and should be treated as highly dangerous."
        )
    elif verdict == "HIGH RISK":
        sentences.append(
            f"This {ticker} tip carries significant risk — the technical setup or "
            f"pump indicators are flashing warning signs that you shouldn't ignore."
        )
    elif verdict == "CREDIBLE":
        sentences.append(
            f"This {ticker} tip looks reasonably credible — the technical setup "
            f"broadly supports the suggested trade direction."
        )
    else:  # MIXED
        sentences.append(
            f"This {ticker} tip is a mixed picture — some factors support the trade "
            f"while others raise caution."
        )

    # ── Sentence 2: top driver ───────────────────────────────────────────────────
    drivers = []
    if pump_score >= 55:
        drivers.append(f"extremely high pump-risk score of {pump_score}/100")
    elif pump_score >= 35:
        drivers.append(f"elevated pump-risk score of {pump_score}/100")

    if vol_ratio >= 3:
        drivers.append(f"volume is {vol_ratio:.1f}× its 20-day average — a classic manipulation signal")
    elif vol_ratio >= 2:
        drivers.append(f"volume is {vol_ratio:.1f}× above average, suggesting unusual activity")

    if 0 < mcap_cr < 500:
        drivers.append(f"micro-cap status (₹{mcap_cr:,.0f} Cr) makes it trivially easy to manipulate")

    if any(w in " ".join(claims).lower() for w in ["guaranteed", "operator", "sure shot", "100%"]):
        drivers.append("red-flag language like 'guaranteed' or 'operator backed' in the tip itself")

    if rsi > 75 and action == "BUY":
        drivers.append(f"RSI of {rsi:.0f} is severely overbought — you would be buying the top")
    elif rsi < 30 and action == "BUY":
        drivers.append(f"RSI of {rsi:.0f} is in oversold territory, a potential bounce zone")

    if not above_200 and action == "BUY":
        drivers.append("price is below the 200-day moving average, meaning the long-term trend is down")
    elif above_200 and above_50 and action == "BUY":
        drivers.append("price is above both the 50 and 200-day moving averages, trend is supportive")

    if drift is not None and drift > 8 and action == "BUY":
        drivers.append(f"price has already moved {drift:.1f}% above the tip price — the move may be over")

    if drivers:
        top = drivers[:2]
        sentences.append("The two biggest concerns are: " + ", and ".join(top) + ".")
    else:
        sentences.append(f"Technical score of {tech_score}/100 reflects the overall setup quality.")

    # ── Sentence 3: R:R comment ──────────────────────────────────────────────────
    if rr is None:
        sentences.append(
            "The tip does not specify both a stop loss and target, so risk:reward cannot be calculated — "
            "never enter a trade without defining where you will exit if wrong."
        )
    elif rr < 1:
        sentences.append(
            f"The risk:reward of 1:{rr:.1f} is worse than breakeven — "
            f"you stand to lose more than you gain, which is an unacceptable trade structure."
        )
    elif rr < 1.5:
        sentences.append(
            f"The risk:reward of 1:{rr:.1f} is below the recommended minimum of 1:1.5 — "
            f"consider passing unless you have strong conviction."
        )
    else:
        sentences.append(
            f"The risk:reward of 1:{rr:.1f} is {'excellent' if rr >= 2.5 else 'acceptable'} — "
            f"at least the trade structure makes mathematical sense."
        )

    # ── Sentence 4: actionable advice ───────────────────────────────────────────
    if verdict == "LIKELY PUMP":
        sentences.append(
            "Do not act on this tip — forward it to SEBI's investor helpline (1800-22-7575) "
            "if you received it in a group, as it may be part of an organised pump-and-dump."
        )
    elif verdict == "HIGH RISK":
        sentences.append(
            f"If you still want to trade {ticker}, verify the setup independently on a chart, "
            f"reduce your position size significantly, and only enter if price is near your "
            f"defined entry — never chase."
        )
    elif verdict == "CREDIBLE":
        sentences.append(
            f"Before entering, check {ticker}'s chart on your own platform to confirm the "
            f"breakout or setup is still valid, and make sure you can honour the stop loss "
            f"without hesitation."
        )
    else:
        sentences.append(
            f"Wait for price confirmation before acting — let {ticker} prove the setup is "
            f"still valid rather than entering blind on a forwarded message."
        )

    return " ".join(sentences)
