# Reviewer Merge Contract

Reviewer outputs are raw evidence for the editor loop. The orchestrator must
merge them into one deterministic `paper/state/reviewer-issues.yaml` before
gate decisions or revision planning.

## Inputs

Each reviewer writes a round-scoped file such as
`paper/state/reviewer-issues.chem-method-reviewer.r1.yaml`. The merge script
accepts one or more files with this shape:

```yaml
version: 1
issues:
  - id: R1
    reviewer: chem-method-reviewer
    severity: BLOCKER
    target_type: claim
    target_id: C1
    summary: "Missing convergence status for direct evidence."
    evidence_paths:
      - paper/inputs/manifest.yaml
    required_action: "Add convergence source or downgrade the claim."
    status: open
```

The compatibility alias `reviewer_role` is accepted as input and normalized to
`reviewer` in the merged output. Missing inputs become parser failures; missing
scientific evidence must remain a reviewer issue, not prose or a fabricated
calculation.

## Deterministic Merge Rules

- Sort issues by target type, target ID, normalized summary, normalized required
  action, reviewer, source ID, and source path.
- Ignore raw reviewer IDs as stable identifiers. Reassign merged IDs as `M001`,
  `M002`, ... after sorting.
- Treat two issues as duplicates when they share target type, target ID,
  normalized summary, and normalized required action.
- For duplicate same-location issues, keep one merged issue, collect all
  reviewers/source IDs/evidence paths, keep the strictest severity
  (`BLOCKER` > `MAJOR` > `MINOR`), and keep the most restrictive status
  (`open` before accepted/deferred/resolved/rejected).
- Duplicate raw issue IDs are allowed but produce a deterministic warning.
- Malformed issue files fail non-zero and must not overwrite the merged state.

## Command

```bash
python3 mesa/SKILL/TASK_MANUSCRIPT_LOOP/scripts/merge_reviewer_issues.py \
  --output paper/state/reviewer-issues.yaml \
  paper/state/reviewer-issues.*.r1.yaml
```

Review `stderr` warnings before advancing the stage. A duplicate warning is not
automatic approval; it is the editor's prompt to confirm the merged issue still
names the correct target and action.
