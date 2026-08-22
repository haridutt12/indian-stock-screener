"""
SQLite-backed TTL cache for stock data.
Survives Streamlit reruns and process restarts.

Serialisation: JSON with typed envelope — no pickle, no RCE risk.
DataFrames are stored as {"__type__": "dataframe", "data": <split JSON>}.
All other values use {"__type__": "value", "data": <json-serialisable>}.
Existing pickle blobs in the DB are transparently evicted on read.
"""
import sqlite3
import json
import time
import os
from typing import Any, Optional
from config.settings import CACHE_DB_PATH


def _encode(value: Any) -> bytes:
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            return json.dumps({"__type__": "dataframe", "data": value.to_json(orient="split")}).encode()
    except ImportError:
        pass
    return json.dumps({"__type__": "value", "data": value}).encode()


def _decode(raw: bytes) -> Any:
    try:
        envelope = json.loads(raw)
    except Exception:
        # Unreadable (old pickle blob) — treat as miss so the key is evicted
        raise ValueError("undecodable")
    if envelope.get("__type__") == "dataframe":
        import pandas as pd
        return pd.read_json(envelope["data"], orient="split")
    return envelope["data"]


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
        raw, expires_at = row
        if time.time() > expires_at:
            self.delete(key)
            return None
        try:
            return _decode(raw)
        except Exception:
            # Corrupt or old pickle blob — evict and return miss
            self.delete(key)
            return None

    def set(self, key: str, value: Any, ttl: int):
        try:
            encoded = _encode(value)
        except (TypeError, ValueError):
            return  # skip un-serialisable values rather than crash
        now = time.time()
        expires_at = now + ttl
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cache (key, value, expires_at, created_at)
                   VALUES (?, ?, ?, ?)""",
                (key, encoded, expires_at, now),
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
