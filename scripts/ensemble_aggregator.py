"""Deterministic offline ensemble aggregator (evaluation lane only)."""

from __future__ import annotations

import math
import uuid
from typing import Any

from ensemble_compare import classify_candidate
from ensemble_geometry import tick_size_from_envelope, validate_entry_candidate_geometry

SELECTION_SCHEMA = "glitch.topstep.ensemble_selection.v1"
POOL_STATES = frozenset({"candidate", "held"})
ABSTENTION_STATES = frozenset({"no_edge", "held"})
EXCLUDED_STATES = frozenset(
    {
        "missing_required_evidence",
        "data_quality_insufficient",
        "timeout",
        "error",
        "invalid",
    }
)


def _tick_tol(rules: dict[str, Any], instrument: str, field: str) -> int:
    table = (rules.get("candidate_equivalence") or {}).get("tick_tolerance_by_instrument") or {}
    row = table.get(instrument) or table.get("DEFAULT") or {}
    return int(row.get(f"{field}_ticks") or 4)


def _within_ticks(a: float | None, b: float | None, *, ticks: int, tick_size: float) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= ticks * tick_size


def _entry_mid(row: dict[str, Any]) -> float | None:
    entry = row.get("entry")
    if isinstance(entry, (int, float)):
        return float(entry)
    entry_range = row.get("entry_range")
    if isinstance(entry_range, dict):
        low = entry_range.get("low")
        high = entry_range.get("high")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            return (float(low) + float(high)) / 2.0
    return None


def candidates_equivalent(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    rules: dict[str, Any],
    instrument: str,
    tick_size: float,
) -> bool:
    if str(a.get("direction") or "").lower() != str(b.get("direction") or "").lower():
        return False
    if str(a.get("instrument") or "") != str(b.get("instrument") or ""):
        return False
    if a.get("horizon_bars") != b.get("horizon_bars"):
        return False
    if not _within_ticks(_entry_mid(a), _entry_mid(b), ticks=_tick_tol(rules, instrument, "entry"), tick_size=tick_size):
        return False
    if not _within_ticks(a.get("stop"), b.get("stop"), ticks=_tick_tol(rules, instrument, "stop"), tick_size=tick_size):
        return False
    target_a = a.get("target")
    target_b = b.get("target")
    if target_a is not None and target_b is not None:
        if not _within_ticks(target_a, target_b, ticks=_tick_tol(rules, instrument, "target"), tick_size=tick_size):
            return False
    return True


def evidence_score(candidate: dict[str, Any], rules: dict[str, Any]) -> int:
    if candidate.get("evidence_score") is not None:
        return int(candidate["evidence_score"])
    score_cfg = rules.get("evidence_score") or {}
    score = 0
    completeness = candidate.get("completeness_used") or {}
    if isinstance(completeness, dict):
        for _src, status in completeness.items():
            if status == "available":
                score += int(score_cfg.get("required_source_available", 10))
            elif status == "partial":
                score += int(score_cfg.get("optional_source_available", 5))
            elif status == "missing_required":
                score += int(score_cfg.get("missing_required_penalty", -20))
            elif status in {"stale", "inconsistent"}:
                score += int(score_cfg.get("stale_or_inconsistent_penalty", -10))
    refs = candidate.get("evidence_refs") or []
    bonus = min(len(refs), int(score_cfg.get("evidence_ref_bonus_cap", 5)))
    score += bonus * int(score_cfg.get("evidence_ref_bonus_each", 1))
    return score


def warning_penalty(candidate: dict[str, Any], objections: list[dict[str, Any]]) -> int:
    explicit = candidate.get("warning_priority_penalty")
    if explicit is not None:
        return int(explicit)
    profile_id = str(candidate.get("profile_id") or "")
    total = 0
    for obj in objections:
        if str(obj.get("target_profile_id") or "") != profile_id:
            continue
        sev = str(obj.get("severity") or "").lower()
        if sev == "warning":
            total += 1
        elif sev == "info":
            total += 0
        # ponytail: downgraded critical (no objective rule) is audit-only for tiebreak;
        # see critical_normalization.no_objective_rule_match in aggregator_rules.v1.json
    return total


