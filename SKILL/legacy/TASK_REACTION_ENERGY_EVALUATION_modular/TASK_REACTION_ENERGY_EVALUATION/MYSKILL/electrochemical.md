# Electrochemical Knowledge for Catalyst Performance Analysis

## Purpose

This reference gives the minimum electrochemical background needed to interpret DFT reaction-energy tables in this MESA skill. It is intentionally practical: the evaluator can rank catalysts from thermodynamic free-energy data, but it must not overclaim kinetic rates, full selectivity, or experimental overpotential without matching experimental definitions.


## Required use when LLM interpretation is involved

If an LLM is used to interpret catalyst performance, assign PDS/RDS labels, discuss competing reactions, or write conclusions, this file must be consulted before the LLM writes the interpretation. The deterministic Python output is the numerical source of truth; the LLM should only add cautious domain interpretation consistent with this reference.

Priority rules:

1. Never call a pure adsorption/desorption step an overpotential.
2. Never equate PDS with RDS unless kinetic evidence is provided.
3. Treat competing reaction data as selectivity warnings rather than final selectivity predictions.
4. State missing electrochemical context such as pH, reference electrode, potential scale, coverage, and solvent assumptions.

## Core electrochemical concepts

### Electrolytic cell

An electrolytic cell drives a non-spontaneous redox process using an applied electrical potential. A cathodic half-reaction consumes electrons, and an anodic half-reaction produces electrons.

### Redox reaction

A redox reaction combines a reduction half-reaction and an oxidation half-reaction.

- **Reduction**: gain of electrons.
- **Oxidation**: loss of electrons.
- In electrocatalysis, reduction reactions normally occur at the cathode and oxidation reactions normally occur at the anode.

### Electrolyte

An electrolyte is an ion-conducting medium. It transports ionic charge through solution or membrane phases but does not conduct electrons like a metal electrode.

### Electrode potential and reference electrodes

Absolute single-electrode potentials are not measured directly in routine experiments. Potentials are reported relative to reference electrodes such as SHE, RHE, Ag/AgCl, or Hg/HgO.

- **SHE**: standard hydrogen electrode, conventionally tied to the hydrogen redox couple under standard conditions.
- **RHE**: reversible hydrogen electrode, a pH-dependent hydrogen reference in the electrolyte of interest.
- When comparing DFT and experiment, always state the reference scale and pH correction.

## DFT free energy interpretation

### Free energy of an intermediate

A common corrected free energy expression is:

```text
G = E_DFT + ZPE - T*S + correction
```

The input table may already contain corrected free energies. The skill assumes the row values are a reaction-coordinate energy diagram unless the user states otherwise.

### Step free energy

For consecutive reaction-coordinate states:

```text
ΔG_step = G_next - G_previous
```

Positive ΔG means the step is uphill under the chosen reference conditions.

### CHE approximation

In the computational hydrogen electrode approximation, a proton-electron pair is referenced to one half of H2 under the chosen potential/pH convention. This is useful for proton-coupled electron transfer (PCET) steps, but it does not automatically describe pure adsorption, desorption, solvent rearrangement, or kinetic barriers.

## PDS, RDS, limiting potential, and overpotential

### Potential-determining step (PDS)

The PDS is the elementary electrochemical step with the largest uphill free-energy change after applying the chosen electrochemical convention. It is a thermodynamic descriptor.

### Rate-determining step (RDS)

The RDS is the slowest kinetic step and should ideally be identified from activation barriers or kinetic modeling. Do not equate PDS with RDS unless additional kinetic evidence supports it.

### Limiting potential

For a reduction reaction in a simple free-energy diagram, a common thermodynamic estimate is:

```text
U_L = -max(ΔG_electrochemical_step)
```

For OER using the four-step adsorbate evolution mechanism:

```text
U_L = max(ΔG1, ΔG2, ΔG3, ΔG4)
η_OER = U_L - 1.23 V
```

### Overpotential warning

Do **not** classify a non-electrochemical step energy as overpotential. Pure adsorption/desorption such as `NO3- -> *NO3` or `*NH3 -> NH3` can be important, but it should be reported as adsorption/desorption thermodynamics unless the input explicitly defines it as part of an electrochemical elementary step.

## Common reactions handled algorithmically

### HER: hydrogen evolution reaction

Main descriptor:

```text
ΔG_H* = G(*H) - G(*)
```

A value close to 0 eV is usually favorable in a thermodynamic HER descriptor analysis. This does not replace kinetic analysis of Volmer, Heyrovsky, or Tafel barriers.

### OER: oxygen evolution reaction

Default acidic/RHE-style adsorbate evolution mechanism:

```text
*      -> *OH
*OH    -> *O
*O     -> *OOH
*OOH   -> O2 + *
```

The evaluator calculates the largest of the four step free energies and estimates `η = max(ΔG_i) - 1.23 V` when the input energies are compatible with this convention.

## Competing reactions

A competing reaction is a side reaction that consumes the same electrons, protons, reactants, surface sites, or potential window as the target reaction. It is not merely any reaction that appears in the system.

Examples:

- For cathodic NO3RR, CO2RR, NRR, and many other reductions, **HER** is often the major competing reaction because it consumes proton/electron equivalents and active sites.
- For NO3RR, partial reduction to nitrite, NO, N2, N2O, or other nitrogen-containing products can compete with NH3 formation.
- For OER, catalyst oxidation/dissolution or electrolyte oxidation can compete depending on material and conditions.

How this skill treats competing reactions:

1. The target reaction ranking is computed from the target reaction-energy table.
2. Optional competing reaction descriptors can be supplied under `competing_reactions` or `competing_descriptors`.
3. The report treats competing descriptors as selectivity warnings, not final selectivity predictions.
4. A selectivity claim needs comparable reaction conditions, surface coverages, kinetic barriers, transport assumptions, and product quantification.

## Naming conventions used by the skill

Common reactions use established electrocatalysis names and abbreviations:

- HER: hydrogen evolution reaction
- OER: oxygen evolution reaction
- ORR: oxygen reduction reaction
- NO3RR: nitrate reduction reaction
- NO2RR: nitrite reduction reaction
- NRR: nitrogen reduction reaction
- CO2RR: carbon dioxide reduction reaction

For less common reactions, the skill constructs a conservative formula-based name such as `<species name> reduction reaction` and an abbreviation such as `<formula>RR`. If the species is not in the internal name map, the formula is preserved to avoid hallucinated systematic names.
