from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prac_live_ensemble as runner


def packet() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "schema_version": "glitch.direct.decision_packet.v2",
        "packet_id": "pkt-live-test",
        "created_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_utc": (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "instrument": "MNQ",
        "account": {"name": "PRAC"},
        "account_selection": {"selected_contract_id": "CON.F.US.MNQ.U26"},
        "contract": {"id": "CON.F.US.MNQ.U26", "tick_size": 0.25, "tick_value": 0.5},
        "market": {"snapshot_hash": "a" * 64, "last": 20000.0, "bid": 19999.75, "ask": 20000.25},
        "market_observation": {"timeframes": {"1m": {"close": 20000.0}}},
        "data_quality": {"state_complete": True, "bar_1m_closed": True, "issues": []},
        "bar_close_utc": now.isoformat().replace("+00:00", "Z"),
        "decision_scope": {"scope_hash": "scope", "generation": 1},
        "policy": {},
    }


def health() -> dict:
    return {"status": "ok", "lifecycle": {"state": "ready"}}


def config(mode: str = "offline") -> runner.RunnerConfig:
    return runner.RunnerConfig.load(ROOT / "evaluation" / "prac-live-ensemble-config.v1.json", mode=mode, authorize=mode == "prac_live")


class PracLiveEnsembleTests(unittest.TestCase):
    def test_packet_gates(self):
        cases = [
            (lambda p: p.pop("market_observation"), "packet_incomplete"),
            (lambda p: p["data_quality"]["issues"].append("quote_missing"), "quote_missing"),
            (lambda p: p.__setitem__("expires_utc", "2000-01-01T00:00:00Z"), "snapshot_expired"),
            (lambda p: p["account_selection"].__setitem__("selected_contract_id", "OTHER"), "contract_divergent"),
        ]
        for mutate, reason in cases:
            value = packet()
            mutate(value)
            with self.assertRaisesRegex(runner.RunnerError, reason):
                runner.validate_live_packet(value, health())

    def test_gateway_observation_proves_closed_bar_without_derived_packet_field(self):
        value = packet()
        fixed_now = datetime(2026, 9, 10, 17, 55, 30, tzinfo=timezone.utc)
        value["created_utc"] = "2026-09-10T17:55:30Z"
        value["expires_utc"] = "2026-09-10T17:56:30Z"
        value["data_quality"].pop("bar_1m_closed")
        value.pop("bar_close_utc")
        value["market_observation"] = {"observation": {
            "timeframes": [{
                "timeframe_minutes": 1,
                "latest_bar_utc": "2026-09-10T17:54:00Z",
                "latest_bar_partial": False,
                "prior_completed_bar": None,
            }],
        }}
        runner.validate_live_packet(value, health(), now=fixed_now)

    def test_six_profiles_share_one_envelope_and_missing_profile_is_blocked(self):
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text())
        registry = json.loads((ROOT / "evaluation/registry.json").read_text())
        envelope = runner.seal_live_envelope(packet(), matrix=matrix, mapping=json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text()), config=config())
        seen = []
        def invoker(profile, received, _timeout):
            seen.append((profile["profile_id"], received["envelope_hash"]))
            return {"state": "no_edge", "direction": "flat", "thesis": "none"}
        slots = runner.run_profiles(envelope=envelope, registry=registry, matrix=matrix, config=config(), invoker=invoker)
        self.assertEqual({row[0] for row in seen}, set(runner.PROFILE_IDS))
        self.assertEqual({row[1] for row in seen}, {envelope["envelope_hash"]})
        broken = copy.deepcopy(registry)
        broken["profiles"] = [p for p in broken["profiles"] if p["profile_id"] != "orderflow"]
        with self.assertRaisesRegex(runner.RunnerError, "profile_missing"):
            runner.run_profiles(envelope=envelope, registry=broken, matrix=matrix, config=config(), invoker=invoker)

    def test_timeout_and_single_global_decision(self):
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text())
        registry = json.loads((ROOT / "evaluation/registry.json").read_text())
        rules = json.loads((ROOT / "evaluation/aggregator_rules.v1.json").read_text())
        envelope = runner.seal_live_envelope(packet(), matrix=matrix, mapping=json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text()), config=config())
        def invoker(profile, _envelope, _timeout):
            if profile["profile_id"] == "orderflow":
                raise TimeoutError("profile timeout")
            return {"state": "no_edge", "direction": "flat", "thesis": "none"}
        slots = runner.run_profiles(envelope=envelope, registry=registry, matrix=matrix, config=config(), invoker=invoker)
        decision = runner.aggregate_global(envelope=envelope, slots=slots, rules=rules, run_id="run")
        self.assertEqual(len(decision["decision_id"]), 36)
        self.assertEqual(decision["delivery_count"], 0)
        self.assertEqual(sum(1 for row in slots if row["profile_id"] == "orderflow" and row["normalized"]["state"] == "error"), 1)

    def test_no_candidate_and_direction_conflict_are_one_abstaining_decision(self):
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text())
        registry = json.loads((ROOT / "evaluation/registry.json").read_text())
        rules = json.loads((ROOT / "evaluation/aggregator_rules.v1.json").read_text())
        envelope = runner.seal_live_envelope(packet(), matrix=matrix, mapping=json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text()), config=config())
        def no_edge(_profile, _envelope, _timeout):
            return {"state": "no_edge", "direction": "flat", "thesis": "none"}
        abstain = runner.aggregate_global(envelope=envelope, slots=runner.run_profiles(envelope=envelope, registry=registry, matrix=matrix, config=config(), invoker=no_edge), rules=rules, run_id="abstain")
        self.assertEqual(abstain["outcome"], "no_selection")
        candidates = []
        for index, profile_id in enumerate(runner.PROFILE_IDS):
            long_side = index < 3
            candidates.append({"profile_id": profile_id, "state": "candidate", "comparability": "comparable", "instrument": "MNQ", "direction": "long" if long_side else "short", "entry": 20000, "stop": 19990 if long_side else 20010, "target": 20010 if long_side else 19990, "horizon_bars": 5, "envelope_hash": envelope["envelope_hash"], "completeness_used": {}, "evidence_refs": []})
        conflicted = runner.aggregate_envelope(run_id="conflict", envelope=envelope, candidates=candidates, rules=rules, required_profile_ids=list(runner.PROFILE_IDS))
        self.assertEqual(conflicted["decision_code"], "DIRECTION_CONFLICT")

    def test_no_candidate_conflict_second_exposure_and_mode_fail_closed(self):
        with self.assertRaisesRegex(runner.RunnerError, "prac_live_requires_authorize"):
            runner.RunnerConfig.load(ROOT / "evaluation/prac-live-ensemble-config.v1.json", mode="prac_live", authorize=False)
        self.assertFalse(runner.reset_allowed(flattened=True, reconciled=False, pending_orders=False, receipts_persisted=True, outcomes_persisted=True))
        self.assertTrue(runner.reset_allowed(flattened=True, reconciled=True, pending_orders=False, receipts_persisted=True, outcomes_persisted=True))
        self.assertEqual(runner.deliver_global_decision(decision={}, packet=packet(), config=config()), {"status": "not_delivered", "reason": "delivery_disabled_by_mode", "orders_sent": 0})
        live = config("prac_live")
        with self.assertRaisesRegex(runner.RunnerError, "second_exposure_blocked"):
            runner.deliver_global_decision(decision={"outcome": "selected"}, packet=packet(), config=live, active_exposure=1)

    def test_delivery_requires_stop_and_rejects_ambiguous_receipt(self):
        live = config("prac_live")
        decision = {"selected_candidate_full": {"direction": "long", "entry": 20000, "target": 20010, "quantity": 1}}
        with self.assertRaisesRegex(runner.RunnerError, "decision_missing_execution_fields"):
            runner.deliver_global_decision(decision=decision, packet=packet(), config=live)
        candidate = {"direction": "long", "entry": 20000, "stop": 19990, "target": 20010, "quantity": 1}
        with mock.patch.dict("os.environ", {"GLITCH_TOPSTEP_LOCAL_TOKEN": "test-token"}):
            with self.assertRaisesRegex(runner.RunnerError, "receipt_ambiguous"):
                runner.deliver_global_decision(decision={"selected_candidate_full": candidate}, packet=packet(), config=live, client=lambda *a, **k: (202, {"status": "ambiguous"}))

    def test_no_projectx_credentials_and_sanitized_error(self):
        source = (ROOT / "scripts/prac_live_ensemble.py").read_text()
        self.assertNotIn("PROJECTX_API_KEY", source)
        self.assertNotIn("PROJECTX_USERNAME", source)
        self.assertNotIn("PROJECTX_PASSWORD", source)
        self.assertNotIn("secret-value", runner.sanitize_text("Bearer secret-value"))

    def test_hermes_utf8_stdout_and_separate_stderr(self):
        completed = runner.subprocess.CompletedProcess(
            args=["hermes"],
            returncode=0,
            stdout=b'{"state":"no_edge","thesis":"caf\xc3\xa9 \xf0\x9f\x9a\x80"}',
            stderr="diagnostic stderr\n".encode("utf-8"),
        )
        with mock.patch.object(runner.shutil, "which", return_value="hermes"), mock.patch.object(
            runner.subprocess, "run", return_value=completed
        ) as run:
            result = runner._invoke_hermes(
                {"profile_id": "baseline-current", "skills": []},
                {"envelope_id": "env"},
                1000,
            )
        self.assertEqual(result["thesis"], "café 🚀")
        kwargs = run.call_args.kwargs
        self.assertFalse(kwargs["text"])
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")

    def test_hermes_off_path_absolute_runtime_is_resolved(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "hermes.exe"
            executable.write_bytes(b"official-runtime")
            with mock.patch.dict("os.environ", {"HERMES_EXECUTABLE": str(executable)}, clear=False), mock.patch.object(
                runner.shutil, "which", return_value=None
            ):
                self.assertEqual(runner.resolve_hermes_executable(), str(executable.resolve()))

    def test_hermes_invalid_bytes_or_json_are_safety_stop(self):
        cases = [
            (b'{"state":"no_edge"}\x90', b"", "hermes_utf8_decode_failed"),
            (b'{"state":"no_edge"}', b"diagnostic\x90", "hermes_utf8_decode_failed"),
            (b'{"state":', b"", "hermes_json_invalid"),
        ]
        for stdout, stderr, reason in cases:
            completed = runner.subprocess.CompletedProcess(
                args=["hermes"], returncode=0, stdout=stdout, stderr=stderr
            )
            with self.subTest(reason=reason), mock.patch.object(runner.shutil, "which", return_value="hermes"), mock.patch.object(
                runner.subprocess, "run", return_value=completed
            ):
                with self.assertRaisesRegex(runner.SafetyStopError, reason):
                    runner._invoke_hermes({"profile_id": "baseline-current", "skills": []}, {"envelope_id": "env"}, 1000)

    def test_safety_stop_does_not_write_partial_run_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "run.json"
            with mock.patch.object(runner, "fetch_live_packet", return_value=(health(), packet())), mock.patch.object(
                runner, "run_profiles", side_effect=runner.SafetyStopError("safety_stop:hermes_json_invalid")
            ):
                with self.assertRaisesRegex(runner.SafetyStopError, "safety_stop:hermes_json_invalid"):
                    runner.main(["--mode", "shadow", "--output", str(output)])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
