---
name: search-papers-with-mcp
description: Search, screen, and recommend catalyst papers from paper_search MCP metadata using an exact author_reported_claim as the scientific boundary. Use when a MESA project needs a no-download literature handoff organized into Domain Foundation Papers, Computational Proof-Strategy Papers, and optional Legacy Anchor Papers without broadening the claim from other experimental-extraction content.
---

For MESA end-to-end use, read `SKILL/literature/workflow.md` before applying this skill.

# Search Papers With MCP

## Purpose

Build a claim-faithful catalyst literature handoff with exactly three public
sections:

1. Domain Foundation Papers
2. Computational Proof-Strategy Papers
3. Legacy Anchor Papers

Treat the section contract and the evidence classification as separate
dimensions. Classify direct support, challenge, analogy, and method relevance
inside the Computational Proof-Strategy section; never replace the three
public sections with those classifications.

This skill is metadata/abstract search only. Stop after saving recommendations
and a manual-download queue. Do not download or read PDFs, decompose papers,
generate strategies, or run calculations.

## Claim-Only Input Boundary

When an experimental extraction is supplied:

1. Run `scripts/project_author_claim.py` on the extraction.
2. Use the resulting claim-only JSON as the exclusive scientific input.
3. Do not use material identity, structure, phase, characterization, measured
   properties, figure data, missing-information lists, or any other extraction
   content to generate queries or rank papers.

The claim-only object contains only:

```json
{
  "author_reported_claim": {
    "statement": "...",
    "source_locations": {
      "abstract": "...",
      "conclusion": "..."
    },
    "extraction_artifact": "..."
  }
}
```

If the claim lacks enough catalyst context, ask the user for a neutral material
domain or reaction filter. Use it only to constrain discovery. Never append it
to, reinterpret, or replace the claim.

## Claim Fidelity Invariants

- Copy the claim statement byte-for-byte into every saved search artifact.
- Derive scientific query terms only from concepts explicitly named in the
  claim. Add only role terms needed by a section, such as `review`,
  `perspective`, `DFT`, `first-principles`, `free energy`, `activation barrier`,
  `kinetics`, `stability`, `benchmark`, or `seminal`.
- Do not introduce a phase, interface, defect, active site, mechanism,
  descriptor, composition, or causal variable because it appears elsewhere in
  an extraction.
- Preserve logical strength. Do not turn association into causation, a trend
  into a mechanism, a high fraction into phase coexistence, or activity into
  selectivity or stability.
- Search for supporting and contradicting computational evidence.
- Never force an exact-match conclusion when literature supports only an
  analogy.
- Keep these rules general. Do not add material-specific rewriting rules,
  keyword exceptions, or lookup tables.

## Required Inputs

- One validated claim-only JSON from `project_author_claim.py`, or an exact
  user-supplied claim when no extraction exists.
- An optional neutral catalyst material-domain/reaction filter only when the
  claim lacks enough search context.

Do not accept the full experimental extraction as generation context.

## Required Output Sections

Run separate searches for each section because their purposes and evidence
requirements differ.

### 1. Domain Foundation Papers

Build domain knowledge for the catalyst material and reaction explicitly named
in the claim. Prefer reviews, perspectives, tutorials, and broad surveys that
explain the material class, catalytic use, structural vocabulary, stability,
and established performance context.

Computational chemistry is not required in this section. A paper must still be
catalyst-relevant and materially useful for interpreting the claim. Do not let
domain background redefine the proof target.

### 2. Computational Proof-Strategy Papers

Find papers that show how to computationally support, challenge, or test the
exact author-reported claim. Require an explicit DFT, first-principles, reactive
simulation, kinetic-model, or comparable computational-chemistry signal in the
title, abstract, or metadata.

Assign one `strategy_relation` to every paper in this section:

- `direct_support`: computationally tests the same variables, comparison, and
  catalytic outcome and reports a compatible result;
- `direct_challenge`: tests the same proposition and reports a conflicting or
  limiting result;
- `computational_analogue`: tests the same logical relationship in an adjacent
  catalyst, reaction, or model, with transfer limits stated explicitly;
- `method_anchor`: supplies a rigorous computational method needed to test or
  falsify the claim but does not itself establish the claim.

Use analogues and method anchors when exact computational papers are
insufficient. Never allow them to redefine the target.

### 3. Legacy Anchor Papers

Optionally identify older or foundational catalyst papers that establish a
seminal mechanism, descriptor, benchmark, computational protocol, or concept
explicitly relevant to the claim. Computational chemistry is preferred when
relevant but is not mandatory for a genuinely foundational anchor.

