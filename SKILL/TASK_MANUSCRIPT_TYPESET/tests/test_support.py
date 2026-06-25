from __future__ import annotations

import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = TASK_ROOT / "scripts" / "build_typst.py"
EXPORT_SCRIPT = TASK_ROOT / "scripts" / "export_docx.py"
FIXTURE_PAPER = (
    TASK_ROOT.parent / "TASK_MANUSCRIPT_LOOP" / "examples" / "fixture_project" / "paper"
)


def copy_fixture(tmp_path: Path) -> Path:
    paper = tmp_path / "paper"
    shutil.copytree(FIXTURE_PAPER, paper)
    return paper
