from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import classify_procedure_information as classifier
import generate_explicit_recipe as generator
import map_strategy_to_procedures as mapper


class ThreeStageContractTest(unittest.TestCase):
    def test_each_stage_writes_only_its_declared_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            strategy_path = root / "strategy.json"
            recipe_root = root / "recipes"
            strategy_path.write_text(
                json.dumps(
                    {
                        "selected_strategy": {
                            "strategy_id": "S1",
                            "experiment": {
                                "computational": {
                                    "procedures": ["Compute the target comparison."]
                                },
                                "condition": "fixed condition",
                            },
                            "results": {"expected": "target result"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                sys,
                "argv",
                [
                    str(generator.__file__),
                    "--strategy",
                    str(strategy_path),
                    "--out",
                    str(recipe_root),
                ],
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(generator.main(), 0)

            procedure = recipe_root / "P001"
            self.assertEqual(
                json.loads((procedure / "procedure.json").read_text(encoding="utf-8")),
                {"source_text": "Compute the target comparison."},
            )
            self.assertFalse((procedure / "mapping.json").exists())
            self.assertFalse((recipe_root / "recipe_index.json").exists())

            with (
                patch.object(
                    mapper,
                    "map_with_llm",
                    return_value={"P001": ["S0001", "S0002"]},
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        str(mapper.__file__),
                        "--strategy",
                        str(strategy_path),
                        "--recipe-root",
                        str(recipe_root),
                    ],
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(mapper.main(), 0)

            self.assertTrue((procedure / "mapping.json").is_file())
            self.assertFalse((procedure / "calculations").exists())
            self.assertFalse((recipe_root / "recipe_index.json").exists())

            with (
                patch.object(
                    classifier,
                    "classify_with_llm",
                    return_value={
                        "p_shared": ["M001"],
                        "c_tasks": [
                            {
                                "task": "Compute the target comparison.",
                                "source_ids": ["M002"],
                            }
                        ],
                    },
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        str(classifier.__file__),
                        "--strategy",
                        str(strategy_path),
                        "--recipe-root",
                        str(recipe_root),
                    ],
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(classifier.main(), 0)

            recipe = json.loads(
                (
                    procedure / "calculations" / "C001" / "recipe.json"
                ).read_text(encoding="utf-8")
            )
            index = json.loads(
                (recipe_root / "recipe_index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(recipe["procedure_id"], "P001")
            self.assertEqual(recipe["calculation_id"], "C001")
            self.assertEqual(index["strategy_id"], "S1")
            self.assertEqual(
                index["procedures"][0]["calculations"][0]["calculation_id"],
                "C001",
            )


if __name__ == "__main__":
    unittest.main()
