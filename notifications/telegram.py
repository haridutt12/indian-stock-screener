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
        f"🕐 {now}\n\n"
        f"<i>For research purposes only. Not investment advice. "
        f"Verify independently before trading. Past signals are not a guarantee of future results.</i>"
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
        f"🕐 {now}\n\n"
        f"<i>For research purposes only. Not investment advice. "
        f"Verify independently before trading.</i>"
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


def format_trade_resolved(signal: dict, outcome: str, price: float, pnl_pct: float) -> str:
    """Format a trade resolution alert (SL hit, T1 hit, T2 hit)."""
    ticker = signal.get("ticker", "").replace(".NS", "")
    strategy = signal.get("strategy", "")
    timeframe = signal.get("timeframe", "")
    direction = signal.get("direction", "LONG")
    entry = float(signal.get("entry_price") or 0)
    pnl_inr = pnl_pct / 100 * float(signal.get("position_size_inr") or 100_000)
    now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")

    outcome_map = {
        "TARGET2_HIT":  ("🎯🎯", "TARGET 2 HIT"),
        "TARGET1_HIT":  ("🎯",   "TARGET 1 HIT"),
        "STOPPED":      ("🛑",   "STOPPED OUT"),
        "SQUARED_OFF":  ("⎋",    "SQUARED OFF"),
        "EXPIRED":      ("⏰",   "EXPIRED"),
    }
    emoji, label = outcome_map.get(outcome, ("📊", outcome))
    pnl_sign = "+" if pnl_pct >= 0 else ""

    return (
        f"{emoji} <b>{label} — {ticker}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Strategy:  {strategy} · {timeframe}\n"
        f"Direction: {'🟢 LONG' if direction == 'LONG' else '🔴 SHORT'}\n\n"
        f"Entry:  ₹{entry:,.2f}\n"
        f"Exit:   ₹{price:,.2f}\n"
        f"P&L:    <b>{pnl_sign}{pnl_pct:.2f}% · ₹{pnl_sign}{pnl_inr:,.0f}</b>\n\n"
        f"🕐 {now}"
    )


def notify_trade_resolved(signal: dict, outcome: str, price: float, pnl_pct: float) -> bool:
    """Send a trade resolution alert to the Telegram channel."""
    if not is_configured():
        return False
    try:
        return send_message(format_trade_resolved(signal, outcome, price, pnl_pct))
    except Exception as e:
        logger.error(f"notify_trade_resolved failed: {e}")
        return False


# ── Price Alerts ───────────────────────────────────────────────────────────────

def format_price_alert(ticker: str, condition: str, alert_price: float, current_price: float, label: str = "") -> str:
    now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    emoji = "🔔"
    cond_str = "crossed above" if condition == "above" else "dropped below"
    label_line = f"\n📝 <i>{label}</i>" if label else ""
    return (
        f"{emoji} <b>PRICE ALERT — {ticker}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Alert: {ticker} {cond_str} ₹{alert_price:,.2f}{label_line}\n\n"
        f"Alert Price: ₹{alert_price:,.2f}\n"
        f"Current:     ₹{current_price:,.2f}\n\n"
        f"🕐 {now}"
    )


def notify_price_alert(ticker: str, condition: str, alert_price: float, current_price: float, label: str = "") -> bool:
    """Fire a Telegram alert when a price alert is triggered."""
    if not is_configured():
        return False
    try:
        return send_message(format_price_alert(ticker, condition, alert_price, current_price, label))
    except Exception as e:
        logger.error(f"notify_price_alert failed: {e}")
        return False


# ── Daily Top 3 ────────────────────────────────────────────────────────────────

_MEDAL = ["🥇", "🥈", "🥉"]
_SCORE_BAR_FILLED   = "█"
_SCORE_BAR_EMPTY    = "░"


def _score_bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return _SCORE_BAR_FILLED * filled + _SCORE_BAR_EMPTY * (width - filled)


