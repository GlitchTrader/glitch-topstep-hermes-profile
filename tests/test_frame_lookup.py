import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from parity import frame_for_packet_id, packet_for_outbox_id  # noqa: E402


class FrameLookupTests(unittest.TestCase):
    def test_shared_lookup_returns_frame_and_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            frames = state / "minute-frames"
            frames.mkdir(parents=True)
            (frames / "broken.json").write_text("{", encoding="utf-8")
            expected = {
                "schema_version": "glitch.topstep.minute_frame.v2",
                "minute_id": "20260802T1200Z",
                "packet": {"packet_id": "packet-1", "market": {"last": 20000}},
            }
            (frames / "20260802T1200Z.json").write_text(
                json.dumps(expected),
                encoding="utf-8",
            )

            self.assertEqual(frame_for_packet_id(frames, "packet-1"), expected)
            self.assertEqual(packet_for_outbox_id(state, "packet-1"), expected["packet"])
            self.assertIsNone(frame_for_packet_id(frames, "missing"))
            self.assertIsNone(packet_for_outbox_id(state, "missing"))


if __name__ == "__main__":
    unittest.main()
