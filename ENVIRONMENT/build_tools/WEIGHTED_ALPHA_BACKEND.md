# Native weighted-alpha adsorption-site backend

## Status and scope

`backend="weighted_alpha"` is an explicit, strict geometry-site and contact-anchor placement backend for MESA Tool 4. The C++ source remains private and is not part of this repository or Python wheel. MESA obtains a source-free Windows runtime bundle from a hash-pinned private GitHub Release.

Phase 1 accepts only:

- `pbc=[True, True, False]`;
- a flat slab whose `a × b` surface normal is aligned with Cartesian `+z`;
- the engine construction mode `pbc_masked_image_aware`;
- graph JSON containing the additive P0/P1/P2 semantics documented below.

The v1 geometry gate rejects fully periodic bulk input, tilted slab cells, top-layer height spread above 0.25 Å, and stepped/incomplete upper terraces whose population differs from the complete underlying layer. It does not impose a separate minimum-vacuum-thickness cutoff. The legacy `backend="auto"` path remains unchanged and never invokes weighted-alpha.

## First-party source-free runtime

With no explicit executable/radius override, MESA reads the package resource:

```text
slabuilder/data/weighted_alpha_releases.json
```

The trusted index pins the release tag, platform, GitHub asset API URL, archive byte size, archive SHA-256, archive root, runtime-manifest SHA-256, executable SHA-256, radius-table SHA-256, and the private source-manifest aggregate SHA-256. The current platform is `windows-x86_64`.

Private GitHub download authentication uses `GH_TOKEN` or `GITHUB_TOKEN`; when neither is present, the resolver reads the token from an authenticated `gh` CLI and still uses the same bounded HTTPS path. The Authorization header is stripped before cross-origin signed-asset redirects. `MESA_WEIGHTED_ALPHA_CACHE` optionally selects the cache root. Otherwise Windows uses `%LOCALAPPDATA%/MESA/weighted-alpha` and other platforms use `~/.cache/mesa/weighted-alpha`.

Before an atomic versioned-cache install, the resolver verifies:

- platform support and trusted release-index schema;
- streaming download cap, then exact archive byte size and SHA-256;
- bounded member count and total uncompressed size;
- no absolute path, `..` traversal, backslash separator, drive/ADS colon path, or ZIP symlink;
- no C/C++ source, CMake, patch/diff, PDB, or map file;
- strict duplicate-free runtime-manifest JSON;
- exact runtime artifact set and every artifact SHA-256;
- executable/radius hashes and the contact-anchor CLI contract.

Every cache hit is reverified. Extra, missing, or modified files fail closed.

## Explicit audited override

An explicit `WeightedAlphaConfig` or complete environment override has priority over the first-party resolver:

```text
MESA_WEIGHTED_ALPHA_EXE
MESA_WEIGHTED_ALPHA_RADIUS_FILE
MESA_WEIGHTED_ALPHA_EXPECTED_SHA256
MESA_WEIGHTED_ALPHA_EXPECTED_RADIUS_SHA256
MESA_WEIGHTED_ALPHA_RUNTIME_SHA256_MANIFEST
MESA_WEIGHTED_ALPHA_EXPECTED_RUNTIME_MANIFEST_SHA256
MESA_WEIGHTED_ALPHA_ALLOW_UNPINNED_RUNTIME  default false; unsafe local-only opt-out
MESA_WEIGHTED_ALPHA_ALPHA_FACTOR           default 3.5
MESA_WEIGHTED_ALPHA_PROBE_RADIUS           compatibility name for contact-anchor radius; default 1.52 Å
MESA_WEIGHTED_ALPHA_PLACEMENT_GAP          default 0.5 Å
MESA_WEIGHTED_ALPHA_PLACEMENT_STEP         default 0.0125 Å
MESA_WEIGHTED_ALPHA_PLACEMENT_MAX_DISTANCE default 8.0 Å
MESA_WEIGHTED_ALPHA_TIMEOUT_S              default 120 s
```

Executable and radius overrides must be supplied together. Audited explicit execution requires all hashes. Adjacent DLLs must be listed exactly in the runtime manifest. The unsafe unpinned option is restricted to local development and is never staged as an audited bundle.

The Tool 4 CLIs use the first-party resolver when `--backend weighted_alpha` or `--site-backend weighted_alpha` is selected without binary paths. Numeric `--weighted-alpha-*` overrides can be used with the first-party runtime. Manual pins or unsafe mode require both explicit binary paths.

## Alpha factor and contact-anchor radius

The two physical controls are independent:

- `alpha_factor` / `--alpha-factor` controls weighted-alpha construction and classification.
- Python's compatibility field `probe_radius`, environment variable `MESA_WEIGHTED_ALPHA_PROBE_RADIUS`, and engine `-a` all mean the contact-anchor radius in Å. They are not the alpha factor and are not a generic physical probe-radius claim.

For a weighted-alpha site, MESA places binding atom index 0 at:

```text
anchor_position + normalize(direction) * precursor_radius
```

