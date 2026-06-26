---
name: search-papers-with-mcp
description: "Search, screen, read, and download catalyst-domain academic papers using the paper_search MCP tools, organized into three outputs: Domain Foundation Papers for material-domain knowledge, Computational Proof-Strategy Papers for recent DFT-backed evidence related to the target task, and optional Legacy Anchor Papers for older implicitly related foundations. Use when Codex needs to find catalyst papers for a user-specified target task and material domain, especially for new catalyst ideas where exact equivalent papers may not exist, compare candidate catalysts or materials, extract computational chemistry evidence such as DFT adsorption energies/free energies/barriers/electronic structure, retrieve metadata from scholarly sources, read accessible papers, download PDFs, or produce source-grounded catalyst literature summaries with citations."
---

# Search Papers With MCP

## Overview

Use this skill for catalyst literature discovery and paper retrieval when the `paper_search` MCP tools are available. Prefer MCP calls from the `mcp__paper_search` namespace over web search, shell scripts, or the bundled `paper-search` CLI because the MCP server exposes structured search, read, download, and fallback tools directly.

The largest permitted domain is **Catalyst**. Every search lane must stay connected to catalyst materials, catalytic reactions, active sites, catalytic performance, or catalyst design. Computational chemistry is mandatory for the proof-strategy lane, but not for the domain-foundation lane.

## Required User Input

Require both fields before starting the search:

- `target task`: the claim, hypothesis, comparison, or literature goal the user wants to support.
- `material domain`: the catalyst material class, chemistry family, or structural class to search within.

If either field is missing, ask for it directly before calling the MCP tools. Example accepted input:

- `target task`: Prove CoNiCuRu is great for NO3RR
- `material domain`: High Entropy Alloy

Treat the target task as a literature-search objective, not as a conclusion to force. Search for supporting and contradicting evidence, then report what the papers actually show.

## New Idea Handling

Assume the project may be trying to prove a new catalyst idea. Do not treat the absence of exact-match papers for the target composition, material, or reaction as a failure. If no equivalent paper exists, explicitly say so and build the evidence from adjacent systems, shared material-domain principles, analogous reactions, similar active-site motifs, and reusable DFT proof strategies.

Prefer a defensible proof route over forced equivalence. The goal is to identify what prior work can justify testing the new idea: which descriptors to compute, which intermediates to compare, which competing pathways to rule out, which stability checks matter, and which related materials establish plausibility.

## Required Output Lanes

Produce the final answer in these three sections. Run separate searches for each lane because each lane has a different purpose and evidence gate.

### 1. Domain Foundation Papers

Purpose: build domain knowledge for the input `material domain`.

Search target: review papers, perspectives, tutorials, highly cited overviews, and broad experimental/computational surveys about the material domain as catalyst materials. Use this lane to explain what the material class is, why it is used in catalysis, common synthesis/structure concepts, stability issues, active-site hypotheses, composition/strain/electronic effects, and known application areas.

Evidence gate: DFT or computational chemistry evidence is **not required** for this lane. Review papers are recommended. The papers must still be catalyst-relevant and materially useful for understanding the input material domain.

Example query shape: `<material domain> catalyst review`, `<material domain> electrocatalyst review`, `<material domain> catalysis active site stability overview`.

### 2. Computational Proof-Strategy Papers

Purpose: find recent approaches for proving similar materials or systems for the `target task`.

Search target: papers close to the target task, reaction, material system, or proof style. Prefer recent papers and papers that show how authors used DFT or first-principles calculations to argue activity, selectivity, stability, active sites, reaction pathways, or descriptor trends for similar catalysts.

Evidence gate: require DFT or closely related computational chemistry information for final inclusion, such as adsorption energies, reaction/free-energy diagrams, activation barriers, projected density of states, charge transfer, Bader/charge analysis, surface/slab models, defect models, Pourbaix/solvation corrections, or microkinetic parameters derived from first-principles calculations.

For electrocatalysis tasks, prefer papers that report at least one of these DFT-linked quantities: adsorption energy of intermediates, free-energy limiting step, overpotential descriptor, surface active-site model, charge/electronic-structure descriptor, competing reaction pathway, or kinetic barrier.

Example query shape: `<target task> <material domain> DFT`, `<reaction> electrocatalyst DFT adsorption free energy`, `<similar material> <similar reaction> density functional theory catalyst`.

### 3. Legacy Anchor Papers

Purpose: optionally identify older or foundational papers that are implicitly related to the `target task`, even if they are not about the exact material domain.

Search target: seminal mechanism, descriptor, benchmark catalyst, computational protocol, reaction-pathway, or early catalyst-design papers that later work relies on. These papers may explain why a reaction intermediate, descriptor, active-site motif, alloy effect, or computational method matters.

Evidence gate: this lane is useful but not mandatory. Include legacy anchors when they add real context; otherwise state that no strong legacy anchor was found from the MCP search. Computational chemistry is preferred when relevant, but older experimental or conceptual papers may be included if their connection to the target task is explicit in your explanation.

Example query shape: `<reaction> catalyst mechanism seminal`, `<reaction> DFT descriptor catalyst`, `<key intermediate> adsorption energy catalyst`, `<method or descriptor> electrocatalysis`.

## Workflow

