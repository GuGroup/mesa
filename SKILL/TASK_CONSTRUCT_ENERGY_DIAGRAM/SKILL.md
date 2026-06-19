Energy Diagram Construction Skill

Purpose

Construct a reaction free-energy profile from:

1. A balanced reaction pathway (reaction.json)
2. A calculation registry (map.json)
3. VASP OUTCAR files

The skill computes:

G = E + ZPE - TS

for each reaction state and returns relative free energies referenced to the first state.

Transition states are not currently supported.

⸻

Inputs

reaction.json

Balanced reaction pathway metadata.

Example:

{
  "reaction_pathway": "HNO3(g)>*NO3>*NO2>*NO",
  "states": [...]
}

Each state contains:

{
  "label": "*NO2",
  "balanced_state": [
    {
      "species": "NO2",
      "phase": "ADS",
      "coefficient": 1.0
    },
    {
      "species": "H2O",
      "phase": "GAS",
      "coefficient": 1.0
    }
  ],
  "slab_count": 0.0
}

⸻

map.json

Calculation registry.

Example:

{
  "species": "NH3",
  "phase": "GAS",
  "calc_mode": "vib",
  "outcar": "...",
  "thermo": {
    "geometry": "nonlinear",
    "symmetrynumber": 3,
    "spin": 0
  }
}

Each species-phase pair should have:

static calculation

and optionally:

vib calculation

⸻

Thermodynamic Model

ADS species

Use:

ase.thermochemistry.HarmonicThermo

Free energy:

G = E + ZPE - TS

where:

E = static DFT energy
ZPE = harmonic zero-point correction
TS = harmonic entropy contribution

⸻

GAS species

Use:

ase.thermochemistry.IdealGasThermo

Free energy:

G = E + ZPE - TS

Required metadata:

{
  "geometry": "...",
  "symmetrynumber": ...,
  "spin": ...
}

Examples:

Species	Geometry	Symmetry Number	Spin
H2	linear	2	0
H2O	nonlinear	2	0
NH3	nonlinear	3	0
HNO3	nonlinear	1	0

⸻

Slab Contribution

The reaction metadata contains:

{
  "slab_count": 1.0
}

State free energies must include:

slab_count × G_slab

where:

G_slab = E_slab

using the static slab calculation.

Vibrational corrections are currently not applied to slabs.

⸻

State Energy

For each state:

G_state =
Σ coefficient_i × G_species_i
+
slab_count × G_slab

where:

G_species_i =
E_i + ZPE_i - TS_i

⸻

Reference State

The first reaction state is used as the reference:

ΔG(state) =
G(state)
-
G(reference)

⸻

Output

Return:

{
    "HNO3(g)": 0.000,
    "*NO3": -0.231,
    "*NO2": 0.152,
    "*NO": 0.681,
    ...
}

and optionally:

{
    "labels": [...],
    "relative_energies": [...]
}

for plotting.

⸻

Required Validation

Raise an error if:

missing static calculation
missing slab calculation
missing thermo metadata for GAS vib calculation
unknown phase
duplicate species-phase-calc_mode entries

Do not silently guess thermodynamic parameters.

⸻

Current Scope

Supported:

ElectroChemPolicy reaction pathways
CHON chemistry
ADS + GAS species
Static energies
Vibrational corrections
Free-energy diagrams

Not supported:

Transition states
Kinetic barriers
Charged species
Potential-dependent free energies
Thermal catalytic bookkeeping
Solvation corrections
