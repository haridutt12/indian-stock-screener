"""
Signal Logger — persists trade signals to SQLite (local) or PostgreSQL (production).

Production setup (Supabase / Neon / any Postgres):
  .streamlit/secrets.toml:  DATABASE_URL = "postgresql://user:pass@host/db"
  Environment variable:     export DATABASE_URL="postgresql://..."

The table is created automatically on first run — no manual DDL needed.
Without DATABASE_URL the app falls back to local data_store/signals.db.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pytz

if TYPE_CHECKING:
    from signals.signal_models import TradeSignal

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

SIGNALS_DB_PATH = Path("data_store/signals.db")

# ── Outcome constants ──────────────────────────────────────────────────────────
OUTCOME_OPEN        = "OPEN"
OUTCOME_TARGET1     = "TARGET1_HIT"
OUTCOME_TARGET2     = "TARGET2_HIT"
OUTCOME_STOPPED     = "STOPPED"
OUTCOME_SQUARED_OFF = "SQUARED_OFF"
OUTCOME_EXPIRED     = "EXPIRED"

SWING_EXPIRY_DAYS = 14

# ── Backend detection ──────────────────────────────────────────────────────────

def _resolve_db_url() -> Optional[str]:
    url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL") or st.secrets.get("SUPABASE_DB_URL")
    except Exception:
        return None


_DATABASE_URL: Optional[str] = _resolve_db_url()
_USE_PG = False

try:
    import psycopg2
    import psycopg2.extras as _pg_extras
    if _DATABASE_URL:
        _USE_PG = True
        logger.info("SignalLogger: PostgreSQL backend active")
    else:
        logger.info("SignalLogger: psycopg2 available but DATABASE_URL not set — using SQLite")
except ImportError:
    logger.info("SignalLogger: psycopg2 not installed — using SQLite")

# ── Schema ─────────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           TEXT    UNIQUE NOT NULL,
    logged_at           TEXT    NOT NULL,
    signal_date         TEXT    NOT NULL,
    ticker              TEXT    NOT NULL,
    name                TEXT,
    timeframe           TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,
    direction           TEXT    NOT NULL,
    sector              TEXT,
    entry_price         REAL    NOT NULL,
    stop_loss           REAL    NOT NULL,
    target_1            REAL    NOT NULL,
    target_2            REAL    NOT NULL,
    risk_reward         REAL,
    sl_pct              REAL,
    t1_pct              REAL,
    t2_pct              REAL,
    technical_score     REAL,
    fundamental_score   REAL,
    sentiment_score     REAL,
    confidence          INTEGER,
    patterns            TEXT,
    reasoning           TEXT,
    outcome             TEXT    NOT NULL DEFAULT 'OPEN',
    outcome_price       REAL,
    outcome_at          TEXT,
    max_gain_pct        REAL,
    max_loss_pct        REAL,
    pnl_r               REAL,
    position_size_inr   REAL,
    cost_brokerage      REAL,
    cost_stt            REAL,
    cost_exchange       REAL,
    cost_stamp_duty     REAL,
    cost_gst            REAL,
    cost_total_inr      REAL,
    cost_total_pct      REAL,
    gross_pnl_inr       REAL,
    net_pnl_inr         REAL,
    net_pnl_pct         REAL,
    net_pnl_r           REAL
)
"""

# PostgreSQL uses SERIAL instead of AUTOINCREMENT; rest of the schema is identical
_CREATE_TABLE_PG_SQL = _CREATE_TABLE_SQL.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT",
    "SERIAL PRIMARY KEY",
)

_MIGRATION_COLUMNS = [
    ("position_size_inr",  "REAL"),
    ("cost_brokerage",     "REAL"),
    ("cost_stt",           "REAL"),
    ("cost_exchange",      "REAL"),
    ("cost_stamp_duty",    "REAL"),
    ("cost_gst",           "REAL"),
    ("cost_total_inr",     "REAL"),
    ("cost_total_pct",     "REAL"),
    ("gross_pnl_inr",      "REAL"),
    ("net_pnl_inr",        "REAL"),
    ("net_pnl_pct",        "REAL"),
    ("net_pnl_r",          "REAL"),
]

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_sl_ticker_date ON signal_log (ticker, signal_date)",
    "CREATE INDEX IF NOT EXISTS idx_sl_outcome      ON signal_log (outcome)",
    "CREATE INDEX IF NOT EXISTS idx_sl_timeframe    ON signal_log (timeframe)",
]


