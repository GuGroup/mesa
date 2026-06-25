# Quickstart

The minimum flow for a first **deterministic** run (no API keys). To enable the
full LLM + PaperQA agent, see [Full agent mode](user/full-agent.md).

## 1. Install

```bash
uv sync
```

OpenDataLoader (PDF parsing) is included. GROBID is optional — see
[Setup & configuration](admin/setup.md).

## 2. (Optional) local files

```bash
cp config.example.yaml config.yaml
cp .env.example .env       # set PAPER_SEARCH_EMAIL for polite API use
```

Both files are optional; structured defaults are used when they are absent.

## 3. Run

```bash
uv run paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her
```

`--out` is optional — omit it and the run writes to its own session folder under
`~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/` (see
[Setup → Storage layout](admin/setup.md#storage-layout)).

This searches Crossref / OpenAlex / Semantic Scholar, resolves and downloads
usable full text, parses it, and extracts surface evidence — all rule-based.

## 4. Inspect results

```bash
python -m json.tool data/runs/ruo2-her/opportunity_report.json
```

Look first at `candidate_surfaces`, `calculation_suggestions`, and
`run_level_gaps`. See [Outputs](user/outputs.md) for the full reference.

## Next

- [CLI usage](user/cli.md) — every flag and resume behavior
- [Full agent mode](user/full-agent.md) — enable LLM + PaperQA
- [Writing the research prompt](user/research-prompt.md) — steer the agent
