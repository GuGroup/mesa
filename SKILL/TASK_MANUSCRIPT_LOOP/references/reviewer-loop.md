# Reviewer Loop Contract

Reviewer agents are read-only issue producers. They inspect the canonical
workspace and write structured issues; they must not edit prose, change figures,
invent calculations, invent citations, invent line numbers, or create new
scientific claims.

## Reviewer Inputs

Reviewers may read:

- `paper/inputs/manifest.yaml`
- `paper/logic/result-inventory.md`
- `paper/logic/claim-matrix.yaml`
- `paper/logic/story-spine.md`
- `paper/logic/figure-map.yaml`
- `paper/logic/reviewer-risks.md`
- `paper/manuscript/section-contracts.yaml`
- named prose chunks under `paper/manuscript/sections/` only when the review
  stage allows prose review
- QA files under `paper/figures/qa/`

## Reviewer Outputs

Each reviewer writes a round-scoped raw issue file such as
`paper/state/reviewer-issues.chem-method-reviewer.r1.yaml`. The editor loop
merges raw files into `paper/state/reviewer-issues.yaml` using
`references/reviewer-merge-contract.md`.

Merged review issues are stored in `paper/state/reviewer-issues.yaml`:

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

Required issue fields are `id`, `reviewer`, `severity`, `target_type`,
`target_id`, `summary`, `evidence_paths`, `required_action`, and `status`.
Severity is `BLOCKER`, `MAJOR`, or `MINOR`. Status is `open`, `accepted`,
`resolved`, `deferred`, or `rejected-with-rationale`.

## Round Control

Default reviewer loop:

- R1 full critique: run `chem-significance-reviewer`,
  `chem-method-reviewer`, and `chem-claim-reviewer` in parallel against the
  Gate 0, claim, figure, architecture, and allowed prose files.
- R2 changed-files verification: reviewers inspect only R1 resolutions,
  changed logic/prose/figure files, and any newly introduced issues.
- R3 coherence and polish-readiness: reviewers check remaining cross-document
  consistency and whether prose can proceed or final polish can begin.

The editor role is the main manuscript-loop session, not another reviewer. It
merges raw reviewer files, records synthesis and round events in
`paper/state/ledger.jsonl`, and decides whether the gate advances. Stop after
round 3 or earlier when there are no remaining `BLOCKER` or `MAJOR` issues. If
any `BLOCKER` remains after R3, halt and report the blocker; do not fake
resolution.

## Gate Rules

- No `BLOCKER` issue may remain open before section prose generation.
- Major scientific issues must be resolved, accepted into caveats, or deferred
  with explicit rationale before prose.
- Reviewers may mark missing inputs as blockers; they may not fill the gap by
  guessing.
- Revision editors may patch only the chunks named by accepted issues.
