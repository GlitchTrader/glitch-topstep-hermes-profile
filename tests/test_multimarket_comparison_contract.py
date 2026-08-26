import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("run_topstep_cycle", SCRIPTS / "run-topstep-cycle.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

from scanner_contract import (  # noqa: E402
    MARKER,
    comparison_line_template,
    parse_comparison_line,
    serialize_comparison_line,
    validate_comparison_ledger,
)


def multi_packet() -> dict:
    universe = json.loads(
        (ROOT / "tests" / "fixtures" / "paired" / "multi01_scanner_packet.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "packet_id": "multi01-packet",
        "expires_utc": "2026-08-20T12:05:00Z",
        "instrument": "MNQ",
        "account": {"name": "TopstepX-50K"},
        "contract": {"id": "CON.F.US.MNQ.U26"},
        "market": {"snapshot_hash": "hash-multi"},
        "decision_scope": {"scope_hash": "scope-mnq-mes-mcl", "generation": 7},
        "market_universe": universe,
        "account_selection": universe["account_selection"],
    }


def filled_ledger_text(action: str = "NOTHING") -> str:
    text = (
        ROOT / "tests" / "fixtures" / "paired" / "multi01_comparison_ledger.txt"
    ).read_text(encoding="utf-8").replace("SELECTION_ACTION=NOTHING", f"SELECTION_ACTION={action}")
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        direction = "LONG" if action == "ENTER_LONG" else "SHORT"
        if direction == "LONG":
            ev = (
                "SELECTION_EV=direction=LONG;entry=20000;stop=19990;target=20030;"
                "risk_points=10;reward_points=30;friction_points=1;breakeven_target_first=0.275;"
                "estimated_target_first_range=0.30-0.40;now_ev=POSITIVE_ROBUST;wait_price=19995;"
                "wait_ev=no improvement;decisive_reason=current-zone positive EV"
            )
        else:
            ev = (
                "SELECTION_EV=direction=SHORT;entry=20000;stop=20010;target=19970;"
                "risk_points=10;reward_points=30;friction_points=1;breakeven_target_first=0.275;"
                "estimated_target_first_range=0.30-0.40;now_ev=POSITIVE_ROBUST;wait_price=20005;"
                "wait_ev=no improvement;decisive_reason=current-zone positive EV"
            )
        text = re.sub(r"(?m)^SELECTION_EV=.*$", ev, text)
    return text


class MultiMarketComparisonContractTests(unittest.TestCase):
    def test_template_lists_every_candidate(self):
        template = comparison_line_template(multi_packet())
        self.assertIn("INSTRUMENT MNQ:", template)
        self.assertIn("INSTRUMENT MES:", template)
        self.assertIn("INSTRUMENT MCL:", template)

    def test_complete_line_passes(self):
        validated = validate_comparison_ledger(
            filled_ledger_text(),
            multi_packet(),
            action="NOTHING",
        )
        self.assertEqual(validated["ranking"], ["MNQ", "MES", "MCL"])

    def test_missing_instrument_rejected(self):
        text = filled_ledger_text()
        text = text.split("INSTRUMENT MES:", 1)[0] + text.split("INSTRUMENT MCL:", 1)[1]
        with self.assertRaisesRegex(ValueError, "instrument_candidates_incomplete"):
            validate_comparison_ledger(text, multi_packet(), action="NOTHING")

    def test_placeholder_rejected(self):
        text = filled_ledger_text().replace(
            "CURRENT_AUCTION=partial 1m below 5m VWAP; quote fresh; observation ready",
            "CURRENT_AUCTION=REPLACE",
        )
        with self.assertRaisesRegex(ValueError, "instrument_candidate_field_invalid"):
            validate_comparison_ledger(text, multi_packet(), action="NOTHING")

    def test_build_prompt_multi_uses_line_only(self):
        prompt = MODULE.build_prompt(multi_packet(), [], {}, None)
        envelope = json.loads(prompt.split("CURRENT_CYCLE=", 1)[1])
        decisive = envelope["required_output_template"]["decision_audit"]["decisive_evidence"]
        self.assertTrue(decisive.startswith(MARKER + "\n"))
        self.assertNotIn("prior_hypothesis=", decisive)
        disconfirming = envelope["required_output_template"]["decision_audit"]["disconfirming_evidence"]
        self.assertIn("prior_hypothesis=", disconfirming)

    def test_round_trip(self):
        parsed = parse_comparison_line(
            filled_ledger_text(),
            packet_id=multi_packet()["packet_id"],
            expires_utc=multi_packet()["expires_utc"],
        )
        round_trip = serialize_comparison_line(
            parsed,
            packet_id=multi_packet()["packet_id"],
            expires_utc=multi_packet()["expires_utc"],
            action="NOTHING",
        )
        reparsed = parse_comparison_line(
            round_trip,
            packet_id=multi_packet()["packet_id"],
            expires_utc=multi_packet()["expires_utc"],
        )
        self.assertEqual(reparsed["ranking"], parsed["ranking"])


if __name__ == "__main__":
    unittest.main()
