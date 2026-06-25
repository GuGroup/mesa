# SearchAgent

SearchAgent is a full-text literature **agent** for catalyst / material surface
modeling. Given a research prompt it retrieves papers, resolves usable full text
with open-access/TDM sources first and a configurable Sci-Hub fallback, studies
them with an LLM and PaperQA2, validates the evidence against its citations,
finds data gaps, and proposes surface-modeling calculations to run next.

It is orchestrated as a LangGraph `StateGraph` of nine nodes and runs in two
modes, selected by `llm.provider`:

| Mode | Requires | What it does |
| --- | --- | --- |
| Deterministic (default) | no API keys | rule-based query planning, regex surface-claim extraction, rule-based opportunity report |
| Full agent | `anthropic` / `openai` key or `openai-oauth` proxy | LLM query expansion + sub-questions, relevance grading, **iterative gap-driven re-search**, PaperQA2 agentic evidence + citation-grounded validation, LLM gap ranking, citation-grounded `report.md` |

## Where to start

| Role | Doc |
| --- | --- |
| First run, minimal flow | [Quickstart](quickstart.md) |
| Run from the command line | [CLI usage](user/cli.md) |
| Turn on the LLM + PaperQA agent | [Full agent mode](user/full-agent.md) |
| Steer the agent with a prompt | [Writing the research prompt](user/research-prompt.md) |
| Read and interpret results | [Outputs](user/outputs.md) |
| Inspect the graph visually | [LangGraph Studio](user/studio.md) |
| Understand the architecture | [Agent graph](architecture/agent-graph.md) |
| Install and configure the tool | [Setup & configuration](admin/setup.md) |
| Develop and run tests | [Development](admin/development.md) |
| Deploy the documentation site | [Deployment](admin/deployment.md) |

If you are just trying it for the first time, follow the
[Quickstart](quickstart.md).

## Core policy

- Primary full-text sources first: Unpaywall OA locations, Crossref TDM links,
  and configured publisher APIs such as Elsevier.
- Sci-Hub fallback is enabled by default and is queried only after primary
  sources leave a paper without usable full text.
- No publisher scraping, user-uploaded PDFs, or abstract-only evidence
  extraction.
