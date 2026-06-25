# Full agent mode

By default SearchAgent runs deterministically (rule-based, no API keys). Setting
a provider enables the full agent: LLM query expansion, LLM structured
extraction, PaperQA2 indexing of parsed full text, citation-grounded claim
validation, LLM-augmented gap ranking, and a citation-grounded `report.md`.

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --provider openai --prompt "prioritize DFT-feasible HER surfaces"
```

LLM/PaperQA nodes self-gate on the provider: any node whose key is missing falls
back to the deterministic path, so a run never hard-fails on a missing key.

## Providers and keys

| Provider | Key (in `.env`) | Default model |
| --- | --- | --- |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `OPENAI_API_KEY` | `gpt-5.4-mini` |
| `openai-oauth` | none; local `openai-oauth` proxy | `gpt-5.4` |

Set the provider with `--provider` or `llm.provider` in `config.yaml`, and the
model with `--model` or `llm.model`.

```yaml
llm:
  provider: openai
  model: gpt-5.4-mini
  base_url:
  api_key_env:
  temperature: 0
  max_tokens: 4096
```

### OpenAI OAuth proxy

`openai-oauth` runs through the community `npx openai-oauth` localhost proxy.
It does not require `OPENAI_API_KEY`, but it does require a local Codex/ChatGPT
OAuth auth file and the proxy process must be running on the same machine.

```bash
npx @openai/codex login
npx openai-oauth

uv sync --extra local-embeddings
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --provider openai-oauth --model gpt-5.4
```

The default OAuth proxy base URL is `http://127.0.0.1:10531/v1`. Override it with
`llm.base_url` or `OPENAI_BASE_URL` if the proxy runs elsewhere. The proxy is a
local-only compatibility layer; keep the auth file private and do not expose the
proxy on a shared network.

## Caching

LLM caching is on by default and is toggleable under `llm.cache`:

- `response_cache`: a SQLite cache of prompt→completion pairs at
  `<out>/llm_cache.db` (override with `response_cache_path`). Identical re-runs
  cost nothing — the same idea as `execution.resume`.
- `prompt_cache`: provider prompt caching of the shared corpus prefix — Anthropic
  ephemeral `cache_control`; OpenAI prefix caching is automatic. Prompts put the
  large, stable content in the cached prefix, but the benefit is bounded
  (Anthropic only caches prefixes above a minimum size). In practice the
  **response cache** is the larger cost lever for re-runs.

## PaperQA2

PaperQA2 (`paper-qa`) runs **locally** using the same provider keys — it does
**not** require a FutureHouse account or API. It indexes the parsed full text and
answers material/surface questions with citations, which drives claim validation
and the report.

```yaml
paperqa:
  enabled: true
  embedding:                  # see below
  evidence_k: 10
  answer_max_sources: 5
  validation_max_queries: 25  # one PaperQA query per unique surface, capped
  agentic: true               # use agent_query (multi-step gather) for validation
  agent_evidence_n: 5
  search_count: 8
```

Claim validation deduplicates claims by surface and issues at most
`validation_max_queries` PaperQA queries (one per unique surface), then maps each
verdict back to the claims sharing that surface. With `agentic: true` each query
uses PaperQA's agent (`agent_query`, multi-step `gather_evidence`) over our
corpus, falling back to a single `aquery` pass on error.

## Iterative gap-driven loop

The agent re-searches to fill evidence gaps. After ranking, if coverage gaps
remain it loops back to query planning with gap-targeted queries (and, in full
mode, LLM-decomposed sub-questions and LLM-generated gap queries). The loop is
bounded and idempotent — each round only processes newly found papers.

```yaml
agent:
  max_search_rounds: 3          # 1 = single pass (no loop)
  min_new_papers_to_continue: 1 # stop when a round adds no new relevant papers
  relevance_filter: lenient     # strict | lenient (topical + keep-if-unsure) | off
```

The loop stops when there are no meaningful gaps, the round budget is exhausted,
or a round adds no new relevant papers. `relevance_filter` grades hits before
download (keyword in deterministic mode, LLM in full mode): `lenient` (default)
keeps anything topically about the material/reaction and keeps borderline papers
(surface details are usually only in the full text); `strict` requires
surface-evidence signals; `off` keeps every paper.

### Embeddings

Embeddings auto-select OpenAI `text-embedding-3-small` when
`OPENAI_EMBEDDING_KEY` is present, otherwise a local sentence-transformers
model. The local model needs the optional extra:

```bash
uv sync --extra local-embeddings
```

For an Anthropic-only or `openai-oauth` setup without an OpenAI embedding key,
either install that extra or set `paperqa.embedding` explicitly, e.g.
`st-multi-qa-MiniLM-L6-cos-v1`.

## Outputs added in full mode

- `report.md`: the citation-grounded surface-modeling proposal.
- `validated_claims` in `run_manifest.json`: each claim plus its PaperQA
  `validation`.
- `opportunity_report.llm_ranking`: the LLM-refined surface ranking.
- `llm_cache.db`, `paperqa/`: response cache and persisted PaperQA index.

See [Outputs](outputs.md) for details.
