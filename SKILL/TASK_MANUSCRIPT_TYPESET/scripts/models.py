#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import models"
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final


BLOCKED_FIGURE_STATUSES: Final = frozenset({"blocked", "needs-source", "excluded"})
REQUIRED_NOTATION_KEYS: Final = ("systems", "methods", "energies", "figures", "abbreviations")
SECTION_ORDER: Final = (
    "abstract",
    "introduction",
    "results_and_discussion",
    "results",
    "discussion",
    "computational_methods",
    "methods",
    "conclusion",
    "si",
)


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class TypesetError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class SectionRecord:
    source_path: Path
    section_id: str
    path: str
    status: str
    allowed_claims: tuple[str, ...]
    required_figures: tuple[str, ...]
    required_sources: tuple[str, ...]
    blocked_by: tuple[str, ...]


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class ClaimRecord:
    source_path: Path
    claim_id: str
    status: str
    figures: tuple[str, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class FigureRecord:
    source_path: Path
    figure_id: str
    label: str
    title: str
    caption: str
    status: str
    source_files: tuple[str, ...]
    exported_files: tuple[str, ...]
    qa_files: tuple[str, ...]


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class ContractFiles:
    outline: Path
    sections: Path
    references: Path
    claims: Path
    figures: Path
    notation: Path

    def as_tuple(self) -> tuple[Path, ...]:
        return (self.outline, self.sections, self.references, self.claims, self.figures, self.notation)


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class PaperWorkspace:
    root: Path
    sections: tuple[SectionRecord, ...]
    claims: tuple[ClaimRecord, ...]
    figures: tuple[FigureRecord, ...]
    source_files: tuple[Path, ...]


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class AssemblyResult:
    workspace: PaperWorkspace
    source_digest: str
    manuscript_path: Path
    qa_path: Path
    manifest_path: Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Shared immutable data models and constants for TASK_MANUSCRIPT_TYPESET. "
            "Import this module from Word export helpers; it does not run an export directly."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
