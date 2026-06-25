"""MCP server exposing the catalyst literature agent as a tool.

Optional: install with the ``mcp`` extra (``uv sync --extra mcp``) and run

    uv run --extra mcp paper-search-mcp

This module imports ``mcp`` lazily so the package stays importable without the
extra installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_server() -> Any:
    from mcp.server.fastmcp import FastMCP

    from paper_search.config import PipelineConfig, resolve_output_dir
    from paper_search.pipeline import LiteraturePipeline

    server = FastMCP("paper-search")

    @server.tool()
    def propose_surface_models(
        material: str,
        reaction: str,
        prompt: str | None = None,
        provider: str = "none",
        model: str | None = None,
        out_dir: str | None = None,
    ) -> dict[str, Any]:
        """Run the full-text literature agent and return a surface-modeling proposal.

        Args:
            material: target material (e.g. "RuO2").
            reaction: target reaction/application (e.g. "HER").
            prompt: optional research direction to steer the agent.
            provider: "none" | "anthropic" | "openai" | "openai-oauth".
            model: optional chat model id override.
            out_dir: output directory (defaults to a session under ~/.SearchAgent).
        """
        out = resolve_output_dir(Path(out_dir) if out_dir else None, material, reaction)
        config = PipelineConfig.from_sources(
            output_dir=out,
            llm_provider=None if provider == "none" else provider,
            llm_model=model,
            research_prompt=prompt,
            cwd=Path.cwd(),
        )
        result = LiteraturePipeline(config).run(material=material, reaction=reaction)
        return {
            "mode": result.get("mode"),
            "rounds": result.get("rounds"),
            "paper_count": result.get("paper_count"),
            "surface_claim_count": result.get("surface_claim_count"),
            "opportunity_report": result.get("opportunity_report"),
            "report_markdown": result.get("report_markdown"),
            "out_dir": str(out),
        }

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
