"""Tests for production evaluation lease and cron defer coordination."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evaluation_lease import (  # noqa: E402
    ProductionEvaluationLease,
    acquire_evaluation_lease,
    defer_production_worker_if_evaluation_lease,
    evaluation_lease_active,
    evaluation_lease_path,
    read_evaluation_lease,
    release_evaluation_lease,
    renew_evaluation_lease,
)
from model_owner_lock import acquire_model_owner, release_model_owner  # noqa: E402


class EvaluationLeaseTests(unittest.TestCase):
    def test_acquire_release_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_evaluation_lease(
                    state,
                    run_id="replay-a",
                    invocation_id="inv-1",
                    ttl_seconds=120,
                )
            )
            self.assertTrue(evaluation_lease_active(state))
            lease = read_evaluation_lease(state)
            assert lease is not None
            self.assertEqual(lease["run_id"], "replay-a")
            release_evaluation_lease(state, run_id="replay-a")
            self.assertFalse(evaluation_lease_active(state))

    def test_foreign_lease_blocks_acquire(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_evaluation_lease(state, run_id="replay-a", invocation_id="inv-1")
            )
            self.assertFalse(
                acquire_evaluation_lease(state, run_id="replay-b", invocation_id="inv-2")
            )
            release_evaluation_lease(state, run_id="replay-a")

    def test_same_run_id_renews(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            acquire_evaluation_lease(state, run_id="replay-a", invocation_id="inv-1", ttl_seconds=60)
            first = read_evaluation_lease(state)
            assert first is not None
            self.assertTrue(
                renew_evaluation_lease(state, run_id="replay-a", invocation_id="inv-2", ttl_seconds=120)
            )
            second = read_evaluation_lease(state)
            assert second is not None
            self.assertEqual(second["invocation_id"], "inv-2")
            self.assertNotEqual(second["expires_utc"], first["expires_utc"])
            release_evaluation_lease(state, run_id="replay-a")

    def test_expired_lease_allows_acquire(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            past = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat().replace(
                "+00:00", "Z"
            )
            path = evaluation_lease_path(state)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "glitch.topstep.evaluation_lease.v1",
                        "run_id": "stale",
                        "invocation_id": "old",
                        "pid": 1,
                        "process_start_utc": past,
                        "acquired_utc": past,
                        "expires_utc": past,
                        "renewed_utc": past,
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(evaluation_lease_active(state))
            self.assertTrue(
                acquire_evaluation_lease(state, run_id="replay-b", invocation_id="inv-new")
            )

    def test_defer_production_worker_when_lease_active(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            status_path = state / "supervisor" / "worker-status.json"
            acquire_evaluation_lease(state, run_id="replay-a", invocation_id="inv-1")
            deferred = defer_production_worker_if_evaluation_lease(
                state,
                worker_kind="direct_cycle",
                run_id="cron-1",
                status_path=status_path,
                status_schema="glitch.topstep.direct_worker_status.v2",
            )
            self.assertTrue(deferred)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "deferred")
            self.assertEqual(payload["phase"], "evaluation_lease_active")
            release_evaluation_lease(state, run_id="replay-a")

    def test_context_manager_releases_on_exit(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with ProductionEvaluationLease(
                production_state=state,
                run_id="replay-a",
                invocation_id="inv-1",
            ) as lease:
                self.assertTrue(lease.acquired)
                self.assertTrue(evaluation_lease_active(state))
            self.assertFalse(evaluation_lease_active(state))

    def test_cron_defers_while_evaluation_holds_lease(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            status_path = state / "supervisor" / "direct-worker-status.json"
            with ProductionEvaluationLease(
                production_state=state,
                run_id="replay-critical",
                invocation_id="session",
            ) as lease:
                self.assertTrue(lease.acquired)
                self.assertTrue(
                    defer_production_worker_if_evaluation_lease(
                        state,
                        worker_kind="direct_cycle",
                        run_id="cron-attempt",
                        status_path=status_path,
                        status_schema="glitch.topstep.direct_worker_status.v2",
                    )
                )
            self.assertFalse(evaluation_lease_active(state))
            self.assertFalse(
                defer_production_worker_if_evaluation_lease(
                    state,
                    worker_kind="direct_cycle",
                    run_id="cron-after",
                    status_path=status_path,
                    status_schema="glitch.topstep.direct_worker_status.v2",
                )
            )
            self.assertTrue(
                acquire_model_owner(state, owner_kind="direct_cycle", invocation_id="cron-after")
            )
            release_model_owner(state, owner_kind="direct_cycle", invocation_id="cron-after")

    def test_concurrent_renew_while_holder_alive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            acquire_evaluation_lease(state, run_id="replay-a", invocation_id="inv-1", ttl_seconds=90)

            def renew_loop() -> None:
                for idx in range(5):
                    renew_evaluation_lease(
                        state,
                        run_id="replay-a",
                        invocation_id=f"inv-{idx}",
                        ttl_seconds=90,
                    )
                    time.sleep(0.01)

            thread = threading.Thread(target=renew_loop)
            thread.start()
            thread.join()
            self.assertTrue(evaluation_lease_active(state))
            release_evaluation_lease(state, run_id="replay-a")


if __name__ == "__main__":
    unittest.main()