def _make_signal_id(signal: "TradeSignal", date_str: str) -> str:
    raw = f"{signal.ticker}|{signal.strategy}|{signal.timeframe}|{date_str}|{signal.entry_price:.2f}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


# ── SignalLogger ───────────────────────────────────────────────────────────────

class SignalLogger:
    """Thread-safe signal log backed by SQLite (local) or PostgreSQL (production)."""

    def __init__(self, db_path: Path = SIGNALS_DB_PATH):
        self._db_path = db_path
        self._init_db()

    # ── Connection management ──────────────────────────────────────────────────

    def _open_conn(self):
        if _USE_PG:
            from urllib.parse import urlparse, unquote
            p = urlparse(_DATABASE_URL)
            return psycopg2.connect(
                host=p.hostname,
                port=p.port or 5432,
                dbname=(p.path or "/postgres").lstrip("/"),
                user=unquote(p.username or ""),
                password=unquote(p.password or ""),
                sslmode="require",
                connect_timeout=10,
                cursor_factory=_pg_extras.RealDictCursor,
            )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _db_conn(self):
        conn = self._open_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _exec(self, conn, sql: str, params=()):
        """Execute SQL, converting ? → %s for PostgreSQL. Returns the cursor."""
        if _USE_PG:
            sql = sql.replace("?", "%s")
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur

    # ── Schema init / migration ────────────────────────────────────────────────

    def _init_db(self):
        global _USE_PG
        create_sql = _CREATE_TABLE_PG_SQL if _USE_PG else _CREATE_TABLE_SQL
        try:
            with self._db_conn() as conn:
                self._exec(conn, create_sql)
                for stmt in _CREATE_INDEXES_SQL:
                    try:
                        self._exec(conn, stmt)
                    except Exception:
                        pass
        except Exception as pg_err:
            if _USE_PG:
                logger.error(f"PostgreSQL unavailable ({pg_err}). Falling back to SQLite.")
                _USE_PG = False
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                with self._db_conn() as conn:
                    self._exec(conn, _CREATE_TABLE_SQL)
                    for stmt in _CREATE_INDEXES_SQL:
                        try:
                            self._exec(conn, stmt)
                        except Exception:
                            pass
            else:
                raise

        # Migrations — separate transaction per column to be safe
        for col, col_type in _MIGRATION_COLUMNS:
            try:
                with self._db_conn() as conn:
                    if _USE_PG:
                        self._exec(conn, f"ALTER TABLE signal_log ADD COLUMN IF NOT EXISTS {col} {col_type}")
                    else:
                        existing = {
                            row[1]
                            for row in conn.execute("PRAGMA table_info(signal_log)").fetchall()
                        }
                        if col not in existing:
                            self._exec(conn, f"ALTER TABLE signal_log ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # ── Write ──────────────────────────────────────────────────────────────────

    def log_signal(self, signal: "TradeSignal") -> bool:
        now_ist   = datetime.now(IST)
        date_str  = now_ist.strftime("%Y-%m-%d")
        signal_id = _make_signal_id(signal, date_str)

        cols = (
            "signal_id, logged_at, signal_date, ticker, name, "
            "timeframe, strategy, direction, sector, "
            "entry_price, stop_loss, target_1, target_2, "
            "risk_reward, sl_pct, t1_pct, t2_pct, "
            "technical_score, fundamental_score, sentiment_score, "
            "confidence, patterns, reasoning, outcome"
        )
        ph = ", ".join(["?"] * 24)

        if _USE_PG:
            sql = f"INSERT INTO signal_log ({cols}) VALUES ({ph}) ON CONFLICT (signal_id) DO NOTHING"
        else:
            sql = f"INSERT OR IGNORE INTO signal_log ({cols}) VALUES ({ph})"

        params = (
            signal_id,
            now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            date_str,
            signal.ticker,
            signal.name,
            signal.timeframe,
            signal.strategy,
            signal.direction,
            signal.sector,
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
            json.dumps(signal.patterns),
            signal.reasoning,
            OUTCOME_OPEN,
        )

        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql, params)
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(f"SignalLogger.log_signal failed for {signal.ticker}: {exc}")
            return False

    def log_signals(self, signals: list["TradeSignal"]) -> int:
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
        cost_breakdown: Optional[dict] = None,
    ):
        cb = cost_breakdown or {}
        sql = """
            UPDATE signal_log
            SET outcome=?, outcome_price=?, outcome_at=?,
                max_gain_pct=?, max_loss_pct=?, pnl_r=?,
                position_size_inr=?,
                cost_brokerage=?, cost_stt=?, cost_exchange=?,
                cost_stamp_duty=?, cost_gst=?, cost_total_inr=?,
                cost_total_pct=?, gross_pnl_inr=?, net_pnl_inr=?,
                net_pnl_pct=?, net_pnl_r=?
            WHERE signal_id=? AND outcome=?
        """
        params = (
            outcome,
            round(outcome_price, 2),
            outcome_at,
            round(max_gain_pct, 2)  if max_gain_pct  is not None else None,
            round(max_loss_pct, 2)  if max_loss_pct  is not None else None,
            round(pnl_r, 3)         if pnl_r         is not None else None,
            cb.get("position_size_inr"),
            cb.get("brokerage_inr"),
            cb.get("stt_inr"),
            cb.get("exchange_charges_inr"),
            cb.get("stamp_duty_inr"),
            cb.get("gst_inr"),
            cb.get("cost_total_inr"),
            cb.get("cost_total_pct"),
            cb.get("gross_pnl_inr"),
            cb.get("net_pnl_inr"),
            cb.get("net_pnl_pct"),
            cb.get("net_pnl_r"),
            signal_id,
            OUTCOME_OPEN,
        )
        try:
            with self._db_conn() as conn:
                self._exec(conn, sql, params)
        except Exception as exc:
            logger.error(f"SignalLogger.update_outcome failed ({signal_id}): {exc}")

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_open_signals(self, timeframe: Optional[str] = None) -> list[dict]:
        if timeframe:
            sql    = "SELECT * FROM signal_log WHERE outcome=? AND timeframe=? ORDER BY logged_at ASC"
            params = (OUTCOME_OPEN, timeframe)
        else:
            sql    = "SELECT * FROM signal_log WHERE outcome=? ORDER BY logged_at ASC"
            params = (OUTCOME_OPEN,)
        with self._db_conn() as conn:
            cur = self._exec(conn, sql, params)
            return [dict(r) for r in cur.fetchall()]

    def get_signals(
        self,
        timeframe: Optional[str] = None,
        strategy: Optional[str] = None,
        outcome: Optional[str] = None,
        days_back: int = 60,
    ) -> list[dict]:
        cutoff  = (date.today() - timedelta(days=days_back)).isoformat()
        clauses = ["signal_date >= ?"]
        params: list = [cutoff]

        if timeframe:
            clauses.append("timeframe=?");  params.append(timeframe)
        if strategy:
            clauses.append("strategy=?");   params.append(strategy)
        if outcome:
            clauses.append("outcome=?");    params.append(outcome)

        where = " AND ".join(clauses)
        with self._db_conn() as conn:
            cur = self._exec(conn, f"SELECT * FROM signal_log WHERE {where} ORDER BY logged_at DESC", params)
            return [dict(r) for r in cur.fetchall()]

    def get_performance_summary(
        self,
        timeframe: Optional[str] = None,
        days_back: int = 60,
    ) -> dict:
        cutoff  = (date.today() - timedelta(days=days_back)).isoformat()
        clauses = ["signal_date >= ?"]
        params: list = [cutoff]
        if timeframe:
            clauses.append("timeframe=?"); params.append(timeframe)
        where = " AND ".join(clauses)

        with self._db_conn() as conn:
            cur = self._exec(
                conn,
                f"SELECT outcome, COUNT(*) AS cnt FROM signal_log WHERE {where} GROUP BY outcome",
                params,
            )
            by_outcome = {r["outcome"]: r["cnt"] for r in cur.fetchall()}

            cur = self._exec(
                conn,
                f"SELECT AVG(pnl_r) AS avg_r FROM signal_log WHERE {where} AND outcome NOT IN (?,?)",
                params + [OUTCOME_OPEN, OUTCOME_EXPIRED],
            )
            avg_r_row = cur.fetchone()

            cur = self._exec(
                conn,
                f"""
                SELECT AVG(net_pnl_inr)    AS avg_net_pnl,
                       SUM(net_pnl_inr)    AS total_net_pnl,
                       AVG(cost_total_inr) AS avg_cost,
                       SUM(cost_total_inr) AS total_cost
                FROM signal_log
                WHERE {where} AND outcome NOT IN (?,?)
                """,
                params + [OUTCOME_OPEN, OUTCOME_EXPIRED],
            )
            pnl_row = cur.fetchone()

            cur = self._exec(
                conn,
                f"""
                SELECT strategy,
                       COUNT(*) AS total,
                       SUM(CASE WHEN outcome IN (?,?) THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN outcome=? THEN 1 ELSE 0 END)        AS losses,
                       AVG(CASE WHEN outcome NOT IN (?,?) THEN pnl_r END)        AS avg_r,
                       SUM(CASE WHEN outcome NOT IN (?,?) THEN net_pnl_inr END)  AS net_pnl,
                       AVG(CASE WHEN outcome NOT IN (?,?) THEN net_pnl_inr END)  AS avg_net_pnl
                FROM signal_log
                WHERE {where}
                GROUP BY strategy
                """,
                [
                    OUTCOME_TARGET1, OUTCOME_TARGET2,
                    OUTCOME_STOPPED,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                ] + params,
            )
            strat_rows = cur.fetchall()

        won         = by_outcome.get(OUTCOME_TARGET1, 0) + by_outcome.get(OUTCOME_TARGET2, 0)
        lost        = by_outcome.get(OUTCOME_STOPPED, 0)
        squared_off = by_outcome.get(OUTCOME_SQUARED_OFF, 0)
        open_cnt    = by_outcome.get(OUTCOME_OPEN, 0)
        expired     = by_outcome.get(OUTCOME_EXPIRED, 0)
        total       = sum(by_outcome.values())
        closed      = won + lost + squared_off
        win_rate    = round(won / closed * 100, 1) if closed > 0 else 0.0

        by_strategy = {}
        for r in strat_rows:
            s_wins   = r["wins"]   or 0
            s_losses = r["losses"] or 0
            s_closed = s_wins + s_losses
            by_strategy[r["strategy"]] = {
                "total":       r["total"],
                "wins":        s_wins,
                "losses":      s_losses,
                "win_rate":    round(s_wins / s_closed * 100, 1) if s_closed else 0.0,
                "avg_r":       round(r["avg_r"], 3)        if r["avg_r"]       is not None else None,
                "net_pnl_inr": round(r["net_pnl"], 2)     if r["net_pnl"]     is not None else None,
                "avg_net_pnl": round(r["avg_net_pnl"], 2) if r["avg_net_pnl"] is not None else None,
            }

        return {
            "total":             total,
            "open":              open_cnt,
            "won":               won,
            "lost":              lost,
            "squared_off":       squared_off,
            "expired":           expired,
            "win_rate":          win_rate,
            "avg_r":             round(avg_r_row["avg_r"], 3)        if avg_r_row and avg_r_row["avg_r"]       is not None else None,
            "avg_net_pnl_inr":   round(pnl_row["avg_net_pnl"], 2)   if pnl_row   and pnl_row["avg_net_pnl"]  is not None else None,
            "total_net_pnl_inr": round(pnl_row["total_net_pnl"], 2) if pnl_row   and pnl_row["total_net_pnl"] is not None else None,
            "avg_cost_inr":      round(pnl_row["avg_cost"], 2)       if pnl_row   and pnl_row["avg_cost"]     is not None else None,
            "by_outcome":        by_outcome,
            "by_strategy":       by_strategy,
        }

    def purge_non_trading_day_signals(self) -> int:
        from data.market_status import ALL_HOLIDAYS
        deleted = 0
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, "SELECT DISTINCT signal_date FROM signal_log")
                dates = cur.fetchall()
                for row in dates:
                    d_str = row["signal_date"]
                    try:
                        d = datetime.strptime(d_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if d.weekday() >= 5 or d in ALL_HOLIDAYS:
                        c = self._exec(conn, "DELETE FROM signal_log WHERE signal_date=?", (d_str,))
                        deleted += c.rowcount
        except Exception as exc:
            logger.error(f"purge_non_trading_day_signals failed: {exc}")
        if deleted:
            logger.info(f"Purged {deleted} signal(s) from non-trading days.")
        return deleted


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[SignalLogger] = None


def get_signal_logger() -> SignalLogger:
    global _instance
    if _instance is None:
        _instance = SignalLogger()
    return _instance
