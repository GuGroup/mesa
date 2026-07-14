# DEPENDENCY KNOWLEDGE BASE

## OVERVIEW

- `DEPENDENCY/` owns runtime routing, bootstrap, readiness checks, and
  machine-specific setup artifacts; it does not own scientific implementations.
- `runtimes.yaml` is the canonical skill-to-runtime and recipe registry.
- `non_deterministic_runtimes.yaml` is the canonical UMA/AdsorbDiff decision
  contract. Keep deterministic facts separate from machine-specific choices.

## WHERE TO LOOK

| Concern | Location |
|---|---|
| Runtime kinds, recipes, skill mappings | `runtimes.yaml` |
| Machine-specific policy and output names | `non_deterministic_runtimes.yaml` |
| Fresh-clone POSIX / Windows entry points | `bootstrap.sh`, `bootstrap.ps1` |
| User-facing CLI | `tools/mesa_env.py`, `tools/mesa_env_support/cli.py` |
| Registry parsing, paths, env, subprocess helpers | `tools/mesa_env_support/common.py` |
| Deterministic checks and recipe execution | `tools/mesa_env_support/runtime.py` |
| Profiles, plans, execution, reports, status | `tools/mesa_env_support/nd_*.py` |
| Manual machine-specific requirements | `uma/runtime.md`, `adsorbdiff/runtime.md` |

## CODE MAP

- `common.py` is an implicit internal API: constants, YAML/JSON loading,
  runtime resolution, path lookup, env merging, tool discovery, and probes.
  Wildcard-import consumers depend on its exported names; change cautiously.
- `cli.py` owns command parsing and dispatch only. Keep operations in focused
  support modules; keep `mesa_env.py` a thin entry point.
- Registry schema: top-level `version`, `recipes`, `runtimes`, `skills`;
  recipe runtime names and skill targets must resolve to declared runtimes.
- Deterministic path: registry -> check/dry-run -> explicit `--yes` -> install
  or smoke. Machine-specific path: profile -> saved plan -> review/dry-run ->
  explicit `--yes` execution.
- Profiles, plans, status Markdown, and event JSONL belong under
  `project/<name>/initialization/`; they are run artifacts, not source.

## CONVENTIONS

- Commands that mutate environments dry-run by default. `--yes` is the only
  execution transition; preserve it in direct installs, recipes, and plans.
- Environment precedence: root `.env` legacy fallback, then
  `DEPENDENCY/.env`, then process environment. Later non-empty values win.
- Report secret presence only as `SET` / `MISSING`. Redact probe output before
  persistence if new probes could echo credentials.
- Pass no more secrets to subprocesses than required. Never embed values in
  registry commands, plans, Markdown, JSON, events, or Codex config.
- UMA/AdsorbDiff plans may configure environments and smoke tests only after
  machine inspection. They have no authority to download checkpoints or submit
  `qsub`/`sbatch` jobs; those actions require a separate explicit user decision.
- Treat saved plan JSON as reviewed executable input. Validate schema,
  blockers, categories, working directories, and commands before execution.

## ANTI-PATTERNS

- Do not label floating manifests as bit-reproducible merely because setup is
  deterministic in control flow; distinguish resolution locks from policy.
- Do not bypass `--yes`, auto-execute generated plans, or re-decide recorded
  CUDA/checkpoint/scheduler choices inside the executor.
- Do not weaken forbidden checkpoint-download or scheduler-submit categories.
- Do not add prose sentinels as executable commands. `no-runtime` currently
  uses `No runtime install required.`; special-case/refuse execution if touched.
- Do not add a runtime or skill mapping without validating all referenced
  paths, recipe members, runtime targets, smoke commands, and manual contracts.

## COMMANDS

```bash
# Read-only registry and CLI validation
PYTHONDONTWRITEBYTECODE=1 python3 DEPENDENCY/tools/mesa_env.py --help
PYTHONDONTWRITEBYTECODE=1 python3 DEPENDENCY/tools/mesa_env.py list --recipes --skills
PYTHONDONTWRITEBYTECODE=1 python3 DEPENDENCY/tools/mesa_env.py check --all
sh -n DEPENDENCY/bootstrap.sh

# Dry-run only; add --yes solely after reviewing printed commands
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan <PLAN_JSON>
```
