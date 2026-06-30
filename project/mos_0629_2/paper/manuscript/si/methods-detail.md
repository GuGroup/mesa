# Supplementary Methods Detail

**Structure and endpoint scope** | The workflow used compact MoS2(100) S-edge proxies, isolated Ni edge or near-edge motifs, and broader Ni/interface or phase-like proxy structures. S1 and S1R used the compact pristine and Ni-modified edge proxies. S2 tested isolated Ni motifs. S6 tested interface-like and phase-like proxies. S6R repaired the S6 Ni2 interface with standalone H* and OH* endpoints and an H-removal thermodynamic proxy.

**Adsorbate placement and product construction** | AdsorbDiff was used for H~2~O placement. Coadsorbed H*+OH* product endpoints and S6R standalone H*/OH* endpoints were constructed from accepted relaxed reactants or products using project-local scripts, then relaxed with UMA.

**Endpoint acceptance** | Relaxed endpoints were evaluated using convergence status, final maximum force, analyzer verdicts, and geometry checks. Dissociated H*+OH* endpoints required one retained O-H bond, one broken transferred O-H bond, and one surface-H contact. Endpoints with failed force convergence or recombined water-like final states were excluded from primary product evidence.

**Energy definitions** | Hydrogen adsorption used $\Delta G_H \approx \Delta E_H + 0.24$ eV. H~2~O adsorption used the endpoint energy relative to the clean slab and gas-phase H~2~O. Product gaps used relaxed H*+OH* product energy minus H~2~O* reactant energy. S6R OH retention used OH* relative to H~2~O - 1/2 H~2~. S6R H removal used OH* + 1/2 H~2~ minus H*+OH*.

**VASP prepare-only rule** | VASP-compatible inputs were prepared for S1, S1R, S2, S6, and S6R using `vasp-job prepare`. No VASP jobs were submitted. Non-POTCAR files were mirrored under the project tree; POTCAR files were not copied into the project copy.
