"""Durable, audit-friendly local research state."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    report_path TEXT NOT NULL,
    holdout_evaluated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
"""


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "research.sqlite3"
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_by_fingerprint(self, fingerprint: str) -> dict | None:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM experiments WHERE fingerprint=?", (fingerprint,)).fetchone()
            return dict(r) if r else None

    def get(self, run_id: str) -> dict | None:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM experiments WHERE id=?", (run_id,)).fetchone()
            return dict(r) if r else None

    def save(self, fingerprint: str, candidate: dict, metadata: dict, result: dict, status: str,
             report_path: Path) -> str:
        run_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute("INSERT INTO experiments (id,fingerprint,created_at,status,candidate_json,metadata_json,result_json,report_path) VALUES (?,?,?,?,?,?,?,?)",
                         (run_id, fingerprint, now, status, json.dumps(candidate),
                          json.dumps(metadata), json.dumps(result), str(report_path)))
        return run_id

    def finalize(self, run_id: str, result: dict, status: str) -> None:
        with self.connect() as conn:
            cursor = conn.execute("UPDATE experiments SET result_json=?,status=?,holdout_evaluated=1 WHERE id=? AND holdout_evaluated=0 AND status='PENDING_SEALED_HOLDOUT'",
                                  (json.dumps(result), status, run_id))
            if cursor.rowcount != 1:
                raise ValueError("Holdout already evaluated or experiment not eligible")

    def list(self, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(x) for x in conn.execute("SELECT id,created_at,fingerprint,status,report_path FROM experiments ORDER BY created_at DESC LIMIT ?", (limit,))]

    def usage_count(self) -> int:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self.connect() as conn:
            return conn.execute("SELECT count(*) FROM usage WHERE called_at LIKE ?", (month + "%",)).fetchone()[0]

    def reserve_api_call(self, model: str, monthly_limit: int) -> int:
        """Count attempts before calling API, even if request fails. Not a spend meter."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT count(*) FROM usage WHERE called_at LIKE ?", (month + "%",)).fetchone()[0]
            if count >= monthly_limit:
                raise RuntimeError("Monthly API call limit reached; check provider spend cap")
            cursor = conn.execute("INSERT INTO usage (called_at,model) VALUES (?,?)",
                                  (datetime.now(timezone.utc).isoformat(), model))
            return cursor.lastrowid

    def record_usage(self, attempt_id: int, usage: dict) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE usage SET input_tokens=?,output_tokens=? WHERE id=?",
                         (int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), attempt_id))

    def paused(self) -> bool:
        return (self.root / "PAUSED").exists()

    def set_paused(self, paused: bool) -> None:
        path = self.root / "PAUSED"
        if paused:
            path.write_text("Paused by user\n")
        else:
            path.unlink(missing_ok=True)
