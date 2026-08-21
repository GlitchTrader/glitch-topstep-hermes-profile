#!/usr/bin/env python3
"""Expire stale HELD comparison triggers and clear orphan pending rescan."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
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
    args = parser.parse_args()
    profile = Path(args.profile)
    sys.path.insert(0, str(profile / "scripts"))

    from common import parse_utc, read_optional_json, utc_now, write_json_atomic
    from trigger_lifecycle import comparison_trigger_path, pending_held_rescan_path

    supervisor = profile / "state" / "supervisor"
    path = comparison_trigger_path(supervisor)
    doc = read_optional_json(path)
    now = datetime.now(timezone.utc)
    if not isinstance(doc, dict):
        print("no trigger document")
        return 0

    rows = doc.get("triggers")
    if not isinstance(rows, list):
        print("no triggers list")
        return 0

    expired = 0
    active_held = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "HELD":
            continue
        raw = row.get("expires_utc")
        if isinstance(raw, str) and raw.strip():
            try:
                if parse_utc(raw) <= now:
                    row["status"] = "EXPIRED"
                    row["updated_utc"] = utc_now()
                    expired += 1
                    continue
            except (TypeError, ValueError):
                pass
        active_held += 1

    doc["updated_utc"] = utc_now()
    write_json_atomic(path, doc)

    pending = pending_held_rescan_path(supervisor)
    cleared_pending = False
    if active_held == 0 and pending.is_file():
        pending.unlink()
        cleared_pending = True

    print(
        f"expired_held={expired} active_held={active_held} "
        f"cleared_pending={cleared_pending} total_rows={len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
