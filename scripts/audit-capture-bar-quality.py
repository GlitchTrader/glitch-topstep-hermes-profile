"""Audit bar timing / partial_evidence risk in capture packets (offline)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO / "tests" / "fixtures" / "frozen_corpus" / "enriched" / "manifest.json"
DEFAULT_OUT = REPO / "evaluation" / "runs" / "capture-bar-quality-audit-2026-09-01.json"
DEFAULT_REVIEW = REPO / "evaluation" / "reviews" / "CAPTURE-BAR-QUALITY-AUDIT-2026-09-01.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_packet(frame_path: Path) -> dict[str, Any] | None:
    try:
        frame = json.loads(frame_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    packet = frame.get("packet")
    return packet if isinstance(packet, dict) else None


def _bar_audit(packet: dict[str, Any]) -> dict[str, Any]:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    obs = packet.get("market_observation") if isinstance(packet.get("market_observation"), dict) else {}
    dq = packet.get("data_quality") if isinstance(packet.get("data_quality"), dict) else {}
    timeframes = []
    partial_1m = None
    last_bar_close = None
    if isinstance(obs.get("observation"), dict):
        for tf in obs["observation"].get("timeframes") or []:
            if not isinstance(tf, dict):
                continue
            minutes = tf.get("timeframe_minutes")
            bars = tf.get("bars") if isinstance(tf.get("bars"), list) else []
            last = bars[-1] if bars else {}
            timeframes.append(
                {
                    "timeframe_minutes": minutes,
                    "bars_accepted": tf.get("bars_accepted"),
                    "last_bar": {
                        "open": last.get("open"),
                        "close": last.get("close"),
                        "high": last.get("high"),
                        "low": last.get("low"),
                        "volume": last.get("volume"),
                        "timestamp": last.get("timestamp") or last.get("bar_end_utc"),
                    },
                }
            )
            if minutes == 1 and isinstance(last, dict):
                last_bar_close = last.get("timestamp") or last.get("bar_end_utc")
                partial_1m = last.get("partial")
    capture_utc = str(packet.get("created_utc") or market.get("quote_timestamp") or "")
    timing_class = "unknown"
    if dq.get("state_complete") is True:
        timing_class = "state_complete"
    elif partial_1m is True:
        timing_class = "mid_bar_partial"
    elif partial_1m is False:
        timing_class = "bar_close_complete"
    return {
        "capture_utc": capture_utc,
        "quote_timestamp": market.get("quote_timestamp"),
        "state_complete": dq.get("state_complete"),
        "session_levels_reliable": market.get("session_levels_reliable"),
        "timing_class": timing_class,
        "partial_1m_bar": partial_1m,
        "last_1m_bar_close_utc": last_bar_close,
        "timeframes": timeframes,
        "recommendation": (
            "prefer_bar_close_or_state_complete_true"
            if timing_class in {"mid_bar_partial", "unknown"}
            else "acceptable"
        ),
    }


def audit_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus_root = manifest_path.parent
    rows: list[dict[str, Any]] = []
    by_timing: dict[str, int] = {}
    for entry in manifest.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("corpus_file") or "")
        frame_path = corpus_root / rel
        packet = _load_packet(frame_path) if frame_path.is_file() else None
        audit = _bar_audit(packet) if packet else {"timing_class": "missing_packet"}
        timing = str(audit.get("timing_class") or "unknown")
        by_timing[timing] = by_timing.get(timing, 0) + 1
        rows.append(
            {
                "frame_id": entry.get("frame_id"),
                "scenario_tag": entry.get("scenario_tag"),
                "instrument": entry.get("instrument"),
                "origin": entry.get("origin"),
                **audit,
            }
        )
    return {
        "schema_version": "glitch.topstep.capture_bar_quality_audit.v1",
        "generated_utc": _utc_now(),
        "manifest_path": str(manifest_path),
        "entry_count": len(rows),
        "timing_histogram": by_timing,
        "next_capture_policy": {
            "require_data_quality_state_complete": True,
            "prefer_capture_at_1m_bar_close": True,
            "record_bar_close_utc_in_packet": True,
            "do_not_change_baseline_doctrine": True,
        },
        "entries": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    hist = report.get("timing_histogram") or {}
    policy = report.get("next_capture_policy") or {}
    lines = [
        "# Auditoria qualidade de barra — captura (2026-09-01)",
        "",
        f"**Gerado:** {report.get('generated_utc')}",
        f"**Frames:** {report.get('entry_count')}",
        "",
        "## Histograma timing",
        "",
    ]
    for key, count in sorted(hist.items()):
        lines.append(f"- `{key}`: {count}")
    lines.extend(["", "## Política próximo PRAC soak", ""])
    for key, val in policy.items():
        lines.append(f"- `{key}`: {val}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit bar timing in enriched corpus packets")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    manifest = args.manifest if args.manifest.is_absolute() else REPO / args.manifest
    report = audit_manifest(manifest)
    out = args.output if args.output.is_absolute() else REPO / args.output
    review = args.review_output if args.review_output.is_absolute() else REPO / args.review_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(out), "timing_histogram": report["timing_histogram"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
