"""Cognitive overlay governance for learning loops (audit C1)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from common import read_jsonl, read_optional_json, utc_now, write_json_atomic
from parity import PROMPT_VERSION
from workflows.learning_journal import append_unique, stable_id


def auto_overlay_enabled() -> bool:
    return os.environ.get("GLITCH_TOPSTEP_AUTO_ACTIVATE_OVERLAY", "false").strip().lower() == "true"


OVERLAY_LIFECYCLE: dict[str, frozenset[str]] = {
    "proposed": frozenset({"holdout_evaluated", "active", "rolled_back"}),
    "holdout_evaluated": frozenset({"shadow", "rolled_back"}),
    "shadow": frozenset({"canary", "expired", "rolled_back"}),
    "canary": frozenset({"active", "expired", "rolled_back"}),
    "active": frozenset({"promoted", "expired", "rolled_back"}),
    "promoted": frozenset({"expired", "rolled_back"}),
    "activated": frozenset({"promoted", "expired", "rolled_back"}),
    "expired": frozenset(),
    "rolled_back": frozenset(),
}


def transition_overlay_lifecycle(overlay: dict[str, Any], next_status: str) -> None:
    current = str(overlay.get("status") or "")
    allowed = OVERLAY_LIFECYCLE.get(current, frozenset())
    if next_status not in allowed:
        raise ValueError("overlay_lifecycle_transition_invalid")
    overlay["status"] = next_status
    overlay["evaluated_utc"] = utc_now()


def overlay_min_episodes() -> int:
    try:
        return max(2, int(os.environ.get("GLITCH_TOPSTEP_OVERLAY_MIN_EPISODES", "6")))
    except ValueError:
        return 6


def cognitive_candidate_is_general(expected_old_text: str, replacement_text: str) -> bool:
    forbidden_patterns = (
        r"\b(?:MES|MNQ|MCL|ES|NQ|YM|RTY|CL|GC)\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b\d+(?:\.\d+)?\s*(?:ticks?|points?|contracts?)\b",
        r"\b(?:always|never)\s+(?:enter|exit|buy|sell|go\s+long|go\s+short)\b",
        r"\b(?:long|short)[ -]only\b",
        r"\b(?:daily|weekly)\s+(?:profit|loss|trade)\s+(?:target|limit|quota)\b",
        r"\bfixed\s+(?:stop|target|size|quantity|risk|reward)\b",
    )
    if any(re.search(pattern, replacement_text, flags=re.IGNORECASE) for pattern in forbidden_patterns):
        return False
    old = expected_old_text.lower()
    new = replacement_text.lower()
    protected_terms = (
        "schema_version",
        "intent_id",
        "operator_profile",
        "authorization",
        "loss floor",
        "account limit",
        "execution contract",
    )
    return not any(term in new and term not in old for term in protected_terms)


def decision_episode_session_dates(supervisor: Path, evidence_ids: list[str]) -> set[str]:
    wanted = set(evidence_ids)
    sessions: set[str] = set()
    for row in read_jsonl(supervisor / "decision-episodes.jsonl"):
        episode_id = str(row.get("episode_id") or "")
        if episode_id not in wanted:
            continue
        context = row.get("evidence_context") if isinstance(row.get("evidence_context"), dict) else {}
        session = str(context.get("session_date_et") or "")
        if not session:
            stamp = str(row.get("decision_utc") or row.get("recorded_utc") or "")
            session = stamp[:10]
        if session:
            sessions.add(session)
    for row in read_jsonl(supervisor / "trade-episodes.jsonl"):
        episode_id = str(row.get("episode_id") or "")
        if episode_id not in wanted:
            continue
        stamp = str(row.get("exit_utc") or row.get("recorded_utc") or "")
        if stamp[:10]:
            sessions.add(stamp[:10])
    return sessions


def promotion_gate_allows_proposal(
    supervisor: Path,
    evidence_ids: list[str],
    *,
    expected_old_text: str,
    replacement_text: str,
    evaluation_metric: Any,
    rollback_condition: Any,
) -> bool:
    unique_ids = sorted(set(evidence_ids))
    if len(unique_ids) < 2:
        return False
    if len(decision_episode_session_dates(supervisor, unique_ids)) < 2:
        return False
    if not cognitive_candidate_is_general(expected_old_text, replacement_text):
        return False
    if not str(evaluation_metric or "").strip() or not str(rollback_condition or "").strip():
        return False
    return True


def process_candidate(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    candidate = record.get("cognitive_change_candidate")
    if not isinstance(candidate, dict) or candidate.get("propose") is not True:
        return
    instruction = str(candidate.get("instruction") or "").strip()
    evidence_ids = [str(value) for value in candidate.get("evidence_episode_ids", [])]
    target = str(candidate.get("target") or "")
    if target not in {"core_prompt", "soul"} and not target.startswith("skill:"):
        return
    if not instruction or len(instruction) > 1200 or len(set(evidence_ids)) < overlay_min_episodes():
        return
    if any(value not in set(episode_ids) for value in evidence_ids):
        return
    if not promotion_gate_allows_proposal(
        supervisor,
        evidence_ids,
        expected_old_text=instruction,
        replacement_text=instruction,
        evaluation_metric=candidate.get("evaluation_metric"),
        rollback_condition=candidate.get("rollback_condition"),
    ):
        return
    candidate_id = str(candidate.get("candidate_id") or stable_id("cognitive-change", target + "|" + instruction))
    value = {
        "schema_version": "glitch.topstep.cognitive_candidate.v1",
        "candidate_id": candidate_id,
        "recorded_utc": utc_now(),
        "target": target,
        "instruction": instruction,
        "evidence_episode_ids": evidence_ids,
        "expected_effect": candidate.get("expected_effect"),
        "evaluation_metric": candidate.get("evaluation_metric"),
        "rollback_condition": candidate.get("rollback_condition"),
        "status": "active" if auto_overlay_enabled() else "proposed",
    }
    append_unique(supervisor / "cognitive-candidates.jsonl", [value], "candidate_id")
    if auto_overlay_enabled() and not read_optional_json(supervisor / "active-cognitive-overlay.json"):
        write_json_atomic(supervisor / "active-cognitive-overlay.json", value)


def trade_evidence_ids(supervisor: Path) -> list[str]:
    return [
        str(row.get("episode_id"))
        for row in read_jsonl(supervisor / "trade-episodes.jsonl")
        if row.get("episode_id")
    ]


def later_evidence_ids(value: dict[str, Any], episode_ids: list[str]) -> set[str]:
    baseline = value.get("baseline_evidence_ids")
    if isinstance(baseline, list):
        return set(episode_ids).difference(str(item) for item in baseline)
    cursor = int(value.get("evaluation_episode_count", value.get("baseline_episode_count")) or 0)
    return set(episode_ids[cursor:])


def apply_cognitive_decision(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    active_path = supervisor / "active-cognitive-overlay.json"
    active = read_optional_json(active_path)
    decision = record.get("cognitive_change_decision")
    if not isinstance(decision, dict):
        return
    action = str(decision.get("action") or "").lower()
    contradiction_review = str(decision.get("contradiction_review") or "").strip()
    if (
        active
        and active.get("status") in {"active", "promoted"}
        and active.get("replacement_text")
        and str(decision.get("candidate_id")) == str(active.get("candidate_id"))
    ):
        later_episode_ids = later_evidence_ids(active, episode_ids).intersection(
            trade_evidence_ids(supervisor)
        )
        later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
        if len(set(later)) < 1 or action not in {
            "continue",
            "promote",
            "rollback",
            "holdout_pass",
            "shadow_pass",
            "canary_pass",
            "expire",
        } or not contradiction_review:
            return
        if action == "continue":
            pass
        elif action == "promote":
            transition_overlay_lifecycle(active, "promoted")
        elif action == "rollback":
            transition_overlay_lifecycle(active, "rolled_back")
            active.pop("replacement_text", None)
        elif action == "holdout_pass":
            transition_overlay_lifecycle(active, "holdout_evaluated")
        elif action == "shadow_pass":
            transition_overlay_lifecycle(active, "shadow")
        elif action == "canary_pass":
            transition_overlay_lifecycle(active, "canary")
        elif action == "expire":
            transition_overlay_lifecycle(active, "expired")
        active["evaluation_episode_count"] = len(episode_ids)
        active["baseline_evidence_ids"] = list(episode_ids)
        active["evaluation"] = decision
        write_json_atomic(active_path, active)
        return

    proposed_path = supervisor / "proposed-cognitive-overlay.json"
    proposed = read_optional_json(proposed_path)
    if (
        not proposed
        or proposed.get("status") != "proposed"
        or not proposed.get("replacement_text")
        or str(decision.get("candidate_id")) != str(proposed.get("candidate_id"))
        or action not in {"activate", "rollback"}
    ):
        return
    later_episode_ids = later_evidence_ids(proposed, episode_ids).intersection(
        trade_evidence_ids(supervisor)
    )
    later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
    if len(set(later)) < 1 or not contradiction_review:
        return
    if action == "activate":
        transition_overlay_lifecycle(proposed, "active")
    elif action == "rollback":
        transition_overlay_lifecycle(proposed, "rolled_back")
        proposed.pop("replacement_text", None)
    else:
        return
    proposed["evaluation"] = decision
    write_json_atomic(proposed_path, proposed)
    if action == "activate":
        write_json_atomic(
            active_path,
            {
                **proposed,
                "status": "active",
                "activated_utc": utc_now(),
                "baseline_episode_count": len(episode_ids),
                "evaluation_episode_count": len(episode_ids),
                "baseline_evidence_ids": list(episode_ids),
                "prompt_version": PROMPT_VERSION,
                "operation": "replace",
                "target": "core_prompt",
            },
        )


def activate_cognitive_candidate(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    candidate = record.get("cognitive_change_candidate")
    if not isinstance(candidate, dict) or candidate.get("propose") is not True:
        return
    current = read_optional_json(supervisor / "active-cognitive-overlay.json")
    if current and current.get("status") in {"active", "promoted"} and current.get("replacement_text"):
        return
    proposed_path = supervisor / "proposed-cognitive-overlay.json"
    proposed = read_optional_json(proposed_path)
    if proposed and proposed.get("status") == "proposed" and proposed.get("replacement_text"):
        return
    target = str(candidate.get("target") or "")
    operation = str(candidate.get("operation") or "replace")
    expected_old_text = str(candidate.get("expected_old_text") or candidate.get("instruction") or "").strip()
    replacement_text = str(candidate.get("replacement_text") or candidate.get("instruction") or "").strip()
    evidence_ids = [str(value) for value in candidate.get("evidence_episode_ids", [])]
    if (
        target != "core_prompt"
        or operation != "replace"
        or not expected_old_text
        or not replacement_text
        or expected_old_text == replacement_text
        or len(expected_old_text) > 600
        or len(replacement_text) > 600
        or len(set(evidence_ids)) < 2
        or any(value not in set(episode_ids) for value in evidence_ids)
        or not promotion_gate_allows_proposal(
            supervisor,
            evidence_ids,
            expected_old_text=expected_old_text,
            replacement_text=replacement_text,
            evaluation_metric=candidate.get("evaluation_metric"),
            rollback_condition=candidate.get("rollback_condition"),
        )
    ):
        return
    candidate_id = str(
        candidate.get("candidate_id")
        or stable_id("cognitive-change", target + "|" + expected_old_text + "|" + replacement_text)
    )
    value = {
        "schema_version": "glitch.topstep.cognitive_overlay.v1",
        "candidate_id": candidate_id,
        "recorded_utc": utc_now(),
        "target": target,
        "operation": operation,
        "expected_old_text": expected_old_text,
        "expected_old_sha256": hashlib.sha256(expected_old_text.encode("utf-8")).hexdigest(),
        "replacement_text": replacement_text,
        "evidence_episode_ids": evidence_ids,
        "expected_effect": candidate.get("expected_effect"),
        "evaluation_metric": candidate.get("evaluation_metric"),
        "rollback_condition": candidate.get("rollback_condition"),
        "status": "proposed",
        "prompt_version": PROMPT_VERSION,
    }
    write_json_atomic(proposed_path, value)


def persist_hourly(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    append_unique(supervisor / "hourly-reviews.jsonl", [record], "review_id")
    append_unique(supervisor / "observations.jsonl", [record], "review_id")
    trade_count = len(trade_evidence_ids(supervisor))
    decision_count = len(read_jsonl(supervisor / "decision-episodes.jsonl"))
    lesson_influence = "outcome_backed" if trade_count >= 2 else "observational"
    guidance = {
        "schema_version": "glitch.topstep.guidance.v1",
        "guidance_id": stable_id("guidance", str(record["review_id"])),
        "recorded_utc": record.get("recorded_utc") or utc_now(),
        "source_review_id": record["review_id"],
        "prompt_version": PROMPT_VERSION,
        "trading_influence": "outcome_backed" if trade_count >= 2 else "observational",
        "trade_episode_count": trade_count,
        "decision_episode_count": decision_count,
        "guidance": record.get("guidance"),
    }
    append_unique(supervisor / "guidance.jsonl", [guidance], "guidance_id")
    write_json_atomic(supervisor / "current-guidance.json", guidance)
    lessons = []
    for index, lesson in enumerate(record.get("candidate_lessons", [])):
        if not isinstance(lesson, dict):
            continue
        lessons.append({
            "schema_version": "glitch.topstep.candidate_lesson.v1",
            "lesson_id": str(lesson.get("lesson_id") or stable_id("lesson", f"{record['review_id']}:{index}")),
            "recorded_utc": utc_now(),
            "source_review_id": record["review_id"],
            "trading_influence": lesson_influence,
            **lesson,
        })
    append_unique(supervisor / "lessons.jsonl", lessons, "lesson_id")
    apply_cognitive_decision(record, supervisor, episode_ids)
    activate_cognitive_candidate(record, supervisor, episode_ids)
    process_candidate(record, supervisor, episode_ids)
