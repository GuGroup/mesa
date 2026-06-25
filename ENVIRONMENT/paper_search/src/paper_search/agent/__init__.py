"""LangGraph orchestration layer over the deterministic paper-search pipeline.

The deterministic retrieval/parsing/extraction modules are reused unchanged as
node tool-functions. When ``llm.provider == none`` (or no API key is present) the
LLM/PaperQA nodes degrade to the existing rule-based behavior, reproducing the
original pipeline output.
"""

from typing import Any

__all__ = ["CatalystLiteratureGraph"]


def __getattr__(name: str) -> Any:
    # Lazy import so ``graph`` (which imports the agent submodules) does not
    # trigger a circular import when the package is first loaded.
    if name == "CatalystLiteratureGraph":
        from paper_search.agent.graph import CatalystLiteratureGraph

        return CatalystLiteratureGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
