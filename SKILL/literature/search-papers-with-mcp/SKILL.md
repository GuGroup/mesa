---
name: search-papers-with-mcp
description: "Search, screen, and recommend catalyst-domain academic papers using paper_search MCP metadata only, organized into three outputs: Domain Foundation Papers for material-domain knowledge, Computational Proof-Strategy Papers for recent DFT-backed evidence related to the target task, and optional Legacy Anchor Papers for older implicitly related foundations. Use when Codex needs to find and rank candidate catalyst papers for a user-specified target task and material domain, create a manual-download queue, report DOI/URL/PDF-link metadata, or hand off recommended domain/strategy/legacy papers before any PDF download or extraction. This skill must not download PDFs or decompose papers."
---

For MESA end-to-end use, read `SKILL/literature/workflow.md` before applying this skill.

# Search Papers With MCP

## Overview

Use this skill for catalyst literature discovery when the `paper_search` MCP
tools are available. Prefer MCP search calls from the `mcp__paper_search`
namespace over web search, shell scripts, or the bundled `paper-search` CLI
because the MCP server exposes structured scholarly metadata.

This is a **search-only and recommendation-only** skill. It must stop after
reporting ranked candidate papers and a manual-download queue. It must not
download PDFs, call download tools, call full-text decomposition skills, or
continue into `extract-strategy-paper` / `extract-general-insights-paper`.

The largest permitted domain is **Catalyst**. Every search lane must stay
connected to catalyst materials, catalytic reactions, active sites, catalytic
performance, or catalyst design. Computational chemistry is mandatory for the
proof-strategy lane, but not for the domain-foundation lane.

## Required User Input

Require both fields before starting the search:

- `target task`: the claim, hypothesis, comparison, or literature goal the user wants to support.
- `material domain`: the catalyst material class, chemistry family, or structural class to search within.

If either field is missing, ask for it directly before calling the MCP tools. Example accepted input:

- `target task`: Prove CoNiCuRu is great for NO3RR
- `material domain`: High Entropy Alloy

Treat the target task as a literature-search objective, not as a conclusion to
force. Search for supporting and contradicting evidence, then report what the
metadata and abstracts show.

## New Idea Handling

Assume the project may be trying to prove a new catalyst idea. Do not treat the absence of exact-match papers for the target composition, material, or reaction as a failure. If no equivalent paper exists, explicitly say so and build the evidence from adjacent systems, shared material-domain principles, analogous reactions, similar active-site motifs, and reusable DFT proof strategies.

Prefer a defensible proof route over forced equivalence. The goal is to identify what prior work can justify testing the new idea: which descriptors to compute, which intermediates to compare, which competing pathways to rule out, which stability checks matter, and which related materials establish plausibility.

## Required Output Lanes

Produce a search handoff in these three sections. Run separate searches for
each lane because each lane has a different purpose and evidence gate.

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
   - DOI or known-paper lookup: `get_crossref_paper_by_doi` or
     `search_unpaywall` for metadata only.
7. Run small focused searches first, usually 5-10 results per source per lane. Broaden only when a lane lacks useful coverage.
8. Deduplicate by DOI, arXiv ID, title, and first author/year. Prefer peer-reviewed or authoritative versions over preprints when the user did not ask specifically for preprints.
9. Do not read or download full papers in this skill. Treat search metadata,
   abstracts, DOI records, and visible `pdf_url` fields as search evidence only.
10. Rank recommended papers in each lane. For each recommended paper, record
    why it belongs in that lane and whether the recommendation is based on
    title-only, abstract/metadata, DOI metadata, or explicit search result
    fields such as `pdf_url`.
11. Build a manual-download queue for papers that should be downloaded by the
    user before extraction. Include DOI, publisher URL, source URL, and visible
    PDF URL when the search result provides one, but do not fetch the file.
12. Do not mix lanes. A paper can appear in more than one lane only if it
    genuinely serves both purposes; otherwise place it where it is most useful.
13. If exact target-task papers are absent, continue with adjacent evidence and
    label it as indirect support, analogy, or proof-strategy evidence.
14. Stop after reporting and saving the search handoff. Do not call
    `extract-strategy-paper`, `extract-general-insights-paper`, or
    `generate-strategies` in the same step unless the user separately provides
    local PDF/extraction artifacts and asks to proceed.

## Tool Selection

Use `search_papers` when combining sources is useful and the query is broad.
Pass `sources` as a comma-separated list such as
`crossref,semantic,openalex,arxiv` rather than `all` by default.

Use source-native search tools when the user names a source, when a source has better coverage for the domain, or when the query needs source-specific filters:

