"""
Backtest run persistence layer.
Stores strategy specs + results in the same SQLite / PostgreSQL DB as signals.
"""
from __future__ import annotations

import json
import logging

from signals.signal_logger import SignalLogger, _USE_PG, SIGNALS_DB_PATH

logger = logging.getLogger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email      TEXT    NOT NULL,
    strategy_name   TEXT,
    spec_json       TEXT    NOT NULL,
    results_json    TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    error_msg       TEXT,
    run_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""
_CREATE_PG_SQL = _CREATE_SQL.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
).replace("datetime('now')", "NOW()")

_CREATE_IDX = "CREATE INDEX IF NOT EXISTS idx_bt_user ON backtest_runs (user_email, created_at)"


def _sl() -> SignalLogger:
    return SignalLogger(SIGNALS_DB_PATH)


def ensure_table() -> None:
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            sl._exec(conn, _CREATE_PG_SQL if _USE_PG else _CREATE_SQL)
            try:
                sl._exec(conn, _CREATE_IDX)
            except Exception:
                pass
    except Exception as e:
        logger.error("backtest_store ensure_table: %s", e)


def save_run(
    user_email: str,
    strategy_name: str,
    spec: dict,
    results: dict | None = None,
    status: str = "done",
    error_msg: str | None = None,
) -> int | None:
    ensure_table()
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            sl._exec(
                conn,
                "INSERT INTO backtest_runs"
                " (user_email, strategy_name, spec_json, results_json, status, error_msg)"
                " VALUES (?,?,?,?,?,?)",
                (
                    user_email,
                    strategy_name or "Unnamed Strategy",
                    json.dumps(spec),
                    json.dumps(results) if results else None,
                    status,
                    error_msg,
                ),
            )
            row = sl._exec(conn, "SELECT last_insert_rowid()").fetchone()
            return int(row[0]) if row else None
    except Exception as e:
        logger.error("backtest_store save_run: %s", e)
        return None


def update_run(
    run_id: int,
    results: dict | None,
    status: str = "done",
    error_msg: str | None = None,
) -> None:
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            sl._exec(
                conn,
                "UPDATE backtest_runs SET results_json=?, status=?, error_msg=? WHERE id=?",
                (json.dumps(results) if results else None, status, error_msg, run_id),
            )
    except Exception as e:
        logger.error("backtest_store update_run: %s", e)


def get_runs(user_email: str, limit: int = 30) -> list[dict]:
    ensure_table()
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            rows = sl._exec(
                conn,
                "SELECT id, strategy_name, status, created_at FROM backtest_runs"
                " WHERE user_email=? ORDER BY created_at DESC LIMIT ?",
                (user_email, limit),
            ).fetchall()
        return [{"id": r[0], "strategy_name": r[1], "status": r[2], "created_at": r[3]} for r in rows]
    except Exception as e:
        logger.error("backtest_store get_runs: %s", e)
        return []


def get_run(run_id: int) -> dict | None:
    ensure_table()
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            row = sl._exec(
                conn,
                "SELECT id, user_email, strategy_name, spec_json, results_json,"
                " status, error_msg, created_at FROM backtest_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "user_email": row[1], "strategy_name": row[2],
            "spec":     json.loads(row[3] or "{}"),
            "results":  json.loads(row[4]) if row[4] else None,
            "status":   row[5], "error_msg": row[6], "created_at": row[7],
        }
    except Exception as e:
        logger.error("backtest_store get_run: %s", e)
        return None


def run_count_today(user_email: str) -> int:
    """Used for free-tier usage cap checks."""
    ensure_table()
    sl = _sl()
    try:
        with sl._db_conn() as conn:
            row = sl._exec(
                conn,
                "SELECT COUNT(*) FROM backtest_runs WHERE user_email=?"
                " AND created_at >= date('now')",
                (user_email,),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
