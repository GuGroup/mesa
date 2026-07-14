# SKILL SUBTREE KNOWLEDGE

## OVERVIEW

`SKILL/` contains discoverable Codex skill bundles plus domain routing manuals.
A leaf `SKILL.md` is an operator contract, not package documentation. Domain
manuals own stage entry, handoff, evidence, and project-layout rules; leaf files
add only task-specific instructions.

## WHERE TO LOOK

| Need | Location |
|---|---|
| Stage routing and exact active catalog | `<domain>/workflow.md` |
| Trigger, inputs, procedure, outputs, limits | `<domain>/<skill>/SKILL.md` |
| UI chip and invocation metadata | `<skill>/agents/openai.yaml` |
| Deterministic or repeated operations | `<skill>/scripts/` |
| Schemas, policies, theory, API detail | `<skill>/references/` |
| Always-load or variant-selected fragments | `<skill>/static/`, `manifest.yaml` |
| Reused by two or more skills | `_shared/` |
| Decision/execution split | `<skill>/MYSKILL/`, `<skill>/EXTSKILL/` |
| Archived implementations only | `legacy/` |

## CONVENTIONS

- Active directory and frontmatter `name` match exactly: lowercase kebab-case,
  verb-led, under 64 characters. Frontmatter contains only `name` and
  `description`.
- Make `description` discovery-complete: action, concrete inputs/outputs,
  invocation context, and routing-sensitive exclusions. Do not hide triggers in
  the body.
- Start each domain leaf with its domain-manual preflight. A leaf may narrow a
  parent rule; it may not relax stage gates, provenance, or claim boundaries.
- Keep bodies imperative and compact: scope, required inputs, command/workflow,
  output contract, validation, boundaries. Move long schemas and examples to
  directly linked references.
- Write runnable commands from an explicitly stated working directory. Prefer
  repository-root paths; never encode an author's home directory.
- `agents/openai.yaml` uses quoted strings. `default_prompt` is one sentence and
  explicitly says `Use $<skill-name> ...`; `short_description` is 25-64 chars.
  Declare MCP dependencies only when the leaf actually requires them.
- Add/rename/remove atomically: leaf folder, domain catalog, root active catalog,
  `agents/openai.yaml`, `DEPENDENCY/runtimes.yaml`, cross-skill handoffs, and
  command examples must agree before merge.
- Put stable CLIs in `scripts/`; expose explicit paths/flags, structured outputs,
  non-zero failure, and a representative smoke test. Do not restate script logic
  in prose.
- Keep references one hop from `SKILL.md`; say exactly when each is read.
  Skill-only material stays local; `_shared/` requires two real consumers.
- Use `MYSKILL/EXTSKILL` only for a real controller-runner boundary. Controller
  owns choices and writes resolved config; runner executes it without new
  scientific decisions. Helper protocol files are not named `SKILL.md`.
- Validate every changed leaf with:
  `uv run --with pyyaml "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" SKILL/<domain>/<skill>`.
  Also smoke the documented entry point and inspect `agents/openai.yaml` drift.
- Before adding fixtures, tests, or assets, run `git check-ignore -v <path>`;
  current broad rules ignore `SKILL/**/tests/` and `SKILL/**/assets/`.

## ANTI-PATTERNS

- No current routing through `TASK_*`, `legacy/`, old directory names, or stale
  task IDs in prompts, examples, manifests, and public output fields.
- No skill-level README, quick-reference, or duplicate schema when `SKILL.md` or
  `references/` already owns the content.
- No orphan reference: an unlinked file is invisible at invocation time.
- No ambiguous `python scripts/...`, `/home/...`, or maintainer-local validator
  path in runnable examples.
- No empty `EXTSKILL`/"no external tools" placeholder. Omit the layer when no
  external execution boundary exists.
- No untracked validation evidence. Do not rely on ignored tests/assets without
  deliberately fixing tracking for the intended files.
- No generated `__pycache__`, `.pyc`, `Zone.Identifier`, run output, secret, or
  author-local path in a skill bundle.
