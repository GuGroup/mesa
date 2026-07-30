---
name: initialize-project
description: Interview for and create a MESA project profile after repository setup. Use when Codex or a user needs to start or switch a MESA research project, choose project_name, record source materials such as prompts/PDFs/proposals/manuscripts/numeric data, define the scientific objective, choose evidence level and calculation backend policy, set scheduler/submission/API-key expectations, or write/update a project profile. Treat start-research as an optional explicit next step, not an automatic continuation.
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
- scientific claim or research objective, material family, catalyst domain,
  and target reaction, inferred from the source material when possible;
- evidence level: quick screening, UMA/MLIP test, DFT refinement, or
  manuscript-proof package;
- active backend policy: UMA/MLIP mode, VASP mode, or MLIP screening with VASP
  refinement;
- whether VASP execution/submission is allowed, dry-run only, or forbidden;
- if VASP execution is allowed, the VASP execution mode: `sge-qsub` or
  `local-node-runner`; do not leave this implicit;
- calculation artifact policy: whether VASP-compatible input artifacts may be
  prepared in non-VASP modes, whether backend cross-checks are exploratory or
  evidence-producing, and which backend is authoritative for claims;
- scheduler policy: local-only, qsub allowed, qsub forbidden, or
  user-approval-required;
- required runtimes: paper search, modeling, UMA, AdsorbDiff, VASP tooling,
  manuscript/figure export;
- API-key expectations and whether missing keys should block the run;
- language policy: user interaction and QA may be multilingual, but all saved
  project research artifacts must be English-only.

Use `request_user_input` when that tool is available in the active surface.
Otherwise ask concise plain-text questions. Do not fabricate missing project
decisions.

Skip the interview only when one of these is true:

- exactly one active project profile already exists, satisfies the Profile
  Contract below, and the user did not ask to create, switch, or update
  projects;
- the user explicitly asked to defer project setup;
- the user asked to repair repository setup before deciding the research
  project.

If the user has not provided a research prompt, paper, proposal, manuscript,
experimental data, or objective yet, ask for it. Do not report project
initialization as complete until either
`project/<project_name>/project_profile.md` exists or the user has explicitly
declined/deferred project setup.

## Profile Contract

The project profile must record:

- project name and canonical output directory;
- source artifact paths or identifiers, or the plain research prompt;
- user's research objective;
- material family, catalyst domain, and target reaction when known;
- evidence level;
- required runtimes;
- English-only saved-artifact policy;
- concrete `calculation_policy` section containing backend,
  artifact-generation, scheduler, submission, acceptance, and cross-check
  rules.
- if VASP is allowed, one explicit sentence naming `sge-qsub` or
  `local-node-runner` as the execution mode.

The selected project directory also owns any future `initialization/` artifacts
for non-deterministic analyzer output, dependency handoff files, runtime plans,
or status ledgers. Create that directory only after a real project name has
been selected.

Keep the calculation policy short but explicit. Examples:

- `MLIP-only evidence workflow; use UMA/MLIP for calculations and do not create
  or submit VASP jobs.`
- `VASP-only evidence workflow; use VASP for calculations and do not use
  UMA/MLIP outputs as evidence.`
- `MLIP screening with VASP refinement; use MLIP outputs as exploratory screens
  and VASP outputs as claim-supporting evidence.`
- `VASP execution mode: sge-qsub; submit approved jobs with vasp-job.`
- `VASP execution mode: local-node-runner; prepare inputs with vasp-job, run
  one calculation at a time inside a 48-core allocation using 40 VASP ranks.`

## Boundaries

- Do not choose a backend silently. If the source material does not imply a
  backend policy, ask.
- Do not treat repository setup as project setup. Use `initialize-mesa` for
  dependency checks, MCP config, skill symlink sync, and environment repair.
- Do not start the research loop or invoke `start-research` automatically. Treat
  `start-research` as an optional explicit next step after the profile is
  complete.
- Do not append a MESA scientific skill-call log entry for this setup-only
  skill unless it is invoked as part of a scientific workflow run.
