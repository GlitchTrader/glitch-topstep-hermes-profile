"""Fault-injection kill proofs for profile durability (audit Fases 1–2)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import append_jsonl, jsonl_contains_sequence  # noqa: E402
from model_owner_lock import (  # noqa: E402
    acquire_model_owner,
    model_owner_lock_path,
    read_model_owner,
    release_model_owner,
)
from state_store import ProfileStateStore  # noqa: E402
from workflows.intent_outbox import (  # noqa: E402
    gateway_receipt_gate,
    prune_delivered_outboxes,
    write_outbox_record,
)


class ExportCrashFaultTests(unittest.TestCase):
    def test_reexport_after_crash_between_append_and_dequeue_has_no_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            payload = {"packet_id": "p1"}
            try:
                with store.db:
                    store.db.execute(
                        """
                        INSERT INTO jsonl_export_queue(target, payload_json, created_utc)
                        VALUES (?, ?, ?)
                        """,
                        (
                            str(jsonl),
                            json.dumps(payload, separators=(",", ":")),
                            "2026-08-24T12:00:00Z",
                        ),
                    )
                row = store.db.execute(
                    "SELECT sequence FROM jsonl_export_queue WHERE target = ?",
                    (str(jsonl),),
                ).fetchone()
                sequence = int(row[0])
                # ponytail: simulate kill after append_jsonl but before queue DELETE
                append_jsonl(jsonl, {**payload, "export_sequence": sequence})
                self.assertEqual(store.export_backlog_count(jsonl), 1)
                line_count = len(jsonl.read_text(encoding="utf-8").strip().splitlines())
                self.assertEqual(store.export_pending_jsonl(jsonl), 0)
                self.assertEqual(len(jsonl.read_text(encoding="utf-8").strip().splitlines()), line_count)
                self.assertEqual(store.export_backlog_count(jsonl), 0)
            finally:
                store.close()

    def test_export_idempotent_when_jsonl_already_contains_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            jsonl = state / "decisions.jsonl"
            store = ProfileStateStore(state)
            try:
                append_jsonl(jsonl, {"packet_id": "p1", "export_sequence": 1})
                with store.db:
                    store.db.execute(
                        """
                        INSERT INTO jsonl_export_queue(target, payload_json, created_utc)
                        VALUES (?, ?, ?)
                        """,
                        (
                            str(jsonl),
                            json.dumps({"packet_id": "p1"}, separators=(",", ":")),
                            "2026-08-24T12:00:00Z",
                        ),
                    )
                self.assertEqual(store.export_pending_jsonl(jsonl), 0)
                self.assertEqual(store.export_backlog_count(jsonl), 0)
                self.assertEqual(len(jsonl.read_text(encoding="utf-8").strip().splitlines()), 1)
            finally:
                store.close()


class ModelOwnerLockFaultTests(unittest.TestCase):
    def test_concurrent_acquire_exactly_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            results: list[bool] = []
            barrier = threading.Barrier(2)

            def attempt(owner_kind: str, invocation_id: str) -> None:
                barrier.wait()
                results.append(
                    acquire_model_owner(
                        state,
                        owner_kind=owner_kind,  # type: ignore[arg-type]
                        invocation_id=invocation_id,
                    )
                )

            threads = [
                threading.Thread(target=attempt, args=("learning", "run-1")),
                threading.Thread(target=attempt, args=("learning", "run-2")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(sum(1 for won in results if won), 1)
            self.assertEqual(len(results), 2)

    def test_release_does_not_steal_new_owner_toctou(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            lock_path = model_owner_lock_path(state)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="direct_cycle",
                    invocation_id="run-a",
                )
            )
            original = read_model_owner(lock_path)
            assert isinstance(original, dict)
            new_owner = {
                **original,
                "owner_kind": "learning",
                "invocation_id": "run-b",
                "generation": int(original.get("generation") or 0) + 1,
            }
            lock_path.write_text(json.dumps(new_owner, separators=(",", ":")), encoding="utf-8")
            release_model_owner(state, owner_kind="direct_cycle", invocation_id="run-a")
            current = read_model_owner(lock_path)
            self.assertIsNotNone(current)
            assert isinstance(current, dict)
            self.assertEqual(current.get("invocation_id"), "run-b")
            self.assertEqual(current.get("owner_kind"), "learning")


class DeliveryAmbiguousFaultTests(unittest.TestCase):
    def test_gateway_receipt_gate_404_retains_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            intent = {"intent_id": "i-404", "action": "ENTER_LONG"}
            with mock.patch("parity.request_json", return_value=(404, None)):
                gate = gateway_receipt_gate(state, "pkt-1", intent, token="tok")
            self.assertEqual(gate, "retain_unknown")

    def test_prune_skips_delivery_unknown_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "outbox").mkdir()
            (state / "receipts").mkdir()
            outbox = state / "outbox" / "pkt-1.json"
            write_outbox_record(outbox, {"intent_id": "i1", "action": "ENTER_LONG"}, state="delivery_unknown")
            receipt = {
                "intent_id": "i1",
                "result": {"transport_error": "timeout"},
            }
            (state / "receipts" / "pkt-1.json").write_text(
                json.dumps(receipt, separators=(",", ":")),
                encoding="utf-8",
            )
            self.assertEqual(prune_delivered_outboxes(state), 0)
            self.assertTrue(outbox.is_file())


if __name__ == "__main__":
    unittest.main()