def format_top3_signals(ranked: list) -> str:
    """
    Format the top 3 ranked open signals into a single Telegram message.
    ranked: list of (score, breakdown, signal_dict, curr_price) from rank_signals()
    """
    now  = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    top  = ranked[:3]
    lines = [
        "⭐ <b>Top 3 Trade Ideas — NiftyEdge</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🕐 {now}\n",
    ]

    for i, (score, bd, sig, curr_price) in enumerate(top):
        ticker  = sig.get("ticker", "").replace(".NS", "")
        strat   = sig.get("strategy", "")
        tf      = sig.get("timeframe", "")
        direction = sig.get("direction", "LONG")
        entry   = float(sig.get("entry_price") or 0)
        sl      = float(sig.get("stop_loss")   or 0)
        t1      = float(sig.get("target_1")    or 0)
        t2      = float(sig.get("target_2")    or 0)
        rr      = float(sig.get("risk_reward") or 0)
        conf    = sig.get("confidence") or 0
        prox    = bd.get("_prox_label", "")
        dir_lbl = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
        tf_lbl  = "📅 Swing" if tf == "SWING" else "⚡ Intraday"
        cp_lbl  = f"₹{curr_price:,.1f}" if curr_price else "—"

        lines += [
            f"{_MEDAL[i]} <b>{ticker}</b>  {dir_lbl}  {tf_lbl}",
            f"Strategy: {strat}",
            f"Score:    {score:.0f}/100  {_score_bar(score)}",
            f"Conf:     {'★' * conf}{'☆' * (5 - conf)}",
            f"",
            f"  Entry ₹{entry:,.2f}  |  Now {cp_lbl}",
            f"  SL    ₹{sl:,.2f}  |  T1  ₹{t1:,.2f}  |  T2  ₹{t2:,.2f}",
            f"  R:R   1:{rr:.1f}  |  {prox}",
        ]
        if i < len(top) - 1:
            lines.append("─────────────────────")

    lines += [
        "",
        "🔗 <a href='https://stockscreener4.streamlit.app/Signal_Log'>Full Signal Log →</a>",
    ]
    return "\n".join(lines)


def send_top3_signals() -> bool:
    """
    Fetch open signals, rank them, and send the Top 3 to Telegram.
    Returns True if the message was sent successfully.
    """
    if not is_configured():
        logger.warning("Telegram not configured — skipping Top 3 alert.")
        return False
    try:
        from signals.signal_logger import get_signal_logger
        from signals.signal_ranker import rank_signals
        open_sigs = get_signal_logger().get_open_signals()
        ranked    = rank_signals(open_sigs)
        if not ranked:
            logger.info("Top 3 Telegram: no open signals to send.")
            return False
        msg = format_top3_signals(ranked)
        ok  = send_message(msg)
        if ok:
            logger.info("Top 3 daily signal alert sent to Telegram.")
        return ok
    except Exception as e:
        logger.error(f"send_top3_signals failed: {e}")
        return False


# ── PCR / Derivatives Alert ───────────────────────────────────────────────────

def send_derivatives_morning_brief() -> bool:
    """
    Sends a morning derivatives brief: India VIX, PCR (Nifty options chain),
    and Max Pain level to the Telegram channel.
    Designed to run after the 10 AM scheduled scan.
    """
    if not is_configured():
        return False
    try:
        import yfinance as yf
        import pandas as pd
        from analysis.options import compute_pcr, compute_max_pain, compute_iv_rank

        # VIX
        vdf = yf.Ticker("^INDIAVIX").history(period="1y", interval="1d", auto_adjust=True)
        vix_curr = float(vdf["Close"].iloc[-1]) if not vdf.empty else None
        vix_hist = vdf["Close"].dropna().tolist() if not vdf.empty else []
        vix_rank = None
        if vix_curr and vix_hist:
            _vh, _vl = max(vix_hist), min(vix_hist)
            vix_rank = round((vix_curr - _vl) / (_vh - _vl) * 100, 1) if _vh != _vl else 50.0

        # Options chain — nearest expiry
        nifty = yf.Ticker("^NSEI")
        expiries = nifty.options
        pcr_msg = max_pain_msg = ""

        if expiries:
            chain  = nifty.option_chain(expiries[0])
            calls  = chain.calls
            puts   = chain.puts
            pcr    = compute_pcr(calls, puts)
            mp     = compute_max_pain(calls, puts)

            pcr_oi  = pcr.get("pcr_oi")
            signal  = pcr.get("signal", "NEUTRAL")
            sentiment = pcr.get("sentiment", "")
            pcr_emoji = "🟢" if signal == "LONG" else ("🔴" if signal == "SHORT" else "🟡")
            pcr_msg = (
                f"\n📊 <b>Nifty Options (Expiry {expiries[0]})</b>"
                f"\nOI PCR:   <b>{pcr_oi or '—'}</b>  {pcr_emoji} {sentiment}"
            )
            if mp:
                spot_df = nifty.history(period="2d", interval="1d", auto_adjust=True)
                spot = float(spot_df["Close"].iloc[-1]) if not spot_df.empty else None
                gap_str = f" (spot {spot:,.0f} → {'+' if spot and mp > spot else ''}{mp-spot if spot else 0:,.0f} gap)" if spot else ""
                max_pain_msg = f"\nMax Pain: <b>₹{mp:,.0f}</b>{gap_str}"

        # IV Rank
        ivr = ""
        if vix_curr and vix_hist:
            from analysis.options import compute_iv_rank as _ivr
            ir = _ivr(vix_curr, vix_hist)
            ivr = f"\nIV Rank:  <b>{ir.get('iv_rank','—')}%</b>  — {ir.get('label','')}"

        now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
        vix_line = ""
        if vix_curr:
            vix_emoji = "😱" if (vix_rank or 0) >= 70 else ("😬" if (vix_rank or 0) >= 40 else "😌")
            vix_line = f"\nIndia VIX: <b>{vix_curr:.1f}</b>  ({vix_rank:.0f}% rank)  {vix_emoji}"

        msg = (
            f"📐 <b>Derivatives Morning Brief — NiftyEdge</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {now}"
            + vix_line
            + ivr
            + pcr_msg
            + max_pain_msg
            + f"\n\n🔗 <a href='https://stockscreener4.streamlit.app/Derivatives'>Full Options Chain →</a>"
        )
        ok = send_message(msg)
        if ok:
            logger.info("Derivatives morning brief sent to Telegram.")
        return ok
    except Exception as exc:
        logger.error("send_derivatives_morning_brief failed: %s", exc)
        return False


