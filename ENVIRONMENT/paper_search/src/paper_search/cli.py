from __future__ import annotations

import argparse
import collections
import sys
import time
from pathlib import Path
from typing import Any, Callable

from paper_search.config import resolve_output_dir
from paper_search.pipeline import LiteraturePipeline, PipelineConfig
from paper_search.run_input import RunInput, load_run_input


def _progress_reporter() -> Callable[[str, dict[str, Any]], None]:
    """Print one concise stderr line per completed graph node.

    The pipeline is otherwise silent for minutes while it downloads, parses,
    and runs PaperQA; this makes a long run legible without touching the stdout
    summary contract the tests assert on.
    """
    start = time.monotonic()

    def report(node: str, delta: dict[str, Any]) -> None:
        detail = ""
        if "papers" in delta:
            detail = f"{len(delta['papers'])} papers"
        elif "graded" in delta:
            kept = sum(1 for v in delta["graded"].values() if v)
            detail = f"{kept}/{len(delta['graded'])} kept"
        elif "processed" in delta:
            tally = collections.Counter(r.get("status") for r in delta["processed"])
            detail = ", ".join(f"{v} {k}" for k, v in tally.most_common())
        elif "coverage" in delta:
            cov = delta["coverage"] or {}
            detail = "gaps remain" if cov.get("has_gaps") else "coverage complete"
        elif "surface_claims" in delta:
            detail = f"{len(delta['surface_claims'])} claims"
        elapsed = time.monotonic() - start
        line = f"[{elapsed:6.1f}s] {node}"
        if detail:
            line += f" — {detail}"
        print(line, file=sys.stderr, flush=True)

    return report


def _research_prompt(
    input_prompt: str | None, prompt: str | None, prompt_file: Path | None
) -> str | None:
    parts = []
    if input_prompt:
        parts.append(input_prompt.strip())
    if prompt_file is not None:
        parts.append(prompt_file.read_text(encoding="utf-8").strip())
    if prompt:
        parts.append(prompt.strip())
    text = "\n\n".join(part for part in parts if part)
    return text or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paper-search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run full-text literature pipeline.")
    run_parser.add_argument("--material")
    run_parser.add_argument("--reaction")
    run_parser.add_argument(
        "--input",
        type=Path,
        help="YAML run input with material, reaction, extra_terms, and research fields.",
    )
    run_parser.add_argument(
        "--out",
        type=Path,
        help="Output directory. Defaults to "
        "~/.SearchAgent/sessions/<material>_<reaction>_<timestamp> "
        "($SEARCHAGENT_HOME overrides the base).",
    )
    run_parser.add_argument(
        "--session",
        help="Reuse a named session folder under the base (for resume). "
        "Ignored when --out is given.",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        help="YAML/OmegaConf config file. Defaults to ./config.yaml when present.",
    )
    run_parser.add_argument("--email", help="Email for polite OpenAlex/Crossref/Unpaywall API use.")
    run_parser.add_argument("--limit", type=int, help="Per-query search limit.")
    run_parser.add_argument("--max-papers", type=int)
    run_parser.add_argument("--timeout", type=int, help="HTTP timeout in seconds.")
    run_parser.add_argument(
        "--prompt",
        help="Research direction, collaboration context, or decision question.",
    )
    run_parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Text/Markdown file with detailed research context.",
    )
    run_parser.add_argument(
        "--provider",
        choices=["none", "anthropic", "openai", "openai-oauth", "openai_oauth"],
        help="LLM provider. 'none' (default) runs deterministic rule-based mode; "
        "'anthropic'/'openai'/'openai-oauth' enable the full PaperQA + LLM agent.",
    )
    run_parser.add_argument(
        "--model",
        help="Override the chat model id for the selected provider.",
    )
    run_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore cached run artifacts and recompute stages where possible.",
    )
    run_parser.add_argument(
        "--grobid-url",
        help="Optional GROBID base URL for PDF parsing.",
    )
    run_parser.add_argument(
        "--grobid-start-cmd",
        help="Optional command to start a GROBID-compatible server.",
    )
    run_parser.add_argument(
        "--opendataloader-cmd",
        help="Override the default OpenDataLoader CLI fallback with {input} and {output_dir}.",
    )
    run_parser.add_argument(
        "--extra-term",
        action="append",
        default=[],
        help="Additional query term. Can be repeated.",
    )
    run_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-node progress output on stderr.",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        run_input = load_run_input(args.input) if args.input else RunInput()
        material = args.material or run_input.material
        reaction = args.reaction or run_input.reaction
        if not material or not reaction:
            run_parser.error("--material and --reaction are required unless provided by --input YAML")
        extra_terms = [*run_input.extra_terms, *args.extra_term]
        output_dir = resolve_output_dir(
            args.out, material, reaction, args.session
        )
        research_prompt = _research_prompt(
            run_input.research.prompt, args.prompt, args.prompt_file
        )
        config = PipelineConfig.from_sources(
            output_dir=output_dir,
            config_path=args.config,
            email=args.email,
            grobid_url=args.grobid_url,
            grobid_start_cmd=args.grobid_start_cmd,
            opendataloader_cmd=args.opendataloader_cmd,
            per_query_limit=args.limit,
            max_papers=args.max_papers,
            timeout=args.timeout,
            research=run_input.research,
            research_prompt=research_prompt,
            resume=False if args.no_resume else None,
            llm_provider=args.provider,
            llm_model=args.model,
        )
        result = LiteraturePipeline(config).run(
            material=material,
            reaction=reaction,
            extra_terms=extra_terms,
            on_node=None if args.quiet else _progress_reporter(),
        )
        print(f"mode={result.get('mode', 'deterministic')}")
        print(f"out={output_dir}")
        print(f"papers={result['paper_count']}")
        print(f"surface_claims={result['surface_claim_count']}")
        print(f"manifest={output_dir / 'run_manifest.json'}")
        if result.get("report_markdown"):
            print(f"report={output_dir / 'report.md'}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
