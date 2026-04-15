"""
Telegram notification integration.
Sends signal alerts and morning briefings to a Telegram channel.

Required environment variables (set in Streamlit Cloud Secrets):
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_CHANNEL_ID — e.g. @NSEStockSignals
"""
import html
import os
import logging
import requests
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _get_config():
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "")
    return token, channel


def is_configured() -> bool:
    token, channel = _get_config()
    return bool(token and channel)


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message to the configured channel. Returns True on success."""
    token, channel = _get_config()
    if not token or not channel:
        logger.warning("Telegram not configured — skipping notification.")
        return False
    try:
        url = TELEGRAM_API.format(token=token, method="sendMessage")
        resp = requests.post(url, json={
            "chat_id":    channel,
            "text":       text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"Telegram API error {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Telegram send_message failed: {e}")
        return False


# ── Message formatters ─────────────────────────────────────────────────────────

def _stars(confidence: int) -> str:
    return "★" * (confidence or 1) + "☆" * (5 - (confidence or 1))


def _direction_emoji(direction: str) -> str:
    return "🟢 LONG" if direction.upper() == "LONG" else "🔴 SHORT"


def format_swing_signal(signal) -> str:
    """Format a swing TradeSignal into a Telegram message."""
    s = signal if isinstance(signal, dict) else signal.__dict__
    ticker = s.get("ticker", "").replace(".NS", "")
    now    = datetime.now(IST).strftime("%d %b %Y %H:%M IST")

    entry = float(s.get('entry_price') or s.get('entry') or 0)
    stop  = float(s.get('stop_loss', 0))
    t1    = float(s.get('target_1', 0))
    t2    = float(s.get('target_2', 0))
    sl_pct = abs(entry - stop) / entry * 100 if entry else 0
    t1_pct = abs(t1 - entry) / entry * 100 if entry else 0
    t2_pct = abs(t2 - entry) / entry * 100 if entry else 0

    return (
        f"📈 <b>SWING SIGNAL — {ticker}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Strategy:  {s.get('strategy', '')}\n"
        f"Direction: {_direction_emoji(s.get('direction', 'LONG'))}\n"
        f"Confidence: {_stars(s.get('confidence', 3))}\n\n"
        f"Entry:  ₹{entry:,.2f}\n"
        f"SL:     ₹{stop:,.2f}  (<b>{sl_pct:.1f}%</b>)\n"
        f"T1:     ₹{t1:,.2f}  (+{t1_pct:.1f}%)\n"
        f"T2:     ₹{t2:,.2f}  (+{t2_pct:.1f}%)\n"
        f"R:R:    1:{s.get('risk_reward', 0):.1f}\n\n"
        f"🕐 {now}"
    )


def format_intraday_signal(signal) -> str:
    """Format an intraday TradeSignal into a Telegram message."""
    s = signal if isinstance(signal, dict) else signal.__dict__
    ticker = s.get("ticker", "").replace(".NS", "")
    now    = datetime.now(IST).strftime("%d %b %Y %H:%M IST")

    entry = float(s.get('entry_price') or s.get('entry') or 0)
    stop  = float(s.get('stop_loss', 0))
    t1    = float(s.get('target_1', 0))
    t2    = float(s.get('target_2', 0))
    sl_pct = abs(entry - stop) / entry * 100 if entry else 0
    t1_pct = abs(t1 - entry) / entry * 100 if entry else 0
    t2_pct = abs(t2 - entry) / entry * 100 if entry else 0

    return (
        f"⚡ <b>INTRADAY SIGNAL — {ticker}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Strategy:  {s.get('strategy', '')}\n"
        f"Direction: {_direction_emoji(s.get('direction', 'LONG'))}\n"
        f"Confidence: {_stars(s.get('confidence', 3))}\n\n"
        f"Entry:  ₹{entry:,.2f}\n"
        f"SL:     ₹{stop:,.2f}  (<b>{sl_pct:.1f}%</b>)\n"
        f"T1:     ₹{t1:,.2f}  (+{t1_pct:.1f}%)\n"
        f"T2:     ₹{t2:,.2f}  (+{t2_pct:.1f}%)\n"
        f"R:R:    1:{s.get('risk_reward', 0):.1f}\n\n"
        f"⚠️ Square off by <b>3:30 PM IST</b>\n"
        f"🕐 {now}"
    )


def format_morning_briefing(sentiment: dict, swing_count: int, intraday_count: int) -> str:
    """Format the 8:45 AM morning briefing message."""
    now  = datetime.now(IST)
    date = now.strftime("%A, %d %b %Y")

    score = sentiment.get("overall_sentiment", 5)
    label = sentiment.get("sentiment_label", "Neutral")
    emoji = (
        "🟢" if score >= 7 else
        "🟡" if score >= 4 else
        "🔴"
    )

    themes = sentiment.get("key_themes", [])
    themes_text = ""
    for t in themes[:3]:
        themes_text += f"  • {t[:60]}\n"

    catalysts = sentiment.get("key_catalysts", [])
    risks     = sentiment.get("key_risks", [])

    cat_text  = "\n".join(f"  ✅ {c[:55]}" for c in catalysts[:2])
    risk_text = "\n".join(f"  ⚠️ {r[:55]}" for r in risks[:2])

    app_url = "https://stockscreener4.streamlit.app"

    msg = (
        f"🌅 <b>NSE PRE-MARKET BRIEFING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {date}\n\n"
        f"{emoji} <b>Market Sentiment:</b> {label} ({score}/10)\n\n"
    )
    if themes_text:
        msg += f"🔑 <b>Key Themes:</b>\n{themes_text}\n"
    if cat_text:
        msg += f"<b>Catalysts:</b>\n{cat_text}\n\n"
    if risk_text:
        msg += f"<b>Risks:</b>\n{risk_text}\n\n"

    msg += (
        f"📈 Swing signals today:   <b>{swing_count}</b>\n"
        f"⚡ Intraday signals today: <b>{intraday_count}</b>\n\n"
        f"🔗 <a href='{app_url}'>Open Screener App</a>"
    )
    return msg


def format_market_update(label: str, indices: dict, top_gainers: list,
                         top_losers: list, advances: int, declines: int,
                         news_headlines: list) -> str:
    """
    Format a mid-session or closing market update.
    label: e.g. 'Mid-Day Update' or 'Market Closing Summary'
    """
    now  = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    emoji = "📊"

    # Index lines
    idx_lines = ""
    for name, data in indices.items():
        val   = data.get("price", 0)
        chg   = data.get("change_pct", 0)
        arrow = "🟢" if chg >= 0 else "🔴"
        idx_lines += f"  {arrow} <b>{name}</b>: {val:,.0f} ({chg:+.2f}%)\n"

    # Breadth
    total = advances + declines
    breadth_pct = advances / total * 100 if total else 50
    breadth_emoji = "🟢" if breadth_pct > 55 else ("🔴" if breadth_pct < 45 else "🟡")

    # Top gainers/losers (max 3 each)
    gainer_lines = ""
    for g in top_gainers[:3]:
        gainer_lines += f"  ▲ {g.get('ticker','').replace('.NS','')}  {g.get('change_pct',0):+.1f}%\n"

    loser_lines = ""
    for l in top_losers[:3]:
        loser_lines += f"  ▼ {l.get('ticker','').replace('.NS','')}  {l.get('change_pct',0):+.1f}%\n"

    # News (max 3 headlines)
    news_lines = ""
    for item in news_headlines[:3]:
        title = html.unescape((item.get("title") or ""))[:65]
        news_lines += f"  • {title}\n"

    msg = (
        f"{emoji} <b>NSE {label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n\n"
        f"<b>Indices:</b>\n{idx_lines}\n"
        f"{breadth_emoji} <b>Breadth:</b> {advances} Adv / {declines} Dec "
        f"({breadth_pct:.0f}% advancing)\n\n"
    )
    if gainer_lines:
        msg += f"📈 <b>Top Gainers:</b>\n{gainer_lines}"
    if loser_lines:
        msg += f"📉 <b>Top Losers:</b>\n{loser_lines}"
    if news_lines:
        msg += f"\n📰 <b>Latest News:</b>\n{html.unescape(news_lines)}"

    msg += f"\n🔗 <a href='https://stockscreener4.streamlit.app'>Open Screener</a>"
    return msg


def notify_swing_signals(signals: list) -> int:
    """Send alerts for a list of swing signals. Returns count sent."""
    if not is_configured() or not signals:
        return 0
    sent = 0
    for s in signals:
        try:
            msg = format_swing_signal(s)
            if send_message(msg):
                sent += 1
        except Exception as e:
            logger.error(f"Failed to send swing signal alert: {e}")
    return sent


def notify_intraday_signals(signals: list) -> int:
    """Send alerts for a list of intraday signals. Returns count sent."""
    if not is_configured() or not signals:
        return 0
    sent = 0
    for s in signals:
        try:
            msg = format_intraday_signal(s)
            if send_message(msg):
                sent += 1
        except Exception as e:
            logger.error(f"Failed to send intraday signal alert: {e}")
    return sent
