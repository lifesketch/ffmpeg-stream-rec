"""SQLite: состояние сессий записи."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionRow:
    id: str
    stream_url: str
    storage_mode: int
    subpath: str | None
    basename: str
    current_part: int
    status: str
    pid: int | None
    manual_stop: bool
    continuation_count: int
    max_continuations: int
    browser_download_hint: bool
    created_at: str
    updated_at: str
    ended_at: str | None
    current_output_path: str | None
    completed_parts_json: str


@dataclass
class HistoryRow:
    id: str
    stream_url: str
    basename: str
    storage_mode: int
    subpath: str | None
    added_at: str


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    stream_url TEXT NOT NULL,
                    storage_mode INTEGER NOT NULL,
                    subpath TEXT,
                    basename TEXT NOT NULL,
                    current_part INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    pid INTEGER,
                    manual_stop INTEGER NOT NULL DEFAULT 0,
                    continuation_count INTEGER NOT NULL DEFAULT 0,
                    max_continuations INTEGER NOT NULL,
                    browser_download_hint INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    current_output_path TEXT,
                    completed_parts TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            cur = conn.execute("PRAGMA table_info(sessions)")
            scols = {row[1] for row in cur.fetchall()}
            if "ended_at" not in scols:
                conn.execute("ALTER TABLE sessions ADD COLUMN ended_at TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_history (
                    id TEXT PRIMARY KEY,
                    stream_url TEXT NOT NULL,
                    basename TEXT NOT NULL,
                    storage_mode INTEGER NOT NULL,
                    subpath TEXT,
                    added_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def row_to_session(self, row: sqlite3.Row) -> SessionRow:
        try:
            ended_val = row["ended_at"]
        except (IndexError, KeyError):
            ended_val = None
        return SessionRow(
            id=row["id"],
            stream_url=row["stream_url"],
            storage_mode=row["storage_mode"],
            subpath=row["subpath"],
            basename=row["basename"],
            current_part=row["current_part"],
            status=row["status"],
            pid=row["pid"],
            manual_stop=bool(row["manual_stop"]),
            continuation_count=row["continuation_count"],
            max_continuations=row["max_continuations"],
            browser_download_hint=bool(row["browser_download_hint"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ended_at=ended_val,
            current_output_path=row["current_output_path"],
            completed_parts_json=row["completed_parts"],
        )

    def create_session(
        self,
        *,
        stream_url: str,
        storage_mode: int,
        subpath: str | None,
        basename: str,
        current_part: int,
        max_continuations: int,
        browser_download_hint: bool,
        status: str,
        pid: int | None,
        current_output_path: str | None,
    ) -> str:
        sid = str(uuid.uuid4())
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, stream_url, storage_mode, subpath, basename, current_part,
                    status, pid, manual_stop, continuation_count, max_continuations,
                    browser_download_hint, created_at, updated_at, ended_at,
                    current_output_path, completed_parts
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    stream_url,
                    storage_mode,
                    subpath,
                    basename,
                    current_part,
                    status,
                    pid,
                    0,
                    0,
                    max_continuations,
                    1 if browser_download_hint else 0,
                    now,
                    now,
                    None,
                    current_output_path,
                    "[]",
                ),
            )
            conn.commit()
        return sid

    def get(self, session_id: str) -> SessionRow | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            return self.row_to_session(row) if row else None

    def update(
        self,
        session_id: str,
        **fields: Any,
    ) -> None:
        if not fields:
            return
        fields = dict(fields)
        fields["updated_at"] = _utc_now()
        if "manual_stop" in fields:
            fields["manual_stop"] = 1 if fields["manual_stop"] else 0
        if "browser_download_hint" in fields:
            fields["browser_download_hint"] = (
                1 if fields["browser_download_hint"] else 0
            )
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        values.append(session_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE sessions SET {cols} WHERE id = ?", values)
            conn.commit()

    def append_completed_part(self, session_id: str, rel_path: str) -> None:
        sess = self.get(session_id)
        if not sess:
            return
        parts = json.loads(sess.completed_parts_json or "[]")
        if rel_path not in parts:
            parts.append(rel_path)
        self.update(session_id, completed_parts=json.dumps(parts, ensure_ascii=False))

    def list_all(self) -> list[SessionRow]:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC")
            return [self.row_to_session(r) for r in cur.fetchall()]

    def count_recording(self) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = ?", ("recording",)
            )
            return int(cur.fetchone()[0])

    def add_recording_history(
        self,
        *,
        stream_url: str,
        basename: str,
        storage_mode: int,
        subpath: str | None,
    ) -> str:
        hid = str(uuid.uuid4())
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO recording_history (
                    id, stream_url, basename, storage_mode, subpath, added_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (hid, stream_url, basename, storage_mode, subpath, now),
            )
            conn.commit()
        return hid

    def list_recording_history(self) -> list[HistoryRow]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM recording_history ORDER BY added_at DESC"
            )
            rows = []
            for r in cur.fetchall():
                rows.append(
                    HistoryRow(
                        id=r["id"],
                        stream_url=r["stream_url"],
                        basename=r["basename"],
                        storage_mode=r["storage_mode"],
                        subpath=r["subpath"],
                        added_at=r["added_at"],
                    )
                )
            return rows

    def get_recording_history(self, history_id: str) -> HistoryRow | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM recording_history WHERE id = ?", (history_id,)
            )
            r = cur.fetchone()
            if not r:
                return None
            return HistoryRow(
                id=r["id"],
                stream_url=r["stream_url"],
                basename=r["basename"],
                storage_mode=r["storage_mode"],
                subpath=r["subpath"],
                added_at=r["added_at"],
            )

    def delete_recording_history(self, history_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM recording_history WHERE id = ?", (history_id,)
            )
            conn.commit()
            return cur.rowcount > 0
