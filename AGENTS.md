# Project

You need to prove scientific claim with computational chemistry.
Present domain is limited to catalyst.
Api keys are saved on ./DEPENDENCY/.env 

# Workflow loading

Before computational chemistry project work, read ./workflow.md.

When the task is scoped to a SKILL subdomain, also read that subdomain's
`workflow.md` before using the skill.

Do not add workflow.md to project_doc_fallback_filenames. Load workflow files explicitly according to task scope.

# Result save directory
There is a directory named as 'project'.
Please save all the result in there.
Use `project/<project_name>/` for project outputs unless the user explicitly
names a concrete project directory.

# Language policy

User interaction, clarification, status updates, and QA discussion may use any
language requested by the user.

All project-internal MESA research artifacts must be written in English only.
This includes project profiles, extracted evidence, strategy artifacts,
recipes, manifests, logs, analysis notes, figure text, manuscript text, and
reports saved under `project/<project_name>/`.

# Calculation policy

For MESA scientific work, read the active
`project/<project_name>/project_profile.md` for the calculation backend and
execution policy. Use `workflow.md` for the reusable process contract, not for
project-specific policy. Do not infer backend policy from AGENTS.md.

# Research startup

Use `initialize-mesa` for repository setup, dependency checks, and skill
symlink sync. Use `initialize-project` for project-profile creation. After
project initialization, wait for an explicit user request before starting the
scientific research loop. Use `start-research` only as an optional explicit
startup gate for guided/autonomous execution; Codex goal setup and full-access
session checks are helpful automation controls, not mandatory defaults.

# Skill-first operating rules

You are operating inside a skills repository.

Before doing any user task:
1. Inspect the available skills index or skill folders.
2. Select the most relevant skill.
3. Read that skill's SKILL.md completely.
4. Follow the skill's workflow exactly.

Do not solve tasks ad hoc unless:
- no relevant skill exists, or
- the selected skill explicitly cannot apply.

When a relevant skill exists:
- use its scripts, templates, examples, and checklists;
- cite which skill was used in your response;
- do not bypass the skill with general reasoning.

If multiple skills apply:
- choose the narrowest task-specific skill first;
- compose skills only when necessary.

If no skill applies:
- say: "No matching skill found; proceeding without a skill."

# Sub-agent delegation

Sub-agent use is opt-in. Spawn a sub-agent only when an applicable skill and
workflow explicitly require delegation.

For multi-step literature preparation, the parent must use
`delegate-literature-workflow` and spawn exactly one fresh sub-agent for each
active phase. The parent owns user interaction, phase selection, and returned
artifact-path validation. The sub-agent owns only its bounded worker steps,
must not spawn another sub-agent, and returns the compact handoff required by
the delegation skill.

For planned strategy execution, use `delegate-strategy-execution` after the
explicit recipe root and `execution_plan.json` exist. Assign one sub-agent when
a strategy lineage becomes active. Continue its resume, fix, and bounded
revision work with `followup_task` on that agent. Replace the agent only when it
is unavailable, recording the reason in strategy status. The worker owns
recipe-backed E execution and terminal E/C/P management, must not spawn another
sub-agent, and stops before S-level evaluation. The parent owns the configured
strategy-agent pool, user interaction, returned-path validation, and scientific
strategy evaluation.

Pass only the minimum task-local context needed by the sub-agent. Every agent
must follow the same workflow-loading, skill-first, language, and skill-call
logging rules in this file.

# Skill-call logging

For MESA scientific workflow tasks only, append one entry per MESA skill call
or project-local script to `project/<project_name>/skill_call_log.md`.

Do not read, rewrite, reorder, or deduplicate the existing log unless the user
explicitly asks for a log audit. Create the parent directory if needed, then
append with shell redirection (`>>`) using this fixed block format. Start each
append with a newline and end it with a blank line so adjacent entries cannot
run together:

```md
## YYYY-MM-DDTHH:MM:SS+TZ - <skill-or-script-name>

- reason:
- inputs:
- outputs:
- validation:
- boundary:

```
