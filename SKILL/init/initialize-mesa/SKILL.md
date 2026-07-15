---
name: initialize-mesa
description: Check and report fresh-clone readiness for this MESA Codex repository. Use when Codex or a user needs to initialize, bootstrap, audit, install core dependencies, synchronize repo skills into CODEX_HOME skills via symlinks, analyze non-deterministic CUDA/GPU/checkpoint/scheduler runtime facts, prepare a non-deterministic dependency handoff, generate or execute saved runtime install plans, notify users of initialization progress, interview for project-level research settings, or diagnose the repo before running skills, including Linux/macOS/Windows OS support, uv-first bootstrapping, DEPENDENCY runtime mappings and recipes, repo-local .codex/config.toml, paper_search MCP setup, DEPENDENCY/.env/API-key presence, optional Hugging Face checkpoint token/cache readiness, repo-local mamba/micromamba setup, Codex analyzer/profile/status/plan files for CUDA/checkpoint/scheduler-dependent runtimes, vasp-job uv-tool readiness, and skill-specific environment readiness.
---

For MESA repository setup use, read `workflow.md` before applying this skill.

# MESA Init

## Overview

Use this skill as the first gate after cloning the repository or after changing
dependency, API-key, Codex config, or MCP setup. Bootstrap is `uv`-first:
check the OS, check/install `uv`, then use `uv` to provide Python and run the
deterministic checker. Keep all non-uv runtime installs opt-in.

Default initialization has two phases: a lightweight environment readiness
check, then project-profile creation. Do not run install, update,
smoke-test-all, `doctor --all`, or runtime-plan execution steps unless the user
explicitly asks for setup changes or the active project requires that specific
runtime now. Already-installed environments should be treated as reusable; do
not re-prove every runtime on every initialization.

This skill prepares the repository and project settings. It must not end after
environment checks when no active project profile exists, unless the user
explicitly asked for environment/bootstrap checking only. It does not by itself
execute a research workflow, select a strategy, run calculations, or write a
manuscript. After initialization, run `start-research` for the active project.

Recommended entry points:

```bash
# Linux/macOS
bash DEPENDENCY/bootstrap.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1
```

After `uv` is available, the deterministic checker is:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap
```

To also install the repo-local conda-compatible manager needed by conda-env
runtimes, pass:

```bash
# Linux/macOS
bash DEPENDENCY/bootstrap.sh --install-mamba

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba

# Direct checker form
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba
```

To dry-run the deterministic core dependency recipe:

```bash
bash DEPENDENCY/bootstrap.sh --install-core
```

To write the non-deterministic analyzer profile for machine-specific runtimes
without installing anything:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic --output-dir project/<project_name>/initialization
bash DEPENDENCY/bootstrap.sh --analyze-nondeterministic --nd-dir project/<project_name>/initialization
```

To notify the user and refresh resumable status:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --output-dir project/<project_name>/initialization --message "Initialization status refreshed."
```

To synchronize this repo's skills into Codex discovery:

```bash
bash DEPENDENCY/sync_codex_skills.sh
bash DEPENDENCY/sync_codex_skills.sh --apply
```

To generate and review a saved non-deterministic runtime plan:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma --project-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/<project_name>/initialization/runtime_plans/mesa-uma_plan.json --project-dir project/<project_name>/initialization
```

Execute the saved plan only after review and explicit approval:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/<project_name>/initialization/runtime_plans/mesa-uma_plan.json --project-dir project/<project_name>/initialization --yes
```

Legacy handoff output remains available:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py handoff --output-dir project/<project_name>/initialization
bash DEPENDENCY/bootstrap.sh --write-handoff --handoff-dir project/<project_name>/initialization
```

To execute that recipe:

```bash
# Linux/macOS
bash DEPENDENCY/bootstrap.sh --install-mamba --install-core --yes

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba -InstallCore -Yes
```

Manual Python fallback:

```bash
python3 DEPENDENCY/tools/mesa_env.py bootstrap
```

Initialization-owned artifacts are written under
`project/<project_name>/initialization/` when an explicit path or active project
profile selects that directory. Keep the project root for
workflow outputs such as literature, strategy, modeling, calculation, analysis,
figures, and manuscript artifacts. Do not clean or migrate older root-level
initialization files automatically; treat them as historical outputs unless the
user explicitly asks for cleanup.

## Project Interview

When the user invokes `initialize-mesa`, asks to initialize MESA, or wants to
start a new MESA research project, check for an active
`project/<project_name>/project_profile.md`. If no active project profile
exists, interview for only the decisions that cannot be inferred from the
repository. Do this even if environment readiness has blockers; record blockers
in the profile or final report instead of silently ending after the bootstrap
check.

