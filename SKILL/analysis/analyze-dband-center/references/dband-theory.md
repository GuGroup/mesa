# D-Band Center Theory — Interpretation Guide

## Purpose

Interpret d-band center values obtained from d-PDOS integration to qualitatively
assess adsorption strength, reactivity, and catalytic trends of surface/active
metal sites.

Unless an adsorbate-induced analysis is explicitly requested, this guide uses
the d-PDOS of an **adsorbate-free clean surface before adsorbate interaction**.
The adsorption energy belongs to the property being explained; the adsorbate
does not belong in the default d-band input structure.

---

## Theory Core

### Definition

The d-band center (ε_d) is the first moment of the d-projected density of states
of a metal atom.  It is conventionally reported as a relative energy (eV) with
the Fermi level set to E_F = 0.

### Physical Picture

When a frontier orbital of an adsorbate hybridizes with the d-states of a metal
surface, bonding and antibonding states are formed.  The closer the d-band sits
to E_F, the stronger the adsorbate–metal coupling, and—in general—the stronger
the adsorption bond.

### Main Claim

For a **fixed target adsorbate** and matched adsorption-site definition, an
upward shift of the corresponding **clean-surface** ε_d across comparable
catalyst surfaces tends to correlate with stronger adsorption, while a downward
shift tends to correlate with weaker adsorption. "Fixed target adsorbate" means
that the adsorption-energy trend uses the same adsorbate; it does not instruct
the analyst to place that adsorbate in the DOS structures.

---

## Interpretation Rules

### Reference Checks

- Always confirm that ε_d is reported relative to E_F.
- For the conventional descriptor, verify that every input is an
  **adsorbate-free clean slab**. Do not mix clean and adsorbate-covered values.
- Compare only values obtained with the **same functional, clean-slab relaxation
  protocol, facet, slab thickness, vacuum, k-point mesh, magnetic treatment,
  projection scheme, and integration window**.
- Use the same target adsorbate, coverage convention, and adsorption-site
  definition when correlating clean-surface ε_d with adsorption energies.
- Prefer surface-atom / site-resolved ε_d when it is actually available. The
  current `analyze_dband.py` CLI is element-resolved and aggregates all atoms of
  the selected element, so its output must not be described as site-resolved.

### Adsorbate-Covered Exception

Adsorbate-covered d-PDOS answers a different question: how adsorption has
perturbed the electronic structure. Use it only when that post-adsorption
question is explicit.

- Pair every covered structure with its corresponding clean slab.
- Match adsorbate identity, adsorption site, and coverage across covered
  systems.
- Label covered results explicitly and report Δε_d(adsorption) =
  ε_d(covered) − ε_d(clean).
- Do not use ε_d(covered) as though it were the conventional clean-surface
  descriptor for predicting adsorption strength.

### Sign Convention

| Observation | Terminology |
|---|---|
| ε_d is less negative or more positive | **Up-shifted / closer to E_F** |
| ε_d is more negative | **Down-shifted / farther from E_F** |

### Trend Interpretation

| Shift | Expected effect |
|---|---|
| **Upshift** | Stronger adsorption, stronger activation of adsorbate bonds, possible poisoning or desorption difficulty |
| **Downshift** | Weaker adsorption, easier desorption, possible insufficient activation |
| **Optimum** | Per the Sabatier principle, intermediate binding—neither too strong nor too weak—is most favorable for catalytic activity |

### Comparison Language Templates

- "A has a higher ε_d than B, so A is expected to bind the adsorbate more strongly."
- "A lower ε_d suggests weakened metal–adsorbate hybridization and reduced adsorption strength."
- "If activity follows a volcano trend, the best catalyst is not necessarily the
  one with the highest ε_d, but the one near optimal binding."

---

## Allowed Claims

- The d-band center is a descriptor of adsorption strength.
- Within the same family of metals, alloys, or surfaces, changes in ε_d can
  explain adsorption-strength trends.
- An ε_d upshift can promote stabilization of reaction intermediates and
  activation of chemical bonds.
- An ε_d downshift can alleviate over-adsorption of intermediates and improve
  desorption or catalytic turnover.

## Claims NOT Allowed

- **Do not** determine absolute adsorption energies from ε_d alone.
- **Do not** use an adsorbate-covered ε_d as the conventional clean-surface
  descriptor or silently mix clean and covered structures in one trend.
- **Do not** directly compare surfaces with different compositions, oxidation
  states, spin states, or adsorbate types and draw definitive conclusions.
- **Do not** call the current CLI's element-aggregated result site-resolved.
- **Do not** claim that ε_d fully explains the electronic structure of oxides,
  strongly correlated materials, or ionic materials.
- **Do not** attribute numerical differences to physical differences when the
  calculation window, PDOS projection, smearing, or E_F alignment differs
  between systems.

---

## Additional Checks

| Check | Reason |
|---|---|
| **d-band width** | A broader d-band can weaken the explanatory power of the center alone |
| **d-band filling / DOS at E_F** | Needed to assess conductivity and antibonding occupation |
| **Site specificity** | In alloys, use a genuinely site-projected method when the adsorption-site atoms must be isolated; the current CLI is element-resolved |
| **Cross-validation** | Corroborate with adsorption energy, charge-density difference, or reaction barrier calculations |

---

## Response Template

When reporting the current CLI's conventional clean-surface result, use this
pattern and name the selected metal element rather than claiming site
resolution:

> "For the adsorbate-free **{system}** surface, the element-resolved d-band
> center of **{metal element}** is **{value} eV**,
> which is **{up/down}-shifted** relative to the reference **{ref}**
> (**{ref_value} eV**).  This indicates that the d-states are positioned
> **{closer to / farther from}** E_F, indicating an expected trend toward
> **{stronger / weaker}** d-orbital hybridization with the target
> **{adsorbate}** and consequently **{stronger / weaker}** adsorption. For the
> **{reaction_step}** step, this
> suggests **{expected_effect}** in terms of
> **{activation / desorption / poisoning / activity}**.

---

## Minimal Decision Flow

1. Verify that candidate and reference inputs are adsorbate-free clean slabs.
2. Confirm that the values are referenced to E_F = 0.
3. Fix the target adsorbate and adsorption-site definition for the adsorption
   trend being interpreted.
4. Choose a clean reference surface with matched computational conditions.
5. Compute Δε_d = ε_d(clean candidate) − ε_d(clean reference).
6. If Δε_d > 0 → interpret as a trend toward **stronger adsorption**.
7. If Δε_d < 0 → interpret as a trend toward **weaker adsorption**.
8. Assess catalytic performance from a **volcano / Sabatier** perspective and
   locate the optimal intermediate-binding regime.
