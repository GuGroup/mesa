# Methods Formalism Guide

Use this guide as a conditional reference while writing the four supported
Methods sections. The evidence digest is authoritative for project-specific
values and procedures. Do not copy an example into public prose unless the
corresponding fact is present in the digest.

## Selection rule

- Include only calculator, code, optimizer, convergence, thermodynamic, and
  electrochemical details supported by the evidence digest.
- Omit a formalism when the project did not use it.
- Do not leave bracketed placeholders such as `[FMAX]` or `{{VALUE}}` in the
  manuscript output.
- Keep equations in `equation` content blocks rather than embedding equations
  in paragraph text.
- Report the project convention explicitly when a gas pressure, electrode
  potential, pH, or standard state is supplied.

## Geometry optimization examples

### DFT branch

Use this pattern only when the evidence contains the relevant DFT settings:

> Electronic-structure calculations were performed using [CODE] with the
> [FUNCTIONAL] exchange-correlation functional and [PAW/PSEUDOPOTENTIAL]
> description. The [BULK/SURFACE]-appropriate [K-POINT] mesh and
> [CUTOFF] eV plane-wave cutoff were used, and structures were optimized until
> [CONVERGENCE CRITERION].

Replace every bracketed item from evidence before producing public prose. Omit
an item when its value is unavailable rather than guessing it.

### UMA/ASE branch

Use this pattern only when the evidence records the corresponding calculator
and optimizer:

> Geometry optimization was performed with [MODEL/CALCULATOR] through ASE
> using the [OPTIMIZER] algorithm. Optimization was considered converged when
> the maximum force was below [FMAX] eV Å−1, subject to a maximum of [MAXIMUM
> STEPS] steps.

FIRE is an example, not a default. Do not write FIRE, ASE, UMA, FAIRChem, or a
model name unless the calculation evidence explicitly identifies it.

## Vibrational and Gibbs corrections

When UMA energies are combined with thermochemical corrections, use scientific
methodology language such as:

\[
G_i(T) = E_{\mathrm{UMA},i}
       + H_{\mathrm{trans},i}(T)
       + H_{\mathrm{rot},i}(T)
       + H_{\mathrm{vib},i}(T)
       - T\left[S_{\mathrm{trans},i}(T)
       + S_{\mathrm{rot},i}(T)
       + S_{\mathrm{vib},i}(T)\right].
\]

Here, `E_UMA` is the energy of the relaxed structure predicted by UMA. The
zero-point energy is included in the vibrational enthalpy. For gas-phase
species, translational, rotational, and vibrational contributions are included;
for adsorbates, only vibrational contributions are retained because translation
and rotation are constrained; and for the clean slab, only `E_UMA` is used.
Retain only the terms that were actually included in the calculation.

For gas-phase species, include pressure dependence only when the evidence
provides a pressure or standard state:

\[
\mu(T,p) = \mu^{\circ}(T,p^{\circ})
          + k_{\mathrm{B}}T\ln\left(\frac{p}{p^{\circ}}\right).
\]

If vibrational frequencies were evaluated, describe the finite-displacement
method and the treatment of the resulting modes. Do not name internal software
classes, workflow components, skill names, or artifact paths in the manuscript
example.

## HER computational hydrogen electrode example

Use this example only when the study evaluates HER or hydrogen adsorption with
the computational hydrogen electrode (CHE):

> Hydrogen adsorption free energies were evaluated within the computational
> hydrogen electrode framework. At equilibrium, the chemical potential of a
> proton-electron pair was referenced to one-half of the Gibbs free energy of
> gas-phase hydrogen. Accordingly, the hydrogen adsorption free energy was
> obtained from the free-energy difference between the hydrogen-covered and
> clean surfaces and the molecular-hydrogen reference.

Introduce the equilibrium relation first:

\[
\mathrm{H^+} + e^- \rightleftharpoons \frac{1}{2}\mathrm{H_2(g)}.
\]

At 0 V versus RHE, the corresponding chemical-potential relation is:

\[
\mu_{\mathrm{H^+}+e^-} = \frac{1}{2}G_{\mathrm{H_2}}.
\]

The hydrogen adsorption free energy is then:

\[
\Delta G_{\mathrm{H^*}}
 = G_{\mathrm{H^*}} - G_* - \frac{1}{2}G_{\mathrm{H_2}}.
\]

For calculations performed at a different potential, add the potential
correction only when it was included in the reported free energy. This is a HER
writing example only; do not add OH-, water autoionization, or unrelated
electrochemical derivations.

## Citation anchors

Canonical method citations are supplied separately to `select-citations`.
Typical conditional anchors are PBE, VASP, PAW, DFT-D3, Monkhorst-Pack, UMA,
and CHE. Include only references corresponding to methods actually stated in
the manuscript.
