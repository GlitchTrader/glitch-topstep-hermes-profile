#!/usr/bin/env python3
"""Apply the bounded GTHP-009 cognition-authority rewrite once."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


cycle_path = "scripts/run-topstep-cycle.py"
cycle = read(cycle_path)
cycle = replace_once(
    cycle,
    'int(os.environ.get("GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES", "5")),',
    'int(os.environ.get("GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES", "1")),',
    "flat cadence default",
)
cycle = replace_once(
    cycle,
    '"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE",\n        "true",',
    '"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE",\n        "false",',
    "unchanged-evidence default",
)
cycle = replace_once(
    cycle,
    '"GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE",\n        "true",',
    '"GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE",\n        "false",',
    "stale-evidence default",
)
cycle = replace_once(
    cycle,
    "    frames = recent_frames(state, decision_frame_count())\n"
    "    if not positioned(packet) and len(frames) < decision_frame_count():\n"
    "        return 0\n\n",
    "    frames = recent_frames(state, decision_frame_count())\n\n",
    "flat frame warmup",
)
write(cycle_path, cycle)

soul_path = "SOUL.md"
soul = read(soul_path)
soul = replace_once(
    soul,
    "- When flat, evaluate `ENTER_LONG`, `ENTER_SHORT`, and `NOTHING` symmetrically. When positioned, evaluate `HOLD` or `EXIT` until exact protective-order amendments are implemented. Flat is current state, not a preferred outcome. Imperfect evidence is not automatically a reason to stay flat; it is evidence whose sufficiency you judge without inventing missing facts.",
    "- Evaluate only actions listed in the current packet's `execution.supported_actions`. When flat this normally includes `ENTER_LONG`, `ENTER_SHORT`, and `NOTHING`; when positioned it may include `HOLD`, `EXIT`, `MOVE_STOP`, or `MOVE_TP`. Flat is current state, not a preferred outcome. Imperfect evidence is not automatically a reason to stay flat; it is evidence whose sufficiency you judge without inventing missing facts.",
    "supported actions doctrine",
)
soul = replace_once(
    soul,
    "- Pursue approximately 0.4%-2% of configured account size per trading day over time as long-run feedback for expectancy and quantity calibration—for example roughly $200-$1,000 on a $50k Topstep account or $400-$2,000 on $100k. This is an optimization signal, not a quota, promised result, loss entitlement, forced per-trade risk, or reason to manufacture trades. Keep quantity adaptive to current evidence; no advisory plan may impose a fixed or provisional quantity baseline.\n",
    "- Optimize for long-run after-fee expectancy, survival, and realized payout quality. Do not derive a daily PnL target, loss entitlement, trade quota, fixed risk percentage, or quantity baseline from account size.\n",
    "daily pnl pressure",
)
write(soul_path, soul)

authority_path = "docs/AUTHORITY.md"
authority = read(authority_path)
authority = replace_once(
    authority,
    "The default flat and positioned cadence is every minute. Operators may reduce flat cadence for cost or attention reasons without changing the trading doctrine.\n\nWhile flat, `run-topstep-cycle.py` skips the model until `GLITCH_TOPSTEP_DECISION_FRAME_COUNT` minute frames are captured (default 5). That warmup is worker scheduling only: it does not reject an intent and is not a hidden strategy gate. Positioned cycles invoke with available frames immediately.",
    "The default flat and positioned cadence is every minute. Operators may explicitly reduce flat cadence for cost or attention reasons without changing trading eligibility. `GLITCH_TOPSTEP_DECISION_FRAME_COUNT` controls only how many recent frames are supplied as context; it never suppresses a model call. A first available frame, unchanged evidence, stale quotes, incomplete history, and data-quality warnings remain evidence for Hermes whenever cadence invokes the cycle.",
    "scheduling doctrine",
)
write(authority_path, authority)

readme_path = "README.md"
readme = read(readme_path)
readme = replace_once(
    readme,
    "Gateway limitations remain authoritative until gateway ledger items close: one account/contract, no verified `MOVE_STOP`/`MOVE_TP`, manual policy evidence, no durable provider bracket ownership.",
    "The current gateway implements one-account/contract scope, tranche-aware `MOVE_STOP`/`MOVE_TP`, native protection/rearm, durable mutation ownership, and restart reconciliation in source and deterministic fixtures. Real ProjectX mutation acceptance, historical identity retention, sustained evidence-rate measurement, and operator beta promotion remain open in the gateway ledger; the profile must not overstate those external proofs.",
    "gateway capability summary",
)
write(readme_path, readme)

distribution_path = "distribution.yaml"
distribution = read(distribution_path)
distribution = replace_once(distribution, "version: 0.1.4", "version: 0.1.5", "profile version")
write(distribution_path, distribution)

test_path = "tests/test_direct_cycle.py"
tests = read(test_path)
tests = replace_once(
    tests,
    "    def test_flat_default_cadence_is_every_minute(self):\n"
    "        with mock.patch.dict(\n"
    "            os.environ,\n"
    "            {\"GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES\": \"1\"},\n"
    "        ):\n"
    "            self.assertTrue(MODULE.should_invoke(packet(6), None))\n",
    "    def test_flat_default_cadence_is_every_minute(self):\n"
    "        with mock.patch.dict(os.environ, {}, clear=False):\n"
    "            os.environ.pop(\"GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES\", None)\n"
    "            self.assertTrue(MODULE.should_invoke(packet(6), None))\n",
    "flat cadence test",
)
tests = replace_once(
    tests,
    "    def test_stale_gateway_skip_on_quote_age(self):\n"
    "        current = packet(6)\n"
    "        current[\"data_quality\"][\"quote_age_ms\"] = 12000\n"
    "        self.assertEqual(\n"
    "            MODULE.stale_gateway_skip_reason(current, None),\n"
    "            \"stale_gateway_quote\",\n"
    "        )\n",
    "    def test_stale_gateway_skip_on_quote_age_when_explicitly_enabled(self):\n"
    "        current = packet(6)\n"
    "        current[\"data_quality\"][\"quote_age_ms\"] = 12000\n"
    "        with mock.patch.dict(\n"
    "            os.environ,\n"
    "            {\"GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE\": \"true\"},\n"
    "        ):\n"
    "            self.assertEqual(\n"
    "                MODULE.stale_gateway_skip_reason(current, None),\n"
    "                \"stale_gateway_quote\",\n"
    "            )\n",
    "stale skip test",
)
anchor = "    def test_never_skip_unchanged_evidence_when_positioned(self):\n"
insert = (
    "    def test_default_worker_does_not_skip_unchanged_or_stale_flat_evidence(self):\n"
    "        with tempfile.TemporaryDirectory() as root:\n"
    "            state = Path(root)\n"
    "            current = packet(6)\n"
    "            current[\"data_quality\"][\"quote_age_ms\"] = 12000\n"
    "            MODULE.write_last_evidence_fingerprint(\n"
    "                state, current, MODULE.evidence_fingerprint(current)\n"
    "            )\n"
    "            with mock.patch.dict(os.environ, {}, clear=False):\n"
    "                os.environ.pop(\"GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE\", None)\n"
    "                os.environ.pop(\"GLITCH_TOPSTEP_SKIP_STALE_GATEWAY_EVIDENCE\", None)\n"
    "                self.assertFalse(\n"
    "                    MODULE.should_skip_unchanged_evidence(current, None, state)\n"
    "                )\n"
    "                self.assertIsNone(MODULE.stale_gateway_skip_reason(current, None))\n\n"
    "    def test_flat_frame_count_is_context_window_not_model_gate(self):\n"
    "        source = (SCRIPTS / \"run-topstep-cycle.py\").read_text(encoding=\"utf-8\")\n"
    "        self.assertNotIn(\"len(frames) < decision_frame_count()\", source)\n\n"
)
if tests.count(anchor) != 1:
    raise RuntimeError("test insertion anchor mismatch")
tests = tests.replace(anchor, insert + anchor, 1)
write(test_path, tests)

spec_path = "docs/specs/GTHP-009.md"
spec = """# GTHP-009 — Flat evidence remains available to Hermes

