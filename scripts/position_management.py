"""POSITION_MANAGEMENT_V1 — compact positioned ledger (NT parity)."""

from __future__ import annotations

import re
from typing import Any

MARKER = "POSITION_MANAGEMENT_V1"
FIELDS = (
    "POSITION_SIDE",
    "ENTRY_CURRENT_STOP_TARGET",
    "MFE_MAE_ROLLBACK",
    "CURRENT_SETUP",
    "CONTINUATION_EVIDENCE",
    "REVERSAL_EVIDENCE",
    "NOISE_SUPPORTED_PROTECTION_LEVEL",
    "REMAINING_OBJECTIVE",
    "HOLD_EV",
    "MOVE_STOP_EV",
    "MOVE_TP_EV",
    "EXIT_EV",
    "SELECTION_ACTION",
    "SELECTION_REASON",
)
MANAGEMENT_ACTIONS = frozenset({
    "HOLD",
    "MOVE_STOP",
    "MOVE_TP",
    "EXIT",
    "ENTER_LONG",
    "ENTER_SHORT",
})


def position_management_template(packet: dict[str, Any]) -> str:
    instrument = str(packet.get("instrument") or "REPLACE_INSTRUMENT").upper()
    lines = [MARKER, f"INSTRUMENT={instrument}"]
    lines.extend(f"{field}=REPLACE_WITH_CURRENT_POSITION_EVIDENCE" for field in FIELDS)
    return "\n".join(lines)


def _placeholder(value: str) -> bool:
    normalized = value.strip()
    if not normalized or normalized in {"...", "?"}:
        return True
    upper = normalized.upper()
    return upper.startswith("REPLACE_WITH_") or upper == "REPLACE"


def validate_position_management(
    text: Any,
    packet: dict[str, Any],
    *,
    action: str,
) -> None:
    if not isinstance(text, str) or MARKER not in text:
        raise ValueError("position_management_missing")
    instrument_match = re.search(r"(?mi)^INSTRUMENT\s*=\s*([A-Za-z0-9._-]+)\s*$", text)
    expected = str(packet.get("instrument") or "").upper()
    if not instrument_match or instrument_match.group(1).upper() != expected:
        raise ValueError("position_management_instrument_mismatch")
    values: dict[str, str] = {}
    for field in FIELDS:
        match = re.search(rf"(?mi)^{re.escape(field)}\s*=\s*(.+?)\s*$", text)
        if not match or not match.group(1).strip():
            raise ValueError(f"position_management_field_missing:{field}")
        value = match.group(1).strip()
        if _placeholder(value):
            raise ValueError(f"position_management_field_placeholder:{field}")
        values[field] = value
    if values["SELECTION_ACTION"].upper() != str(action).upper():
        raise ValueError("position_management_action_mismatch")
    if str(action).upper() not in MANAGEMENT_ACTIONS:
        raise ValueError("position_management_action_unsupported")
