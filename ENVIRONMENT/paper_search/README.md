# paper-search

Full-text literature **agent** for catalyst / material surface-modeling proposals.

Given a research prompt, the agent retrieves papers from scholarly indexes,
resolves usable full text with open-access/TDM sources first and a configurable
Sci-Hub fallback, parses them, studies them with an LLM and PaperQA2
(citation-grounded QA), validates the extracted surface evidence against its
citations, finds evidence gaps, and proposes surface-modeling calculations
(facets, descriptors, stability) to run next.

This project intentionally does not use publisher scraping, user-uploaded PDFs,
or abstract-only evidence extraction. Sci-Hub fallback is enabled by default and
is used only after primary sources fail; set `scihub.enabled: false` where that
fallback is not legal or appropriate.

## Agent orchestration

The pipeline is orchestrated as a LangGraph `StateGraph`
(`CatalystLiteratureGraph`) of eleven nodes:

```text
intake -> query_planner -> search -> relevance_grading -> resolve_download -> parse
  -> paperqa_index -> evidence_extraction -> claim_validation -> gap_ranking
  -> (loop back to query_planner while gaps remain) -> report_writer
```

It is a **bounded agent loop**: after `gap_ranking`, a conditional edge re-enters
query planning with gap-targeted queries while coverage gaps remain, the round
budget (`agent.max_search_rounds`) is not exhausted, and the last round added new
relevant papers. Each round is incremental (only new papers are processed).

Each node reuses the deterministic retrieval/parsing modules as tool-functions.
LLM/PaperQA nodes self-gate on the configured provider:

- **Deterministic mode** (`llm.provider: none`, the default — no API keys
  needed): rule-based query planning, keyword relevance filtering, regex
  surface-claim extraction, rule-based gap-driven re-search, and the rule-based
  opportunity report. Reproduces the original downloader output (single pass when
  `agent.max_search_rounds: 1`).
- **Full agent mode** (`llm.provider: anthropic | openai | openai-oauth`): LLM
  query expansion + sub-questions, LLM relevance grading, structured extraction,
  PaperQA2 indexing, PaperQA agentic (`agent_query`) citation-grounded validation,
  iterative gap-driven re-search, LLM-augmented gap ranking, and a
  citation-grounded `report.md`.

### Providers and caching

Anthropic, OpenAI, and the `openai-oauth` localhost proxy are supported via
LangChain chat models. **LLM caching is on by default**:

- **Response cache** — a SQLite cache of prompt→completion pairs
  (`<out>/llm_cache.db`), so identical re-runs cost nothing (matches the
  existing `resume` philosophy).
- **Prompt cache** — Anthropic ephemeral `cache_control` on the shared corpus
  prefix (OpenAI prefix caching is automatic).

Both are toggleable under `llm.cache` in config. Set keys via `.env`
(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) or run `npx openai-oauth` and select
`--provider openai-oauth` for the local OAuth proxy.

### PaperQA2

PaperQA2 (`paper-qa`) is a core dependency and runs **locally** using the chat
provider plus either a separate `OPENAI_EMBEDDING_KEY` for OpenAI embeddings or
local embeddings — it does **not** require the FutureHouse hosted API. Embeddings
default to OpenAI `text-embedding-3-small` when `OPENAI_EMBEDDING_KEY` is present,
otherwise a local sentence-transformers model (set `paperqa.embedding` to
override, e.g. `st-multi-qa-MiniLM-L6-cos-v1`).

```bash
# deterministic (no keys)
paper-search run --material RuO2 --reaction HER --out runs/ruo2

# full agent mode
paper-search run --material RuO2 --reaction HER --out runs/ruo2 \
  --provider anthropic --prompt "prioritize durable HER catalysts"

# local OpenAI OAuth proxy mode
npx @openai/codex login
npx openai-oauth
paper-search run --material RuO2 --reaction HER --out runs/ruo2 \
  --provider openai-oauth --model gpt-5.4
```

### Inspecting the graph (LangGraph Studio)

The graph can be run and inspected node-by-node in LangGraph Studio:

```bash
uv run --frozen --extra studio langgraph dev --allow-blocking
```

`--allow-blocking` is required (the pipeline is synchronous; the dev server's
`blockbuster` otherwise rejects blocking I/O). This starts the local dev server
and prints a Studio URL
(`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`). Provide
the run input as JSON, e.g.:

```json
{"material": "RuO2", "reaction": "HER", "extra_terms": [],
 "research_context": {}, "harness_errors": [], "resume_events": []}
```

Set `PAPER_SEARCH_PROVIDER=openai`, `anthropic`, or `openai-oauth` in `.env` to
drive the full agent in Studio; otherwise it runs deterministically. The Studio
entrypoint is `langgraph.json` → `paper_search.agent.studio:make_graph`.

For a static diagram instead, `compiled.get_graph().draw_mermaid()`; for live
per-node progress in code, `CatalystLiteratureGraph(config).stream(...)`.

## Documentation

The checked-in documentation source is under `docs/`. Build it locally with:

```bash
uv run --frozen --extra docs mkdocs build --strict
```

This package does not currently define a documentation deployment workflow.

## Pipeline

```text
User query
  -> Query planner
  -> Crossref / OpenAlex / Semantic Scholar search
  -> DOI deduplication
  -> Unpaywall / Crossref TDM / configured publisher full-text resolution
  -> full-text XML/PDF download and local cache
  -> XML/JATS parser or PDF parser router
  -> Surface evidence extraction
  -> surface-level opportunity report
  -> run_manifest.json + surface_claims.json + opportunity_report.json
```

