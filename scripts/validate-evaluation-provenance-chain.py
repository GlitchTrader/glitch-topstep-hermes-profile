"""Validate evaluation provenance chain for offline artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CHAIN_SCHEMA = "glitch.topstep.evaluation_provenance_chain_audit.v1"
REQUIRED_LINKS = (
    "packet_id",
    "snapshot_hash",
    "envelope_hash",
    "profile_id",
    "invocation_id",
    "profile_decision",
    "aggregator_decision",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _chain_row(
    *,
    packet_id: str | None,
    snapshot_hash: str | None,
    envelope_hash: str | None,
    profile_id: str | None,
    invocation_id: str | None,
    profile_decision: str | None,
    aggregator_decision: str | None,
    outcome: str | None,
    diagnostic_only: bool,
) -> dict[str, Any]:
    row = {
        "packet_id": packet_id,
        "snapshot_hash": snapshot_hash,
        "envelope_hash": envelope_hash,
        "profile_id": profile_id,
        "invocation_id": invocation_id,
        "profile_decision": profile_decision,
        "aggregator_decision": aggregator_decision,
        "outcome": outcome,
        "diagnostic_only": diagnostic_only,
        "chain_complete": all(
            [
                packet_id,
                snapshot_hash,
                envelope_hash,
                profile_id,
                invocation_id,
                profile_decision,
                aggregator_decision is not None,
            ]
        ),
    }
    return row


def validate_bundle_chain(bundle: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    rows: list[dict[str, Any]] = []
    agg_code = str((bundle.get("selection") or {}).get("decision_code") or "")

    if bundle.get("multi_envelope"):
        for frame in bundle.get("frame_results") or []:
            agg_code = str((frame.get("selection") or {}).get("decision_code") or "")
            for slot in frame.get("profile_slots") or []:
                art = slot.get("artifact") or {}
                norm = art.get("normalized") or {}
                packet_id = str(
                    norm.get("packet_id")
                    or art.get("packet_id")
                    or norm.get("envelope_id")
                    or art.get("envelope_id")
                    or ""
                ) or None
                row = _chain_row(
                    packet_id=packet_id or None,
                    snapshot_hash=str(art.get("snapshot_hash") or frame.get("sealed_snapshot_hash") or ""),
                    envelope_hash=str(norm.get("envelope_hash") or frame.get("sealed_envelope_hash") or ""),
                    profile_id=str(slot.get("profile_id") or ""),
                    invocation_id=str(art.get("invocation_id") or ""),
                    profile_decision=str(norm.get("state") or ""),
                    aggregator_decision=agg_code or None,
                    outcome=None,
                    diagnostic_only=agg_code in {"", "INSUFFICIENT_ENSEMBLE_AGREEMENT", "ENSEMBLE_UNANIMOUS_ABSTENTION"},
                )
                rows.append(row)
                if not row["chain_complete"]:
                    issues.append(f"incomplete_chain:{row['profile_id']}:{frame.get('frame_id')}")
    else:
        for slot in bundle.get("profile_slots") or []:
            art = slot.get("artifact") or {}
            norm = art.get("normalized") or {}
            row = _chain_row(
                packet_id=str(art.get("envelope_id") or ""),
                snapshot_hash=str(art.get("snapshot_hash") or bundle.get("sealed_snapshot_hash") or ""),
                envelope_hash=str(norm.get("envelope_hash") or bundle.get("envelope_hash") or ""),
                profile_id=str(slot.get("profile_id") or ""),
                invocation_id=str(art.get("invocation_id") or ""),
                profile_decision=str(norm.get("state") or ""),
                aggregator_decision=agg_code or None,
                outcome=None,
                diagnostic_only=True,
            )
            rows.append(row)

    return {
        "schema_version": CHAIN_SCHEMA,
        "generated_utc": utc_now(),
        "run_id": bundle.get("run_id"),
        "verdict": "PASS" if not issues else "FAIL",
        "issues": issues,
        "rows": rows,
        "complete_rows": sum(1 for r in rows if r["chain_complete"]),
        "total_rows": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evaluation provenance chain")
    parser.add_argument("bundle", type=Path, nargs="?", default=REPO / "evaluation" / "runs" / "trail-a-multi-envelope-2026-09-02.json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    report = validate_bundle_chain(bundle)
    output = args.output or args.bundle.with_name(args.bundle.stem + "-provenance-chain.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "output": str(output)}, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
