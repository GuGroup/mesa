# Analysis Domain Workflow

Use this manual for evidence readiness, energy diagrams, descriptor assembly,
and scientific caveat handling after recipe-backed calculations exist.

Analysis turns validated outputs into bounded evidence. It does not run new
calculations, hide missing data, or promote proxies into full proof.

# Skills

- `evaluate-energy-diagram`
- `construct-energy-diagram`
- `assemble-alkaline-her-descriptors`
- `analyze-dband-center`
- `charge-flow-analyzer`

Use `analyze-relaxation-results` from the calculation domain for trajectory or
optimization sanity checks before higher-level analysis.

# Entry Requirements

Before analysis, confirm:

- source calculations are linked to explicit recipes;
- required structures, energies, vibrations, or bookkeeping artifacts exist;
- E-level `execution_manifest.json` files identify each actual attempt;
- recipe-local C-level manifests link the exact artifacts used by each
  calculation;
- separate diagnosis or evaluation artifacts identify acceptance and caveats;
- terminal E-level gaps in recipe-required artifacts are recorded with
  `record-missing-evidence`.

# Evidence Readiness

Before manuscript intake:

- Use calculation-result checks for relaxations, trajectories, and raw outputs.
- Use `construct-energy-diagram` only when its data model matches the required
  chemistry.
- Use `evaluate-energy-diagram` when the task is evaluating an energy profile,
  reaction-energy sequence, or comparable diagram artifact.
- Use `assemble-alkaline-her-descriptors` for bounded alkaline HER descriptor
  assembly, ranking, or free-energy summaries when the target and data fit the
  skill.
- Use `record-missing-evidence` for absent required evidence only after the
  corresponding E-level manifest-diagnosis-repair loop terminates.
- Require terminal E- and P-level diagnosis/repair handling before treating
  evidence as manuscript-ready.
- Separate accepted, accepted-with-caveat, exploratory, failed, and excluded
  artifacts.

# Caveat Rules

Do not hide scope mismatches. Explicitly flag when any of these are outside the
available evidence or skill scope:

- charged species;
- pH corrections;
- electrode potential;
- solvation;
- kinetic barriers;
- DOS, PDOS, Bader charge, charge density, or wavefunction data;
- isotope, entropy, or vibrational corrections;
- experimental comparability.

Do not silently replace:

- full free energies with electronic energies;
- kinetics with thermodynamics;
- DOS or charge evidence with geometry descriptors;
- charged electrochemical states with neutral gas references.

# Alkaline HER Boundary

If the target task is alkaline HER, `Delta G_H` evidence alone is
descriptor-level support, not a complete alkaline mechanism, unless the target
was explicitly narrowed to H adsorption only.

Use descriptor evidence to support a bounded claim, not to claim complete
mechanistic proof of alkaline HER without the missing water dissociation,
hydroxyl, electrolyte, solvation, potential, or kinetic evidence.

# Handoff

The manuscript or result artifact may use only trusted structures, tables,
figures, and result artifacts. Missing or caveated items must remain visible in
the result artifact and in the subsequent strategy update.