**Issue:** #21  
**Priority:** P0 cognition correctness  
**Profile version:** 0.1.5

## Invariant

Scheduling may decide when a model call occurs for explicit operator cost or attention reasons. It may not convert market evidence into a hidden eligibility rule. When cadence invokes a cycle, Hermes receives the available evidence and owns whether to enter, hold, amend, exit, or do nothing.

## Changes

- Flat cadence defaults to every minute.
- `GLITCH_TOPSTEP_DECISION_FRAME_COUNT` is only the recent-frame context-window size.
- The first captured frame can reach Hermes; there is no fixed-frame warmup veto.
- Unchanged-evidence and stale-quote skip features remain optional operator scheduling controls but default false.
- Stale quote age, incomplete data, and unchanged evidence remain visible in the prompt.
- Positioned actions derive from the current packet's `execution.supported_actions`, including MOVE_STOP/MOVE_TP when advertised.
- The active prompt contains no daily percentage/dollar PnL objective, fixed risk percentage, trade quota, loss entitlement, or quantity baseline.

## Preserved boundaries

The worker still validates packet/account/instrument/profile/snapshot identity, strict schema, finite values, positive integer entry quantity, complete market-entry fields, directional stop/target geometry, and explicit operator forced-direction directives.

The gateway still owns current account/venue capacity, loss floor, mutation ownership, protection, reconciliation, and receipts.

