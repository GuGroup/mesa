from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_reviewer_issues.py"


def load_module():
    spec = importlib.util.spec_from_file_location("merge_reviewer_issues", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules["merge_reviewer_issues"] = module
    spec.loader.exec_module(module)
    return module


class TestMergeReviewerIssues(unittest.TestCase):
    def test_merges_same_location_duplicates_when_reviewers_overlap(self) -> None:
        module = load_module()
        first = module.Issue(
            source_path=Path("claim.yaml"),
            source_id="R1",
            reviewer="chem-method-reviewer",
            severity=module.Severity.BLOCKER,
            target_type="claim",
            target_id="C1",
            summary="Missing convergence status",
            evidence_paths=("paper/inputs/manifest.yaml",),
            required_action="Add convergence evidence or downgrade the claim.",
            status=module.Status.OPEN,
        )
        second = module.Issue(
            source_path=Path("claim.yaml"),
            source_id="R1",
            reviewer="chem-claim-reviewer",
            severity=module.Severity.MAJOR,
            target_type="claim",
            target_id="C1",
            summary="Missing convergence status",
            evidence_paths=("paper/logic/claim-matrix.yaml",),
            required_action="Add convergence evidence or downgrade the claim.",
            status=module.Status.OPEN,
        )

        result = module.merge_issues((second, first))

        self.assertEqual(len(result.issues), 1)
        merged = result.issues[0]
        self.assertEqual(merged.stable_id, "M001")
        self.assertEqual(merged.severity, module.Severity.BLOCKER)
        self.assertEqual(merged.reviewers, ("chem-claim-reviewer", "chem-method-reviewer"))
        self.assertIn("duplicate source issue id R1", result.warnings)
        self.assertIn("merged duplicate target claim:C1", result.warnings)

    def test_cli_rewrites_duplicate_ids_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_a = tmp_path / "a.yaml"
            input_b = tmp_path / "b.yaml"
            output = tmp_path / "reviewer-issues.yaml"
            input_a.write_text(
                """version: 1
issues:
  - id: R1
    reviewer: chem-method-reviewer
    severity: MAJOR
    target_type: claim
    target_id: C2
    summary: "Reference state mismatch"
    evidence_paths:
      - paper/logic/claim-matrix.yaml
    required_action: "State the reference convention."
    status: open
""",
                encoding="utf-8",
            )
            input_b.write_text(
                """version: 1
issues:
  - id: R1
    reviewer: chem-significance-reviewer
    severity: MINOR
    target_type: figure
    target_id: F1
    summary: "Audience framing unclear"
    evidence_paths:
      - paper/logic/figure-map.yaml
    required_action: "Clarify why the figure matters."
    status: open
""",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--output",
                    str(output),
                    str(input_b),
                    str(input_a),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            text = output.read_text(encoding="utf-8")
            self.assertIn("id: M001", text)
            self.assertIn("id: M002", text)
            self.assertIn("duplicate source issue id R1", completed.stderr)
            self.assertLess(text.index("target_id: C2"), text.index("target_id: F1"))

    def test_cli_rejects_malformed_issue_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.yaml"
            out = Path(tmp) / "out.yaml"
            bad.write_text("version: 1\nissues:\n  - id: R1\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(out), str(bad)],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("missing required fields", completed.stderr)


if __name__ == "__main__":
    unittest.main()
