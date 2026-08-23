from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SELECT = SKILL_ROOT / "scripts" / "select_next_strategy.py"
STATUS = SKILL_ROOT / "scripts" / "manage_strategy_status.py"


class StrategyPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.status_dir = self.root / "status"
        self.artifact = self.root / "strategies.json"
        self.recipe_root = self.root / "recipe"
        self.recipe_root.mkdir()
        (self.recipe_root / "recipe_index.json").write_text("{}\n", encoding="utf-8")
        (self.recipe_root / "execution_plan.json").write_text("{}\n", encoding="utf-8")
        self.artifact.write_text(
            json.dumps(
                {
                    "strategies": [
                        {"strategy_id": "S1", "title": "One"},
                        {"strategy_id": "S2", "title": "Two"},
                        {"strategy_id": "S3", "title": "Three"},
                    ],
                    "prioritization": {"recommended_order": ["S1", "S2", "S3"]},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_command(self, *args: object, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, *(str(arg) for arg in args)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr or completed.stdout)
        return completed

    def select(self, name: str, expected: int = 0) -> dict[str, object]:
        output = self.root / name
        self.run_command(
            SELECT,
            "--strategy-artifact",
            self.artifact,
            "--status-dir",
            self.status_dir,
            "--max-active-strategies",
            2,
            "--output",
            output,
            expected=expected,
        )
        return json.loads(output.read_text(encoding="utf-8"))

    def activate(self, lineage: str, strategy: str, agent: str, *extra: object, expected: int = 0) -> None:
        self.run_command(
            STATUS,
            "activate",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            lineage,
            "--strategy-id",
            strategy,
            "--strategy-artifact",
            self.artifact,
            "--recipe-root",
            self.recipe_root,
            "--agent-id",
            agent,
            "--max-active",
            2,
            *extra,
            expected=expected,
        )

    def outcome(self, lineage: str, strategy: str, classification: str, report: Path) -> None:
        self.run_command(
            STATUS,
            "record-outcome",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            lineage,
            "--strategy-id",
            strategy,
            "--classification",
            classification,
            "--report",
            report,
        )

    def test_active_lineages_fill_capacity_without_duplicate_selection(self) -> None:
        self.assertEqual(self.select("first.json")["selected_strategy_id"], "S1")
        self.activate("S1", "S1", "agent-1")
        self.assertEqual(self.select("second.json")["selected_strategy_id"], "S2")
        self.activate("S2", "S2", "agent-2")
        capacity = self.select("capacity.json")
        self.assertEqual(capacity["status"], "at_capacity")
        self.assertEqual(capacity["active_strategy_lineages"], 2)

    def test_manuscript_ready_stops_new_launches_and_records_one_winner(self) -> None:
        self.activate("S1", "S1", "agent-1")
        self.activate("S2", "S2", "agent-2")
        report_one = self.root / "S1.md"
        report_two = self.root / "S2.md"
        report_one.write_text("# S1 result\n", encoding="utf-8")
        report_two.write_text("# S2 result\n", encoding="utf-8")
        self.outcome("S1", "S1", "manuscript_ready", report_one)
        stopped = self.select("stopped.json")
        self.assertEqual(stopped["status"], "launch_stopped")
        early_winner = self.root / "early_winner.json"
        self.run_command(
            STATUS,
            "record-winner",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            "S1",
            "--reason",
            "Strongest complete evidence.",
            "--evidence-source",
            report_one,
            "--output",
            early_winner,
            expected=1,
        )
        self.outcome("S2", "S2", "replace_strategy", report_two)

        winner = self.root / "winning_strategy.json"
        self.run_command(
            STATUS,
            "record-winner",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            "S1",
            "--reason",
            "Strongest complete evidence.",
            "--evidence-source",
            report_one,
            "--output",
            winner,
        )
        payload = json.loads(winner.read_text(encoding="utf-8"))
        self.assertEqual(payload["winning_strategy_id"], "S1")

    def test_extension_keeps_agent_and_gpu_lease(self) -> None:
        self.activate("S1", "S1", "agent-1", "--run-id", "S1-R0", "--gpu-index", 0)
        self.activate("S2", "S2", "agent-2", "--gpu-index", 0, expected=1)
        report = self.root / "S1.md"
        revised = self.root / "revised.py"
        report.write_text("# S1 result\n", encoding="utf-8")
        revised.write_text("updated_strategy_plan = {}\n", encoding="utf-8")
        self.run_command(
            STATUS,
            "record-outcome",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            "S1",
            "--strategy-id",
            "S1",
            "--classification",
            "extend_strategy",
            "--report",
            report,
            "--next-strategy-id",
            "S1",
            "--next-run-id",
            "S1-R1",
            "--next-strategy-artifact",
            revised,
        )
        record = json.loads((self.status_dir / "S1.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["agent_id"], "agent-1")
        self.assertTrue(record["gpu_assignment"]["lease_active"])
        self.assertEqual(record["current_strategy_id"], "S1")
        self.assertEqual(record["current_run_id"], "S1-R1")
        self.activate("S1", "S1", "agent-3", "--run-id", "S1-R1", expected=1)
        self.activate("S1", "S1", "agent-1", "--run-id", "S1-R1")
        continued = json.loads((self.status_dir / "S1.json").read_text(encoding="utf-8"))
        self.assertIsNone(continued["classification"])
        self.assertIsNone(continued["strategy_result_report"])

    def test_active_revision_materializes_after_launch_stop(self) -> None:
        self.activate("S1", "S1", "agent-1")
        self.activate("S2", "S2", "agent-2")
        ready_report = self.root / "S2.md"
        ready_report.write_text("# S2 result\n", encoding="utf-8")
        self.outcome("S2", "S2", "manuscript_ready", ready_report)
        updated = self.root / "updated.json"
        updated.write_text(
            json.dumps(
                {
                    "updated_strategies": [
                        {
                            "strategy_id": "S1",
                            "title": "Revised one",
                            "hypothesis": {"statement": "Revised"},
                        }
                    ],
                    "updated_prioritization": {"recommended_order": ["S1"]},
                }
            ),
            encoding="utf-8",
        )
        output = self.root / "revision.json"
        self.run_command(
            SELECT,
            "--strategy-artifact",
            updated,
            "--status-dir",
            self.status_dir,
            "--max-active-strategies",
            2,
            "--continue-lineage",
            "S1",
            "--strategy-id",
            "S1",
            "--output",
            output,
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["selection_mode"], "lineage_continuation")
        self.assertEqual(payload["selected_strategy_id"], "S1")

    def test_winner_comparison_requires_every_ready_candidate(self) -> None:
        self.activate("S1", "S1", "agent-1")
        self.activate("S2", "S2", "agent-2")
        report_one = self.root / "S1.md"
        report_two = self.root / "S2.md"
        report_one.write_text("# S1 result\n", encoding="utf-8")
        report_two.write_text("# S2 result\n", encoding="utf-8")
        self.outcome("S1", "S1", "manuscript_ready", report_one)
        self.outcome("S2", "S2", "manuscript_ready", report_two)
        winner = self.root / "winning_strategy.json"
        base = [
            STATUS,
            "record-winner",
            "--status-dir",
            self.status_dir,
            "--lineage-id",
            "S1",
            "--reason",
            "Stronger claim coverage.",
            "--evidence-source",
            report_one,
            "--output",
            winner,
        ]
        self.run_command(*base, expected=1)
        self.run_command(
            *base[:-2],
            "--evidence-source",
            report_two,
            "--output",
            winner,
        )
        payload = json.loads(winner.read_text(encoding="utf-8"))
        self.assertEqual(payload["winning_lineage_id"], "S1")
        self.assertEqual(len(payload["evidence_sources"]), 2)


if __name__ == "__main__":
    unittest.main()
