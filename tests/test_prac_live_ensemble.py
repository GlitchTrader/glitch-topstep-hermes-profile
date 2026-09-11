from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import subprocess
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
    @staticmethod
    def selected_candidate() -> dict:
        return {
            "direction": "long",
            "entry": 20000,
            "stop": 19990,
            "target": 20010,
            "quantity": 1,
            "confidence": 0.5,
            "thesis": "Bounded evidence supports a long test.",
            "decision_audit": {
                "bull_case": "Support held.",
                "bear_case": "Failure below support invalidates.",
                "flat_case": "No edge if range remains unresolved.",
                "aggressive_case": "Accept only the bounded entry.",
                "conservative_case": "Wait for gateway validation.",
                "decisive_evidence": "Observed support and valid quote.",
                "disconfirming_evidence": "A stale packet or broken support.",
                "change_condition": "Reassess on scope or quote change.",
                "final_choice": "ENTER_LONG",
            },
        }

    def selected_decision(self, candidate: dict | None = None) -> dict:
        return {
            "outcome": "selected",
            "decision_id": "11111111-1111-4111-8111-111111111111",
            "selected_prompt_version": runner.PROMPT_VERSION,
            "selected_model_version": "gpt-5.6-luna",
            "selected_candidate_full": candidate or self.selected_candidate(),
        }

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
            candidates.append({"profile_id": profile_id, "state": "candidate", "comparability": "comparable", "instrument": "MNQ", "direction": "long" if long_side else "short", "entry": 20000, "stop": 19990 if long_side else 20010, "target": 20010 if long_side else 19990, "quantity": 1, "horizon_bars": 5, "envelope_hash": envelope["envelope_hash"], "completeness_used": {}, "evidence_refs": []})
        conflicted = runner.aggregate_envelope(run_id="conflict", envelope=envelope, candidates=candidates, rules=rules, required_profile_ids=list(runner.PROFILE_IDS))
        self.assertEqual(conflicted["decision_code"], "DIRECTION_CONFLICT")

    def test_reason_normalization_preserves_global_nothing_and_no_delivery(self):
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text())
        registry = json.loads((ROOT / "evaluation/registry.json").read_text())
        rules = json.loads((ROOT / "evaluation/aggregator_rules.v1.json").read_text())
        envelope = runner.seal_live_envelope(
            packet(),
            matrix=matrix,
            mapping=json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text()),
            config=config(),
        )

        def reason_only(_profile, _envelope, _timeout):
            return {"state": "no_edge", "direction": "flat", "reason": "No executable edge."}

        reason_slots = runner.run_profiles(
            envelope=envelope,
            registry=registry,
            matrix=matrix,
            config=config(),
            invoker=reason_only,
        )
        self.assertEqual({row["normalized"]["thesis_source"] for row in reason_slots}, {"reason"})
        reason_decision = runner.aggregate_global(
            envelope=envelope,
            slots=reason_slots,
            rules=rules,
            run_id="reason-run",
        )

        def thesis_only(_profile, _envelope, _timeout):
            return {"state": "no_edge", "direction": "flat", "thesis": "No executable edge."}

        thesis_slots = runner.run_profiles(
            envelope=envelope,
            registry=registry,
            matrix=matrix,
            config=config(),
            invoker=thesis_only,
        )
        thesis_decision = runner.aggregate_global(
            envelope=envelope,
            slots=thesis_slots,
            rules=rules,
            run_id="thesis-run",
        )
        self.assertEqual(reason_decision["outcome"], "no_selection")
        self.assertEqual(reason_decision["decision_code"], thesis_decision["decision_code"])
        self.assertEqual(runner.deliver_global_decision(decision=reason_decision, packet=packet(), config=config())["orders_sent"], 0)

    def test_no_candidate_conflict_second_exposure_and_mode_fail_closed(self):
        with self.assertRaisesRegex(runner.RunnerError, "prac_live_requires_authorize"):
            runner.RunnerConfig.load(ROOT / "evaluation/prac-live-ensemble-config.v1.json", mode="prac_live", authorize=False)
        self.assertFalse(runner.reset_allowed(flattened=True, reconciled=False, pending_orders=False, receipts_persisted=True, outcomes_persisted=True))
        self.assertTrue(runner.reset_allowed(flattened=True, reconciled=True, pending_orders=False, receipts_persisted=True, outcomes_persisted=True))
        self.assertEqual(runner.deliver_global_decision(decision={}, packet=packet(), config=config()), {"status": "not_delivered", "reason": "delivery_disabled_by_mode", "orders_sent": 0})
        live = config("prac_live")
        nothing = runner.deliver_global_decision(
            decision={"outcome": "no_selection", "decision_code": "ENSEMBLE_UNANIMOUS_ABSTENTION"},
            packet=packet(),
            config=live,
        )
        self.assertEqual(nothing["reason"], "global_nothing")
        self.assertEqual(nothing["orders_sent"], 0)
        with self.assertRaisesRegex(runner.RunnerError, "second_exposure_blocked"):
            runner.deliver_global_decision(decision={"outcome": "selected"}, packet=packet(), config=live, active_exposure=1)

    def _global_slots(self, adversarial_raw: dict | None) -> list[dict]:
        envelope_hash = "a" * 64
        def candidate(profile_id: str) -> dict:
            return {
                "profile_id": profile_id, "state": "candidate", "comparability": "comparable", "instrument": "MNQ",
                "direction": "long", "entry": 20000, "stop": 19990, "target": 20010, "quantity": 1,
                "envelope_hash": envelope_hash, "completeness_used": {}, "evidence_refs": [],
            }
        slots = [
            {"profile_id": "baseline-current", "normalized": candidate("baseline-current"), "raw_profile_output": {"state": "candidate"}},
            {"profile_id": "structure", "normalized": candidate("structure"), "raw_profile_output": {"state": "candidate"}},
        ]
        for profile_id in ("smart-money", "indicators", "orderflow"):
            slots.append({"profile_id": profile_id, "normalized": {"profile_id": profile_id, "state": "missing_required_evidence", "comparability": "not_comparable", "instrument": "MNQ", "envelope_hash": envelope_hash}, "raw_profile_output": {"state": "missing_required_evidence"}})
        slots.append({"profile_id": "adversarial-risk", "normalized": {"profile_id": "adversarial-risk", "state": "missing_required_evidence", "comparability": "not_comparable", "instrument": "MNQ", "envelope_hash": envelope_hash}, "raw_profile_output": adversarial_raw or {"state": "missing_required_evidence"}})
        return slots

    def test_adversarial_objection_is_transported_and_vetoes_before_selection(self):
        rules = json.loads((ROOT / "evaluation" / "aggregator_rules.v1.json").read_text())
        objection = {
            "target_profile_id": "baseline-current",
            "risk_code": "invalid_stop_geometry",
            "severity": "critical",
            "objective_rule_match": True,
            "reason": "Stop is outside the permitted geometry.",
            "evidence_refs": ["quote:1"],
        }
        decision = runner.aggregate_global(envelope={"envelope_id": "env", "instrument": "MNQ", "snapshot_hash": "a" * 64, "envelope_hash": "a" * 64, "contract": {"tick_size": 0.25}, "packet": {"market": {"last": 20000}}}, slots=self._global_slots({"state": "no_edge", "objections": [objection]}), rules=rules, run_id="veto")
        self.assertEqual(decision["adversarial_objection_status"], "present")
        self.assertEqual(decision["objections"][0]["source_profile_id"], "adversarial-risk")
        self.assertEqual(decision["objections"][0]["reason"], objection["reason"])
        self.assertEqual(decision["outcome"], "no_selection")

    def test_adversarial_objection_absent_is_distinct_and_malformed_transport_blocks(self):
        rules = json.loads((ROOT / "evaluation" / "aggregator_rules.v1.json").read_text())
        envelope = {"envelope_id": "env", "instrument": "MNQ", "snapshot_hash": "a" * 64, "envelope_hash": "a" * 64, "contract": {"tick_size": 0.25}, "packet": {"market": {"last": 20000}}}
        absent = runner.aggregate_global(envelope=envelope, slots=self._global_slots(None), rules=rules, run_id="absent")
        self.assertEqual(absent["adversarial_objection_status"], "absent")
        with self.assertRaisesRegex(runner.RunnerError, "adversarial_objection_transport_failed"):
            runner.aggregate_global(envelope=envelope, slots=self._global_slots({"state": "no_edge", "objections": {}}), rules=rules, run_id="malformed")
        broken = self._global_slots(None)
        broken[-1]["raw_profile_output"] = None
        with self.assertRaisesRegex(runner.RunnerError, "adversarial_objection_transport_failed"):
            runner.aggregate_global(envelope=envelope, slots=broken, rules=rules, run_id="transport")

    def test_delivery_requires_stop_and_rejects_ambiguous_receipt(self):
        live = config("prac_live")
        decision = {"selected_candidate_full": {"direction": "long", "entry": 20000, "target": 20010, "quantity": 1}}
        with self.assertRaisesRegex(runner.RunnerError, "decision_missing_execution_fields"):
            runner.deliver_global_decision(decision=decision, packet=packet(), config=live)
        candidate = self.selected_candidate()
        with mock.patch.dict("os.environ", {"GLITCH_TOPSTEP_LOCAL_TOKEN": "test-token"}):
            with self.assertRaisesRegex(runner.RunnerError, "receipt_ambiguous"):
                runner.deliver_global_decision(decision=self.selected_decision(candidate), packet=packet(), config=live, client=lambda *a, **k: (202, {"status": "ambiguous"}))

    def test_selected_intent_contains_gateway_required_provenance_and_audit(self):
        intent = runner.decision_to_gateway_intent(self.selected_decision(), packet())
        self.assertRegex(intent["intent_id"], r"^[0-9a-f-]{36}$")
        self.assertTrue(intent["created_utc"].endswith("Z"))
        self.assertEqual(intent["operator_profile"], "glitch-topstep")
        self.assertEqual(intent["model_version"], "gpt-5.6-luna")
        self.assertEqual(intent["prompt_version"], runner.PROMPT_VERSION)
        self.assertEqual(intent["scope_hash"], "scope")
        self.assertEqual(intent["scope_generation"], 1)
        self.assertEqual(intent["action"], "ENTER_LONG")
        self.assertEqual(intent["stop_loss"], 19990)
        self.assertEqual(intent["take_profit_1"], 20010)

    def test_each_missing_intent_provenance_field_fails_closed(self):
        for field in ("decision_id", "selected_prompt_version", "selected_model_version"):
            decision = self.selected_decision()
            decision.pop(field)
            context = mock.patch.object(runner, "_operator_identity", return_value=("glitch-topstep", "")) if field == "selected_model_version" else mock.patch.object(runner, "_operator_identity", wraps=runner._operator_identity)
            with self.subTest(field=field), context, self.assertRaisesRegex(runner.RunnerError, "intent_provenance_missing|prompt_version_mismatch"):
                runner.decision_to_gateway_intent(decision, packet())
        for field in ("packet_id", "scope_hash", "scope_generation"):
            value = packet()
            if field == "packet_id":
                value.pop(field)
            elif field == "scope_hash":
                value["decision_scope"].pop(field)
            else:
                value["decision_scope"].pop("generation")
            with self.subTest(field=field), self.assertRaisesRegex(runner.RunnerError, "intent_provenance_missing"):
                runner.decision_to_gateway_intent(self.selected_decision(), value)

    def test_no_selection_never_creates_intent(self):
        result = runner.deliver_global_decision(
            decision={"outcome": "no_selection", "decision_code": "NO_EDGE"},
            packet=packet(),
            config=config("prac_live"),
        )
        self.assertEqual(result["reason"], "global_nothing")
        self.assertEqual(result["orders_sent"], 0)

    def test_selected_intent_is_accepted_by_real_gateway_validator(self):
        candidates = [
            ROOT.parents[1] / ".prac-operational-20260910" / "gateway",
            ROOT.parent / "glitch-topstep",
        ]
        gateway = next((path for path in candidates if path.is_dir()), candidates[-1])
        intent = runner.decision_to_gateway_intent(self.selected_decision(), packet())
        script = """
import { parseTradeIntent } from './dist/src/domain/intents.js';
let raw = '';
for await (const chunk of process.stdin) raw += chunk;
try { parseTradeIntent(JSON.parse(raw)); process.stdout.write('accepted'); }
catch (error) { process.stdout.write(error?.errorCode || error?.message || 'rejected'); process.exitCode = 1; }
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=gateway,
            input=json.dumps(intent),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout, "accepted")

    def test_specialty_skills_are_distinct_and_fail_closed_without_data(self):
        registry = json.loads((ROOT / "evaluation/registry.json").read_text())
        rows = {row["profile_id"]: row for row in registry["profiles"]}
        self.assertIn("topstep-smart-money", rows["smart-money"]["skills"])
        self.assertIn("topstep-indicators", rows["indicators"]["skills"])
        self.assertNotEqual(rows["smart-money"]["skills"], rows["indicators"]["skills"])
        matrix = json.loads((ROOT / "evaluation/capability-matrix.json").read_text())
        self.assertIn("topstep-smart-money", matrix["profiles"]["smart-money"]["skills"])
        self.assertIn("topstep-indicators", matrix["profiles"]["indicators"]["skills"])
        self.assertEqual(runner._normalize_result(None, profile=rows["smart-money"], envelope=runner.seal_live_envelope(packet(), matrix=matrix, mapping=json.loads((ROOT / "evaluation/packet_envelope_mapping.v1.json").read_text()), config=config()), run_id="r", gate={"completeness_used": {}, "missing_required": ["structure"], "stale_or_inconsistent": [], "comparable": False}, started="2026-09-10T00:00:00Z", finished="2026-09-10T00:00:01Z", latency_ms=1)["state"], "missing_required_evidence")

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
        self.assertIn("-Q", run.call_args.args[0])
        prompt = json.loads(run.call_args.args[0][-1])
        self.assertTrue(prompt["output_contract"]["single_json_object"])
        self.assertIn("exactly one", prompt["instruction"])
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
            (b'Introductory text\n{"event":"progress"}\n{"state":"no_edge"}', b"", "hermes_json_invalid"),
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
