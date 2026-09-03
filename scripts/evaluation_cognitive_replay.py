"""Minimal controlled cognitive replay — one envelope, one profile, isolated storage."""

from __future__ import annotations

import importlib.util
import json
import os
import time
import uuid
from pathlib import Path
from dataclasses import dataclass

from typing import Any, Callable

from common import read_json, utc_now, write_json_atomic
from evaluation_cost import (
    HermesInvocationCapture,
    account_evaluation_cost,
    cost_gate_blocks_expansion,
)
from ensemble_capability import capacity_gate
from ensemble_capacity_overlay import apply_capacity_gate_overlay
from ensemble_envelope import envelope_hash
from ensemble_envelope_seal import (
    envelope_validity_seconds,
    envelope_validity_seconds_from_envelope,
    seal_evaluation_envelope_from_frame,
)
from ensemble_validate import validate_evaluation_envelope, validate_normalized_candidate
from evaluation_owner import (
    EvaluationOwnerSession,
    assert_cognitive_replay_blocked,
    assert_evaluation_write_allowed,
    cognitive_replay_controlled_scope,
    cognitive_replay_permitted,
    ensure_evaluation_auth_ready,
    evaluation_hermes_home,
    evaluation_hermes_subprocess_env,
    evaluation_repo_root,
    evaluation_run_state_root,
    load_evaluation_budget,
    load_evaluation_credentials,
    open_evaluation_session,
    production_state_root,
    resolve_evaluation_model_provider,
)
from model_owner_lock import model_owner_lock_path, read_model_owner

_SCRIPTS = Path(__file__).resolve().parent


