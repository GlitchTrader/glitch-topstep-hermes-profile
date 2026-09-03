"""Single-shot coherent evaluation bundle capture — read-only, no polling."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from common import local_token, parse_utc, read_json, read_jsonl, utc_now  # noqa: E402
from ensemble_envelope import build_evaluation_envelope, load_packet_envelope_mapping  # noqa: E402
from ensemble_envelope_seal import envelope_validity_seconds, sealed_envelope_identity  # noqa: E402
from evaluation_owner import production_state_root  # noqa: E402
from shadow_gateway_readonly import (  # noqa: E402
    ShadowGatewayError,
    fetch_gateway_health_readonly,
    fetch_gateway_readonly_snapshot,
)

BUNDLE_SCHEMA = "glitch.topstep.coherent_evaluation_bundle.v1"
CAPTURE_MODE_DELIVERY_COMPLETE = "delivery_complete"
CAPTURE_MODE_LIVE_GATEWAY = "live_gateway"
CAPTURE_MODES = (CAPTURE_MODE_DELIVERY_COMPLETE, CAPTURE_MODE_LIVE_GATEWAY)


def _load_measurement_ready():
    spec = importlib.util.spec_from_file_location(
        "evaluation_measurement_ready", SCRIPTS / "evaluation-measurement-ready.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def index_decisions_by_packet_id(path: Path) -> dict[str, dict[str, Any]]:
    """Last row wins per packet_id — ponytail: jsonl append-only, duplicates rare."""
    index: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        packet_id = str(row.get("packet_id") or "")
        if packet_id:
            index[packet_id] = row
    return index


def latest_decision_row(index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not index:
        return None
    rows = list(index.values())

    def _key(row: dict[str, Any]) -> datetime:
        raw = row.get("recorded_utc")
        try:
            return parse_utc(raw) if raw else datetime.min.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)

    return max(rows, key=_key)


def latest_delivery_complete_anchor(state_root: Path) -> dict[str, Any] | None:
    """Latest cycle-empirical row with phase=delivery_complete."""
    latest: dict[str, Any] | None = None
    path = state_root / "cycle-empirical.jsonl"
    if not path.is_file():
        return None
    for row in read_jsonl(path):
        if str(row.get("phase") or "") == "delivery_complete" and row.get("packet_id"):
            latest = row
    return latest


def find_frozen_packet(state_root: Path, packet_id: str) -> tuple[dict[str, Any] | None, Path | None]:
    """Scan minute-frames newest-first for matching frozen packet."""
    frames_dir = state_root / "minute-frames"
    if not frames_dir.is_dir():
        return None, None
    paths = sorted(frames_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        doc = read_json(path)
        pkt = doc.get("packet") if isinstance(doc.get("packet"), dict) else None
        if pkt and str(pkt.get("packet_id") or "") == packet_id:
            return pkt, path
    return None, None


def load_receipt_for_packet(
    state_root: Path,
    *,
    packet_id: str,
    intent_id: str | None = None,
) -> dict[str, Any] | None:
    per_packet = state_root / "receipts" / f"{packet_id}.json"
    if per_packet.is_file():
        doc = read_json(per_packet)
        if isinstance(doc, dict):
            return doc
    for row in reversed(read_jsonl(state_root / "receipts.jsonl")):
        if str(row.get("packet_id") or "") == packet_id:
            return row
        if intent_id and str(row.get("intent_id") or "") == intent_id:
            return row
    return None


def _snapshot_hashes_aligned(
    *,
    envelope_snapshot_hash: str,
    decision: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
) -> tuple[bool, str]:
    if not envelope_snapshot_hash:
        return False, "snapshot_hash_missing_envelope"
    intent = decision.get("intent") if isinstance((decision or {}).get("intent"), dict) else {}
    decision_hash = str(intent.get("snapshot_hash") or (decision or {}).get("snapshot_hash") or "")
    if decision and not decision_hash:
        return False, "snapshot_hash_missing_decision"
    if decision_hash and decision_hash != envelope_snapshot_hash:
        return False, "snapshot_hash_mismatch_decision"
    receipt_hash = str((receipt or {}).get("snapshot_hash") or "")
    if receipt_hash and receipt_hash != envelope_snapshot_hash:
        return False, "snapshot_hash_mismatch_receipt"
    if receipt_hash and decision_hash and receipt_hash != decision_hash:
        return False, "snapshot_hash_mismatch_receipt_decision"
    return True, "aligned"


def _temporal_consistency(
    *,
    packet: dict[str, Any],
    decision: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Reject decision/receipt recorded before packet anchor (impossible coherent chain)."""
    try:
        packet_ts = parse_utc(packet.get("created_utc") or utc_now())
    except (TypeError, ValueError):
        return True, "ok"
    for row in (decision, receipt):
        if not row:
            continue
        raw = row.get("recorded_utc")
        if not raw:
            continue
        try:
            row_ts = parse_utc(raw)
        except (TypeError, ValueError):
            continue
        if row_ts < packet_ts:
            return False, "future_data_rejected"
    return True, "ok"


