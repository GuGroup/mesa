# Typst Build Contract

`build_typst.py` converts canonical paper files into a deterministic Typst build
directory. It never rewrites the `paper/` workspace.

## Check-Only Mode

`--check-only` must run with only Python standard-library dependencies. It:

- confirms the paper root and required manuscript/logic files exist;
- checks section contracts against claim and figure IDs;
- checks figure source, exported, and QA files named by `figure-map.yaml`;
- checks evidence paths named by `claim-matrix.yaml`;
- writes `manuscript.typ`, `assets/nature-mesa.typ`,
  `qa/crossref-qa.txt`, and `build-manifest.json`;
- exits non-zero if a previous PDF in the output directory is stale relative to
  the current source digest.

## Real Build Mode

Without `--check-only`, the script runs `typst compile` after the same checks.
If Typst is unavailable, it fails with an actionable message naming
`--check-only` and `--typst-bin`.

## Source Safety

Markdown sections are emitted as Typst raw blocks with a delimiter longer than
any backtick run in the source text. This keeps Markdown text and prompt-like
instructions from being executed as Typst code.
