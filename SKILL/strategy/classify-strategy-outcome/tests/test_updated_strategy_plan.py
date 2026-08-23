from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).parents[1] / "scripts" / "prepare_strategy_outcome_input.py"
SPEC = importlib.util.spec_from_file_location("prepare_strategy_outcome_input", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def strategy(strategy_id: str) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "title": f"Strategy {strategy_id}",
        "decision_target": "Bounded causal link",
        "hypothesis": {"statement": "Original hypothesis"},
        "results": {
            "expected_computational_results": [{"statement": "Expected result"}],
            "computational_benchmark_comparisons": [{"statement": "Expected comparison"}],
        },
        "author_claim_support_if_successful": {
            "expected_strength": "bounded support",
            "maximum_supported_conclusion": "Bounded conclusion",
            "out_of_scope": ["Unmeasured behavior"],
        },
    }


class UpdatedStrategyPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_path = self.root / "generated.py"
        self.original = {
            "target_task": {"author_reported_claim": {"statement": "Author claim"}},
            "strategies": [strategy("S1"), strategy("S2")],
            "prioritization": {
                "recommended_order": ["S1", "S2"],
                "rationale": [{"statement": "Original order"}],
            },
        }
        self.original_path.write_text(
            f"generated_strategies = {self.original!r}\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_updated(self, item: dict[str, object]) -> Path:
        path = self.root / "updated.py"
        updated = {
            "revision_context": {"original_strategies_artifact": "generated.py"},
            "updated_strategies": [item],
            "updated_prioritization": {
                "recommended_order": [item["strategy_id"], "S2"],
                "rationale": [{"statement": "Revised order"}],
            },
        }
        path.write_text(f"updated_strategy_plan = {updated!r}\n", encoding="utf-8")
        return path

    def test_same_lineage_revision_inherits_classifier_boundary(self) -> None:
        revised = {
            "strategy_id": "S1R",
            "title": "Revised strategy",
            "origin": "repair_completed_strategy",
            "supersedes": "S1",
            "hypothesis": {"statement": "Revised hypothesis"},
            "results": {
                "expected_computational_results": [{"statement": "Revised result"}],
                "computational_benchmark_comparisons": [{"statement": "Revised comparison"}],
            },
        }
        path = self.write_updated(revised)
        normalized, original_path = MODULE.load_strategy_context_data(path, self.root, "S1R")
        current = next(item for item in normalized["strategies"] if item["strategy_id"] == "S1R")
        self.assertEqual(original_path, self.original_path)
        self.assertEqual(current["decision_target"], "Bounded causal link")
        self.assertEqual(current["hypothesis"]["statement"], "Revised hypothesis")
        self.assertEqual(normalized["prioritization"]["recommended_order"], ["S1R", "S2"])

    def test_new_direction_requires_complete_classifier_boundary(self) -> None:
        new_direction = {
            "strategy_id": "S3",
            "title": "New direction",
            "origin": "new_direction",
            "hypothesis": {"statement": "New hypothesis"},
            "results": {
                "expected_computational_results": [{"statement": "New result"}],
                "computational_benchmark_comparisons": [{"statement": "New comparison"}],
            },
        }
        path = self.write_updated(new_direction)
        with self.assertRaises(MODULE.AssemblyError):
            MODULE.load_strategy_context_data(path, self.root, "S3")

    def test_complete_new_direction_is_accepted_without_inheritance(self) -> None:
        new_direction = {
            "strategy_id": "S3",
            "title": "New direction",
            "decision_target": "New bounded target",
            "origin": "new_direction",
            "hypothesis": {"statement": "New hypothesis"},
            "results": {
                "expected_computational_results": [{"statement": "New result"}],
                "computational_benchmark_comparisons": [{"statement": "New comparison"}],
            },
            "author_claim_support_if_successful": {
                "expected_strength": "bounded support",
                "maximum_supported_conclusion": "New bounded conclusion",
                "out_of_scope": ["External behavior"],
            },
        }
        path = self.write_updated(new_direction)
        normalized, _ = MODULE.load_strategy_context_data(path, self.root, "S3")
        current = next(item for item in normalized["strategies"] if item["strategy_id"] == "S3")
        self.assertEqual(current["decision_target"], "New bounded target")

    def test_updated_plan_assembles_with_recipe_evidence(self) -> None:
        revised = {
            **strategy("S1"),
            "origin": "repair_completed_strategy",
            "hypothesis": {"statement": "Revised hypothesis"},
        }
        updated_path = self.write_updated(revised)
        recipe_root = self.root / "S1-R1_explicit_recipe"
        procedure = recipe_root / "P001"
        procedure.mkdir(parents=True)
        (recipe_root / "recipe_index.json").write_text(
            json.dumps({"strategy_id": "S1", "procedures": [{"procedure_id": "P001"}]}),
            encoding="utf-8",
        )
        evidence = self.root / "evidence.json"
        evidence.write_text(json.dumps({"value": 1}), encoding="utf-8")
        (procedure / "procedure_diagnosis.json").write_text(
            json.dumps(
                {
                    "procedure_id": "P001",
                    "verdict": "pass",
                    "coverage": {"complete": True},
                    "outputs_for_strategy_diagnosis": ["evidence.json"],
                    "execution_gaps": [],
                }
            ),
            encoding="utf-8",
        )
        payload = MODULE.assemble(
            SimpleNamespace(
                project_root=self.root,
                strategy_artifact=updated_path,
                strategy_id="S1",
                recipe_root=recipe_root,
                missing_evidence=[],
            )
        )
        self.assertEqual(payload["current_strategy_id"], "S1")
        self.assertEqual(payload["sources"]["original_strategy_artifact"], "generated.py")
        self.assertEqual(payload["scientific_outputs"][0]["data"], {"value": 1})


if __name__ == "__main__":
    unittest.main()
