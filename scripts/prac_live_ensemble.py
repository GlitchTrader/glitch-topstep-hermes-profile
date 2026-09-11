"""Hermes six-profile runner with an explicit, fail-closed PRAC lane.

This module is intentionally the only profile-side bridge to gateway execution.
The profile never imports ProjectX clients or credentials.  In offline and shadow
modes delivery is structurally disabled; in prac_live it requires --authorize
and still sends one global decision only.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol

from common import SafetyStopError, utc_now
from paired_contract import PROMPT_VERSION
from ensemble_aggregator import aggregate_envelope
from ensemble_capability import capacity_gate
from ensemble_envelope import build_evaluation_envelope, envelope_hash
from ensemble_parallel_runner import cleanup_work_dirs, run_profiles_parallel
from ensemble_skill_gate import (
    SkillPreloadError,
    assert_declared_skills_ready,
    default_glitch_topstep_hermes_home,
)
from ensemble_validate import validate_evaluation_envelope, validate_normalized_candidate
from gateway_client import local_token, request_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "evaluation" / "prac-live-ensemble-config.v1.json"
PROFILE_IDS = (
    "baseline-current",
    "structure",
    "adversarial-risk",
    "smart-money",
    "indicators",
    "orderflow",
)
ALLOWED_MODES = frozenset({"offline", "shadow", "prac_live"})
SENSITIVE = re.compile(r"(bearer\s+)[^\s,;]+|(token|secret|password|api[_-]?key)[^\s,;]*", re.IGNORECASE)


class RunnerError(RuntimeError):
    """A fail-closed runner stop with a stable audit code."""


class ProfileInvoker(Protocol):
    def __call__(self, profile: dict[str, Any], envelope: dict[str, Any], timeout_ms: int) -> dict[str, Any]: ...


@lru_cache(maxsize=1)
def _operator_identity() -> tuple[str, str]:
    """Load non-secret operator provenance from the checked-out profile."""
    path = ROOT / "operator.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("intent_provenance_missing") from exc
    operator_profile = str(document.get("operator_profile") or "").strip()
    loops = document.get("loops")
    model_version = ""
    if isinstance(loops, list):
        for loop in loops:
            if isinstance(loop, dict) and loop.get("id") == "core_decision":
                model_version = str(loop.get("model") or "").strip()
                break
    if not operator_profile or not model_version or not PROMPT_VERSION:
        raise RunnerError("intent_provenance_missing")
    return operator_profile, model_version


def resolve_hermes_executable() -> str:
    """Resolve only the configured or official host Hermes installation."""
    configured = os.environ.get("HERMES_EXECUTABLE", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    path_candidate = shutil.which("hermes")
    if path_candidate:
        candidates.append(Path(path_candidate))
    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        candidates.append(Path(local_app) / "hermes" / "hermes-agent" / "venv" / "Scripts" / "hermes.exe")
    seen: set[str] = set()
    path_candidate_text = str(path_candidate) if path_candidate else ""
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
            exists = candidate.is_file()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if exists or (path_candidate_text and str(candidate) == path_candidate_text):
            return resolved
    raise RunnerError("hermes_executable_not_found")


@dataclass(frozen=True)
class RunnerConfig:
    mode: str
    authorize: bool
    max_parallel_slots: int
    per_profile_timeout_ms: int
    total_timeout_ms: int
    session_limit: int
    exposure_limit: int
    reset_limit: int
    expected_contract_id: str | None
    evidence_root: Path

    @classmethod
    def load(cls, path: Path, *, mode: str, authorize: bool) -> "RunnerConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        modes = raw.get("modes") or {}
        if mode not in ALLOWED_MODES or mode not in modes:
            raise RunnerError("mode_invalid")
        selected = modes[mode]
        if mode == "prac_live" and not authorize:
            raise RunnerError("prac_live_requires_authorize")
        return cls(
            mode=mode,
            authorize=authorize,
            max_parallel_slots=min(2, max(1, int(selected.get("max_parallel_slots", 2)))),
            per_profile_timeout_ms=max(1, int(selected.get("per_profile_timeout_ms", 35_000))),
            total_timeout_ms=max(1, int(selected.get("total_timeout_ms", 120_000))),
            session_limit=max(1, int(selected.get("session_limit", 6))),
            exposure_limit=max(1, int(selected.get("exposure_limit", 1))),
            reset_limit=max(0, int(selected.get("reset_limit", 0))),
            expected_contract_id=selected.get("expected_contract_id") or None,
            evidence_root=ROOT / str(raw.get("evidence_root", "docs/evidence")),
        )


def sanitize_text(value: Any) -> str:
    return SENSITIVE.sub(r"\1[REDACTED]", str(value))


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise RunnerError("timestamp_missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise RunnerError("timestamp_invalid") from exc


def _has_closed_1m_bar_evidence(packet: dict[str, Any]) -> bool:
    quality = packet.get("data_quality")
    if isinstance(quality, dict) and quality.get("bar_1m_closed") is True:
        return True
    if packet.get("bar_close_utc"):
        return True
    observation = packet.get("market_observation")
    if not isinstance(observation, dict):
        return False
    nested_observation = observation.get("observation")
    if isinstance(nested_observation, dict):
        observation = nested_observation
    timeframes = observation.get("timeframes")
    if isinstance(timeframes, dict):
        frames = list(timeframes.values())
    elif isinstance(timeframes, list):
        frames = timeframes
    else:
        frames = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        if frame.get("timeframe_minutes") != 1 and frame.get("timeframe") not in {"1m", "1"}:
            continue
        if frame.get("latest_bar_partial") is False and frame.get("latest_bar_utc"):
            return True
        prior = frame.get("prior_completed_bar")
        if frame.get("latest_bar_partial") is True and isinstance(prior, dict) and prior.get("timestamp"):
            return True
    return False


def validate_live_packet(
    packet: dict[str, Any],
    health: dict[str, Any],
    *,
    now: datetime | None = None,
    expected_contract_id: str | None = None,
) -> None:
    if not isinstance(health, dict) or health.get("status") not in {"ok", "ready"}:
        raise RunnerError("health_invalid")
    if not isinstance(packet, dict):
        raise RunnerError("packet_incomplete")
    required = ("schema_version", "packet_id", "instrument", "created_utc", "expires_utc", "market", "market_observation", "contract", "data_quality")
    if any(not packet.get(field) for field in required):
        raise RunnerError("packet_incomplete")
    quality = packet["data_quality"]
    if not isinstance(quality, dict) or quality.get("state_complete") is not True:
        raise RunnerError("state_complete_false")
    issues = {str(item) for item in quality.get("issues", [])}
    if "quote_missing" in issues or quality.get("quote_missing") is True:
        raise RunnerError("quote_missing")
    market = packet["market"]
    if not isinstance(market, dict) or not market.get("snapshot_hash"):
        raise RunnerError("snapshot_missing")
    if not isinstance(packet["contract"], dict) or not packet["contract"].get("id"):
        raise RunnerError("contract_ambiguous")
    contract_id = str(packet["contract"]["id"])
    selected = (packet.get("account_selection") or {}).get("selected_contract_id")
    if selected and str(selected) != contract_id:
        raise RunnerError("contract_divergent")
    if expected_contract_id and contract_id != expected_contract_id:
        raise RunnerError("contract_divergent")
    if "bar_1m_partial" in issues or quality.get("bar_1m_closed") is False:
        raise RunnerError("bar_1m_not_closed")
    if not _has_closed_1m_bar_evidence(packet):
        raise RunnerError("bar_1m_close_missing")
    current = now or datetime.now(timezone.utc)
    if _parse_utc(packet["expires_utc"]) <= current:
        raise RunnerError("snapshot_expired")


def seal_live_envelope(packet: dict[str, Any], *, matrix: dict[str, Any], mapping: dict[str, Any], config: RunnerConfig) -> dict[str, Any]:
    envelope = build_evaluation_envelope(
        packet=packet,
        source_catalog=matrix["source_catalog"],
        reference_utc=str(packet["created_utc"]),
        validity_seconds=max(1, int(config.total_timeout_ms / 1000)),
        frame_id=str(packet["packet_id"]),
        corpus_ref="gateway:/packet",
        mapping=mapping,
    )
    envelope["envelope_hash"] = envelope_hash(envelope)
    validate_evaluation_envelope(envelope)
    return envelope


def _load_builder() -> Callable[..., dict[str, Any]]:
    path = Path(__file__).with_name("run-ensemble-evaluation.py")
    spec = importlib.util.spec_from_file_location("prac_normalizer", path)
    if not spec or not spec.loader:
        raise RunnerError("normalizer_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_normalized_candidate


def _normalize_result(raw: dict[str, Any] | None, *, profile: dict[str, Any], envelope: dict[str, Any], run_id: str, gate: dict[str, Any], started: str, finished: str, latency_ms: int) -> dict[str, Any]:
    builder = _load_builder()
    normalized = builder(
        fixture=raw,
        run_id=run_id,
        profile=profile,
        envelope=envelope,
        gate=gate,
        started_utc=started,
        finished_utc=finished,
        latency_ms=latency_ms,
    )
    # Execution fields remain cognitive evidence only; the gateway revalidates
    # contract, quantity, price geometry, and every risk/protection gate.
    if raw:
        for field in ("quantity", "confidence", "action", "order_type"):
            if field in raw:
                normalized[field] = copy.deepcopy(raw[field])
        if raw.get("state") in {"candidate", "held", "no_edge", "missing_required_evidence", "timeout", "error", "invalid"}:
            normalized["state"] = raw["state"]
            if raw["state"] in {"timeout", "error", "invalid"}:
                normalized["comparability"] = "not_comparable"
        if isinstance(raw.get("decision_audit"), dict):
            normalized["decision_audit"] = copy.deepcopy(raw["decision_audit"])
    validate_normalized_candidate(normalized)
    return normalized


def _invoke_hermes(profile: dict[str, Any], envelope: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    """Invoke Hermes without exposing gateway or ProjectX credentials."""
    executable = resolve_hermes_executable()
    skill_ids = [str(item) for item in (profile.get("skills") or []) if str(item).strip()]
    if skill_ids:
        try:
            assert_declared_skills_ready(skill_ids, profile_root=ROOT)
        except SkillPreloadError as exc:
            raise RunnerError(str(exc)) from exc
    hermes_home = default_glitch_topstep_hermes_home()
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(("PROJECTX_", "GLITCH_TOPSTEP_LOCAL_TOKEN", "GLITCH_LOCAL_TOKEN")):
            env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["HERMES_HOME"] = str(hermes_home)
    prompt = json.dumps(
        {
            "instruction": (
                "Return exactly one UTF-8 JSON object and nothing else. Do not emit prose, "
                "markdown, code fences, progress events, or multiple JSON objects. The object "
                "must contain state with one of candidate, held, no_edge, missing_required_evidence, "
                "timeout, error, or invalid. A no-edge response must use state no_edge and "
                "direction flat."
            ),
            "envelope": envelope,
            "profile_id": profile["profile_id"],
            "prompt_version": PROMPT_VERSION,
            "skills": skill_ids,
            "output_contract": {
                "schema": "hermes.profile_candidate.v1",
                "single_json_object": True,
                "markdown": False,
            },
        },
        ensure_ascii=False,
    )
    completed = subprocess.run(
        [executable, "chat", "--source", "trading", "--max-turns", "4", "--skills", ",".join(skill_ids), "-Q", "-q", prompt],
        capture_output=True,
        text=False,
        timeout=max(0.001, timeout_ms / 1000),
        env=env,
        cwd=str(ROOT),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        stdout = completed.stdout.decode("utf-8", errors="strict")
        completed.stderr.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SafetyStopError("safety_stop:hermes_utf8_decode_failed") from exc
    if completed.returncode:
        raise RunnerError("hermes_failed")
    from common import extract_single_json_object
    try:
        value = extract_single_json_object(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SafetyStopError("safety_stop:hermes_json_invalid") from exc
    if not isinstance(value, dict):
        raise SafetyStopError("safety_stop:hermes_json_invalid")
    return value


def _slot_loader(invoker: ProfileInvoker, profiles: dict[str, dict[str, Any]], envelope: dict[str, Any], timeout_ms: int, profile_id: str, _frame_id: str) -> dict[str, Any] | None:
    return invoker(profiles[profile_id], envelope, timeout_ms)


def run_profiles(*, envelope: dict[str, Any], registry: dict[str, Any], matrix: dict[str, Any], config: RunnerConfig, invoker: ProfileInvoker = _invoke_hermes) -> list[dict[str, Any]]:
    profiles = {str(row["profile_id"]): row for row in registry.get("profiles", []) if row.get("enabled", True)}
    missing = [pid for pid in PROFILE_IDS if pid not in profiles]
    if missing:
        raise RunnerError("profile_missing:" + ",".join(missing))
    run_id = str(uuid.uuid4())
    gates = {pid: capacity_gate(envelope, pid, matrix) for pid in PROFILE_IDS}
    started = time.monotonic()

    def loader(pid: str, frame_id: str) -> dict[str, Any] | None:
        return _slot_loader(invoker, profiles, envelope, config.per_profile_timeout_ms, pid, frame_id)

    def builder(**kwargs: Any) -> dict[str, Any]:
        raw = kwargs.get("fixture")
        return _normalize_result(raw, profile=kwargs["profile"], envelope=envelope, run_id=run_id, gate=kwargs["gate"], started=kwargs["started_utc"], finished=kwargs["finished_utc"], latency_ms=kwargs["latency_ms"])

    slots = run_profiles_parallel(
        profiles=[profiles[pid] for pid in PROFILE_IDS],
        frame_id=str(envelope["snapshot_id"]),
        run_id=run_id,
        envelope=envelope,
        gates_by_profile=gates,
        loader=loader,
        builder=builder,
        max_parallel_slots=config.max_parallel_slots,
        per_profile_timeout_ms=config.per_profile_timeout_ms,
        total_timeout_ms=config.total_timeout_ms,
    )
    if (time.monotonic() - started) * 1000 > config.total_timeout_ms:
        raise RunnerError("ensemble_timeout")
    _operator_profile, model_version = _operator_identity()
    return [{"profile_id": row.profile_id, "profile_version": profiles[row.profile_id].get("profile_version"), "prompt_version": profiles[row.profile_id].get("prompt_version"), "model_version": model_version, "invocation_id": row.invocation_id, "latency_ms": row.latency_ms, "error": row.error, "raw_profile_output": copy.deepcopy(row.raw_profile_output), "normalized": row.normalized} for row in slots]


def aggregate_global(*, envelope: dict[str, Any], slots: list[dict[str, Any]], rules: dict[str, Any], run_id: str) -> dict[str, Any]:
    candidates = [row["normalized"] for row in slots if isinstance(row.get("normalized"), dict)]
    adversarial = next((row for row in slots if row.get("profile_id") == "adversarial-risk"), None)
    if not isinstance(adversarial, dict):
        raise RunnerError("adversarial_objection_transport_failed")
    raw_adversarial = adversarial.get("raw_profile_output")
    if not isinstance(raw_adversarial, dict):
        raise RunnerError("adversarial_objection_transport_failed")
    if "objections" not in raw_adversarial:
        objections: list[dict[str, Any]] = []
        objection_status = "absent"
    else:
        raw_objections = raw_adversarial.get("objections")
        if not isinstance(raw_objections, list):
            raise RunnerError("adversarial_objection_transport_failed")
        objections = []
        for item in raw_objections:
            if not isinstance(item, dict):
                raise RunnerError("adversarial_objection_transport_failed")
            target = item.get("target_profile_id")
            risk_code = item.get("risk_code")
            severity = item.get("severity")
            reason = item.get("reason")
            evidence_refs = item.get("evidence_refs")
            if (
                not isinstance(target, str) or target not in PROFILE_IDS or target == "adversarial-risk"
                or not isinstance(risk_code, str) or not risk_code.strip()
                or severity not in {"info", "warning", "critical"}
                or not isinstance(item.get("objective_rule_match"), bool)
                or not isinstance(reason, str) or not reason.strip()
                or not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, str) and ref.strip() for ref in evidence_refs)
            ):
                raise RunnerError("adversarial_objection_transport_failed")
            objections.append({
                "source_profile_id": "adversarial-risk",
                "target_profile_id": target,
                "risk_code": risk_code,
                "severity": severity,
                "objective_rule_match": item["objective_rule_match"],
                "summary": reason,
                "reason": reason,
                "evidence_refs": list(evidence_refs),
            })
        objection_status = "present" if objections else "empty"
    decision = aggregate_envelope(run_id=run_id, envelope=envelope, candidates=candidates, objections=objections, rules=rules, required_profile_ids=list(PROFILE_IDS))
    decision["adversarial_objection_status"] = objection_status
    decision["decision_id"] = str(uuid.uuid4())
    decision["execution_authority"] = "gateway_only"
    decision["delivery_count"] = 0
    decision["prac_live_eligible"] = decision.get("outcome") == "selected"
    if decision["prac_live_eligible"]:
        selected_id = decision.get("selected_profile_id")
        selected = next((c for c in candidates if c.get("profile_id") == selected_id), None)
        decision["selected_candidate_full"] = copy.deepcopy(selected)
        selected_slot = next((row for row in slots if row.get("profile_id") == selected_id), None)
        if isinstance(selected_slot, dict):
            decision["selected_profile_version"] = selected_slot.get("profile_version")
            decision["selected_prompt_version"] = selected_slot.get("prompt_version")
            decision["selected_model_version"] = selected_slot.get("model_version")
    return decision


def decision_to_gateway_intent(decision: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    candidate = decision.get("selected_candidate_full") or {}
    direction = str(candidate.get("direction") or "").lower()
    action = {"long": "ENTER_LONG", "short": "ENTER_SHORT"}.get(direction)
    required = ("entry", "stop", "target", "quantity")
    if decision.get("outcome") not in {None, "selected"} or not action or any(candidate.get(key) is None for key in required):
        raise RunnerError("decision_missing_execution_fields")
    operator_profile, configured_model_version = _operator_identity()
    decision_id = str(decision.get("decision_id") or "").strip()
    prompt_version = str(decision.get("selected_prompt_version") or candidate.get("prompt_version") or "").strip()
    model_version = str(decision.get("selected_model_version") or candidate.get("model_version") or configured_model_version).strip()
    packet_id = str(packet.get("packet_id") or "").strip()
    scope = packet.get("decision_scope") if isinstance(packet.get("decision_scope"), dict) else {}
    scope_hash = str(scope.get("scope_hash") or "").strip()
    scope_generation = scope.get("generation")
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    account_name = str(account.get("name") or "").strip()
    snapshot_hash = str((packet.get("market") or {}).get("snapshot_hash") or "").strip()
    contract_id = str((packet.get("contract") or {}).get("id") or "").strip()
    expires_utc = str(packet.get("expires_utc") or "").strip()
    if not decision_id or not prompt_version or not model_version or not packet_id or not scope_hash or not isinstance(scope_generation, int) or scope_generation < 1 or not account_name or not snapshot_hash or not contract_id or not expires_utc:
        raise RunnerError("intent_provenance_missing")
    if prompt_version != PROMPT_VERSION:
        raise RunnerError("prompt_version_mismatch")
    audit = candidate.get("decision_audit")
    audit_fields = ("bull_case", "bear_case", "flat_case", "aggressive_case", "conservative_case", "decisive_evidence", "disconfirming_evidence", "change_condition", "final_choice")
    if not isinstance(audit, dict) or set(audit) != set(audit_fields) or any(not isinstance(audit.get(field), str) or not audit[field].strip() for field in audit_fields) or audit.get("final_choice") != action:
        raise RunnerError("decision_audit_incomplete")
    reason = candidate.get("thesis") or candidate.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RunnerError("decision_reason_missing")
    return {
        "schema_version": "glitch.intent.v3",
        "intent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch-topstep:{packet_id}:{decision_id}")),
        "created_utc": utc_now(),
        "action": action,
        "instrument": packet["instrument"],
        "account": account_name,
        "operator_profile": operator_profile,
        "packet_id": packet_id,
        "snapshot_hash": snapshot_hash,
        "contract_id": contract_id,
        "scope_hash": scope_hash,
        "scope_generation": scope_generation,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "entry_price_min": candidate.get("entry_range", {}).get("low", candidate["entry"]),
        "entry_price_max": candidate.get("entry_range", {}).get("high", candidate["entry"]),
        "stop_loss": candidate["stop"],
        "take_profit_1": candidate["target"],
        "quantity": candidate["quantity"],
        "order_type": "MARKET",
        "confidence": candidate.get("confidence", 0.0),
        "reason": reason,
        "decision_audit": copy.deepcopy(audit),
        "expires_utc": expires_utc,
    }


def deliver_global_decision(*, decision: dict[str, Any], packet: dict[str, Any], config: RunnerConfig, active_exposure: int = 0, client: Callable[..., tuple[int, dict[str, Any]]] = request_json) -> dict[str, Any]:
    if config.mode != "prac_live" or not config.authorize:
        return {"status": "not_delivered", "reason": "delivery_disabled_by_mode", "orders_sent": 0}
    outcome = decision.get("outcome")
    if outcome == "no_selection":
        return {
            "status": "not_delivered",
            "reason": "global_nothing",
            "decision_code": decision.get("decision_code"),
            "orders_sent": 0,
        }
    if outcome is None and "selected_candidate_full" in decision:
        pass
    elif outcome != "selected":
        raise RunnerError("global_decision_invalid")
    if active_exposure >= config.exposure_limit and decision.get("outcome") == "selected":
        raise RunnerError("second_exposure_blocked")
    intent = decision_to_gateway_intent(decision, packet)
    status, body = client("/intent", method="POST", body=intent, token=local_token())
    if status not in {200, 201, 202}:
        raise RunnerError("gateway_rejected_global_decision")
    receipt = body.get("receipt") if isinstance(body.get("receipt"), dict) else body
    if not receipt or receipt.get("status") in {"ambiguous", "unknown"}:
        raise RunnerError("receipt_ambiguous")
    if receipt.get("protection_confirmed") is not True:
        raise RunnerError("protection_not_confirmed")
    return {"status": "delivered", "orders_sent": 1, "receipt": {k: receipt.get(k) for k in ("status", "intent_id", "protection_confirmed")}}


def reset_allowed(*, flattened: bool, reconciled: bool, pending_orders: bool, receipts_persisted: bool, outcomes_persisted: bool) -> bool:
    return bool(flattened and reconciled and not pending_orders and receipts_persisted and outcomes_persisted)


def fetch_live_packet() -> tuple[dict[str, Any], dict[str, Any]]:
    token = local_token()
    health_status, health = request_json("/health", token=token)
    packet_status, packet = request_json("/packet", token=token)
    if health_status != 200 or packet_status != 200:
        raise RunnerError("gateway_authentication_failure")
    return health, packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes six-profile runner; PRAC delivery is fail-closed")
    parser.add_argument("--mode", choices=sorted(ALLOWED_MODES), required=True)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    config = RunnerConfig.load(args.config, mode=args.mode, authorize=args.authorize)
    if args.mode == "offline":
        if not args.packet:
            raise RunnerError("offline_packet_required")
        health = {"status": "ok"}
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    else:
        health, packet = fetch_live_packet()
    validate_live_packet(packet, health, expected_contract_id=config.expected_contract_id)
    matrix = json.loads((ROOT / "evaluation" / "capability-matrix.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "evaluation" / "registry.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "evaluation" / "aggregator_rules.v1.json").read_text(encoding="utf-8"))
    mapping = json.loads((ROOT / "evaluation" / "packet_envelope_mapping.v1.json").read_text(encoding="utf-8"))
    envelope = seal_live_envelope(packet, matrix=matrix, mapping=mapping, config=config)
    slots = run_profiles(envelope=envelope, registry=registry, matrix=matrix, config=config)
    decision = aggregate_global(envelope=envelope, slots=slots, rules=rules, run_id=str(uuid.uuid4()))
    delivery = deliver_global_decision(decision=decision, packet=packet, config=config)
    result = {"schema_version": "glitch.topstep.prac_live_ensemble_run.v1", "mode": args.mode, "authorized": config.authorize, "orders_sent": delivery.get("orders_sent", 0), "resets": 0, "envelope": {"envelope_id": envelope["envelope_id"], "snapshot_hash": envelope["snapshot_hash"], "envelope_hash": envelope["envelope_hash"]}, "profiles": slots, "decision": decision, "delivery": delivery}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerError, SafetyStopError) as exc:
        print(sanitize_text(f"runner_blocked:{exc}"), file=sys.stderr)
        raise SystemExit(2)
