#!/usr/bin/env python3
"""Apply the bounded GTHP-010 gateway/profile compatibility rewrite once."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_VERSION = "0.1.6"
GATEWAY_VERSION = "0.1.2"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


manifest = {
    "schema_version": "glitch.topstep.profile_compatibility.v1",
    "profile_name": "glitch-topstep",
    "profile_version": PROFILE_VERSION,
    "prompt_version": "glitch-topstep-v2",
    "hermes_minimum_version": "0.18.2",
    "gateway": {
        "name": "glitch-topstep",
        "exact_version": GATEWAY_VERSION,
        "health_schema": "glitch.direct.health.v2",
        "intent_schemas": ["glitch.intent.v2"],
        "decision_packet_schemas": [
            "glitch.direct.decision_packet.v1",
            "glitch.direct.decision_packet.v2",
        ],
        "required_capabilities": [
            "packet_supported_actions",
            "position_management",
            "tranche_ownership",
            "native_protection",
            "durable_mutation_receipts",
            "restart_reconciliation",
        ],
    },
}
write("compatibility.json", json.dumps(manifest, indent=2) + "\n")

write(
    "scripts/compatibility.py",
    '''"""Machine-enforced Glitch Topstep gateway/profile compatibility contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROFILE_ROOT / "compatibility.json"


