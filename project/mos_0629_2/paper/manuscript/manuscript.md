# Ni-modified MoS2 improves hydrogen descriptors but does not pass alkaline HER endpoint tests in present calculations

## Abstract

Ni doping is often invoked as a route to improve alkaline hydrogen evolution on MoS2, but a useful computational test must go beyond the near-thermoneutral H* descriptor and include water activation, OH handling, and H~2~ formation. Here we evaluate this claim on compact MoS2 edge models and Ni-containing edge/interface proxies using AdsorbDiff placement, UMA relaxations, endpoint thermodynamics, and calculation-result-analyzer gates, with VASP-compatible inputs prepared but not submitted. A compact Ni-modified S-edge proxy improves the simple descriptor picture, shifting estimated $\Delta G_H$ from +0.557 eV on pristine MoS2 to +0.050 eV and strengthening H~2~O adsorption from -1.040 to -1.385 eV. This descriptor benefit does not persist when alkaline Volmer products are enforced: the lowest accepted compact-Ni H*+OH* product lies +0.594 eV above H~2~O*, compared with +0.090 eV for pristine MoS2. Broader isolated Ni motifs are also unfavorable, with the best Ni-sub-S44 product at +0.917 eV. A Ni2 edge-cluster/interface partly rescues the Ni-containing mechanism by giving direct Ni-bound H~2~O and a lower H*+OH* product gap of +0.292 eV, and S6R further shows favorable H removal to OH* + 1/2 H~2~ (-0.182 eV). However, the same Ni2 interface remains +0.202 eV worse than pristine for H~2~O* to H*+OH* formation and binds OH* strongly. These present calculations therefore support a bounded negative conclusion: Ni-containing MoS2 models can improve selected descriptors and identify a plausible Ni2 interface, but the current evidence does not demonstrate enhanced alkaline HER activity over pristine MoS2.

## Introduction

Alkaline hydrogen evolution on MoS2 depends on more than hydrogen adsorption. A catalyst that binds H* near thermoneutrality can still fail if water dissociation is unfavorable, if OH* blocks the active site, or if H~2~ formation is not competitive after water-derived intermediates form. This distinction is especially important for doped MoS2, where a metal dopant may improve one descriptor while worsening another step in the alkaline reaction sequence.

Ni modification provides a useful stress test for this problem. A compact Ni-substituted or Ni-decorated edge site can shift H* binding toward the ideal HER value and can increase water affinity, but those two changes do not by themselves establish improved alkaline HER activity. The relevant computational question is whether a Ni-containing MoS2 model can remain competitive with pristine MoS2 after explicit H~2~O*, H*+OH*, OH*, and H-removal endpoints are considered under a consistent screening protocol.

We therefore treated the Ni-doped MoS2 claim as a sequence of increasingly strict computational tests. First, we compared pristine and compact Ni-modified S-edge proxies by H* and H~2~O adsorption descriptors. Second, we repaired that descriptor-level test with explicit dissociated H*+OH* products. Third, we screened isolated Ni edge and near-edge motifs. Finally, we tested broader interface-like and phase-perturbed proxies, then repaired the most promising Ni2 interface with standalone H* and OH* endpoints plus an H-removal thermodynamic proxy.

The present manuscript reports the outcome of that completed sequence, not an additional strategy cycle. The strongest result is not a proof of enhanced Ni-doped MoS2 activity. Instead, the calculations show that the simple Ni descriptor advantage is fragile: a Ni2 edge-cluster/interface is the best Ni-containing model identified, but it still does not outperform pristine MoS2 for the key H~2~O* to H*+OH* product benchmark and may suffer from strong OH retention.

## Results

**Compact Ni modification improves the simplest HER descriptors**

The first calculation set tested whether a compact Ni-modified MoS2(100) S-edge proxy improves the conventional endpoint descriptors relative to pristine MoS2. It does. The estimated hydrogen adsorption free energy changes from +0.557 eV on pristine MoS2 to +0.050 eV on the Ni-modified S-edge proxy, moving the descriptor close to the thermoneutral HER target. The same model strengthens water adsorption from -1.040 eV to -1.385 eV. These results support the qualified descriptor claim that Ni modification can improve H binding and water affinity on the compact edge proxy.