- project name / output folder under `project/<project_name>/`;
- source material supplied by the user: plain prompt, reference papers,
  experimental-only papers, numeric tables, collaborator proposal, existing
  manuscript, reviewer comments, or instructions to repair gaps or weaknesses
  in prior work;
- scientific claim or research objective, material family, catalyst domain,
  and target reaction, inferred from the source material when possible;
- evidence level: quick screening, UMA/MLIP test, DFT refinement, or
  manuscript-proof package;
- active backend policy: UMA/MLIP mode or VASP mode;
- whether VASP execution/submission is allowed, dry-run only, or forbidden;
- calculation artifact policy: whether VASP-compatible input artifacts may be
  prepared in non-VASP modes, whether backend cross-checks are exploratory or
  evidence-producing, and which backend is authoritative for claims;
- scheduler policy: local-only, qsub allowed, qsub forbidden, or
  user-approval-required;
- required runtimes: paper search, modeling, UMA, AdsorbDiff, VASP tooling,
  manuscript/figure export;
- API-key expectations and whether missing keys should block the run.
- language policy: user interaction and QA may be multilingual, but all saved
  project research artifacts must be English-only.

Use `request_user_input` when that tool is available in the active surface.
Otherwise ask concise plain-text questions. Do not fabricate missing project
decisions. After the interview, write the agreed decisions to
`project/<project_name>/project_profile.md` and use that profile as the active
project policy source for the run. The project profile must record source
artifact paths or identifiers, the user's research objective, required
runtimes, the English-only artifact policy, and a concrete `calculation_policy`
section containing backend, artifact-generation, scheduler, submission,
acceptance, and cross-check rules.

Skip the project interview only when one of these is true:

- the user explicitly asked for environment-only bootstrap, dependency audit,
  or config/MCP checking;
- exactly one active project profile already exists and the user did not ask to
  create or switch projects;
- the user asked to repair setup before deciding the research project.

If the user has not provided a research prompt, paper, proposal, manuscript,
experimental data, or objective yet, ask for it. Do not report initialization as
complete until either `project/<project_name>/project_profile.md` exists or the
user has declined/deferred project setup.

## Workflow

1. Run from the repository root.
2. Confirm the OS is Linux, macOS, or Windows. Do not try to support other
   operating systems in this skill.
3. Check whether `uv` is installed. If not, install `uv` with the official
   standalone installer:
   - Linux/macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows PowerShell:
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
4. Run the bootstrap preflight through `uv`:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap
```

This is the normal environment-readiness path. After this command, continue to
Project Interview when no active project profile exists, unless the user asked
for environment/bootstrap checking only.

4a. Synchronize the remaining repository skills into Codex discovery. Fresh
clones require the user to link only `initialize-mesa`; this step lets the
agent link `start-research` and the task-specific MESA skills during
initialization. First dry-run, then apply. Existing non-symlink paths are
reported as `SKIP` by the script and must not be overwritten:

```bash
bash DEPENDENCY/sync_codex_skills.sh
bash DEPENDENCY/sync_codex_skills.sh --apply
```

5. Check for `mamba`, `micromamba`, or repo-local
   `DEPENDENCY/bin/mamba`. If no mamba-compatible manager exists and the user
   wants first-run setup, install repo-local micromamba:

```bash
# Linux/macOS
bash DEPENDENCY/bootstrap.sh --install-mamba

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba

# Direct checker form
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba
```

6. For first-run dependency setup only, dry-run the core recipe before
executing it. Do not run this during routine initialization on an already-set-up
machine:

```bash
bash DEPENDENCY/bootstrap.sh --install-core
```

7. Execute the core recipe only when the user explicitly wants setup changes:

```bash
bash DEPENDENCY/bootstrap.sh --install-mamba --install-core --yes
```

8. For non-deterministic runtimes, write a structured analyzer profile instead
   of installing CUDA, checkpoints, or scheduler setup automatically:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic --output-dir project/<project_name>/initialization
```

   This writes `project/<project_name>/initialization/nondeterministic_profile.json` and
   `project/<project_name>/initialization/nondeterministic_profile.md`. It must
   not print secret values, download checkpoints, install CUDA-specific wheels,
   or submit jobs. The profile must separate facts into `cuda`, `scheduler`,
   `checkpoints`, `python_env`, `platform`, `tools`, and `runtimes` sections.

9. Generate a runtime install plan only after the analyzer profile exists:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma --project-dir project/<project_name>/initialization
```

   This writes
   `project/<project_name>/initialization/runtime_plans/<runtime>_plan.json` and
   `project/<project_name>/initialization/runtime_plans/<runtime>_plan.md`. The plan must
   state runtime, CUDA/Torch choice, scheduler policy, checkpoint policy, exact
   commands, blockers, warnings, and the next dry-run/execute commands.

10. Notify the user through status artifacts whenever a plan is generated,
    dry-run, blocked, started, failed, or completed:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --output-dir project/<project_name>/initialization --message "Plan generated; review before execution."
```

    Status artifacts are
    `project/<project_name>/initialization/initialize_status.md` and
    `project/<project_name>/initialization/initialize_events.jsonl`.

11. Execute a saved non-deterministic runtime plan only after review and
    explicit approval:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/<project_name>/initialization/runtime_plans/mesa-uma_plan.json --project-dir project/<project_name>/initialization --yes
```

    Without `--yes`, the executor must dry-run or report blockers. If a saved
    plan is blocked, the executor must refuse to run commands even with `--yes`.
    The executor must not submit scheduler jobs or download checkpoints unless
    those actions are explicitly represented in a reviewed plan and allowed by
    a future policy.

12. If the user asks for a specific skill, resolve that skill's runtime. Prefer
the narrow skill-specific doctor command over `doctor --all`:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --skill build-slab-models
```

13. Do not install or smoke-test every runtime by default. Install or smoke-test
only the runtime needed for the requested skill or workflow.
14. Do not print secret values. Report API keys only as `SET` or `MISSING`.
   When a required key is missing, print official acquisition links and the
   exact `DEPENDENCY/.env` variable name to fill.

## What To Check

Treat these as the standard init checks:

- `DEPENDENCY/runtimes.yaml` parses and lists skill-to-runtime mappings.
- `DEPENDENCY/runtimes.yaml` defines `recipes.core` with exactly:
  `mesa-general`, `paper-search-mcp`, `mesa-paper-search`, `mesa-modeling`,
  and `mesa-manuscript`.
- `DEPENDENCY/non_deterministic_runtimes.yaml` parses and records analyzer
  output names, deterministic facts, and Codex decision points for `mesa-uma`
  and `mesa-adsorbdiff`.
- `DEPENDENCY/sync_codex_skills.sh` exists and can symlink remaining repository
  skill folders containing `SKILL.md` into `$CODEX_HOME/skills` or
  `~/.codex/skills` after the user has linked `initialize-mesa`.
- An active project profile exists for research execution, or the user has been
  interviewed for the decisions needed to write
  `project/<project_name>/project_profile.md`.
- The OS is Linux, macOS, or Windows.
- `uv` is installed or can be installed with the OS-specific standalone
  installer. Treat `uv` as the first required dependency.
- `DEPENDENCY/.env.example` exists.
- `DEPENDENCY/.env` exists when the user expects local secrets. A repo-root
  `.env` is only a backward-compatible fallback.
- Core keys are present when needed:
  - `OPENAI_API_KEY` for OpenAI-backed PDF and strategy skills.
  - `MP_API_KEY` or `PMG_MAPI_KEY` for Materials Project slab fetching.
- Optional Hugging Face checkpoint access is reported without failing
  bootstrap:
  - `HF_TOKEN` for gated/private Hugging Face checkpoint downloads.
  - `HF_HOME` for Hugging Face token/cache location. If unset, Hugging Face
    uses its default cache location.
- Missing core keys include user-facing setup links:
  - OpenAI API keys: `https://platform.openai.com/api-keys`
  - OpenAI key help:
    `https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key`
  - Materials Project API key: `https://next-gen.materialsproject.org/api`
  - Materials Project API docs:
    `https://docs.materialsproject.org/downloading-data/using-the-api/getting-started`
  - Hugging Face tokens: `https://huggingface.co/settings/tokens`
  - Hugging Face Hub quickstart:
    `https://huggingface.co/docs/huggingface_hub/en/quick-start`
- `.codex/config.toml` exists and defines `mcp_servers.paper_search`.
- The project TOML parses and the `paper_search` MCP config has:
  - `enabled = true`;
  - `required = false`;
  - `command = "uv"`;
  - `args = ["run", "--frozen", "-m", "paper_search_mcp.server"]`;
  - `cwd = "EXTERNAL/paper-search-mcp"`;
  - positive `startup_timeout_sec` and `tool_timeout_sec`;
  - `default_tools_approval_mode = "auto"`;
  - no `env_vars` list, because secrets are read through
    `PAPER_SEARCH_MCP_ENV_FILE`.
- `mcp_servers.paper_search.env.PAPER_SEARCH_MCP_ENV_FILE` resolves from
  `EXTERNAL/paper-search-mcp` to `DEPENDENCY/.env`.
- `.codex/config.toml` does not contain literal API keys, tokens, or secrets.
- External MCP package files exist under `EXTERNAL/paper-search-mcp`, including
  `pyproject.toml`, `uv.lock`, and `paper_search_mcp/server.py`.
- If `codex` is available on PATH, `codex mcp get paper_search` sees the same
  server. If it does not, tell the user to trust the repository and restart
  Codex or open a new session.
- `$CODEX_HOME/skills` or `~/.codex/skills` symlinks point to this repository's
  current `SKILL/` folders after initialization. Existing non-symlink paths
  must not be overwritten.
- `vasp-job` is available on PATH when VASP preparation or VASP execution
  workflows are expected. Prefer `uv tool list`, `which vasp-job`, and
  `vasp-job schema` for verification.
- `mamba`, `micromamba`, or repo-local `DEPENDENCY/bin/mamba` is available
  before conda-env dependency installation. If the user passes
  `--install-mamba`, install micromamba into `DEPENDENCY/bin`, create a
  `mamba` wrapper, and use `DEPENDENCY/.micromamba` as `MAMBA_ROOT_PREFIX`.
- `bootstrap --install-core` dry-runs the core dependency recipe by default.
  `bootstrap --install-core --yes` executes it. During execution, smoke-test
  each runtime first, skip it if healthy, otherwise install and smoke-test
  again.
- `analyze-nondeterministic` writes
  `project/<project_name>/initialization/nondeterministic_profile.json` and
  `project/<project_name>/initialization/nondeterministic_profile.md`. These files
  summarize OS/tool/env presence and separate CUDA/GPU, scheduler/HPC,
  checkpoint, Python/env, and runtime decision facts. They must not contain
  secret values.
- `bootstrap --analyze-nondeterministic` performs the same analyzer write as
  part of bootstrap. It is read-only with respect to dependencies.
- `notify`/`status` writes or refreshes
  `project/<project_name>/initialization/initialize_status.md` and appends to
  `project/<project_name>/initialization/initialize_events.jsonl`. Use these artifacts as
  the user-facing progress ledger for future Codex sessions.
- `generate-runtime-plan <runtime>` writes
  `project/<project_name>/initialization/runtime_plans/<runtime>_plan.json` and
  `project/<project_name>/initialization/runtime_plans/<runtime>_plan.md` from the
  non-deterministic profile. It must not execute commands.
- `execute-runtime-plan <plan.json>` dry-runs by default. It executes only with
  `--yes`, refuses blocked plans, logs status events, and runs only commands
  stored in the saved plan.
- `handoff` and `bootstrap --write-handoff` remain available for legacy
  `machine_profile.json` and `dependency_handoff.md` output.
- Python readiness is reported, but system Python is not a first dependency
  because `uv` can provide Python. `qsub` is not fatal unless the requested
  workflow needs it.

## Runtime Checks

Use these commands as needed:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --skills
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --recipes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py check mesa-general
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --skill build-slab-models
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic --output-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --output-dir project/<project_name>/initialization --message "Initialization status refreshed."
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma --project-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/<project_name>/initialization/runtime_plans/mesa-uma_plan.json --project-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py handoff --output-dir project/<project_name>/initialization
bash DEPENDENCY/sync_codex_skills.sh
```

For install dry-runs:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-core
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --analyze-nondeterministic --nd-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --write-handoff --handoff-dir project/<project_name>/initialization
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install --skill build-slab-models
```

Execute installs only when the user explicitly wants setup changes:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba --install-core --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/<project_name>/initialization/runtime_plans/mesa-uma_plan.json --project-dir project/<project_name>/initialization --yes
```

## Reporting

Report in this order:

1. Platform and `uv` bootstrap readiness.
2. Secret/API-key readiness, with no values and official setup links when
   missing.
3. Codex/project TOML and paper-search MCP readiness.
4. Active project profile status:
   - if exactly one profile exists, report its path and active calculation
     policy;
   - if none exists and this is not environment-only initialization, ask the
     Project Interview questions before ending;
   - if multiple profiles exist, ask which project is active.
5. Codex skill symlink dry-run/apply status for the remaining MESA skills.
6. `vasp-job` uv-tool readiness when VASP workflows are in scope.
7. Mamba/micromamba readiness and exact local install command if missing.
8. Core dependency recipe dry-run or execution status, if requested.
9. Non-deterministic analyzer or dependency handoff status, if requested.
10. Runtime plan path, blocked/readiness state, and approval command, if a plan
   was generated.
11. Runtime plan dry-run or execution status, if requested.
12. Runtime registry and requested skill runtime, if applicable.
13. Exact next commands for missing setup.

If `.codex/config.toml` was newly added or changed, remind the user that Codex
loads project config only after the repository is trusted and may need a restart
or new session before MCP servers appear.
