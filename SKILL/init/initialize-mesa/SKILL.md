---
name: initialize-mesa
description: Check and report fresh-clone readiness for this MESA Codex repository. Use when Codex or a user needs to initialize, bootstrap, audit, install core dependencies, synchronize repo skills into CODEX_HOME skills via symlinks, or diagnose the repo before running skills, including Linux/macOS/Windows OS support, uv-first bootstrapping, DEPENDENCY runtime mappings and recipes, repo-local .codex/config.toml, paper_search MCP setup, DEPENDENCY/.env/API-key presence, optional Hugging Face checkpoint token/cache readiness, repo-local mamba/micromamba setup, vasp-job uv-tool readiness, and skill-specific environment readiness.
---

For MESA repository setup use, read `workflow.md` before applying this skill.

# MESA Init

## Overview

Use this skill as the first gate after cloning the repository or after changing
dependency, API-key, Codex config, or MCP setup. Bootstrap is `uv`-first:
check the OS, check/install `uv`, then use `uv` to provide Python and run the
deterministic checker. Keep all non-uv runtime installs opt-in.

Default initialization is a lightweight repository and environment readiness
check. Do not run install, update, smoke-test-all, or `doctor --all` unless the
user explicitly asks for setup changes or the active project requires that
specific runtime now. Already-installed environments should be treated as
reusable; do not re-prove every runtime on every initialization.

This skill prepares the repository setup only. It does not create project
profiles, execute a research workflow, select a strategy, run calculations, or
write a manuscript. After repository initialization, run `initialize-project`
to create/select the active project profile, then run `start-research`.

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

To synchronize this repo's skills into Codex discovery:

```bash
bash DEPENDENCY/sync_codex_skills.sh
bash DEPENDENCY/sync_codex_skills.sh --apply
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

This is the normal environment-readiness path. After this command, report
repository readiness and direct project-profile creation to
`initialize-project` when no active project profile exists.

4a. Synchronize the remaining repository skills into Codex discovery. Fresh
clones require the user to link only `initialize-mesa`; this step lets the
agent link `initialize-project`, `start-research`, and the task-specific MESA
skills during initialization. First dry-run, then apply. Existing non-symlink
paths are reported as `SKIP` by the script and must not be overwritten:

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

8. If the user asks for a specific skill, resolve that skill's runtime. Prefer
the narrow skill-specific doctor command over `doctor --all`:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --skill build-slab-models
```

9. Do not install or smoke-test every runtime by default. Install or smoke-test
only the runtime needed for the requested skill or workflow.
10. Do not print secret values. Report API keys only as `SET` or `MISSING`.
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
- Project profile creation is intentionally out of scope. If no active profile
  exists, tell the user to run `initialize-project`.
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
- `.codex/config.toml` exists, parses, and defines `mcp_servers.paper_search`.
  Inspect this file read-only during initialization. Do not add, rewrite, or
  normalize `.codex/config.toml` unless the user explicitly asks for a Codex
  config edit.
- If `codex` is available on PATH, prefer `codex mcp get paper_search` as the
  readiness check for the project TOML and paper-search MCP registration.
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
- Project-scoped initialization artifacts, non-deterministic analyzer outputs,
  dependency handoff files, status ledgers, and runtime plans are outside this
  skill. Create/select the project with `initialize-project` first.
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
bash DEPENDENCY/sync_codex_skills.sh
```

For install dry-runs:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-core
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install --skill build-slab-models
```

Execute installs only when the user explicitly wants setup changes:

```bash
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba --install-core --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general --yes
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
   - if none exists, report that project setup is pending and run
     `initialize-project` next;
   - if multiple profiles exist, ask which project is active.
5. Codex skill symlink dry-run/apply status for the remaining MESA skills.
6. `vasp-job` uv-tool readiness when VASP workflows are in scope.
7. Mamba/micromamba readiness and exact local install command if missing.
8. Core dependency recipe dry-run or execution status, if requested.
9. Runtime registry and requested skill runtime, if applicable.
10. Exact next commands for missing setup.

If the user explicitly changed `.codex/config.toml`, remind them that Codex
loads project config only after the repository is trusted and may need a
restart or new session before MCP servers appear.
