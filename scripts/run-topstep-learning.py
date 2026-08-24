"""Evidence-gated debrief, supervision, planning, and daily learning.

The worker consumes only canonical `glitch.topstep.trade_outcome.v1` records. It
never infers a completed trade from balances or position disappearance. Cognitive
overlays are proposed by default and activate only when the operator explicitly
enables automatic activation and the configured evidence threshold is met.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from model_owner_lock import acquire_model_owner, release_model_owner
from workflows.learning_evidence import (
    bounded_learning_rows,
    fit_debrief_evidence,
    outcome_is_reconciled_for_learning,
)
from workflows.learning_journal import (
    append_unique,
    canonical_outcomes,
    outcomes_path,
    reconcile_corrected_episodes,
    stable_id,
    upsert_unique,
)
from workflows.learning_loops import invoke_loop
from workflows.overlay_governance import (
    activate_cognitive_candidate,
    apply_cognitive_decision,
    persist_hourly,
    process_candidate,
)
from common import (
    PROFILE_NAME,
    configure_environment,
    gateway_feed_is_fresh,
    hermes_model_version_label,
    parse_utc,
    profile_root,
    read_jsonl,
    read_optional_json,
    bootstrap_profile_state,
    sync_gateway_execution_facts,
    utc_now,
    write_json_atomic,
)
from calibration_metrics import compute_session_metrics
from parity import (
    PROMPT_VERSION,
    classify_delivery_result,
    classify_gateway_rejection,
    compute_nothing_counterfactual,
    debrief_prompt_evidence,
    frame_for_packet_id,
    review_change_condition,
    suggest_flat_abstention_classification,
)


def learning_model(root: Path | None = None) -> str:
    return hermes_model_version_label(
        root or profile_root(),
        model_env="GLITCH_TOPSTEP_CORE_MODEL",
        fallback="gpt-5.6-luna",
    )


EASTERN = ZoneInfo("America/New_York")
GATEWAY_COGNITIVE_REJECTION_ERRORS = frozenset({
    "move_stop_unavailable",
})
MAX_DEBRIEF_OUTCOMES = 4


def is_gateway_cognitive_rejection(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    http_status = result.get("http_status")
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return True
    body = result.get("body")
    if not isinstance(body, dict):
        return False
    message = str(body.get("message") or body.get("error") or "")
    if message in GATEWAY_COGNITIVE_REJECTION_ERRORS:
        return True
    return str(body.get("status") or "").lower() in {"rejected", "invalid"}


def packet_is_flat(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    if not isinstance(account, dict):
        return True
    return int(account.get("instrument_open_contracts") or 0) == 0


def price_observation(frame: dict[str, Any]) -> dict[str, Any] | None:
    packet = frame.get("packet") if isinstance(frame.get("packet"), dict) else None
    if packet is None:
        return None
    market = packet.get("market")
    if not isinstance(market, dict):
        return None
    try:
        close = float(market["last"])
        high = float(market.get("high", close))
        low = float(market.get("low", close))
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "minute_id": frame.get("minute_id"),
        "close": close,
        "high": high,
        "low": low,
    }


def collect_decision_episodes(state_root: Path, supervisor: Path) -> list[dict[str, Any]]:
    output_path = supervisor / "decision-episodes.jsonl"
    existing = {str(row.get("intent_id")) for row in read_jsonl(output_path) if row.get("intent_id")}
    frames_root = state_root / "minute-frames"
    records: list[dict[str, Any]] = []
    seen_intents: set[str] = set()

    def enqueue(packet_id: str, intent: dict[str, Any]) -> None:
        nonlocal records
        receipt_path = state_root / "receipts" / f"{packet_id}.json"
        if not receipt_path.is_file():
            return
        receipt = read_optional_json(receipt_path)
        if not isinstance(receipt, dict):
            return
        if classify_delivery_result(
            receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        ) == "transport_uncertain":
            return
        intent_id = str(intent.get("intent_id") or receipt.get("intent_id") or "")
        if not intent_id or intent_id in existing or intent_id in seen_intents:
            return
        frame = frame_for_packet_id(frames_root, packet_id)
        if frame is None:
            return
        minute_id = str(frame.get("minute_id") or "")
        if not minute_id:
            return
        future_paths = [path for path in sorted(frames_root.glob("*.json")) if path.stem > minute_id][:5]
        if len(future_paths) < 5:
            return
        future: list[dict[str, Any]] = []
        for path in future_paths:
            observed = price_observation(read_optional_json(path) or {})
            if observed is None:
                future = []
                break
            future.append(observed)
        if len(future) < 5:
            return
        packet = frame.get("packet")
        if not isinstance(packet, dict):
            return
        action = str(intent.get("action") or "")
        flat_nothing = action == "NOTHING" and packet_is_flat(packet)
        relevant_failure = (
            action in {"ENTER_LONG", "ENTER_SHORT", "MOVE_STOP", "EXIT"}
            and is_gateway_cognitive_rejection(receipt.get("result"))
        )
        if not flat_nothing and not relevant_failure:
            return
        try:
            initial = float(packet["market"]["last"])
        except (KeyError, TypeError, ValueError):
            return
        forward_high = max(row["high"] for row in future)
        forward_low = min(row["low"] for row in future)
        account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
        contract = packet.get("contract") if isinstance(packet.get("contract"), dict) else {}
        delivery_result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        record: dict[str, Any] = {
            "schema_version": "glitch.topstep.decision_episode.v1",
            "episode_id": stable_id("decision-episode", intent_id),
            "recorded_utc": utc_now(),
            "intent_id": intent_id,
            "packet_id": packet_id,
            "decision_utc": intent.get("created_utc") or receipt.get("recorded_utc"),
            "account": intent.get("account") or account.get("name"),
            "instrument": intent.get("instrument") or contract.get("symbol"),
            "action": action,
            "reason": intent.get("reason"),
            "decision_audit": intent.get("decision_audit"),
            "pre_decision_state": {
                "position_contracts": account.get("instrument_open_contracts"),
                "initial_price": initial,
                "regime": packet.get("regime"),
            },
            "proposed_geometry": {
                key: intent.get(key)
                for key in (
                    "quantity", "stop_loss", "take_profit_1", "take_profit_2",
                    "quantity_tp1", "stop_loss_2", "take_profit_3", "quantity_tp2",
                    "stop_loss_3",
                )
                if key in intent
            },
            "delivery_result": delivery_result,
            "rejection_class": classify_gateway_rejection(delivery_result),
            "evidence_kind": "flat_nothing" if flat_nothing else "rejected_or_nonexecuted_intent",
            "forward_observation_count": len(future),
            "forward_observations": future,
            "forward_high": forward_high,
            "forward_low": forward_low,
            "forward_close": future[-1]["close"],
            "upward_excursion_points": forward_high - initial,
            "downward_excursion_points": initial - forward_low,
            "classification": None,
            "classification_hint": (
                suggest_flat_abstention_classification(
                    initial_price=initial,
                    forward_high=forward_high,
                    forward_low=forward_low,
                    forward_close=future[-1]["close"],
                )
                if flat_nothing
                else None
            ),
            "classification_owner": "hermes",
        }
        if flat_nothing:
            counterfactual = compute_nothing_counterfactual(
                {
                    "action": action,
                    "contract": contract,
                    "decision_audit": intent.get("decision_audit"),
                    "packet": packet,
                    "pre_decision_state": record["pre_decision_state"],
                },
                future,
            )
            record.update(
                counterfactual_classification=counterfactual["classification"],
                counterfactual_mfe_ticks=counterfactual["mfe_ticks"],
                counterfactual_mae_ticks=counterfactual["mae_ticks"],
            )
            next_frame = read_optional_json(future_paths[-1]) or {}
            if isinstance(next_frame, dict):
                subsequent = next(
                    (
                        row.get("intent")
                        for row in read_jsonl(state_root / "decisions.jsonl")
                        if isinstance(row.get("intent"), dict)
                        and str(row.get("packet_id") or "") > packet_id
                    ),
                    None,
                )
                if isinstance(subsequent, dict):
                    next_frame = dict(next_frame)
                    next_frame["subsequent_intent"] = subsequent
                record["change_condition_review"] = review_change_condition(
                    {**intent, "packet": packet},
                    next_frame,
                )
        records.append(record)
        seen_intents.add(intent_id)
        existing.add(intent_id)

    for row in read_jsonl(state_root / "decisions.jsonl"):
        packet_id = str(row.get("packet_id") or "")
        intent = row.get("intent")
        if packet_id and isinstance(intent, dict):
            enqueue(packet_id, intent)

    for outbox_path in sorted((state_root / "outbox").glob("*.json")):
        intent = read_optional_json(outbox_path)
        if isinstance(intent, dict):
            enqueue(outbox_path.stem, intent)

    append_unique(output_path, records, "episode_id")
    return read_jsonl(output_path)


def cognitive_evidence_ids(supervisor: Path) -> list[str]:
    rows = read_jsonl(supervisor / "trade-episodes.jsonl") + read_jsonl(supervisor / "decision-episodes.jsonl")
    rows.sort(key=lambda row: str(row.get("recorded_utc") or row.get("decision_utc") or ""))
    return [str(row.get("episode_id")) for row in rows if row.get("episode_id")]



def minutes_since(value: Any, now: datetime) -> float:
    try:
        return (now - parse_utc(value)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


def run_once(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    state_root = root / "state"
    supervisor = state_root / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    state_path = supervisor / "learning-state.json"
    state = read_optional_json(state_path) or {"schema_version": "glitch.topstep.learning_state.v1"}
    sync_meta = bootstrap_profile_state(state_root)
    execution_facts_meta = sync_gateway_execution_facts(state_root)
    outcome_file = outcomes_path(root)
    all_outcomes = canonical_outcomes(outcome_file)
    outcomes = [row for row in all_outcomes if row.get("learning_eligible") is True]
    episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
    if not args.dry_run:
        episodes = reconcile_corrected_episodes(supervisor / "trade-episodes.jsonl", all_outcomes)
    processed_revisions = {
        str(key): int(value)
        for key, value in (state.get("debriefed_outcome_revisions") or {}).items()
    }
    for row in episodes:
        outcome_id = str(row.get("outcome_id") or "")
        if outcome_id:
            processed_revisions[outcome_id] = max(
                processed_revisions.get(outcome_id, 0),
                int(row.get("outcome_revision") or 1),
            )
    for row in all_outcomes:
        if row.get("learning_eligible") is not True:
            processed_revisions[str(row["outcome_id"])] = max(
                processed_revisions.get(str(row["outcome_id"]), 0),
                int(row.get("_feed_revision") or 1),
            )
    pending = [
        row for row in outcomes
        if outcome_is_reconciled_for_learning(row)
        and int(row.get("_feed_revision") or 1) > processed_revisions.get(str(row.get("outcome_id")), 0)
    ]
    pending = sorted(pending, key=lambda row: str(row.get("exit_utc") or ""))[:MAX_DEBRIEF_OUTCOMES]
    quarantined = [
        row for row in outcomes
        if not outcome_is_reconciled_for_learning(row)
        and int(row.get("_feed_revision") or 1) > processed_revisions.get(str(row.get("outcome_id")), 0)
    ]
    now = datetime.now(timezone.utc)
    feed_fresh = gateway_feed_is_fresh()
    if feed_fresh and not args.dry_run:
        decision_episodes = collect_decision_episodes(state_root, supervisor)
    else:
        decision_episodes = read_jsonl(supervisor / "decision-episodes.jsonl")
    result: dict[str, Any] = {
        "feed_fresh": feed_fresh,
        "outcomes_synced": int(sync_meta.get("added") or 0),
        "outcomes_sync_http_status": sync_meta.get("http_status"),
        "outcome_feed_sequence": sync_meta.get("sequence"),
        "outcome_revisions_synced": int(sync_meta.get("revised") or 0),
        "execution_facts_synced": int(execution_facts_meta.get("added") or 0),
        "execution_facts_sequence": execution_facts_meta.get("sequence"),
        "debriefed": 0,
        "quarantined_unreconciled": len(quarantined),
        "hourly": False,
        "planning": False,
        "daily": False,
        "weekly": False,
    }

    if feed_fresh and pending and args.force_loop in {None, "debrief"}:
        if not args.dry_run:
            pending, factual_evidence = fit_debrief_evidence(state_root, pending, supervisor)
            ids = [stable_id("episode", str(row["outcome_id"])) for row in pending]
            records = invoke_loop(
                args,
                "debrief",
                debrief_prompt_evidence(factual_evidence),
                ids,
                supervisor,
            )
            for record, outcome in zip(records, pending):
                record["outcome_id"] = outcome["outcome_id"]
                record["intent_id"] = outcome["intent_id"]
                record["account"] = outcome["account"]
                record["instrument"] = outcome["instrument"]
                record["outcome_revision"] = int(outcome.get("_feed_revision") or 1)
                record["outcome_content_hash"] = str(outcome.get("_feed_content_hash") or "")
                record["prompt_version"] = PROMPT_VERSION
            upsert_unique(supervisor / "trade-episodes.jsonl", records, "episode_id")
            for row in pending:
                processed_revisions[str(row["outcome_id"])] = int(row.get("_feed_revision") or 1)
            state["debriefed_outcome_revisions"] = dict(sorted(processed_revisions.items()))
            state["debriefed_outcome_ids"] = sorted(processed_revisions)
        result["debriefed"] = len(pending)

    episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
    episode_ids = cognitive_evidence_ids(supervisor)
    supervision_trade_cursor = int(state.get("supervision_trade_count", max(0, len(episodes) - 12)))
    supervision_decision_cursor = int(
        state.get("supervision_decision_count", max(0, len(decision_episodes) - 24))
    )
    hourly_due = (
        (len(episodes) > supervision_trade_cursor or len(decision_episodes) > supervision_decision_cursor or int(sync_meta.get("revised") or 0) > 0)
        and minutes_since(state.get("last_hourly_utc"), now) >= 60
    )
    if feed_fresh and (hourly_due or args.force_loop == "hourly") and args.force_loop in {None, "hourly"}:
        review_id = stable_id("hourly", now.strftime("%Y%m%dT%H"))
        overlay = read_optional_json(supervisor / "active-cognitive-overlay.json")
        if overlay and overlay.get("status") not in {"active", "promoted"}:
            overlay = None
        if not args.dry_run:
            record = invoke_loop(
                args,
                "hourly",
                {
                    "trade_episodes": bounded_learning_rows(episodes[supervision_trade_cursor:], 12, 180_000),
                    "decision_episodes": bounded_learning_rows(
                        decision_episodes[supervision_decision_cursor:], 24, 220_000
                    ),
                    "active_cognitive_overlay": overlay,
                    "scope": {"kind": "supervision_delta", "since_utc": state.get("last_hourly_utc")},
                },
                [review_id],
                supervisor,
            )[0]
            persist_hourly(record, supervisor, episode_ids)
            state["last_hourly_utc"] = utc_now()
            state["supervision_trade_count"] = len(episodes)
            state["supervision_decision_count"] = len(decision_episodes)
        result["hourly"] = True

    reviews = read_jsonl(supervisor / "observations.jsonl") or read_jsonl(supervisor / "hourly-reviews.jsonl")
    planning_due = bool(reviews) and minutes_since(state.get("last_planning_utc"), now) >= 360 and int(state.get("planning_review_count", 0)) < len(reviews)
    if feed_fresh and (planning_due or args.force_loop == "planning") and args.force_loop in {None, "planning"}:
        plan_id = stable_id("plan", now.strftime("%Y%m%dT%H") + f":{now.minute // 5 * 5:02d}")
        if not args.dry_run:
            record = invoke_loop(
                args,
                "planning",
                {
                    "reviews": bounded_learning_rows(reviews, 6, 240_000),
                    "episodes": bounded_learning_rows(episodes, 24, 180_000),
                },
                [plan_id],
                supervisor,
            )[0]
            trade_count = len(episodes)
            record["trading_influence"] = "outcome_backed" if trade_count >= 2 else "observational"
            record["prompt_version"] = PROMPT_VERSION
            record["trade_episode_count"] = trade_count
            record["decision_episode_count"] = len(decision_episodes)
            append_unique(supervisor / "plans.jsonl", [record], "plan_id")
            write_json_atomic(supervisor / "current-plan.json", record)
            state["last_planning_utc"] = utc_now()
            state["planning_review_count"] = len(reviews)
        result["planning"] = True

    plans = read_jsonl(supervisor / "plans.jsonl")
    daily_due = (
        (not feed_fresh and (
            len(reviews) > int(state.get("daily_review_count", 0))
            or len(plans) > int(state.get("daily_plan_count", 0))
        ))
        or args.force_loop == "daily"
    )
    if daily_due and args.force_loop in {None, "daily"}:
        session_date = now.astimezone(EASTERN).date().isoformat()
        journal_id = stable_id("daily-distill", f"{len(reviews)}:{len(plans)}")
        if not args.dry_run:
            evidence = {
                "session_date_et": session_date,
                "scope": {
                    "kind": "maintenance_distillation",
                    "source": "supervision_summaries_plus_plans",
                    "through_utc": now.isoformat(),
                },
                "reviews": bounded_learning_rows(reviews, max_rows=12, max_chars=260_000),
                "plans": bounded_learning_rows(plans, max_rows=4, max_chars=260_000),
            }
            record = invoke_loop(args, "daily", evidence, [journal_id], supervisor)[0]
            append_unique(supervisor / "daily-journal.jsonl", [record], "journal_id")
            apply_cognitive_decision(record, supervisor, episode_ids)
            activate_cognitive_candidate(record, supervisor, episode_ids)
            process_candidate(record, supervisor, episode_ids)
            state["daily_review_count"] = len(reviews)
            state["daily_plan_count"] = len(plans)
        result["daily"] = True
        result["daily_distilled"] = True

    daily_journals = read_jsonl(supervisor / "daily-journal.jsonl")
    weekly_due = len(daily_journals) - int(state.get("weekly_daily_count", 0)) >= 7
    if args.force_loop == "weekly":
        weekly_due = True
    if weekly_due and args.force_loop in {None, "weekly"}:
        proposal_id = stable_id("weekly-skill-proposal", f"{len(daily_journals)}")
        if not args.dry_run:
            records = invoke_loop(
                args,
                "weekly",
                {
                    "scope": {"kind": "weekly_distillation", "daily_journal_count": len(daily_journals)},
                    "daily_journals": bounded_learning_rows(daily_journals[-7:], 7, 260_000),
                    "recent_plans": bounded_learning_rows(plans[-4:], 4, 160_000),
                    "calibration_metrics": compute_session_metrics(state_root),
                },
                [proposal_id],
                supervisor,
            )
            append_unique(supervisor / "weekly-skill-proposals.jsonl", records, "skill_proposal_id")
            state["weekly_daily_count"] = len(daily_journals)
        result["weekly"] = True

    if not args.dry_run:
        state["updated_utc"] = utc_now()
        write_json_atomic(state_path, state)
    result["canonical_outcomes"] = len(outcomes)
    result["episodes"] = len(episodes)
    result["decision_episodes"] = len(decision_episodes)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=PROFILE_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-loop", choices=("debrief", "hourly", "planning", "daily", "weekly"))
    args = parser.parse_args()
    root = configure_environment()
    state = root / "state"
    supervisor = state / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    run_id = stable_id("learning-run", utc_now())
    started_utc = utc_now()
    if not acquire_model_owner(state, owner_kind="learning", invocation_id=run_id):
        write_json_atomic(supervisor / "learning-worker-status.json", {
            "schema_version": "glitch.topstep.learning_worker_status.v2",
            "run_id": run_id,
            "recorded_utc": utc_now(),
            "status": "preempted",
            "phase": "lock_admission",
            "retryable": True,
        })
        return 0
    write_json_atomic(supervisor / "learning-worker-status.json", {
        "schema_version": "glitch.topstep.learning_worker_status.v2",
        "run_id": run_id,
        "started_utc": started_utc,
        "recorded_utc": utc_now(),
        "status": "running",
        "phase": "admission",
        "retryable": False,
    })
    try:
        try:
            result = run_once(args, root)
        except Exception as error:
            failure = {
                "schema_version": "glitch.topstep.learning_worker_status.v2",
                "run_id": run_id,
                "started_utc": started_utc,
                "recorded_utc": utc_now(),
                "status": "failed",
                "phase": "learning",
                "retryable": isinstance(error, (OSError, TimeoutError)),
                "error": f"{type(error).__name__}:{error}"[:500],
            }
            write_json_atomic(supervisor / "learning-worker-status.json", failure)
            print(json.dumps(failure, separators=(",", ":")), file=sys.stderr)
            return 1
        write_json_atomic(supervisor / "learning-worker-status.json", {
            "schema_version": "glitch.topstep.learning_worker_status.v2",
            "run_id": run_id,
            "started_utc": started_utc,
            "completed_utc": utc_now(),
            "recorded_utc": utc_now(),
            "status": "ok",
            "phase": "completed",
            "retryable": False,
            "result": result,
        })
        print(json.dumps(result, separators=(",", ":")))
        return 0
    finally:
        release_model_owner(state, owner_kind="learning", invocation_id=run_id)


if __name__ == "__main__":
    raise SystemExit(main())

# ponytail: tests import runner module symbols directly after workflow extraction
from workflows.learning_journal import valid_outcomes  # noqa: E402
from workflows.learning_loops import (  # noqa: E402
    LOOP_SCHEMAS,
    output_template,
    prompt_for,
    validate_output,
)
from workflows.overlay_governance import promotion_gate_allows_proposal  # noqa: E402
