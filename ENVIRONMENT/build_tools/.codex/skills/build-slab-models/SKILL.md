---
name: build-slab-models
description: Legacy vendored slab-building skill copy. Direct Materials Project/formula slab generation is disabled; use the active SKILL/modeling/build-slab-models skill with an optimized --bulk-file handoff instead.
---

# Legacy Build Slab Models Copy

Do not use this vendored `.codex` copy for new MESA workflows. The active skill
is `SKILL/modeling/build-slab-models`.

Direct Materials Project or formula-based slab generation is disabled. Import,
register, or directly create the source bulk first with
`import-bulk-structure`, optimize the bulk under the root calculation policy,
then run the active build-slab skill with the optimized bulk artifact passed as
`--bulk-file`.
