"""Descriptive similarity clusters for GTHP-021 — cognition only, no execution path."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _cluster_key(episode: dict[str, Any]) -> tuple[str, ...]:
    audit = episode.get("decision_audit") if isinstance(episode.get("decision_audit"), dict) else {}
    pre = episode.get("pre_decision_state") if isinstance(episode.get("pre_decision_state"), dict) else {}
    return (
        str(episode.get("action") or "UNKNOWN"),
        str(episode.get("rejection_class") or "none"),
        str(pre.get("regime") or "unknown"),
        str(audit.get("final_choice") or "unknown"),
    )


def build_similarity_clusters(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        buckets[_cluster_key(episode)].append(episode)

    clusters: list[dict[str, Any]] = []
    for index, (key, rows) in enumerate(sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))):
        action, rejection_class, regime, final_choice = key
        clusters.append({
            "schema_version": "glitch.topstep.similarity_cluster.v1",
            "cluster_id": f"cluster-{index + 1}",
            "label": f"{action}/{rejection_class}/{regime}/{final_choice}",
            "count": len(rows),
            "sample_intent_ids": [str(row.get("intent_id")) for row in rows[:5] if row.get("intent_id")],
            "descriptive_only": True,
        })
    return clusters


def summarize_clusters(clusters: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    return clusters[: max(0, limit)]
