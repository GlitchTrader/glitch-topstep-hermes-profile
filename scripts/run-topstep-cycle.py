"""Deterministic Glitch Topstep operator worker.

The worker fetches one authenticated gateway packet, maintains a bounded five-frame
path, invokes one isolated Hermes decision only when due, validates the returned
`glitch.intent.v2` object, persists an outbox, and posts the intent to the local
Glitch Topstep gateway. ProjectX credentials never enter this process.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    PROFILE_NAME,
    append_jsonl,
    configure_environment,
    extract_single_json_object,
    local_token,
    parse_utc,
    prune_files,
    read_json,
    read_optional_json,
    request_json,
    tail_jsonl,
    utc_now,
    write_json_atomic,
    windows_hidden_subprocess_flags,
)
from telegram_notify import maybe_notify_telegram, notify_new_trade_outcomes
from reconcile_topstep_outcomes import reconcile_outcomes

CORE_MODEL_DEFAULT = "nvidia/nemotron-3-ultra-550b-a55b:free"
CORE_PROVIDER_DEFAULT = "openrouter"


def core_model() -> str:
    return os.environ.get("GLITCH_TOPSTEP_CORE_MODEL", CORE_MODEL_DEFAULT)


def core_provider() -> str:
    return os.environ.get("GLITCH_TOPSTEP_CORE_PROVIDER", CORE_PROVIDER_DEFAULT)


TRADING_SOURCE = "trading"
PROMPT_VERSION = "glitch-topstep-v2"
ALLOWED_ACTIONS = {"ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT", "NOTHING", "MOVE_STOP"}
AUDIT_FIELDS = {
    "bull_case", "bear_case", "flat_case", "aggressive_case", "conservative_case",
    "decisive_evidence", "disconfirming_evidence", "change_condition", "final_choice",
}
CORE_FIELDS = {
    "schema_version", "intent_id", "created_utc", "instrument", "account",
    "operator_profile", "action", "confidence", "snapshot_hash", "model_version",
    "prompt_version", "reason", "decision_audit",
}
ENTRY_FIELDS = {"quantity", "order_type", "stop_loss", "take_profit_1"}


def state_root(profile_root: Path) -> Path:
    return profile_root / "state"


def packet_max_age_seconds() -> int:
    try:
        return max(1, int(os.environ.get("GLITCH_TOPSTEP_PACKET_MAX_AGE_SECONDS", "90")))
    except ValueError:
        return 90


def frame_retention() -> int:
    try:
        return max(decision_frame_count(), int(os.environ.get("GLITCH_TOPSTEP_FRAME_RETENTION", "180")))
    except ValueError:
        return max(decision_frame_count(), 180)


def decision_frame_count() -> int:
    try:
        return max(1, int(os.environ.get("GLITCH_TOPSTEP_DECISION_FRAME_COUNT", "5")))
    except ValueError:
        return 5


def packet_is_current(packet: dict[str, Any], now: datetime | None = None) -> bool:
    try:
        created = parse_utc(packet["created_utc"])
    except (KeyError, TypeError, ValueError):
        return False
    current = now or datetime.now(timezone.utc)
    age = (current - created).total_seconds()
    return -5 <= age <= packet_max_age_seconds()


def available_actions(packet: dict[str, Any]) -> set[str]:
    if positioned(packet):
        actions = {"HOLD", "EXIT"}
        if packet.get("execution", {}).get("move_stop_available"):
            actions.add("MOVE_STOP")
        return actions
    actions = {"NOTHING"}
    if entry_eligible(packet):
        actions.update({"ENTER_LONG", "ENTER_SHORT"})
    return actions


def positioned(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    return isinstance(account, dict) and int(account.get("instrument_open_contracts") or 0) != 0


def entry_eligible(packet: dict[str, Any]) -> bool:
    execution = packet.get("execution")
    if not isinstance(execution, dict):
        return False
    quantities = execution.get("valid_entry_quantities")
    return execution.get("entry_actions_enabled") is True and isinstance(quantities, list) and bool(quantities)


def packet_minute(packet: dict[str, Any]) -> int:
    return parse_utc(packet["created_utc"]).minute


def should_invoke(packet: dict[str, Any], directive: dict[str, Any] | None = None) -> bool:
    if directive is not None:
        return True
    if positioned(packet):
        return True
    return entry_eligible(packet) and packet_minute(packet) % 5 == 0


def capture_frame(packet: dict[str, Any], root: Path) -> Path:
    created = parse_utc(packet["created_utc"])
    minute_id = created.strftime("%Y%m%dT%H%MZ")
    path = root / "minute-frames" / f"{minute_id}.json"
    write_json_atomic(path, {
        "schema_version": "glitch.topstep.minute_frame.v1",
        "minute_id": minute_id,
        "captured_utc": utc_now(),
        "packet": packet,
    })
    prune_files((root / "minute-frames").glob("*.json"), frame_retention())
    return path


def recent_frames(root: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is None:
        limit = decision_frame_count()
    values = []
    for path in sorted((root / "minute-frames").glob("*.json"))[-limit:]:
        value = read_optional_json(path)
        if value:
            values.append(value)
    return values


def packet_for_model(packet: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(packet)
    account = value.get("account")
    if isinstance(account, dict):
        account.pop("id", None)
    contract = value.get("contract")
    if isinstance(contract, dict):
        contract.pop("id", None)
        contract.pop("symbol_id", None)
    template = value.get("required_output_template")
    if isinstance(template, dict):
        template["operator_profile"] = PROFILE_NAME
        template["model_version"] = core_model()
        template["prompt_version"] = PROMPT_VERSION
    return value


def read_directive(root: Path) -> dict[str, Any] | None:
    path = root / "operator-directive.json"
    value = read_optional_json(path)
    if not value or value.get("schema_version") != "glitch.topstep.operator_directive.v1":
        return None
    if value.get("status") != "pending":
        return None
    try:
        expiry = parse_utc(value.get("expires_utc"))
    except (TypeError, ValueError):
        return None
    if datetime.now(timezone.utc) >= expiry:
        expired = dict(value)
        expired["status"] = "expired"
        expired["expired_utc"] = utc_now()
        write_json_atomic(path, expired)
        return None
    return value


def consume_directive(root: Path, directive: dict[str, Any], packet_id: str) -> None:
    path = root / "operator-directive.json"
    current = read_optional_json(path)
    if not current or current.get("directive_id") != directive.get("directive_id") or current.get("status") != "pending":
        return
    current["status"] = "consumed"
    current["consumed_utc"] = utc_now()
    current["packet_id"] = packet_id
    write_json_atomic(path, current)


def recent_context(root: Path) -> dict[str, Any]:
    supervisor = root / "supervisor"
    return {
        "decisions": tail_jsonl(root / "decisions.jsonl", 6),
        "receipts": tail_jsonl(root / "receipts.jsonl", 6),
        "outcomes": tail_jsonl(root / "outcomes.jsonl", 6),
        "current_plan": read_optional_json(supervisor / "current-plan.json"),
        "current_guidance": read_optional_json(supervisor / "current-guidance.json"),
        "active_cognitive_overlay": read_optional_json(supervisor / "active-cognitive-overlay.json"),
    }


def build_prompt(
    packet: dict[str, Any],
    frames: list[dict[str, Any]],
    context: dict[str, Any],
    directive: dict[str, Any] | None,
) -> str:
    model_packet = packet_for_model(packet)
    template = copy.deepcopy(model_packet.get("required_output_template") or {})
    default_action = "HOLD" if positioned(packet) else "NOTHING"
    template.update({
        "schema_version": "glitch.intent.v2",
        "intent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch-topstep:{packet['packet_id']}")),
        "created_utc": utc_now(),
        "operator_profile": PROFILE_NAME,
        "action": default_action,
        "model_version": core_model(),
        "prompt_version": PROMPT_VERSION,
    })
    audit = template.get("decision_audit")
    if not isinstance(audit, dict):
        audit = {}
        template["decision_audit"] = audit
    for field in AUDIT_FIELDS:
        audit.setdefault(field, default_action if field == "final_choice" else "Replace")
    envelope = {
        "decision_packet": model_packet,
        "recent_frames": [packet_for_model(frame.get("packet", {})) for frame in frames],
        "recent_glitch_ledger": context,
        "operator_directive": directive,
        "required_output_template": template,
        "current_capabilities": {
            "available_actions": sorted(available_actions(packet)),
            "move_stop_available": bool(packet.get("execution", {}).get("move_stop_available")),
            "move_tp_available": False,
            "single_account": True,
            "single_contract": True,
        },
    }
    return (
        "Apply the Glitch Topstep SOUL and loaded skills to CURRENT_CYCLE. The authenticated current gateway packet "
        "outranks memory, plans, prior decisions, and interpretation. ProjectX numeric identifiers and credentials are "
        "deliberately absent and must never be requested or invented. Use the recent frame path for short-horizon market "
        "context. When flat, forecast the most likely next five minutes. When positioned, choose HOLD or EXIT from the "
        "Use decision_packet.market.bars_1m, market.features, market.levels, market.correlation, "
        "execution.setup_candidates, position_state, protection, reconciliation, and policy fields. "
        "Prefer setup_candidates when flat; do not invent levels or indicators beyond supplied data. "
        "most likely next one-minute path; MOVE_TP is unavailable. MOVE_STOP is allowed only when "
        "execution.move_stop_available=true and requires stop_loss only. Entries require "
        "absolute structural stop and target prices and a quantity from decision_packet.execution.valid_entry_quantities. "
        "The deterministic allowed_risk_usd and current_buffer are hard context, not suggestions. Optimize long-run net "
        "payouts and survival without a daily profit quota. Return exactly one strict glitch.intent.v2 JSON object, no "
        "markdown, prose, tool calls, or trailing text. Preserve account, instrument, snapshot_hash, and operator_profile "
        "exactly. decision_audit must contain exactly bull_case, bear_case, flat_case, aggressive_case, conservative_case, "
        "decisive_evidence, disconfirming_evidence, change_condition, and final_choice; final_choice must equal action. "
        "For HOLD, EXIT, and NOTHING omit quantity, order_type, stop_loss, and take_profit_1. For entries use MARKET and "
        "include all four entry fields. Before deciding, retrieve relevant durable Glitch Topstep lessons exactly once "
        "through native memory, then return JSON without writing memory. CURRENT_CYCLE="
        + json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
    )


def invoke_hermes(profile: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    python_executable = Path(executable).with_name("python.exe" if sys.platform == "win32" else "python")
    if not python_executable.is_file():
        python_executable = Path(sys.executable)
    cli_args = [
        "chat", "-Q",
        "--source", TRADING_SOURCE,
        "--model", core_model(),
        "--provider", core_provider(),
        "--max-turns", "4",
        "--skills", "topstep-observe-market,topstep-assess-risk,topstep-form-thesis,topstep-build-intent,topstep-self-learning",
        "--toolsets", "memory",
    ]
    wrapper = (
        "import os,sys;from pathlib import Path;"
        "os.environ['HERMES_HOME']=str(Path.home()/'AppData'/'Local'/'hermes'/'profiles'/"
        + repr(profile)
        + ");from hermes_cli.main import main;prompt=sys.stdin.read();"
        "sys.argv=[sys.argv[0]]+" + repr(cli_args) + "+['-q',prompt];main()"
    )
    completed = subprocess.run(
        [str(python_executable), "-c", wrapper],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        creationflags=windows_hidden_subprocess_flags(),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"hermes_failed:{completed.returncode}:{completed.stderr.strip()[:400]}")
    return extract_single_json_object(completed.stdout, schema="glitch.intent.v2")


def normalize_intent(value: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    intent = copy.deepcopy(value)
    action = "NOTHING" if intent.get("action") == "NO_ACTION" else intent.get("action")
    intent["schema_version"] = "glitch.intent.v2"
    intent["intent_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch-topstep:{packet['packet_id']}"))
    intent["created_utc"] = utc_now()
    intent["instrument"] = packet["instrument"]
    intent["account"] = packet["account"]["name"]
    intent["operator_profile"] = PROFILE_NAME
    intent["snapshot_hash"] = packet["market"]["snapshot_hash"]
    intent["model_version"] = core_model()
    intent["prompt_version"] = PROMPT_VERSION
    intent["action"] = action
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        pass
    elif action == "MOVE_STOP":
        for field in ("quantity", "order_type", "take_profit_1"):
            intent.pop(field, None)
    else:
        for field in ENTRY_FIELDS:
            intent.pop(field, None)
    return intent


def _number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"invalid_number:{field}")
    return float(value)


def validate_intent(
    intent: dict[str, Any],
    packet: dict[str, Any],
    directive: dict[str, Any] | None = None,
) -> None:
    action = intent.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("unsupported_action")
    if action not in available_actions(packet):
        raise ValueError("action_not_available")
    expected_fields = CORE_FIELDS | (
        ENTRY_FIELDS if action in {"ENTER_LONG", "ENTER_SHORT"} else (
            {"stop_loss"} if action == "MOVE_STOP" else set()
        )
    )
    unknown = set(intent).difference(expected_fields)
    missing = expected_fields.difference(intent)
    if unknown:
        raise ValueError("unknown_fields:" + ",".join(sorted(unknown)))
    if missing:
        raise ValueError("missing_fields:" + ",".join(sorted(missing)))
    if intent.get("schema_version") != "glitch.intent.v2":
        raise ValueError("schema_version_invalid")
    if intent.get("instrument") != packet.get("instrument"):
        raise ValueError("instrument_mismatch")
    if intent.get("account") != packet.get("account", {}).get("name"):
        raise ValueError("account_mismatch")
    if intent.get("operator_profile") != PROFILE_NAME:
        raise ValueError("operator_profile_mismatch")
    if intent.get("snapshot_hash") != packet.get("market", {}).get("snapshot_hash"):
        raise ValueError("snapshot_hash_mismatch")
    if not isinstance(intent.get("reason"), str) or not intent["reason"].strip():
        raise ValueError("reason_invalid")
    confidence = _number(intent.get("confidence"), "confidence")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence_out_of_range")
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict) or set(audit) != AUDIT_FIELDS:
        raise ValueError("decision_audit_invalid")
    if any(not isinstance(audit[field], str) or not audit[field].strip() for field in AUDIT_FIELDS):
        raise ValueError("decision_audit_value_invalid")
    if audit.get("final_choice") != action:
        raise ValueError("decision_audit_choice_mismatch")
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        if positioned(packet):
            raise ValueError("positioned_entry_not_supported")
        if not entry_eligible(packet):
            raise ValueError("entry_not_eligible")
        quantity = intent.get("quantity")
        valid_quantities = packet.get("execution", {}).get("valid_entry_quantities", [])
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity not in valid_quantities:
            raise ValueError("entry_quantity_invalid")
        if intent.get("order_type") != "MARKET":
            raise ValueError("entry_order_type_invalid")
        stop = _number(intent.get("stop_loss"), "stop_loss")
        target = _number(intent.get("take_profit_1"), "take_profit_1")
        market = packet.get("market", {})
        reference = market.get("ask") if action == "ENTER_LONG" else market.get("bid")
        if not isinstance(reference, (int, float)) or reference <= 0:
            reference = market.get("last")
        reference = _number(reference, "reference_price")
        if action == "ENTER_LONG" and not (stop < reference < target):
            raise ValueError("long_geometry_invalid")
        if action == "ENTER_SHORT" and not (target < reference < stop):
            raise ValueError("short_geometry_invalid")
    elif action == "MOVE_STOP":
        stop = _number(intent.get("stop_loss"), "stop_loss")
        current_stop = packet.get("protection", {}).get("stop_price")
        side = packet.get("position_state", {}).get("side")
        if not isinstance(current_stop, (int, float)):
            raise ValueError("move_stop_current_unknown")
        if side == "long" and stop <= current_stop:
            raise ValueError("move_stop_must_tighten_long")
        if side == "short" and stop >= current_stop:
            raise ValueError("move_stop_must_tighten_short")
    elif any(field in intent for field in ENTRY_FIELDS):
        raise ValueError("non_entry_contains_entry_fields")
    if directive and directive.get("directive_type") == "forced_entry":
        expected = "ENTER_LONG" if directive.get("bias") == "long" else "ENTER_SHORT"
        if action != expected:
            raise ValueError("forced_entry_not_honored")


def invoke_valid_intent(
    profile: str,
    prompt: str,
    packet: dict[str, Any],
    directive: dict[str, Any] | None,
    timeout_seconds: int,
) -> tuple[dict[str, Any], int]:
    current_prompt = prompt
    for repair_count in range(2):
        try:
            value = invoke_hermes(profile, current_prompt, timeout_seconds)
            intent = normalize_intent(value, packet)
            validate_intent(intent, packet, directive)
            return intent, repair_count
        except ValueError as error:
            if repair_count:
                raise
            current_prompt += "\nSTRICT_OUTPUT_CORRECTION=" + json.dumps({
                "validation_error": str(error)[:240],
                "instruction": "Regenerate the same current decision as one complete strict glitch.intent.v2 object. Preserve current account, instrument, snapshot, and requested forced direction.",
            }, separators=(",", ":"))
    raise AssertionError("unreachable")


def post_intent(intent: dict[str, Any]) -> dict[str, Any]:
    status, body = request_json("/intent", method="POST", body=intent, token=local_token())
    return {"http_status": status, "body": body}


def run_once(args: argparse.Namespace, root: Path) -> int:
    state = state_root(root)
    if not args.dry_run:
        reconcile_result = reconcile_outcomes(root)
        notify_new_trade_outcomes(state, reconcile_result.get("new_outcome_ids", []), root)
    health_status, health = request_json("/health")
    if health_status != 200 or health.get("status") != "ok":
        raise RuntimeError("gateway_health_unavailable")
    packet_status, packet = request_json("/packet", token=local_token())
    if packet_status != 200:
        raise RuntimeError(f"gateway_packet_failed:{packet_status}")
    if packet.get("schema_version") not in {
        "glitch.direct.decision_packet.v1",
        "glitch.direct.decision_packet.v2",
    } or not packet_is_current(packet):
        return 0

    state = state_root(root)
    capture_frame(packet, state)
    directive = read_directive(state)
    if not should_invoke(packet, directive):
        return 0
    required_frames = decision_frame_count()
    frames = recent_frames(state, required_frames)
    if not positioned(packet) and len(frames) < required_frames:
        return 0

    packet_id = str(packet.get("packet_id") or "")
    if not packet_id:
        raise ValueError("packet_id_missing")
    receipt_path = state / "receipts" / f"{packet_id}.json"
    outbox_path = state / "outbox" / f"{packet_id}.json"
    attempt_path = state / "attempts" / f"{packet_id}.json"
    if receipt_path.is_file():
        return 0
    if outbox_path.is_file():
        intent = read_json(outbox_path)
        validate_intent(intent, packet, None)
    else:
        if attempt_path.is_file():
            return 0
        write_json_atomic(attempt_path, {
            "schema_version": "glitch.topstep.model_attempt.v1",
            "packet_id": packet_id,
            "started_utc": utc_now(),
            "status": "started",
            "model": core_model(),
            "provider": core_provider(),
            "session_mode": "isolated",
        })
        prompt = build_prompt(packet, frames, recent_context(state), directive)
        try:
            intent, repair_count = invoke_valid_intent(
                args.profile, prompt, packet, directive, args.timeout_seconds
            )
        except Exception as error:
            attempt = read_json(attempt_path)
            attempt.update({
                "completed_utc": utc_now(),
                "status": "failed",
                "error": f"{type(error).__name__}:{error}"[:500],
            })
            write_json_atomic(attempt_path, attempt)
            append_jsonl(state / "events.jsonl", {
                "schema_version": "glitch.topstep.cycle_event.v1",
                "event": "decision_failed",
                "recorded_utc": utc_now(),
                "packet_id": packet_id,
                "error": attempt["error"],
            })
            raise
        write_json_atomic(outbox_path, intent)
        append_jsonl(state / "decisions.jsonl", {
            "schema_version": "glitch.topstep.decision_record.v1",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent": intent,
        })
        attempt = read_json(attempt_path)
        attempt.update({
            "completed_utc": utc_now(),
            "status": "decision_ready",
            "output_repair_count": repair_count,
        })
        write_json_atomic(attempt_path, attempt)
        if directive:
            consume_directive(state, directive, packet_id)

    if args.dry_run:
        maybe_notify_telegram(state, intent, packet, dry_run=True)
        print(json.dumps({"packet_id": packet_id, "submitted": False}, separators=(",", ":")))
        return 0
    result = post_intent(intent)
    receipt = {
        "schema_version": "glitch.topstep.delivery_receipt.v1",
        "recorded_utc": utc_now(),
        "packet_id": packet_id,
        "intent_id": intent["intent_id"],
        "result": result,
    }
    write_json_atomic(receipt_path, receipt)
    append_jsonl(state / "receipts.jsonl", receipt)
    maybe_notify_telegram(state, intent, packet, receipt=receipt)
    print(json.dumps(receipt, separators=(",", ":")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=PROFILE_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("GLITCH_TOPSTEP_MODEL_TIMEOUT_SECONDS", "240")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = configure_environment()
    state = state_root(root)
    state.mkdir(parents=True, exist_ok=True)
    lock_path = state / "direct-cycle.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if time.time() - lock_path.stat().st_mtime <= max(args.timeout_seconds * 2, 600):
                return 0
            lock_path.unlink()
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileNotFoundError, FileExistsError):
            return 0
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        return run_once(args, root)
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"event": "topstep_cycle_failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
