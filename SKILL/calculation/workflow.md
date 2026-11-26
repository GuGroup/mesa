# Calculation

Use the backend and submission constraints in the task. Supply structures,
settings, and output paths directly to the chosen skill.

- Use `relax-uma-trajectory` for UMA relaxation and
  `calculate-uma-vibrational-frequencies` for UMA frequencies.
- Use `manage-vasp-jobs` for VASP input preparation, submission, and status
  inspection when the task authorizes those actions.
- Use `balance-reaction-pathway` for balanced reaction and state definitions.
- Use `analyze-relaxation-results` to inspect available relaxation outputs.

Keep the tool's inputs, logs, and available outputs. Report completed and failed
jobs, convergence, geometry warnings, and which values are usable. Label
prepared inputs and dry runs as such. For vibrational work, report important
imaginary or unstable modes as well as the usable frequencies and corrections.
