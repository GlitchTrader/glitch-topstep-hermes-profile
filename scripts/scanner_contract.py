"""Strict multi-instrument cognition ledger carried in decision_audit.decisive_evidence."""

from __future__ import annotations

import re
from typing import Any

MARKER = "INSTRUMENT_COMPARISON_V1"
LEGACY_JSON_MARKER = "INSTRUMENT_COMPARISON_V1:"
PATH_FIELDS = ("current_auction", "bullish_path", "bearish_path", "next_transition")
LINE_FIELDS = (
    "CURRENT_AUCTION",
    "BULLISH_PATH",
    "BEARISH_PATH",
    "NEXT_TRANSITION",
    "PRIOR_TRIGGER_REVIEW",
    "ASYMMETRY",
)
TRIGGER_LINE_PREFIXES = (
    "TRIGGER_ID",
    "TRIGGER_PATH",
    "TRIGGER_CONDITION",
    "TRIGGER_STATUS",
)
TRIGGER_STATUSES = {"HELD", "FAILED", "EXPIRED"}
_INSTRUMENT_HEADER = re.compile(r"^INSTRUMENT\s+([A-Za-z0-9._-]+)\s*:\s*$")
_FIELD_LINE = re.compile(r"^(?P<key>[A-Z_]+)\s*=\s*(?P<value>.+?)\s*$")


def candidate_instruments(packet: dict[str, Any]) -> list[str]:
    universe = packet.get("market_universe")
    candidates = universe.get("candidates") if isinstance(universe, dict) else None
    if not isinstance(candidates, list):
        return []
    return [
        str(row.get("instrument") or "").upper()
        for row in candidates
        if isinstance(row, dict) and str(row.get("instrument") or "").strip()
    ]


def multi_candidate_packet(packet: dict[str, Any]) -> bool:
    return len(candidate_instruments(packet)) > 1


def comparison_line_template(packet: dict[str, Any]) -> str:
    instruments = candidate_instruments(packet)
    lines = [MARKER]
    for instrument in instruments:
        lines.append(f"INSTRUMENT {instrument}:")
        for field in LINE_FIELDS:
            if field == "PRIOR_TRIGGER_REVIEW":
                lines.append(f"{field}=NOT_APPLICABLE")
            else:
                lines.append(f"{field}=REPLACE_WITH_CURRENT_PACKET_EVIDENCE")
        lines.extend([
            "TRIGGER_ID=REPLACE_STABLE_ID",
            "TRIGGER_PATH=NEXT",
            "TRIGGER_CONDITION=REPLACE_FROZEN_CONDITION",
            "TRIGGER_STATUS=HELD",
        ])
    lines.extend([
        f"RANKING={','.join(instruments)}",
        f"SELECTION_INSTRUMENT={packet.get('instrument')}",
        "SELECTION_ACTION=REPLACE_WITH_ACTION",
        "SELECTION_REASON=REPLACE_WITH_COMPARATIVE_REASON",
    ])
    return "\n".join(lines)


def comparison_template(packet: dict[str, Any]) -> str:
    return comparison_line_template(packet)


