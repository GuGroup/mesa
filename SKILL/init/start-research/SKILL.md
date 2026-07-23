---
name: start-research
description: Start a MESA scientific research run after initialize-mesa and initialize-project. Use when the user says start research, begin the project, run the MESA workflow, proceed autonomously, or provides research inputs such as prompts, reference papers, experimental-only papers, numeric data, collaborator proposals, existing manuscripts, reviewer comments, or gap/weakness-repair instructions and asks Codex to verify project profile, create or verify a Codex goal for writing a DOCX manuscript, check full-access filesystem/session state, runtime readiness, and choose the correct workflow entry point before executing the catalyst research loop.
---

# Start Research

## Overview

Use this skill after `initialize-mesa` has prepared the repository and
`initialize-project` has created or selected the project profile. This skill
verifies that the current Codex session is allowed to run the research workflow
and then enters the root `workflow.md` loop.

## Required Inputs

- `project/<project_name>/project_profile.md`
- `workflow.md`
- The nearest domain `workflow.md` for the chosen entry point.
- Any user-supplied source package recorded in the project profile: prompt,
  papers, experimental data, collaborator proposal, existing manuscript,
  reviewer comments, numeric tables, or gap/weakness-repair instructions.

If the project profile is missing or incomplete, stop and run
`initialize-project` before starting research.

## Session Gate

Before executing research steps:

1. Confirm the session has full filesystem access from the active environment
   context. Accept `danger-full-access`, unrestricted filesystem access, or an
   equivalent full-access profile. If access is workspace-only, read-only, or
   otherwise restricted, stop and tell the user to restart the session with
   full access.
2. Create or confirm the Codex goal. If the `get_goal`/`create_goal` tools are
   available:
   - call `get_goal`;
   - if no goal is active, call `create_goal` with an objective built from the
     project profile and the user's research request using the template below;
   - if a different goal is active, stop and report the conflict;
   - if the active goal already matches the manuscript objective for this
     project, continue.
   If the goal tools are unavailable, stop and tell the user this surface cannot
   create the required research goal automatically.
3. Read `project/<project_name>/project_profile.md` and root `workflow.md`.
   Treat the profile as the active project policy source and root `workflow.md`
   as the reusable execution contract.
4. Verify the project profile's calculation policy before calculation work. If
   the policy is missing or ambiguous, return to `initialize-project` instead of
   assuming a backend.
5. Run the relevant readiness checks for the profile's required runtimes:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --skills
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py check mesa-general
```

Use `initialize-mesa` for deeper setup, runtime plans, or dependency repair.
Use `initialize-project` for missing or ambiguous project-profile decisions.
Do not use this skill to install dependencies except when the user explicitly
asks for setup changes.

## Goal Objective Template

When calling `create_goal`, do not invent a broad prompt. Use one concrete
objective derived from `project_profile.md`. The goal must be to satisfy the
user's research objective by producing a manuscript DOCX:

```text
Complete the MESA research workflow for project/<project_name> and write a
DOCX manuscript that satisfies the user's research objective:
"<research_objective>". Use the recorded source package
(<source_package_summary>) for <material_family>/<catalyst_domain> and
<target_reaction>. Apply the project calculation policy:
<calculation_policy_sentence>. Save all English-only research artifacts under
project/<project_name>, assemble the accepted evidence into a manuscript, and
produce the final DOCX under project/<project_name>/manuscript/.
```

If any template field is missing, do not create the goal. Ask for only the
missing project-profile decision or return to `initialize-project`.

Keep `<calculation_policy_sentence>` short but explicit. Examples:

- `MLIP-only evidence workflow; use UMA/MLIP for calculations and do not create
  or submit VASP jobs.`
- `VASP-only evidence workflow; use VASP for calculations and do not use UMA/MLIP
  outputs as evidence.`
- `MLIP screening with VASP refinement; use MLIP outputs as exploratory screens
  and VASP outputs as claim-supporting evidence.`

## Source Package Handling

Treat the project profile's source package as the research starting point, not
as a single prompt. Supported source types include:

- a short free-form research prompt;
- reference papers or literature PDFs;
- experimental-only papers that define observed trends, catalysts, reactions,
  conditions, or measured numbers;
- collaborator proposals or research requests from an experimental team;
- numeric tables, target values, selectivity/activity/stability measurements,
  or catalyst lists supplied by the user;
- existing manuscripts, drafts, SI files, reviewer comments, or instructions to
  repair gaps and weaknesses in prior work.

Before selecting the workflow entry point, classify the source package:

- If it contains a manuscript or gap/weakness-repair request, start from
  manuscript/literature evidence extraction and strategy generation for the
  missing computational proof.
- If it contains experimental-only papers, proposals, or numeric experimental
  data, start from literature or experimental-data extraction before strategy
  generation.
- If it contains only a broad prompt, interview only for the missing objective,
  material family, catalyst domain, target reaction, and evidence level.
- If it already includes a valid current strategy artifact, enter
  `select-next-strategy`.

All saved source digests, extracted evidence, strategies, recipes, logs,
analysis notes, figure text, manuscript text, and reports must be English-only.
User-facing clarification and QA may use the user's preferred language.

## Entry Point

After the session gate passes, choose exactly one starting point:

- If the active project has a current strategy artifact, enter the
  Per-Strategy Execution Loop at `select-next-strategy`.
- If the source package contains an existing manuscript or gap/weakness-repair
  instruction, extract the claim/gap context first, then generate or update
  computational strategies.
- If the source package contains experimental-only papers, collaborator
  proposals, or numeric data, run the literature or experimental-data workflow
  before strategy generation.
- If literature and target-task evidence exist but no strategy artifact exists,
  run `generate-strategies`.
- If the target task is known but literature grounding is missing, start with
  the literature workflow.
- If the target task itself is unclear, stop and ask only for the missing
  research objective.

Do not jump directly into modeling or calculations. The selected strategy must
first be translated into explicit calculation recipes.

## Logging

For MESA scientific workflow tasks, append this skill call to
`project/<project_name>/skill_call_log.md` using the root `workflow.md`
append-only format. Do not read or rewrite the existing log.
