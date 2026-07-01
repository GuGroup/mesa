---
name: missing-evidence-recorder
description: Record missing required scientific artifacts as explicit unresolved, excluded, or blocked evidence records without proxy substitution. Use when a workflow recipe requests charge density, Bader charge, PDOS/DOS, wavefunction/projector files, kinetic barriers, solvent data, or any other artifact that is absent, and Codex needs to create auditable JSON/CSV/Markdown summaries before updating results or manuscripts.
---

# Missing Evidence Recorder

## Scope

Use this skill when a required procedure or calculation cannot be completed
because the necessary artifact does not exist. The goal is to make the evidence
gap explicit, not to work around it with a weak proxy.

Typical cases:

- charge transfer requested but no charge density or Bader-compatible grid
  exists;
- PDOS requested but no wavefunction, projector, DOS, or PDOS output exists;
- kinetic-barrier claims requested but no transition state, NEB, or barrier
  calculation exists;
- solvation/double-layer claims requested but no explicit solvation or
  electrochemical model exists.

## Quick Start

Create a missing-evidence spec, then run:

```bash
python scripts/record_missing_evidence.py \
  --input missing_evidence_spec.json \
  --outdir path/to/unresolved_evidence \
  --project-root /path/to/project-root
```

For the input schema, read `references/input-schema.md`.

## Required Policy

- Mark missing evidence as `excluded`, `blocked`, or `unresolved`; do not mark it
  `accepted`.
- Set `not_substituted_with_proxy` to `true`.
- List the exact missing artifacts and the future artifacts needed to resolve
  the gap.
- Carry the unresolved record into result artifacts and manuscripts.
- Do not create geometry-only, energy-only, or text-only substitutes for charge,
  DOS, barrier, or solvation evidence.

## Outputs

The helper script writes:

| Artifact | Purpose |
| --- | --- |
| `missing_evidence_summary.json` | Machine-readable top-level unresolved/excluded evidence summary. |
| `missing_evidence_summary.md` | Human-readable summary for result artifacts or manuscripts. |
| `missing_evidence_records.csv` / `.json` | Flat table of missing requirements by calculation/procedure/target. |
| `execution_manifest.json` | Minimal manifest documenting command, inputs, outputs, status, and caveats. |

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