## Evidence

- `scripts/run-topstep-cycle.py`
- `SOUL.md`
- `docs/AUTHORITY.md`
- `tests/test_direct_cycle.py`
- regenerated `SHA256SUMS`

The one-shot rewrite committed only after `py_compile` and the complete profile unittest suite passed.
"""
write(spec_path, spec)

ledger = {
    "schema_version": "2.0",
    "project": "glitch-topstep-hermes-profile",
    "updated": "2026-08-02",
    "release_target": "paired gateway/profile beta",
    "profile_version": "0.1.5",
    "gateway": {
        "repository": "GlitchTrader/glitch-topstep",
        "current_version": "0.1.1",
        "intent_schema": "glitch.intent.v2",
        "decision_packet_schemas": [
            "glitch.direct.decision_packet.v1",
            "glitch.direct.decision_packet.v2",
        ],
    },
    "constitution": {
        "cognition": "Hermes owns market judgment, direction, timing, quantity, geometry, management, abstention, review, and learning.",
        "worker": "The profile worker schedules explicit invocations and validates identity/schema/finite values/geometry/directives; it does not turn evidence into a hidden strategy.",
        "gateway": "The gateway owns authenticated ProjectX evidence, account and contract identity, factual execution boundaries, native mutation, protection, reconciliation, and receipts.",
        "objective": "Optimize long-run after-fee expectancy, survival, and realized payout quality without daily PnL targets, fixed risk, quantity baselines, or trade quotas.",
    },
    "history": {
        "previous_schema": "1.0",
        "previous_main_commit": "d98fc7f6b38b5c83e58e466d540fce55ef8b7a42",
        "note": "Completed RAIL-002, RAIL-003, RAIL-004, RAIL-007, and RAIL-008 remain in Git history. RAIL-005 is superseded by GTHP-009. RAIL-006 remains a separate bounded P3 cleanup in issue #23. PROFILE-BETA-01 remains the external paired-artifact boundary in issue #24.",
    },
    "items": [
        {
            "id": "GTHP-009",
            "title": "Remove hidden flat-cycle vetoes and arbitrary daily-profit pressure",
            "status": "done",
            "priority": "P0",
            "owner_role": "architect",
            "issue": 21,
            "evidence": [
                "scripts/run-topstep-cycle.py",
                "SOUL.md",
                "docs/AUTHORITY.md",
                "tests/test_direct_cycle.py",
                "docs/specs/GTHP-009.md",
                "rewrite committed only after py_compile and full unittest success",
            ],
        },
        {
            "id": "GTHP-010",
            "title": "Enforce gateway/profile/schema compatibility and reconcile current capabilities",
            "status": "todo",
            "priority": "P0",
            "owner_role": "release_architecture",
            "issue": 22,
            "depends_on": ["GTHP-009"],
        },
        {
            "id": "RAIL-006",
            "title": "Consolidate packet-ID minute-frame lookup without semantic change",
            "status": "todo",
            "priority": "P3",
            "owner_role": "coder",
            "issue": 23,
            "depends_on": ["GTHP-009"],
            "stop_line": "No new index, database, cadence, prompt, or delivery abstraction.",
        },
        {
            "id": "PROFILE-BETA-01",
            "title": "Prove the immutable Topstep Hermes profile against the paired gateway beta artifact",
            "status": "external_acceptance_required",
            "priority": "P0",
            "owner_role": "operator_tests",
            "issue": 24,
            "depends_on": [
                "GTHP-009",
                "GTHP-010",
                "glitch-topstep:TS-R1-04",
                "glitch-topstep:TS-R2-06",
                "glitch-topstep:TS-R2-07",
            ],
            "stop_line": "No beta-ready or unattended evaluation/live claim until exact paired artifacts and operator promotion are recorded.",
        },
    ],
}
write("docs/ledger/ledger.json", json.dumps(ledger, indent=2) + "\n")

# Recalculate the existing distribution inventory and add the new spec. The
# installer-stamped distribution.yaml and SHA256SUMS itself remain excluded.
sums_path = ROOT / "SHA256SUMS"
paths: list[str] = []
for raw in sums_path.read_text(encoding="utf-8-sig").splitlines():
    if raw.strip():
        _old_hash, rel = raw.split(None, 1)
        paths.append(rel.strip())
if spec_path not in paths:
    insert_at = paths.index("operator.json") if "operator.json" in paths else len(paths)
    paths.insert(insert_at, spec_path)
entries = [
    f"{hashlib.sha256((ROOT / rel).read_bytes()).hexdigest().upper()}  {rel}"
    for rel in paths
]
sums_path.write_text("\n".join(entries) + "\n", encoding="utf-8-sig")

print("GTHP-009 rewrite applied")
