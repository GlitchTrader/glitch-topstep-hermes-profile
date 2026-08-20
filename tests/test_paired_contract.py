import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PairedContractTests(unittest.TestCase):
    def test_runtime_intent_schema_is_v3(self) -> None:
        contract = json.loads((ROOT / "paired-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["runtime_intent_schema"], "glitch.intent.v3")

    def test_operator_json_uses_runtime_intent_schema(self) -> None:
        operator = json.loads((ROOT / "operator.json").read_text(encoding="utf-8"))
        core = operator["loops"][0]
        self.assertEqual(core["output_schema"], "glitch.intent.v3")

    def test_active_configs_do_not_declare_v2_runtime(self) -> None:
        active_paths = (
            ROOT / "operator.json",
            ROOT / "docs" / "ARCHITECTURE.md",
            ROOT / "plugins" / "topstep-control" / "__init__.py",
        )
        for path in active_paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "glitch.intent.v2",
                text,
                f"{path.relative_to(ROOT)} still references glitch.intent.v2",
            )


if __name__ == "__main__":
    unittest.main()