def _mixed_cycle(decision: dict[str, Any] | None, receipt: dict[str, Any] | None) -> tuple[bool, str]:
    if not decision or not receipt:
        return True, "ok"
    dp = str(decision.get("packet_id") or "")
    rp = str(receipt.get("packet_id") or "")
    if dp and rp and dp != rp:
        return False, "mixed_cycle_rejected"
    intent = decision.get("intent") if isinstance(decision.get("intent"), dict) else {}
    ip = str(intent.get("packet_id") or "")
    if ip and rp and ip != rp:
        return False, "mixed_cycle_rejected"
    return True, "ok"


def _correlation_reason(
    *,
    packet_id: str,
    decision: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    decisions_index: dict[str, dict[str, Any]],
    capture_mode: str,
) -> str | None:
    if decision is None:
        latest = latest_decision_row(decisions_index)
        if capture_mode == CAPTURE_MODE_LIVE_GATEWAY and latest and str(latest.get("packet_id") or "") != packet_id:
            # ponytail: GET /packet mints fresh UUID; profile decisions bind to frozen capture id
            return "live_packet_not_correlatable"
        if latest and str(latest.get("packet_id") or "") != packet_id:
            return "packet_advanced_no_match"
        return "decision_not_yet_available_for_packet"
    if receipt is None:
        return "receipt_not_yet_available_for_packet"
    intent = decision.get("intent") if isinstance(decision.get("intent"), dict) else {}
    if intent.get("packet_id") and str(intent["packet_id"]) != packet_id:
        return "packet_id_mismatch_intent"
    if decision.get("packet_id") and str(decision["packet_id"]) != packet_id:
        return "packet_id_mismatch_decision"
    if receipt.get("packet_id") and str(receipt["packet_id"]) != packet_id:
        return "packet_id_mismatch_receipt"
    return None


def _delivery_complete_anchor(
    state_root: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, Path | None, str | None]:
    anchor_row = latest_delivery_complete_anchor(state_root)
    if not anchor_row:
        return None, None, None, "delivery_complete_anchor_missing"
    packet_id = str(anchor_row.get("packet_id") or "")
    packet, frame_path = find_frozen_packet(state_root, packet_id)
    if not packet:
        return anchor_row, None, None, "frozen_packet_missing"
    return anchor_row, packet, frame_path, None


