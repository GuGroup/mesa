"""LangGraph Studio / ``langgraph dev`` entrypoint.

Studio needs to *import* a graph, but the nodes are bound to a runtime
``AgentServices`` instance. This factory builds those services from config
(``./config.yaml`` + ``.env``) and returns the compiled graph. No checkpointer
is attached here — the dev server provides its own persistence.

Run (``--allow-blocking`` is required because this pipeline is synchronous; the
dev server's blockbuster otherwise rejects blocking I/O on the event loop):

    uv run --extra studio langgraph dev --allow-blocking

then open the printed Studio URL. Provide the initial state as JSON, e.g.::

    {"material": "RuO2", "reaction": "HER", "extra_terms": [],
     "research_context": {}, "harness_errors": [], "resume_events": []}

Set ``PAPER_SEARCH_PROVIDER=openai``, ``anthropic``, or ``openai-oauth`` in
``.env`` to run the full agent in Studio; otherwise it runs in deterministic
mode.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from paper_search.agent.graph import CatalystLiteratureGraph
from paper_search.agent.services import AgentServices
from paper_search.config import PipelineConfig, base_dir


def _project_root() -> Path:
    """Stable project dir for config/.env discovery.

    The dev server may invoke this factory from an arbitrary (or stale) working
    directory, so never rely on ``os.getcwd()`` here.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "langgraph.json").exists() or (parent / "pyproject.toml").exists():
            return parent
    return here.parents[3]


def make_graph() -> Any:
    root = _project_root()
    env_out = os.environ.get("PAPER_SEARCH_OUT")
    out = Path(env_out) if env_out else base_dir() / "sessions" / "studio"
    config = PipelineConfig.from_sources(
        output_dir=out,
        llm_provider=os.environ.get("PAPER_SEARCH_PROVIDER"),
        llm_model=os.environ.get("PAPER_SEARCH_MODEL"),
        cwd=root,
    )
    services = AgentServices.create(config)
    return CatalystLiteratureGraph(config).build(services)
