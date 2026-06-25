# Setup & configuration

## Install

```bash
uv sync
```

Optional extras:

```bash
uv sync --extra docs              # MkDocs Material (build the site)
uv sync --extra studio            # langgraph-cli (LangGraph Studio)
uv sync --extra local-embeddings  # sentence-transformers (local PaperQA embeddings)
```

`torch` is **not** in the core install; it comes only with `local-embeddings`.
Deterministic mode and OpenAI-embedding full mode do not need it.

## Storage layout

By default each run gets its own isolated session folder under
`~/.SearchAgent` (override the base with `$SEARCHAGENT_HOME`):

```text
~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/
  run_manifest.json  surface_claims.json  opportunity_report.json
  report.md  llm_cache.db  paperqa/  papers/<paper_id>/{sources,parses,extraction}
```

- Sessions are **fully isolated** — downloaded papers and caches are not shared
  across sessions.
- `--out <dir>` writes to an explicit directory instead; re-running with the same
  `--out` resumes it.
- `--session <id>` reuses a named session folder under the base (for resume).

## Configuration layers

- `config.yaml`: non-secret runtime settings, loaded with OmegaConf.
- `.env`: local secrets, loaded with `python-dotenv`.

`config.yaml` is optional; if present in the working directory it loads
automatically, and `--config` can point elsewhere.

```text
CLI arguments > --config YAML > ./config.yaml > structured defaults
```

Shell environment variables take priority over `.env` values (`.env` is loaded
with `override=False`).

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

## Secrets

```env
PAPER_SEARCH_EMAIL=you@example.com
SEMANTIC_SCHOLAR_API_KEY=
ELSEVIER_API_KEY=
ELSEVIER_INSTTOKEN=
OPENAI_API_KEY=
OPENAI_EMBEDDING_KEY=
OPENAI_BASE_URL=
ANTHROPIC_API_KEY=
```

Reference secrets from YAML with `oc.env` interpolation:

```yaml
semantic_scholar:
  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
```

LLM keys (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) or the local `openai-oauth`
proxy enable the full agent. PaperQA OpenAI embeddings use
`OPENAI_EMBEDDING_KEY` separately — see [Full agent mode](../user/full-agent.md).

## Search

```yaml
search:
  per_query_limit: 10
  max_papers: 30
  max_concurrency: 4    # concurrent (query, client) search requests
```

### Semantic Scholar rate limit

Semantic Scholar allows only **1 request/second**, cumulative across all
endpoints, even with an API key (sent as the `x-api-key` header). The client
serializes and spaces out its requests accordingly — keep `min_request_interval`
above `1.0`:

```yaml
semantic_scholar:
  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
  min_request_interval: 1.1
```

Other clients (Crossref/OpenAlex) still run concurrently; only Semantic Scholar
is throttled.

### Elsevier full text (optional)

Crossref's TDM links for Elsevier articles point at `api.elsevier.com`. Fetched
unauthenticated, that endpoint returns a metadata-only **coredata** stub (title,
DOI, journal — no body), which parses to a title-only document and yields no
evidence. With an [Elsevier API key](https://dev.elsevier.com/) — and
institutional entitlement (on-network IP, or an inst token) — the same links
return the full article XML. SearchAgent attaches the credentials only to
`api.elsevier.com` requests, so non-Elsevier downloads are unaffected.

```yaml
elsevier:
  api_key: ${oc.env:ELSEVIER_API_KEY,""}
  inst_token: ${oc.env:ELSEVIER_INSTTOKEN,""}   # only if your key is not IP-entitled
```

```env
ELSEVIER_API_KEY=your-key
ELSEVIER_INSTTOKEN=
```

Leave both blank to skip Elsevier auth (coredata stubs are still downloaded but
contribute no evidence). Text and data mining via the Elsevier API is subject to
your institution's ScienceDirect agreement and Elsevier's API policy.

## Parsers

Supported parser routes:

- `oa_xml` → built-in XML/JATS/TEI block parser.
- `oa_pdf` → OpenDataLoader (default) and GROBID (opt-in).

OpenDataLoader is a normal dependency. For standard digital PDFs the adapter
tries the Python API and then the configured CLI form.

GROBID is **optional** and never started by default. Configure it only if you run
a service or provide a managed start command:

```yaml
parsers:
  grobid:
    url: ${oc.env:PAPER_SEARCH_GROBID_URL,""}
    start_cmd: ${oc.env:PAPER_SEARCH_GROBID_START_CMD,""}
    startup_timeout: 120
    shutdown_timeout: 10
  opendataloader:
    cmd: ${oc.env:PAPER_SEARCH_OPENDATALOADER_CMD,"opendataloader-pdf {input} {output_dir}"}
```

When a GROBID URL or start command is set, PDF parsing tries GROBID lazily and
then continues with OpenDataLoader.

## Retry and resume

Transient API failures retry the status codes under `http.retry`. For `429`,
SearchAgent respects `Retry-After` when present, otherwise the backoff sequence.

```yaml
http:
  timeout: 30
  retry:
    max_attempts: 4
    backoff_seconds: [5, 15, 60]
    retry_statuses: [429, 500, 502, 503, 504]
    respect_retry_after: true
    max_sleep_seconds: 120
```

Runs are resumable by default:

```yaml
execution:
  resume: true
  checkpoint: false   # opt-in LangGraph checkpointer (streaming/inspection)

agent:
  max_search_rounds: 3          # gap-driven re-search loop (1 = single pass)
  min_new_papers_to_continue: 1 # stop when a round adds no new relevant papers
  relevance_filter: lenient     # strict | lenient (topical + keep-if-unsure) | off
```

The `agent` block controls the gap-driven loop; see
[Full agent mode](../user/full-agent.md#iterative-gap-driven-loop).

With `resume`, successful artifacts are reused: `papers.json`, resolved links,
downloaded source, successful parse blocks, per-paper `surface_claims.json`, and
(full mode) the PaperQA index. Failed or incomplete stages are retried, and a
per-paper failure is recorded in `run_manifest.json` without stopping the run.
JSON artifacts are written via atomic replacement. Use `--no-resume` to force
recomputation.

In full mode the SQLite response cache (`llm_cache.db`) adds a second layer: even
with `--no-resume`, identical LLM prompts are served from cache rather than
re-billed. See [Full agent mode](../user/full-agent.md#caching).
