"""
Signal Logger: Persists generated trade signals to SQLite for backtesting.

Each signal is stored once per (ticker, strategy, timeframe, date) — duplicate
calls for the same signal on the same trading day are silently skipped.

Outcomes are updated by outcome_tracker.py after market close.
"""
import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz

from signals.signal_models import TradeSignal

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# DB lives alongside the cache DB
SIGNALS_DB_PATH = Path("data_store/signals.db")

# Outcome constants
OUTCOME_OPEN     = "OPEN"
OUTCOME_TARGET1  = "TARGET1_HIT"
OUTCOME_TARGET2  = "TARGET2_HIT"
OUTCOME_STOPPED  = "STOPPED"
OUTCOME_EXPIRED  = "EXPIRED"

# Swing signals expire after this many calendar days with no trigger
SWING_EXPIRY_DAYS = 14


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id         TEXT    UNIQUE NOT NULL,
    logged_at         TEXT    NOT NULL,
    signal_date       TEXT    NOT NULL,
    ticker            TEXT    NOT NULL,
    name              TEXT,
    timeframe         TEXT    NOT NULL,
    strategy          TEXT    NOT NULL,
    direction         TEXT    NOT NULL,
    entry_price       REAL    NOT NULL,
    stop_loss         REAL    NOT NULL,
    target_1          REAL    NOT NULL,
    target_2          REAL    NOT NULL,
    risk_reward       REAL,
    sl_pct            REAL,
    t1_pct            REAL,
    t2_pct            REAL,
    technical_score   REAL,
    fundamental_score REAL,
    sentiment_score   REAL,
    confidence        INTEGER,
    sector            TEXT,
    patterns          TEXT,
    reasoning         TEXT,
    outcome           TEXT    NOT NULL DEFAULT 'OPEN',
    outcome_price     REAL,
    outcome_at        TEXT,
    max_gain_pct      REAL,
    max_loss_pct      REAL,
    pnl_r             REAL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_signal_log_ticker_date
    ON signal_log (ticker, signal_date);
CREATE INDEX IF NOT EXISTS idx_signal_log_outcome
    ON signal_log (outcome);
CREATE INDEX IF NOT EXISTS idx_signal_log_timeframe
    ON signal_log (timeframe);
