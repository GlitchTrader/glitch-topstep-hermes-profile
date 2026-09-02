"""Metrics for parallel ensemble evaluation runs (non-gating)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def compute_ensemble_metrics(run: dict[str, Any]) -> dict[str, Any]:
    """Aggregate per-profile and global metrics from a parallel ensemble run."""
    profile_latency: dict[str, list[int]] = defaultdict(list)
    profile_cost: dict[str, float] = defaultdict(float)
    state_counts: Counter[str] = Counter()
    aggregator_outcomes: Counter[str] = Counter()
    direction_by_profile: dict[str, list[str]] = defaultdict(list)
    divergence_pairs = 0
    frames = run.get("frame_results") or []

    for frame in frames:
        selections = frame.get("selection") or {}
        aggregator_outcomes[str(selections.get("outcome") or "unknown")] += 1
        dirs: dict[str, str] = {}
        for slot in frame.get("profile_slots") or []:
            pid = str(slot.get("profile_id") or "")
            norm = slot.get("normalized") or {}
            state = str(norm.get("state") or "unknown")
            state_counts[state] += 1
            profile_latency[pid].append(int(slot.get("latency_ms") or 0))
            profile_cost[pid] += float(slot.get("estimated_cost_usd") or 0.0)
            direction = str(norm.get("direction") or "")
            if direction:
                direction_by_profile[pid].append(direction)
                dirs[pid] = direction
        unique_dirs = {d for d in dirs.values() if d in {"long", "short"}}
        if len(unique_dirs) > 1:
            divergence_pairs += 1

    def _p50(values: list[int]) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        return ordered[len(ordered) // 2]

    per_profile = {}
    for pid in set(profile_latency) | set(profile_cost):
        latencies = profile_latency.get(pid, [])
        per_profile[pid] = {
            "invocation_count": len(latencies),
            "latency_ms_p50": _p50(latencies),
            "latency_ms_total": sum(latencies),
            "cost_usd_total": round(profile_cost.get(pid, 0.0), 6),
            "no_edge_rate": (
                state_counts.get("no_edge", 0) / len(latencies) if latencies else None
            ),
            "candidate_rate": (
                sum(1 for _ in latencies if True)  # filled below
            ),
        }

    for frame in frames:
        for slot in frame.get("profile_slots") or []:
            pid = str(slot.get("profile_id") or "")
            if pid not in per_profile:
                continue
            state = str((slot.get("normalized") or {}).get("state") or "")
            if state == "candidate":
                per_profile[pid].setdefault("_candidates", 0)
                per_profile[pid]["_candidates"] += 1
    for row in per_profile.values():
        inv = row.get("invocation_count") or 0
        row["candidate_rate"] = (row.pop("_candidates", 0) / inv) if inv else 0.0

    total_latency = sum(sum(profile_latency[p]) for p in profile_latency)
    return {
        "schema_version": "glitch.topstep.ensemble_metrics.v1",
        "frame_count": len(frames),
        "total_latency_ms": total_latency,
        "session_cost_usd": round(float(run.get("session_cost_usd") or 0.0), 6),
        "failure_rate": (
            sum(1 for s, c in state_counts.items() if s in {"error", "timeout", "invalid"} for _ in range(c))
            / max(1, sum(state_counts.values()))
        ),
        "no_edge_rate": state_counts.get("no_edge", 0) / max(1, sum(state_counts.values())),
        "candidate_rate": state_counts.get("candidate", 0) / max(1, sum(state_counts.values())),
        "profile_divergence_frames": divergence_pairs,
        "aggregator_outcomes": dict(aggregator_outcomes),
        "state_counts": dict(state_counts),
        "per_profile": per_profile,
        "evaluation_only": True,
        "promotion_gate": False,
    }
