"""Pure delivery classification — no filesystem or network."""

from __future__ import annotations

from typing import Any


def classify_delivery_result(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "transport_uncertain"
    if result.get("transport_error"):
        return "transport_uncertain"
    status = result.get("http_status")
    if not isinstance(status, int):
        return "transport_uncertain"
    if status in {408, 425, 429} or status >= 500:
        return "transport_uncertain"
    if isinstance(result.get("body"), dict):
        body = result["body"]
        if body.get("code") in {
            "intent_delivery_unreconciled",
            "intent_already_processing_or_recovery_required",
        }:
            return "transport_uncertain"
    if status >= 400:
        return "terminal_rejection"
    body = result.get("body")
    if isinstance(body, dict):
        executor = body.get("executor")
        executor_code = body.get("executor_code")
        if executor == "failed":
            return "terminal_rejection"
        if executor == "skipped" and executor_code != "no_op_action":
            return "terminal_rejection"
        if executor == "pending":
            return "transport_uncertain"
    return "successful"


GATEWAY_COGNITIVE_REJECTION_CODES = frozenset({
    "stop_would_widen",
    "target_would_widen",
    "stop_wrong_side_of_market",
    "target_wrong_side_of_entry",
    "move_stop_unavailable",
    "protection_not_proven",
    "action_not_supported_in_current_packet",
    "position_already_flat",
    "position_not_found",
    "target_tranche_not_found",
    "target_tranche_already_flat",
    "exit_quantity_exceeds_tranche_remaining",
    "exit_quantity_exceeds_attributable_remaining",
    "exit_quantity_invalid",
    "target_intent_id_required",
    "protective_leg_unresolved",
    "position_side_unknown",
    "amendment_current_price_missing",
    "amendment_market_reference_missing",
    "amendment_entry_reference_missing",
    "no_execution_action",
})

GATEWAY_SYSTEM_DEFECT_CODES = frozenset({
    "intent_schema_invalid",
    "intent_delivery_unreconciled",
    "intent_already_processing_or_recovery_required",
    "intent_body_conflict",
    "projectx_mutation_rejected",
    "projectx_mutation_outcome_ambiguous",
    "protection_cancel_failed",
    "decision_packet_unknown_or_expired",
    "action_not_implemented",
    "trading_disabled_by_operator",
    "account_name_mismatch",
    "snapshot_hash_mismatch",
})


def classify_gateway_rejection(result: dict[str, Any]) -> str | None:
    if classify_delivery_result(result) != "terminal_rejection":
        return None
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    code = str(body.get("code") or body.get("executor_code") or "")
    if code in GATEWAY_COGNITIVE_REJECTION_CODES:
        return "cognitive_rejection"
    if code in GATEWAY_SYSTEM_DEFECT_CODES:
        return "system_defect"
    http_status = result.get("http_status")
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return "cognitive_rejection"
    return "system_defect"
