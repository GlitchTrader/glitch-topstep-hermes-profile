"""Aggregate shadow observation metrics across sessions — evaluation lane only."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
METRICS_SCHEMA = "glitch.topstep.shadow_metrics_report.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[idx]


def _load_observations(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, list):
            rows.extend([r for r in doc if isinstance(r, dict)])
        elif isinstance(doc, dict):
            if "observation" in doc:
                obs = doc["observation"]
                if isinstance(obs, dict):
                    rows.append(obs)
            elif doc.get("schema_version", "").startswith("glitch.topstep.shadow_observation"):
                rows.append(doc)
    return rows


def build_shadow_metrics_report(*, observation_paths: list[Path]) -> dict[str, Any]:
    observations = _load_observations(observation_paths)
    latencies: list[int] = []
    costs: list[float] = []
    no_selection = 0
    errors = 0
    writes = 0
    divergence_count = 0
    snapshot_ages: list[int] = []
    evidence_available = 0
    evidence_total = 0
    directions_by_profile: dict[str, list[str]] = defaultdict(list)

    for obs in observations:
        latencies.append(int(obs.get("latency_ms_total") or 0))
        costs.append(float(obs.get("cost_usd") or 0))
        writes += int(obs.get("writes_operacionais") or 0)
        if obs.get("aggregator_selection", {}).get("outcome") == "no_selection":
            no_selection += 1
        divergence_count += len(obs.get("divergences") or [])
        age = (obs.get("envelope") or {}).get("snapshot_age_ms")
        if isinstance(age, int):
            snapshot_ages.append(age)
        for row in obs.get("profile_decisions") or []:
            evidence_total += 1
            if row.get("state") not in {"error", "timeout", "invalid"}:
                evidence_available += 1
            pid = str(row.get("profile_id") or "")
            directions_by_profile[pid].append(str(row.get("direction") or ""))

        if any(row.get("error") for row in obs.get("profile_decisions") or []):
            errors += 1
        if obs.get("isolation_failures"):
            errors += 1

    n = len(observations) or 1
    correlation: dict[str, float] = {}
    baseline_dirs = directions_by_profile.get("baseline-current") or []
    for pid, dirs in directions_by_profile.items():
        if pid == "baseline-current":
            continue
        pairs = [(b, d) for b, d in zip(baseline_dirs, dirs) if b and d]
        if not pairs:
            correlation[pid] = 0.0
            continue
        agree = sum(1 for b, d in pairs if b == d or d in {"flat", "hold"} or b in {"flat", "hold"})
        correlation[pid] = round(agree / len(pairs), 4)

    return {
        "schema_version": METRICS_SCHEMA,
        "generated_utc": utc_now(),
        "session_count": len(observations),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
        "cost_usd": {
            "total": round(sum(costs), 6),
            "mean_per_session": round(sum(costs) / n, 6),
        },
        "error_rate": round(errors / n, 4),
        "no_selection_rate": round(no_selection / n, 4),
        "divergence_events": divergence_count,
        "profile_direction_correlation": correlation,
        "evidence_availability_rate": round(evidence_available / max(evidence_total, 1), 4),
        "snapshot_age_ms": {
            "mean": round(sum(snapshot_ages) / len(snapshot_ages), 2) if snapshot_ages else None,
            "max": max(snapshot_ages) if snapshot_ages else None,
        },
        "operational_writes_total": writes,
        "aggregator_outcomes": dict(Counter(
            str((o.get("aggregator_selection") or {}).get("outcome") or "unknown") for o in observations
        )),
        "promotion_use_allowed": False,
        "production_parallelism": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow metrics report across observation sessions")
    parser.add_argument("observations", nargs="+", type=Path, help="Shadow observation JSON files")
    parser.add_argument("--output", type=Path, default=REPO / "evaluation" / "runs" / "shadow-metrics-report.json")
    args = parser.parse_args()

    report = build_shadow_metrics_report(observation_paths=args.observations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"session_count": report["session_count"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
