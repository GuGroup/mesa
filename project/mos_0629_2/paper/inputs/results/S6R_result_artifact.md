---
claim_ids: [C3, C7]
strategy_id: S6R
artifact_type: bounded_result
---
# S6R Result Artifact: Repaired Ni2 Interface H/OH and H2-Release Endpoints

## Scope

S6R repaired the S6 Ni2 edge-cluster/interface test by adding standalone H* and OH* endpoints and a thermodynamic H-removal proxy for H2 evolution. The goal was to check whether the Ni2 interface result becomes a complete alkaline HER enhancement argument once missing OH handling and H2-release terms are included. UMA relaxations and analyzer gates were used; VASP-compatible inputs were prepared for the new S6R endpoints but not submitted.

## Endpoint Results

Three new endpoints were relaxed: H* on Ni45, H* on Ni46, and OH* derived from the best S6 H*+OH* product after removing the separated H*. The OH* endpoint passed analyzer checks with final fmax = 0.044 eV/A. Both H* endpoints converged but retained analyzer topology warnings, so they are usable as qualified endpoint evidence rather than clean structural proof.

The best S6R H-binding endpoint is `S6R_Ni2_H_on_Ni46_gpu`, with estimated DeltaG_H = -0.132 eV. This is much closer to thermoneutral than the H-on-Ni45 endpoint (-0.520 eV), but still stronger than ideal and less compelling than the original compact Ni descriptor-only result.

## OH and H2-Release Check

The accepted S6R OH* endpoint gives DeltaE_OH versus H2O - 1/2 H2 of -0.963 eV, indicating strong OH retention on the Ni2 interface. From the best S6 H*+OH* product, removing H* as 1/2 H2 to the S6R OH* endpoint is exergonic by -0.182 eV. This repairs one missing part of S6: the Ni2 product is not obviously trapped by H* once OH* is retained.

## Comparison Against Pristine and Earlier Ni Motifs

The best S6 Ni2 H2O* -> H*+OH* product remains +0.292 eV above H2O*. This is better than previous Ni-containing benchmarks, including compact Ni (+0.594 eV) and isolated S44-substitution Ni (+0.917 eV), but it is still worse than the pristine benchmark (+0.090 eV). Thus, the Ni2 interface is the best Ni-containing model tested so far, but it does not yet demonstrate enhanced alkaline HER relative to pristine MoS2.

## Decision

S6R does not prove that Ni doping enhances alkaline HER activity. It strengthens the mechanistic picture for a Ni2 interface by showing improved Ni-product thermodynamics versus earlier Ni motifs and favorable H-removal to OH* + 1/2 H2, but the key H2O* -> H*+OH* product remains 0.202 eV less favorable than pristine and the OH* endpoint suggests possible OH poisoning. The next strategy should continue with broader alkaline descriptors such as coverage, solvation, potential, and OH removal rather than narrowing to H-only binding.
