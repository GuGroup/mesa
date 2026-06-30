# Result Inventory

## S1 Primary Accepted Artifacts

S1 evaluates a compact MoS2(100) S-edge proxy and a Ni-modified S-edge proxy with UMA endpoint relaxations. Accepted endpoints are convergence-checked and used only for descriptor-level comparisons.

| Label | Energy (eV) | Final Fmax (eV/A) | Analyzer verdict | Role |
|---|---:|---:|---|---|
| pristine_clean | -305.961907 | 0.0478 | pass | descriptor endpoint |
| ni_clean | -310.610009 | 0.0484 | warn | descriptor endpoint |
| pristine_H | -308.967122 | 0.0465 | warn | descriptor endpoint |
| ni_H | -314.122154 | 0.0432 | pass | descriptor endpoint |
| pristine_H2O | -320.927802 | 0.0496 | pass | descriptor endpoint |
| ni_H2O | -325.920531 | 0.0406 | pass | descriptor endpoint |
| gas_H2 | -6.644459 | 0.0196 | not_applicable | gas reference |
| gas_H2O | -13.925807 | 0.0441 | not_applicable | gas reference |

## Exploratory Or Excluded Artifacts

| Label | Status | Reason |
|---|---|---|
| pristine_OH_warn | warn | 1 bond(s) broke vs initial (possible dissociation) |
| ni_OH_excluded_0004 | fail | final fmax 0.110 > 0.050 eV/Å (cli --fmax-threshold) — not converged |
| ni_OH_excluded_0005 | fail | final fmax 0.103 > 0.050 eV/Å (cli --fmax-threshold) — not converged |

## Method Notes

- UMA endpoint relaxations are treated as VASP-accurate for this test, per project instruction.
- VASP input files were prepared but not submitted.
- Visual analyzer PNG validation was unavailable due host Playwright/GLIBC incompatibility; numeric analyzer outputs were used.

## S1R Repair Artifacts

S1R repaired the missing H*+OH* product endpoint evidence for the compact MoS2 S-edge proxy. Accepted dissociated products were required to keep one O-H bond, break the transferred O-H bond, and form a surface-H bond after UMA relaxation.

| Surface | Product DeltaE vs H2O* (eV) | Frozen scan max vs H2O* (eV) | Status |
|---|---:|---:|---|
| pristine | 0.090 | 2.080 | accepted dissociated product |
| Ni_sedge | 0.594 | 3.315 | accepted dissociated product |

The compact-proxy S1R repair is a negative result for the original Volmer-barrier hypothesis: the lowest accepted dissociated Ni product is less favorable than the pristine product by 0.504 eV, and the frozen scan proxy is higher on Ni by 1.234 eV.

## S2 Active-Site Ensemble Artifacts

S2 tested isolated Ni edge and near-edge motifs. Only the Ni-sub-S44 motif retained a direct Ni-bound molecular H2O endpoint, but its accepted H*+OH* product remained +0.917 eV above H2O*, worse than both pristine and compact Ni benchmarks. S2 is therefore negative evidence for isolated Ni motifs, not for all Ni-containing MoS2 configurations.

| Artifact | Status | Role |
|---|---|---|
| s2_h2o_relaxation_summary.json | primary | H2O endpoint gate for four isolated Ni motifs |
| s2_s44_product_summary.json | primary | H*+OH* product endpoint test for the only direct Ni-bound H2O motif |
| s2_vasp_prepare_manifest.json | supporting | prepare-only VASP input record; no submission |

## S6 Interface/Phase Proxy Artifacts

S6 tested broader Ni/interface and phase-like proxies. The Ni2 edge cluster/interface was the first Ni-containing model with clean direct Ni-bound molecular H2O and a materially improved H*+OH* product relative to previous Ni motifs, but the best product remained +0.292 eV above H2O*, worse than the pristine +0.090 eV benchmark.

| Artifact | Status | Role |
|---|---|---|
| s6_clean_gate_summary.json | primary | clean proxy convergence and analyzer gate |
| s6_h2o_relaxation_summary.json | primary | H2O endpoint gate for accepted S6 proxies |
| s6_ni2_product_summary.json | primary | Ni2 H*+OH* product endpoint comparison |
| s6_vasp_prepare_manifest.json | supporting | prepare-only VASP input record; no submission |

## S6R Repaired Ni2 Interface Artifacts

S6R added standalone H*, OH*, and H-removal endpoint checks for the S6 Ni2 interface. The repaired endpoint set gives favorable H removal from H*+OH* to OH* + 1/2 H2 (-0.182 eV) and a best Ni2 DeltaG_H_est of -0.132 eV, but it does not reverse the key benchmark: Ni2 H2O* -> H*+OH* remains +0.202 eV less favorable than pristine. The S6R decision is therefore qualified negative for the full enhanced alkaline HER claim.

| Artifact | Status | Role |
|---|---|---|
| s6r_descriptor_summary.json | primary | integrated S6R H binding, OH retention, H2-release proxy, and product-gap decision |
| s6r_h_binding.csv | supporting | standalone H* endpoint details |
| s6r_oh_retention.csv | supporting | standalone OH* endpoint details |
| s6r_h2_release_proxy.csv | supporting | H-removal thermodynamic proxy |
| s6r_product_gaps.csv | supporting | H2O* -> H*+OH* product benchmark table |
| s6r_vasp_prepare_manifest.json | supporting | prepare-only VASP input record; no submission |
