# Literature Domain Workflow

Use this manual when collecting or extracting source evidence before strategy
generation, strategy update, or manuscript citation work.

Literature work provides constraints, background, and citations. It does not
create wet-lab tasks, run calculations, or decide that a strategy is complete.

# Skills

- `delegate-literature-workflow`
- `extract-data-from-experiment`
- `search-papers-with-mcp`
- `extract-strategy-paper`
- `extract-general-insights-paper`

# Outputs

Save outputs under `project/<project_name>/` in task-appropriate literature,
strategy-input, or reference subfolders. Preserve source paths, metadata,
paper identifiers, extracted claims, and confidence or caveat fields.

# Delegated Literature Preparation

Use `delegate-literature-workflow` for the multi-step path from an experimental
PDF through paper search and local paper extraction. The parent must spawn one
fresh literature sub-agent for each active phase and must not execute the
worker skills itself.

Phase 1 runs `extract-data-from-experiment` and `search-papers-with-mcp`, saves
their normal artifacts, and stops at the manual-download queue. The parent
reports that queue to the user and waits. After the user confirms that selected
PDFs are present, phase 2 starts a fresh sub-agent to run
`extract-strategy-paper` and `extract-general-insights-paper`, then stops before
strategy generation.

Use existing artifacts as the checkpoint between phases. Keep user interaction
and final artifact-path validation in the parent. Follow the delegation skill
for the child boundary and compact handoff. Direct use of one worker skill
remains valid for a standalone, explicitly scoped literature task.

# Experimental Data Extraction

Use `extract-data-from-experiment` when local experimental reports, PDFs, notes,
or tables define the benchmark to explain computationally.

The extraction should provide:

- material identity and composition;
- target reaction or catalytic task;
- measured properties, trends, or benchmarks;
- experimental conditions needed to interpret the computational target;
- constraints that strategy generation must respect.

Do not convert experimental evidence into new experimental actions. It is input
for computational proof strategy, not a wet-lab plan.

# Paper Search

Use `search-papers-with-mcp` when the project needs domain, computational
proof-strategy, and legacy papers centered on an exact
`author_reported_claim`.

Project the experimental extraction into a claim-only JSON before searching.
The paper-search step must not use any other experimental-extraction section to
generate queries, rank candidates, or redefine the proof target. A separately
supplied material/reaction domain is only a neutral search filter.

`search-papers-with-mcp` is search-only. It must preserve the public output
contract in this order: Domain Foundation Papers, Computational Proof-Strategy
Papers, and Legacy Anchor Papers. Direct support, direct challenge,
computational analogue, and method anchor are classifications inside the
Computational Proof-Strategy section, not replacement output sections. Save a
claim-faithful search handoff and manual-download queue, then stop. Do not
download PDFs, call paper extraction skills, or proceed to strategy generation
from the paper-search step.

If papers must be downloaded manually or cannot be accessed through the
available tools, stop and ask the user rather than fabricating source content.

# Paper Extraction

Use `extract-strategy-paper` for papers placed under a strategy-paper folder or
papers intended to inspire computational proof strategies.

Extract:

- proposed mechanisms, descriptors, or computational checks;
- model systems and calculation methods;
- claim structure and supporting figures/tables;
- citations and source metadata that strategy generation must inherit.

Use `extract-general-insights-paper` for non-strategy papers, review papers,
domain background, benchmark context, or method references.

Extract:

- general domain claims;
- reusable concepts and caveats;
- citation metadata;
- relevance to the current catalyst problem.

# Handoff

Before `generate-strategies`, confirm that source artifacts are present and
traceable. Strategy generation should inherit references and claims from these
extraction artifacts, not from memory.

For manuscript citation work, the bounded citation library is managed in
`SKILL/manuscript/workflow.md`; use this literature workflow only when the
source library itself needs to be built or refreshed.
