# OER literature and provenance guide

Use this file to document where each non-DFT term came from. Do not treat the
entries below as permission to insert a number without checking temperature,
phase, standard state, functional, PAW/pseudopotential set, and thermal method.

## Core references

1. Rossmeisl, J.; Qu, Z.-W.; Zhu, H.; Kroes, G.-J.; Nørskov, J. K.
   **Electrolysis of water on oxide surfaces.** *J. Electroanal. Chem.* **2007**,
   607, 83-89. DOI: `10.1016/j.jelechem.2006.11.008`.
   - Early four-step oxide OER/CHE framework.
   - Relevant to the water-splitting thermodynamic closure.

2. Man, I. C.; Su, H.-Y.; Calle-Vallejo, F.; et al.
   **Universality in Oxygen Evolution Electrocatalysis on Oxide Surfaces.**
   *ChemCatChem* **2011**, 3, 1159-1165. DOI: `10.1002/cctc.201000397`.
   - Four-step AEM free-energy analysis, theoretical overpotential, and
     `*OH`/`*OOH` scaling.

3. Sargeant, E.; Illas, F.; Rodríguez, P.; Calle-Vallejo, F.
   **Importance of the gas-phase error correction for OER/ORR calculations.**
   *J. Electroanal. Chem.* **2021**, 896, 115178.
   DOI: `10.1016/j.jelechem.2021.115178`.
   - Supports explicit auditing of gas-phase O2 errors rather than assuming
     direct semilocal-DFT O2 is exact.

## Required provenance fields

For `o2_cycle_free_energy_eV`, record at least:

```json
{
  "source": "DOI, database record, or lab calculation ID",
  "temperature_K": 298.15,
  "standard_state": "H2O(l), H2(g), O2(g)",
  "thermal_convention": "G at 298.15 K",
  "evidence_label": "CLOSURE ONLY"
}
```

For a direct-O2 reference, additionally record:

```json
{
  "functional": "PBE",
  "paw_or_pseudopotential": "exact identifiers",
  "spin_state": "triplet",
  "cell_and_cutoff": "documented gas calculation settings",
  "correction_method": "none, fitted gas correction, or reaction closure"
}
```

## Evidence labels

- `MATCHED`: the source and current calculation settings/standard states match.
- `PARTIALLY MATCHED`: only part of the method metadata matches.
- `CLOSURE ONLY`: used only to force the overall thermodynamic cycle.
- `SCREENING ASSUMPTION`: exploratory value; not manuscript-ready.
- `UNVERIFIED`: source or convention is missing; block quantitative ranking.

## Double-counting rule

Choose exactly one O2 treatment:

1. cycle-derived O2; **or**
2. direct O2 plus one documented method-specific correction.

Never use a cycle-derived O2 and then add another O2-overbinding correction.
