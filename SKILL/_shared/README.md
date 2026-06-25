# `_shared/` - shared content for retained nature skills

This directory is not an independent skill. It has no `SKILL.md` and is not registered by the plugin loader.

The retained nature skills use it for shared material that should not be duplicated across skill folders.

## Current Contents

| File | Used By |
|---|---|
| `core/reader-workflow.md` | `nature-polishing`, `nature-writing` |
| `core/paper-type-taxonomy.md` | `nature-polishing`, `nature-writing` |
| `core/ethics.md` | `nature-polishing`, `nature-writing` |
| `core/terminology-ledger.md` | `nature-polishing`, `nature-writing` |
| `journal-formats/nat-comms.md` | `nature-polishing`, `nature-writing` |

## When Content Belongs Here

Put content here only when two or more retained skills reuse the same material. Content that serves only one skill should stay in that skill's own `static/` or `references/` directory.

## Boundary

The shared layer stores definitions and reference material, such as paper-type taxonomy, reader workflow, ethics rules, and terminology ledgers. Skill-specific diagnosis, drafting, revision, and output logic stays inside each skill.
