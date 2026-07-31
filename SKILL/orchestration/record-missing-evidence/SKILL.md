---
name: record-missing-evidence
description: Record terminally missing scientific artifacts as unresolved, excluded, or blocked evidence without proxy substitution. Use only after the E-level manifest-diagnosis-repair loop ends with a non-pass diagnosis and a no_repair or escalate decision.
---

For MESA end-to-end use, read `SKILL/orchestration/workflow.md` before applying this skill.

# Missing Evidence Recorder

## Scope

Use this skill after E-level execution has been manifested, diagnosed, and
repair handling has terminated, but a required artifact still does not exist.
The goal is to make the final evidence gap explicit, not to diagnose execution
or work around the gap with a weak proxy.

Typical cases:

- charge transfer requested but no charge density or Bader-compatible grid
  exists;
- PDOS requested but no wavefunction, projector, DOS, or PDOS output exists;
- kinetic-barrier claims requested but no transition state, NEB, or barrier
  calculation exists;
- solvation/double-layer claims requested but no explicit solvation or
  electrochemical model exists.

## Quick Start

Require the terminal E attempt's:

- `execution_diagnosis.json` with verdict `warn`, `fail`, or `unknown`;
- `repair_decision.json` with decision `no_repair` or `escalate`.

Reference both artifacts in a temporary missing-evidence spec, then run:

```bash
python3 SKILL/orchestration/record-missing-evidence/scripts/record_missing_evidence.py \
  --input /tmp/missing_evidence_spec.json \
  --output project/<project_name>/strategy_execution/S1_explicit_recipe/P006_example/calculations/C001_example/execution/units/E009-R2/missing_evidence.json \
  --project-root .
```

For the input schema, read `references/input-schema.md`.

## Required Policy

- Mark missing evidence as `excluded`, `blocked`, or `unresolved`; do not mark it
  `accepted`.
- Set `not_substituted_with_proxy` to `true`.
- List the exact missing artifacts and the future artifacts needed to resolve
  the gap.
- Record evidence only after the E-level manifest-diagnosis-repair loop
  terminates.
- Write the records in the terminal E attempt directory beside the diagnosis
  and repair decision.
- Keep the input spec temporary; do not preserve it as a second execution
  artifact.
- Carry the unresolved record into result artifacts and manuscripts.
- Never create, replace, or update `execution_manifest.json`; manifests remain
  the responsibility of `write-execution-manifest`.
- Do not create geometry-only, energy-only, or text-only substitutes for charge,
  DOS, barrier, or solvation evidence.

## Outputs

The helper script writes exactly one artifact:

| Artifact | Purpose |
| --- | --- |
| `missing_evidence.json` | Canonical machine-readable terminal evidence-gap record, including provenance and requirements. |

## Claim Policy

Allowed wording:

- "Charge-transfer evidence was excluded because no density artifact was
  generated."
- "PDOS remains unresolved pending wavefunction/projector/DOS outputs."

Not allowed:

- "Charge transfer is supported by geometry" unless a charge-density method was
  actually run.
- "PDOS confirms the mechanism" unless PDOS/DOS artifacts exist and were
  analyzed.