def send_daily_performance_summary() -> bool:
    """
    Sends a daily post-market performance summary to Telegram.
    Includes: closed trades today, win/loss, P&L in R, expectancy, portfolio heat.
    Designed to run at 4:30 PM after outcome tracker resolves positions.
    """
    if not is_configured():
        return False
    try:
        import datetime
        from signals.signal_logger import get_signal_logger
        from analysis.signal_quality import full_report

        log = get_signal_logger()
        all_signals = log.get_signals(days_back=30)
        today = datetime.date.today().isoformat()

        closed_today = [
            s for s in all_signals
            if s.get("outcome") not in ("OPEN", None)
            and (s.get("outcome_at") or "")[:10] == today
        ]

        if not closed_today:
            logger.info("No trades closed today — skipping performance summary.")
            return False

        n_today  = len(closed_today)
        wins     = [s for s in closed_today if s.get("net_pnl_r", 0) and float(s["net_pnl_r"]) > 0]
        losses   = [s for s in closed_today if s.get("net_pnl_r", 0) and float(s["net_pnl_r"]) <= 0]
        total_r  = sum(float(s.get("net_pnl_r") or 0) for s in closed_today)
        win_rate = len(wins) / n_today * 100 if n_today > 0 else 0

        report = full_report(all_signals)
        expectancy = report.get("expectancy")
        sharpe_r   = report.get("sharpe_r")
        max_dd     = report.get("max_drawdown_r")

        emoji_overall = "🟢" if total_r > 0 else "🔴"

        lines = [
            f"<b>📊 NiftyEdge Daily Performance · {today}</b>",
            "",
            f"{emoji_overall} <b>Closed today:</b> {n_today} trades",
            f"  ✅ Wins: {len(wins)} | ❌ Losses: {len(losses)}",
            f"  📈 Win rate: {win_rate:.0f}%",
            f"  💰 Total P&L: <b>{total_r:+.2f}R</b>",
            "",
        ]

        for s in closed_today:
            r = float(s.get("net_pnl_r") or 0)
            icon = "✅" if r > 0 else "❌"
            outcome_short = (s.get("outcome") or "").replace("_", " ").title()
            lines.append(
                f"  {icon} {s['ticker'].replace('.NS','')} ({s.get('direction','')}) "
                f"{r:+.2f}R — {outcome_short}"
            )

        lines += [
            "",
            f"<b>30-Day System Stats:</b>",
            f"  Expectancy: {expectancy:+.3f}R/trade" if expectancy is not None else "  Expectancy: —",
            f"  Sharpe-R: {sharpe_r:.2f}" if sharpe_r is not None else "  Sharpe-R: —",
            f"  Max DD: {max_dd:.2f}R" if max_dd is not None else "  Max DD: —",
            "",
            f"<i>NiftyEdge · stockscreener4.streamlit.app</i>",
        ]

        msg = "\n".join(lines)
        ok = send_message(msg)
        if ok:
            logger.info("Daily performance summary sent to Telegram.")
        return ok
    except Exception as exc:
        logger.error("send_daily_performance_summary failed: %s", exc)
        return False
