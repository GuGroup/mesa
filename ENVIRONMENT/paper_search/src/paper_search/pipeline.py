from __future__ import annotations

from typing import Any, Callable

from paper_search.agent.graph import CatalystLiteratureGraph
from paper_search.config import PipelineConfig

__all__ = ["LiteraturePipeline", "CatalystLiteratureGraph", "PipelineConfig"]


class LiteraturePipeline:
    """Backward-compatible facade over :class:`CatalystLiteratureGraph`.

    Runs deterministically when ``llm.provider == none`` (or no API key is
    present), reproducing the original downloader/parser output; otherwise it
    runs the full LLM + PaperQA agent. The ``run()`` signature and the returned
    manifest dict are unchanged.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.graph = CatalystLiteratureGraph(config)

    def run(
        self,
        material: str,
        reaction: str,
        extra_terms: list[str] | None = None,
        on_node: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return self.graph.run(
            material, reaction, extra_terms=extra_terms, on_node=on_node
        )
