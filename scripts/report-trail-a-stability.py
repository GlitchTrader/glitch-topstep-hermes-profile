"""Stability and diversity metrics from Trilha A multi-envelope run artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "glitch.topstep.trail_a_stability_report.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _direction_agreement(directions: list[str]) -> float | None:
    dirs = [d for d in directions if d in {"long", "short"}]
    if not dirs:
        return None
    top = Counter(dirs).most_common(1)[0][1]
    return top / len(dirs)


def _state_agreement(states: list[str]) -> float | None:
    if not states:
        return None
    top = Counter(states).most_common(1)[0][1]
    return top / len(states)


def _pairwise_direction_correlation(profiles: dict[str, list[str]]) -> dict[str, float]:
    """Simple agreement rate vs baseline direction per frame."""
    baseline = profiles.get("baseline-current") or []
    out: dict[str, float] = {}
    for pid, dirs in profiles.items():
        if pid == "baseline-current":
            continue
        pairs = [(b, d) for b, d in zip(baseline, dirs) if b and d]
        if not pairs:
            out[pid] = 0.0
            continue
        agree = sum(1 for b, d in pairs if b == d or d in {"flat", "hold"} or b in {"flat", "hold"})
        out[pid] = round(agree / len(pairs), 4)
    return out


def build_trail_a_stability_report(*, bundle_path: Path) -> dict[str, Any]:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    frame_results = bundle.get("frame_results") or []

    directions_by_profile: dict[str, list[str]] = defaultdict(list)
    states_by_profile: dict[str, list[str]] = defaultdict(list)
    latency_by_profile: dict[str, list[int]] = defaultdict(list)
    cost_by_profile: dict[str, float] = defaultdict(float)
    aggregator_codes: list[str] = []
    envelope_identities: list[dict[str, str]] = []

    for frame in frame_results:
        aggregator_codes.append(str((frame.get("selection") or {}).get("decision_code") or ""))
        envelope_identities.append(
            {
                "frame_id": str(frame.get("frame_id") or ""),
                "snapshot_hash": str(frame.get("sealed_snapshot_hash") or ""),
                "envelope_hash": str(frame.get("sealed_envelope_hash") or ""),
            }
        )
        slots_sorted = sorted(frame.get("profile_slots") or [], key=lambda s: str(s.get("profile_id")))
        slots_shuffled = list(reversed(slots_sorted))
        order_invariant = True
        for slot in slots_sorted:
            pid = str(slot.get("profile_id") or "")
            art = slot.get("artifact") or {}
            norm = art.get("normalized") or {}
            directions_by_profile[pid].append(str(norm.get("direction") or ""))
            states_by_profile[pid].append(str(norm.get("state") or ""))
            latency_by_profile[pid].append(int(art.get("latency_ms") or 0))
            cost_by_profile[pid] += float(art.get("cost_usd") or 0.0)
        if slots_sorted and slots_shuffled:
            order_invariant = [s.get("profile_id") for s in slots_sorted] != [s.get("profile_id") for s in slots_shuffled]

    per_profile = {}
    for pid in sorted(set(directions_by_profile) | set(states_by_profile)):
        per_profile[pid] = {
            "direction_stability": _direction_agreement(directions_by_profile.get(pid, [])),
            "state_stability": _state_agreement(states_by_profile.get(pid, [])),
            "latency_ms_p50": sorted(latency_by_profile.get(pid, [0]))[len(latency_by_profile.get(pid, [0])) // 2]
            if latency_by_profile.get(pid)
            else None,
            "cost_usd_total": round(cost_by_profile.get(pid, 0.0), 6),
        }

    return {
        "schema_version": REPORT_SCHEMA,
        "generated_utc": utc_now(),
        "source_bundle": str(bundle_path),
        "run_id": bundle.get("run_id"),
        "envelope_count": len(frame_results),
        "sequential_vs_parallel": {
            "note": "Trail A used parallel slots=2; per-frame profile order sorted for audit",
            "parallel_slots": bundle.get("max_parallel_slots"),
        },
        "envelope_identities": envelope_identities,
        "aggregator_stability": {
            "decision_codes": aggregator_codes,
            "unique_codes": sorted(set(aggregator_codes)),
            "stable_across_envelopes": len(set(aggregator_codes)) == 1 if aggregator_codes else False,
        },
        "per_profile": per_profile,
        "pairwise_baseline_correlation": _pairwise_direction_correlation(dict(directions_by_profile)),
        "session_cost_usd": bundle.get("session_cost_usd"),
        "textual_equality_required": False,
        "promotion_gate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trail A stability report")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=REPO / "evaluation" / "runs" / "trail-a-multi-envelope-2026-09-02.json",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = build_trail_a_stability_report(bundle_path=args.bundle)
    output = args.output or args.bundle.with_name(args.bundle.stem + "-stability-report.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "envelopes": report["envelope_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
