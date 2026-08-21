#!/usr/bin/env python3
"""Mark orphan model attempts stuck in started as failed (breaks retry_after_failure loop)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default=os.environ.get(
            "GLITCH_TOPSTEP_PROFILE_ROOT",
            str(Path(os.environ["LOCALAPPDATA"]) / "hermes/profiles/glitch-topstep"),
        ),
    )
    parser.add_argument("--older-than-minutes", type=int, default=5)
    args = parser.parse_args()
    profile = Path(args.profile)
    attempts_dir = profile / "state" / "attempts"
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.older_than_minutes)
    repaired = 0
    for path in attempts_dir.glob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if doc.get("status") != "started":
            continue
        started_raw = doc.get("started_utc")
        if not isinstance(started_raw, str):
            continue
        started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
        if started > cutoff:
            continue
        doc["status"] = "failed"
        doc["completed_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        doc["error"] = "stale_orphan:attempt_never_completed"
        path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        repaired += 1
    print(f"repaired_stale_started={repaired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
