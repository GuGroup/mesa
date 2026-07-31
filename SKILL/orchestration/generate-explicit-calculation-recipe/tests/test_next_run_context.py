from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from classify_procedure_information import procedure_inputs
from generate_explicit_recipe import attach_next_run
from map_strategy_to_procedures import source_catalog


class NextRunContextTest(unittest.TestCase):
    def test_next_run_is_cataloged_and_resolved_without_changing_procedures(self):
        strategy = {
            "strategy_id": "S2",
            "computational": {"procedures": ["Run the target calculation."]},
            "results": {"expected": "Target result"},
        }
        classification = {
            "schema_version": "1.0",
            "classification": "prerequisite",
            "next_run": {
                "mode": "prerequisite",
                "target_strategy_id": "S2",
                "input_sources": ["analysis/evaluation.json"],
                "report": [
                    "Inherited value: Carry the prior descriptor into S2.",
                    "Run objective: Test the S2 hypothesis using that descriptor.",
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            next_run_path = root / "classification.json"
            next_run_path.write_text(json.dumps(classification), encoding="utf-8")
            data = attach_next_run(strategy, next_run_path)
            pointers = {
                item["source_json_pointer"] for item in source_catalog(data)
            }
            self.assertIn("/next_run/report/0", pointers)
            self.assertEqual(
                data["computational"]["procedures"],
                ["Run the target calculation."],
            )

            procedure = root / "recipes" / "P001"
            procedure.mkdir(parents=True)
            (procedure / "procedure.json").write_text(
                json.dumps({"source_text": "Run the target calculation."}),
                encoding="utf-8",
            )
            (procedure / "mapping.json").write_text(
                json.dumps(
                    {"source_json_pointers": ["/next_run/report/0"]}
                ),
                encoding="utf-8",
            )
            items = procedure_inputs(data, root / "recipes")
            self.assertEqual(
                items[0]["sources"][0]["value"],
                "Inherited value: Carry the prior descriptor into S2.",
            )

    def test_target_mismatch_is_rejected(self):
        strategy = {
            "strategy_id": "S3",
            "computational": {"procedures": ["Run calculation."]},
        }
        classification = {
            "schema_version": "1.0",
            "classification": "prerequisite",
            "next_run": {
                "mode": "prerequisite",
                "target_strategy_id": "S2",
                "input_sources": ["analysis/evaluation.json"],
                "report": [
                    "Inherited value: Carry the prior result into S2.",
                    "Run objective: Test the S2 hypothesis.",
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "classification.json"
            path.write_text(json.dumps(classification), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "target"):
                attach_next_run(strategy, path)

    def test_extend_and_replace_contexts_are_accepted(self):
        strategy = {
            "strategy_id": "S1",
            "computational": {"procedures": ["Run calculation."]},
        }
        cases = [
            {
                "schema_version": "1.0",
                "classification": "extend_strategy",
                "next_run": {
                    "mode": "extend_strategy",
                    "target_strategy_id": "S1",
                    "input_sources": ["analysis/evaluation.json"],
                    "report": [
                        "Evidence gap: One bounded comparison is absent.",
                        "Additional procedure: Compute that comparison.",
                        "Expected evidence: Produce a discriminating result.",
                    ],
                },
            },
            {
                "schema_version": "1.0",
                "classification": "replace_strategy",
                "next_run": {
                    "mode": "replace_strategy",
                    "target_strategy_id": None,
                    "input_sources": ["analysis/evaluation.json"],
                    "report": [
                        "Failed expectation: The predicted advantage was absent.",
                        "Observed evidence: The trend opposed the hypothesis.",
                        "Replacement implication: Avoid the unsupported direction.",
                        "Replacement hypothesis: Another mechanism controls activity.",
                        "Procedure: Compute a bounded mechanism comparison.",
                        "Expected evidence: Produce a discriminating comparison.",
                    ],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for index, classification in enumerate(cases):
                path = Path(temporary) / f"classification-{index}.json"
                path.write_text(json.dumps(classification), encoding="utf-8")
                merged = attach_next_run(strategy, path)
                self.assertEqual(
                    merged["next_run"]["mode"],
                    classification["classification"],
                )


if __name__ == "__main__":
    unittest.main()
