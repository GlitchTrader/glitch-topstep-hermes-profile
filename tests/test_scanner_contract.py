import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scanner_contract import (  # noqa: E402
    MARKER,
    comparison_line_template,
    comparison_template,
    parse_comparison_line,
    serialize_comparison_line,
    validate_comparison_ledger,
)


def packet():
    return {
        "packet_id": "multi01-packet",
        "expires_utc": "2026-08-20T12:05:00Z",
        "instrument": "MNQ",
        "market_universe": {
            "candidates": [
                {"instrument": "MNQ"},
                {"instrument": "MES"},
                {"instrument": "MCL", "symbol_id": "F.US.MCLE"},
            ]
        },
        "account_selection": {
            "schema_version": "glitch.topstep.account_selection.v1",
            "mode": "single_contract",
            "selected_instrument": "MNQ",
            "selected_contract_id": "CON.F.US.MNQ.U26",
            "scope_generation": 1,
            "scope_hash": "scope-hash",
            "simultaneous_exposure_enabled": False,
        },
    }


def filled_ledger_text(action: str = "NOTHING") -> str:
    fixture = (
        ROOT / "tests" / "fixtures" / "paired" / "multi01_comparison_ledger.txt"
    ).read_text(encoding="utf-8")
    return fixture.replace("SELECTION_ACTION=NOTHING", f"SELECTION_ACTION={action}")


class ScannerContractTests(unittest.TestCase):
    def test_template_lists_every_candidate(self):
        template = comparison_line_template(packet())
        self.assertIn("INSTRUMENT MNQ:", template)
        self.assertIn("INSTRUMENT MES:", template)
        self.assertIn("INSTRUMENT MCL:", template)
        self.assertTrue(template.startswith(MARKER + "\n"))

    def test_complete_line_passes(self):
        validated = validate_comparison_ledger(filled_ledger_text(), packet(), action="NOTHING")
        self.assertEqual(validated["ranking"], ["MNQ", "MES", "MCL"])
        self.assertEqual(validated["selected_instrument"], "MNQ")

    def test_preserves_exact_account_selection_envelope(self):
        validated = validate_comparison_ledger(filled_ledger_text(), packet(), action="NOTHING")
        self.assertEqual(validated["selected_instrument"], "MNQ")

    def test_requires_complete_candidate_ledger_before_ranking(self):
        validated = validate_comparison_ledger(filled_ledger_text(), packet(), action="NOTHING")
        self.assertEqual(validated["ranking"], ["MNQ", "MES", "MCL"])

    def test_missing_instrument_rejected(self):
        text = filled_ledger_text()
        text = text.split("INSTRUMENT MES:", 1)[0] + text.split("INSTRUMENT MCL:", 1)[1]
        with self.assertRaisesRegex(ValueError, "instrument_candidates_incomplete"):
            validate_comparison_ledger(text, packet(), action="NOTHING")

    def test_placeholder_rejected(self):
        text = filled_ledger_text().replace(
            "CURRENT_AUCTION=partial 1m below 5m VWAP; quote fresh; observation ready",
            "CURRENT_AUCTION=REPLACE_WITH_CURRENT_PACKET_EVIDENCE",
        )
        with self.assertRaisesRegex(ValueError, "instrument_candidate_field_invalid"):
            validate_comparison_ledger(text, packet(), action="NOTHING")

    def test_round_trip(self):
        parsed = parse_comparison_line(
            filled_ledger_text(),
            packet_id=packet()["packet_id"],
            expires_utc=packet()["expires_utc"],
        )
        round_trip = serialize_comparison_line(
            parsed,
            packet_id=packet()["packet_id"],
            expires_utc=packet()["expires_utc"],
            action="NOTHING",
        )
        reparsed = parse_comparison_line(
            round_trip,
            packet_id=packet()["packet_id"],
            expires_utc=packet()["expires_utc"],
        )
        self.assertEqual(
            [row["instrument"] for row in reparsed["candidates"]],
            [row["instrument"] for row in parsed["candidates"]],
        )
        self.assertEqual(reparsed["ranking"], parsed["ranking"])

    def test_comparison_template_alias(self):
        self.assertEqual(comparison_template(packet()), comparison_line_template(packet()))


if __name__ == "__main__":
    unittest.main()