- `search_crossref` / `get_crossref_paper_by_doi` for DOI-centered metadata
  and publisher records.
- `search_semantic(query, year=...)` for broad citation metadata and year filtering.
- `search_openalex` for broad scholarly metadata.
- `search_arxiv(query, sort_by="submittedDate" or "relevance")` for recent preprints and computational methods.
- `search_pubmed` / `search_pmc` for catalyst work tied to biomedical or enzymatic systems.
- `search_unpaywall` for DOI-centered open-access metadata.

Use `search_unpaywall` only as DOI-centered open-access metadata for the
manual-download queue. Do not use Unpaywall URLs to download files in this
skill.

Never call `download_with_fallback`, `download_arxiv`, `download_openalex`,
`download_doaj`, `download_base`, `download_zenodo`, `download_hal`,
`download_openaire`, `download_citeseerx`, `download_iacr`, Sci-Hub fallback,
or any other PDF download tool from this skill. Never call `read_*_paper` or
local PDF-decomposition skills from this skill.

If the project needs full-text evidence after the search handoff, tell the user
which PDFs to download manually and where to place them, for example:

```text
project/<project_name>/literature/strategy_papers/
project/<project_name>/literature/domain_papers/
project/<project_name>/literature/legacy_papers/
```

After the user provides local PDFs, use `extract-strategy-paper` or
`extract-general-insights-paper` as a separate workflow step.

## Saved Search Handoff

When working inside a MESA project folder, save the search handoff under:

```text
project/<project_name>/literature/search/
  paper_search_results.md
  paper_search_results.json
  manual_download_queue.md
```

The Markdown result must be suitable for the user to inspect directly. The JSON
must preserve the lane, rank, title, authors, year/date, DOI/arXiv/PMID/URL,
source database, `pdf_url` if present in metadata, recommendation reason,
evidence basis, and caveats.

The manual-download queue must group recommended papers by destination folder:

- `strategy_papers`: papers to decompose with `extract-strategy-paper`;
- `domain_papers`: review/background papers for `extract-general-insights-paper`;
- `legacy_papers`: optional anchors for mechanism/descriptor context.

## Reporting Standard

Start the final answer with the resolved inputs:

- `target task`;
- `material domain`;
- search date;
- MCP sources searched.

Then report the three output lanes in order:

1. `Domain Foundation Papers`
2. `Computational Proof-Strategy Papers`
3. `Legacy Anchor Papers`

For each recommended paper, include:

- title;
- first author et al. or author list if short;
- year;
- catalyst/material system;
- target reaction or catalytic task;
- lane-specific reason for inclusion;
- DFT/computational chemistry signal found in metadata/abstract, or
  `not required for this lane` for Domain Foundation Papers;
- recommendation rank and whether the paper is recommended for manual download;
- source/database;
- DOI, arXiv ID, PMID/PMCID, URL, and metadata `pdf_url` when present.

For summaries, separate metadata-grounded statements from full-text-grounded
statements. In this search-only skill, full-text-grounded statements should be
absent unless they were already present in a prior saved extraction artifact.
Say when a conclusion is based only on title/abstract/metadata. If papers
appear to disagree, report the disagreement as a search-stage signal, not as a
resolved scientific conclusion.

When the user frames the task as `prove X is great`, do not overstate the evidence. Use language such as `supports`, `is consistent with`, `contradicts`, or `not enough DFT evidence found` depending on the papers.

For new-idea searches, include a short `Evidence Gap / Proof Route` note when
exact equivalent papers are missing. State what was not found, then list the
most relevant adjacent evidence and the computations or comparisons needed to
make the new claim credible.

End the final answer with:

- paths to `paper_search_results.md`, `paper_search_results.json`, and
  `manual_download_queue.md` when saved;
- a clear statement that no PDFs were downloaded;
- the next step: user manually downloads selected PDFs, then Codex runs the
  appropriate extraction skill.

## Boundaries

Do not use general web search as the primary paper search path while
`paper_search` MCP tools are available. Use web only for publisher pages,
missing official links, or non-paper context that MCP cannot provide.

Do not invent citation details or computed values. If a tool response lacks
DOI, venue, year, authors, or DFT values, mark that field as unavailable or
verify through another search/metadata source.

Do not include non-catalyst papers in the final evidence set. Do not include papers lacking computational chemistry evidence in the Computational Proof-Strategy lane unless explicitly labeled as background and kept outside that lane.

Do not over-broaden by querying every source for routine searches. Target sources to the lane purpose, then expand if coverage is weak.

Do not download, copy, move, or create PDF files. Do not continue into paper
extraction or strategy generation from this skill.
