---
name: initialize-project
description: Interview for and create a MESA project profile after repository setup. Use when starting or switching a project, recording source materials, selecting UMA or VASP, configuring concurrent strategy-execution agents, assigning local CUDA devices for UMA, or updating project-specific instructions.
---

For MESA project setup, read `workflow.md` first.

# Initialize Project

Create or update one English project profile:

```text
project/<project_name>/project_profile.md
```

Use `initialize-mesa` for repository and dependency setup. Finish after writing
the profile; mention `start-research` as an optional next step.
Confirm `DEPENDENCY/.env` exists and route missing setup back to
`initialize-mesa`.

## Interview

Collect three grouped items:

1. Project identity and source package: project name plus prompts, papers,
   tables, proposals, manuscripts, reviewer comments, or prior-work gaps.
2. Calculation and strategy-execution policy:
   - backend: `UMA` or `VASP`;
   - positive integer `max_active_strategy_agents`;
   - for UMA, GPU allocation mode and eligible physical CUDA indices.
3. User instructions: scope, comparisons, constraints, and exclusions. Omit
   this section when none were supplied.

Use concise questions for unresolved decisions. Reuse a valid profile unless
the user requests a new project, switch, or update. Require a real project name
and at least one source item before reporting completion.

## Backend Policy

Record VASP as `sge-submission` by default. Use `local-node-runner` only
when the user explicitly selects the long-lived compute-node allocation
workflow.

For UMA, run:

```bash
python3 SKILL/init/initialize-project/scripts/probe_cuda_devices.py \
  --output project/<project_name>/initialization/gpu_inventory.json
```

Present the detected physical indices, UUIDs, names, total memory, and CUDA
visibility mapping. Ask for one allocation mode:

- `fixed` (recommended): reserve one selected physical device for each active
  strategy lineage until that lineage becomes terminal.
- `dynamic` (riskier): select and reserve one device from the eligible pool
  when a strategy becomes active, using a fresh runtime availability check.

Validate that every chosen device is CUDA-visible and that the selected or
eligible device count is at least `max_active_strategy_agents`. Treat the
inventory as initialization evidence; runtime availability is evaluated when
a dynamic lease is created.

When the probe reports unavailable hardware, preserve its diagnostic artifact
and stop UMA initialization until CUDA visibility is resolved.

`max_active_strategy_agents` limits active strategy lineages. Each lineage may
run every calculation authorized by its recipe and execution backend.

## Profile Contract

Keep the profile compact and include:

- project name and relative output directory;
- source paths, identifiers, or research prompt;
- `calculation_policy.backend`;
- `calculation_policy.submission_mode: sge-submission | local-node-runner`
  for VASP;
- `strategy_execution.max_active_strategy_agents`;
- for UMA, `gpu_allocation.mode`, physical device indices, and the relative
  GPU inventory path;
- concise user instructions when supplied.

Create `project/<project_name>/initialization/` only after the project name is
known. Keep project artifacts and paths portable across repository locations.

## Boundary

Limit this skill to profile creation. Strategy generation, execution, and
manuscript work begin only after an explicit research-start request.

Append a skill-call log entry only when initialization is part of an active
scientific workflow run.
