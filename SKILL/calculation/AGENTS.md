# CALCULATION KNOWLEDGE BASE

## OVERVIEW

Recipe-authorized execution layer for the calculation backend selected by the
root workflow, including backend-specific relaxation/vibration, input
preparation or inspection, endpoint analysis, and reaction bookkeeping.

## WHERE TO LOOK

| Need | Location | Local contract |
|---|---|---|
| Domain routing | `workflow.md` | Read after the root workflow policy selection |
| UMA relaxation | `relax-uma-trajectory/` | POSCAR-only controller input |
| UMA vibrations | `calculate-uma-vibrational-frequencies/` | Relaxed POSCAR preferred |
| Endpoint gate | `analyze-calculation-results/` | Existing outputs only |
| VASP helper | `manage-vasp-jobs/` | Use only within the root workflow policy boundary |
| Reaction bookkeeping | `balance-reaction-pathway/` | `tools.main.run` is the entry point |
| Runtime ownership | `../../DEPENDENCY/runtimes.yaml` | Never mix runtime environments |
| Recipe-local state | `P###_*/calculations/C###_*/execution/` | Artifacts and manifest live here |

## CONVENTIONS

- Authorization is one concrete `P###/C###/recipe.json`; match method, structure,
  and output intent before execution. Record missing prerequisites, do not infer.
- Write outputs below `C###_<slug>/execution/`. Keep generated recipe JSON/Markdown
  immutable; execution truth belongs in `execution_manifest.json`.
- Manifests name source recipe/procedure, invoked skill or script, resolved command,
  inputs, outputs, validation, caveats, and policy boundaries.
- Acceptance vocabulary is closed: `accepted`, `accepted-with-caveat`,
  `exploratory`, `failed`, or `excluded`.
- UMA uses a decision/execution split: `MYSKILL/*_controller.py` owns scientific
  settings and writes `results/resolved_*.json`; `EXTSKILL/*_runner.py` consumes
  that config unchanged and produces fixed artifacts.
- Upstream UMA input supplies `poscar_path` plus execution context only. Run the
  controller, never the runner directly, unless reproducing an already-resolved run.
- From the repository root, UMA uses the configured external FAIRChem Python:
  `python SKILL/calculation/relax-uma-trajectory/MYSKILL/uma_relax_traj_controller.py --input input.json --output controller_output.json --workdir <run_dir> [--dry-run]`
- Vibration controller mirrors that contract:
  `python SKILL/calculation/calculate-uma-vibrational-frequencies/MYSKILL/uma_vib_freq_controller.py --input input.json --output controller_output.json --workdir <run_dir> [--dry-run]`
- Runtime device and submission choices must follow the root workflow policy or
  execution plan. Use qsub wrappers only when qsub execution is explicit;
  controller config must exist first.
- VASP runtime is the installed `vasp-job` uv tool. Allowed commands are
  constrained by the root workflow policy: use prepare/dry-run/status commands
  when execution is not enabled, and use submit only when the selected policy
  explicitly enables VASP execution.
- Analyze existing endpoints in the modeling runtime:
  `mamba run -n modeling python SKILL/calculation/analyze-calculation-results/scripts/analyze_calculation_result.py --input <output-or-traj> --outdir <analysis-dir>`.
- Analyzer `pass/warn/fail` gates endpoint reuse; it does not create missing energy,
  vibration, convergence, or claim evidence. Preserve recipe evidence requirements.
- Reaction balancing runs in `mesa-general` (`uv run`) and only through
  `from tools.main import run`; balanced metadata is bookkeeping, not a calculation.
- No tests live under `SKILL/calculation`. Validate controller dry-runs, required
  artifacts, JSON envelopes, manifest state, and package-level runtime checks.

## ANTI-PATTERNS

- No calculation without explicit recipe authorization; no ad hoc procedure reading.
- No caller-supplied UMA model/device/optimizer/thresholds smuggled into required input.
- No direct runner invocation before controller resolution; no hand-edited resolved config.
- No `vasp-job submit`, VASP qsub, or backend submission unless the selected
  root workflow policy explicitly enables it; preparation is not execution.
- No result analyzer used to launch/repair jobs or to promote a proxy into final evidence.
- No success inferred from file presence alone; require validation and an acceptance state.
- No execution status written back into `recipe.json`, `recipe.md`, or recipe indexes.
