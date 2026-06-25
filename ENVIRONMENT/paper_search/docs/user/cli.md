# CLI usage

The single entry point is `paper-search run`. It builds and runs the
`CatalystLiteratureGraph`; with no provider configured it runs deterministically.

```bash
uv run paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her
```

## Options

| Flag | Description |
| --- | --- |
| `--material` | Target material (required). |
| `--reaction` | Target reaction / application (required). |
| `--out` | Output directory. Optional — defaults to a session folder under `~/.SearchAgent` (see [Setup → Storage layout](../admin/setup.md#storage-layout)). |
| `--session` | Reuse a named session folder under the base (for resume); ignored when `--out` is given. |
| `--config` | YAML/OmegaConf config file. Defaults to `./config.yaml` when present. |
| `--email` | Email for polite OpenAlex/Crossref/Unpaywall use. |
| `--limit` | Per-query search limit. |
| `--max-papers` | Cap on deduplicated papers processed. |
| `--timeout` | HTTP timeout in seconds. |
| `--prompt` | Research direction / decision question. |
| `--prompt-file` | Text/Markdown file with detailed research context. |
| `--provider` | `none` (default) / `anthropic` / `openai` / `openai-oauth`. See [Full agent mode](full-agent.md). |
| `--model` | Override the chat model id for the selected provider. |
| `--extra-term` | Additional query term (repeatable). |
| `--no-resume` | Ignore cached artifacts and recompute where possible. |
| `--grobid-url`, `--grobid-start-cmd`, `--opendataloader-cmd` | Parser overrides (see [Setup](../admin/setup.md)). |

CLI values override `config.yaml`; see the priority order in
[Setup & configuration](../admin/setup.md).

## Output

On completion the run prints the mode, paper/claim counts, and artifact paths:

```text
mode=deterministic
papers=12
surface_claims=23
manifest=data/runs/ruo2-her/run_manifest.json
```

In full mode a `report=...report.md` line is also printed. See
[Outputs](outputs.md) for the artifact reference.

## Resume

Runs are resumable by default. When `resume` is enabled, SearchAgent reuses
existing successful artifacts (`papers.json`, resolved links, downloaded source,
successful parse blocks, per-paper `surface_claims.json`, and — in full mode —
the PaperQA index). Failed or incomplete stages are retried, and a per-paper
failure is recorded without stopping the run. Use `--no-resume` to force
recomputation. Details in [Setup & configuration](../admin/setup.md#retry-and-resume).
