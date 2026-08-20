#!/usr/bin/env python3
"""GTHP-AUDIT-06: lightweight quality gate without new dependencies."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REGRESSION_TESTS = (
    "tests/test_state_store.py",
    "tests/test_jsonl_tail.py",
    "tests/test_paired_contract.py",
)


def _syntax_ok(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def main() -> None:
    for relative in REGRESSION_TESTS:
        target = ROOT / relative
        if not target.is_file():
            raise SystemExit(f"missing_regression_test:{relative}")
    for path in sorted(ROOT.glob("scripts/*.py")):
        _syntax_ok(path)
    _syntax_ok(ROOT / "plugins/topstep-control/__init__.py")
    print("profile_quality_ok")


if __name__ == "__main__":
    main()
