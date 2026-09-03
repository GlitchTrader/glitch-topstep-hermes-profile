"""Six-profile evaluation milestone — parallel ensemble + shadow offline + audits."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
MILESTONE_SCHEMA = "glitch.topstep.evaluation_milestone_six_profiles.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_parallel():
    spec = importlib.util.spec_from_file_location(
        "run_parallel_ensemble", SCRIPTS / "run-parallel-ensemble-evaluation.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_milestone(*, run_id: str, frames_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS))
    parallel = _load_parallel()

    def _load_script(name: str, filename: str):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    shadow_mod = _load_script("shadow_observe_offline", "shadow-observe-offline.py")
    stability_mod = _load_script("report_trail_a_stability", "report-trail-a-stability.py")
    provenance_mod = _load_script("validate_provenance", "validate-evaluation-provenance-chain.py")
    from common import read_json
    from ensemble_envelope_seal import seal_evaluation_envelope_from_frame, sealed_envelope_identity

    matrix = read_json(REPO / "evaluation" / "capability-matrix.json")
    registry = read_json(REPO / "evaluation" / "registry.json")
    rules = read_json(REPO / "evaluation" / "aggregator_rules.v1.json")
    mapping = read_json(REPO / "evaluation" / "packet_envelope_mapping.v1.json")
    fixtures_dir = REPO / "tests" / "fixtures" / "ensemble_candidates"

    ensemble_run = parallel.build_parallel_run(
        frames_dir=frames_dir,
        matrix_path=REPO / "evaluation" / "capability-matrix.json",
        registry_path=REPO / "evaluation" / "registry.json",
        config_path=REPO / "evaluation" / "ensemble_config.json",
        rules_path=REPO / "evaluation" / "aggregator_rules.v1.json",
        mapping_path=REPO / "evaluation" / "packet_envelope_mapping.v1.json",
        candidate_fixtures_dir=fixtures_dir,
    )
    ensemble_run["milestone_run_id"] = run_id

    runs_dir = REPO / "evaluation" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ensemble_path = runs_dir / f"{run_id}-six-profile-ensemble.json"
    ensemble_path.write_text(json.dumps(ensemble_run, indent=2) + "\n", encoding="utf-8")

    shadow_reports: list[dict[str, Any]] = []
    for frame_path in sorted(frames_dir.glob("*.json"))[:1]:
        frame = read_json(frame_path)
        frame_id = str(frame.get("minute_id") or frame_path.stem)
        sealed = seal_evaluation_envelope_from_frame(
            frame=frame,
            source_catalog=matrix["source_catalog"],
            mapping=mapping,
            validity_seconds=35,
            frame_path=str(frames_dir),
        )
        identity = sealed_envelope_identity(sealed)
        sealed["envelope_hash"] = identity["envelope_hash"]
        fixtures = {
            str(p["profile_id"]): (
                read_json(fixtures_dir / str(p["profile_id"]) / f"{frame_id}.json")
                if (fixtures_dir / str(p["profile_id"]) / f"{frame_id}.json").is_file()
                else None
            )
            for p in registry.get("profiles") or []
        }
        shadow_reports.append(
            shadow_mod.observe_envelope_offline(
                envelope=sealed,
                profile_fixtures=fixtures,
                registry=registry,
                matrix=matrix,
                rules=rules,
                run_id=f"{run_id}-shadow-{frame_id}",
            )
        )

    shadow_path = runs_dir / f"{run_id}-shadow-offline.json"
    shadow_path.write_text(json.dumps(shadow_reports, indent=2) + "\n", encoding="utf-8")

    trail_a = REPO / "evaluation" / "runs" / "trail-a-multi-envelope-2026-09-02.json"
    stability = stability_mod.build_trail_a_stability_report(bundle_path=trail_a) if trail_a.is_file() else None
    stability_path = runs_dir / f"{run_id}-stability-report.json"
    if stability:
        stability_path.write_text(json.dumps(stability, indent=2) + "\n", encoding="utf-8")

    provenance = provenance_mod.validate_bundle_chain(ensemble_run) if ensemble_run.get("frame_results") else {"verdict": "SKIP"}
    prov_path = runs_dir / f"{run_id}-provenance-chain.json"
    prov_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    profile_count = len([p for p in registry.get("profiles") or [] if p.get("enabled")])
    ok = (
        profile_count == 6
        and ensemble_run.get("evaluation_only")
        and provenance.get("verdict") in {"PASS", "SKIP"}
        and all(r.get("gateway_touched") is False for r in shadow_reports)
    )

    return {
        "schema_version": MILESTONE_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": run_id,
        "verdict": "PASS" if ok else "FAIL",
        "profile_count": profile_count,
        "artifacts": {
            "ensemble": str(ensemble_path),
            "shadow_offline": str(shadow_path),
            "stability": str(stability_path) if stability else None,
            "provenance": str(prov_path),
        },
        "shadow_live": False,
        "promotion_gate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Six-profile evaluation milestone")
    parser.add_argument("--run-id", default="eval-milestone-six-profiles-2026-09-02")
    parser.add_argument(
        "--frames-dir",
        type=Path,
        default=REPO / "tests" / "fixtures" / "frozen_corpus" / "minute-frames",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = run_milestone(run_id=args.run_id, frames_dir=args.frames_dir)
    output = args.output or (REPO / "evaluation" / "runs" / f"{args.run_id}.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
