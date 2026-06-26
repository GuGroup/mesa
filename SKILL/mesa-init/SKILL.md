---
name: mesa-init
description: Check and report fresh-clone readiness for this MESA Codex repository. Use when Codex or a user needs to initialize, bootstrap, audit, or diagnose the repo before running skills, including DEPENDENCY runtime mappings, repo-local .codex/config.toml, paper_search MCP setup, .env/API-key presence, and skill-specific environment readiness.
---

# MESA Init

## Overview

Use this skill as the first gate after cloning the repository or after changing
dependency, API-key, Codex config, or MCP setup. Keep it read-only by default:
check readiness and report exact missing steps before installing anything.

The deterministic entry point is:

```bash
python3 DEPENDENCY/tools/mesa_env.py bootstrap
```

## Workflow

1. Run from the repository root.
2. Run the bootstrap preflight:

```bash
python3 DEPENDENCY/tools/mesa_env.py bootstrap
```

3. If the user asks for a specific skill, resolve that skill's runtime:

```bash
python3 DEPENDENCY/tools/mesa_env.py doctor --skill TASK_BUILD_SLAB_MODELS
```

4. Do not install every runtime by default. Install only the runtime needed for
the requested skill or workflow.
5. Do not print secret values. Report API keys only as `SET` or `MISSING`.

## What To Check

Treat these as the standard init checks:

- `DEPENDENCY/runtimes.yaml` parses and lists skill-to-runtime mappings.
- `DEPENDENCY/.env.example` exists.
- Repo-root `.env` exists when the user expects local secrets.
- Core keys are present when needed:
  - `OPENAI_API_KEY` for OpenAI-backed PDF and strategy skills.
  - `MP_API_KEY` or `PMG_MAPI_KEY` for Materials Project slab fetching.
- `.codex/config.toml` exists and defines `mcp_servers.paper_search`.
- The `paper_search` MCP config points to `EXTERNAL/paper-search-mcp` and does
  not contain literal API-key values.
- `uv`, `python3`/`python`, `mamba`, and `qsub` readiness is reported by runtime
  context; missing `mamba` or `qsub` is not fatal unless the requested workflow
  needs them.

## Runtime Checks

Use these commands as needed:

```bash
python3 DEPENDENCY/tools/mesa_env.py list --skills
python3 DEPENDENCY/tools/mesa_env.py check mesa-general
python3 DEPENDENCY/tools/mesa_env.py doctor --all
python3 DEPENDENCY/tools/mesa_env.py smoke mesa-general --yes
```

For install dry-runs:

```bash
python3 DEPENDENCY/tools/mesa_env.py install mesa-general
python3 DEPENDENCY/tools/mesa_env.py install --skill TASK_BUILD_SLAB_MODELS
```

Execute installs only when the user explicitly wants setup changes:

```bash
python3 DEPENDENCY/tools/mesa_env.py install mesa-general --yes
```

## Reporting

Report in this order:

1. Codex/project config readiness.
2. Secret/API-key readiness, with no values.
3. Runtime registry and tool readiness.
4. Requested skill runtime, if applicable.
5. Exact next commands for missing setup.

If `.codex/config.toml` was newly added or changed, remind the user that Codex
loads project config only after the repository is trusted and may need a restart
or new session before MCP servers appear.
