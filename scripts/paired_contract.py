"""Load the paired gateway/profile contract (TS-AUDIT-10 / GTHP-AUDIT-05)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DISTRIBUTION_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = DISTRIBUTION_ROOT / "paired-contract.json"


@lru_cache(maxsize=1)
def load_paired_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


CONTRACT = load_paired_contract()
RUNTIME_INTENT_SCHEMA = str(CONTRACT["runtime_intent_schema"])
PROMPT_VERSION = str(CONTRACT["profile"]["prompt_version"])
MIN_GATEWAY_VERSION = str(CONTRACT["profile"]["min_gateway_version"])
TESTED_GATEWAY_VERSION = str(CONTRACT["profile"]["tested_gateway_version"])
HERMES_INSTALL_NAME = str(CONTRACT["profile"]["hermes_install_name"])
