# NO3RR literature and provenance guide

Read this file before assigning any HNO3/NO3- correction. The purpose is to
record a thermodynamic cycle and its applicability, not to maintain a universal
lookup table of constants.

## Core references

1. Calle-Vallejo, F.; et al.
   **Nitrate reduction on Ag and Au: a mechanistic DFT study.**
   *Phys. Chem. Chem. Phys.* **2013**. DOI: `10.1039/C2CP44620K`.
   - Uses an HNO3/H2 reference to avoid direct use of a vacuum nitrate-anion
     energy for aqueous nitrate.
   - Its supporting thermochemical bookkeeping reports the commonly reused
     HNO3 molecular correction example and separate phase/acid-cycle terms.
   - Treat those values as source- and method-specific.

2. Urrego-Ortiz, R.; Builes, S.; Calle-Vallejo, F.
   **Impact of Intrinsic Density Functional Theory Errors on the Predictive
   Power of Nitrogen Cycle Electrocatalysis Models.** *ACS Catal.* **2022**,
   12, 4784-4791. DOI: `10.1021/acscatal.1c05333`.
   - Demonstrates large, species-dependent errors for oxidized gas-phase
     nitrogen compounds.
   - Supports rejecting a single HNO3-derived correction for all NOx species.

3. Urrego-Ortiz, R.; et al.
   **Gas-phase errors in computational electrocatalysis: a review.**
   *EES Catalysis* **2024**. DOI: `10.1039/D3EY00126A`.
   - Reviews molecule- and group-dependent gas-phase errors and correction
     strategies.

## Correction ledger

Store the HNO3 terms separately:

```json
{
  "hno3_molecular_correction_eV": 1.12,
  "hno3_gas_to_liquid_eV": -0.075,
  "hno3_liquid_to_nitrate_plus_proton_eV": -0.317
}
```

The numbers above are shown only to identify the literature-style decomposition.
The calculation must also include provenance and evidence labels. The script
never inserts the 1.12 eV value automatically.

## Minimum provenance

```json
{
  "source": "DOI or lab calculation ID",
  "functional": "exact functional",
  "paw_or_pseudopotential": "exact identifiers",
  "molecular_spin_state": "if relevant",
  "gas_box_cutoff_kmesh": "documented settings",
  "thermal_method": "ZPE/enthalpy/entropy convention",
  "temperature_K": 298.15,
  "phase_and_standard_state": "gas/liquid/aqueous definitions",
  "evidence_label": "MATCHED | PARTIALLY MATCHED | CLOSURE ONLY | SCREENING ASSUMPTION | UNVERIFIED"
}
```

## Transferability rule

A correction for HNO3 can correct the HNO3 reference in the nitrate cycle. It
must not be copied to HNO2, NO2, NO, N2O, adsorbed NOx, or every species with an
N-O bond. Add a distinct species/group correction only when its own benchmark
and provenance exist.

## pH and electrode scale

The standard acid cycle is stored separately from the pH/activity term. On RHE,
internal proton-electron steps do not receive an extra explicit pH shift, but
the nitrate-feed protonation/transfer offset can still change with pH. On SHE,
the CHE proton-electron chemical potential carries the explicit pH term.