Here `anchor_position`, `direction`, and `precursor_radius` come from the validated engine placement record. Multi-atom adsorbates are rigidly rotated from their builder `+z` binding direction onto the engine normal and translated with binding atom 0 at that target. The target is wrapped through the slab's periodic x/y cell, preserving the same periodic image. A minimum-image post-placement collision check is mandatory.

The engine's farther ray-clearance `placement.position` remains diagnostic provenance; it is not substituted for the contact-anchor formula. Tool 4's legacy `height` option is ignored for weighted-alpha sites and remains unchanged for legacy backends.

## Strict execution contract

The backend stages a Cartesian POSCAR using MESA's `stable_element_group_order`, records both index-map directions, and maps graph atom IDs back to the original ASE order. Graph atom IDs are zero-based staged-POSCAR indices; `atoms_with_images` carries periodic-image identity. The staged POSCAR SHA-256 is passed to the engine and must be echoed exactly with matching atom count and cell.

On Windows the runner creates the engine suspended, attaches it to a kill-on-close Job Object, then resumes it. It uses an argument vector with `shell=False`, a private temporary workdir, a minimal child environment, bounded live stdout/stderr capture, a bounded graph, fresh-output checks, strict JSON, and complete SHA-256 pins. Timeout, live output overflow, and normal parent exit close the Job so descendants cannot escape. Missing configuration, artifact mismatch, timeout, nonzero exit, malformed graph, unsupported geometry, or an empty accepted candidate set raises a weighted-alpha exception. It never falls back to another backend.

## Required graph semantics

P0/P1/P2 nodes must add:

| Node | `site_kind` | `coordination` | `hollow_subtype` | `subsurface_ref_dist` |
| --- | --- | ---: | --- | --- |
| P0 | `top` | 1 | null | null |
| P1 | `bridge` | 2 | null | null |
| P2 | `hollow` | 3 | `fcc`, `hcp`, or `undefined` | finite Å value for fcc/hcp; null for undefined |

`coordination` is simplex/image coordination, not necessarily `len(atoms)`: periodic images may collapse to fewer unique physical atom IDs. A P1 made from two distinct periodic-image identities of one physical atom is a valid bridge candidate and preserves both image offsets in provenance. A P1 without image identities requires two physical source IDs. P2 requires exactly three distinct image identities and exact agreement between its physical `atoms` IDs and image atom IDs. Mismatched or `undefined` P2 evidence is ineligible. P3 is recognized but ignored as an adsorption candidate.

Graph edges are pinned to integer weight 1 and the directed contracts `contains` P3→P2/P1, `contains` P2→P1, and `endpoint` P1→P0. Unknown node types, duplicate IDs, dangling edges, invalid PBC/mode/input provenance, and nonfinite required values are schema errors. Topology-invalid or benchmark-blocking P2 nodes remain valid evidence but are filtered from candidates.

## Candidate and provenance policy

MESA infers top-open candidates from complete top-layer membership, regularity/topology flags, an outward normal, and a successful engine ray-clearance placement; this is not an independent Python vacuum-clearance proof. Accepted candidates must report `target_clearance_reached=true`, `status="target_clearance_reached"`, and `clearance_at_position >= precursor_radius + gap`. P1/P2 must be regular. P2 must be topology-valid, non-blocking, image/atom consistent, and classified `fcc` or `hcp`. These map to MESA `fcc_hollow`/`hcp_hollow`. Fourfold aggregation additionally requires P2 centers within 0.1 Å, constituent normals within 5 degrees, coplanar convex cyclic source geometry, a common circumcenter, and diagonal-center consistency; merged placement is resynthesized from the merged center and normal.

Each `AdsorptionSite` records `sources=["weighted_alpha"]`, `placement_method="weighted_alpha_contact_anchor"`, a non-cross-backend validation note, engine/graph/input hashes, command, node identity, source-index maps, semantic labels, normal, and placement diagnostics. Metadata survives site-map JSON, `source_site_json`, multi-adsorbate metadata, and both Tool 4 CLI outputs.

## Minimal usage

```python
from slabuilder.adsorption import identify_adsorption_sites

sites = identify_adsorption_sites(
    slab_atoms,
    "O",
    backend="weighted_alpha",
)
```

The first call downloads and verifies the trusted private runtime if it is not already cached. An explicit `WeightedAlphaConfig` remains available for audited local overrides.

## Verification gates

Before merge or runtime promotion:

1. build and test the private C++ exporter;
2. run backend, resolver, dispatch, placement, site-map, packet, and CLI tests;
3. run the complete Tool 4 suite and compare legacy `auto` output;
4. manually dispatch the private-runtime workflow on the reviewed PR head before merge, then download the private release into a clean cache and run the real YTK slab;
5. verify graph counts/hashes, finite geometry, source indices, contact-anchor placement, collision checks, cleanup, and repeated determinism;
6. build/install the wheel and prove the trusted release index is packaged;
7. complete independent security, scientific-geometry, and compatibility reviews.