def capture_coherent_evaluation_bundle(
    *,
    state_root: Path | None = None,
    matrix: dict[str, Any] | None = None,
    mapping: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    token: str | None = None,
    http_get: Callable[[str, str, float], tuple[int, dict[str, Any]]] | None = None,
    gateway_snapshot: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    skip_gateway: bool = False,
    capture_mode: str = CAPTURE_MODE_DELIVERY_COMPLETE,
    anchor_row: dict[str, Any] | None = None,
    minute_frame_path: Path | None = None,
) -> dict[str, Any]:
    """Capture one coherent evaluation bundle; never mutates profile or gateway state."""
    if capture_mode not in CAPTURE_MODES:
        capture_mode = CAPTURE_MODE_DELIVERY_COMPLETE

    captured_utc = utc_now()
    health_fetched_utc: str | None = None
    packet_fetched_utc: str | None = None
    gateway_error: str | None = None
    envelope: dict[str, Any] | None = None
    identity: dict[str, Any] | None = None
    anchor: dict[str, Any] | None = None
    methods_used: list[str] = []

    matrix_doc = matrix or read_json(REPO / "evaluation" / "capability-matrix.json")
    mapping_doc = mapping or load_packet_envelope_mapping()
    budget_doc = budget or read_json(REPO / "evaluation" / "shadow-live-run-config.v1.json").get("budget") or {}

    root = (state_root or production_state_root()).resolve()
    decisions_path = root / "decisions.jsonl"
    decisions_index = index_decisions_by_packet_id(decisions_path)

    if capture_mode == CAPTURE_MODE_DELIVERY_COMPLETE and packet is None and gateway_snapshot is None:
        anchor_row, frozen_packet, frame_path, anchor_err = _delivery_complete_anchor(root)
        if anchor_err:
            gateway_error = anchor_err
        elif anchor_row and frozen_packet:
            packet = frozen_packet
            packet_fetched_utc = str(anchor_row.get("recorded_utc") or captured_utc)
            captured_utc = packet_fetched_utc
            anchor = {
                "packet_id": str(anchor_row.get("packet_id") or ""),
                "delivery_complete_recorded_utc": str(anchor_row.get("recorded_utc") or ""),
                "minute_frame_path": str(frame_path) if frame_path else None,
            }
            minute_frame_path = frame_path

    if gateway_snapshot:
        health = gateway_snapshot.get("health")
        packet = gateway_snapshot.get("packet") or gateway_snapshot.get("envelope", {}).get("packet")
        captured_utc = str(gateway_snapshot.get("captured_utc") or gateway_snapshot.get("fetched_utc") or captured_utc)
        health_fetched_utc = captured_utc
        packet_fetched_utc = captured_utc
        methods_used = list(gateway_snapshot.get("methods_used") or ["GET /health", "GET /packet"])
        if gateway_snapshot.get("envelope"):
            envelope = gateway_snapshot["envelope"]
            identity = gateway_snapshot.get("identity")
    elif not skip_gateway:
        try:
            if capture_mode == CAPTURE_MODE_DELIVERY_COMPLETE:
                health_fetched_utc = utc_now()
                health = fetch_gateway_health_readonly(token=token, http_get=http_get)
                methods_used = ["GET /health"]
            else:
                health_fetched_utc = utc_now()
                snap = fetch_gateway_readonly_snapshot(
                    matrix=matrix_doc,
                    mapping=mapping_doc,
                    budget=budget_doc,
                    token=token,
                    http_get=http_get,
                )
                health = snap.get("health")
                packet = snap.get("envelope", {}).get("packet") or snap.get("packet")
                envelope = snap.get("envelope")
                identity = snap.get("identity")
                packet_fetched_utc = str(snap.get("fetched_utc") or utc_now())
                captured_utc = packet_fetched_utc
                methods_used = list(snap.get("methods_used") or ["GET /health", "GET /packet"])
        except ShadowGatewayError as exc:
            gateway_error = exc.code

    if anchor is None and anchor_row and minute_frame_path:
        anchor = {
            "packet_id": str(anchor_row.get("packet_id") or (packet or {}).get("packet_id") or ""),
            "delivery_complete_recorded_utc": str(anchor_row.get("recorded_utc") or ""),
            "minute_frame_path": str(minute_frame_path),
        }

    packet_id = str((packet or {}).get("packet_id") or "")
    if decision is None and packet_id:
        decision = decisions_index.get(packet_id)
    if receipt is None and packet_id:
        intent_id = None
        if isinstance((decision or {}).get("intent"), dict):
            intent_id = str(decision["intent"].get("intent_id") or "") or None
        receipt = load_receipt_for_packet(root, packet_id=packet_id, intent_id=intent_id)

    not_ready_reason: str | None = gateway_error
    if not not_ready_reason and not packet_id:
        not_ready_reason = "gateway_unavailable" if skip_gateway and packet is None else "state_incomplete"

    if envelope is None and packet and not gateway_error:
        try:
            envelope = build_evaluation_envelope(
                packet=packet,
                source_catalog=matrix_doc["source_catalog"],
                reference_utc=str(packet.get("created_utc") or captured_utc),
                frame_id=packet_id or "gateway-packet",
                corpus_ref="coherent_evaluation_bundle",
                mapping=mapping_doc,
            )
            validity = envelope_validity_seconds(budget=budget_doc)
            envelope["validity_seconds"] = validity
            identity = sealed_envelope_identity(envelope)
            envelope["envelope_hash"] = identity["envelope_hash"]
        except (KeyError, TypeError, ValueError) as exc:
            not_ready_reason = not_ready_reason or f"envelope_build_error:{exc}"

    if not not_ready_reason:
        corr = _correlation_reason(
            packet_id=packet_id,
            decision=decision,
            receipt=receipt,
            decisions_index=decisions_index,
            capture_mode=capture_mode,
        )
        if corr:
            not_ready_reason = corr

    if not not_ready_reason:
        ok, reason = _mixed_cycle(decision, receipt)
        if not ok:
            not_ready_reason = reason

    if not not_ready_reason and packet:
        ok, reason = _temporal_consistency(packet=packet, decision=decision, receipt=receipt)
        if not ok:
            not_ready_reason = reason

    snapshot_aligned = False
    snapshot_detail = "not_evaluated"
    envelope_hash = str((identity or {}).get("envelope_hash") or (envelope or {}).get("envelope_hash") or "")
    snapshot_hash = str((identity or {}).get("snapshot_hash") or (envelope or {}).get("snapshot_hash") or "")
    if envelope and not not_ready_reason:
        snapshot_aligned, snapshot_detail = _snapshot_hashes_aligned(
            envelope_snapshot_hash=snapshot_hash,
            decision=decision,
            receipt=receipt,
        )
        if not snapshot_aligned:
            not_ready_reason = snapshot_detail

    measurement = _load_measurement_ready()
    measurement_result = measurement.evaluation_measurement_ready(
        mode="capture",
        packet=packet,
        decision=decision,
        receipt=receipt,
        gateway_health=health,
    )
    if not not_ready_reason and not measurement_result.get("ready"):
        blocking = measurement_result.get("blocking_reasons") or []
        not_ready_reason = blocking[0] if blocking else "measurement_not_ready"

    ready = (
        not_ready_reason is None
        and bool(packet_id)
        and snapshot_aligned
        and bool(measurement_result.get("ready"))
    )

    return {
        "schema_version": BUNDLE_SCHEMA,
        "capture_mode": capture_mode,
        "anchor": anchor,
        "captured_utc": captured_utc,
        "health_fetched_utc": health_fetched_utc,
        "packet_fetched_utc": packet_fetched_utc,
        "ready": ready,
        "not_ready_reason": not_ready_reason,
        "packet_id": packet_id or None,
        "snapshot_hash": snapshot_hash or None,
        "envelope_hash": envelope_hash or None,
        "snapshot_alignment": snapshot_detail,
        "operational_writes": 0,
        "methods_used": methods_used,
        "state_root": str(root),
        "health": health,
        "packet": packet,
        "decision": decision,
        "receipt": receipt,
        "envelope": envelope,
        "identity": identity,
        "measurement_ready": measurement_result,
    }


