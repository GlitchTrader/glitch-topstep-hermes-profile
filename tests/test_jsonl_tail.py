import json
import tempfile
import unittest
from pathlib import Path

from common import read_jsonl, tail_jsonl


class JsonlTailTests(unittest.TestCase):
    def test_tail_jsonl_reads_last_rows_without_full_scan(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "events.jsonl"
            rows = [{"index": index} for index in range(5000)]
            path.write_text(
                "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
                encoding="utf-8",
            )
            tail = tail_jsonl(path, 3, tail_bytes=4096)
            full = read_jsonl(path)[-3:]
            self.assertEqual(tail, full)


if __name__ == "__main__":
    unittest.main()
