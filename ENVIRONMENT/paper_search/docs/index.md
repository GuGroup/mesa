# MESA Paper Search

`paper-search` is the MESA-owned literature agent for catalyst and
surface-modeling decisions. It combines full-text retrieval, parsing, evidence
extraction, claim validation, gap analysis, and calculation-oriented reporting
in an eleven-node LangGraph workflow.

## Execution modes

- Deterministic mode requires no LLM key and uses rule-based query planning,
  relevance filtering, evidence extraction, and reporting.
- Full agent mode adds LLM query expansion, relevance grading, structured
  extraction, PaperQA validation, gap ranking, and report generation.

## Run

From `ENVIRONMENT/paper_search`:

```bash
uv run --frozen paper-search run \
  --material RuO2 \
  --reaction HER \
  --out ../../project/<project_name>/paper_search/ruo2-her
```

See the package `README.md` for configuration precedence, providers, parsers,
artifact layout, full-text policy, and LangGraph Studio usage.
