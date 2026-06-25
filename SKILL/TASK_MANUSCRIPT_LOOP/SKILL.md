---
name: mesa-manuscript-loop
description: Orchestrate a Nature-family manuscript workspace from completed MESA outputs by enforcing Gate 0 intake, claim/figure/reviewer gates, section contracts, and locked prose chunks. Use after calculations and analysis artifacts already exist. This skill does not run calculations, literature search, citation verification, or document export.
---

# MESA Manuscript Loop

Use this skill to turn completed MESA artifacts into a file-backed manuscript
workspace under `paper/`. The `paper/` folder is the source of truth; do not
infer manuscript state from chat history.

## Required Inputs

Start only from completed post-computation artifacts and explicit manuscript
state files:

- completed MESA task output envelopes, analyzer folders, structures, tables,
  figures, and manually supplied notes for Gate 0 intake
- `paper/inputs/manifest.yaml` and `paper/logic/result-inventory.md`
- `paper/logic/claim-matrix.yaml`, `paper/logic/figure-map.yaml`,
  `paper/logic/story-spine.md`, and `paper/logic/notation.yaml`
- `paper/state/current-stage.yaml`, `paper/state/ledger.jsonl`, and
  `paper/state/reviewer-issues.yaml`
- `paper/manuscript/section-contracts.yaml` and named section chunks only after
  the heavy gates pass

## Gate Order

Gate 0 intake must happen before any manuscript logic or prose work. Load
`references/intake-contract.md` and verify that the workspace has canonical
inputs under `paper/inputs/`, logic files under `paper/logic/`, state files
under `paper/state/`, manuscript files under `paper/manuscript/`, and figure
files under `paper/figures/`.

Advance in this order:

0. Gate 0 intake: normalize completed MESA outputs into `paper/inputs/` and
   `paper/logic/result-inventory.md`.
1. Result inventory: separate primary, exploratory, failed, and excluded
   artifacts.
2. Claim matrix: approve claim IDs, direct evidence, assumptions, caveats, and
   risks.
3. Reviewer logic round: run the read-only reviewer panel and merge issues.
4. Architecture: produce story spine, figure map, outline, and section
   contracts.
5. Figure generation/review: tie every figure asset and QA note to claim IDs.
6. Prose lock: validate claim matrix, figure map, reviewer issues, section
   contracts, and notation before any section drafting.
7. Section drafting/revision: write or patch only named chunks allowed by
   section contracts and accepted issues.

Do not draft or revise section prose before the prose lock. Heavy scientific
criticism belongs before prose. After prose exists, review only readability,
notation, consistency, and issues tied to explicit locked chunks.

## Routing

- New or incomplete workspace: load `references/workflow.md` and
  `references/intake-contract.md`.
- Claim or evidence work: load `references/claim-matrix-schema.md`.
- Figure planning or QA: load `references/figure-map-schema.md` and
  `references/figure-policy.md`.
- Reviewer rounds: load `references/reviewer-loop.md` and
  `references/reviewer-merge-contract.md`; merge reviewer outputs with
  `scripts/merge_reviewer_issues.py`.
- Section planning: load `references/section-contracts.md`.
- Section drafting or revision: load `references/section-writing-policy.md`
  after all heavy gates pass.
- Terminology, symbols, and formatting consistency: load
  `references/notation-style.md`.

## Fixed Agents

Use fixed agents only when their role is needed, and pass exact file paths every
time. Do not ask agents to infer state from chat.

- `chem-manuscript-architect`: story spine, figure order, and section
  contracts; no finished prose.
- `chem-significance-reviewer`, `chem-method-reviewer`, and
  `chem-claim-reviewer`: read-only structured issues for reviewer rounds.
- `chem-figure-reviewer`: figure QA tied to claim and figure IDs.
- `chem-section-writer`: one contracted section or patch after the prose lock.
- `chem-revision-editor`: accepted-issue patches to named chunks only.

Reviewer round defaults are R1 full critique, R2 changed-files verification,
and R3 coherence/polish-readiness. Halt rather than fake resolution if any
BLOCKER remains after R3.

## V1 Exclusions

Do not run VASP, UMA, DFT, qsub, or new calculations from this skill. Do not do
literature search, citation verification, reference export, autonomous
hypothesis generation, or dynamic agent creation in v1. Reviewers are read-only:
they may create structured issues, but they must not edit prose or invent
missing data.