## Full-text policy

Primary automatic download sources:

- Unpaywall OA locations
- Crossref TDM full-text links
- Configured publisher full-text APIs, such as Elsevier when credentials and
  entitlement are available

Fallback source:

- Sci-Hub mirrors, queried only by the parse-node recovery pass for papers still
  without usable full text. This fallback is enabled by default; set
  `scihub.enabled: false` to disable it.

If no usable full text is found, the paper is recorded as `full_text_unavailable`
and is not used for evidence extraction.

## Parsers

Supported MVP parser routes:

- `oa_xml` -> built-in XML/JATS/TEI block parser
- `oa_pdf` -> GROBID and OpenDataLoader adapters

OpenDataLoader is installed by default through `uv sync`. For standard digital
PDFs, the adapter first tries the Python API and then falls back to the default
CLI form:

```bash
opendataloader-pdf file.pdf output_dir/
```

GROBID is optional. SearchAgent does not start Docker by default. If a GROBID URL
or start command is explicitly configured, PDF parsing will try GROBID lazily and
then continue with OpenDataLoader.

### GROBID

Use GROBID only if you already run a service or intentionally provide a managed
start command:

```bash
export PAPER_SEARCH_GROBID_URL=http://localhost:8070
# Optional: PAPER_SEARCH_GROBID_START_CMD='your-grobid-start-command'
```

### OpenDataLoader

OpenDataLoader is a normal project dependency, not an extra. Internally the
adapter tries:

```python
opendataloader_pdf.convert(
    input_path="paper.pdf",
    output_dir="output/",
    format="json,markdown",
)
```

If that API is incompatible, it falls back to:

```bash
opendataloader-pdf {input} {output_dir}
```

The adapter looks for `.md`, `.markdown`, or `.json` files under `{output_dir}`.

## Run

```bash
uv run --frozen paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her \
  --prompt-file research-prompt.md
```

Example `research-prompt.md`:

```markdown
We are choosing follow-up DFT calculations for a joint experimental/computational
HER project. The experimental team can synthesize RuO2-rich surfaces but needs
guidance on which facets have enough activity evidence and which ones lack
descriptor or stability data. Prioritize tractable slab calculations that can
close a clear literature gap.
```

Outputs:

```text
data/runs/<run>/
  papers.json
  run_manifest.json
  surface_claims.json
  papers/<paper_id>/
    metadata.json
    sources/
      original_0.pdf
      original_0.xml
      source_manifest.json
      resolved_links.json
    parses/
      jats.blocks.json
      grobid.tei.xml
      grobid.blocks.json
      opendataloader.blocks.json
      parse_manifest.json
    extraction/
      surface_claims.json
  opportunity_report.json
```

## Configuration

Runtime configuration is centralized in `paper_search.config` and loaded with
OmegaConf. The CLI loads `./config.yaml` automatically when present, or accepts
an explicit YAML config file:

```bash
uv run --frozen paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her \
  --config config.yaml \
  --prompt-file research-prompt.md
```

Configuration priority is:

```text
CLI arguments > --config YAML > ./config.yaml > built-in structured defaults
```

Use `config.example.yaml` as a starting point for runtime settings. Secret
values such as API keys belong in the working directory `.env`, not in the YAML
config. The loader reads `./.env` with `python-dotenv` before OmegaConf resolves
interpolations, so YAML can reference secrets with `${oc.env:...}`:

```yaml
semantic_scholar:
  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
```

Shell environment variables still take priority over `.env` values. Use
`.env.example` as a template for local secrets. LLM settings select the
extraction path. Deterministic mode uses the rule-based extractor; full agent
mode first attempts structured LLM extraction and falls back to the
deterministic extractor when necessary.

Research direction can be supplied either as `research.prompt` in YAML, with
structured `research.decision_criteria` / `research.constraints`, or at runtime
with `--prompt` / `--prompt-file`. The prompt is preserved in the run manifest,
used to expand search terms, and included in opportunity prioritization.

HTTP calls retry transient failures such as `429` and selected `5xx` responses.
Runs are resumable by default: existing search results, resolved links,
downloads, successful parses, and extracted claims are reused so a failed run can
continue after rate-limit waits or parser configuration fixes. Per-paper stage
failures are recorded in the manifest and do not stop the remaining papers. Use
`--no-resume` to force recomputation.

## Current extraction scope

Deterministic mode captures evidence blocks where the requested material,
reaction alias, surface/facet context, and Miller-index pattern occur together.
Full agent mode applies structured LLM extraction to parsed text first and
persists the resulting claims; if that path is unavailable or produces no
claims, it falls back to the deterministic extractor over saved block files.

## Decision-support scope

This project is not intended to be a clean paper library. The run outputs are
structured to support material/surface triage:

- discovery and access signals are normalized across Crossref, OpenAlex,
  Semantic Scholar, Unpaywall, and Crossref TDM where available
- surface claims are grouped by material, reaction, and surface
- `opportunity_report.json` highlights candidate surfaces, extracted claim-type
  coverage, data gaps, and calculation suggestions such as descriptor,
  stability, selectivity, or activity follow-up

Publisher full-text APIs that require journal credentials are intentionally not
part of the default pipeline.