def _load_ensemble_runner():
    spec = importlib.util.spec_from_file_location(
        "run_ensemble_evaluation",
        _SCRIPTS / "run-ensemble-evaluation.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_BUILD_NORMALIZED = _load_ensemble_runner().build_normalized_candidate

MINIMAL_REPLAY_SCHEMA = "glitch.topstep.minimal_cognitive_replay.v1"
NORMALIZATION_VERSION = "2026-09-01-post-candidate-flat-rule"
DEFAULT_PROFILE_ID = "baseline-current"
DEFAULT_FRAME = (
    evaluation_repo_root()
    / "tests"
    / "fixtures"
    / "frozen_corpus"
    / "minute-frames"
    / "20260820T1200Z.json"
)

@dataclass(frozen=True)
class HermesInvokeResult:
    parsed: dict[str, Any]
    stdout: str
    stderr: str
    model: str
    provider: str
    calls: int = 1


def _coerce_invoke_result(
    result: HermesInvokeResult | dict[str, Any],
    *,
    prompt: str,
    model: str,
    provider: str,
) -> HermesInvokeResult:
    if isinstance(result, HermesInvokeResult):
        return result
    if isinstance(result, dict):
        return HermesInvokeResult(
            parsed=result,
            stdout=json.dumps(result, separators=(",", ":")),
            stderr="",
            model=model,
            provider=provider,
        )
    raise TypeError("hermes_invoker_return_invalid")


HermesInvoker = Callable[..., HermesInvokeResult | dict[str, Any]]


def load_frozen_frame(frame_path: Path) -> dict[str, Any]:
    value = json.loads(frame_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_frozen_frame")
    packet = value.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("frozen_frame_packet_missing")
    return {
        "minute_id": str(value.get("minute_id") or frame_path.stem),
        "captured_utc": str(value.get("captured_utc") or utc_now()),
        "packet": packet,
        "frame": value,
    }


def operational_artifact_snapshot(state_root: Path) -> dict[str, tuple[int, int] | None]:
    snapshot: dict[str, tuple[int, int] | None] = {}
    for name in ("decisions.jsonl", "receipts.jsonl", "profile-state.sqlite", "model-owner.lock"):
        path = state_root / name
        if path.is_file():
            stat = path.stat()
            snapshot[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size)
        else:
            snapshot[str(path.resolve())] = None
    outbox = state_root / "outbox"
    if outbox.is_dir():
        for path in sorted(outbox.glob("*.json")):
            stat = path.stat()
            snapshot[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def assert_operational_artifacts_unchanged(
    before: dict[str, tuple[int, int] | None],
    after: dict[str, tuple[int, int] | None],
) -> None:
    if before != after:
        raise PermissionError("production_operational_artifacts_mutated")


def build_minimal_cognitive_prompt(envelope: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": "glitch.topstep.evaluation_cognitive_prompt.v1",
            "instruction": (
                "Evaluate the frozen envelope and return exactly one JSON object. "
                "Do not put market snapshots inside state — state must be a canonical string token. "
                "If abstaining from a trade, use state=no_edge with direction=flat or hold — never candidate. "
                "If state=candidate or held, direction must be long or short and entry+stop are required numbers."
            ),
            "output_contract": {
                "schema_version": "glitch.topstep.evaluation_output_contract.v1",
                "state": {
                    "type": "string",
                    "required": True,
                    "enum": [
                        "candidate",
                        "held",
                        "no_edge",
                        "data_quality_insufficient",
                        "expired",
                        "timeout",
                        "error",
                    ],
                },
                "direction": {
                    "type": "string",
                    "required": True,
                    "enum": ["long", "short", "flat", "hold"],
                },
                "state_direction_rules": {
                    "candidate": {
                        "direction_must_be": ["long", "short"],
                        "requires": ["entry", "stop"],
                    },
                    "held": {
                        "direction_must_be": ["long", "short"],
                        "requires": ["entry", "stop"],
                    },
                    "no_edge": {
                        "direction_typically": ["flat", "hold"],
                        "forbidden": "Do not use candidate when abstaining.",
                    },
                },
                "thesis": {"type": "string", "required": True},
                "entry": {"type": "number", "required_when_state": ["candidate", "held"]},
                "stop": {"type": "number", "required_when_state": ["candidate", "held"]},
                "target": {"type": "number", "required_when_state": ["candidate"]},
                "target_absence_reason": {
                    "type": "string",
                    "required_when_state": ["held"],
                },
                "action": {"type": "string", "required": False},
            },
            "envelope": envelope,
        },
        indent=2,
        ensure_ascii=False,
    )


def normalize_raw_profile_output(
    *,
    raw: dict[str, Any],
    run_id: str,
    profile: dict[str, Any],
    envelope: dict[str, Any],
    gate: dict[str, Any],
    invocation_id: str,
    started_utc: str,
    finished_utc: str,
    latency_ms: int,
) -> dict[str, Any]:
    fixture = {**raw, "invocation_id": invocation_id}
    normalized = _BUILD_NORMALIZED(
        fixture=fixture,
        run_id=run_id,
        profile=profile,
        envelope=envelope,
        gate=gate,
        started_utc=started_utc,
        finished_utc=finished_utc,
        latency_ms=latency_ms,
    )
    validate_normalized_candidate(normalized)
    return normalized


def invoke_live_evaluation_hermes(
    prompt: str,
    skills: list[str],
    timeout_seconds: int,
    hermes_home: Path,
) -> HermesInvokeResult:
    import shutil
    import subprocess
    import sys

    from common import extract_single_json_object
    from hermes_toolsets import DEFAULT_HERMES_TOOLSETS
    from process_supervisor import run_supervised

    ready, auth_error = ensure_evaluation_auth_ready(hermes_home)
    if not ready:
        raise RuntimeError(auth_error)
    credentials = load_evaluation_credentials()
    provider_env = evaluation_hermes_subprocess_env(credentials)
    from common import hermes_chat_model_cli_args

    model_cli = hermes_chat_model_cli_args(
        hermes_home,
        model_env="EVALUATION_GLITCH_TOPSTEP_CORE_MODEL",
        provider_env="EVALUATION_GLITCH_TOPSTEP_CORE_PROVIDER",
    )
    model, provider = resolve_evaluation_model_provider(hermes_home)

    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    python_executable = Path(executable).with_name(
        "python.exe" if sys.platform == "win32" else "python"
    )
    if not python_executable.is_file():
        python_executable = Path(sys.executable)

    args = [
        "chat",
        "-Q",
        "--source",
        "trading",
        *model_cli,
        "--max-turns",
        "4",
        "--skills",
        ",".join(skills),
        "--toolsets",
        DEFAULT_HERMES_TOOLSETS,
    ]
    home_text = str(hermes_home)
    wrapper = (
        "import os,sys;from pathlib import Path;"
        f"os.environ['HERMES_HOME']={home_text!r};"
        "from hermes_cli.main import main;prompt=sys.stdin.read();"
        f"sys.argv=[sys.argv[0]]+{args!r}+['-q',prompt];main()"
    )
    completed = run_supervised(
        [str(python_executable), "-c", wrapper],
        input_text=prompt,
        timeout_seconds=timeout_seconds,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        extra_env=provider_env,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"evaluation_hermes_failed:{completed.returncode}:{detail[:800]}"
        )
    parsed = extract_single_json_object(completed.stdout)
    return HermesInvokeResult(
        parsed=parsed,
        stdout=completed.stdout,
        stderr=completed.stderr,
        model=model,
        provider=provider,
    )


def run_minimal_cognitive_replay(
    *,
    frame_path: Path | None = None,
    profile_id: str = DEFAULT_PROFILE_ID,
    run_id: str | None = None,
    repo_root: Path | None = None,
    output_path: Path | None = None,
    hermes_invoker: HermesInvoker | None = None,
    production_state: Path | None = None,
    session_cost_usd_so_far: float = 0.0,
    sealed_envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert_cognitive_replay_blocked()
    repo = repo_root or evaluation_repo_root()
    frame = load_frozen_frame(frame_path or DEFAULT_FRAME)
    matrix = read_json(repo / "evaluation" / "capability-matrix.json")
    registry = read_json(repo / "evaluation" / "registry.json")
    mapping = read_json(repo / "evaluation" / "packet_envelope_mapping.v1.json")
    budget = load_evaluation_budget(repo / "evaluation" / "ensemble_config.json")

    profiles = {
        str(row["profile_id"]): row
        for row in registry.get("profiles", [])
        if isinstance(row, dict)
    }
    if profile_id not in profiles:
        raise ValueError("profile_not_registered")
    profile = profiles[profile_id]

    source_catalog = matrix.get("source_catalog")
    if not isinstance(source_catalog, dict):
        raise ValueError("source_catalog_missing")

    if sealed_envelope is not None:
        envelope = sealed_envelope
        validate_evaluation_envelope(envelope)
        frame_snap = seal_evaluation_envelope_from_frame(
            frame=frame,
            source_catalog=source_catalog,
            mapping=mapping,
            validity_seconds=envelope_validity_seconds_from_envelope(envelope),
            frame_path=str(frame_path or DEFAULT_FRAME),
        )
        if str(frame_snap.get("snapshot_hash") or "") != str(envelope.get("snapshot_hash") or ""):
            raise ValueError("sealed_envelope_snapshot_mismatch")
        if envelope_hash(frame_snap) != envelope_hash(envelope):
            raise ValueError("sealed_envelope_identity_mismatch")
    else:
        envelope = seal_evaluation_envelope_from_frame(
            frame=frame,
            source_catalog=source_catalog,
            mapping=mapping,
            validity_seconds=envelope_validity_seconds(budget=budget),
            frame_path=str(frame_path or DEFAULT_FRAME),
        )
    snapshot_hash_before = str(envelope["snapshot_hash"])
    envelope_hash_before = envelope_hash(envelope)

    effective_run_id = run_id or f"minimal-{uuid.uuid4()}"
    session = open_evaluation_session(effective_run_id, repo_root=repo)
    prod_state = production_state or production_state_root()
    operational_before = operational_artifact_snapshot(prod_state)

    if not session.acquire(production_state=prod_state):
        return {
            "schema_version": MINIMAL_REPLAY_SCHEMA,
            "status": "deferred",
            "reason": "production_lane_active",
            "run_id": effective_run_id,
            "profile_id": profile_id,
            "snapshot_hash": snapshot_hash_before,
        }

    started = time.monotonic()
    started_utc = utc_now()
    raw_output: dict[str, Any] | None = None
    normalized: dict[str, Any] | None = None
    cost_record: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    adapter_overlay: dict[str, Any] | None = None
    model, provider = resolve_evaluation_model_provider(session.hermes_home)
    try:
        gate = capacity_gate(envelope, profile_id, matrix)
        prompt = build_minimal_cognitive_prompt(envelope)
        invoker = hermes_invoker or invoke_live_evaluation_hermes
        invoke_result = _coerce_invoke_result(
            invoker(
                prompt,
                list(profile.get("skills") or []),
                session.supervised_timeout_seconds(),
                session.hermes_home,
            ),
            prompt=prompt,
            model=model,
            provider=provider,
        )
        raw_output = invoke_result.parsed
        adapter_overlay = apply_capacity_gate_overlay(fixture=raw_output, gate=gate)
        cost_record = account_evaluation_cost(
            prompt=prompt,
            capture=HermesInvocationCapture(
                stdout=invoke_result.stdout,
                stderr=invoke_result.stderr,
                model=invoke_result.model,
                provider=invoke_result.provider,
                calls=invoke_result.calls,
            ),
            parsed_output=raw_output,
            session_cost_usd_so_far=session_cost_usd_so_far,
        )
        if not cost_record.get("cost_gate_passed"):
            raise RuntimeError("evaluation_cost_gate_failed")
        finished_utc = utc_now()
        latency_ms = max(1, int((time.monotonic() - started) * 1000))
        normalized = normalize_raw_profile_output(
            raw=raw_output,
            run_id=effective_run_id,
            profile=profile,
            envelope=envelope,
            gate=gate,
            invocation_id=session.invocation_id,
            started_utc=started_utc,
            finished_utc=finished_utc,
            latency_ms=latency_ms,
        )
    finally:
        session.release()

    snapshot_hash_after = str(envelope["snapshot_hash"])
    envelope_hash_after = envelope_hash(envelope)
    if snapshot_hash_before != snapshot_hash_after:
        raise ValueError("snapshot_hash_mutated_during_replay")
    if envelope_hash_before != envelope_hash_after:
        raise ValueError("envelope_hash_mutated_during_replay")

    operational_after = operational_artifact_snapshot(prod_state)
    assert_operational_artifacts_unchanged(operational_before, operational_after)

    owner = read_model_owner(model_owner_lock_path(session.state))
    lock_released = owner is None

    artifact = {
        "schema_version": MINIMAL_REPLAY_SCHEMA,
        "status": "completed",
        "evaluation_only": True,
        "cognitive_replay": True,
        "run_id": effective_run_id,
        "profile_id": profile_id,
        "invocation_id": session.invocation_id,
        "owner_kind": "evaluation",
        "envelope_id": envelope["envelope_id"],
        "snapshot_hash": snapshot_hash_after,
        "snapshot_hash_before": snapshot_hash_before,
        "snapshot_hash_after": snapshot_hash_after,
        "envelope_hash_before": envelope_hash_before,
        "envelope_hash_after": envelope_hash_after,
        "hermes_home": str(session.hermes_home),
        "state_root": str(session.state),
        "raw_profile_output": raw_output,
        "normalized": normalized,
        "profile_version": profile.get("profile_version"),
        "prompt_version": profile.get("prompt_version"),
        "latency_ms": normalized.get("latency_ms") if normalized else None,
        "capacity_gate": gate,
        "cost_usd": cost_record.get("cost_usd") if cost_record else None,
        "cost_basis": (cost_record or {}).get("cost_basis"),
        "estimated_cost_usd": (cost_record or {}).get("estimated_cost_usd"),
        "provider_reported_cost_usd": (cost_record or {}).get("provider_reported_cost_usd"),
        "cost_accounting": cost_record,
        "cost_gate_passed": bool(cost_record and cost_record.get("cost_gate_passed")),
        "expansion_blocked": cost_gate_blocks_expansion(cost_record or {}),
        "adapter_classification": (adapter_overlay or {}).get("adapter_classification"),
        "classification": {
            "thesis_quality": "not_evaluated_on_thin_fixture",
            "missing_required_evidence": (normalized or {}).get("state") == "missing_required_evidence",
            "not_comparable": (normalized or {}).get("comparability") == "not_comparable",
            "output_contract_category": (
                ((adapter_overlay or {}).get("adapter_classification") or {}).get("category")
            ),
            "adapter_error_code": (normalized or {}).get("error_code"),
        },
        "credentials_channel": "EVALUATION_*",
        "production_paths_untouched": True,
        "lock_released": lock_released,
        "budget": {
            "max_calls_per_snapshot": budget.get("max_calls_per_snapshot"),
            "max_cost_usd_per_session": budget.get("max_cost_usd_per_session"),
            "max_tokens_per_call": budget.get("max_tokens_per_call"),
            "max_tokens_per_session": budget.get("max_tokens_per_session"),
            "per_profile_timeout_ms": budget.get("per_profile_timeout_ms"),
        },
        "recorded_utc": utc_now(),
        "normalization_version": NORMALIZATION_VERSION,
    }

    if output_path is not None:
        assert_evaluation_write_allowed(output_path)
        write_json_atomic(output_path, artifact)

    return artifact
