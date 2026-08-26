"""Decision regret classification and batch processing."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from decision_regret import (  # noqa: E402
    classify_enter_regret,
    classify_nothing_regret,
    classify_now_vs_wait_regret,
    observed_path_from_frames,
    process_pending_regret_evaluations,
    summarize_regret,
)
from common import write_json_atomic  # noqa: E402


class DecisionRegretTests(unittest.TestCase):
    def test_nothing_missed_edge(self):
        decision = {
            "action": "NOTHING",
            "packet_id": "pkt-1",
            "intent": {
                "action": "NOTHING",
                "decision_audit": {
                    "decisive_evidence": (
                        "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                        "risk_points=10;reward_points=30;friction_points=1;"
                        "breakeven_target_first=0.275;estimated_target_first_range=0.20-0.25;"
                        "now_ev=NEGATIVE;wait_price=19995;wait_ev=no;decisive_reason=no"
                    )
                },
            },
        }
        record = classify_nothing_regret(decision, observed_high=20035, observed_low=19995)
        self.assertIsNotNone(record)
        self.assertEqual(record["classification"], "missed_directional_participation")
        self.assertEqual(record["alias"], "missed_edge")

    def test_nothing_justified_abstention(self):
        decision = {
            "packet_id": "pkt-2",
            "intent": {
                "action": "NOTHING",
                "decision_audit": {
                    "decisive_evidence": (
                        "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                        "risk_points=10;reward_points=30;friction_points=1;"
                        "breakeven_target_first=0.275;estimated_target_first_range=0.20-0.25;"
                        "now_ev=NEGATIVE;wait_price=19995;wait_ev=no;decisive_reason=no"
                    )
                },
            },
        }
        record = classify_nothing_regret(decision, observed_high=20005, observed_low=19985)
        self.assertEqual(record["classification"], "justified_abstention")
        self.assertEqual(record["alias"], "good_abstention")

    def test_enter_bad_participation_on_path(self):
        decision = {
            "intent": {
                "action": "ENTER_LONG",
                "intent_id": "intent-1",
                "entry_price_min": 20000,
                "entry_price_max": 20002,
                "stop_loss": 19990,
                "take_profit_1": 20030,
            }
        }
        record = classify_enter_regret(decision, 20001, observed_high=20005, observed_low=19985)
        self.assertEqual(record["classification"], "bad_participation")

    def test_now_vs_wait_wait_better(self):
        decision = {
            "packet_id": "pkt-3",
            "intent": {
                "action": "ENTER_LONG",
                "entry_price_min": 20000,
                "entry_price_max": 20002,
                "decision_audit": {
                    "decisive_evidence": (
                        "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                        "risk_points=10;reward_points=30;friction_points=1;"
                        "breakeven_target_first=0.275;estimated_target_first_range=0.35-0.45;"
                        "now_ev=POSITIVE_ROBUST;wait_price=19990;wait_ev=better;decisive_reason=edge"
                    )
                },
            },
        }
        record = classify_now_vs_wait_regret(decision, 20010, 19988, fill_price=20001)
        self.assertEqual(record["classification"], "wait_better")

    def test_process_pending_writes_regret_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "minute-frames").mkdir()
            recorded = datetime.now(timezone.utc).replace(microsecond=0)
            recorded = recorded - __import__("datetime").timedelta(minutes=15)
            recorded_utc = recorded.isoformat().replace("+00:00", "Z")
            write_json_atomic(
                state / "minute-frames" / "20260826T2100Z.json",
                {
                    "captured_utc": recorded_utc,
                    "packet": {
                        "market": {"last": 20005, "bid": 20004, "ask": 20006},
                        "market_observation": {
                            "prior_completed_bar_1m": {"high": 20008, "low": 19998}
                        },
                    },
                },
            )
            decision = {
                "schema_version": "glitch.topstep.decision_record.v2",
                "recorded_utc": recorded_utc,
                "packet_id": "pkt-batch",
                "intent": {
                    "action": "NOTHING",
                    "decision_audit": {
                        "decisive_evidence": (
                            "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                            "risk_points=10;reward_points=30;friction_points=1;"
                            "breakeven_target_first=0.275;estimated_target_first_range=0.20-0.25;"
                            "now_ev=NEGATIVE;wait_price=19995;wait_ev=no;decisive_reason=no"
                        )
                    },
                },
            }
            with (state / "decisions.jsonl").open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(decision) + "\n")
            batch = process_pending_regret_evaluations(state, horizon_minutes=10)
            self.assertEqual(batch["evaluated_decisions"], 1)
            self.assertGreaterEqual(batch["records_written"], 1)
            summary = summarize_regret(state / "decision-regret.jsonl")
            self.assertGreater(summary["total"], 0)

    def test_observed_path_from_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "minute-frames").mkdir()
            write_json_atomic(
                state / "minute-frames" / "20260826T2100Z.json",
                {
                    "captured_utc": "2026-08-26T21:00:00Z",
                    "packet": {"market": {"last": 100, "bid": 99, "ask": 101}},
                },
            )
            high, low = observed_path_from_frames(state, "2026-08-26T21:00:00Z", horizon_minutes=5)
            self.assertEqual(high, 101)
            self.assertEqual(low, 99)


if __name__ == "__main__":
    unittest.main()
