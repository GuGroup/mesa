# Gibbs Thermochemistry Writing Example

Use this as a sentence-and-equation style reference for Supporting Information.
It follows the explanatory order of the supplied feedback while expressing the
method in terms of UMA energies and physical thermochemical contributions. The
calculation record remains authoritative. Keep only terms, temperature,
pressure, and phase treatments that were actually used.

## Manuscript example

Use the following as a manuscript-style example and replace the bracketed
conditions with the values used in the calculation:

> The Gibbs free energy of species *i* was calculated as

\[
G_i(T) = E_{\mathrm{UMA},i}
       + H_{\mathrm{trans},i}(T)
       + H_{\mathrm{rot},i}(T)
       + H_{\mathrm{vib},i}(T)
       - T\left[S_{\mathrm{trans},i}(T)
       + S_{\mathrm{rot},i}(T)
       + S_{\mathrm{vib},i}(T)\right],
\]

> where \(E_{\mathrm{UMA},i}\) is the energy of the relaxed structure of species
> *i* predicted by UMA, and \(T\) is the temperature. The terms
> \(H_{\mathrm{trans},i}(T)\), \(H_{\mathrm{rot},i}(T)\), and
> \(H_{\mathrm{vib},i}(T)\) denote the translational, rotational, and
> vibrational enthalpy contributions, respectively, whereas
> \(S_{\mathrm{trans},i}(T)\), \(S_{\mathrm{rot},i}(T)\), and
> \(S_{\mathrm{vib},i}(T)\) are the corresponding entropy contributions. The
> zero-point energy is included in \(H_{\mathrm{vib},i}(T)\). For gas-phase
> species, all translational, rotational, and vibrational contributions were
> included at [TEMPERATURE] K and [PRESSURE]. For adsorbates, only vibrational
> contributions were included because translational and rotational motion is
> constrained on the surface. For the clean slab, only
> \(E_{\mathrm{UMA}}\) was considered.

Replace the bracketed conditions from evidence. Omit a condition if it was not
recorded; never leave a bracketed token in public SI text. Do not include
software implementation details or internal workflow terminology in this
methodology paragraph.
