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
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pytz

# Per-ticker mutex — serialises check+insert to prevent TOCTOU race when
# the scheduler and _catchup_signals() fire concurrently for the same ticker.
_ticker_locks: dict[str, threading.Lock] = {}
_ticker_locks_guard = threading.Lock()


def _get_ticker_lock(ticker: str) -> threading.Lock:
    with _ticker_locks_guard:
        if ticker not in _ticker_locks:
            _ticker_locks[ticker] = threading.Lock()
        return _ticker_locks[ticker]

if TYPE_CHECKING:
    from signals.signal_models import TradeSignal

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

SIGNALS_DB_PATH = Path("data_store/signals.db")

# ── Outcome constants ──────────────────────────────────────────────────────────────────
OUTCOME_OPEN        = "OPEN"
OUTCOME_TARGET1     = "TARGET1_HIT"
OUTCOME_TARGET2     = "TARGET2_HIT"
OUTCOME_STOPPED     = "STOPPED"
OUTCOME_SQUARED_OFF = "SQUARED_OFF"
OUTCOME_EXPIRED     = "EXPIRED"

SWING_EXPIRY_DAYS = 7

# ── Backend detection ────────────────────────────────────────────────────────────────

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

# ── Schema ───────────────────────────────────────────────────────────────────────

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

_CREATE_PORTFOLIO_SQL = """
CREATE TABLE IF NOT EXISTS user_portfolio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key    TEXT    NOT NULL,
    stock_name  TEXT    NOT NULL,
    ticker      TEXT    NOT NULL,
    qty         INTEGER NOT NULL,
    avg_price   REAL    NOT NULL,
    UNIQUE(user_key, stock_name)
)
"""
_CREATE_PORTFOLIO_PG_SQL = _CREATE_PORTFOLIO_SQL.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
)