def _objective_geometry_codes(candidate: dict[str, Any], envelope: dict[str, Any]) -> list[str]:
    try:
        from ensemble_geometry import reference_price_from_envelope

        ref = reference_price_from_envelope(envelope)
    except ValueError:
        ref = 0.0
    entry_range = candidate.get("entry_range")
    return validate_entry_candidate_geometry(
        direction=str(candidate.get("direction") or ""),
        entry=candidate.get("entry") if isinstance(candidate.get("entry"), (int, float)) else None,
        entry_range=entry_range if isinstance(entry_range, dict) else None,
        stop=candidate.get("stop") if isinstance(candidate.get("stop"), (int, float)) else None,
        target=candidate.get("target") if isinstance(candidate.get("target"), (int, float)) else None,
        reference_price=ref,
    )


def _normalize_objections(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw:
        sev = str(row.get("severity") or "info").lower()
        objective = bool(row.get("objective_rule_match"))
        eliminates = sev == "critical" and objective
        out.append(
            {
                "objection_id": str(row.get("objection_id") or uuid.uuid4()),
                "target_profile_id": str(row.get("target_profile_id") or ""),
                "severity": sev,
                "risk_code": str(row.get("risk_code") or ""),
                "summary": str(row.get("summary") or row.get("risk_code") or ""),
                "evidence_refs": list(row.get("evidence_refs") or []),
                "eliminates_candidate": eliminates,
                "objective_rule_match": objective,
            }
        )
    return out


def _fixture_row_to_candidate(row: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """Convert aggregator fixture profile row to normalized_candidate shape."""
    return {
        "profile_id": row.get("profile_id"),
        "invocation_id": str(row.get("invocation_id") or uuid.uuid4()),
        "state": row.get("normalized_state") or row.get("state"),
        "comparability": row.get("comparability") or "comparable",
        "instrument": row.get("instrument") or envelope.get("instrument"),
        "direction": row.get("direction"),
        "entry": row.get("entry"),
        "entry_range": row.get("entry_range"),
        "stop": row.get("stop"),
        "target": row.get("target"),
        "horizon_bars": row.get("horizon_bars"),
        "evidence_score": row.get("evidence_score"),
        "warning_priority_penalty": row.get("warning_priority_penalty"),
        "error_code": row.get("error_code"),
        "envelope_hash": row.get("envelope_hash") or envelope.get("envelope_hash") or envelope.get("snapshot_hash"),
    }


def aggregate_envelope(
    *,
    run_id: str,
    envelope: dict[str, Any],
    candidates: list[dict[str, Any]],
    objections: list[dict[str, Any]] | None = None,
    rules: dict[str, Any],
    required_profile_ids: list[str] | None = None,
    process: dict[str, Any] | None = None,
    baseline_profile_id: str = "baseline-current",
) -> dict[str, Any]:
    """Deterministic aggregator — evaluation artifacts only."""
    process = process or {}
    objections_norm = _normalize_objections(objections or [])
    trace: list[str] = []
    instrument = str(envelope.get("instrument") or "MNQ")
    tick_size = tick_size_from_envelope(envelope)
    envelope_hash = str(envelope.get("envelope_hash") or envelope.get("snapshot_hash") or "")

    present_ids = {str(c.get("profile_id")) for c in candidates}
    missing = list(process.get("missing_profiles") or [])
    if required_profile_ids:
        missing.extend(pid for pid in required_profile_ids if pid not in present_ids)
    if missing:
        trace.append("PROFILE_MISSING")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="classified_failure",
            decision_code="PROFILE_MISSING",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    if process.get("ensemble_timeout") or process.get("budget_exhausted_before_final_candidates"):
        states = [str(c.get("state") or "") for c in candidates]
        if states and all(s == "timeout" for s in states):
            trace.append("ENSEMBLE_TIMEOUT")
            return _selection(
                run_id=run_id,
                envelope=envelope,
                rules=rules,
                outcome="classified_failure",
                decision_code="ENSEMBLE_TIMEOUT",
                failure_class="ensemble_timeout",
                trace=trace,
                candidates=candidates,
                objections=objections_norm,
            )

    if process.get("snapshot_divergence"):
        trace.append("SNAPSHOT_DIVERGENCE")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="classified_failure",
            decision_code="SNAPSHOT_DIVERGENCE",
            failure_class="snapshot_divergence",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    if process.get("version_incompatible"):
        trace.append("VERSION_INCOMPATIBLE")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="classified_failure",
            decision_code="VERSION_INCOMPATIBLE",
            failure_class="version_incompatible",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    by_profile = {str(c.get("profile_id")): c for c in candidates}
    categories: dict[str, str] = {}
    for pid, cand in by_profile.items():
        gate = {"comparable": cand.get("comparability") != "not_comparable"}
        categories[pid] = classify_candidate(cand, gate)

    for cand in candidates:
        eh = str(cand.get("envelope_hash") or "")
        if eh and envelope_hash and eh != envelope_hash:
            trace.append("SNAPSHOT_DIVERGENCE")
            return _selection(
                run_id=run_id,
                envelope=envelope,
                rules=rules,
                outcome="classified_failure",
                decision_code="SNAPSHOT_DIVERGENCE",
                failure_class="snapshot_divergence",
                trace=trace,
                candidates=candidates,
                objections=objections_norm,
            )

    pool: list[dict[str, Any]] = []
    abstainers = 0
    for cand in candidates:
        state = str(cand.get("state") or "")
        pid = str(cand.get("profile_id") or "")
        cat = categories.get(pid, "")
        if state in EXCLUDED_STATES or cat in {"missing_required_evidence", "timeout", "schema_invalid"}:
            if state == "missing_required_evidence" or cat == "missing_required_evidence":
                trace.append("MISSING_REQUIRED_EVIDENCE")
            if state in {"invalid", "error"} or cat == "schema_invalid":
                trace.append("SCHEMA_INVALID")
            continue
        if state == "no_edge" or cat == "no_edge":
            abstainers += 1
            trace.append(f"NO_EDGE:{pid}")
            continue
        if state in POOL_STATES and cat == "thesis_quality":
            pool.append(cand)
        else:
            trace.append(f"EXCLUDED:{pid}:{state}")

    if not pool and abstainers == len(candidates) and abstainers > 0:
        trace.append("ENSEMBLE_UNANIMOUS_ABSTENTION")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="ENSEMBLE_UNANIMOUS_ABSTENTION",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    if pool and abstainers > 0:
        trace.append("ENSEMBLE_CATEGORY_DIVERGENCE")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="ENSEMBLE_CATEGORY_DIVERGENCE",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    directions = {str(c.get("direction") or "").lower() for c in pool if c.get("direction")}
    longs = [c for c in pool if str(c.get("direction")).lower() == "long"]
    shorts = [c for c in pool if str(c.get("direction")).lower() == "short"]
    if longs and shorts:
        trace.append("DIRECTION_CONFLICT")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="DIRECTION_CONFLICT",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    eliminated: set[str] = set()
    for obj in objections_norm:
        target = str(obj.get("target_profile_id") or "")
        if not target:
            continue
        if obj.get("eliminates_candidate"):
            eliminated.add(target)
            trace.append(f"ADVERSARIAL_CRITICAL_OBJECTIVE:{target}")
        elif str(obj.get("severity")) == "critical" and not obj.get("objective_rule_match"):
            trace.append(f"ADVERSARIAL_CRITICAL_DOWNGRADED:{target}")

    for cand in list(pool):
        pid = str(cand.get("profile_id") or "")
        for obj in objections_norm:
            if str(obj.get("target_profile_id")) != pid:
                continue
            if obj.get("eliminates_candidate"):
                eliminated.add(pid)
        codes = _objective_geometry_codes(cand, envelope)
        for code in codes:
            if code in {"invalid_stop_geometry", "invalid_target_geometry", "identity_mismatch"}:
                eliminated.add(pid)
                trace.append(f"OBJECTIVE_ELIMINATION:{pid}:{code}")

    pool = [c for c in pool if str(c.get("profile_id")) not in eliminated]

    if len(pool) == 0:
        if eliminated:
            trace.append("ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION")
            return _selection(
                run_id=run_id,
                envelope=envelope,
                rules=rules,
                outcome="no_selection",
                decision_code="ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION",
                trace=trace,
                candidates=candidates,
                objections=objections_norm,
            )
        trace.append("INSUFFICIENT_ENSEMBLE_AGREEMENT")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="INSUFFICIENT_ENSEMBLE_AGREEMENT",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    if len(pool) == 1:
        trace.append("INSUFFICIENT_ENSEMBLE_AGREEMENT")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="INSUFFICIENT_ENSEMBLE_AGREEMENT",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    groups: list[list[dict[str, Any]]] = []
    for cand in pool:
        placed = False
        for group in groups:
            if candidates_equivalent(cand, group[0], rules=rules, instrument=instrument, tick_size=tick_size):
                group.append(cand)
                placed = True
                break
        if not placed:
            groups.append([cand])

    if len(groups) > 1:
        trace.append("DIRECTION_CONFLICT")
        return _selection(
            run_id=run_id,
            envelope=envelope,
            rules=rules,
            outcome="no_selection",
            decision_code="DIRECTION_CONFLICT",
            trace=trace,
            candidates=candidates,
            objections=objections_norm,
        )

    group = groups[0]

    def sort_key(cand: dict[str, Any]) -> tuple[int, int, str]:
        score = evidence_score(cand, rules)
        penalty = warning_penalty(cand, objections_norm)
        pid = str(cand.get("profile_id") or "")
        baseline_rank = 0 if pid == baseline_profile_id else 1
        return (-score, penalty, baseline_rank, pid)

    ranked = sorted(group, key=sort_key)
    winner = ranked[0]
    winner_score = evidence_score(winner, rules)
    runner_up = ranked[1] if len(ranked) > 1 else None
    decision_code = "EVIDENCE_SCORE_WIN"
    if runner_up and evidence_score(runner_up, rules) == winner_score:
        if warning_penalty(winner, objections_norm) == warning_penalty(runner_up, objections_norm):
            decision_code = "PREFER_BASELINE_ON_TIE"
        else:
            decision_code = "ADVERSARIAL_WARNING_PENALTY"
    if any(
        str(o.get("severity")) == "critical" and not o.get("objective_rule_match")
        for o in objections_norm
    ):
        decision_code = "ADVERSARIAL_CRITICAL_DOWNGRADED"

    trace.append(decision_code)
    return _selection(
        run_id=run_id,
        envelope=envelope,
        rules=rules,
        outcome="selected",
        decision_code=decision_code,
        selected_profile_id=str(winner.get("profile_id")),
        selected_candidate=winner,
        trace=trace,
        candidates=candidates,
        objections=objections_norm,
    )


def aggregate_fixture_case(case: dict[str, Any], *, rules: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
    inputs = case.get("inputs") or {}
    envelope = {
        "envelope_id": inputs.get("envelope_id"),
        "instrument": inputs.get("instrument"),
        "snapshot_hash": inputs.get("snapshot_hash"),
        "envelope_hash": inputs.get("snapshot_hash"),
        "contract": {"tick_size": 0.25},
        "packet": {"market": {"last": 100.0}, "contract": {"tick_size": 0.25}},
    }
    candidates = [_fixture_row_to_candidate(row, envelope) for row in inputs.get("profiles") or []]
    process = dict(inputs.get("process") or {})
    if inputs.get("missing_profiles"):
        process["missing_profiles"] = list(inputs["missing_profiles"])
    return aggregate_envelope(
        run_id=run_id or str(case.get("case_id") or uuid.uuid4()),
        envelope=envelope,
        candidates=candidates,
        objections=inputs.get("objections") or [],
        rules=rules,
        required_profile_ids=inputs.get("registry_required_profiles"),
        process=process,
    )


def _selection(
    *,
    run_id: str,
    envelope: dict[str, Any],
    rules: dict[str, Any],
    outcome: str,
    decision_code: str,
    trace: list[str],
    candidates: list[dict[str, Any]],
    objections: list[dict[str, Any]],
    selected_profile_id: str | None = None,
    selected_candidate: dict[str, Any] | None = None,
    failure_class: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SELECTION_SCHEMA,
        "run_id": run_id,
        "envelope_id": str(envelope.get("envelope_id") or ""),
        "envelope_hash": str(envelope.get("envelope_hash") or envelope.get("snapshot_hash") or ""),
        "aggregator_version": str(rules.get("rules_version") or ""),
        "outcome": outcome,
        "decision_code": decision_code,
        "selected_profile_id": selected_profile_id,
        "selected_candidate": (
            {
                "profile_id": selected_candidate.get("profile_id"),
                "invocation_id": selected_candidate.get("invocation_id"),
                "state": selected_candidate.get("state"),
            }
            if selected_candidate
            else None
        ),
        "candidates_considered": [str(c.get("profile_id")) for c in candidates],
        "candidates_preserved": candidates,
        "objections": objections,
        "decision_trace": trace,
        "failure_class": failure_class,
        "evaluation_only": True,
        "armed_promotion_allowed": False,
    }
