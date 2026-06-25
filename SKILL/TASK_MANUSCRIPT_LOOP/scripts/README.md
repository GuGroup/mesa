# Manuscript Loop Scripts

These scripts operate on a canonical MESA manuscript `paper/` workspace. They
are deterministic stdlib CLIs intended for fixture-driven regression tests and
agent-visible gate checks.

Core commands:

- `init_paper_workspace.py`: create or refresh the canonical `paper/` tree.
- `ingest_mesa_outputs.py`: normalize completed MESA envelopes, structures,
  tables, figures, and analyzer artifacts into `paper/inputs/`.
- `validate_claim_matrix.py`, `validate_figure_map.py`,
  `validate_reviewer_issues.py`, and `validate_section_contracts.py`: enforce
  prose-lock gate files.
- `notation_lint.py`: check declared notation against manuscript sections.
- `merge_reviewer_issues.py`: merge fixed-reviewer issue files
  deterministically.
- `init_revision_round.py`: create a file-backed review/revision audit
  directory for round comments, responses, diffs, and verification.

Run any command with `--help` for the required inputs and expected outputs.