_CREATE_ALLOWED_USERS_SQL = """
CREATE TABLE IF NOT EXISTS allowed_users (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email     TEXT    NOT NULL UNIQUE,
    name      TEXT    DEFAULT '',
    added_at  TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""
_CREATE_ALLOWED_USERS_PG_SQL = """
CREATE TABLE IF NOT EXISTS allowed_users (
    id        SERIAL  PRIMARY KEY,
    email     TEXT    NOT NULL UNIQUE,
    name      TEXT    DEFAULT '',
    added_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_CREATE_SENTIMENT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS sentiment_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT    NOT NULL UNIQUE,
    score      REAL    NOT NULL,
    label      TEXT    NOT NULL,
    key_themes TEXT,
    created_at TEXT    NOT NULL
)
"""
_CREATE_SENTIMENT_HISTORY_PG_SQL = """
CREATE TABLE IF NOT EXISTS sentiment_history (
    id         SERIAL  PRIMARY KEY,
    date       TEXT    NOT NULL UNIQUE,
    score      REAL    NOT NULL,
    label      TEXT    NOT NULL,
    key_themes TEXT,
    created_at TEXT    NOT NULL
)
"""

_CREATE_PRICE_ALERTS_SQL = """
CREATE TABLE IF NOT EXISTS price_alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL,
    alert_price  REAL    NOT NULL,
    condition    TEXT    NOT NULL,
    label        TEXT,
    created_at   TEXT    NOT NULL,
    triggered    INTEGER NOT NULL DEFAULT 0,
    triggered_at TEXT
)
"""
_CREATE_PRICE_ALERTS_PG_SQL = _CREATE_PRICE_ALERTS_SQL.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
)


def _make_signal_id(signal: "TradeSignal", date_str: str) -> str:
    # entry_price intentionally excluded — price fluctuates between scans,
    # but ticker+strategy+timeframe+date uniquely identifies a signal for the day.
    raw = f"{signal.ticker}|{signal.strategy}|{signal.timeframe}|{date_str}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


# ── SignalLogger ───────────────────────────────────────────────────────────────────────

class SignalLogger:
    """Thread-safe signal log backed by SQLite (local) or PostgreSQL (production)."""

    def __init__(self, db_path: Path = SIGNALS_DB_PATH):
        self._db_path = db_path
        self._init_db()

    # ── Connection management ────────────────────────────────────────────────────────────

    def _open_conn(self):
        if _USE_PG:
            from urllib.parse import unquote
            # Manual parse — urlparse breaks when password contains '@'
            # (Supabase-generated passwords often do). rfind('@') always
            # splits on the LAST '@', correctly separating userinfo from host.
            url = _DATABASE_URL
            rest = url.split("://", 1)[1].partition("?")[0]   # strip scheme + query
            at = rest.rfind("@")
            userinfo, hostinfo = rest[:at], rest[at + 1:]
            colon = userinfo.find(":")
            user = unquote(userinfo[:colon])
            password = unquote(userinfo[colon + 1:])
            host_port, _, dbname = hostinfo.partition("/")
            if ":" in host_port:
                host, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
            else:
                host, port = host_port, 5432
            return psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname or "postgres",
                user=user,
                password=password,
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

    # ── Schema init / migration ─────────────────────────────────────────────────────────

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

        # Portfolio table — created once, non-fatal if it fails
        try:
            _port_sql = _CREATE_PORTFOLIO_PG_SQL if _USE_PG else _CREATE_PORTFOLIO_SQL
            with self._db_conn() as conn:
                self._exec(conn, _port_sql)
        except Exception as _pe:
            logger.warning("user_portfolio table creation failed (non-fatal): %s", _pe)

        # Allowed users table — non-fatal if creation fails
        try:
            _au_sql = _CREATE_ALLOWED_USERS_PG_SQL if _USE_PG else _CREATE_ALLOWED_USERS_SQL
            with self._db_conn() as conn:
                self._exec(conn, _au_sql)
        except Exception as _aue:
            logger.warning("allowed_users table creation failed (non-fatal): %s", _aue)

        # Sentiment history table — non-fatal if creation fails
        try:
            _sh_sql = _CREATE_SENTIMENT_HISTORY_PG_SQL if _USE_PG else _CREATE_SENTIMENT_HISTORY_SQL
            with self._db_conn() as conn:
                self._exec(conn, _sh_sql)
        except Exception as _she:
            logger.warning("sentiment_history table creation failed (non-fatal): %s", _she)

        # Price alerts table — non-fatal if creation fails
        try:
            _pa_sql = _CREATE_PRICE_ALERTS_PG_SQL if _USE_PG else _CREATE_PRICE_ALERTS_SQL
            with self._db_conn() as conn:
                self._exec(conn, _pa_sql)
        except Exception as _pae:
            logger.warning("price_alerts table creation failed (non-fatal): %s", _pae)

        # Dedup migration — runs every startup, fully idempotent.
        # Step 1: try to create the unique index directly (no-op if it exists).
        # Step 2: if that fails because duplicates exist, delete them first, then retry.
        # Using separate connections so a failed CREATE INDEX doesn't abort the DELETE.
        try:
            with self._db_conn() as conn:
                self._exec(conn, """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_sl_uniq_signal
                    ON signal_log (ticker, strategy, timeframe, signal_date)
                """)
        except Exception:
            # Duplicates exist — delete all but the highest-id row per combo, then create index.
            try:
                with self._db_conn() as conn:
                    self._exec(conn, """
                        DELETE FROM signal_log
                        WHERE id NOT IN (
                            SELECT MAX(id) FROM signal_log
                            GROUP BY ticker, strategy, timeframe, signal_date
                        )
                    """)
                    logger.info("Dedup migration: removed duplicate signals.")
                with self._db_conn() as conn:
                    self._exec(conn, """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_sl_uniq_signal
                        ON signal_log (ticker, strategy, timeframe, signal_date)
                    """)
                    logger.info("Dedup migration: unique index created.")
            except Exception as exc2:
                logger.warning(f"Dedup migration failed (non-fatal): {exc2}")

    # ── Write ──────────────────────────────────────────────────────────────────────────

    def log_signal(self, signal: "TradeSignal") -> bool:
        # Serialize per ticker so concurrent scans (scheduler + catchup) can't
        # both see "0 OPEN" before either has committed its INSERT (TOCTOU fix).
        with _get_ticker_lock(signal.ticker):
            return self._log_signal_locked(signal)

    def _log_signal_locked(self, signal: "TradeSignal") -> bool:
        # One-trade-per-ticker rule: don't open a second position while one is OPEN.
        # Fail-safe: if the guard check itself throws, refuse to insert (return False)
        # rather than silently continuing — a missed signal is safer than a duplicate.
        try:
            with self._db_conn() as conn:
                cur = self._exec(
                    conn,
                    "SELECT COUNT(*) as n FROM signal_log WHERE ticker=? AND outcome=?"
                    if not _USE_PG else
                    "SELECT COUNT(*) as n FROM signal_log WHERE ticker=%s AND outcome=%s",
                    (signal.ticker, OUTCOME_OPEN),
                )
                row = cur.fetchone()
                n   = (row["n"] if isinstance(row, dict) else row[0]) if row else 0
                if n > 0:
                    logger.debug(
                        "Skipping %s (%s): already has an OPEN position",
                        signal.ticker, signal.strategy,
                    )
                    return False
        except Exception as _exc:
            logger.warning("One-trade-per-ticker check failed — skipping insert: %s", _exc)
            return False  # Fail-safe: guard failure → refuse to insert, never continue

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
            sql = (f"INSERT INTO signal_log ({cols}) VALUES ({ph}) "
                   f"ON CONFLICT (ticker, strategy, timeframe, signal_date) DO NOTHING")
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

    def update_stop_loss(self, signal_id: str, new_stop: float) -> None:
        sql = "UPDATE signal_log SET stop_loss=? WHERE signal_id=? AND outcome=?"
        try:
            with self._db_conn() as conn:
                self._exec(conn, sql, (round(new_stop, 2), signal_id, OUTCOME_OPEN))
        except Exception as exc:
            logger.error(f"SignalLogger.update_stop_loss failed ({signal_id}): {exc}")

    # ── Sentiment history ────────────────────────────────────────────────────────────

    def log_daily_sentiment(
        self,
        score: float,
        label: str,
        key_themes: list[str] | None = None,
        date_str: str | None = None,
    ) -> None:
        """Upsert today's market sentiment score. Called by scheduler + News page."""
        today = date_str or date.today().isoformat()
        themes_json = json.dumps(key_themes or [])
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        if _USE_PG:
            sql = """
                INSERT INTO sentiment_history (date, score, label, key_themes, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (date) DO UPDATE SET
                    score=EXCLUDED.score, label=EXCLUDED.label,
                    key_themes=EXCLUDED.key_themes, created_at=EXCLUDED.created_at
            """
        else:
            sql = """
                INSERT OR REPLACE INTO sentiment_history (date, score, label, key_themes, created_at)
                VALUES (?, ?, ?, ?, ?)
            """
        try:
            with self._db_conn() as conn:
                self._exec(conn, sql, (today, round(score, 2), label, themes_json, now_str))
        except Exception as exc:
            logger.error(f"SignalLogger.log_daily_sentiment failed: {exc}")

    def get_sentiment_history(self, days: int = 30) -> list[dict]:
        """Return daily sentiment rows for the past N days, oldest first."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        sql = """
            SELECT date, score, label, key_themes
            FROM sentiment_history
            WHERE date >= ?
            ORDER BY date ASC
        """
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql, (cutoff,))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    row = dict(r)
                    try:
                        row["key_themes"] = json.loads(row.get("key_themes") or "[]")
                    except Exception:
                        row["key_themes"] = []
                    result.append(row)
                return result
        except Exception as exc:
            logger.warning(f"SignalLogger.get_sentiment_history failed: {exc}")
            return []

    # ── Read ──────────────────────────────────────────────────────────────────────────

    def get_open_signals(self, timeframe: Optional[str] = None) -> list[dict]:
        # One row per ticker (MAX id wins) — one open position per stock, always.
        if timeframe:
            sql = """
                SELECT * FROM signal_log
                WHERE id IN (
                    SELECT MAX(id) FROM signal_log
                    WHERE outcome=? AND timeframe=?
                    GROUP BY ticker
                )
                ORDER BY logged_at DESC
            """
            params: tuple = (OUTCOME_OPEN, timeframe)
        else:
            sql = """
                SELECT * FROM signal_log
                WHERE id IN (
                    SELECT MAX(id) FROM signal_log
                    WHERE outcome=?
                    GROUP BY ticker
                )
                ORDER BY logged_at DESC
            """
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
        # Deduplicate at query time — one row per (ticker, strategy, timeframe, signal_date),
        # keeping the highest id, so any duplicate rows never reach the caller.
        dedup_sql = f"""
            SELECT * FROM signal_log
            WHERE id IN (
                SELECT MAX(id) FROM signal_log
                WHERE {where}
                GROUP BY ticker, strategy, timeframe, signal_date
            )
            ORDER BY logged_at DESC
        """
        with self._db_conn() as conn:
            cur = self._exec(conn, dedup_sql, params)
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

        # Same dedup logic as get_signals(): keep only MAX(id) per
        # (ticker, strategy, timeframe, signal_date) so expired duplicates
        # created by close_duplicate_open_positions() don't inflate counts.
        dedup_sub = (
            f"SELECT MAX(id) FROM signal_log WHERE {where} "
            f"GROUP BY ticker, strategy, timeframe, signal_date"
        )

        with self._db_conn() as conn:
            cur = self._exec(
                conn,
                f"SELECT outcome, COUNT(*) AS cnt FROM signal_log "
                f"WHERE id IN ({dedup_sub}) GROUP BY outcome",
                params,
            )
            by_outcome = {r["outcome"]: r["cnt"] for r in cur.fetchall()}

            cur = self._exec(
                conn,
                f"SELECT AVG(net_pnl_r) AS avg_r FROM signal_log "
                f"WHERE id IN ({dedup_sub}) AND outcome NOT IN (?,?) AND net_pnl_r IS NOT NULL",
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
                WHERE id IN ({dedup_sub}) AND outcome NOT IN (?,?)
                """,
                params + [OUTCOME_OPEN, OUTCOME_EXPIRED],
            )
            pnl_row = cur.fetchone()

            cur = self._exec(
                conn,
                f"""
                SELECT strategy,
                       COUNT(*) AS total,
                       SUM(CASE WHEN outcome=? THEN 1 ELSE 0 END) AS open_count,
                       SUM(CASE WHEN outcome=? THEN 1 ELSE 0 END) AS expired_count,
                       SUM(CASE WHEN outcome IN (?,?)
                                  OR (outcome=? AND COALESCE(net_pnl_inr, gross_pnl_inr, 0) > 0)
                                THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN outcome=?
                                  OR (outcome=? AND COALESCE(net_pnl_inr, gross_pnl_inr, 0) <= 0)
                                THEN 1 ELSE 0 END) AS losses,
                       AVG(CASE WHEN outcome NOT IN (?,?) AND net_pnl_r IS NOT NULL THEN net_pnl_r END) AS avg_r,
                       SUM(CASE WHEN outcome NOT IN (?,?) THEN net_pnl_inr END)  AS net_pnl,
                       AVG(CASE WHEN outcome NOT IN (?,?) THEN net_pnl_inr END)  AS avg_net_pnl
                FROM signal_log
                WHERE id IN ({dedup_sub})
                GROUP BY strategy
                """,
                [
                    OUTCOME_OPEN,
                    OUTCOME_EXPIRED,
                    OUTCOME_TARGET1, OUTCOME_TARGET2, OUTCOME_SQUARED_OFF,
                    OUTCOME_STOPPED, OUTCOME_SQUARED_OFF,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                    OUTCOME_OPEN, OUTCOME_EXPIRED,
                ] + params,
            )
            strat_rows = cur.fetchall()

            cur = self._exec(
                conn,
                f"SELECT COUNT(*) AS cnt FROM signal_log "
                f"WHERE id IN ({dedup_sub}) AND outcome=? "
                f"AND COALESCE(net_pnl_inr, gross_pnl_inr, 0) > 0",
                params + [OUTCOME_SQUARED_OFF],
            )
            sq_profitable = (cur.fetchone() or {}).get("cnt", 0) or 0

        won         = by_outcome.get(OUTCOME_TARGET1, 0) + by_outcome.get(OUTCOME_TARGET2, 0) + sq_profitable
        lost        = by_outcome.get(OUTCOME_STOPPED, 0) + (by_outcome.get(OUTCOME_SQUARED_OFF, 0) - sq_profitable)
        squared_off = by_outcome.get(OUTCOME_SQUARED_OFF, 0)
        open_cnt    = by_outcome.get(OUTCOME_OPEN, 0)
        expired     = by_outcome.get(OUTCOME_EXPIRED, 0)
        total       = sum(by_outcome.values())
        closed      = by_outcome.get(OUTCOME_TARGET1, 0) + by_outcome.get(OUTCOME_TARGET2, 0) + by_outcome.get(OUTCOME_STOPPED, 0) + squared_off
        win_rate    = round(won / closed * 100, 1) if closed > 0 else 0.0

        by_strategy = {}
        for r in strat_rows:
            s_wins    = r["wins"]         or 0
            s_losses  = r["losses"]       or 0
            s_open    = r["open_count"]   or 0
            s_expired = r["expired_count"] or 0
            s_closed  = s_wins + s_losses
            by_strategy[r["strategy"]] = {
                "total":        r["total"],
                "open_count":   s_open,
                "expired_count": s_expired,
                "wins":         s_wins,
                "losses":       s_losses,
                "win_rate":     round(s_wins / s_closed * 100, 1) if s_closed else 0.0,
                "avg_r":        round(r["avg_r"], 3)        if r["avg_r"]       is not None else None,
                "net_pnl_inr":  round(r["net_pnl"], 2)     if r["net_pnl"]     is not None else None,
                "avg_net_pnl":  round(r["avg_net_pnl"], 2) if r["avg_net_pnl"] is not None else None,
            }

        target_wins = by_outcome.get(OUTCOME_TARGET1, 0) + by_outcome.get(OUTCOME_TARGET2, 0)
        sq_losing   = squared_off - sq_profitable

        return {
            "total":             total,
            "open":              open_cnt,
            "won":               won,
            "lost":              lost,
            "target_wins":       target_wins,
            "sq_profitable":     sq_profitable,
            "sq_losing":         sq_losing,
            "squared_off":       squared_off,
            "stops":             by_outcome.get(OUTCOME_STOPPED, 0),
            "expired":           expired,
            "win_rate":          win_rate,
            "avg_r":             round(avg_r_row["avg_r"], 3)        if avg_r_row and avg_r_row["avg_r"]       is not None else None,
            "avg_net_pnl_inr":   round(pnl_row["avg_net_pnl"], 2)   if pnl_row   and pnl_row["avg_net_pnl"]  is not None else None,
            "total_net_pnl_inr": round(pnl_row["total_net_pnl"], 2) if pnl_row   and pnl_row["total_net_pnl"] is not None else None,
            "avg_cost_inr":      round(pnl_row["avg_cost"], 2)       if pnl_row   and pnl_row["avg_cost"]     is not None else None,
            "by_outcome":        by_outcome,
            "by_strategy":       by_strategy,
        }

    def get_duplicate_count(self) -> int:
        """Return the number of duplicate signal rows currently in the DB."""
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, """
                    SELECT COALESCE(SUM(cnt - 1), 0) AS extra_rows FROM (
                        SELECT COUNT(*) AS cnt
                        FROM signal_log
                        GROUP BY ticker, strategy, timeframe, signal_date
                        HAVING cnt > 1
                    ) t
                """)
                row = cur.fetchone()
                return int(row[0] if row else 0)
        except Exception as exc:
            logger.error(f"get_duplicate_count failed: {exc}")
            return -1

    def purge_duplicates(self) -> int:
        """
        Delete all but the highest-id row for each (ticker, strategy, timeframe, signal_date)
        group, then ensure the unique index exists.
        Returns the number of rows deleted.
        """
        deleted = 0
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, """
                    DELETE FROM signal_log
                    WHERE id NOT IN (
                        SELECT MAX(id) FROM signal_log
                        GROUP BY ticker, strategy, timeframe, signal_date
                    )
                """)
                deleted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            logger.info(f"purge_duplicates: removed {deleted} duplicate row(s).")
        except Exception as exc:
            logger.error(f"purge_duplicates DELETE failed: {exc}")
            return -1

        # Ensure the unique index exists after the cleanup
        try:
            with self._db_conn() as conn:
                self._exec(conn, """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_sl_uniq_signal
                    ON signal_log (ticker, strategy, timeframe, signal_date)
                """)
        except Exception as exc:
            logger.warning(f"purge_duplicates: unique index creation failed: {exc}")

        return deleted

    def close_duplicate_open_positions(self) -> int:
        """
        Expire all but the most-recently-inserted OPEN signal for each ticker.
        This enforces the one-open-position-per-ticker rule retroactively in the DB,
        so stale duplicates can never surface in the UI.
        Returns the number of rows updated (expired).
        """
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            UPDATE signal_log
            SET outcome = ?, outcome_at = ?
            WHERE outcome = ?
            AND id NOT IN (
                SELECT MAX(id) FROM signal_log
                WHERE outcome = ?
                GROUP BY ticker
            )
        """
        params = (OUTCOME_EXPIRED, now_str, OUTCOME_OPEN, OUTCOME_OPEN)
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql, params)
                n = cur.rowcount or 0
            if n:
                logger.info("close_duplicate_open_positions: expired %d stale duplicate(s).", n)
            return n
        except Exception as exc:
            logger.error("close_duplicate_open_positions failed: %s", exc)
            return 0

    def save_portfolio(self, user_key: str, holdings: list[dict]) -> None:
        """Persist a user's portfolio holdings (replace-all semantics)."""
        try:
            with self._db_conn() as conn:
                self._exec(conn, "DELETE FROM user_portfolio WHERE user_key=?", (user_key,))
                for h in holdings:
                    self._exec(conn,
                        "INSERT INTO user_portfolio (user_key, stock_name, ticker, qty, avg_price) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (user_key, h["name"], h["ticker"], int(h["qty"]), float(h["avg_price"])),
                    )
        except Exception as exc:
            logger.error("save_portfolio failed: %s", exc)

    def load_portfolio(self, user_key: str) -> list[dict]:
        """Return saved holdings for a user, or [] if none / table missing."""
        try:
            with self._db_conn() as conn:
                cur = self._exec(
                    conn,
                    "SELECT stock_name, ticker, qty, avg_price FROM user_portfolio "
                    "WHERE user_key=? ORDER BY id",
                    (user_key,),
                )
                return [
                    {"name": r["stock_name"], "ticker": r["ticker"],
                     "qty": r["qty"], "avg_price": r["avg_price"]}
                    for r in cur.fetchall()
                ]
        except Exception as exc:
            logger.error("load_portfolio failed: %s", exc)
            return []

    # ── Allowed users (access control) ──────────────────────────────────────────────────

    def is_user_allowed(self, email: str) -> bool:
        """Return True if email is in the allowed_users table (case-insensitive)."""
        try:
            with self._db_conn() as conn:
                cur = self._exec(
                    conn,
                    "SELECT 1 FROM allowed_users WHERE LOWER(email)=LOWER(?)",
                    (email.strip(),),
                )
                return cur.fetchone() is not None
        except Exception as exc:
            logger.error("is_user_allowed failed: %s", exc)
            return False

    def add_allowed_user(self, email: str, name: str = "") -> bool:
        """Insert an email into the allowlist. Returns True on success, False if already exists."""
        try:
            with self._db_conn() as conn:
                self._exec(
                    conn,
                    "INSERT OR IGNORE INTO allowed_users (email, name) VALUES (?, ?)",
                    (email.strip().lower(), name.strip()),
                )
            return True
        except Exception as exc:
            logger.error("add_allowed_user failed: %s", exc)
            return False

    def remove_allowed_user(self, email: str) -> bool:
        """Remove an email from the allowlist. Returns True on success."""
        try:
            with self._db_conn() as conn:
                self._exec(
                    conn,
                    "DELETE FROM allowed_users WHERE LOWER(email)=LOWER(?)",
                    (email.strip(),),
                )
            return True
        except Exception as exc:
            logger.error("remove_allowed_user failed: %s", exc)
            return False

    def list_allowed_users(self) -> list[dict]:
        """Return all allowed users as list of dicts with keys: email, name, added_at."""
        try:
            with self._db_conn() as conn:
                cur = self._exec(
                    conn,
                    "SELECT email, name, added_at FROM allowed_users ORDER BY added_at",
                )
                return [
                    {"email": r["email"], "name": r["name"] or "", "added_at": r["added_at"]}
                    for r in cur.fetchall()
                ]
        except Exception as exc:
            logger.error("list_allowed_users failed: %s", exc)
            return []

    # ── Price Alerts ────────────────────────────────────────────────────────────────────

    def add_price_alert(
        self,
        ticker: str,
        alert_price: float,
        condition: str,
        label: str = "",
    ) -> int:
        """Insert a new price alert. condition must be 'above' or 'below'. Returns the new row id."""
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT INTO price_alerts (ticker, alert_price, condition, label, created_at, triggered)
            VALUES (?, ?, ?, ?, ?, 0)
        """
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql, (ticker, round(alert_price, 2), condition, label or "", now_str))
                if _USE_PG:
                    cur2 = self._exec(conn, "SELECT lastval()")
                    row = cur2.fetchone()
                    return int(row[0]) if row else -1
                return cur.lastrowid or -1
        except Exception as exc:
            logger.error("add_price_alert failed: %s", exc)
            return -1

    def get_active_alerts(self) -> list[dict]:
        """Return all alerts that have not been triggered yet."""
        sql = "SELECT * FROM price_alerts WHERE triggered=0 ORDER BY created_at DESC"
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql)
                return [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            logger.error("get_active_alerts failed: %s", exc)
            return []

    def mark_alert_triggered(self, alert_id: int) -> None:
        """Mark a price alert as triggered (idempotent)."""
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        sql = "UPDATE price_alerts SET triggered=1, triggered_at=? WHERE id=?"
        try:
            with self._db_conn() as conn:
                self._exec(conn, sql, (now_str, alert_id))
        except Exception as exc:
            logger.error("mark_alert_triggered failed: %s", exc)

    def delete_price_alert(self, alert_id: int) -> None:
        """Permanently remove a price alert by id."""
        try:
            with self._db_conn() as conn:
                self._exec(conn, "DELETE FROM price_alerts WHERE id=?", (alert_id,))
        except Exception as exc:
            logger.error("delete_price_alert failed: %s", exc)

    def get_all_alerts(self) -> list[dict]:
        """Return all alerts (active and triggered), newest first."""
        sql = "SELECT * FROM price_alerts ORDER BY created_at DESC"
        try:
            with self._db_conn() as conn:
                cur = self._exec(conn, sql)
                return [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            logger.error("get_all_alerts failed: %s", exc)
            return []

    def purge_non_trading_day_signals(self) -> int:
        """
        Purge INTRADAY-only signals logged on weekends/holidays.
        SWING signals are intentionally kept — they're generated on any day and
        tracked across multiple calendar days including non-trading ones.
        """
        from data.market_status import ALL_HOLIDAYS
        deleted = 0
        try:
            with self._db_conn() as conn:
                cur = self._exec(
                    conn,
                    "SELECT DISTINCT signal_date FROM signal_log WHERE timeframe='INTRADAY'",
                )
                dates = cur.fetchall()
                for row in dates:
                    d_str = row["signal_date"]
                    try:
                        d = datetime.strptime(d_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if d.weekday() >= 5 or d in ALL_HOLIDAYS:
                        c = self._exec(
                            conn,
                            "DELETE FROM signal_log WHERE signal_date=? AND timeframe='INTRADAY'",
                            (d_str,),
                        )
                        deleted += c.rowcount
        except Exception as exc:
            logger.error(f"purge_non_trading_day_signals failed: {exc}")
        if deleted:
            logger.info(f"Purged {deleted} intraday signal(s) from non-trading days.")
        return deleted

    def get_confluence_signals(self) -> list[dict]:
        """
        Return tickers that have BOTH an open SWING and an open INTRADAY signal.
        These are multi-timeframe confluences — highest-conviction setups.
        Returns list of dicts with keys: ticker, swing_signal, intraday_signal, direction.
        """
        try:
            with self._db_conn() as conn:
                # All open signals, both timeframes
                cur = self._exec(
                    conn,
                    """
                    SELECT ticker, timeframe, strategy, direction, entry_price,
                           stop_loss, target_1, target_2, risk_reward, confidence,
                           signal_date, signal_id
                    FROM signal_log
                    WHERE outcome=?
                    ORDER BY logged_at DESC
                    """,
                    (OUTCOME_OPEN,),
                )
                rows = [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            logger.error("get_confluence_signals failed: %s", exc)
            return []

        swing_by_ticker: dict = {}
        intra_by_ticker: dict = {}
        for r in rows:
            t = r["ticker"]
            if r["timeframe"] == "SWING" and t not in swing_by_ticker:
                swing_by_ticker[t] = r
            elif r["timeframe"] == "INTRADAY" and t not in intra_by_ticker:
                intra_by_ticker[t] = r

        confluences = []
        for ticker, swing in swing_by_ticker.items():
            intra = intra_by_ticker.get(ticker)
            if intra and swing["direction"] == intra["direction"]:
                confluences.append({
                    "ticker":          ticker,
                    "direction":       swing["direction"],
                    "swing_strategy":  swing["strategy"],
                    "intra_strategy":  intra["strategy"],
                    "entry":           swing["entry_price"],
                    "stop_loss":       swing["stop_loss"],
                    "target_1":        swing["target_1"],
                    "target_2":        swing["target_2"],
                    "confidence":      max(swing["confidence"] or 1, intra["confidence"] or 1),
                    "risk_reward":     swing["risk_reward"],
                })
        return confluences


# ── Singleton ──────────────────────────────────────────────────────────────────────────

_instance: Optional[SignalLogger] = None


def get_signal_logger() -> SignalLogger:
    global _instance
    if _instance is None:
        _instance = SignalLogger()
    return _instance
