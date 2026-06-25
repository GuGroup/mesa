# Outputs

A run writes machine-readable artifacts under its output directory — by default a
session folder `~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/`, or
the path you pass to `--out` (see [Setup → Storage layout](../admin/setup.md#storage-layout)).

```text
<output dir>/
  papers.json
  run_manifest.json
  surface_claims.json
  opportunity_report.json
  report.md            # full mode only
  llm_cache.db         # full mode only (SQLite response cache)
  paperqa/             # full mode only (persisted PaperQA index)
  papers/<paper_id>/
    metadata.json
    sources/
      resolved_links.json
      source_manifest.json
    parses/
      parse_manifest.json
      *.blocks.json
    extraction/
      surface_claims.json
```

## `surface_claims.json`

Surface claims are evidence snippets tying a specific surface to the target
reaction (rule-extracted in deterministic mode, LLM-extracted in full mode).

```json
{
  "paper_id": "paper1",
  "material": "RuO2",
  "reaction": "HER",
  "surface_text": "(110)",
  "evidence_text": "RuO2(110) surface shows HER activity at 42 mV.",
  "claim_type": "activity",
  "value": "42",
  "unit": "mV",
  "confidence": 0.8
}
```

## `opportunity_report.json`

The main decision-support artifact. Important fields:

- `research_context`: user-provided research direction.
- `prioritization_basis`: signals used for ranking and suggestions.
- `candidate_surfaces`: grouped surface records and coverage gaps.
- `calculation_suggestions`: suggested next calculations.
- `run_level_gaps`: problems that affect the whole run.
- `llm_ranking` (full mode): the LLM-refined surface ranking and suggestions.

Example suggestion:

```json
{
  "material": "RuO2",
  "reaction": "HER",
  "surface": "(110)",
  "calculation_type": "descriptor_calculation",
  "reason": "Activity evidence exists, but descriptor evidence was not extracted.",
  "suggested_next_step": "Compute adsorption/free-energy descriptors for the reported active surface.",
  "priority": "high"
}
```

## `report.md` (full mode)

In full agent mode, `report_writer` synthesizes a citation-grounded Markdown
surface-modeling proposal: ranked candidate surfaces, recommended calculations
(facet, descriptor, stability, selectivity), and open data gaps — grounded in the
validated claims and PaperQA evidence.

## `run_manifest.json`

The provenance-heavy artifact:

- `mode` (`deterministic` / `full`) and `provider`,
- `rounds` (gap-driven search rounds run) and `coverage` (the gap summary that
  drove the loop),
- query list and search errors,
- per-paper resolver/download/parse status,
- extracted claims,
- `validated_claims` — each claim plus its PaperQA `validation` (`null` in
  deterministic mode or beyond the validation cap),
- opportunity report (with `llm_ranking` in full mode),
- retry and resume harness events.

Use this file when debugging why a paper was included, skipped, or marked
`full_text_unavailable`. A paper is also marked `full_text_unavailable` when its
parsed body is shorter than `parsers.min_full_text_chars` (a content-quality
gate): a title-only or metadata-stub download — e.g. an unauthenticated Elsevier
`coredata` response — is rejected instead of passing as full text and silently
yielding no evidence (`parsed_char_count` records the measured length). The
`harness` section records resume reuse, HTTP retry sleeps, and per-paper stage
errors that did not stop the run:

```json
{
  "harness": {
    "resume": true,
    "resume_events": [
      {"stage": "parse", "paper_id": "paper1", "status": "reused_successful_parse"}
    ],
    "http_retry": {
      "event_count": 1,
      "events": [
        {"url": "https://api.semanticscholar.org/...", "attempt": 1, "status": 429, "sleep_seconds": 60}
      ]
    },
    "error_count": 1,
    "errors": [
      {"stage": "extract", "paper_id": "paper2", "error_type": "JSONDecodeError", "error": "Expecting value..."}
    ]
  }
}
```