Keep this section even when no strong anchor is found; state that outcome
instead of filling it with weakly related papers.

## Workflow

1. Produce or load the claim-only object.
2. Record an immutable claim ledger containing the exact statement, explicit
   variables/comparisons, catalytic outcome, logical qualifiers, and absent
   concepts that must not be imported.
3. Build three query groups from the ledger plus section-role terms:
   - domain foundation: explicit material/reaction terms plus catalyst and
     review/overview terms;
   - computational proof strategy: claim variables and outcome plus generic
     computational-proof terms;
   - legacy anchor: explicit material/reaction/outcome terms plus
     seminal/benchmark/method terms.
4. Search each section separately through Crossref, Semantic Scholar,
   OpenAlex, and arXiv as appropriate.
5. Start with 5-10 results per source and broaden only when a section lacks
   useful coverage.
6. Deduplicate by DOI, arXiv ID, title, and author/year. Prefer peer-reviewed
   versions over preprints unless the preprint is the only accessible record.
7. Apply the admission gate to every recommended paper.
8. Rank papers within each of the three sections.
9. Save the handoff and manual-download queue, then stop.

## Candidate Admission Gate

Record for every recommended paper:

- `section`: `domain_foundation`, `computational_proof_strategy`, or
  `legacy_anchor`;
- `claim_clause`: an exact substring or faithful minimal clause from the claim;
- `computational_test`: the calculation signal visible in metadata/abstract,
  or `not required for this section` outside the strategy section;
- `strategy_relation`: one of the four values above for strategy papers and
  `not_applicable` for the other sections;
- `scope_match`: what matches the claim or its explicit domain;
- `scope_mismatch`: what differs or is unavailable;
- `claim_drift_check`: `pass` only when the paper does not redefine the target;
- bibliographic identifiers, evidence basis, and caveats.

Reject a paper from Computational Proof-Strategy when it lacks a computational
signal, depends on extraction content outside the claim, merely shares a
material name, or requires an unclaimed causal variable to appear relevant.
Retain a useful near match only as `computational_analogue` or `method_anchor`
with an explicit mismatch; otherwise exclude it.

Do not move a strategy near match into Domain Foundation merely to bypass the
computational evidence requirement. Domain papers must independently satisfy
the domain-purpose gate.

## MCP Tool Policy

Prefer `mcp__paper_search` metadata tools:

- `search_papers` with targeted sources such as
  `crossref,semantic,openalex,arxiv`;
- `search_crossref` and `get_crossref_paper_by_doi` for DOI metadata;
- `search_semantic` and `search_openalex` for citation/abstract coverage;
- `search_arxiv` for computational preprints;
- `search_unpaywall` only for DOI-centered open-access metadata.

Never call download or `read_*_paper` tools in this skill. Do not use general
web search as the primary paper-search path while paper_search MCP is
available.

## Saved Handoff

Save under:

```text
project/<project_name>/literature/search/
  author_reported_claim.json
  paper_search_results.md
  paper_search_results.json
  manual_download_queue.md
```

The JSON must preserve:

- the exact claim-only object and claim ledger;
- search date, queries, and MCP sources;
- the three top-level sections in contract order;
- rank, title, authors, year/date, DOI/arXiv/URL, and metadata `pdf_url`;
- every Candidate Admission Gate field;
- evidence basis and caveats;
- a boolean stating that no PDFs were downloaded.

The Markdown must lead with the exact claim and contain exactly these public
paper headings in order:

1. `Background Papers`
2. `Computational Proof-Strategy Papers`
3. `Legacy Anchor Papers`

Use strategy-relation labels inside the second section only. Do not emit Direct
Proof, Computational Analogues, or Falsification/Method Anchors as replacement
top-level sections.

Group the manual-download queue by destination:

- `domain_papers/`
- `strategy_papers/`
- `legacy_papers/`

## Validation Checklist

Before reporting completion, verify:

- the saved claim exactly equals the projected `author_reported_claim`;
- no scientific query term came from another extraction section;
- the Markdown and JSON preserve the three-section contract in order;
- every strategy paper has an explicit computational signal and exactly one
  valid `strategy_relation`;
- every mismatch is visible rather than silently generalized;
- supporting and challenging evidence were considered;
- no material-specific rewrite rule or exception was added;
- no PDF was downloaded or read;
- the workflow stops before paper extraction or strategy generation.

End by reporting artifact paths, stating that no PDFs were downloaded, and
asking the user to place selected PDFs in their queued domain, strategy, and
legacy folders for the separate extraction step.
