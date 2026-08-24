"""Learning loop schemas, prompts, and Hermes invocation (audit C1)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from common import read_optional_json, utc_now
from workflows.hermes_invoker import invoke_learning_hermes

EASTERN = ZoneInfo("America/New_York")

LOOP_SCHEMAS = {
    "debrief": "glitch.topstep.trade_episode.v1",
    "hourly": "glitch.topstep.hourly_review.v1",
    "planning": "glitch.topstep.portfolio_plan.v1",
    "daily": "glitch.topstep.daily_journal.v1",
    "weekly": "glitch.topstep.weekly_skill_proposal.v1",
}


def output_template(loop_id: str, record_ids: list[str]) -> dict[str, Any]:
    records = []
    for record_id in record_ids:
        if loop_id == "debrief":
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "episode_id": record_id,
                "recorded_utc": utc_now(),
                "outcome_id": "COPY_FROM_EVIDENCE",
                "intent_id": "COPY_FROM_EVIDENCE",
                "account": "COPY_FROM_EVIDENCE",
                "instrument": "COPY_FROM_EVIDENCE",
                "entry_assessment": "REPLACE",
                "exit_assessment": "REPLACE",
                "risk_assessment": "REPLACE",
                "what_went_well": ["REPLACE"],
                "what_went_wrong": ["REPLACE"],
                "lesson_candidates": ["REPLACE"],
                "uncertainties": ["REPLACE"],
            })
        elif loop_id == "hourly":
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "review_id": record_id,
                "recorded_utc": utc_now(),
                "working": ["REPLACE"],
                "failing": ["REPLACE"],
                "unknown": ["REPLACE"],
                "repeated_patterns": ["REPLACE"],
                "system_findings": ["REPLACE"],
                "guidance": {"summary": "REPLACE", "consider": ["REPLACE"], "avoid": ["REPLACE"]},
                "decision_episode_classifications": [{
                    "episode_id": "COPY_FROM_EVIDENCE",
                    "classification": "justified_abstention|avoided_adverse_movement|missed_directional_participation|ambiguous",
                    "counterfactual_summary": "REPLACE",
                    "change_condition_review": "met|reassessed|threshold_moved|not_applicable",
                }],
                "cognitive_change_candidate": {
                    "propose": False,
                    "candidate_id": "",
                    "target": "core_prompt",
                    "instruction": "",
                    "evidence_episode_ids": [],
                    "expected_effect": "",
                    "evaluation_metric": "",
                    "rollback_condition": "",
                },
            })
        elif loop_id == "planning":
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "plan_id": record_id,
                "recorded_utc": utc_now(),
                "horizon_minutes": 360,
                "regime_posture": "REPLACE",
                "objectives": ["REPLACE"],
                "risk_guidance": "REPLACE",
                "geometry_guidance": "REPLACE",
                "management_guidance": "REPLACE",
                "experiments": ["REPLACE"],
                "preservation_conditions": ["REPLACE"],
                "revision_triggers": ["REPLACE"],
            })
        elif loop_id == "daily":
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "journal_id": record_id,
                "recorded_utc": utc_now(),
                "session_date_et": datetime.now(EASTERN).date().isoformat(),
                "net_performance": "REPLACE",
                "survival_and_rule_compliance": "REPLACE",
                "what_worked": ["REPLACE"],
                "what_failed": ["REPLACE"],
                "durable_memory_updates": [],
                "tomorrow_questions": ["REPLACE"],
                "cognitive_change_candidate": {
                    "propose": False,
                    "candidate_id": "",
                    "target": "core_prompt",
                    "instruction": "",
                    "evidence_episode_ids": [],
                    "expected_effect": "",
                    "evaluation_metric": "",
                    "rollback_condition": "",
                },
            })
        else:
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "skill_proposal_id": record_id,
                "recorded_utc": utc_now(),
                "proposal_summary": "REPLACE",
                "skill_candidates": [{
                    "skill_name": "REPLACE",
                    "instruction": "REPLACE",
                    "evidence_journal_ids": ["REPLACE"],
                    "expected_effect": "REPLACE",
                    "evaluation_metric": "REPLACE",
                    "rollback_condition": "REPLACE",
                }],
                "uncertainties": ["REPLACE"],
            })
    return {
        "schema_version": "glitch.topstep.learning_output.v1",
        "loop_id": loop_id,
        "records": records,
    }


def prompt_for(loop_id: str, evidence: Any, template: dict[str, Any], continuity: dict[str, Any]) -> str:
    instructions = {
        "debrief": (
            "Produce one honest debrief per canonical completed outcome. Reconstruct decision quality, stop-aware risk, "
            "execution, fees, account-buffer impact, payout-state impact when supplied, and plausible alternatives. Each "
            "evidence row includes facts and facts_sha256; treat the hash as the audit anchor and do not invent facts "
            "beyond the supplied facts block. A provider or gateway defect is a system finding, not a trading lesson."
        ),
        "hourly": (
            "Supervise recent trade and decision episodes. For each flat NOTHING, preserve the "
            "developing movement, favorable participation condition, invalidation, and later observed "
            "path. Classify matured flat abstentions as justified_abstention, avoided_adverse_movement, "
            "missed_directional_participation, or ambiguous by comparing the declared forecast and "
            "change_condition with the observed path. Label the actual outcome no trade and every "
            "counterfactual informational only; never invent counterfactual fills, geometry, or PnL. "
            "Independently reconstruct the nearest setup-specific invalidation that survives ordinary "
            "noise; do not inherit a remote invalidation, consumed objective, or acceptance/retest "
            "prerequisite merely because the rejected rationale used it. Ordinary partial bars, stale "
            "depth, or incomplete flow are uncertainty costs, not proof that abstention was disciplined. "
            "When supplied evidence includes daily_economics mirrors, note band position and stage-appropriate "
            "preservation or eval-target context without creating entry pressure or automatic stop rules. "
            "For each prior change_condition, record met, reassessed, threshold_moved, or not_applicable. "
            "Separate repeated cognitive errors from venue, policy, transport, or execution defects. "
            "Propose at most one compact cognitive change only when multiple comparable episodes across "
            "at least two sessions support it, with contradiction-reviewed IDs and a declared metric. "
            "Decision episodes may improve questions and attention, but must not create entry pressure, "
            "anti-abstention pressure, or quantity pressure."
        ),
        "planning": (
            "Create a six-hour advisory plan. Preserve deterministic risk and gateway authority. Do not create entry "
            "gates, fixed quantities, daily profit quotas, or instructions that bypass current packets. "
            "When daily_economics mirrors are available in current packets, you may name a daily intent band "
            "(for example preserve upper-band gains on approved accounts) and stop-trading questions — not quotas. "
            "Use completed decision episodes to question habitual abstention and rejected geometry while preserving "
            "uncertainty; decision-only findings are observational and cannot pressure entries or size."
        ),
        "daily": (
            "Distill the supplied supervision summaries and plans into a compact maintenance learning journal. Do not "
            "reconstruct a whole trading session or consume raw market packets. Evaluate survival, rule compliance, "
            "evidence quality, and when mirrors were present whether band position supported good day-level sizing. "
            "Write durable native memory only for repeated attributable lessons; current account "
            "state is never memory."
        ),
        "weekly": (
            "Distill only the supplied daily journals into compact proposal-only skill language. Preserve contradictions "
            "and uncertainty; do not infer new trading rules from a single outcome. Each skill proposal must include "
            "evidence IDs, expected effect, evaluation metric, and rollback condition. Do not activate skills in this loop."
        ),
    }[loop_id]
    memory = "Retrieve relevant durable memory exactly once. Do not write memory in this loop. "
    return (
        "Apply the Glitch Topstep SOUL and loaded learning skills. Canonical outcome records and gateway evidence outrank "
        "memory and interpretation. Optimize long-run net payouts, survival, and rule compliance; never manufacture a "
        "daily target. " + memory + instructions + " Return exactly the required_output_template shape as one strict "
        "JSON object with no markdown or prose. Preserve every supplied ID. CURRENT_LEARNING_CYCLE="
        + json.dumps({
            "loop_id": loop_id,
            "evidence": evidence,
            "continuity": continuity,
            "required_output_template": template,
        }, separators=(",", ":"), ensure_ascii=False)
    )


def validate_output(value: dict[str, Any], loop_id: str, expected_ids: list[str]) -> list[dict[str, Any]]:
    if value.get("schema_version") != "glitch.topstep.learning_output.v1" or value.get("loop_id") != loop_id:
        raise ValueError("learning_output_envelope_invalid")
    records = value.get("records")
    if not isinstance(records, list) or len(records) != len(expected_ids):
        raise ValueError("learning_output_record_count_invalid")
    id_field = {
        "debrief": "episode_id",
        "hourly": "review_id",
        "planning": "plan_id",
        "daily": "journal_id",
        "weekly": "skill_proposal_id",
    }[loop_id]
    ids = [str(record.get(id_field) or "") for record in records if isinstance(record, dict)]
    if ids != expected_ids:
        raise ValueError("learning_output_identity_mismatch")
    if any(record.get("schema_version") != LOOP_SCHEMAS[loop_id] for record in records):
        raise ValueError("learning_output_schema_invalid")
    return records


def invoke_loop(
    args: argparse.Namespace,
    loop_id: str,
    evidence: Any,
    ids: list[str],
    supervisor: Path,
) -> list[dict[str, Any]]:
    from workflows.learning_evidence import MAX_PROMPT_CHARS, overlay_context

    template = output_template(loop_id, ids)
    skills = {
        "debrief": "topstep-review-outcomes,topstep-self-learning,topstep-learning-loop",
        "hourly": "topstep-review-outcomes,topstep-self-learning,topstep-self-heal,topstep-supervisor-ledger,topstep-learning-loop",
        "planning": "topstep-self-learning,topstep-supervisor-ledger,topstep-learning-loop",
        "daily": "topstep-review-outcomes,topstep-self-learning,topstep-supervisor-ledger,topstep-learning-loop",
        "weekly": "topstep-self-learning,topstep-supervisor-ledger,topstep-learning-loop",
    }[loop_id]
    continuity = overlay_context(supervisor)
    prompt = prompt_for(loop_id, evidence, template, continuity)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"learning_prompt_too_large:{loop_id}:{len(prompt)}")
    try:
        value = invoke_learning_hermes(args.profile, prompt, skills, args.timeout_seconds)
        return validate_output(value, loop_id, ids)
    except (json.JSONDecodeError, ValueError) as error:
        repair_prompt = (
            prompt
            + "\nThe previous response failed strict validation with: "
            + f"{type(error).__name__}:{error}"[:300]
            + ". Re-answer the same evidence once using exactly required_output_template. "
            + "Return one complete JSON object only; do not explain the repair."
        )
        if len(repair_prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"learning_repair_prompt_too_large:{loop_id}:{len(repair_prompt)}")
        value = invoke_learning_hermes(args.profile, repair_prompt, skills, args.timeout_seconds)
        return validate_output(value, loop_id, ids)
