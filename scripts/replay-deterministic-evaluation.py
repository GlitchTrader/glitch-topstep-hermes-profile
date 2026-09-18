"""Phase 8 deterministic replay — sealed envelope + normalized candidates + aggregator rules."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import read_json  # noqa: E402
from ensemble_aggregator import aggregate_envelope  # noqa: E402
from evaluation_run_public_bundle import slot_normalized  # noqa: E402

REPLAY_SCHEMA = "glitch.topstep.deterministic_replay.v1"
DEFAULT_RULES = REPO / "evaluation" / "aggregator_rules.v1.json"
DEFAULT_WORK = REPO / "evaluation" / "runs" / "phase8-replay-2026-09-02"

FAILURE_CLASSES = frozenset(
    {
        "thesis_error",
        "selection_error",
        "data_error",
        "execution_error",
        "timeout",
        "missing_evidence",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fixture_aggregate_kwargs(case: dict[str, Any]) -> dict[str, Any]:
    """Build process/required_profile_ids like aggregate_fixture_case for replay tests."""
    inputs = case.get("inputs") or {}
    process = dict(inputs.get("process") or {})
    missing = inputs.get("missing_profiles")
    if missing:
        process["missing_profiles"] = list(missing)
    return {
        "process": process,
        "required_profile_ids": inputs.get("registry_required_profiles"),
    }


def collect_candidates(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if bundle.get("profile_slots"):
        for slot in bundle["profile_slots"]:
            norm = slot_normalized(slot) or (slot.get("artifact") or {}).get("normalized")
            if norm:
                rows.append(norm)
    for frame in bundle.get("frame_results") or []:
        for slot in frame.get("profile_slots") or []:
            norm = slot.get("normalized")
            if norm:
                rows.append(norm)
    return rows


def extract_envelope(bundle: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if bundle.get("sealed_snapshot_hash"):
        return {
            "envelope_id": bundle.get("envelope_id") or f"env-{str(bundle.get('frame_id') or 'replay')[:16]}",
            "instrument": "MNQ",
            "snapshot_hash": bundle["sealed_snapshot_hash"],
            "envelope_hash": bundle.get("envelope_hash") or bundle["sealed_snapshot_hash"],
            "contract": {"tick_size": 0.25},
            "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
        }
    frame = (bundle.get("frame_results") or [None])[0]
    if isinstance(frame, dict):
        return {
            "envelope_id": f"env-{frame.get('frame_id', 'replay')}",
            "instrument": "MNQ",
            "snapshot_hash": frame["sealed_snapshot_hash"],
            "envelope_hash": frame["envelope_hash"],
            "contract": {"tick_size": 0.25},
            "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
        }
    hashes = {str(c.get("envelope_hash") or "") for c in candidates}
    hashes.discard("")
    env_hash = hashes.pop() if len(hashes) == 1 else "0" * 64
    return {
        "envelope_id": "env-fixture-replay",
        "instrument": "MNQ",
        "snapshot_hash": env_hash,
        "envelope_hash": env_hash,
        "contract": {"tick_size": 0.25},
        "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
    }


def classify_failure(
    *,
    selection: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str | None:
    failure_class = selection.get("failure_class")
    if failure_class == "ensemble_timeout":
        return "timeout"
    if failure_class in {"snapshot_divergence", "schema_invalid", "version_incompatible"}:
        return "data_error"

    states = {str(c.get("state") or "") for c in candidates}
    if "timeout" in states:
        return "timeout"
    if "error" in states:
        return "execution_error"
    if "missing_required_evidence" in states or "data_quality_insufficient" in states:
        return "missing_evidence"

    outcome = str(selection.get("outcome") or "")
    code = str(selection.get("decision_code") or "")

    if outcome == "classified_failure":
        if failure_class:
            return "data_error"
        return "selection_error"

    if code in {"DIRECTION_CONFLICT", "ENSEMBLE_CATEGORY_DIVERGENCE"}:
        return "thesis_error"
    if code in {
        "INSUFFICIENT_ENSEMBLE_AGREEMENT",
        "ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION",
        "PROFILE_MISSING",
    }:
        return "selection_error"

    if outcome == "no_selection" and code == "ENSEMBLE_UNANIMOUS_ABSTENTION":
        return None

    return None


def replay_bundle(
    *,
    bundle_path: Path,
    rules: dict[str, Any],
    run_id: str | None = None,
    shuffle_passes: int = 3,
) -> dict[str, Any]:
    bundle = read_json(bundle_path)
    candidates = collect_candidates(bundle)
    envelope = extract_envelope(bundle, candidates)
    base_run_id = run_id or str(bundle.get("run_id") or bundle_path.stem)

    selection = aggregate_envelope(
        run_id=base_run_id,
        envelope=envelope,
        candidates=list(candidates),
        rules=rules,
        objections=(bundle.get("selection") or {}).get("objections") or [],
    )

    import random

    rng = random.Random(42)
    order_invariant = True
    base_sig = (
        selection["outcome"],
        selection["decision_code"],
        selection.get("selected_profile_id"),
        selection.get("failure_class"),
    )
    for _ in range(shuffle_passes):
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        replay = aggregate_envelope(
            run_id=base_run_id,
            envelope=envelope,
            candidates=shuffled,
            rules=rules,
            objections=(bundle.get("selection") or {}).get("objections") or [],
        )
        sig = (
            replay["outcome"],
            replay["decision_code"],
            replay.get("selected_profile_id"),
            replay.get("failure_class"),
        )
        if sig != base_sig:
            order_invariant = False
            break

    failure_classification = classify_failure(selection=selection, candidates=candidates)

    return {
        "bundle_path": str(bundle_path),
        "run_id": base_run_id,
        "candidate_count": len(candidates),
        "global_decision": {
            "outcome": selection["outcome"],
            "decision_code": selection["decision_code"],
            "selected_profile_id": selection.get("selected_profile_id"),
            "failure_class": selection.get("failure_class"),
        },
        "failure_classification": failure_classification,
        "order_invariant": order_invariant,
        "envelope_hash": envelope.get("envelope_hash"),
    }


def run_phase8_replay(
    *,
    bundles: list[Path],
    rules_path: Path = DEFAULT_RULES,
    work_dir: Path = DEFAULT_WORK,
) -> dict[str, Any]:
    rules = read_json(rules_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    replays = [replay_bundle(bundle_path=path, rules=rules) for path in bundles]
    order_ok = all(r["order_invariant"] for r in replays)

    return {
        "schema_version": REPLAY_SCHEMA,
        "generated_utc": utc_now(),
        "evaluation_only": True,
        "armed_promotion_allowed": False,
        "rules_version": rules.get("rules_version"),
        "bundle_count": len(replays),
        "order_invariant_all": order_ok,
        "failure_classifications": sorted(
            {r["failure_classification"] for r in replays if r["failure_classification"]}
        ),
        "replays": replays,
    }


def default_bundles() -> list[Path]:
    candidates = [
        REPO / "evaluation" / "runs" / "eval-milestone-six-profiles-2026-09-02-six-profile-ensemble.json",
        REPO / "evaluation" / "runs" / "trail-a-real-2026-09-02.json",
        REPO / "evaluation" / "runs" / "parallel-ensemble-offline-2026-09-02.json",
        REPO / "tests" / "fixtures" / "evaluation_runs" / "bundle-run-a.json",
    ]
    return [p for p in candidates if p.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 8 deterministic evaluation replay")
    parser.add_argument("--bundle", type=Path, action="append", dest="bundles")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--output", type=Path, default=DEFAULT_WORK / "replay-report.json")
    args = parser.parse_args()

    bundles = args.bundles or default_bundles()
    if not bundles:
        print(json.dumps({"ok": False, "error": "no_bundles_found"}))
        return 1

    usable = []
    for path in bundles:
        doc = read_json(path)
        if doc.get("profile_slots") or doc.get("frame_results"):
            usable.append(path)
    if not usable:
        usable = bundles

    report = run_phase8_replay(bundles=usable, rules_path=args.rules, work_dir=args.work_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "bundles": len(report["replays"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
