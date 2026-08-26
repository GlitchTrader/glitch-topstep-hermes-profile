import re
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
    parse_selected_candidate_handoff,
    serialize_comparison_line,
    validate_comparison_ledger,
    validate_selected_candidate_handoff,
)


def packet():
    return {
        "packet_id": "multi01-packet",
        "expires_utc": "2026-08-20T12:05:00Z",
        "instrument": "MNQ",
        "market_universe": {
            "candidates": [
                {"instrument": "MNQ", "execution_mode": "eligible"},
                {"instrument": "MES", "execution_mode": "eligible"},
                {"instrument": "MCL", "execution_mode": "eligible", "symbol_id": "F.US.MCLE"},
            ]
        },
        "account_selection": {
            "schema_version": "glitch.topstep.account_selection.v1",
            "mode": "single_active_position",
            "selected_instrument": "MNQ",
            "selected_contract_id": "CON.F.US.MNQ.U26",
            "scope_generation": 1,
            "scope_hash": "scope-hash",
            "simultaneous_exposure_enabled": False,
        },
        "account": {"total_open_contracts": 0},
    }


def filled_ledger_text(action: str = "NOTHING") -> str:
    fixture = (
        ROOT / "tests" / "fixtures" / "paired" / "multi01_comparison_ledger.txt"
    ).read_text(encoding="utf-8")
    text = fixture.replace("SELECTION_ACTION=NOTHING", f"SELECTION_ACTION={action}")
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
                "estimated_target_first_range=0.30-0.40;now_ev=POSITIVE;wait_price=20005;"
                "wait_ev=no improvement;decisive_reason=current-zone positive EV"
            )
        text = re.sub(r"(?m)^SELECTION_EV=.*$", ev, text)
    return text


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

    def test_parse_selected_candidate_handoff(self):
        intent = {
            "packet_id": packet()["packet_id"],
            "expires_utc": packet()["expires_utc"],
            "decision_audit": {"decisive_evidence": filled_ledger_text("ENTER_LONG")},
            "account_selection": packet()["account_selection"],
        }
        handoff = parse_selected_candidate_handoff(intent)
        self.assertIsNotNone(handoff)
        assert handoff is not None
        self.assertEqual(handoff["selected_instrument"], "MNQ")
        self.assertEqual(handoff["selection_action"], "ENTER_LONG")
        validate_selected_candidate_handoff(handoff, packet())

    def test_validate_selected_candidate_handoff_allows_flat_eligible_winner(self):
        mes_packet = {
            **packet(),
            "instrument": "MES",
            "account_selection": {
                **packet()["account_selection"],
                "selected_instrument": "MES",
                "selected_contract_id": "CON.F.US.MES.U26",
            },
        }
        intent = {
            "packet_id": packet()["packet_id"],
            "expires_utc": packet()["expires_utc"],
            "decision_audit": {
                "decisive_evidence": filled_ledger_text("ENTER_LONG").replace(
                    "SELECTION_INSTRUMENT=MNQ",
                    "SELECTION_INSTRUMENT=MES",
                )
            },
            "account_selection": {
                **packet()["account_selection"],
                "selected_instrument": "MES",
                "selected_contract_id": "CON.F.US.MES.U26",
            },
        }
        handoff = parse_selected_candidate_handoff(intent)
        assert handoff is not None
        validate_selected_candidate_handoff(handoff, mes_packet)

    def test_validate_selected_candidate_handoff_rejects_scope_mismatch(self):
        positioned_packet = {
            **packet(),
            "account": {"total_open_contracts": 1},
            "market_universe": {
                "candidates": [
                    {"instrument": "MNQ", "execution_mode": "selected", "open_contracts": 1},
                    {"instrument": "MES", "execution_mode": "flat_required"},
                    {"instrument": "MCL", "execution_mode": "flat_required"},
                ]
            },
        }
        intent = {
            "packet_id": packet()["packet_id"],
            "expires_utc": packet()["expires_utc"],
            "decision_audit": {"decisive_evidence": filled_ledger_text("ENTER_LONG")},
            "account_selection": {
                **packet()["account_selection"],
                "selected_instrument": "MES",
            },
        }
        handoff = parse_selected_candidate_handoff(intent)
        assert handoff is not None
        with self.assertRaisesRegex(ValueError, "selected_candidate_scope_mismatch"):
            validate_selected_candidate_handoff(handoff, positioned_packet)


if __name__ == "__main__":
    unittest.main()
