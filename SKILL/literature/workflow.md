# Literature Domain Workflow

Use this manual when collecting or extracting source evidence before strategy
generation, strategy update, or manuscript citation work.

Literature work provides constraints, background, and citations. It does not
create wet-lab tasks, run calculations, or decide that a strategy is complete.

# Skills

- `extract-data-from-experiment`
- `search-papers-with-mcp`
- `extract-strategy-paper`
- `extract-general-insights-paper`

# Outputs

Save outputs under `project/<project_name>/` in task-appropriate literature,
strategy-input, or reference subfolders. Preserve source paths, metadata,
paper identifiers, extracted claims, and confidence or caveat fields.

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

Use `search-papers-with-mcp` when the project needs papers for strategy
generation, source-library building, or general background.

The user or project context must specify:

- target task or reaction;
- material family or catalyst domain;
- desired search role, such as strategy papers, benchmark papers, method
  papers, or general background.

`search-papers-with-mcp` is search-only. It should recommend Background,
Computational Proof-Strategy, and Legacy Anchor papers, save a search handoff
and manual-download queue, then stop. Do not download PDFs, call paper
extraction skills, or proceed to strategy generation from the paper-search
step.

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