This first result is deliberately limited. The accepted S1 endpoint set contains clean slabs, H* and H~2~O* endpoints, and H~2~/H~2~O gas references, but the OH evidence was not accepted as primary support. One pristine OH endpoint carried a possible-dissociation warning, and two Ni-OH endpoint attempts did not converge within the controller-owned UMA relaxation settings. The S1 result therefore supports a descriptor-level claim only.

**Explicit H~2~O* dissociation reverses the compact-Ni descriptor advantage**

S1R tested whether the compact Ni descriptor advantage survives a stricter alkaline Volmer endpoint comparison. It does not. Accepted dissociated H*+OH* products were required to retain one O-H bond, break the transferred O-H bond, and form a surface-H bond after relaxation. Under that gate, the accepted pristine product lies +0.090 eV above H~2~O*, whereas the lowest accepted compact-Ni product lies +0.594 eV above H~2~O*. The compact Ni product is therefore +0.504 eV less favorable than the pristine product.

A frozen O-H transfer scan gives the same qualitative ordering. The pristine scan maximum is 2.080 eV above H~2~O*, while the compact Ni scan maximum is 3.315 eV. This scan is a barrier proxy rather than a CI-NEB transition state, so it is not used as a kinetic proof. It nevertheless reinforces the endpoint result: the compact Ni proxy does not lower the alkaline water-dissociation step despite its favorable H-binding descriptor.

**Isolated Ni edge motifs do not rescue the alkaline endpoint thermodynamics**

S2 asked whether the compact site was simply the wrong isolated Ni motif. Four isolated edge or near-edge Ni motifs were screened. Only the Ni-sub-S44 motif retained a direct Ni-bound molecular H~2~O state after relaxation, with $\Delta E_{\mathrm{H2O,ads}} = -0.862$ eV. The resulting H*+OH* product comparison was unfavorable: the best accepted Ni-sub-S44 product is +0.917 eV above H~2~O*. This is worse than both the pristine benchmark (+0.090 eV) and the compact Ni product (+0.594 eV).

The S2 result rules out the tested isolated Ni motifs as a sufficient explanation for enhanced alkaline HER within this model family. It does not rule out all Ni effects. Instead, it redirects the mechanistic question toward interface-like motifs, phase perturbations, electrolyte effects, or coverage-dependent OH handling.

**A Ni2 edge-cluster/interface is the best Ni-containing model, but it remains worse than pristine**

S6 broadened the search to interface-like and phase-like proxies. The Ni2 edge-cluster/interface was the only tested S6 proxy that produced a clean direct Ni-bound molecular H~2~O endpoint after relaxation. Its water adsorption energy is -1.073 eV, close to the pristine value (-1.040 eV), and the final O-Ni distance is 2.03 A. This makes the Ni2 interface the first Ni-containing model in the workflow with a clean direct water endpoint and improved product thermodynamics relative to earlier Ni motifs.

Four Ni2-interface H*+OH* products were then relaxed. The best product is +0.292 eV above the Ni2 H~2~O* reactant. This is a substantial improvement over compact Ni (+0.594 eV) and isolated Ni-sub-S44 (+0.917 eV), but it still does not beat pristine MoS2 (+0.090 eV). Thus, S6 partially rescues the Ni-containing mechanism by identifying a better active-site class, but it does not prove enhanced alkaline HER relative to pristine MoS2.

**S6R repairs missing H/OH endpoints but leaves OH retention as a blocking feature**

S6R refined the Ni2 interface by adding standalone H* and OH* endpoints and a thermodynamic H-removal proxy. The best standalone H endpoint is H on the Ni2 interface site relaxed as S6R_Ni2_H_on_Ni46, with estimated $\Delta G_H = -0.132$ eV. This is closer to thermoneutral than the alternative H-on-Ni45 endpoint (-0.520 eV), but both H endpoints carry topology warnings and therefore remain qualified evidence.

The S6R OH endpoint passed the analyzer gate and is strongly retained, with $\Delta E_{\mathrm{OH}} = -0.963$ eV versus H~2~O - 1/2 H~2~. From the best S6 H*+OH* product, removing H* as 1/2 H~2~ to form OH* is exergonic by -0.182 eV. This repairs one missing piece of the Ni2 mechanism: H removal from the coadsorbed product is not thermodynamically blocked. However, it also highlights a likely failure mode. The Ni2 interface may retain OH* too strongly, and the key H~2~O* to H*+OH* product remains +0.202 eV less favorable than pristine.

