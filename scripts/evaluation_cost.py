"""Evaluation invocation cost accounting — provider usage, token estimate, or unknown."""



from __future__ import annotations



import json

import math

import re

from dataclasses import dataclass

from pathlib import Path

from typing import Any



from evaluation_owner import evaluation_repo_root, load_evaluation_budget



SESSION_ID_RE = re.compile(r"session_id:\s*(\S+)", re.IGNORECASE)





@dataclass(frozen=True)

class HermesInvocationCapture:

    stdout: str

    stderr: str

    model: str

    provider: str

    calls: int = 1





def _load_rates(path: Path | None = None) -> dict[str, Any]:

    rates_path = path or (evaluation_repo_root() / "evaluation" / "evaluation_cost_rates.v1.json")

    return json.loads(rates_path.read_text(encoding="utf-8"))





def _estimate_tokens(text: str, *, chars_per_token: int) -> int:

    if not text:

        return 0

    return max(1, len(text) // max(1, chars_per_token))





def _conservative_cost_usd(value: float) -> float:

    if value <= 0:

        return 0.0

    return math.ceil(value * 1_000_000) / 1_000_000





def _token_usage_block(

    *,

    input_tokens: int,

    output_tokens: int,

    estimated: bool,

) -> dict[str, Any]:

    total = input_tokens + output_tokens

    return {

        "input_tokens": input_tokens,

        "output_tokens": output_tokens,

        "total_tokens": total,

        "prompt_tokens": input_tokens,

        "completion_tokens": output_tokens,

        "estimated": estimated,

    }





def _extract_reported_usage(payload: dict[str, Any]) -> dict[str, int] | None:

    for key in ("usage", "token_usage", "metrics"):

        block = payload.get(key)

        if not isinstance(block, dict):

            continue

        prompt = int(block.get("prompt_tokens") or block.get("input_tokens") or 0)

        completion = int(block.get("completion_tokens") or block.get("output_tokens") or 0)

        total = int(block.get("total_tokens") or 0)

        if prompt or completion or total:

            return {

                "prompt_tokens": prompt or max(0, total - completion),

                "completion_tokens": completion or max(0, total - prompt),

                "total_tokens": total or (prompt + completion),

            }

    cost = payload.get("cost_usd")

    if isinstance(cost, (int, float)):

        return {"reported_cost_usd": float(cost)}

    return None





def _session_id(stderr: str) -> str | None:

    match = SESSION_ID_RE.search(stderr or "")

    return match.group(1) if match else None





def _price_tokens(

    *,

    input_tokens: int,

    output_tokens: int,

    model_rates: dict[str, Any],

    conservative: bool,

) -> float:

    raw = (

        input_tokens * float(model_rates["input_usd_per_1m_tokens"]) / 1_000_000

        + output_tokens * float(model_rates["output_usd_per_1m_tokens"]) / 1_000_000

    )

    return _conservative_cost_usd(raw) if conservative else round(raw, 6)





def account_evaluation_cost(

    *,

    prompt: str,

    capture: HermesInvocationCapture,

    parsed_output: dict[str, Any] | None = None,

    rates_path: Path | None = None,

    session_cost_usd_so_far: float = 0.0,

) -> dict[str, Any]:

    rates = _load_rates(rates_path)

    budget = load_evaluation_budget()

    chars_per_token = int(rates.get("token_estimate_chars_per_token") or 4)

    pricing_version = str(rates.get("rates_version") or rates.get("schema_version") or "unknown")

    model = capture.model.strip()

    provider = capture.provider.strip()

    model_rates = (rates.get("models") or {}).get(model, {})



    reported = _extract_reported_usage(parsed_output or {})

    if reported and "reported_cost_usd" in reported:

        provider_cost = float(reported["reported_cost_usd"])

        return _finalize_cost(

            cost_basis="provider_reported_cost",

            pricing_version=pricing_version,

            estimated_cost_usd=None,

            provider_reported_cost_usd=provider_cost,

            token_usage=_token_usage_block(

                input_tokens=int(reported.get("prompt_tokens") or 0),

                output_tokens=int(reported.get("completion_tokens") or 0),

                estimated=False,

            ),

            capture=capture,

            budget=budget,

            rates=rates,

            session_cost_usd_so_far=session_cost_usd_so_far,

            cost_source="model_output.cost_usd",

        )



    if reported and reported.get("total_tokens") and model_rates:

        input_tokens = int(reported.get("prompt_tokens") or 0)

        output_tokens = int(reported.get("completion_tokens") or 0)

        priced = _price_tokens(

            input_tokens=input_tokens,

            output_tokens=output_tokens,

            model_rates=model_rates,

            conservative=False,

        )

        return _finalize_cost(

            cost_basis="provider_reported_usage",

            pricing_version=pricing_version,

            estimated_cost_usd=priced,

            provider_reported_cost_usd=None,

            token_usage=_token_usage_block(

                input_tokens=input_tokens,

                output_tokens=output_tokens,

                estimated=False,

            ),

            capture=capture,

            budget=budget,

            rates=rates,

            session_cost_usd_so_far=session_cost_usd_so_far,

            cost_source="model_output.usage_tokens",

        )



    input_tokens = _estimate_tokens(prompt, chars_per_token=chars_per_token)

    output_tokens = _estimate_tokens(capture.stdout, chars_per_token=chars_per_token)

    token_usage = _token_usage_block(

        input_tokens=input_tokens,

        output_tokens=output_tokens,

        estimated=True,

    )

    if model_rates:

        estimated = _price_tokens(

            input_tokens=input_tokens,

            output_tokens=output_tokens,

            model_rates=model_rates,

            conservative=True,

        )

        return _finalize_cost(

            cost_basis="estimated_tokens",

            pricing_version=pricing_version,

            estimated_cost_usd=estimated,

            provider_reported_cost_usd=None,

            token_usage=token_usage,

            capture=capture,

            budget=budget,

            rates=rates,

            session_cost_usd_so_far=session_cost_usd_so_far,

            cost_source=f"token_estimate:{model}",

        )



    return _finalize_cost(

        cost_basis="unknown",

        pricing_version=pricing_version,

        estimated_cost_usd=None,

        provider_reported_cost_usd=None,

        token_usage=token_usage,

        capture=capture,

        budget=budget,

        rates=rates,

        session_cost_usd_so_far=session_cost_usd_so_far,

        cost_source="model_rates_missing",

    )





def _finalize_cost(

    *,

    cost_basis: str,

    pricing_version: str,

    estimated_cost_usd: float | None,

    provider_reported_cost_usd: float | None,

    token_usage: dict[str, Any],

    capture: HermesInvocationCapture,

    budget: dict[str, Any],

    rates: dict[str, Any],

    session_cost_usd_so_far: float,

    cost_source: str,

) -> dict[str, Any]:

    max_session = float(budget.get("max_cost_usd_per_session") or 2.5)

    max_tokens_call = int(budget.get("max_tokens_per_call") or 50_000)

    max_tokens_session = int(budget.get("max_tokens_per_session") or 500_000)

    total_tokens = int(token_usage.get("total_tokens") or 0)



    if provider_reported_cost_usd is not None:

        cost_usd = round(float(provider_reported_cost_usd), 6)

    elif estimated_cost_usd is not None:

        cost_usd = float(estimated_cost_usd)

    else:

        cost_usd = None



    cost_unknown = cost_usd is None

    invocation_cost = float(cost_usd or 0.0)

    session_cost = session_cost_usd_so_far + invocation_cost



    within_cost = cost_usd is not None and session_cost <= max_session

    within_tokens_call = total_tokens <= max_tokens_call

    within_tokens_session = total_tokens <= max_tokens_session

    gate_passed = (

        not cost_unknown

        and within_cost

        and within_tokens_call

        and within_tokens_session

    )



    cost_status = {

        "provider_reported_cost": "provider_reported",

        "provider_reported_usage": "provider_reported",

        "estimated_tokens": "estimated_tokens",

        "unknown": "unknown",

    }.get(cost_basis, cost_basis)



    return {

        "cost_basis": cost_basis,

        "pricing_version": pricing_version,

        "model": capture.model,

        "provider": capture.provider,

        "estimated_cost_usd": estimated_cost_usd,

        "provider_reported_cost_usd": provider_reported_cost_usd,

        "cost_usd": cost_usd,

        "cost_status": cost_status,

        "cost_source": cost_source,

        "cost_unknown": cost_unknown,

        "token_usage": token_usage,

        "calls": capture.calls,

        "session_id": _session_id(capture.stderr),

        "session_cost_usd_before": round(session_cost_usd_so_far, 6),

        "session_cost_usd_after": round(session_cost, 6) if not cost_unknown else None,

        "budget_limits": {

            "max_cost_usd_per_session": max_session,

            "max_tokens_per_call": max_tokens_call,

            "max_tokens_per_session": max_tokens_session,

        },

        "within_cost_budget": within_cost,

        "within_token_limits": within_tokens_call and within_tokens_session,

        "cost_gate_passed": gate_passed,

        "expansion_blocked_if_unknown": bool(rates.get("unknown_blocks_expansion", True)),

    }





def cost_gate_blocks_expansion(cost_record: dict[str, Any]) -> bool:

    if cost_record.get("cost_unknown"):

        return True

    if cost_record.get("cost_basis") == "unknown":

        return True

    if cost_record.get("cost_status") == "unknown":

        return True

    if not cost_record.get("cost_gate_passed"):

        return True

    return False





def _cost_fields_from_artifact(row: dict[str, Any]) -> dict[str, Any]:

    accounting = row.get("cost_accounting") if isinstance(row.get("cost_accounting"), dict) else {}

    basis = str(accounting.get("cost_basis") or row.get("cost_basis") or "unknown")

    cost_usd = accounting.get("cost_usd")

    if cost_usd is None:

        cost_usd = row.get("cost_usd")

    estimated = accounting.get("estimated_cost_usd")

    if estimated is None:

        estimated = row.get("estimated_cost_usd")

    provider = accounting.get("provider_reported_cost_usd")

    if provider is None:

        provider = row.get("provider_reported_cost_usd")

    token_usage = accounting.get("token_usage") if isinstance(accounting.get("token_usage"), dict) else {}

    return {

        "cost_basis": basis,

        "cost_usd": cost_usd,

        "estimated_cost_usd": estimated,

        "provider_reported_cost_usd": provider,

        "cost_unknown": cost_usd is None,

        "cost_gate_passed": bool(accounting.get("cost_gate_passed", row.get("cost_gate_passed", False))),

        "session_id": accounting.get("session_id"),

        "profile_id": str(row.get("profile_id") or ""),

        "model": str(accounting.get("model") or ""),

        "total_tokens": int(token_usage.get("total_tokens") or 0),

        "latency_ms": row.get("latency_ms"),

    }





def audit_evaluation_costs(

    artifacts: list[dict[str, Any]],

    *,

    budget: dict[str, Any] | None = None,

) -> dict[str, Any]:

    """Offline cost audit across replay artifacts — no Hermes calls."""

    limits = budget or load_evaluation_budget()

    per_profile_limits = limits.get("per_profile") if isinstance(limits.get("per_profile"), dict) else {}

    max_session_cost = float(limits.get("max_cost_usd_per_session") or 2.5)

    max_tokens_call = int(limits.get("max_tokens_per_call") or 50_000)

    max_tokens_session = int(limits.get("max_tokens_per_session") or 500_000)



    basis_counts: dict[str, int] = {}

    violations: list[dict[str, Any]] = []

    per_invocation: list[dict[str, Any]] = []

    sessions: dict[str, dict[str, Any]] = {}

    profile_sessions: dict[str, dict[str, dict[str, Any]]] = {}

    estimated_total = 0.0

    provider_total = 0.0

    confirmed_total = 0.0

    unknown_pricing_count = 0

    latencies: list[int] = []

    max_calls_per_session = int(limits.get("max_calls_per_session") or 36)

    max_calls_per_snapshot = int(limits.get("max_calls_per_snapshot") or 6)

    per_profile_timeout_ms = int(limits.get("per_profile_timeout_ms") or 35_000)

    total_timeout_ms = int(limits.get("total_timeout_ms") or 120_000)

    total_latency_budget_ms = int(limits.get("total_latency_budget_ms") or 180_000)



    for row in artifacts:

        fields = _cost_fields_from_artifact(row)

        basis = fields["cost_basis"]

        basis_counts[basis] = basis_counts.get(basis, 0) + 1

        if fields["cost_unknown"]:

            unknown_pricing_count += 1

            violations.append(

                {

                    "kind": "unknown_pricing",

                    "run_id": row.get("run_id"),

                    "profile_id": fields["profile_id"],

                    "model": fields["model"],

                }

            )

        elif fields["cost_usd"] is not None:

            cost_val = float(fields["cost_usd"])

            if basis in {"estimated_tokens", "provider_reported_usage"} and fields["estimated_cost_usd"] is not None:

                estimated_total += float(fields["estimated_cost_usd"])

            elif basis == "estimated_tokens":

                estimated_total += cost_val

            if fields["provider_reported_cost_usd"] is not None:

                provider_total += float(fields["provider_reported_cost_usd"])

                confirmed_total += float(fields["provider_reported_cost_usd"])

            elif basis == "provider_reported_cost":

                provider_total += cost_val

                confirmed_total += cost_val

            elif basis == "provider_reported_usage":

                confirmed_total += cost_val



        if isinstance(fields["latency_ms"], int):

            latencies.append(fields["latency_ms"])



        session_id = str(fields["session_id"] or "unknown")

        session = sessions.setdefault(

            session_id,

            {

                "session_id": session_id,

                "invocation_count": 0,

                "accumulated_cost_usd": 0.0,

                "accumulated_tokens": 0,

                "unknown_pricing_count": 0,

                "within_session_cost_limit": True,

                "within_session_token_limit": True,

            },

        )

        session["invocation_count"] += 1

        if fields["cost_unknown"]:

            session["unknown_pricing_count"] += 1

        elif fields["cost_usd"] is not None:

            session["accumulated_cost_usd"] += float(fields["cost_usd"])

        session["accumulated_tokens"] += fields["total_tokens"]

        if session["accumulated_cost_usd"] > max_session_cost:

            session["within_session_cost_limit"] = False

        if session["accumulated_tokens"] > max_tokens_session:

            session["within_session_token_limit"] = False



        profile_id = fields["profile_id"] or "unknown"

        profile_bucket = profile_sessions.setdefault(profile_id, {})

        profile_session = profile_bucket.setdefault(session_id, {"accumulated_cost_usd": 0.0, "invocation_count": 0})

        profile_session["invocation_count"] += 1

        if not fields["cost_unknown"] and fields["cost_usd"] is not None:

            profile_session["accumulated_cost_usd"] += float(fields["cost_usd"])



        if fields["total_tokens"] > max_tokens_call:

            violations.append(

                {

                    "kind": "tokens_per_call_exceeded",

                    "run_id": row.get("run_id"),

                    "profile_id": profile_id,

                    "total_tokens": fields["total_tokens"],

                    "limit": max_tokens_call,

                }

            )

        latency_ms = fields.get("latency_ms")

        if isinstance(latency_ms, int) and latency_ms > per_profile_timeout_ms:

            violations.append(

                {

                    "kind": "per_profile_timeout_exceeded",

                    "run_id": row.get("run_id"),

                    "profile_id": profile_id,

                    "latency_ms": latency_ms,

                    "limit": per_profile_timeout_ms,

                }

            )

        if not fields["cost_gate_passed"]:

            violations.append(

                {

                    "kind": "cost_gate_failed",

                    "run_id": row.get("run_id"),

                    "profile_id": profile_id,

                    "cost_basis": basis,

                }

            )



        per_invocation.append(

            {

                "run_id": row.get("run_id"),

                "profile_id": profile_id,

                "session_id": session_id,

                **fields,

            }

        )



    for session_id, session in sessions.items():

        if not session["within_session_cost_limit"]:

            violations.append(

                {

                    "kind": "session_cost_exceeded",

                    "session_id": session_id,

                    "accumulated_cost_usd": round(session["accumulated_cost_usd"], 6),

                    "limit": max_session_cost,

                }

            )

        if not session["within_session_token_limit"]:

            violations.append(

                {

                    "kind": "session_tokens_exceeded",

                    "session_id": session_id,

                    "accumulated_tokens": session["accumulated_tokens"],

                    "limit": max_tokens_session,

                }

            )



    per_profile_audit: dict[str, Any] = {}

    for profile_id, session_map in sorted(profile_sessions.items()):

        profile_limit_cfg = per_profile_limits.get(profile_id) if isinstance(per_profile_limits, dict) else None

        max_profile_cost = (

            float(profile_limit_cfg.get("max_cost_usd_per_session"))

            if isinstance(profile_limit_cfg, dict) and profile_limit_cfg.get("max_cost_usd_per_session") is not None

            else None

        )

        profile_sessions_out = {

            sid: {

                "accumulated_cost_usd": round(data["accumulated_cost_usd"], 6),

                "invocation_count": data["invocation_count"],

                "within_profile_cost_limit": (

                    data["accumulated_cost_usd"] <= max_profile_cost

                    if max_profile_cost is not None

                    else None

                ),

            }

            for sid, data in sorted(session_map.items())

        }

        if max_profile_cost is not None:

            for sid, data in session_map.items():

                if data["accumulated_cost_usd"] > max_profile_cost:

                    violations.append(

                        {

                            "kind": "profile_session_cost_exceeded",

                            "profile_id": profile_id,

                            "session_id": sid,

                            "accumulated_cost_usd": round(data["accumulated_cost_usd"], 6),

                            "limit": max_profile_cost,

                        }

                    )

        per_profile_audit[profile_id] = {

            "limits_configured": max_profile_cost is not None,

            "max_cost_usd_per_session": max_profile_cost,

            "sessions": profile_sessions_out,

        }



    session_cost_max = max((s["accumulated_cost_usd"] for s in sessions.values()), default=0.0)

    calls_audit: dict[str, Any] = {}

    for session_id, session in sessions.items():

        within_calls = session["invocation_count"] <= max_calls_per_session

        calls_audit[session_id] = {

            "invocation_count": session["invocation_count"],

            "max_calls_per_session": max_calls_per_session,

            "within_session_call_limit": within_calls,

        }

        if not within_calls:

            violations.append(

                {

                    "kind": "session_calls_exceeded",

                    "session_id": session_id,

                    "invocation_count": session["invocation_count"],

                    "limit": max_calls_per_session,

                }

            )

    latency_sum = sum(latencies) if latencies else 0

    execution_time_audit = {

        "per_profile_timeout_ms": per_profile_timeout_ms,

        "total_timeout_ms": total_timeout_ms,

        "total_latency_budget_ms": total_latency_budget_ms,

        "latency_sum_ms": latency_sum,

        "within_total_latency_budget": latency_sum <= total_latency_budget_ms if latencies else True,

        "latency_p50_ms": (sorted(latencies)[len(latencies) // 2] if latencies else None),

        "latency_count": len(latencies),

    }

    if latencies and latency_sum > total_latency_budget_ms:

        violations.append(

            {

                "kind": "total_latency_budget_exceeded",

                "latency_sum_ms": latency_sum,

                "limit": total_latency_budget_ms,

            }

        )

    audit_gate_passed = unknown_pricing_count == 0 and not violations



    return {

        "schema_version": "glitch.topstep.evaluation_cost_audit.v1",

        "budget_reference": "evaluation/ensemble_config.json",

        "limits": {

            "max_cost_usd_per_session": max_session_cost,

            "max_tokens_per_call": max_tokens_call,

            "max_tokens_per_session": max_tokens_session,

            "max_calls_per_session": max_calls_per_session,

            "max_calls_per_snapshot": max_calls_per_snapshot,

            "per_profile_timeout_ms": per_profile_timeout_ms,

            "total_timeout_ms": total_timeout_ms,

            "total_latency_budget_ms": total_latency_budget_ms,

            "per_profile_limits_configured": bool(per_profile_limits),

        },

        "invocation_count": len(artifacts),

        "unknown_pricing_count": unknown_pricing_count,

        "cost_basis_counts": basis_counts,

        "cost_breakdown": {

            "estimated_total_usd": round(estimated_total, 6) if estimated_total else 0.0,

            "confirmed_total_usd": round(confirmed_total, 6) if confirmed_total else 0.0,

            "unknown_invocation_count": unknown_pricing_count,

        },

        "estimated_vs_provider": {

            "estimated_total_usd": round(estimated_total, 6) if estimated_total else 0.0,

            "provider_reported_total_usd": round(provider_total, 6) if provider_total else 0.0,

            "confirmed_total_usd": round(confirmed_total, 6) if confirmed_total else 0.0,

            "unknown_invocation_count": unknown_pricing_count,

        },

        "calls_audit": calls_audit,

        "execution_time_audit": execution_time_audit,

        "per_invocation": per_invocation,

        "sessions": {

            sid: {

                **data,

                "accumulated_cost_usd": round(data["accumulated_cost_usd"], 6),

            }

            for sid, data in sorted(sessions.items())

        },

        "per_profile": per_profile_audit,

        "session_cost_usd_max": round(session_cost_max, 6) if session_cost_max else None,

        "latency_ms": {

            "p50_ms": (sorted(latencies)[len(latencies) // 2] if latencies else None),

            "count": len(latencies),

        },

        "violations": violations,

        "audit_gate_passed": audit_gate_passed,

        "notes": [

            "unknown_pricing (cost_usd null) fails audit_gate_passed.",

            "per_profile limits enforced only when evaluation budget defines per_profile.",

        ],

    }


