# Workflow Contract

This skill manages a post-computation manuscript loop for Nature-family targets.
It consumes completed MESA outputs and maintains a deterministic `paper/`
workspace. Generated exports are outside this skill; Markdown, YAML, JSONL, and
figure source files remain canonical.

## Canonical Workspace

```text
paper/
├── inputs/
│   ├── manifest.yaml
│   ├── results/
│   ├── structures/
│   ├── tables/
│   ├── figures/
│   ├── prior-notes/
│   └── references/
├── logic/
│   ├── result-inventory.md
│   ├── claim-matrix.yaml
│   ├── story-spine.md
│   ├── figure-map.yaml
│   ├── reviewer-risks.md
│   └── notation.yaml
├── state/
│   ├── ledger.jsonl
│   ├── current-stage.yaml
│   ├── reviewer-issues.yaml
│   ├── revision-plan.yaml
│   └── qa-checks.yaml
├── manuscript/
│   ├── outline.md
│   ├── section-contracts.yaml
│   ├── sections/
│   ├── si/
│   └── references.bib
└── figures/
    ├── source/
    ├── exported/
    └── qa/
```

## Stage Order

0. Intake: normalize completed MESA artifacts into `paper/inputs/manifest.yaml`
   and `paper/logic/result-inventory.md`.
1. Results inventory: confirm primary, exploratory, failed, and excluded
   artifacts are separated.
2. Claim matrix: encode claims, evidence, assumptions, caveats, and risks in
   `paper/logic/claim-matrix.yaml`.
3. Logic review: read-only reviewers create or update risks and issues; blockers
   must be resolved before architecture.
4. Manuscript architecture: define the story spine, figure map, outline, and
   section contracts.
5. Figure generation and review: figure assets and QA notes are tied to claim
   IDs before prose.
6. Section drafting: write flow-sized chunks in the required order only after
   the heavy gates pass.
7. Internal revision: patch only chunks named by accepted issues; do not reopen
   locked chunks without an explicit issue.

## Stage State

`paper/state/current-stage.yaml` records the active gate, status, blockers, and
next action. `paper/state/ledger.jsonl` is append-only and records stage events,
decisions, inputs, and outputs. A stage may advance only when the current gate
has no unresolved blockers.

## Heavy-Before-Prose Invariant

The claim matrix, figure map, reviewer issue state, and section contracts must
pass before section prose generation starts. If a section has an unsupported
claim, unresolved major issue, missing figure, or unknown source file, update
the upstream logic file instead of writing prose.

## V1 Boundaries

This workflow does not run calculations, prepare VASP jobs, launch UMA/MLIP,
query external literature services, verify citations, export references, or
invent new hypotheses. It may cite manually supplied reference context only as
plain input material, and citation automation remains out of scope.
