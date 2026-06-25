from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Paper:
    paper_id: str
    title: str
    doi: str | None = None
    year: int | None = None
    journal: str | None = None
    publisher: str | None = None
    url: str | None = None
    abstract: str | None = None
    source_databases: list[str] = field(default_factory=list)
    relevance_score: float | None = None
    authors: list[str] = field(default_factory=list)
    publication_type: str | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    citation_count: int | None = None
    influential_citation_count: int | None = None
    is_open_access: bool | None = None
    oa_url: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceLink:
    url: str
    source_type: str
    resolver: str
    license: str | None = None
    content_type: str | None = None
    version: str | None = None
    host_type: str | None = None
    evidence: str | None = None
    is_best: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DownloadedSource:
    paper_id: str
    source_type: str
    resolver: str
    source_url: str
    local_path: Path
    checksum: str
    license: str | None = None
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["local_path"] = str(self.local_path)
        return data


@dataclass(slots=True)
class ParseRun:
    paper_id: str
    parser_name: str
    output_format: str
    output_path: Path
    status: str
    parse_quality: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_path"] = str(self.output_path)
        return data


@dataclass(slots=True)
class DocumentBlock:
    paper_id: str
    parse_id: str
    block_type: str
    text: str
    section: str | None = None
    page: int | None = None
    figure_or_table: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SurfaceClaim:
    """A surface-catalysis evidence claim.

    Originally scoped to a facet of the target material/reaction; now generalized
    to capture field-level evidence (a different metal/surface under the same
    reaction is still useful for descriptor/method transfer). The original fields
    are unchanged; the trailing optional fields broaden the schema:

    - ``system``: the actual catalyst the claim is about (may differ from the
      target ``material``), e.g. "Pt(111)", "Ru-RuO2", "Co3O4".
    - ``descriptor``: controlled-vocabulary descriptor studied (DESCRIPTOR_TYPES),
      e.g. "dG_H", "d_band_center", "overpotential".
    - ``method``: controlled-vocabulary calculation/approach (METHOD_TYPES),
      e.g. "dft_che", "neb_ts", "pourbaix".
    - ``claim``: a one-sentence statement of what the paper argues.
    - ``relation_to_target``: how this claim relates to the run target
      ("same_material" | "same_reaction" | "both" | "analogous").
    """

    paper_id: str
    material: str
    reaction: str
    surface_text: str
    evidence_text: str
    claim_type: str
    section: str | None = None
    figure_or_table: str | None = None
    confidence: float = 0.5
    value: str | None = None
    unit: str | None = None
    system: str | None = None
    descriptor: str | None = None
    method: str | None = None
    claim: str | None = None
    relation_to_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# The broadened schema is conceptually a catalysis claim, not strictly a surface
# claim; alias kept so callers can use the clearer name.
CatalysisClaim = SurfaceClaim
