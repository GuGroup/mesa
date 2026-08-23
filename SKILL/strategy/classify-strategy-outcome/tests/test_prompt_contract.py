from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "classify_strategy_outcome.py"
SPEC = importlib.util.spec_from_file_location("classify_strategy_outcome", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class PromptContractTests(unittest.TestCase):
    def test_prompt_matches_output_schema_and_bounds_large_outputs(self) -> None:
        small = {"source": "small.json", "value": "accepted"}
        large = {
            "source": "large.json",
            "value": "x" * MODULE.MAX_PROMPT_SCIENTIFIC_OUTPUT_BYTES,
        }
        payload = json.loads(
            MODULE.build_prompt({"scientific_outputs": [small, large]})
        )
        schema = payload["contract"]["output_schema"]
        self.assertNotIn("support_strength", schema)
        self.assertEqual(
            payload["strategy_outcome_input"]["scientific_outputs"], [small]
        )
        self.assertEqual(
            payload["contract"]["prompt_scope"]["omitted_large_scientific_outputs"],
            ["large.json"],
        )


if __name__ == "__main__":
    unittest.main()
