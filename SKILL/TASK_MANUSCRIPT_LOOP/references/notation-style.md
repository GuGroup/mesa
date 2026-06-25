# Notation and Style Contract

`paper/logic/notation.yaml` is the canonical list of symbols, names, units, and
formatting choices.

## Required Categories

- `systems`: catalyst, surface, adsorbate, facet, and model names.
- `methods`: functional, basis or cutoff, solvation model, dispersion, spin,
  charge, and convergence notation.
- `energies`: adsorption, reaction, activation, free-energy, and correction
  symbols with units.
- `figures`: figure labels and short references.
- `abbreviations`: first-use expansion and allowed short form.

## Style Defaults

- Target style is Nature-family.
- Use consistent surface notation such as `Pt(111)`.
- Units must be explicit in table headers, axes, and method descriptions.
- Do not mix equivalent symbols for the same quantity.
- Do not introduce notation in prose unless it exists in `notation.yaml`.

## Lint Boundary

This reference defines the contract only. Validator and lint implementation is
owned by later Todos.
