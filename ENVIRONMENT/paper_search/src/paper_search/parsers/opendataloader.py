from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from paper_search.models import ParseRun
from paper_search.parsers.xml_blocks import blocks_to_dicts, markdown_to_blocks
from paper_search.utils import write_json


class OpenDataLoaderParser:
    name = "opendataloader"

    def __init__(self, command_template: str | None = None, timeout: int = 300) -> None:
        self.command_template = command_template
        self.timeout = timeout

    def parse(self, paper_id: str, source_path: Path, output_dir: Path) -> ParseRun:
        output_dir.mkdir(parents=True, exist_ok=True)
        odl_dir = output_dir / "opendataloader"
        blocks_path = output_dir / "opendataloader.blocks.json"
        odl_dir.mkdir(parents=True, exist_ok=True)
        api_error = self._run_python_api(source_path, odl_dir)
        if api_error is None:
            api_run = self._collect_outputs(paper_id, odl_dir, blocks_path)
            if api_run:
                return api_run
            api_error = "Python API completed but no .md or .json output was found."
            if not self.command_template:
                return ParseRun(
                    paper_id=paper_id,
                    parser_name=self.name,
                    output_format="markdown_or_json",
                    output_path=blocks_path,
                    status="failed",
                    error=api_error,
                )
        if not self.command_template:
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="markdown_or_json",
                output_path=blocks_path,
                status="not_configured",
                error=(
                    "OpenDataLoader Python API failed and no CLI fallback command "
                    "is configured. Set PAPER_SEARCH_OPENDATALOADER_CMD with "
                    f"{{input}} and {{output_dir}} placeholders. Python API error: {api_error}"
                ),
            )
        command = self.command_template.format(
            input=str(source_path),
            output_dir=str(odl_dir),
        )
        try:
            result = subprocess.run(
                shlex.split(command),
                cwd=odl_dir,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="markdown_or_json",
                output_path=blocks_path,
                status="failed",
                error=str(exc),
            )
        write_json(
            output_dir / "opendataloader.run.json",
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            },
        )
        if result.returncode != 0:
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="markdown_or_json",
                output_path=blocks_path,
                status="failed",
                error=f"OpenDataLoader exited with code {result.returncode}",
            )
        fallback_run = self._collect_outputs(paper_id, odl_dir, blocks_path)
        if fallback_run:
            fallback_run.parse_quality["execution"] = "command_fallback"
            return fallback_run
        return ParseRun(
            paper_id=paper_id,
            parser_name=self.name,
            output_format="markdown_or_json",
            output_path=blocks_path,
            status="failed",
            error="OpenDataLoader completed but no .md or .json output was found.",
        )

    def _run_python_api(self, source_path: Path, output_dir: Path) -> str | None:
        try:
            import opendataloader_pdf  # type: ignore[import-not-found]
        except ImportError as exc:
            return str(exc)
        try:
            opendataloader_pdf.convert(
                input_path=str(source_path),
                output_dir=str(output_dir),
                format="json,markdown",
            )
        except TypeError:
            try:
                opendataloader_pdf.convert(
                    input_path=[str(source_path)],
                    output_dir=str(output_dir),
                    format=["json", "markdown"],
                )
            except Exception as exc:  # pragma: no cover - external package behavior
                return str(exc)
        except Exception as exc:  # pragma: no cover - external package behavior
            return str(exc)
        return None

    def _collect_outputs(
        self,
        paper_id: str,
        odl_dir: Path,
        blocks_path: Path,
    ) -> ParseRun | None:
        markdown = _first_file(odl_dir, ("*.md", "*.markdown"))
        if markdown:
            blocks = markdown_to_blocks(markdown, paper_id, self.name)
            write_json(blocks_path, blocks_to_dicts(blocks))
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="blocks_json",
                output_path=blocks_path,
                status="ok",
                parse_quality={
                    "block_count": len(blocks),
                    "source_markdown": str(markdown),
                    "execution": "python_api",
                },
            )
        json_file = _first_file(odl_dir, ("*.json",))
        if json_file:
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="json",
                output_path=json_file,
                status="ok",
                parse_quality={
                    "json_output": str(json_file),
                    "execution": "python_api",
                },
            )
        return None


def _first_file(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.rglob(pattern))
        if matches:
            return matches[0]
    return None
