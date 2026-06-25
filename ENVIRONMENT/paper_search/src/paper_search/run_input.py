from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, ListConfig, OmegaConf

from paper_search.config import ResearchConfig


@dataclass(slots=True)
class RunInput:
    material: str | None = None
    reaction: str | None = None
    extra_terms: list[str] = field(default_factory=list)
    research: ResearchConfig = field(default_factory=ResearchConfig)


def load_run_input(path: Path) -> RunInput:
    data = OmegaConf.load(path)
    if not isinstance(data, DictConfig):
        raise TypeError("Run input YAML must contain a mapping.")
    return RunInput(
        material=_optional_text(_select(data, "material", "input.material")),
        reaction=_optional_text(_select(data, "reaction", "input.reaction")),
        extra_terms=_text_list(_select(data, "extra_terms", "input.extra_terms")),
        research=_research_config(data),
    )


def _research_config(data: DictConfig) -> ResearchConfig:
    return ResearchConfig(
        prompt=_optional_text(_select(data, "prompt", "research.prompt", "research_context.prompt")),
        collaboration_context=_optional_text(
            _select(
                data,
                "collaboration_context",
                "research.collaboration_context",
                "research_context.collaboration_context",
            )
        ),
        decision_criteria=_text_list(
            _select(data, "decision_criteria", "research.decision_criteria")
        ),
        target_properties=_text_list(
            _select(data, "target_properties", "research.target_properties")
        ),
        constraints=_text_list(_select(data, "constraints", "research.constraints")),
        calculation_preferences=_text_list(
            _select(data, "calculation_preferences", "research.calculation_preferences")
        ),
    )


def _select(data: DictConfig, *keys: str) -> Any | None:
    for key in keys:
        value = OmegaConf.select(data, key, default=None)
        if value is not None:
            return value
    return None


def _optional_text(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_list(value: Any | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple | ListConfig):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
