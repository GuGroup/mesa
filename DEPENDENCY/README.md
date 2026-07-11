# MESA Dependency Layer

`DEPENDENCY/` is the bootstrap and runtime-dispatch layer for this repository.
It does not replace `ENVIRONMENT/`; it points to the existing environment specs
and adds a small common runtime plus preflight tooling.

Fresh-clone entry points:

```bash
# Linux/macOS: check OS, install uv if needed, then run bootstrap.
bash DEPENDENCY/bootstrap.sh

# Windows PowerShell: check OS, install uv if needed, then run bootstrap.
powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1

# After uv is installed, run checks directly through uv-managed Python.
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-core
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba --install-core --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --analyze-nondeterministic
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --write-handoff
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --recipes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --all
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py check mesa-modeling
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py install mesa-general --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py notify --message "Initialization status refreshed."
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py generate-runtime-plan mesa-uma
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan project/mos/runtime_plans/mesa-uma_plan.json --yes
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py handoff
```

The helper is stdlib-only. The recommended path uses `uv` to provide Python, so
users do not need to install Python manually before bootstrapping.

Secret and checkpoint access policy:

- `OPENAI_API_KEY` and `MP_API_KEY`/`PMG_MAPI_KEY` are checked as core keys.
- `HF_TOKEN` is checked as optional checkpoint access for gated/private
  Hugging Face downloads.
- `HF_HOME` is checked as optional Hugging Face token/cache location.
- Missing `HF_TOKEN` does not fail bootstrap unless a later explicit checkpoint
  download needs it.

Mamba policy:

- Existing `mamba` on `PATH` is used as-is.
- Existing `micromamba` on `PATH` is accepted, but conda-env runtime commands
  still expect a `mamba` command.
- `bootstrap --install-mamba` installs micromamba into `DEPENDENCY/bin`, creates
  a repo-local `mamba` wrapper, and uses `DEPENDENCY/.micromamba` as
  `MAMBA_ROOT_PREFIX`.
- On Windows PowerShell, use
  `powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba`.
- The plain bootstrap check reports the exact install command without changing
  mamba state.

Core dependency recipe:

- `bootstrap --install-core` dry-runs the first-install recipe for
  `mesa-general`, `paper-search-mcp`, `mesa-paper-search`, `mesa-modeling`, and
  `mesa-manuscript`.
- `bootstrap --install-mamba --install-core --yes` executes that recipe.
- During execution, each runtime is smoke-tested first. Healthy runtimes are
  skipped; unhealthy runtimes are installed and smoke-tested again.
- The core recipe intentionally excludes UMA, AdsorbDiff, GPU/CUDA setup,
  checkpoint downloads, and qsub-dependent submission setup.
- On Windows PowerShell, use
  `powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba -InstallCore -Yes`.

Non-deterministic analyzer:

- `DEPENDENCY/non_deterministic_runtimes.yaml` records deterministic
  requirements, analyzer output names, and Codex decision points for UMA and
  AdsorbDiff.
- `uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py analyze-nondeterministic`
  writes `project/mos/nondeterministic_profile.json` and
  `project/mos/nondeterministic_profile.md`.
- `bootstrap --analyze-nondeterministic` writes the same files during
  bootstrap.
- The analyzer is read-only with respect to dependencies: it records OS, tool,
  env, GPU/CUDA probe, scheduler probe, checkpoint, Python/env, and runtime
  decision facts, but does not install CUDA wheels, download checkpoints, or
  submit jobs.
- Secret values are never written; token-like variables are recorded only as
  `SET` or `MISSING`.
- Legacy `handoff` and `bootstrap --write-handoff` still write
  `project/mos/machine_profile.json` and `project/mos/dependency_handoff.md`.

Notification, planning, and execution policy:

- `notify`/`status` writes `project/mos/initialize_status.md` and appends to
  `project/mos/initialize_events.jsonl`.
- `generate-runtime-plan <runtime>` writes a saved plan under
  `project/mos/runtime_plans/`. It does not execute commands.
- `execute-runtime-plan <plan.json>` dry-runs by default. It executes only with
  `--yes`.
- Blocked plans are refused even with `--yes`.
- Runtime plan execution only runs commands stored in the reviewed plan JSON.
- Current non-deterministic plans do not download checkpoints or submit
  scheduler jobs.

Runtime policy:

- Use `mesa-general` for lightweight common scripts and OpenAI API wrappers.
- Use `mesa-modeling` for structures, slabs, adsorbates, trajectories, and ASE.
- Use `mesa-manuscript` for manuscript work, figure export, Pandoc, and
  publication plotting.
- Keep `mesa-paper-search` and `paper-search-mcp` separate because they expose
  similar commands but are different packages.
- Keep UMA, AdsorbDiff, and VASP isolated because their runtime assumptions are
  machine-specific.
