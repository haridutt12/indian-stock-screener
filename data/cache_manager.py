"""
SQLite-backed TTL cache for stock data.
Survives Streamlit reruns and process restarts.
"""
import sqlite3
import json
import time
import pickle
import os
from typing import Any, Optional
from config.settings import CACHE_DB_PATH


class CacheManager:
    def __init__(self, db_path: str = CACHE_DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")

    def get(self, key: str) -> Optional[Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value_blob, expires_at = row
        if time.time() > expires_at:
            self.delete(key)
            return None
        return pickle.loads(value_blob)

    def set(self, key: str, value: Any, ttl: int):
        value_blob = pickle.dumps(value)
        now = time.time()
        expires_at = now + ttl
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache (key, value, expires_at, created_at)
                   VALUES (?, ?, ?, ?)""",
                (key, value_blob, expires_at, now),
            )

    def delete(self, key: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def invalidate_pattern(self, pattern: str):
        """Delete all keys containing the pattern substring."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"%{pattern}%",))

    def purge_expired(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))

    def clear_all(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM cache")


# Singleton instance
_cache = None

def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache
