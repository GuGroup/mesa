---
name: initialize-mesa
description: Check and report fresh-clone readiness for this MESA Codex repository. Use when Codex or a user needs to initialize, bootstrap, audit, install core dependencies, analyze non-deterministic CUDA/GPU/checkpoint/scheduler runtime facts, prepare a non-deterministic dependency handoff, generate or execute saved runtime install plans, notify users of initialization progress, or diagnose the repo before running skills, including Linux/macOS/Windows OS support, uv-first bootstrapping, DEPENDENCY runtime mappings and recipes, repo-local .codex/config.toml, paper_search MCP setup, DEPENDENCY/.env/API-key presence, optional Hugging Face checkpoint token/cache readiness, repo-local mamba/micromamba setup, Codex analyzer/profile/status/plan files for CUDA/checkpoint/scheduler-dependent runtimes, and skill-specific environment readiness.
---

For MESA repository setup use, read `workflow.md` before applying this skill.

# MESA Init

## Overview

Use this skill as the first gate after cloning the repository or after changing
dependency, API-key, Codex config, or MCP setup. Bootstrap is `uv`-first:
check the OS, check/install `uv`, then use `uv` to provide Python and run the
deterministic checker. Keep all non-uv runtime installs opt-in.

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
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic
bash DEPENDENCY/bootstrap.sh --analyze-nondeterministic
```

To notify the user and refresh resumable status:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --message "Initialization status refreshed."
```

To generate and review a saved non-deterministic runtime plan:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json
```

Execute the saved plan only after review and explicit approval:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json --yes
```

Legacy handoff output remains available:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py handoff
bash DEPENDENCY/bootstrap.sh --write-handoff
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

6. For first-run dependency setup, dry-run the core recipe before executing it:

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
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic
```

   This writes `project/mos/nondeterministic_profile.json` and
   `project/mos/nondeterministic_profile.md` by default. It must not print
   secret values, download checkpoints, install CUDA-specific wheels, or submit
   jobs. The profile must separate facts into `cuda`, `scheduler`,
   `checkpoints`, `python_env`, `platform`, `tools`, and `runtimes` sections.

9. Generate a runtime install plan only after the analyzer profile exists:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma
```

   This writes `project/mos/runtime_plans/<runtime>_plan.json` and
   `project/mos/runtime_plans/<runtime>_plan.md`. The plan must state runtime,
   CUDA/Torch choice, scheduler policy, checkpoint policy, exact commands,
   blockers, warnings, and the next dry-run/execute commands.

10. Notify the user through status artifacts whenever a plan is generated,
    dry-run, blocked, started, failed, or completed:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --message "Plan generated; review before execution."
```

    Status artifacts are `project/mos/initialize_status.md` and
    `project/mos/initialize_events.jsonl`.

11. Execute a saved non-deterministic runtime plan only after review and
    explicit approval:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json --yes
```

    Without `--yes`, the executor must dry-run or report blockers. If a saved
    plan is blocked, the executor must refuse to run commands even with `--yes`.
    The executor must not submit scheduler jobs or download checkpoints unless
    those actions are explicitly represented in a reviewed plan and allowed by
    a future policy.

12. If the user asks for a specific skill, resolve that skill's runtime:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --skill build-slab-models
```

13. Do not install every runtime by default. Install only the runtime needed for
the requested skill or workflow.
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
- `mamba`, `micromamba`, or repo-local `DEPENDENCY/bin/mamba` is available
  before conda-env dependency installation. If the user passes
  `--install-mamba`, install micromamba into `DEPENDENCY/bin`, create a
  `mamba` wrapper, and use `DEPENDENCY/.micromamba` as `MAMBA_ROOT_PREFIX`.
- `bootstrap --install-core` dry-runs the core dependency recipe by default.
  `bootstrap --install-core --yes` executes it. During execution, smoke-test
  each runtime first, skip it if healthy, otherwise install and smoke-test
  again.
- `analyze-nondeterministic` writes
  `project/mos/nondeterministic_profile.json` and
  `project/mos/nondeterministic_profile.md`. These files summarize OS/tool/env
  presence and separate CUDA/GPU, scheduler/HPC, checkpoint, Python/env, and
  runtime decision facts. They must not contain secret values.
- `bootstrap --analyze-nondeterministic` performs the same analyzer write as
  part of bootstrap. It is read-only with respect to dependencies.
- `notify`/`status` writes or refreshes `project/mos/initialize_status.md` and
  appends to `project/mos/initialize_events.jsonl`. Use these artifacts as the
  user-facing progress ledger for future Codex sessions.
- `generate-runtime-plan <runtime>` writes
  `project/mos/runtime_plans/<runtime>_plan.json` and
  `project/mos/runtime_plans/<runtime>_plan.md` from the non-deterministic
  profile. It must not execute commands.
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
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --all
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py smoke mesa-general --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --message "Initialization status refreshed."
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py handoff
```

For install dry-runs:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-core
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --analyze-nondeterministic
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --write-handoff
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install --skill build-slab-models
```

Execute installs only when the user explicitly wants setup changes:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba --install-core --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json --yes
```

## Reporting

Report in this order:

1. Platform and `uv` bootstrap readiness.
2. Secret/API-key readiness, with no values and official setup links when
   missing.
3. Codex/project TOML and paper-search MCP readiness.
4. Mamba/micromamba readiness and exact local install command if missing.
5. Core dependency recipe dry-run or execution status, if requested.
6. Non-deterministic analyzer or dependency handoff status, if requested.
7. Runtime plan path, blocked/readiness state, and approval command, if a plan
   was generated.
8. Runtime plan dry-run or execution status, if requested.
9. Runtime registry and requested skill runtime, if applicable.
10. Exact next commands for missing setup.

If `.codex/config.toml` was newly added or changed, remind the user that Codex
loads project config only after the repository is trusted and may need a restart
or new session before MCP servers appear.
