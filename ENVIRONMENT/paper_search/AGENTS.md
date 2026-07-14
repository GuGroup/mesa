# PAPER SEARCH KNOWLEDGE BASE

## OVERVIEW

- MESA-owned Python 3.11 literature agent for catalyst/surface-model proposals.
- CLI, MCP, and LangGraph Studio all converge on `LiteraturePipeline` / the same
  11-node `CatalystLiteratureGraph`; keep behavior in shared nodes/services.
- This package is distinct from `EXTERNAL/paper-search-mcp/`, an upstream vendor
  snapshot with overlapping command names. Never cross-import or patch both by default.

## WHERE TO LOOK

| Task | Location |
|---|---|
| CLI arguments/output contract | `src/paper_search/cli.py` |
| MCP tool surface | `src/paper_search/mcp_server.py` |
| Studio factory/graph registration | `src/paper_search/agent/studio.py`, `langgraph.json` |
| Graph order, loop, checkpointing | `src/paper_search/agent/graph.py` |
| Runtime dependency composition | `src/paper_search/agent/services.py` |
| Structured defaults/merge precedence | `src/paper_search/config.py` |
| Search/access/parse policy | `src/paper_search/agent/nodes/{search,resolve_download,parse}.py` |
| Artifact layout/resume readers | `src/paper_search/cache.py` |

## CODE MAP

```text
CLI / MCP / Studio -> pipeline.py -> agent/graph.py -> agent/nodes/*
  -> services.py -> search/* + resolvers/* + parsers/* + LLM/PaperQA
```

- Graph: `intake -> query_planner -> search -> relevance_grading ->
  resolve_download -> parse -> paperqa_index -> evidence_extraction ->
  claim_validation -> gap_ranking -> report_writer`.
- `gap_ranking` may loop to `query_planner`; round budget and new-paper/gap gates
  bound the cycle. `GraphState` stays serializable; services stay out of state.
- `models.py` is the cross-stage data contract. `http.py`, `cache.py`, and
  `servers.py` own external I/O, persistence, retries, and managed GROBID lifecycle.

## CONVENTIONS

- Config precedence: CLI overrides > explicit `--config` > discovered
  `./config.yaml` > structured defaults. Environment precedence: shell > cwd
  `.env` > `~/.env`. Never print resolved secrets.
- Default output is `$SEARCHAGENT_HOME/sessions/...` or `~/.SearchAgent/sessions/...`.
  Resume is artifact-based: reuse papers, links, downloads, parses, and claims.
  In-memory LangGraph checkpointing is optional and is not durable resume.
- Deterministic mode is the offline default. Full mode requires a supported
  provider/key, then enables LLM extraction/reporting and persisted PaperQA state.
- Access order is indexed OA links, Unpaywall/Crossref TDM, configured publisher
  APIs, then one parse-recovery Sci-Hub attempt. Sci-Hub is enabled by default;
  preserve the disable switch and jurisdiction/legal warning.
- Reject HTML/stubs and abstract-only evidence; retain the full-text quality gate.
- Runtime is synchronous/blocking except bounded threaded search fan-out. Studio
  requires `langgraph dev --allow-blocking`; do not assume async-safe nodes.
- There is currently no package test suite, test dependency, CI, lint, or type
  configuration. Add package-local validation with behavior changes.
- README/MkDocs surfaces drift: README miscounts graph nodes and contains stale
  deterministic-extraction text; referenced `docs/` and docs workflow are absent.

## ANTI-PATTERNS

- Do not treat `EXTERNAL/paper-search-mcp/` as this package's implementation.
- Do not make Sci-Hub a primary resolver or bypass the OA/TDM/full-text gates.
- Do not confuse empty/transient results with durable cache truth; preserve the
  existing rules that avoid caching total resolver/search failure as final state.
- Do not move service objects, clients, or PaperQA `Docs` into `GraphState`.
- Do not claim tests or documentation builds passed when those surfaces are absent.
- Do not commit `.env`, `config.yaml`, run outputs, caches, or `.langgraph_api/`.

## COMMANDS

```bash
cd ENVIRONMENT/paper_search
uv sync --frozen --extra mcp --extra local-embeddings
uv run --frozen paper-search run --material RuO2 --reaction HER \
  --out ../../project/<project_name>/paper_search/ruo2
uv run --frozen --extra mcp paper-search-mcp
uv run --frozen --extra studio langgraph dev --allow-blocking
```
- No canonical test command exists yet; report that boundary explicitly.
