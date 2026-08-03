"""One-shot test fixture migration for GTHP-010. Deletes itself after applying."""
from pathlib import Path

root = Path(__file__).resolve().parent
path = root / "tests" / "test_direct_cycle.py"
text = path.read_text(encoding="utf-8")
marker = "    def test_pending_outbox_validates_against_stored_packet_not_current(self):\n"
if text.count(marker) != 1:
    raise SystemExit("pending outbox test marker mismatch")
head, tail = text.split(marker, 1)
old = '                if path == "/health":\n                    return (200, {"status": "ok"})\n'
new = '''                if path == "/health":
                    return (200, {
                        "schema_version": "glitch.direct.health.v2",
                        "status": "ok",
                        "compatibility": {
                            "gateway_name": "glitch-topstep",
                            "gateway_version": "0.1.2",
                            "health_schema": "glitch.direct.health.v2",
                            "intent_schemas": ["glitch.intent.v2"],
                            "decision_packet_schemas": [
                                "glitch.direct.decision_packet.v1",
                                "glitch.direct.decision_packet.v2",
                            ],
                            "capabilities": [
                                "packet_supported_actions",
                                "position_management",
                                "tranche_ownership",
                                "native_protection",
                                "durable_mutation_receipts",
                                "restart_reconciliation",
                            ],
                        },
                    })
'''
if tail.count(old) < 1:
    raise SystemExit("legacy health fixture mismatch")
path.write_text(head + marker + tail.replace(old, new, 1), encoding="utf-8")
Path(__file__).unlink()
