---
claim_ids: [C3]
---
**Computational scope**

All calculations were performed as a workflow-level computational test of Ni-doped MoS2 alkaline HER models. The protocol used compact MoS2(100) S-edge proxies, isolated Ni edge and near-edge motifs, and broader Ni/interface or phase-like proxy structures. UMA relaxations were treated as VASP-accurate for this test, following the project instruction. VASP-compatible inputs were prepared for accepted calculation sets but no VASP jobs were submitted.

**Structure generation and adsorbate placement**

The pristine MoS2 edge model was used as the starting point for compact Ni modification, isolated Ni motifs, and interface-like Ni proxy structures. AdsorbDiff was used for H~2~O placement where adsorbate placement was required. Custom endpoint builders were used for coadsorbed H*+OH* products and for the S6R H* and OH* repair endpoints, because those states were derived from accepted H~2~O* or H*+OH* products rather than from a single molecular placement task.

**Endpoint relaxation and analyzer gates**

UMA relaxations were run for clean slabs, adsorbate endpoints, gas references, and repaired product endpoints. Endpoint acceptance used convergence status, final maximum force, analyzer verdicts, and explicit bond-distance checks where coadsorbed product identity mattered. For H*+OH* products, accepted geometries had to retain one O-H bond, break the transferred O-H bond, and form a surface-H bond. Analyzer warnings were retained in the evidence tables and carried into the claim caveats rather than discarded.

**Energy descriptors**

Hydrogen adsorption was evaluated using $\Delta G_H \approx \Delta E_H + 0.24$ eV. Water adsorption was evaluated as endpoint adsorption energy relative to the corresponding clean slab and gas-phase H~2~O. H~2~O* to H*+OH* product gaps were computed as the relaxed product energy minus the accepted H~2~O* reactant energy. OH retention in S6R was evaluated relative to H~2~O - 1/2 H~2~. The S6R H-removal proxy was computed as the energy change from the Ni2 H*+OH* product to OH* + 1/2 H~2~.

**VASP input preparation**

VASP-compatible inputs were prepared with `vasp-job prepare` for S1, S1R, S2, S6, and S6R endpoint sets. The prepare manifests are stored under `paper/inputs/results/`. Non-POTCAR prepared files were mirrored under the project tree, and POTCAR files were intentionally not copied into the project copy. No `vasp-job submit` command was run.
