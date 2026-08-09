---
name: delegate-literature-workflow
description: Delegate MESA literature preparation to one fresh, bounded sub-agent while keeping the parent context small. Use when starting from an experimental-data PDF through claim extraction and paper-search handoff, or when resuming after the user manually downloads recommended papers for local extraction.
---

# Delegate Literature Workflow

## Purpose

Keep literature-heavy PDF and search context outside the parent thread. Run one
fresh sub-agent for one bounded phase, persist the result as project artifacts,
and return only a compact handoff to the parent.

## Parent Contract

1. Read the root and literature workflows.
2. Resolve the active project and existing literature artifacts.
3. Select exactly one phase from the artifact rules below.
4. Spawn exactly one fresh sub-agent. Use no inherited conversation context
   when the environment supports that option.
5. Give the sub-agent only the phase, project path, required input paths, and
   optional neutral search filter.
6. Wait for its terminal response, then validate the returned artifact paths
   without loading detailed paper content into the parent context.

Do not perform the delegated literature work in the parent. If sub-agents are
unavailable, report the boundary instead of silently falling back. Keep all
user interaction, including the manual-download pause, in the parent.

## Phase Selection

- If an experimental-data PDF exists but the search handoff does not, run
  `phase_1`.
- If the manual-download queue exists, stop until the user confirms that
  selected PDFs have been placed in its queued folders; then run `phase_2`.
- If every downloaded PDF has a corresponding extraction artifact, do not
  repeat literature delegation unless the user asks.
- If required artifacts are missing, report the exact missing paths and request
  only the input needed to resume.

Never keep a sub-agent alive while waiting for user action. Start a fresh
sub-agent for `phase_2`.

## Sub-Agent Boundary

Include these instructions in every delegated task:

- Read `workflow.md`, `SKILL/literature/workflow.md`, and each selected worker
  skill completely.
- Do not spawn another sub-agent.
- Use only the literature skills required by the assigned phase.
- Write only under the active project's literature directory, except for the
  required append-only `skill_call_log.md` entries.
- Do not modify repository source, project profiles, or prior artifacts outside
  the assigned literature paths.
- Write all project artifacts in English.
- Do not generate strategies, write manuscripts, or run calculations.
- Stop at the phase boundary and return only the compact handoff.

## Phase 1: Extract and Search

Provide the experimental-data PDF and, only when necessary, a neutral
material-domain or reaction filter.

The sub-agent must:

1. Use `extract-data-from-experiment` on the supplied PDF.
2. Save the extraction under
   `project/<project_name>/literature/experimental/`.
3. Use `search-papers-with-mcp` from the exact extracted
   `author_reported_claim`.
4. Preserve that skill's search artifacts and manual-download queue under
   `project/<project_name>/literature/search/`.
5. Return the exact extraction, search-result, and manual-queue paths.
6. Stop before downloading or extracting recommended papers.

## Phase 2: Extract Downloaded Papers

Provide the search handoff and the downloaded-paper folders created from its
manual queue.

The sub-agent must:

1. Treat only local PDFs as available evidence.
2. Use `extract-strategy-paper` for PDFs in the strategy-paper folder.
3. Use `extract-general-insights-paper` for PDFs in domain or legacy folders.
4. Save one extraction per PDF under
   `project/<project_name>/literature/extractions/<section>/`.
5. Return each PDF path, selected skill, extraction path, and failed or missing
   item.
6. Stop before strategy generation.

Do not create a separate workflow-state or index artifact solely for
delegation. Existing literature artifacts are the durable checkpoint.

## Compact Handoff

Require the sub-agent's terminal response to contain only:

```text
status: <awaiting_manual_download | complete | blocked>
artifacts: <exact output paths>
user_action: <one sentence or none>
boundary: <confirmed stopping point>
```

The parent must report these fields to the user and avoid reproducing the
sub-agent's detailed literature analysis.