def load_compatibility(root: Path | None = None) -> dict[str, Any]:
    path = (root or PROFILE_ROOT) / "compatibility.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"profile_compatibility_unavailable:{exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("profile_compatibility_invalid")
    gateway = value.get("gateway")
    if (
        value.get("schema_version") != "glitch.topstep.profile_compatibility.v1"
        or value.get("profile_name") != "glitch-topstep"
        or not isinstance(gateway, dict)
    ):
        raise RuntimeError("profile_compatibility_invalid")
    return value


def supported_packet_schemas(root: Path | None = None) -> frozenset[str]:
    manifest = load_compatibility(root)
    schemas = manifest["gateway"].get("decision_packet_schemas")
    if not isinstance(schemas, list) or not schemas:
        raise RuntimeError("profile_packet_schemas_invalid")
    return frozenset(str(item) for item in schemas if str(item).strip())


def validate_gateway_health(
    health: dict[str, Any],
    root: Path | None = None,
) -> None:
    if not isinstance(health, dict):
        raise RuntimeError("gateway_compatibility_missing")
    manifest = load_compatibility(root)
    expected = manifest["gateway"]
    actual = health.get("compatibility")
    if not isinstance(actual, dict):
        raise RuntimeError("gateway_compatibility_missing")
    checks = {
        "gateway_name": expected.get("name"),
        "gateway_version": expected.get("exact_version"),
        "health_schema": expected.get("health_schema"),
    }
    for field, expected_value in checks.items():
        if actual.get(field) != expected_value:
            raise RuntimeError(
                f"gateway_incompatible:{field}:expected={expected_value}:actual={actual.get(field)}"
            )
    if health.get("schema_version") != expected.get("health_schema"):
        raise RuntimeError("gateway_incompatible:health_payload_schema")
    for field, expected_values in (
        ("intent_schemas", expected.get("intent_schemas")),
        ("decision_packet_schemas", expected.get("decision_packet_schemas")),
        ("capabilities", expected.get("required_capabilities")),
    ):
        actual_values = actual.get(field)
        if not isinstance(actual_values, list):
            raise RuntimeError(f"gateway_incompatible:{field}")
        missing = sorted(set(expected_values or []).difference(str(item) for item in actual_values))
        if missing:
            raise RuntimeError(f"gateway_incompatible:{field}:missing={','.join(missing)}")


def validate_packet_schema(
    packet: dict[str, Any],
    root: Path | None = None,
) -> None:
    if not isinstance(packet, dict) or packet.get("schema_version") not in supported_packet_schemas(root):
        raise RuntimeError("gateway_packet_schema_incompatible")
''',
)

write(
    "scripts/check-compatibility.py",
    '''#!/usr/bin/env python3
"""Validate the installed profile compatibility manifest without network access."""
from __future__ import annotations

import json

from compatibility import load_compatibility


def main() -> int:
    manifest = load_compatibility()
    print(json.dumps({
        "ok": True,
        "schema_version": manifest["schema_version"],
        "profile_name": manifest["profile_name"],
        "profile_version": manifest["profile_version"],
        "gateway_version": manifest["gateway"]["exact_version"],
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

cycle_path = "scripts/run-topstep-cycle.py"
cycle = read(cycle_path)
cycle = replace_once(
    cycle,
    "from packet_model import frame_for_model, packet_for_model as build_model_packet\n",
    "from compatibility import supported_packet_schemas, validate_gateway_health\n"
    "from packet_model import frame_for_model, packet_for_model as build_model_packet\n",
    "cycle compatibility import",
)
cycle = replace_once(
    cycle,
    "SUPPORTED_PACKET_SCHEMAS = {\n"
    "    \"glitch.direct.decision_packet.v1\",\n"
    "    \"glitch.direct.decision_packet.v2\",\n"
    "}\n",
    "SUPPORTED_PACKET_SCHEMAS = supported_packet_schemas()\n",
    "cycle packet schemas",
)
cycle = replace_once(
    cycle,
    "    if health_status != 200 or health.get(\"status\") not in {\"ok\", \"degraded\"}:\n"
    "        raise RuntimeError(\"gateway_health_unavailable\")\n\n"
    "    packet_status, packet = request_json(\"/packet\", token=token)\n",
    "    if health_status != 200 or health.get(\"status\") not in {\"ok\", \"degraded\"}:\n"
    "        raise RuntimeError(\"gateway_health_unavailable\")\n"
    "    validate_gateway_health(health)\n\n"
    "    packet_status, packet = request_json(\"/packet\", token=token)\n",
    "cycle health validation",
)
write(cycle_path, cycle)

plugin_path = "plugins/topstep-control/__init__.py"
plugin = read(plugin_path)
plugin = replace_once(
    plugin,
    "import os\nimport tempfile\n",
    "import os\nimport sys\nimport tempfile\n",
    "plugin sys import",
)
plugin = replace_once(
    plugin,
    "def _job(name: str) -> Optional[dict[str, Any]]:\n",
    '''def _compatibility_module():
    scripts = _profile_root() / "scripts"
    scripts_text = str(scripts)
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    from compatibility import validate_gateway_health, validate_packet_schema
    return validate_gateway_health, validate_packet_schema


def _validate_gateway_health(health: dict[str, Any]) -> None:
    validator, _packet_validator = _compatibility_module()
    validator(health, _profile_root())


def _validate_packet_schema(packet: dict[str, Any]) -> None:
    _health_validator, validator = _compatibility_module()
    validator(packet, _profile_root())


def _job(name: str) -> Optional[dict[str, Any]]:
''',
    "plugin compatibility helpers",
)
plugin = replace_once(
    plugin,
    "    mode = str(health.get(\"trading_mode\") or \"unknown\")\n",
    "    try:\n"
    "        _validate_gateway_health(health)\n"
    "    except RuntimeError as error:\n"
    "        return (\n"
    "            f\"Glitch Topstep gateway: incompatible ({str(error)[:180]}); \"\n"
    "            f\"Hermes jobs: {job_state}; operator worker: {_direct_worker_status()}.\"\n"
    "        )\n"
    "    mode = str(health.get(\"trading_mode\") or \"unknown\")\n",
    "plugin status compatibility",
)
plugin = replace_once(
    plugin,
    "    if status != 200 or health.get(\"status\") != \"ok\":\n"
    "        raise RuntimeError(\"The Glitch Topstep gateway is not healthy; jobs remain paused.\")\n"
    "    mode = str(health.get(\"trading_mode\") or \"unknown\")\n",
    "    if status != 200 or health.get(\"status\") != \"ok\":\n"
    "        raise RuntimeError(\"The Glitch Topstep gateway is not healthy; jobs remain paused.\")\n"
    "    _validate_gateway_health(health)\n"
    "    mode = str(health.get(\"trading_mode\") or \"unknown\")\n",
    "plugin trade compatibility",
)
plugin = replace_once(
    plugin,
    "def _require_flat_eligible() -> dict[str, Any]:\n"
    "    status, packet = _request(\"/packet\")\n",
    "def _require_flat_eligible() -> dict[str, Any]:\n"
    "    health_status, health = _request(\"/health\", authenticated=False)\n"
    "    if health_status != 200 or health.get(\"status\") != \"ok\":\n"
    "        raise RuntimeError(\"The Glitch Topstep gateway is not healthy; no forced entry was queued.\")\n"
    "    _validate_gateway_health(health)\n"
    "    status, packet = _request(\"/packet\")\n",
    "plugin forced entry compatibility",
)
plugin = replace_once(
    plugin,
    "    if status != 200:\n"
    "        raise RuntimeError(\"The current decision packet is unavailable.\")\n"
    "    account = packet.get(\"account\") if isinstance(packet, dict) else None\n",
    "    if status != 200:\n"
    "        raise RuntimeError(\"The current decision packet is unavailable.\")\n"
    "    _validate_packet_schema(packet)\n"
    "    account = packet.get(\"account\") if isinstance(packet, dict) else None\n",
    "plugin packet compatibility",
)
plugin = replace_once(
    plugin,
    "    if status != 200:\n"
    "        raise RuntimeError(f\"Jobs were paused, but the current packet is unavailable; jobs: {jobs}.\")\n"
    "    account = packet.get(\"account\") if isinstance(packet, dict) else None\n",
    "    if status != 200:\n"
    "        raise RuntimeError(f\"Jobs were paused, but the current packet is unavailable; jobs: {jobs}.\")\n"
    "    _validate_packet_schema(packet)\n"
    "    account = packet.get(\"account\") if isinstance(packet, dict) else None\n",
    "plugin flatten packet compatibility",
)
write(plugin_path, plugin)

setup_path = "setup.ps1"
setup = read(setup_path)
setup = replace_once(
    setup,
    "    'scripts\\common.py',\n",
    "    'compatibility.json',\n"
    "    'scripts\\compatibility.py',\n"
    "    'scripts\\check-compatibility.py',\n"
    "    'scripts\\common.py',\n",
    "setup required compatibility files",
)
setup = replace_once(
    setup,
    "if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {\n"
    "    throw \"Could not locate the Hermes Python runtime: $python\"\n"
    "}\n\n",
    "if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {\n"
    "    throw \"Could not locate the Hermes Python runtime: $python\"\n"
    "}\n"
    "$hermesVersionText = (& hermes --version | Out-String).Trim()\n"
    "if ($LASTEXITCODE -ne 0 -or $hermesVersionText -notmatch '(\\d+\\.\\d+\\.\\d+)') {\n"
    "    throw 'Could not determine the installed Hermes version.'\n"
    "}\n"
    "if ([version]$Matches[1] -lt [version]'0.18.2') {\n"
    "    throw \"Hermes 0.18.2 or newer is required; installed: $($Matches[1])\"\n"
    "}\n"
    "& $python (Join-Path $profileRoot 'scripts\\check-compatibility.py') | Out-Null\n"
    "if ($LASTEXITCODE -ne 0) { throw 'The profile compatibility manifest is invalid.' }\n\n",
    "setup compatibility validation",
)
setup = replace_once(
    setup,
    "    # Every minute: capture frames, deliver pending intents, and invoke LLM on the\n"
    "    # flat 5-minute boundary (or every minute while positioned).\n",
    "    # Every minute: capture frames, deliver pending intents, and invoke Hermes\n"
    "    # according to explicit operator cadence. Evidence never becomes eligibility.\n",
    "setup cadence comment",
)
setup = replace_once(
    setup,
    "    distribution_version = '0.1.4'\n",
    "    distribution_version = '0.1.6'\n"
    "    paired_gateway_version = '0.1.2'\n"
    "    compatibility_manifest = 'glitch.topstep.profile_compatibility.v1'\n",
    "setup output version",
)
write(setup_path, setup)

write(
    "tests/test_compatibility.py",
    '''"""GTHP-010 gateway/profile compatibility contracts."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compatibility import (  # noqa: E402
    load_compatibility,
    supported_packet_schemas,
    validate_gateway_health,
    validate_packet_schema,
)


def health() -> dict:
    manifest = load_compatibility()
    gateway = manifest["gateway"]
    return {
        "schema_version": gateway["health_schema"],
        "status": "ok",
        "compatibility": {
            "gateway_name": gateway["name"],
            "gateway_version": gateway["exact_version"],
            "health_schema": gateway["health_schema"],
            "intent_schemas": gateway["intent_schemas"],
            "decision_packet_schemas": gateway["decision_packet_schemas"],
            "capabilities": gateway["required_capabilities"],
        },
    }


class CompatibilityTests(unittest.TestCase):
    def test_manifest_names_exact_paired_contract(self):
        manifest = load_compatibility()
        self.assertEqual(manifest["profile_version"], "0.1.6")
        self.assertEqual(manifest["prompt_version"], "glitch-topstep-v2")
        self.assertEqual(manifest["hermes_minimum_version"], "0.18.2")
        self.assertEqual(manifest["gateway"]["exact_version"], "0.1.2")

    def test_matching_health_and_packets_pass(self):
        validate_gateway_health(health())
        for schema in supported_packet_schemas():
            validate_packet_schema({"schema_version": schema})

    def test_version_schema_and_capability_mismatch_fail_closed(self):
        cases = []
        wrong_version = health()
        wrong_version["compatibility"]["gateway_version"] = "0.1.1"
        cases.append(wrong_version)
        wrong_schema = health()
        wrong_schema["schema_version"] = "glitch.direct.health.v1"
        cases.append(wrong_schema)
        missing_capability = health()
        missing_capability["compatibility"]["capabilities"] = ["packet_supported_actions"]
        cases.append(missing_capability)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    validate_gateway_health(value)
        with self.assertRaises(RuntimeError):
            validate_packet_schema({"schema_version": "unknown.packet"})

    def test_cycle_validates_health_before_packet(self):
        source = (SCRIPTS / "run-topstep-cycle.py").read_text(encoding="utf-8")
        health_index = source.index("validate_gateway_health(health)")
        packet_index = source.index('packet_status, packet = request_json("/packet"', health_index)
        self.assertLess(health_index, packet_index)
        self.assertIn("SUPPORTED_PACKET_SCHEMAS = supported_packet_schemas()", source)

    def test_control_plugin_blocks_resume_but_keeps_schema_checked_flatten(self):
        source = (ROOT / "plugins/topstep-control/__init__.py").read_text(encoding="utf-8")
        self.assertIn("_validate_gateway_health(health)", source)
        self.assertGreaterEqual(source.count("_validate_packet_schema(packet)"), 2)
        trade = source.split("def _trade", 1)[1].split("def _pause", 1)[0]
        self.assertLess(trade.index("_validate_gateway_health(health)"), trade.index("_resume_jobs()"))

    def test_setup_checks_manifest_hermes_and_current_distribution_version(self):
        source = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn("compatibility.json", source)
        self.assertIn("scripts\\check-compatibility.py", source)
        self.assertIn("Hermes 0.18.2 or newer is required", source)
        self.assertIn("distribution_version = '0.1.6'", source)
        self.assertIn("paired_gateway_version = '0.1.2'", source)


if __name__ == "__main__":
    unittest.main()
''',
)

write(
    "docs/specs/GTHP-010.md",
    '''# GTHP-010 — Enforce the paired gateway/profile contract

**Issue:** #22  
**Profile version:** 0.1.6  
**Paired gateway:** glitch-topstep 0.1.2

## Contract

`compatibility.json` is the profile-side release authority. It names the profile, prompt, Hermes minimum, gateway identity/version, health schema, intent schema, decision-packet schemas, and required software capability families.

Scheduled cognition, `/trade`, and operator-directed entry fail closed when authenticated gateway health does not match. Packet delivery and operator controls validate the packet wire schema. Per-packet `execution.supported_actions` remains the current-state action truth.

## Risk-reduction boundary

A global version mismatch blocks cognition and new operator-directed exposure. `/flatten_all` remains available when the current packet schema is still supported because explicit human risk reduction must not be stranded by an entry-side release mismatch; the gateway retains final identity and execution authority.

## Nonsecret boundary

Compatibility metadata contains no ProjectX credentials, local gateway token, account identity, policy value, market evidence, trade direction, or strategy setting.

## Acceptance

- exact 0.1.2 gateway health passes;
- wrong version, health schema, missing capability, or packet schema fails closed;
- setup verifies distribution integrity, profile manifest, and Hermes >= 0.18.2;
- profile 0.1.6 distribution hashes cover the compatibility contract and tests;
- auth, memory, session, and paused/enabled job state remain update-owned and unchanged.
''',
)

readme_path = "README.md"
readme = read(readme_path)
compat_section = '''

## Paired release compatibility

Profile `0.1.6` is paired with `glitch-topstep` gateway `0.1.2`, Hermes `0.18.2+`, health schema `glitch.direct.health.v2`, intent schema `glitch.intent.v2`, and decision packets `glitch.direct.decision_packet.v1/v2`. The exact nonsecret contract is distributed as `compatibility.json`.

Scheduled cognition and exposure-creating slash controls fail closed when authenticated gateway metadata is incompatible. Per-packet `execution.supported_actions` remains the action authority for current state. Operator flatten remains schema-checked and risk-reducing; compatibility metadata never selects or vetoes a market thesis.
'''
if "## Paired release compatibility" in readme:
    raise RuntimeError("README compatibility section already exists")
write(readme_path, readme.rstrip() + compat_section + "\n")

authority_path = "docs/AUTHORITY.md"
authority = read(authority_path)
compat_authority = '''

## Release compatibility

The gateway/profile pair is executable only when authenticated gateway health matches `compatibility.json`. This is software contract validation, not trading judgment. It may block scheduled cognition or new exposure when wire compatibility is unknown; it may not select direction, quantity, geometry, management, or abstention. Current-state action availability remains in each packet's `execution.supported_actions`.
'''
if "## Release compatibility" in authority:
    raise RuntimeError("AUTHORITY compatibility section already exists")
write(authority_path, authority.rstrip() + compat_authority + "\n")

distribution_path = "distribution.yaml"
distribution = read(distribution_path)
distribution = replace_once(distribution, "version: 0.1.5", "version: 0.1.6", "distribution version")
write(distribution_path, distribution)

ledger_path = "docs/ledger/ledger.json"
ledger = json.loads(read(ledger_path))
ledger["profile_version"] = PROFILE_VERSION
ledger["gateway"]["current_version"] = GATEWAY_VERSION
for item in ledger["items"]:
    if item.get("id") == "GTHP-010":
        item.update({
            "status": "done",
            "pull_request": 28,
            "evidence": [
                "compatibility.json",
                "scripts/compatibility.py",
                "scripts/check-compatibility.py",
                "scripts/run-topstep-cycle.py",
                "plugins/topstep-control/__init__.py",
                "tests/test_compatibility.py",
                "setup.ps1",
                "docs/specs/GTHP-010.md",
            ],
        })
    if item.get("id") == "PROFILE-BETA-01":
        dependencies = item.setdefault("depends_on", [])
        if "GTHP-010" not in dependencies:
            dependencies.insert(0, "GTHP-010")
ledger["updated"] = "2026-08-02"
write(ledger_path, json.dumps(ledger, indent=2) + "\n")

# Recalculate the distribution inventory and include new compatibility files.
sums_path = ROOT / "SHA256SUMS"
paths: list[str] = []
for raw in sums_path.read_text(encoding="utf-8-sig").splitlines():
    if raw.strip():
        _old_hash, rel = raw.split(None, 1)
        paths.append(rel.strip())
for rel in (
    "compatibility.json",
    "docs/specs/GTHP-010.md",
    "scripts/check-compatibility.py",
    "scripts/compatibility.py",
    "tests/test_compatibility.py",
):
    if rel not in paths:
        paths.append(rel)
paths.sort()
entries = [
    f"{hashlib.sha256((ROOT / rel).read_bytes()).hexdigest().upper()}  {rel}"
    for rel in paths
]
sums_path.write_text("\n".join(entries) + "\n", encoding="utf-8-sig")

print("GTHP-010 rewrite applied")
