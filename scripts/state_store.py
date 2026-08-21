"""Indexed profile state — decisions/receipts tail without full JSONL scans."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class ProfileStateStore:
    def __init__(self, state: Path) -> None:
        state.mkdir(parents=True, exist_ok=True)
        self.state = state
        self.path = state / "profile-state.sqlite"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_id TEXT,
                intent_id TEXT,
                recorded_utc TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS decisions_packet_uidx ON decisions(packet_id)
                WHERE packet_id IS NOT NULL AND packet_id <> '';
            CREATE INDEX IF NOT EXISTS decisions_packet_idx ON decisions(packet_id);
            CREATE INDEX IF NOT EXISTS decisions_recorded_idx ON decisions(recorded_utc);
            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jsonl_export_queue (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jsonl_export_queue_target_idx
                ON jsonl_export_queue(target, sequence);
            """
        )
        self.db.commit()
        self._decisions_jsonl: Path | None = None

    def close(self) -> None:
        self.db.close()

    def sync_decisions_from_jsonl(self, jsonl_path: Path) -> None:
        self._decisions_jsonl = jsonl_path
        if not jsonl_path.is_file():
            return
        offset_row = self.db.execute(
            "SELECT value FROM sync_meta WHERE key = 'decisions_jsonl_offset'"
        ).fetchone()
        offset = int(offset_row[0]) if offset_row else 0
        size = jsonl_path.stat().st_size
        if offset >= size:
            return
        with jsonl_path.open("rb") as stream:
            stream.seek(offset)
            chunk = stream.read()
        if not chunk:
            return
        pending: list[str] = []
        for raw in chunk.decode("utf-8").splitlines():
            if raw.strip():
                pending.append(raw)
        if not pending:
            return
        new_offset = offset + len(chunk)
        with self.db:
            for raw in pending:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    continue
                self._insert_decision(row)
            self.db.execute(
                """
                INSERT INTO sync_meta(key, value) VALUES ('decisions_jsonl_offset', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(new_offset),),
            )
            line_row = self.db.execute(
                "SELECT value FROM sync_meta WHERE key = 'decisions_jsonl_lines'"
            ).fetchone()
            prior_lines = int(line_row[0]) if line_row else 0
            self.db.execute(
                """
                INSERT INTO sync_meta(key, value) VALUES ('decisions_jsonl_lines', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(prior_lines + len(pending)),),
            )

    def bootstrap_decisions(self, jsonl_path: Path) -> None:
        self.sync_decisions_from_jsonl(jsonl_path)

    def append_decision(self, row: dict[str, Any], *, jsonl_path: Path | None = None) -> bool:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
        recorded = str(row.get("recorded_utc") or row.get("decision_utc") or "")
        target = str(jsonl_path) if jsonl_path is not None else "decisions.jsonl"
        inserted = False
        with self.db:
            inserted = self._insert_decision(row)
            if inserted:
                self.db.execute(
                    """
                    INSERT INTO jsonl_export_queue(target, payload_json, created_utc)
                    VALUES (?, ?, ?)
                    """,
                    (target, payload, recorded),
                )
        if jsonl_path is not None and inserted:
            self.export_pending_jsonl(jsonl_path)
        return inserted

    def export_pending_jsonl(self, jsonl_path: Path) -> int:
        """Drain export queue to JSONL after SQLite commit (GTHP-REAUDIT-01)."""
        target = str(jsonl_path)
        rows = self.db.execute(
            """
            SELECT sequence, payload_json FROM jsonl_export_queue
            WHERE target = ?
            ORDER BY sequence ASC
            """,
            (target,),
        ).fetchall()
        if not rows:
            return 0
        from common import append_jsonl

        exported = 0
        with self.db:
            for row in rows:
                append_jsonl(jsonl_path, json.loads(row["payload_json"]))
                self.db.execute(
                    "DELETE FROM jsonl_export_queue WHERE sequence = ?",
                    (row["sequence"],),
                )
                exported += 1
        return exported

    def export_backlog_count(self, jsonl_path: Path | None = None) -> int:
        target = str(jsonl_path) if jsonl_path is not None else "decisions.jsonl"
        row = self.db.execute(
            "SELECT COUNT(*) AS count FROM jsonl_export_queue WHERE target = ?",
            (target,),
        ).fetchone()
        return int(row[0]) if row else 0

    def _insert_decision(self, row: dict[str, Any]) -> bool:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
        packet_id = str(row.get("packet_id") or "")
        cursor = self.db.execute(
            """
            INSERT OR IGNORE INTO decisions (packet_id, intent_id, recorded_utc, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                packet_id,
                str(row.get("intent_id") or ""),
                str(row.get("recorded_utc") or row.get("decision_utc") or ""),
                payload,
            ),
        )
        return cursor.rowcount > 0

    def tail_decisions(self, limit: int) -> list[dict[str, Any]]:
        jsonl_path = self._decisions_jsonl or (self.state / "decisions.jsonl")
        if jsonl_path.is_file():
            self.sync_decisions_from_jsonl(jsonl_path)
        rows = self.db.execute(
            "SELECT payload_json FROM decisions ORDER BY sequence DESC LIMIT ?",
            (max(0, limit),),
        ).fetchall()
        decoded = [json.loads(row[0]) for row in reversed(rows)]
        return decoded

    def decision_by_packet(self, packet_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload_json FROM decisions WHERE packet_id = ? ORDER BY sequence DESC LIMIT 1",
            (packet_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None