def _comparison_text_starts(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(LEGACY_JSON_MARKER):
        raise ValueError("instrument_comparison_legacy_json")
    first_line = stripped.splitlines()[0].strip() if stripped else ""
    return first_line == MARKER or stripped.startswith(MARKER + "\n")



def _placeholder_value(value: str) -> bool:
    normalized = value.strip()
    if not normalized or normalized in {"...", "?"}:
        return True
    upper = normalized.upper()
    return upper.startswith("REPLACE_WITH_") or upper == "REPLACE"


_TAIL_KEYS = {"RANKING", "SELECTION_INSTRUMENT", "SELECTION_ACTION", "SELECTION_REASON"}


def parse_comparison_line(
    text: str,
    *,
    packet_id: str,
    expires_utc: str | None = None,
) -> dict[str, Any]:
    if not isinstance(text, str) or not _comparison_text_starts(text):
        raise ValueError("instrument_comparison_missing")

    lines = [line.strip() for line in text.splitlines()[1:] if line.strip()]
    candidates: list[dict[str, Any]] = []
    tail_fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        header = _INSTRUMENT_HEADER.match(lines[index])
        if header:
            instrument = str(header.group(1)).upper()
            index += 1
            fields: dict[str, str] = {}
            while index < len(lines):
                if _INSTRUMENT_HEADER.match(lines[index]):
                    break
                field_match = _FIELD_LINE.match(lines[index])
                if field_match and field_match.group("key").upper() in _TAIL_KEYS:
                    break
                if field_match:
                    fields[field_match.group("key").upper()] = field_match.group("value").strip()
                index += 1
            trigger = {
                "trigger_id": fields.get("TRIGGER_ID", ""),
                "source_packet_id": packet_id,
                "path": fields.get("TRIGGER_PATH", ""),
                "condition": fields.get("TRIGGER_CONDITION", ""),
                "expires_utc": expires_utc or "",
                "status": fields.get("TRIGGER_STATUS", ""),
            }
            candidates.append({
                "instrument": instrument,
                "current_auction": fields.get("CURRENT_AUCTION", ""),
                "bullish_path": fields.get("BULLISH_PATH", ""),
                "bearish_path": fields.get("BEARISH_PATH", ""),
                "next_transition": fields.get("NEXT_TRANSITION", ""),
                "prior_trigger_review": fields.get("PRIOR_TRIGGER_REVIEW", ""),
                "asymmetry": fields.get("ASYMMETRY", ""),
                "triggers": [trigger],
            })
            continue
        field_match = _FIELD_LINE.match(lines[index])
        if field_match:
            tail_fields[field_match.group("key").upper()] = field_match.group("value").strip()
        index += 1

    ranking_raw = tail_fields.get("RANKING", "")
    ranking = [
        token.strip().upper()
        for token in re.split(r"[,>|]+", ranking_raw)
        if token.strip()
    ]
    return {
        "candidates": candidates,
        "ranking": ranking,
        "selected_instrument": tail_fields.get("SELECTION_INSTRUMENT", ""),
        "selection_action": tail_fields.get("SELECTION_ACTION", ""),
        "selection_reason": tail_fields.get("SELECTION_REASON", ""),
    }


def serialize_comparison_line(
    ledger: dict[str, Any],
    *,
    packet_id: str,
    expires_utc: str | None,
    action: str,
) -> str:
    lines = [MARKER]
    for row in ledger.get("candidates", []):
        if not isinstance(row, dict):
            continue
        instrument = str(row.get("instrument") or "").upper()
        lines.append(f"INSTRUMENT {instrument}:")
        lines.append(f"CURRENT_AUCTION={row.get('current_auction', '')}")
        lines.append(f"BULLISH_PATH={row.get('bullish_path', '')}")
        lines.append(f"BEARISH_PATH={row.get('bearish_path', '')}")
        lines.append(f"NEXT_TRANSITION={row.get('next_transition', '')}")
        lines.append(
            f"PRIOR_TRIGGER_REVIEW={row.get('prior_trigger_review') or 'NOT_APPLICABLE'}"
        )
        lines.append(f"ASYMMETRY={row.get('asymmetry', 'UNKNOWN')}")
        trigger = (row.get("triggers") or [{}])[0] if isinstance(row.get("triggers"), list) else {}
        if isinstance(trigger, dict):
            lines.append(f"TRIGGER_ID={trigger.get('trigger_id', '')}")
            lines.append(f"TRIGGER_PATH={trigger.get('path', '')}")
            lines.append(f"TRIGGER_CONDITION={trigger.get('condition', '')}")
            lines.append(f"TRIGGER_STATUS={trigger.get('status', '')}")
    ranking = ledger.get("ranking")
    if not isinstance(ranking, list):
        ranking = [row.get("instrument") for row in ledger.get("candidates", []) if isinstance(row, dict)]
    lines.extend([
        f"RANKING={','.join(str(item).upper() for item in ranking)}",
        f"SELECTION_INSTRUMENT={ledger.get('selected_instrument', '')}",
        f"SELECTION_ACTION={action}",
        f"SELECTION_REASON={ledger.get('selection_reason', '')}",
    ])
    return "\n".join(lines)


def backfill_constant_comparison_fields(intent: dict[str, Any]) -> None:
    """Repair omitted constant comparison labels without another model call."""
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return
    evidence = audit.get("decisive_evidence")
    if not isinstance(evidence, str) or not _comparison_text_starts(evidence):
        return
    header = re.compile(r"^INSTRUMENT\s+[A-Za-z0-9._-]+\s*:\s*$", re.IGNORECASE)
    field = re.compile(r"(?i)^PRIOR_TRIGGER_REVIEW\s*=")
    repaired: list[str] = []
    section_start: int | None = None
    section_has_field = False

    def close_section() -> None:
        nonlocal section_start, section_has_field
        if section_start is not None and not section_has_field:
            repaired.insert(section_start + 1, "PRIOR_TRIGGER_REVIEW=NOT_APPLICABLE")
        section_start = None
        section_has_field = False

    for line in evidence.splitlines():
        if header.match(line.strip()):
            close_section()
            repaired.append(line)
            section_start = len(repaired) - 1
            continue
        if section_start is not None and field.match(line.strip()):
            section_has_field = True
        repaired.append(line)
    close_section()
    audit["decisive_evidence"] = "\n".join(repaired)


def parse_selected_candidate_handoff(intent: dict[str, Any]) -> dict[str, Any] | None:
    audit = intent.get("decision_audit")
    if not isinstance(audit, dict):
        return None
    evidence = audit.get("decisive_evidence")
    if not isinstance(evidence, str) or not _comparison_text_starts(evidence):
        return None
    ledger = parse_comparison_line(
        evidence,
        packet_id=str(intent.get("packet_id") or ""),
        expires_utc=str(intent.get("expires_utc") or ""),
    )
    selection = intent.get("account_selection")
    handoff: dict[str, Any] = {
        "schema_version": "glitch.topstep.selected_candidate_handoff.v1",
        "packet_id": str(intent.get("packet_id") or ""),
        "selected_instrument": str(ledger.get("selected_instrument") or "").upper(),
        "selection_action": str(ledger.get("selection_action") or "").upper(),
        "selection_reason": str(ledger.get("selection_reason") or ""),
        "ranking": [
            str(item).upper()
            for item in ledger.get("ranking", [])
            if str(item).strip()
        ],
    }
    if isinstance(selection, dict):
        handoff["account_selection"] = {
            "selected_instrument": str(selection.get("selected_instrument") or "").upper(),
            "selected_contract_id": str(selection.get("selected_contract_id") or ""),
            "scope_generation": selection.get("scope_generation"),
            "scope_hash": selection.get("scope_hash"),
        }
    return handoff


def validate_selected_candidate_handoff(
    handoff: dict[str, Any],
    packet: dict[str, Any],
) -> None:
    selected = str(handoff.get("selected_instrument") or "").upper()
    packet_instrument = str(packet.get("instrument") or "").upper()
    if not selected or selected != packet_instrument:
        raise ValueError("selected_candidate_packet_mismatch")
    account_selection = packet.get("account_selection")
    if not isinstance(account_selection, dict):
        return
    scoped = str(account_selection.get("selected_instrument") or "").upper()
    if scoped and scoped != selected:
        raise ValueError("selected_candidate_scope_mismatch")
    handoff_scope = handoff.get("account_selection")
    if isinstance(handoff_scope, dict):
        handoff_instrument = str(handoff_scope.get("selected_instrument") or "").upper()
        if handoff_instrument and handoff_instrument != packet_instrument:
            raise ValueError("selected_candidate_scope_mismatch")
        contract_id = str(handoff_scope.get("selected_contract_id") or "")
        packet_contract = str(account_selection.get("selected_contract_id") or "")
        if contract_id and packet_contract and contract_id != packet_contract:
            raise ValueError("selected_candidate_contract_mismatch")


def _validate_account_selection(packet: dict[str, Any], expected: list[str]) -> None:
    selection = packet.get("account_selection")
    if selection is None:
        return
    if not isinstance(selection, dict):
        raise ValueError("account_selection_invalid")
    if selection.get("schema_version") != "glitch.topstep.account_selection.v1":
        raise ValueError("account_selection_schema_invalid")
    if selection.get("mode") != "single_contract":
        raise ValueError("account_selection_mode_invalid")
    selected_instrument = str(selection.get("selected_instrument") or "").upper()
    selected_contract_id = str(selection.get("selected_contract_id") or "")
    if selected_instrument not in expected or not selected_contract_id:
        raise ValueError("account_selection_identity_invalid")
    if not isinstance(selection.get("scope_generation"), int) or selection["scope_generation"] < 1:
        raise ValueError("account_selection_generation_invalid")
    if not isinstance(selection.get("scope_hash"), str) or not selection["scope_hash"].strip():
        raise ValueError("account_selection_scope_invalid")


def validate_comparison_ledger(
    text: Any,
    packet: dict[str, Any],
    *,
    action: str | None = None,
) -> dict[str, Any] | None:
    expected = candidate_instruments(packet)
    if len(expected) <= 1:
        return None
    _validate_account_selection(packet, expected)
    if not isinstance(text, str) or not _comparison_text_starts(text):
        raise ValueError("instrument_comparison_missing")

    value = parse_comparison_line(
        text,
        packet_id=str(packet.get("packet_id") or ""),
        expires_utc=str(packet.get("expires_utc") or ""),
    )
    actual = [
        str(row.get("instrument") or "").upper()
        for row in value.get("candidates", [])
        if isinstance(row, dict)
    ]
    if set(actual) != set(expected) or len(set(actual)) != len(expected):
        raise ValueError("instrument_candidates_incomplete")

    for row in value["candidates"]:
        assert isinstance(row, dict)
        instrument = str(row.get("instrument") or "").upper()
        for field in PATH_FIELDS:
            field_value = str(row.get(field) or "").strip()
            if not field_value or field_value == "REPLACE" or _placeholder_value(field_value):
                raise ValueError(f"instrument_candidate_field_invalid:{instrument}:{field}")
        triggers = row.get("triggers")
        if not isinstance(triggers, list) or not triggers:
            raise ValueError("instrument_triggers_invalid")
        for trigger in triggers:
            if not isinstance(trigger, dict):
                raise ValueError("instrument_trigger_invalid")
            required = {"trigger_id", "source_packet_id", "path", "condition", "expires_utc", "status"}
            if set(trigger) != required:
                raise ValueError("instrument_trigger_fields_invalid")
            if trigger.get("source_packet_id") != packet.get("packet_id"):
                raise ValueError("instrument_trigger_source_mismatch")
            if trigger.get("status") not in TRIGGER_STATUSES:
                raise ValueError("instrument_trigger_status_invalid")
            if not all(isinstance(trigger.get(field), str) and trigger[field].strip() for field in required):
                raise ValueError("instrument_trigger_value_invalid")

    ranking = value.get("ranking")
    if not isinstance(ranking, list) or set(map(str.upper, ranking)) != set(expected) or len(ranking) != len(expected):
        raise ValueError("instrument_ranking_incomplete")

    selected = value.get("selected_instrument")
    if selected is not None and str(selected).upper() not in expected:
        raise ValueError("selected_instrument_invalid")

    selection_action = str(value.get("selection_action") or "").upper()
    if _placeholder_value(selection_action):
        raise ValueError("candidate_comparison_selection_incomplete")
    if action is not None and selection_action != str(action).upper():
        raise ValueError("candidate_comparison_selection_action_mismatch")

    selection_reason = str(value.get("selection_reason") or "").strip()
    if not selection_reason or _placeholder_value(selection_reason):
        raise ValueError("candidate_comparison_selection_incomplete")

    return value