def load_coherent_bundle(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    if doc.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("invalid_coherent_bundle_schema")
    return doc


def bundle_preflight_inputs(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract shadow-preflight inputs from a coherent bundle."""
    return {
        "gateway_health": bundle.get("health"),
        "packet": bundle.get("packet"),
        "decision": bundle.get("decision"),
        "receipt": bundle.get("receipt"),
        "coherent_bundle_ready": bundle.get("ready"),
        "coherent_bundle_reason": bundle.get("not_ready_reason"),
        "capture_mode": bundle.get("capture_mode"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-shot coherent evaluation bundle capture (read-only)")
    parser.add_argument("--output", type=Path, help="Write bundle JSON (e.g. evaluation/runs/coherent-bundle-capture.json)")
    parser.add_argument("--state-root", type=Path, help="Hermes state root (default: production profile state)")
    parser.add_argument(
        "--capture-mode",
        choices=CAPTURE_MODES,
        default=CAPTURE_MODE_DELIVERY_COMPLETE,
        help="delivery_complete anchors on profile cycle-empirical; live_gateway uses GET /packet (mint-per-get)",
    )
    parser.add_argument("--skip-gateway", action="store_true", help="Offline: supply packet via --packet-file")
    parser.add_argument("--packet-file", type=Path, help="Packet JSON for offline capture")
    parser.add_argument("--health-file", type=Path, help="Gateway health JSON for offline capture")
    parser.add_argument("--decision-file", type=Path, help="Decision JSON override")
    parser.add_argument("--receipt-file", type=Path, help="Receipt JSON override")
    args = parser.parse_args()

    packet = None
    health = None
    decision = read_json(args.decision_file) if args.decision_file and args.decision_file.is_file() else None
    receipt = read_json(args.receipt_file) if args.receipt_file and args.receipt_file.is_file() else None
    if args.packet_file and args.packet_file.is_file():
        doc = read_json(args.packet_file)
        packet = doc.get("packet") if isinstance(doc.get("packet"), dict) else doc
    if args.health_file and args.health_file.is_file():
        health = read_json(args.health_file)

    result = capture_coherent_evaluation_bundle(
        state_root=args.state_root,
        skip_gateway=args.skip_gateway or (packet is not None and args.capture_mode != CAPTURE_MODE_DELIVERY_COMPLETE),
        capture_mode=args.capture_mode,
        packet=packet,
        health=health,
        decision=decision,
        receipt=receipt,
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
