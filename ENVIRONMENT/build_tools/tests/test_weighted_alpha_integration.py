from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import cast

import pytest
from ase import Atoms
from ase.io import read

from slabuilder.weighted_alpha_backend import (
    WeightedAlphaConfig,
    run_weighted_alpha,
)


INTEGRATION_ENV_KEYS = (
    "MESA_WEIGHTED_ALPHA_INTEGRATION_EXE",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_RADIUS_FILE",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_SLAB",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_SHA256",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_RADIUS_SHA256",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_RUNTIME_SHA256_MANIFEST",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_RUNTIME_MANIFEST_SHA256",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_RELEASE",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_MESA_BASE_COMMIT",
    "MESA_WEIGHTED_ALPHA_INTEGRATION_PRIVATE_SOURCE_MANIFEST_SHA256",
)
MISSING_INTEGRATION_ENV = tuple(
    key for key in INTEGRATION_ENV_KEYS if not os.environ.get(key)
)


def _candidate_semantic_sha256(result: object) -> str:
    candidates = getattr(result, "candidates")
    payload = [
        {
            "id": candidate.engine_node_id,
            "kind": candidate.site_kind,
            "coord": candidate.coordination,
            "subtype": candidate.hollow_subtype,
            "position": [round(float(value), 10) for value in candidate.position],
            "normal": [round(float(value), 10) for value in candidate.normal],
            "sources": list(candidate.source_atom_indices),
        }
        for candidate in candidates
    ]
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.mark.skipif(
    bool(MISSING_INTEGRATION_ENV),
    reason="missing real C++ integration variables: "
    + ", ".join(MISSING_INTEGRATION_ENV),
)
def test_real_ytk_graph_to_filtered_candidates(tmp_path: Path) -> None:
    executable = Path(os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_EXE"])
    radius_file = Path(os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_RADIUS_FILE"])
    slab_path = Path(os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_SLAB"])
    expected_hash = os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_SHA256"]
    expected_radius_hash = os.environ[
        "MESA_WEIGHTED_ALPHA_INTEGRATION_RADIUS_SHA256"
    ]
    runtime_manifest = Path(
        os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_RUNTIME_SHA256_MANIFEST"]
    )
    expected_runtime_manifest_hash = os.environ[
        "MESA_WEIGHTED_ALPHA_INTEGRATION_RUNTIME_MANIFEST_SHA256"
    ]
    release = os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_RELEASE"]
    mesa_base_commit = os.environ["MESA_WEIGHTED_ALPHA_INTEGRATION_MESA_BASE_COMMIT"]
    private_source_manifest_sha256 = os.environ[
        "MESA_WEIGHTED_ALPHA_INTEGRATION_PRIVATE_SOURCE_MANIFEST_SHA256"
    ]

    slab = cast(Atoms, read(slab_path))
    slab.pbc = [True, True, False]
    config = WeightedAlphaConfig(
        executable=executable,
        radius_file=radius_file,
        probe_radius=1.52,
        expected_sha256=expected_hash,
        expected_radius_sha256=expected_radius_hash,
        runtime_sha256_manifest=runtime_manifest,
        expected_runtime_manifest_sha256=expected_runtime_manifest_hash,
        first_party_release=release,
        mesa_base_commit=mesa_base_commit,
        private_source_manifest_sha256=private_source_manifest_sha256,
        timeout_s=120.0,
    )
    assert config.alpha_factor == 3.5
    result = run_weighted_alpha(
        slab,
        config,
        workdir=tmp_path / "engine_run",
    )
    repeated = run_weighted_alpha(
        slab,
        config,
        workdir=tmp_path / "engine_run_repeated",
    )

    assert result.provenance["executable_sha256"] == expected_hash
    assert result.provenance["radius_file_sha256"] == expected_radius_hash
    assert result.provenance["runtime_artifacts_pinned"] is True
    assert result.provenance["runtime_staged_private"] is True
    assert Path(result.provenance["executed_executable"]).parent.name == ".weighted_alpha_runtime"
    assert result.provenance["expected_runtime_manifest_sha256"] == expected_runtime_manifest_hash
    assert result.provenance["runtime_sha256_manifest_hash"] == expected_runtime_manifest_hash
    assert result.provenance["first_party_release"] == release
    assert result.provenance["mesa_base_commit"] == mesa_base_commit
    assert result.provenance["private_source_manifest_sha256"] == (
        private_source_manifest_sha256
    )
    assert len(result.provenance["staged_input_sha256"]) == 64
    assert result.graph["metadata"]["staged_input_sha256"] == result.provenance["staged_input_sha256"]
    assert result.provenance["engine_to_ase_index"]
    assert result.provenance["ase_to_engine_index"]
    assert result.provenance["backend"] == "weighted_alpha"
    assert result.graph["metadata"]["pbc"] == [True, True, False]
    assert result.graph["metadata"]["alpha_parameter"] == 3.5
    assert result.graph["metadata"]["probe_radius_alpha_consistency_warning"] == (
        "physical probe radius not supplied; weighted-alpha geometry construction "
        "uses --alpha-factor and placement uses -a as contact-anchor radius"
    )
    assert len(result.graph["nodes"]) == 1379
    assert len(result.graph["edges"]) == 5752
    assert len(result.candidates) == 26
    assert {kind: sum(c.site_kind == kind for c in result.candidates) for kind in ("top", "bridge", "hollow")} == {
        "top": 6,
        "bridge": 12,
        "hollow": 8,
    }
    assert result.provenance["graph_sha256"] == (
        "076a4399dad6e01765bc4b9fb6ce422babd3b791aff38bbc6b3c7f18cc2ca8a4"
    )
    assert repeated.provenance["graph_sha256"] == result.provenance["graph_sha256"]
    assert _candidate_semantic_sha256(result) == (
        "6f4d9a27af9fd5f35fc9b4fc40e840382f724deb38cd7b278ae1b71abd6e722a"
    )
    assert _candidate_semantic_sha256(repeated) == _candidate_semantic_sha256(result)
    assert result.candidates
    assert all(
        candidate.metadata["placement"]["target_clearance_reached"] is True
        and candidate.metadata["placement"]["status"] == "target_clearance_reached"
        and candidate.metadata["placement"]["clearance_at_position"]
        >= candidate.metadata["placement"]["target_clearance"]
        for candidate in result.candidates
    )
    assert all(
        0 <= index < len(slab)
        for candidate in result.candidates
        for index in candidate.source_atom_indices
    )
    assert all(
        candidate.metadata.get("topology_valid_for_benchmark") is True
        and not candidate.metadata.get("benchmark_blocking")
        for candidate in result.candidates
        if candidate.site_kind == "hollow"
    )
