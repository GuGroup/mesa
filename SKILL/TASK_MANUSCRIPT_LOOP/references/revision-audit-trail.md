# Revision Audit Trail Contract

Every manuscript review or revision round must leave enough file-backed history
to reconstruct reviewer comments, author responses, exact edits, and
verification results without relying on chat memory.

## Round Directory

Create one directory per round:

```text
paper/revisions/round-001/
├── README.md
├── reviewer-comments.raw/
├── reviewer-issues.merged.yaml
├── author-response.yaml
├── change-plan.yaml
├── patches/
├── changed-files.md
├── snapshots/
└── verification.md
```

Use `scripts/init_revision_round.py` to create the directory before running
reviewer or revision agents:

```bash
python3 mesa/SKILL/TASK_MANUSCRIPT_LOOP/scripts/init_revision_round.py --paper paper --round 1
```

## Required Records

- `reviewer-comments.raw/`: one raw file per reviewer or external comment
  source, preserving the unmerged issue text.
- `reviewer-issues.merged.yaml`: deterministic merged issue state for the
  round. It may be copied from `paper/state/reviewer-issues.yaml` after merge.
- `author-response.yaml`: point-by-point response records. Each response must
  name issue IDs, decision, rationale, touched claim IDs, touched files, and
  remaining risk.
- `change-plan.yaml`: accepted edits before implementation. Each change must
  name issue IDs, target files/chunks, intended action, and required
  verification.
- `patches/`: unified diffs for applied manuscript/logic/figure changes. Patch
  filenames should include the issue ID or change ID when possible.
- `changed-files.md`: human-readable index of touched files, issue IDs, and
  patch files.
- `snapshots/`: optional before/after copies of small source files when a diff
  alone is not enough for review.
- `verification.md`: commands, validators, reviewer re-checks, and remaining
  caveats for the round.

## Revision Rules

- Revision editors may patch only files named in `change-plan.yaml`.
- Every patch must map to at least one reviewer issue ID or accepted editor
  change ID.
- Scientific changes must update canonical `paper/` source files, not generated
  DOCX exports.
- If an issue requires missing calculations, missing figures, missing
  references, or unsupported claims, record it as unresolved rather than
  smoothing the prose.
- A round may close only after `verification.md` names the commands or reviewer
  checks that passed and lists remaining unresolved issues.
