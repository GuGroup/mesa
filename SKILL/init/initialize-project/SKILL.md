---
name: initialize-project
description: Interview for and create a MESA project profile after repository setup. Use when Codex or a user needs to start or switch a MESA research project, choose project_name, record source materials such as prompts/PDFs/proposals/manuscripts/numeric data, choose the calculation backend and submission policy, record project-specific user instructions, or write/update a project profile. Treat start-research as an optional explicit next step, not an automatic continuation.
---

For MESA project setup use, read `workflow.md` before applying this skill.

# Initialize Project

## Overview

Use this skill after `initialize-mesa` has prepared the repository, dependency
checks, MCP configuration, and skill symlinks. This skill owns only
project-level research initialization: interview the user for decisions that
cannot be inferred, then write the active
`project/<project_name>/project_profile.md`.

This skill must not install dependencies, generate runtime plans, run
calculations, select strategies, write manuscripts, or enter the research loop.
After the project profile exists, stop and report the profile path. Mention
`start-research` only as an optional explicit next step for users who want a
guided or autonomous research startup.

This skill owns the real project name and project output directory decision.
Never use `mos`, `<project_name>`, or any placeholder as a default project. If
the project name is unknown, ask before writing project files.

## Required Outcome

Create or update exactly one active project profile:

```text
project/<project_name>/project_profile.md
```

All saved project artifacts, including the project profile, must be written in
English. User-facing questions and QA discussion may use the user's preferred
language.

## Project Interview

When the user invokes `initialize-project`, asks to initialize a MESA project,
or wants to start/switch a MESA research project, check for an active
`project/<project_name>/project_profile.md`. If no active project profile
exists, interview for only the decisions that cannot be inferred from the
repository or supplied artifacts.

Collect these decisions:

- project name / output folder under `project/<project_name>/`;
- source material supplied by the user: plain prompt, reference papers,
  experimental-only papers, numeric tables, collaborator proposal, existing
  manuscript, reviewer comments, or instructions to repair gaps or weaknesses
  in prior work;
- calculation backend: `UMA`/MLIP or `VASP`;
- when the backend is `VASP`, the submission mode: SGE/qsub submission, or a
  locally held compute node that runs jobs directly (`local-node-runner`);
- any project-specific instructions or constraints the user states directly
  (for example desired scope, preferred comparisons, explicit exclusions);
  record these briefly and omit the field entirely when the user gave none.

Use `request_user_input` when that tool is available in the active surface.
Otherwise ask concise plain-text questions. Do not fabricate missing project
decisions.

Keep the interview to exactly these three items. Do not ask about or infer
anything beyond project identity, calculation policy, and user notes.

Skip the interview only when one of these is true:

- exactly one active project profile already exists, satisfies the Profile
  Contract below, and the user did not ask to create, switch, or update
  projects;
- the user explicitly asked to defer project setup;
- the user asked to repair repository setup before deciding the research
  project.

If the user has not provided a research prompt, paper, proposal, manuscript,
or experimental data yet, ask for it. Do not report project
initialization as complete until either
`project/<project_name>/project_profile.md` exists or the user has explicitly
declined/deferred project setup.

## Profile Contract

The project profile must record:

- project name and canonical output directory;
- source artifact paths or identifiers, or the plain research prompt;
- any project-specific user instructions, stated briefly (omit this field when
  the user gave none);
- a concrete `calculation_policy` section containing only the backend
  (`UMA` or `VASP`) and, when the backend is `VASP`, the submission mode.

The selected project directory also owns any future `initialization/` artifacts
for non-deterministic analyzer output, dependency handoff files, runtime plans,
or status ledgers. Create that directory only after a real project name has
been selected.

Keep the calculation policy short but explicit. Examples:

- `UMA/MLIP backend; do not create or submit VASP jobs.`
- `VASP backend; submission mode: sge-submission.`
- `VASP backend; submission mode: local-node-runner.`

## Boundaries

- Do not choose a backend silently. If the source material does not imply a
  backend policy, ask.
- Do not treat repository setup as project setup. Use `initialize-mesa` for
  dependency checks, MCP config, skill symlink sync, and environment repair.
- Keep the project profile minimal: project identity/source references,
  calculation policy, and user notes only.
- Do not append a MESA scientific skill-call log entry for this setup-only
  skill unless it is invoked as part of a scientific workflow run.
