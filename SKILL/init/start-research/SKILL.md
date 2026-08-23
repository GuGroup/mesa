---
name: start-research
description: Optional startup gate for a MESA scientific research run after initialize-mesa and initialize-project. Use only when the user explicitly invokes start-research, asks to start the MESA research loop, or requests guided/autonomous execution. This skill verifies the project profile and runtime readiness, optionally handles full-access session checks and Codex goal setup when the user wants automation, and chooses the correct workflow entry point before executing the catalyst research loop.
---

# Start Research

## Overview

Use this optional skill after `initialize-mesa` has prepared the repository and
`initialize-project` has created or selected the project profile. Do not invoke
this skill implicitly from project initialization. Use it only after an explicit
user request to start, guide, or automate the MESA research loop.

Full filesystem access and Codex goal management are helpful for long
autonomous manuscript-producing runs, but they are not mandatory for every
startup. Treat them as opt-in automation controls and continue with bounded
profile review, readiness checks, or user-directed workflow entry when the
current session does not need them.

## Required Inputs

- `project/<project_name>/project_profile.md`
- `workflow.md`
- The nearest domain `workflow.md` for the chosen entry point.
- Any user-supplied source package recorded in the project profile: prompt,
  papers, experimental data, collaborator proposal, existing manuscript,
  reviewer comments, numeric tables, or gap/weakness-repair instructions.

If the project profile is missing or incomplete, stop and run
`initialize-project` before starting research.

## Startup Gate

Before executing research steps:

1. Read `project/<project_name>/project_profile.md` and root `workflow.md`.
   Treat the profile as the active project policy source and root `workflow.md`
   as the reusable execution contract.
2. Verify the backend and positive `max_active_strategy_agents`. For UMA,
   verify the GPU allocation mode, eligible physical devices, and inventory
   path. Return incomplete policy to `initialize-project`.
3. Record the current filesystem/session access state. Full filesystem access
   such as `danger-full-access`, unrestricted filesystem access, or an equivalent
   full-access profile is recommended for autonomous calculation and manuscript
   runs. If the session is workspace-only, read-only, or otherwise restricted,
   continue only with steps that fit the current access and stop before any
   required operation that the session cannot perform.
4. Manage a Codex goal only when the user explicitly asks for goal setup or asks
   for an autonomous manuscript-producing run. If the `get_goal`/`create_goal`
   tools are available in that mode:
   - call `get_goal`;
   - if no goal is active, call `create_goal` with an objective built from the
     project profile and the user's research request using the template below;
   - if a different goal is active, stop and report the conflict;
   - if the active goal already matches the manuscript objective for this
     project, continue.
   If the goal tools are unavailable, report that no Codex goal will be managed
   in this surface and continue only if the requested workflow does not depend on
   goal-managed autonomous continuation.
5. Run baseline readiness checks:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --skills
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py check mesa-general
```

Use `initialize-mesa` for deeper setup, runtime plans, or dependency repair.
Use `initialize-project` for missing or ambiguous project-profile decisions.
Do not use this skill to install dependencies except when the user explicitly
asks for setup changes.

## Optional Goal Objective Template

When the user explicitly requests goal setup and `create_goal` is available, do
not invent a broad prompt. `project_profile.md` records project identity, the
source package, and the calculation policy only; it does not record the
scientific objective, material family, catalyst domain, or target reaction.
Build one concrete objective from the profile's source package plus the
objective, material family, catalyst domain, and target reaction established
during Source Package Handling below, asking the user directly for any of
these that are still unresolved. The goal should satisfy the user's research
objective by producing a manuscript DOCX:

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

If any template field is missing, do not create the goal. Ask the user
directly for the missing scientific field (objective, material family,
catalyst domain, target reaction, evidence level); return to
`initialize-project` only when the missing field is project identity or the
calculation policy itself.

Keep `<calculation_policy_sentence>` short but explicit. Examples:

- `UMA/MLIP backend; local CUDA execution.`
- `VASP backend; submission mode: sge-submission.`

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

After the startup checks pass, choose exactly one starting point:

- If the active project has a current strategy artifact, fill available
  strategy-execution slots at `select-next-strategy`.
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