"""


def _make_signal_id(signal: TradeSignal, date_str: str) -> str:
    """
    Stable dedup key: same ticker + strategy + timeframe + date = same ID.
    Entry price is included so a meaningfully different entry generates a new row.
    """
    raw = f"{signal.ticker}|{signal.strategy}|{signal.timeframe}|{date_str}|{signal.entry_price:.2f}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


class SignalLogger:
    """Thread-safe SQLite-backed signal log."""

    def __init__(self, db_path: Path = SIGNALS_DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            for stmt in _CREATE_INDEX_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.commit()

    # ── Write ──────────────────────────────────────────────────────────────────

    def log_signal(self, signal: TradeSignal) -> bool:
        """
        Persist one signal. Returns True if newly inserted, False if duplicate.
        Never raises — errors are logged and swallowed.
        """
        now_ist = datetime.now(IST)
        date_str = now_ist.strftime("%Y-%m-%d")
        signal_id = _make_signal_id(signal, date_str)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO signal_log
                        (signal_id, logged_at, signal_date, ticker, name,
                         timeframe, strategy, direction,
                         entry_price, stop_loss, target_1, target_2,
                         risk_reward, sl_pct, t1_pct, t2_pct,
                         technical_score, fundamental_score, sentiment_score,
                         confidence, sector, patterns, reasoning, outcome)
                    VALUES
                        (?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?)
                    """,
                    (
                        signal_id,
                        now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                        date_str,
                        signal.ticker,
                        signal.name,
                        signal.timeframe,
                        signal.strategy,
                        signal.direction,
                        round(signal.entry_price, 2),
                        round(signal.stop_loss, 2),
                        round(signal.target_1, 2),
                        round(signal.target_2, 2),
                        round(signal.risk_reward, 2),
                        round(signal.stop_loss_pct, 2),
                        round(signal.target_1_pct, 2),
                        round(signal.target_2_pct, 2),
                        round(signal.technical_score, 3),
                        round(signal.fundamental_score, 3),
                        round(signal.sentiment_score, 3),
                        signal.confidence,
                        signal.sector,
                        json.dumps(signal.patterns),
                        signal.reasoning,
                        OUTCOME_OPEN,
                    ),
                )
                inserted = conn.total_changes > 0
                conn.commit()
                return inserted
        except Exception as exc:
            logger.error(f"SignalLogger.log_signal failed for {signal.ticker}: {exc}")
            return False

    def log_signals(self, signals: list[TradeSignal]) -> int:
        """Log a batch of signals. Returns count of newly inserted rows."""
        new_count = sum(1 for s in signals if self.log_signal(s))
        if new_count:
            logger.info(f"Signal logger: persisted {new_count} new signal(s).")
        return new_count

    def update_outcome(
        self,
        signal_id: str,
        outcome: str,
        outcome_price: float,
        outcome_at: str,
        max_gain_pct: Optional[float] = None,
        max_loss_pct: Optional[float] = None,
        pnl_r: Optional[float] = None,
    ):
        """Update the outcome of a resolved signal."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE signal_log
                    SET outcome=?, outcome_price=?, outcome_at=?,
                        max_gain_pct=?, max_loss_pct=?, pnl_r=?
                    WHERE signal_id=? AND outcome=?
                    """,
                    (
                        outcome,
                        round(outcome_price, 2),
                        outcome_at,
                        round(max_gain_pct, 2) if max_gain_pct is not None else None,
                        round(max_loss_pct, 2) if max_loss_pct is not None else None,
                        round(pnl_r, 3) if pnl_r is not None else None,
                        signal_id,
                        OUTCOME_OPEN,   # only update if still OPEN
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"SignalLogger.update_outcome failed ({signal_id}): {exc}")

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_open_signals(self) -> list[dict]:
        """Return all signals still awaiting outcome resolution."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signal_log WHERE outcome=? ORDER BY logged_at ASC",
                (OUTCOME_OPEN,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_signals(
        self,
        timeframe: Optional[str] = None,
        strategy: Optional[str] = None,
        outcome: Optional[str] = None,
        days_back: int = 60,
    ) -> list[dict]:
        """
        Fetch signal history for display / backtesting analysis.

        Args:
            timeframe: "INTRADAY" | "SWING" | None (all)
            strategy:  exact strategy name or None (all)
            outcome:   specific outcome filter or None (all)
            days_back: how many calendar days of history to return
        """
        clauses = ["signal_date >= date('now', ?)"]
        params: list = [f"-{days_back} days"]

        if timeframe:
            clauses.append("timeframe=?")
            params.append(timeframe)
        if strategy:
            clauses.append("strategy=?")
            params.append(strategy)
        if outcome:
            clauses.append("outcome=?")
            params.append(outcome)

        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM signal_log WHERE {where} ORDER BY logged_at DESC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_performance_summary(
        self,
        timeframe: Optional[str] = None,
        days_back: int = 60,
    ) -> dict:
        """
        Aggregate win/loss statistics for the backtesting dashboard.

        Returns a dict with:
          total, open, won (t1+t2), lost, expired, win_rate (%),
          avg_r (average R-multiple on closed trades), by_strategy
        """
        clauses = ["signal_date >= date('now', ?)"]
        params: list = [f"-{days_back} days"]
        if timeframe:
            clauses.append("timeframe=?")
            params.append(timeframe)
        where = " AND ".join(clauses)

        with self._connect() as conn:
            # Outcome counts
            outcome_rows = conn.execute(
                f"SELECT outcome, COUNT(*) AS cnt FROM signal_log WHERE {where} GROUP BY outcome",
                params,
            ).fetchall()
            by_outcome = {r["outcome"]: r["cnt"] for r in outcome_rows}

            # Average R on closed (non-OPEN, non-EXPIRED) signals
            avg_row = conn.execute(
                f"SELECT AVG(pnl_r) AS avg_r FROM signal_log "
                f"WHERE {where} AND outcome NOT IN (?,?)",
                params + [OUTCOME_OPEN, OUTCOME_EXPIRED],
            ).fetchone()

            # Per-strategy win rates
            strat_rows = conn.execute(
                f"""
                SELECT strategy,
                       COUNT(*) AS total,
                       SUM(CASE WHEN outcome IN (?,?) THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN outcome=? THEN 1 ELSE 0 END) AS losses,
                       AVG(CASE WHEN outcome NOT IN (?,?) THEN pnl_r END) AS avg_r
                FROM signal_log
                WHERE {where}
                GROUP BY strategy
                """,
                [OUTCOME_TARGET1, OUTCOME_TARGET2,
                 OUTCOME_STOPPED,
                 OUTCOME_OPEN, OUTCOME_EXPIRED] + params,
            ).fetchall()

        total     = sum(by_outcome.values())
        won       = by_outcome.get(OUTCOME_TARGET1, 0) + by_outcome.get(OUTCOME_TARGET2, 0)
        lost      = by_outcome.get(OUTCOME_STOPPED, 0)
        open_cnt  = by_outcome.get(OUTCOME_OPEN, 0)
        expired   = by_outcome.get(OUTCOME_EXPIRED, 0)
        closed    = won + lost
        win_rate  = round(won / closed * 100, 1) if closed else 0.0
        avg_r     = round(avg_row["avg_r"], 3) if avg_row["avg_r"] is not None else None

        by_strategy = {}
        for r in strat_rows:
            s_closed = (r["wins"] or 0) + (r["losses"] or 0)
            by_strategy[r["strategy"]] = {
                "total":    r["total"],
                "wins":     r["wins"] or 0,
                "losses":   r["losses"] or 0,
                "win_rate": round((r["wins"] or 0) / s_closed * 100, 1) if s_closed else 0.0,
                "avg_r":    round(r["avg_r"], 3) if r["avg_r"] is not None else None,
            }

        return {
            "total":       total,
            "open":        open_cnt,
            "won":         won,
            "lost":        lost,
            "expired":     expired,
            "win_rate":    win_rate,
            "avg_r":       avg_r,
            "by_outcome":  by_outcome,
            "by_strategy": by_strategy,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────

_instance: Optional[SignalLogger] = None


def get_signal_logger() -> SignalLogger:
    global _instance
    if _instance is None:
        _instance = SignalLogger()
    return _instance
