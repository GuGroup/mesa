from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = TASK_ROOT / "scripts"
INIT_SCRIPT = SCRIPTS / "init_paper_workspace.py"
INGEST_SCRIPT = SCRIPTS / "ingest_mesa_outputs.py"
FIXTURE_OUTPUTS = TASK_ROOT / "examples" / "fixture_project" / "mesa_outputs"


def run_script(script: str | Path, *args: str | Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script), *(str(arg) for arg in args)]
    return subprocess.run(command, text=True, capture_output=True, check=False)


class GlobalSecurityRegressionTests(unittest.TestCase):
    def test_ingest_escapes_untrusted_envelope_text_in_svg(self) -> None:
        # Given: a completed MESA envelope containing XML markup in text fields.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "mesa_outputs"
            shutil.copytree(FIXTURE_OUTPUTS, outputs)
            envelope = outputs / "task_envelopes" / "reaction_energy.json"
            data = json.loads(envelope.read_text(encoding="utf-8"))
            data["data"]["system_id"] = "CO<script>alert(1)</script>_on_Pt111"
            data["data"]["value"] = "<script>alert(1)</script>"
            data["data"]["units"] = "eV<script>alert(1)</script>"
            envelope.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.assertEqual(run_script(INIT_SCRIPT, "--root", root).returncode, 0)

            # When: ingest generates the placeholder figure.
            result = run_script(INGEST_SCRIPT, "--paper", root / "paper", "--input", outputs)

            # Then: the SVG contains escaped text and no executable script tag.
            self.assertEqual(result.returncode, 0, result.stderr)
            svg = (root / "paper" / "figures" / "exported" / "fig1_energy_diagram.placeholder.svg").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("<script>", svg)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", svg)

    def test_init_rejects_symlinked_paper_root_without_outside_writes(self) -> None:
        # Given: paper/ is a symlink to an outside directory.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_paper = root / "outside-paper"
            outside_paper.mkdir()
            (root / "paper").symlink_to(outside_paper, target_is_directory=True)

            # When: init attempts to seed current-stage.yaml.
            result = run_script(INIT_SCRIPT, "--root", root)

            # Then: the command fails closed and does not write through the symlink.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr.lower())
            self.assertFalse((outside_paper / "state" / "current-stage.yaml").exists())

    def test_ingest_rejects_symlinked_state_dir_without_outside_ledger_write(self) -> None:
        # Given: an initialized paper workspace whose state/ directory is redirected.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_state = root / "outside-state"
            outside_state.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, "--root", root).returncode, 0)
            shutil.rmtree(root / "paper" / "state")
            (root / "paper" / "state").symlink_to(outside_state, target_is_directory=True)

            # When: ingest attempts to update current-stage.yaml and ledger.jsonl.
            result = run_script(INGEST_SCRIPT, "--paper", root / "paper", "--input", FIXTURE_OUTPUTS)

            # Then: both writes are blocked before any outside state file is created.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr.lower())
            self.assertFalse((outside_state / "current-stage.yaml").exists())
            self.assertFalse((outside_state / "ledger.jsonl").exists())

    def test_detached_claim_matrix_with_paper_traversal_fails_closed(self) -> None:
        # Given: a copied claim matrix outside any canonical paper/ tree.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claim-matrix.yaml"
            path.write_text(
                json.dumps(
                    {
                        "claims": [
                            {
                                "id": "C1",
                                "level": "main",
                                "statement": "Claim one.",
                                "status": "supported",
                                "evidence": [
                                    {
                                        "id": "E1",
                                        "source_id": "S1",
                                        "path": "paper/inputs/../../outside.txt",
                                        "relation": "direct",
                                        "summary": "Escaped source.",
                                    }
                                ],
                                "figures": [],
                                "assumptions": [],
                                "caveats": [],
                                "risks": [],
                                "allowed_sections": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            # When: the standalone validator cannot infer a paper root.
            result = run_script(SCRIPTS / "validate_claim_matrix.py", path)

            # Then: it refuses to certify paper/... paths as ok.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot infer paper root", result.stderr.lower())

    def test_detached_figure_map_with_paper_traversal_fails_closed(self) -> None:
        # Given: a copied figure map outside any canonical paper/ tree.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "figure-map.yaml"
            path.write_text(
                json.dumps(
                    {
                        "figures": [
                            {
                                "id": "F1",
                                "label": "Figure 1",
                                "role": "main",
                                "title": "Figure one",
                                "claim_ids": ["C1"],
                                "source_files": ["paper/figures/source/../../../outside.spec.yaml"],
                                "exported_files": [],
                                "qa_files": [],
                                "status": "generated",
                                "blockers": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            # When: the standalone validator cannot infer a paper root.
            result = run_script(SCRIPTS / "validate_figure_map.py", path)

            # Then: it fails closed instead of printing ok.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot infer paper root", result.stderr.lower())

    def test_detached_section_contracts_with_paper_traversal_fails_closed(self) -> None:
        # Given: copied section contracts outside any canonical paper/ tree.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "section-contracts.yaml"
            path.write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "id": "results",
                                "path": "paper/manuscript/sections/../../../outside.md",
                                "status": "ready-to-draft",
                                "allowed_claims": ["C1"],
                                "required_figures": [],
                                "required_sources": ["paper/inputs/../../outside.txt"],
                                "required_caveats": [],
                                "blocked_by": [],
                                "chunk_policy": "single",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            # When: the standalone validator cannot infer a paper root.
            result = run_script(SCRIPTS / "validate_section_contracts.py", path)

            # Then: it fails closed instead of printing ok.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot infer paper root", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