1. Confirm `target task` and `material domain` are present.
2. Convert them into query groups:
   - material terms, including formula variants and synonyms;
   - catalysis terms, such as catalyst, electrocatalyst, photocatalyst, thermocatalyst, active site, reaction pathway;
   - computational terms, such as DFT, density functional theory, first-principles, adsorption energy, free energy, Gibbs, barrier, electronic structure;
   - task terms, such as NO3RR, nitrate reduction, HER, ORR, CO2RR, NRR, OER, selectivity, activity, stability.
3. Run a separate MCP search for Domain Foundation Papers using material-domain and catalyst terms. Bias toward reviews and broad overview papers. Do not require DFT here.
4. Run a separate MCP search for Computational Proof-Strategy Papers using target-task, material-system, catalyst, and computational terms. Require DFT or equivalent computational chemistry evidence before final inclusion.
5. Run a separate legacy-anchor search when the target task suggests known mechanisms, descriptors, benchmark systems, or historical foundations. If no strong result appears, keep the section and state that no strong legacy anchor was found.
6. Select targeted MCP sources before searching:
   - Catalyst and computational chemistry coverage: `search_crossref`, `search_semantic`, `search_openalex`, `search_papers` with `crossref,semantic,openalex,arxiv`.
   - Reviews and broad domain coverage: `search_crossref`, `search_semantic`, `search_openalex`.
   - Preprints and method-heavy work: `search_arxiv`.
   - Biomedical or bio-catalyst overlap: `search_pubmed`, `search_pmc`, `search_europepmc` only when relevant.
   - DOI or known-paper lookup: `get_crossref_paper_by_doi`, `search_unpaywall`, or a source-native read/download tool.
7. Run small focused searches first, usually 5-10 results per source per lane. Broaden only when a lane lacks useful coverage.
8. Deduplicate by DOI, arXiv ID, title, and first author/year. Prefer peer-reviewed or authoritative versions over preprints when the user did not ask specifically for preprints.
9. Read candidate papers when claims depend on computed values, mechanisms, active sites, or comparisons. Use source-native `read_*_paper` tools where available.
10. Do not mix lanes. A paper can appear in more than one lane only if it genuinely serves both purposes; otherwise place it where it is most useful.
11. If exact target-task papers are absent, continue with adjacent evidence and label it as indirect support, analogy, or proof-strategy evidence.

## Tool Selection

Use `search_papers` when combining sources is useful and the query is broad. Pass `sources` as a comma-separated list such as `crossref,semantic,openalex,arxiv` rather than `all` by default.

Use source-native search tools when the user names a source, when a source has better coverage for the domain, or when the query needs source-specific filters:

- `search_crossref` / `get_crossref_paper_by_doi` for DOI-centered metadata and publisher records.
- `search_semantic(query, year=...)` for broad citation metadata and year filtering.
- `search_openalex` for broad scholarly metadata.
- `search_arxiv(query, sort_by="submittedDate" or "relevance")` for recent preprints and computational methods.
- `search_pubmed` / `search_pmc` for catalyst work tied to biomedical or enzymatic systems.
- `search_unpaywall` for DOI-centered open-access resolution.

Use `read_*_paper` when the answer depends on paper contents, methods, data, claims, or limitations. Search metadata alone is not enough for detailed catalyst or DFT claims in the Computational Proof-Strategy lane.

Use `download_with_fallback` for PDF retrieval when a source-native download may fail but DOI/title fallback is available. Do not use Sci-Hub fallback unless the user explicitly allows it and local policy permits it.

## Reporting Standard

Start the final answer with the resolved inputs:

- `target task`;
- `material domain`;
- search date if relevant;
- MCP sources searched.

Then report the three output lanes in order:

1. `Domain Foundation Papers`
2. `Computational Proof-Strategy Papers`
3. `Legacy Anchor Papers`

For each paper, include:

- title;
- first author et al. or author list if short;
- year;
- catalyst/material system;
- target reaction or catalytic task;
- lane-specific reason for inclusion;
- DFT/computational chemistry evidence found, or `not required for this lane` for Domain Foundation Papers;
- source/database;
- DOI, arXiv ID, PMID/PMCID, or URL.

For summaries, separate metadata-grounded statements from full-text-grounded statements. Say when a conclusion is based only on title/abstract/metadata. If papers disagree, report the disagreement instead of flattening it into a single claim.

When the user frames the task as `prove X is great`, do not overstate the evidence. Use language such as `supports`, `is consistent with`, `contradicts`, or `not enough DFT evidence found` depending on the papers.

For new-idea searches, include a short `Evidence Gap / Proof Route` note when exact equivalent papers are missing. State what was not found, then list the most relevant adjacent evidence and the computations or comparisons needed to make the new claim credible.

## Boundaries

Do not use general web search as the primary paper search path while `paper_search` MCP tools are available. Use web only for publisher pages, missing official links, or non-paper context that MCP cannot provide.

Do not invent citation details or computed values. If a tool response lacks DOI, venue, year, authors, or DFT values, mark that field as unavailable or verify through another MCP source/full-text read.

Do not include non-catalyst papers in the final evidence set. Do not include papers lacking computational chemistry evidence in the Computational Proof-Strategy lane unless explicitly labeled as background and kept outside that lane.

Do not over-broaden by querying every source for routine searches. Target sources to the lane purpose, then expand if coverage is weak.
