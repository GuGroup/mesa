# Claim Matrix Schema

`paper/logic/claim-matrix.yaml` is the gatekeeper for scientific statements. A
claim may appear in prose only if it is supported, qualified, or explicitly
allowed by its section contract.

## Top-Level Shape

```yaml
version: 1
target: nature-family
claims:
  - id: C1
    level: main
    statement: "Plain-language claim."
    status: supported
    evidence:
      - id: E1
        source_id: result-co-pt111-energy
        path: paper/inputs/results/co_pt111_energy.yaml
        relation: direct
        summary: "What this file supports."
    figures: [F1]
    assumptions: []
    caveats: []
    risks: []
    allowed_sections: [results, discussion, abstract]
```

## Required Claim Fields

- `id`: stable ID such as `C1`, `C1.1`, or `M1`.
- `level`: `main`, `supporting`, `method`, or `context`.
- `statement`: exact claim text to be controlled.
- `status`: `supported`, `qualified`, `blocked`, `excluded`, or `draft`.
- `evidence`: list of direct evidence records. Main claims require at least one
  direct evidence record unless status is `blocked` or `excluded`.
- `figures`: figure IDs from `paper/logic/figure-map.yaml`, or an empty list
  for text-only support.
- `assumptions`: explicit assumptions that constrain the claim.
- `caveats`: limitations that must travel with the claim.
- `risks`: linked issue IDs or short known risks.
- `allowed_sections`: sections allowed to use the claim.

## Evidence Records

Evidence records must include `id`, `source_id`, `path`, `relation`, and
`summary`. `relation` is one of `direct`, `derived`, `context`, or `negative`.
Evidence paths must point to files under `paper/inputs/`, `paper/figures/`, or
`paper/logic/`.

## Gate Rules

- A main claim with no direct evidence is blocked.
- An unsupported claim must be downgraded, excluded, or marked blocked.
- Caveats must be carried into sections that use qualified claims.
- A claim cannot be introduced in prose unless it is already present here.
- Citation records are not required in v1; literature automation is excluded.
