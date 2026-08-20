"""Build glitch.topstep.cognition_run.v1 from frozen minute-frames and archived state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from common import read_jsonl
from parity import classify_gateway_rejection, suggest_flat_abstention_classification


def corpus_hash(frames_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(frames_dir.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def load_frames(frames_dir: Path) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for path in sorted(frames_dir.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"invalid minute frame: {path}")
        minute_id = str(value.get("minute_id") or path.stem)
        packet = value.get("packet")
        if not isinstance(packet, dict):
            raise ValueError(f"packet missing: {path}")
        frames.append({"minute_id": minute_id, "packet": packet, "frame": value})
    if not frames:
        raise ValueError(f"no minute frames under {frames_dir}")
    return frames


def index_by_packet(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        packet_id = str(row.get("packet_id") or "")
        if packet_id:
            indexed[packet_id] = row
    return indexed


def load_state_indexes(state_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    decisions = index_by_packet(read_jsonl(state_root / "decisions.jsonl"))
    receipts = index_by_packet(read_jsonl(state_root / "receipts.jsonl"))
    for path in (state_root / "receipts").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            packet_id = str(value.get("packet_id") or path.stem)
            receipts[packet_id] = value
    return decisions, receipts


def abstention_for_nothing(packet: dict[str, Any], frame: dict[str, Any]) -> str | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    initial = market.get("last")
    forward = frame.get("forward_observation")
    if not isinstance(initial, (int, float)):
        return None
    if isinstance(forward, dict):
        try:
            return suggest_flat_abstention_classification(
                initial_price=float(initial),
                forward_high=float(forward["high"]),
                forward_low=float(forward["low"]),
                forward_close=float(forward["close"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    return None


def decision_row(
    *,
    frame_id: str,
    packet: dict[str, Any],
    frame: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    packet_id = str(packet.get("packet_id") or "")
    action = "NOTHING"
    rejection: str | None = None
    abstention: str | None = None

    decision = decisions.get(packet_id)
    if decision:
        intent = decision.get("intent")
        if isinstance(intent, dict) and isinstance(intent.get("action"), str):
            action = str(intent["action"])

    receipt = receipts.get(packet_id)
    if receipt:
        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        rejection = classify_gateway_rejection(result)

    if action == "NOTHING":
        abstention = abstention_for_nothing(packet, frame)

    return {
        "frame_id": frame_id,
        "packet_id": packet_id,
        "action": action,
        "rejection": rejection,
        "abstention_classification": abstention,
    }


def build_run(*, frames_dir: Path, state_root: Path, prompt_version: str) -> dict[str, Any]:
    frames = load_frames(frames_dir)
    decisions, receipts = load_state_indexes(state_root)
    rows = [
        decision_row(
            frame_id=str(item["minute_id"]),
            packet=item["packet"],
            frame=item["frame"],
            decisions=decisions,
            receipts=receipts,
        )
        for item in frames
    ]
    return {
        "schema_version": "glitch.topstep.cognition_run.v1",
        "prompt_version": prompt_version,
        "corpus_hash": corpus_hash(frames_dir),
        "frame_count": len(rows),
        "decisions": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = build_run(
        frames_dir=args.frames_dir,
        state_root=args.state_root,
        prompt_version=args.prompt_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
