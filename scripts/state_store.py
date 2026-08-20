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
            CREATE INDEX IF NOT EXISTS decisions_packet_idx ON decisions(packet_id);
            CREATE INDEX IF NOT EXISTS decisions_recorded_idx ON decisions(recorded_utc);
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
        skip = self.db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        pending: list[str] = []
        for raw in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            if skip > 0:
                skip -= 1
                continue
            pending.append(raw)
        if not pending:
            return
        with self.db:
            for raw in pending:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    continue
                self._insert_decision(row)

    def bootstrap_decisions(self, jsonl_path: Path) -> None:
        self.sync_decisions_from_jsonl(jsonl_path)

    def append_decision(self, row: dict[str, Any], *, jsonl_path: Path | None = None) -> None:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
        with self.db:
            self._insert_decision(row)
        if jsonl_path is not None:
            from common import append_jsonl

            append_jsonl(jsonl_path, row)

    def _insert_decision(self, row: dict[str, Any]) -> None:
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
        self.db.execute(
            """
            INSERT INTO decisions (packet_id, intent_id, recorded_utc, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(row.get("packet_id") or ""),
                str(row.get("intent_id") or ""),
                str(row.get("recorded_utc") or row.get("decision_utc") or ""),
                payload,
            ),
        )

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
