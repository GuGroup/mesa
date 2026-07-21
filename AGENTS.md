# Project

You need to prove scientific claim with computational chemistry.
Present domain is limited to catalyst.
Api keys are saved on ./DEPENDENCY/.env 

# Workflow loading

Before computational chemistry project work, read ./workflow.md.

When the task is scoped to a SKILL subdomain, also read the nearest matching workflow.md:
- SKILL/modeling/workflow.md for structure/model generation, UMA relaxation, AdsorbDiff, slab/adsorbate work.
- SKILL/calculation/workflow.md for calculation setup or execution.
- SKILL/analysis/workflow.md for energy, selectivity, or free-energy analysis.
- SKILL/literature/workflow.md for literature search or evidence gathering.
- SKILL/figure/workflow.md for figure generation.
- SKILL/manuscript/workflow.md for manuscript/export work.
- SKILL/orchestration/workflow.md or SKILL/strategy/workflow.md for planning, validation, or strategy updates.

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
symlink sync. Use `initialize-project` for project-profile creation. Use
`start-research` after initialization to verify the active project profile,
goal mode, full-access session state, and workflow entry point before running
the scientific research loop.

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


# Skill-call logging

For MESA scientific workflow tasks only, append one entry per MESA skill call
or project-local script to `project/<project_name>/skill_call_log.md`.

Do not read, rewrite, reorder, or deduplicate the existing log unless the user
explicitly asks for a log audit. Create the parent directory if needed, then
append with shell redirection (`>>`) using this fixed block format:

```md
## YYYY-MM-DDTHH:MM:SS+TZ - <skill-or-script-name>
- reason:
- inputs:
- outputs:
- validation:
- boundary:
```
