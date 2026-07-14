# EXTERNAL VENDOR GUIDE

## OVERVIEW

- `paper-search-mcp/` is an upstream-owned, MIT-licensed standalone Python
  project; MESA consumes it as an isolated MCP runtime.
- Snapshot is byte-identical to upstream commit `dba2c7430aec7e17463ad981caf1d391f0204335`.
- Preserve OPENAGS copyright, license, commit provenance, and upstream layout.
- Treat snapshot refreshes as explicit dependency updates, never incidental
  cleanup mixed into MESA feature work.

## WHERE TO LOOK

| Concern | Location |
|---|---|
| Package metadata and entry points | `paper-search-mcp/pyproject.toml` |
| Frozen dependency graph | `paper-search-mcp/uv.lock` |
| MCP tools and stdio entry point | `paper-search-mcp/paper_search_mcp/server.py` |
| User CLI | `paper-search-mcp/paper_search_mcp/cli.py` |
| Source adapter contract | `paper-search-mcp/paper_search_mcp/academic_platforms/base.py` |
| Provider adapters | `paper-search-mcp/paper_search_mcp/academic_platforms/` |
| Offline and live tests | `paper-search-mcp/tests/` |
| MESA runtime declaration | `../DEPENDENCY/runtimes.yaml` |

## CONVENTIONS

- Run all package commands from `EXTERNAL/paper-search-mcp`.
- Use the frozen `uv` runtime for MESA operation: `uv sync --frozen` and
  `uv run --frozen ...`.
- Keep `paper_search_mcp` imports inside this runtime; do not import across the
  MESA environment boundary.
- Refresh only from a named upstream commit. Compare full trees, update the
  lock and source snapshot together, and record old/new commit IDs.
- After a refresh, verify license/provenance, console entry points, MCP startup,
  offline tests, and any deliberately selected live providers.
- Separate offline mocked/unit coverage from provider integration coverage in
  validation reports.

## ANTI-PATTERNS

- Do not patch files in `paper-search-mcp/` ad hoc. Carry a MESA-specific change
  outside the snapshot or make an explicit, documented vendor fork decision.
- Do not regenerate `uv.lock`, reformat source, or upgrade dependencies during
  unrelated work; each breaks byte-identical provenance.
- Do not run the whole test directory assuming it is offline. Provider tests,
  `functional_test.py`, `e2e_test.py`, and PDF paths perform network or file I/O.
- Do not accept upstream publish CI as proof of correctness: its pytest command
  masks failures with `|| echo`, producing false-green runs.
- Do not use the unqualified `paper-search` or `paper-search-mcp` executable
  from an unknown environment. `ENVIRONMENT/paper_search` exposes the same
  command names; cwd and runtime select different products.
- Do not commit `.env`, downloaded PDFs, `.venv/`, or `__pycache__/` artifacts.

## COMMANDS

```bash
cd EXTERNAL/paper-search-mcp
uv sync --frozen
uv run --frozen python -c "import paper_search_mcp; print('paper-search-mcp ok')"
uv run --frozen -m paper_search_mcp.server
uv run --frozen paper-search sources

# Offline-safe focused regression set; expand only after inspecting each module.
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python -m unittest -v \
  tests.test_config_env tests.test_fallback tests.test_unpaywall \
  tests.test_unpaywall_source tests.test_acm tests.test_ieee tests.test_ssrn

# Live integration: opt-in, network/API availability and downloads expected.
uv run --frozen python tests/functional_test.py
uv run --frozen python tests/e2e_test.py
```
