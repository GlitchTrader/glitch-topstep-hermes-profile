"""Wave 5 offline/read-only — global selection + delivery revalidation, zero execution."""

from __future__ import annotations

import uuid
from typing import Any

from ensemble_aggregator import aggregate_envelope
from paper_simulator import assert_paper_simulator_isolation, envelope_expired, normalize_profile_row, utc_now

WAVE5_SCHEMA = "glitch.topstep.wave5_offline_delivery.v1"


def evaluate_delivery_revalidation(
    *,
    envelope: dict[str, Any],
    delivery_context: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return (ok, failure_code). Never emits intents or orders."""
    instrument = str(selection.get("selected_instrument") or "").upper()
    if not instrument and isinstance(selection.get("selected_candidate"), dict):
        instrument = str(selection["selected_candidate"].get("instrument") or "").upper()
    if not instrument:
        instrument = str(
            delivery_context.get("instrument") or envelope.get("instrument") or ""
        ).upper()
    ctx_instrument = str(delivery_context.get("instrument") or "").upper()
    if instrument and ctx_instrument and instrument != ctx_instrument:
        return False, "identity_mismatch"

    env_gen = str(envelope.get("contract_generation") or "")
    if isinstance(envelope.get("contract"), dict):
        env_gen = str(envelope["contract"].get("generation") or env_gen)
    ctx_gen = str(delivery_context.get("contract_generation") or "")
    if ctx_gen and env_gen and ctx_gen != env_gen:
        return False, "generation_mismatch"

    if delivery_context.get("contract_expired") is True:
        return False, "contract_expired"

    quote_age = delivery_context.get("quote_age_ms")
    max_age = delivery_context.get("max_quote_age_ms", 120_000)
    if isinstance(quote_age, (int, float)) and int(quote_age) > int(max_age):
        return False, "quote_stale"

    if delivery_context.get("daily_capture_locked") is True:
        return False, "daily_capture_locked"

    floor = delivery_context.get("hard_loss_floor_usd")
    pnl = delivery_context.get("account_pnl_usd")
    if isinstance(floor, (int, float)) and isinstance(pnl, (int, float)) and float(pnl) <= float(floor):
        return False, "hard_loss_floor_breached"

    if delivery_context.get("geometry_valid") is False:
        return False, "geometry_invalid"

    allowed = delivery_context.get("allowed_instruments")
    if isinstance(allowed, list) and instrument:
        allowed_set = {str(x).upper() for x in allowed}
        if instrument not in allowed_set:
            return False, "invalid_instrument"

    return True, None


def run_wave5_offline(
    *,
    envelope: dict[str, Any],
    profile_outputs: list[dict[str, Any]],
    rules: dict[str, Any],
    delivery_context: dict[str, Any],
    run_id: str | None = None,
    objections: list[dict[str, Any]] | None = None,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    """Six-profile envelope → one global aggregator output → offline delivery gate."""
    assert_paper_simulator_isolation()
    effective_run_id = run_id or f"wave5-offline-{uuid.uuid4()}"
    base: dict[str, Any] = {
        "schema_version": WAVE5_SCHEMA,
        "run_id": effective_run_id,
        "evaluated_utc": utc_now(),
        "wave5_offline": True,
        "paper_only": True,
        "promotion_use_allowed": False,
        "intents_emitted": 0,
        "orders_emitted": 0,
        "operational_writes": 0,
        "projectx_calls": 0,
        "outbox_writes": 0,
    }

    if envelope_expired(envelope, as_of_utc=as_of_utc):
        return {**base, "status": "delivery_failure", "failure_code": "envelope_expired", "selection": None}

    candidates = [normalize_profile_row(row, envelope) for row in profile_outputs]
    selection = aggregate_envelope(
        run_id=effective_run_id,
        envelope=envelope,
        candidates=candidates,
        objections=objections or [],
        rules=rules,
    )
    outcome = str(selection.get("outcome") or "")

    if outcome == "classified_failure":
        return {
            **base,
            "status": "no_delivery",
            "failure_code": str(selection.get("decision_code") or "classified_failure"),
            "selection": selection,
        }

    if outcome != "selected":
        return {**base, "status": "no_delivery", "failure_code": "no_selection", "selection": selection}

    ok, failure = evaluate_delivery_revalidation(
        envelope=envelope,
        delivery_context=delivery_context,
        selection=selection,
    )
    if not ok:
        return {
            **base,
            "status": "delivery_failure",
            "failure_code": failure,
            "selection": selection,
            "attributable": True,
        }

    return {
        **base,
        "status": "delivery_ready_offline",
        "selection": selection,
        "failure_code": None,
    }