**Present result**

Across the completed strategy sequence, Ni doping improves selected descriptors but does not meet the full alkaline HER benchmark used here. The present evidence supports three bounded conclusions: compact Ni modification improves H* and H~2~O descriptors; isolated Ni motifs do not improve the alkaline Volmer product energetics; and a Ni2 edge-cluster/interface is the most plausible Ni-containing model tested but still remains worse than pristine for H~2~O* dissociation and may be limited by OH retention.

## Discussion

**Descriptor improvement is not equivalent to alkaline HER enhancement**

The compact Ni proxy illustrates the central risk in H-only screening. Its estimated $\Delta G_H$ is close to thermoneutral, and its water adsorption is stronger than pristine MoS2. If the analysis stopped there, the model would appear to support enhanced alkaline HER. The S1R repair changes that interpretation: the same compact Ni proxy gives a less favorable H~2~O* to H*+OH* product than pristine. The present evidence therefore separates descriptor improvement from mechanism-level enhancement.

**The active Ni motif matters more than the presence of Ni alone**

The S2 and S6 results show that Ni activity cannot be inferred from dopant identity alone. Tested isolated Ni motifs were not favorable, with the best isolated motif substantially worse than the compact Ni and pristine benchmarks. By contrast, the Ni2 edge-cluster/interface produced direct Ni-bound water and better H*+OH* product thermodynamics than earlier Ni motifs. This suggests that if Ni-doped MoS2 is active under alkaline conditions, the relevant site is more likely to involve an interface-like local environment than a single isolated Ni substitution in the tested edge models.

**The Ni2 interface remains mechanistically incomplete**

The Ni2 interface is the best Ni-containing candidate in this workflow, but the current evidence does not justify an enhanced-activity claim. Its best H~2~O* to H*+OH* product remains +0.292 eV above H~2~O*, while the pristine product is +0.090 eV. S6R adds a favorable H-removal proxy, which means H* formation is not necessarily a terminal trap. At the same time, the accepted OH* endpoint is strongly stabilized. This combination suggests a plausible bifunctional site with a possible OH-retention penalty rather than a proven high-activity alkaline HER center.

**Boundaries of the present manuscript**

Several limitations are intrinsic to the present result. UMA endpoints are treated as VASP-accurate by project instruction, but VASP jobs were not submitted. Endpoint thermodynamics and frozen scans are not CI-NEB barriers. The Ni2 edge-cluster/interface is a computational proxy rather than an experimentally assigned structure. The pristine OH endpoint remains exploratory because of analyzer topology warnings. These boundaries do not invalidate the negative conclusion; they define its scope. Within the completed workflow, the data are sufficient to reject a simple proof of Ni-enhanced alkaline HER, but not sufficient to rule out all electrolyte-, coverage-, potential-, or interface-mediated Ni effects.

**Implication**

The present manuscript should be read as a computational falsification of an over-simple Ni-doping claim. Ni can improve H-binding and water-affinity descriptors, and a Ni2 interface can improve over isolated Ni motifs. However, a complete alkaline HER argument must survive water activation, OH retention, and H~2~-release checks against pristine controls. The current Ni-containing models do not pass that standard.

## Methods

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

## Conclusion

The present calculations do not prove that Ni doping enhances alkaline HER activity on MoS2 relative to pristine MoS2. They show instead that Ni modification can improve the simple H-binding and water-affinity descriptor picture, but this improvement is not sufficient when alkaline HER endpoint chemistry is included.

The strongest Ni-containing model identified here is a Ni2 edge-cluster/interface. It gives direct Ni-bound H~2~O, improves H*+OH* product thermodynamics relative to compact and isolated Ni motifs, and has a favorable thermodynamic H-removal proxy. Even so, it remains worse than pristine MoS2 for H~2~O* to H*+OH* formation and strongly retains OH*. The current evidence therefore supports a bounded conclusion: Ni-containing MoS2 may require interface, coverage, solvation, or potential effects beyond the present endpoint models, but the present calculations should not be written as a positive demonstration of enhanced alkaline HER.
