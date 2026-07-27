from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.io import read

import slabuilder.weighted_alpha_backend as weighted_backend
from slabuilder.weighted_alpha_backend import (
    WeightedAlphaCandidate,
    WeightedAlphaConfig,
    WeightedAlphaConfigError,
    WeightedAlphaExecutionError,
    WeightedAlphaSchemaError,
    aggregate_fourfold_hollows,
    build_engine_command,
    deduplicate_candidates,
    extract_candidates,
    load_graph,
    resolve_weighted_alpha_config,
    run_weighted_alpha,
    stage_slab_for_engine,
    validate_graph,
)


def _write(path: Path, text: str = "payload") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _config(tmp_path: Path, **changes: object) -> WeightedAlphaConfig:
    exe = _write(tmp_path / "weighted_alpha_complex.exe", "exe")
    radius = _write(tmp_path / "UFF.rad", "radius")
    values: dict[str, object] = {
        "executable": exe,
        "radius_file": radius,
        "alpha_factor": 1.0,
        "probe_radius": 1.52,
        "timeout_s": 30.0,
        "expected_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "expected_radius_sha256": hashlib.sha256(radius.read_bytes()).hexdigest(),
    }
    values.update(changes)
    return WeightedAlphaConfig(**values)


def _slab() -> Atoms:
    # Original ASE order is deliberately interleaved by element and layer.
    return Atoms(
        symbols=["Pt", "Ni", "Pt", "Ni", "Pt", "Ni"],
        positions=[
            [0.0, 0.0, 1.0],
            [2.5, 0.0, 1.0],
            [0.0, 2.5, 1.0],
            [0.0, 0.0, 5.0],
            [2.5, 0.0, 5.0],
            [0.0, 2.5, 5.0],
        ],
        cell=[[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]],
        pbc=[True, True, False],
    )


def _semantic_node(
    node_id: str,
    node_type: str,
    atoms: list[int],
    position: list[float],
    *,
    classification: str | None = None,
    topology_valid: bool = True,
    blocking: bool = False,
    normal: list[float] | None = None,
) -> dict[str, object]:
    coordination = {"P0": 1, "P1": 2, "P2": 3}[node_type]
    node: dict[str, object] = {
        "id": node_id,
        "type": node_type,
        "classification": classification or ("atom" if node_type == "P0" else "regular"),
        "atoms": atoms,
        "position": position,
        "site_kind": {1: "top", 2: "bridge", 3: "hollow"}[coordination],
        "coordination": coordination,
        "hollow_subtype": "fcc" if node_type == "P2" else None,
        "subsurface_ref_dist": 1.0 if node_type == "P2" else None,
    }
    if node_type == "P2":
        node.update(
            {
                "atoms_with_images": [
                    {"atom_id": index, "image_offset": [0, 0, 0]}
                    for index in (atoms if atoms else [0, 1, 2])
                ],
                "normal": normal or [0.0, 0.0, 1.0],
                "has_normal": True,
                "topology_valid_for_benchmark": topology_valid,
                "benchmark_blocking": blocking,
            }
        )
    else:
        node.update(
            {
                "surface_normal": normal or [0.0, 0.0, 1.0],
                "has_surface_normal": True,
            }
        )
    placement_direction = normal or [0.0, 0.0, 1.0]
    node["placement"] = {
        "anchor_position": list(position),
        "direction": list(placement_direction),
        "position": [
            position[index] + 2.02 * placement_direction[index]
            for index in range(3)
        ],
        "distance": 2.02,
        "clearance_at_position": 2.02,
        "target_clearance": 2.02,
        "precursor_radius": 1.52,
        "gap": 0.5,
        "target_clearance_reached": True,
        "distance_type": "ray_clearance",
        "status": "target_clearance_reached",
    }
    return node


def _graph(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "directed": False,
        "multigraph": False,
        "graph_type": "undirected_hierarchical",
        "nodes": nodes,
        "edges": [],
        "metadata": {
            "pbc": [True, True, False],
            "requested_construction_mode": "pbc_masked_image_aware",
            "voro_construction_mode": "pbc_masked_image_aware",
            "geometry_schema_version": "pbc_debug_v1",
            "geometry_uses_full_cell_matrix": True,
            "unique_atom_count": 6,
            "cell": [[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]],
            "staged_input_sha256": "0" * 64,
            "placement_precursor_radius": 1.52,
            "placement_gap": 0.5,
            "placement_step": 0.0125,
            "placement_max_distance": 8.0,
        },
    }


def test_resolve_config_uses_first_party_runtime_when_paths_are_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_EXE", raising=False)
    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_RADIUS_FILE", raising=False)
    executable = _write(tmp_path / "weighted_alpha_complex.exe", "exe")
    radius = _write(tmp_path / "atomic_radii_UFF.rad", "radius")
    manifest = _write(
        tmp_path / "runtime_manifest.json",
        '{"schema_version":1,"artifacts":{}}',
    )
    runtime = SimpleNamespace(
        release="weighted-alpha-test-v1",
        mesa_base_commit="a" * 40,
        private_source_manifest_sha256="b" * 64,
        executable=executable,
        radius_file=radius,
        runtime_manifest=manifest,
        expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        expected_radius_sha256=hashlib.sha256(radius.read_bytes()).hexdigest(),
        expected_runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        "slabuilder.weighted_alpha_runtime.resolve_first_party_runtime",
        lambda **_kwargs: runtime,
    )
    config = resolve_weighted_alpha_config(environ={})
    assert config.executable == executable.resolve()
    assert config.radius_file == radius.resolve()
    assert config.runtime_sha256_manifest == manifest.resolve()
    assert config.first_party_release == "weighted-alpha-test-v1"
    assert config.mesa_base_commit == "a" * 40
    assert config.private_source_manifest_sha256 == "b" * 64
    assert config.allow_unpinned_runtime is False


def test_resolve_config_rejects_partial_explicit_path_override(tmp_path: Path) -> None:
    executable = _write(tmp_path / "weighted_alpha_complex.exe", "exe")
    with pytest.raises(WeightedAlphaConfigError, match="RADIUS_FILE"):
        resolve_weighted_alpha_config(environ={"MESA_WEIGHTED_ALPHA_EXE": str(executable)})


def test_resolve_config_checks_sha256(tmp_path: Path) -> None:
    cfg = _config(tmp_path, expected_sha256="0" * 64)
    with pytest.raises(WeightedAlphaConfigError, match="SHA-256"):
        resolve_weighted_alpha_config(cfg)


def test_api_and_environment_defaults_match_documented_values(tmp_path: Path) -> None:
    api = _config(tmp_path)
    env = resolve_weighted_alpha_config(
        environ={
            "MESA_WEIGHTED_ALPHA_EXE": str(api.executable),
            "MESA_WEIGHTED_ALPHA_RADIUS_FILE": str(api.radius_file),
            "MESA_WEIGHTED_ALPHA_EXPECTED_SHA256": api.expected_sha256,
            "MESA_WEIGHTED_ALPHA_EXPECTED_RADIUS_SHA256": api.expected_radius_sha256,
        }
    )
    for config in (WeightedAlphaConfig(api.executable, api.radius_file), env):
        assert config.alpha_factor == 3.5
        assert config.probe_radius == 1.52
        assert config.placement_gap == 0.5
        assert config.placement_step == 0.0125
        assert config.placement_max_distance == 8.0
        assert config.timeout_s == 120.0


@pytest.mark.parametrize(
    "field",
    [
        "alpha_factor",
        "probe_radius",
        "placement_gap",
        "placement_step",
        "placement_max_distance",
        "timeout_s",
    ],
)
def test_resolve_config_rejects_nonfinite_numbers(tmp_path: Path, field: str) -> None:
    cfg = _config(tmp_path, **{field: float("nan")})
    with pytest.raises(WeightedAlphaConfigError, match=f"{field} must be a finite number"):
        resolve_weighted_alpha_config(cfg)


def test_stage_poscar_groups_elements_and_returns_bijection(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    reread = read(staged.path)

    assert tuple(staged.engine_to_ase_index) == (0, 2, 4, 1, 3, 5)
    assert tuple(staged.ase_to_engine_index) == (0, 3, 1, 4, 2, 5)
    assert reread.get_chemical_symbols() == ["Pt", "Pt", "Pt", "Ni", "Ni", "Ni"]
    np.testing.assert_allclose(
        reread.positions,
        slab.positions[list(staged.engine_to_ase_index)],
        atol=1.0e-10,
    )
    np.testing.assert_allclose(reread.cell.array, slab.cell.array, atol=1.0e-10)


def test_stage_rejects_unsupported_pbc_mask(tmp_path: Path) -> None:
    slab = _slab()
    slab.pbc = [True, True, True]
    with pytest.raises(WeightedAlphaConfigError, match=r"\[True, True, False\]"):
        stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")


def test_build_command_uses_contact_anchor_radius_for_short_a(tmp_path: Path) -> None:
    cfg = _config(tmp_path, alpha_factor=1.25, probe_radius=1.52)
    command = build_engine_command(cfg, tmp_path / "slab.POSCAR", "c" * 64)
    assert command[0] == str(cfg.executable)
    assert command[command.index("-a") + 1] == "1.52"
    assert command[command.index("--alpha-factor") + 1] == "1.25"
    assert "--precursor-radius" not in command
    assert command[command.index("--pbc") + 1] == "1,1,0"
    assert "pbc_masked_image_aware" in command
    assert command[command.index("--input-sha256") + 1] == "c" * 64


def test_validate_graph_rejects_wrong_pbc() -> None:
    graph = _graph([_semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])])
    graph["metadata"]["pbc"] = [True, True, True]  # type: ignore[index]
    with pytest.raises(WeightedAlphaSchemaError, match="pbc"):
        validate_graph(graph)


def test_validate_graph_rejects_missing_semantics() -> None:
    node = _semantic_node("p2_0", "P2", [0, 1, 2], [0.0, 0.0, 5.0])
    del node["hollow_subtype"]
    with pytest.raises(WeightedAlphaSchemaError, match="hollow_subtype"):
        validate_graph(_graph([node]))


def test_extract_filters_and_remaps_engine_indices(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    # Engine top indices after species grouping: ASE 4->2, ASE 3->4, ASE 5->5.
    nodes = [
        _semantic_node("p0_top", "P0", [2], [2.5, 0.0, 5.0]),
        _semantic_node("p1_top", "P1", [2, 4], [1.25, 0.0, 5.0]),
        _semantic_node("p2_top", "P2", [2, 4, 5], [0.8, 0.8, 5.0]),
        _semantic_node(
            "p0_bottom", "P0", [0], [0.0, 0.0, 1.0], normal=[0.0, 0.0, -1.0]
        ),
        _semantic_node("p1_irregular", "P1", [2, 4], [1.0, 0.0, 5.0], classification="interior"),
        _semantic_node("p2_invalid", "P2", [2, 4, 5], [1.2, 1.2, 5.0], topology_valid=False),
        _semantic_node("p2_blocked", "P2", [2, 4, 5], [1.4, 1.4, 5.0], blocking=True),
        {"id": "p3_0", "type": "P3", "classification": "regular", "atoms": [0, 1, 2, 3], "position": [0, 0, 2]},
    ]
    candidates = extract_candidates(
        _graph(nodes), staged.atoms, staged.engine_to_ase_index
    )

    assert [candidate.engine_node_id for candidate in candidates] == [
        "p0_top",
        "p1_top",
        "p2_top",
    ]
    assert candidates[0].source_atom_indices == (4,)
    assert candidates[1].source_atom_indices == (4, 3)
    assert candidates[2].source_atom_indices == (4, 3, 5)
    assert [candidate.site_kind for candidate in candidates] == ["top", "bridge", "hollow"]
    assert candidates[2].hollow_subtype == "fcc"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("anchor_position", [0.2, 0.0, 5.0], "anchor_position"),
        ("direction", [0.2, 0.0, 1.0], "direction"),
        ("precursor_radius", 1.6, "precursor_radius"),
        ("position", [0.0, 0.0, 99.0], "position"),
        ("target_clearance", 3.0, "target_clearance"),
    ],
)
def test_extract_rejects_inconsistent_candidate_placement(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    node = _semantic_node("p0_top", "P0", [2], [2.5, 0.0, 5.0])
    placement = node["placement"]
    assert isinstance(placement, dict)
    placement[field] = value
    with pytest.raises(WeightedAlphaSchemaError, match=message):
        extract_candidates(_graph([node]), staged.atoms, staged.engine_to_ase_index)


def test_extract_requires_placement_for_accepted_candidate(tmp_path: Path) -> None:
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    node = _semantic_node("p0_top", "P0", [2], [2.5, 0.0, 5.0])
    node["placement"] = None
    with pytest.raises(WeightedAlphaSchemaError, match="placement"):
        extract_candidates(_graph([node]), staged.atoms, staged.engine_to_ase_index)


def test_extract_accepts_periodic_equivalent_anchor(tmp_path: Path) -> None:
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    node = _semantic_node("p0_top", "P0", [2], [2.5, 0.0, 5.0])
    placement = node["placement"]
    assert isinstance(placement, dict)
    placement["anchor_position"] = [7.5, 0.0, 5.0]
    placement["position"] = [7.5, 0.0, 7.02]
    candidates = extract_candidates(_graph([node]), staged.atoms, staged.engine_to_ase_index)
    assert len(candidates) == 1


def test_extract_rejects_corrupt_nonfinite_normal_as_schema_error(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    nodes = [
        _semantic_node(
            "p0_nan", "P0", [2], [2.5, 0.0, 5.0],
            normal=[0.0, 0.0, float("nan")],
        ),
    ]
    placement = nodes[0]["placement"]
    assert isinstance(placement, dict)
    placement["direction"] = [0.0, 0.0, 1.0]
    placement["position"] = [2.5, 0.0, 7.02]
    with pytest.raises(WeightedAlphaSchemaError, match="surface_normal"):
        extract_candidates(_graph(nodes), staged.atoms, staged.engine_to_ase_index)



def test_extract_filters_inward_normal(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    nodes = [
        _semantic_node(
            "p0_down", "P0", [2], [2.5, 0.0, 5.0], normal=[0.0, 0.0, -1.0]
        ),
    ]
    assert extract_candidates(_graph(nodes), staged.atoms, staged.engine_to_ase_index) == []


def _candidate(node_id: str, x: float, sources: tuple[int, ...] = (0,)) -> WeightedAlphaCandidate:
    return WeightedAlphaCandidate(
        engine_node_id=node_id,
        position=np.asarray([x, 0.0, 5.0]),
        site_kind="top",
        coordination=len(sources),
        hollow_subtype=None,
        source_atom_indices=sources,
        normal=np.asarray([0.0, 0.0, 1.0]),
        metadata={},
    )


def test_periodic_mic_dedup_is_deterministic() -> None:
    slab = _slab()
    candidates = [_candidate("p0_2", 4.9), _candidate("p0_1", 0.1)]
    result = deduplicate_candidates(candidates, slab, tolerance=0.35)
    assert [candidate.engine_node_id for candidate in result] == ["p0_1"]



def test_skew_cell_mic_uses_true_closest_lattice_vector() -> None:
    root3 = np.sqrt(3.0)
    cell = np.asarray([[1.0, 0.0, 0.0], [0.5, root3 / 2.0, 0.0], [0.0, 0.0, 10.0]])
    slab = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=cell, pbc=[True, True, False])
    displaced = np.asarray([0.49, 0.49, 0.0]) @ cell
    expected = np.linalg.norm(np.asarray([0.49, -0.51, 0.0]) @ cell)

    assert weighted_backend._mic_distance(np.zeros(3), displaced, slab) == pytest.approx(expected)
    aligned, shift = weighted_backend._align_periodic_position(np.zeros(3), displaced, slab)
    assert np.linalg.norm(aligned) == pytest.approx(expected)
    assert tuple(shift) in {(0, 1, 0), (1, 0, 0)}


def test_extract_excludes_p2_with_inconsistent_atom_image_identities(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    node = _semantic_node("p2_bad_images", "P2", [2, 4, 5], [1.0, 1.0, 5.0])
    node["atoms_with_images"] = [
        {"atom_id": 0, "image_offset": [0, 0, 0]},
        {"atom_id": 2, "image_offset": [0, 0, 0]},
        {"atom_id": 3, "image_offset": [0, 0, 0]},
    ]
    with pytest.raises(WeightedAlphaSchemaError, match="atom ids must match"):
        extract_candidates(_graph([node]), staged.atoms, staged.engine_to_ase_index)


def test_extract_excludes_hollow_without_subsurface_label(tmp_path: Path) -> None:
    slab = _slab()
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    node = _semantic_node("p2_undefined", "P2", [2, 3, 5], [1.0, 1.0, 5.0])
    node["hollow_subtype"] = "undefined"
    node["subsurface_ref_dist"] = None
    validate_graph(_graph([node]))
    assert extract_candidates(_graph([node]), staged.atoms, staged.engine_to_ase_index) == []

def test_dedup_does_not_merge_different_site_families() -> None:
    slab = _slab()
    top = _candidate("p0_1", 0.1)
    bridge = WeightedAlphaCandidate(
        engine_node_id="p1_1",
        position=np.asarray([0.1, 0.0, 5.0]),
        site_kind="bridge",
        coordination=2,
        hollow_subtype=None,
        source_atom_indices=(0, 1),
        normal=np.asarray([0.0, 0.0, 1.0]),
        metadata={},
    )
    assert len(deduplicate_candidates([top, bridge], slab, tolerance=0.35)) == 2


def _square_surface() -> Atoms:
    return Atoms(
        "Pt4",
        positions=[[0.0, 0.0, 5.0], [2.0, 0.0, 5.0], [2.0, 2.0, 5.0], [0.0, 2.0, 5.0]],
        cell=[[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]],
        pbc=[True, True, False],
    )


def _square_triangle(node_id: str, sources: tuple[int, int, int], position: np.ndarray) -> WeightedAlphaCandidate:
    normal = np.asarray([0.0, 0.0, 1.0])
    distance = 2.02
    return WeightedAlphaCandidate(
        engine_node_id=node_id,
        position=position,
        site_kind="hollow",
        coordination=3,
        hollow_subtype="fcc",
        source_atom_indices=sources,
        normal=normal,
        metadata={
            "placement": {
                "anchor_position": position.tolist(),
                "direction": normal.tolist(),
                "position": (position + normal * distance).tolist(),
                "distance": distance,
                "clearance_at_position": 2.02,
                "target_clearance": 2.02,
                "precursor_radius": 1.52,
                "gap": 0.5,
                "target_clearance_reached": True,
                "distance_type": "ray_clearance",
                "status": "target_clearance_reached",
            }
        },
    )


def test_fourfold_aggregation_requires_shared_diagonal_and_valid_cyclic_geometry() -> None:
    slab = _square_surface()
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([1.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.0, 1.0, 5.0]))
    merged = aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)
    assert len(merged) == 1
    assert merged[0].coordination == 4
    assert merged[0].source_atom_indices == (0, 1, 2, 3)
    assert merged[0].hollow_subtype is None
    assert merged[0].metadata["aggregation"] == "coincident_p2_pair"
    assert merged[0].metadata["fourfold_geometry_validated"] is True


def test_fourfold_aggregation_synthesizes_merged_placement() -> None:
    slab = _square_surface()
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([0.98, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.02, 1.0, 5.0]))
    second_normal = np.asarray([0.0, 0.02, np.sqrt(1.0 - 0.02**2)])
    second = WeightedAlphaCandidate(
        engine_node_id=second.engine_node_id,
        position=second.position,
        site_kind=second.site_kind,
        coordination=second.coordination,
        hollow_subtype=second.hollow_subtype,
        source_atom_indices=second.source_atom_indices,
        normal=second_normal,
        metadata={
            **second.metadata,
            "placement": {
                **second.metadata["placement"],
                "direction": second_normal.tolist(),
                "position": (second.position + second_normal * 2.02).tolist(),
            },
        },
    )
    merged = aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)
    assert len(merged) == 1
    placement = merged[0].metadata["placement"]
    np.testing.assert_allclose(placement["anchor_position"], merged[0].position)
    np.testing.assert_allclose(placement["direction"], merged[0].normal)
    np.testing.assert_allclose(
        placement["position"],
        merged[0].position + merged[0].normal * placement["distance"],
    )
    assert placement["precursor_radius"] == 1.52


def test_fourfold_aggregation_rejects_conflicting_constituent_normals() -> None:
    slab = _square_surface()
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([1.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.0, 1.0, 5.0]))
    conflicting = np.asarray([0.0, 0.8, 0.6])
    second = WeightedAlphaCandidate(
        engine_node_id=second.engine_node_id,
        position=second.position,
        site_kind=second.site_kind,
        coordination=second.coordination,
        hollow_subtype=second.hollow_subtype,
        source_atom_indices=second.source_atom_indices,
        normal=conflicting,
        metadata={
            **second.metadata,
            "placement": {
                **second.metadata["placement"],
                "direction": conflicting.tolist(),
                "position": (second.position + conflicting * 2.02).tolist(),
            },
        },
    )
    assert len(aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)) == 2


def test_fourfold_aggregation_preserves_noncoincident_triangles() -> None:
    slab = _square_surface()
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([1.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.3, 1.0, 5.0]))
    assert len(aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)) == 2


def test_fourfold_aggregation_rejects_non_coplanar_sources() -> None:
    slab = _square_surface()
    slab.positions[3, 2] = 5.5
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([1.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.0, 1.0, 5.0]))
    assert len(aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)) == 2


def test_fourfold_aggregation_rejects_non_cyclic_sources() -> None:
    slab = _square_surface()
    slab.positions[3, :2] = [0.0, 1.0]
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([1.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([1.0, 1.0, 5.0]))
    assert len(aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)) == 2


def test_fourfold_aggregation_uses_mic_across_periodic_boundary() -> None:
    slab = Atoms(
        "Pt4",
        positions=[[4.5, 0.5, 5.0], [0.5, 0.5, 5.0], [0.5, 1.5, 5.0], [4.5, 1.5, 5.0]],
        cell=[[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]],
        pbc=[True, True, False],
    )
    first = _square_triangle("p2_1", (0, 1, 2), np.asarray([0.0, 1.0, 5.0]))
    second = _square_triangle("p2_2", (0, 2, 3), np.asarray([5.0, 1.0, 5.0]))
    merged = aggregate_fourfold_hollows([first, second], slab, center_tolerance=0.1)
    assert len(merged) == 1
    assert merged[0].coordination == 4

def test_dedup_preserves_hollow_subtype_and_coordination() -> None:
    slab = _slab()
    base = dict(
        position=np.asarray([1.0, 1.0, 5.0]),
        site_kind="hollow",
        source_atom_indices=(0, 1, 2),
        normal=np.asarray([0.0, 0.0, 1.0]),
        metadata={},
    )
    fcc = WeightedAlphaCandidate("p2_fcc", coordination=3, hollow_subtype="fcc", **base)
    hcp = WeightedAlphaCandidate("p2_hcp", coordination=3, hollow_subtype="hcp", **base)
    fourfold = WeightedAlphaCandidate("p2_four", coordination=4, hollow_subtype=None, **base)
    assert len(deduplicate_candidates([fcc, hcp, fourfold], slab)) == 3


def test_load_graph_rejects_nonstandard_nan(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    path.write_text('{"nodes": [], "edges": [], "metadata": {"value": NaN}}')
    with pytest.raises(WeightedAlphaSchemaError, match="nonfinite JSON constant"):
        load_graph(path)


def test_load_graph_rejects_overflow_float_and_duplicate_keys(tmp_path: Path) -> None:
    overflow = tmp_path / "overflow.json"
    overflow.write_text('{"nodes": [], "edges": [], "metadata": {"value": 1e309}}')
    with pytest.raises(WeightedAlphaSchemaError, match="nonfinite JSON number"):
        load_graph(overflow)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"nodes": [], "nodes": [], "edges": [], "metadata": {}}')
    with pytest.raises(WeightedAlphaSchemaError, match="duplicate JSON key"):
        load_graph(duplicate)


def test_validate_graph_rejects_nonfinite_semantic_distance() -> None:
    node = _semantic_node("p2_0", "P2", [0, 1, 2], [0.0, 0.0, 5.0])
    node["subsurface_ref_dist"] = float("nan")
    with pytest.raises(WeightedAlphaSchemaError, match="subsurface_ref_dist"):
        validate_graph(_graph([node]))


def test_validate_graph_accepts_p3_but_rejects_unknown_node_type() -> None:
    p3 = {"id": "p3_0", "type": "P3", "classification": "regular", "atoms": [0, 1, 2, 3], "position": [0, 0, 2]}
    validate_graph(_graph([p3]))
    p3["type"] = "P9"
    with pytest.raises(WeightedAlphaSchemaError, match="unknown node type"):
        validate_graph(_graph([p3]))


def test_validate_graph_requires_boolean_pbc_values() -> None:
    graph = _graph([])
    graph["metadata"]["pbc"] = [1, 1, 0]
    with pytest.raises(WeightedAlphaSchemaError, match="three JSON booleans"):
        validate_graph(graph)


def test_validate_graph_rejects_boolean_atom_index_and_coordination() -> None:
    node = _semantic_node("p0_0", "P0", [True], [0.0, 0.0, 5.0])
    with pytest.raises(WeightedAlphaSchemaError, match="non-negative ints"):
        validate_graph(_graph([node]))
    node = _semantic_node("p0_0", "P0", [0], [0.0, 0.0, 5.0])
    node["coordination"] = True
    with pytest.raises(WeightedAlphaSchemaError, match="coordination"):
        validate_graph(_graph([node]))


def test_validate_graph_checks_basic_p3_shape() -> None:
    p3 = {"id": "p3_0", "type": "P3", "atoms": [0, 1, 2, 3], "position": [0, 0]}
    with pytest.raises(WeightedAlphaSchemaError, match="position"):
        validate_graph(_graph([p3]))


def test_validate_graph_rejects_nonstring_edge_endpoints() -> None:
    graph = _graph([_semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])])
    graph["edges"] = [{"source": ["p0_0"], "target": "p0_0"}]
    with pytest.raises(WeightedAlphaSchemaError, match="string source/target"):
        validate_graph(graph)


def test_validate_graph_rejects_dangling_edge() -> None:
    graph = _graph([_semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])])
    graph["edges"] = [
        {"source": "p0_0", "target": "missing", "relationship": "contains", "weight": 1}
    ]
    with pytest.raises(WeightedAlphaSchemaError, match="dangling"):
        validate_graph(graph)


def test_validate_graph_accepts_pinned_endpoint_edge() -> None:
    p0 = _semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])
    p1 = _semantic_node("p1_0", "P1", [0, 1], [0.5, 0.0, 1.0])
    graph = _graph([p0, p1])
    graph["edges"] = [
        {"source": "p1_0", "target": "p0_0", "relationship": "endpoint", "weight": 1}
    ]
    assert validate_graph(graph) is graph


@pytest.mark.parametrize("weight", [True, 1.0])
def test_validate_graph_rejects_noninteger_edge_weight(weight: object) -> None:
    p0 = _semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])
    p1 = _semantic_node("p1_0", "P1", [0, 1], [0.5, 0.0, 1.0])
    graph = _graph([p0, p1])
    graph["edges"] = [
        {"source": "p1_0", "target": "p0_0", "relationship": "endpoint", "weight": weight}
    ]
    with pytest.raises(WeightedAlphaSchemaError, match="integer weight 1"):
        validate_graph(graph)


def test_validate_graph_rejects_relationship_for_wrong_node_types() -> None:
    p0 = _semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])
    p1 = _semantic_node("p1_0", "P1", [0, 1], [0.5, 0.0, 1.0])
    graph = _graph([p0, p1])
    graph["edges"] = [
        {"source": "p1_0", "target": "p0_0", "relationship": "contains", "weight": 1}
    ]
    with pytest.raises(WeightedAlphaSchemaError, match="pinned relationship"):
        validate_graph(graph)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("directed", True),
        ("directed", 0),
        ("multigraph", True),
        ("multigraph", 0),
        ("graph_type", "other"),
    ],
)
def test_validate_graph_pins_envelope(field: str, value: object) -> None:
    graph = _graph([])
    graph[field] = value
    with pytest.raises(WeightedAlphaSchemaError, match=field):
        validate_graph(graph)


def test_stage_rejects_tilted_surface_for_phase_one(tmp_path: Path) -> None:
    slab = _slab()
    slab.set_cell([[5.0, 0.0, 1.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]])
    with pytest.raises(WeightedAlphaConfigError, match="axis-aligned"):
        stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")


def test_execution_error_carries_stderr() -> None:
    error = WeightedAlphaExecutionError(
        "engine failed", command=["engine", "-f", "slab.POSCAR"], returncode=7,
        stdout="out", stderr="fatal graph error",
    )
    assert error.returncode == 7
    assert "fatal graph error" in str(error)
    assert error.command[0] == "engine"


def test_reused_workdir_cannot_accept_stale_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    workdir = tmp_path / "reused"
    workdir.mkdir()
    (workdir / config.graph_filename).write_text(json.dumps(_graph([])))
    class FakeProcess:
        pid = 123
        returncode = 0
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(weighted_backend, "_attach_windows_kill_job", lambda _process: None)
    monkeypatch.setattr(weighted_backend, "_resume_windows_process", lambda _process: None)
    monkeypatch.setattr(
        weighted_backend.subprocess,
        "Popen",
        lambda *_a, **_k: FakeProcess(),
    )
    with pytest.raises(WeightedAlphaExecutionError, match="did not create"):
        weighted_backend._run_in_directory(_slab(), config, workdir)


def test_run_weighted_alpha_rejects_empty_candidate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    empty = weighted_backend.WeightedAlphaRun(
        graph=_graph([]),
        candidates=(),
        provenance={},
        engine_to_ase_index=tuple(range(len(_slab()))),
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(weighted_backend, "_run_in_directory", lambda *_a, **_k: empty)
    with pytest.raises(WeightedAlphaExecutionError, match="no accepted adsorption sites"):
        run_weighted_alpha(_slab(), config, workdir=tmp_path / "engine")


def test_resolve_requires_pinned_executable_and_radius_unless_explicitly_unsafe(
    tmp_path: Path,
) -> None:
    exe = _write(tmp_path / "engine.exe", "exe")
    radius = _write(tmp_path / "UFF.rad", "radius")
    with pytest.raises(WeightedAlphaConfigError, match="expected_sha256 is required"):
        resolve_weighted_alpha_config(WeightedAlphaConfig(exe, radius))
    resolved = resolve_weighted_alpha_config(
        WeightedAlphaConfig(exe, radius, allow_unpinned_runtime=True)
    )
    assert resolved.allow_unpinned_runtime is True


def test_resolve_requires_and_verifies_adjacent_dll_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    dependency = _write(tmp_path / "runtime_support.dll", "dll-v1")
    with pytest.raises(WeightedAlphaConfigError, match="runtime SHA-256 manifest"):
        resolve_weighted_alpha_config(config)

    manifest = tmp_path / "runtime_sha256.json"
    manifest.write_text(json.dumps({
        dependency.name: hashlib.sha256(dependency.read_bytes()).hexdigest()
    }))
    pinned = _config(
        tmp_path,
        runtime_sha256_manifest=manifest,
        expected_runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    assert resolve_weighted_alpha_config(pinned) is pinned

    dependency.write_text("tampered")
    with pytest.raises(WeightedAlphaConfigError, match="runtime dependency SHA-256 mismatch"):
        resolve_weighted_alpha_config(pinned)


def test_release_manifest_supplies_adjacent_dll_hashes(tmp_path: Path) -> None:
    base = _config(tmp_path)
    dependency = _write(tmp_path / "runtime_support.dll", "dll-v1")
    manifest = tmp_path / "runtime_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entrypoint": base.executable.name,
                "radius_table": base.radius_file.name,
                "artifacts": {
                    base.executable.name: hashlib.sha256(base.executable.read_bytes()).hexdigest(),
                    base.radius_file.name: hashlib.sha256(base.radius_file.read_bytes()).hexdigest(),
                    dependency.name: hashlib.sha256(dependency.read_bytes()).hexdigest(),
                },
            }
        )
    )
    config = _config(
        tmp_path,
        runtime_sha256_manifest=manifest,
        expected_runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    assert resolve_weighted_alpha_config(config) is config


def test_extract_rejects_corrugated_top_layer(tmp_path: Path) -> None:
    slab = _slab()
    slab.positions[5, 2] = 4.6
    staged = stage_slab_for_engine(slab, tmp_path / "slab.POSCAR")
    graph = _graph([
        _semantic_node("p0_upper", "P0", [2], [0.0, 0.0, 5.0]),
        _semantic_node("p0_lower", "P0", [0], [0.0, 0.0, 1.0]),
    ])
    with pytest.raises(WeightedAlphaConfigError, match="corrugated top layers"):
        extract_candidates(graph, staged.atoms, staged.engine_to_ase_index)


def test_extract_rejects_separate_incomplete_upper_terrace(tmp_path: Path) -> None:
    slab = _slab()
    slab.positions[5, 2] = 6.2
    staged = stage_slab_for_engine(slab, tmp_path / "stepped.POSCAR")
    graph = _graph([
        _semantic_node("p0_upper", "P0", [5], [0.0, 0.0, 6.2]),
    ])
    with pytest.raises(WeightedAlphaConfigError, match="stepped or incomplete"):
        extract_candidates(graph, staged.atoms, staged.engine_to_ase_index)


def test_validate_graph_rejects_malformed_optional_normal() -> None:
    node = _semantic_node("p0_0", "P0", [0], [0.0, 0.0, 1.0])
    node["has_surface_normal"] = False
    node["surface_normal"] = [0.0, 0.0]
    with pytest.raises(WeightedAlphaSchemaError, match="surface_normal"):
        validate_graph(_graph([node]))


@pytest.mark.parametrize("node_type", ["P0", "P1"])
def test_validate_graph_rejects_empty_p0_p1_sources(node_type: str) -> None:
    node = _semantic_node(
        f"{node_type.lower()}_0", node_type, [], [0.0, 0.0, 1.0]
    )
    with pytest.raises(WeightedAlphaSchemaError, match="source atom"):
        validate_graph(_graph([node]))


def test_single_source_periodic_p1_with_two_images_is_valid_candidate(tmp_path: Path) -> None:
    node = _semantic_node("p1_periodic_self", "P1", [2], [2.5, 0.0, 5.0])
    node["atoms_with_images"] = [
        {"atom_id": 2, "image_offset": [0, 0, 0]},
        {"atom_id": 2, "image_offset": [1, 0, 0]},
    ]
    graph = _graph([node])
    assert validate_graph(graph) is graph
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    candidates = extract_candidates(graph, staged.atoms, staged.engine_to_ase_index)
    assert len(candidates) == 1
    assert candidates[0].coordination == 2
    assert candidates[0].source_atom_indices == (4,)
    assert candidates[0].metadata["source_atom_images"] == [
        {"ase_atom_index": 4, "image_offset": [0, 0, 0]},
        {"ase_atom_index": 4, "image_offset": [1, 0, 0]},
    ]


def test_extract_rejects_candidate_when_target_clearance_was_not_reached(
    tmp_path: Path,
) -> None:
    node = _semantic_node("p0_blocked", "P0", [2], [2.5, 0.0, 5.0])
    node["placement"].update(
        {
            "position": [2.5, 0.0, 5.7],
            "distance": 0.7,
            "clearance_at_position": 0.7,
            "target_clearance_reached": False,
            "status": "max_clearance_fallback",
        }
    )
    graph = _graph([node])
    assert validate_graph(graph) is graph
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    assert extract_candidates(graph, staged.atoms, staged.engine_to_ase_index) == []


def test_runtime_manifest_rejects_duplicate_keys(tmp_path: Path) -> None:
    config = _config(tmp_path)
    dependency = _write(tmp_path / "support.dll", "dll")
    digest = hashlib.sha256(dependency.read_bytes()).hexdigest()
    manifest = tmp_path / "runtime_sha256.json"
    manifest.write_text(
        '{"support.dll":"' + digest + '","support.dll":"' + digest + '"}'
    )
    duplicate = _config(
        tmp_path,
        runtime_sha256_manifest=manifest,
        expected_runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    with pytest.raises(WeightedAlphaConfigError, match="duplicate runtime manifest key"):
        resolve_weighted_alpha_config(duplicate)


def test_live_output_cap_terminates_before_timeout_and_bounds_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    radius = _write(tmp_path / "UFF.rad", "radius")
    config = WeightedAlphaConfig(
        executable=Path(sys.executable),
        radius_file=radius,
        timeout_s=2.0,
        allow_unpinned_runtime=True,
    )
    monkeypatch.setattr(weighted_backend, "MAX_ENGINE_OUTPUT_BYTES", 4096)
    monkeypatch.setattr(
        weighted_backend,
        "build_engine_command",
        lambda *_args: [
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.buffer.write(b'x'*1048576); "
            "sys.stdout.buffer.flush(); time.sleep(30)",
        ],
    )
    started = time.monotonic()
    with pytest.raises(WeightedAlphaExecutionError, match="output .* exceeded"):
        weighted_backend._run_in_directory(_slab(), config, tmp_path / "output-cap")
    assert time.monotonic() - started < config.timeout_s
    assert (tmp_path / "output-cap" / "weighted_alpha.stdout.log").stat().st_size <= 4096


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object regression")
def test_windows_job_kills_child_after_parent_has_exited(tmp_path: Path) -> None:
    import ctypes

    go_path = tmp_path / "go"
    pid_path = tmp_path / "child.pid"
    parent_script = tmp_path / "spawn_child.py"
    parent_script.write_text(
        "import pathlib,subprocess,sys,time\n"
        f"go=pathlib.Path({str(go_path)!r}); pid=pathlib.Path({str(pid_path)!r})\n"
        "while not go.exists(): time.sleep(0.01)\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        "pid.write_text(str(child.pid))\n"
    )
    parent = subprocess.Popen([sys.executable, str(parent_script)])
    job = weighted_backend._attach_windows_kill_job(parent)
    try:
        go_path.write_text("go")
        deadline = time.monotonic() + 5.0
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_path.exists()
        child_pid = int(pid_path.read_text())
        assert parent.wait(timeout=5.0) == 0
        assert parent.poll() == 0
        weighted_backend._terminate_process_tree(parent, job)

        process_handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, child_pid)
        if process_handle:
            try:
                assert ctypes.windll.kernel32.WaitForSingleObject(process_handle, 2000) == 0
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)
    finally:
        job.close()


def test_minimal_engine_environment_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _write(tmp_path / "engine.exe", "engine")
    monkeypatch.setenv("PATH", "C:/ambient/bin")
    monkeypatch.setenv("PYTHONHOME", "C:/ambient/python")
    monkeypatch.setenv("PYTHONPATH", "C:/ambient/modules")
    monkeypatch.setenv("OMP_DYNAMIC", "TRUE")
    monkeypatch.setenv("MESA_SECRET_SENTINEL", "must-not-leak")
    environment = weighted_backend._minimal_engine_environment(executable)
    assert environment["PATH"] == str(executable.parent)
    assert environment["LANG"] == "C"
    assert environment["LC_ALL"] == "C"
    assert environment["OMP_NUM_THREADS"] == "1"
    assert environment["MKL_NUM_THREADS"] == "1"
    assert environment["OPENBLAS_NUM_THREADS"] == "1"
    assert "PYTHONHOME" not in environment
    assert "PYTHONPATH" not in environment
    assert "OMP_DYNAMIC" not in environment
    assert "MESA_SECRET_SENTINEL" not in environment

def test_runtime_manifest_itself_is_pinned(tmp_path: Path) -> None:
    dependency = _write(tmp_path / "support.dll", "dll-v1")
    manifest = tmp_path / "runtime_sha256.json"
    manifest.write_text(json.dumps({dependency.name: hashlib.sha256(dependency.read_bytes()).hexdigest()}))
    with pytest.raises(WeightedAlphaConfigError, match="expected_runtime_manifest_sha256"):
        resolve_weighted_alpha_config(_config(tmp_path, runtime_sha256_manifest=manifest))

    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    pinned = _config(
        tmp_path,
        runtime_sha256_manifest=manifest,
        expected_runtime_manifest_sha256=manifest_digest,
    )
    assert resolve_weighted_alpha_config(pinned) is pinned
    dependency.write_text("dll-v2")
    manifest.write_text(json.dumps({dependency.name: hashlib.sha256(dependency.read_bytes()).hexdigest()}))
    with pytest.raises(WeightedAlphaConfigError, match="runtime manifest SHA-256 mismatch"):
        resolve_weighted_alpha_config(pinned)


def test_audited_runtime_is_copied_and_reverified_in_private_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    executable = _write(source / "engine.exe", "engine-v1")
    radius = _write(source / "UFF.rad", "radius-v1")
    dependency = _write(source / "support.dll", "dll-v1")
    manifest = source / "runtime.json"
    manifest.write_text(json.dumps({dependency.name: hashlib.sha256(dependency.read_bytes()).hexdigest()}))
    config = WeightedAlphaConfig(
        executable=executable,
        radius_file=radius,
        expected_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        expected_radius_sha256=hashlib.sha256(radius.read_bytes()).hexdigest(),
        runtime_sha256_manifest=manifest,
        expected_runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    staged, runtime_dir = weighted_backend._stage_runtime_bundle(config, tmp_path / "work")
    assert staged.executable.parent == runtime_dir
    assert staged.radius_file.parent == runtime_dir
    assert staged.runtime_sha256_manifest is not None
    assert staged.runtime_sha256_manifest.parent == runtime_dir
    weighted_backend._verify_runtime_artifacts(staged)

    executable.write_text("tampered-after-copy")
    radius.write_text("tampered-after-copy")
    dependency.write_text("tampered-after-copy")
    weighted_backend._verify_runtime_artifacts(staged)


def test_load_graph_rejects_integer_outside_signed_64_bit_range(tmp_path: Path) -> None:
    path = tmp_path / "huge-int.json"
    path.write_text('{"directed":false,"multigraph":false,"graph_type":"undirected_hierarchical",'
                    '"nodes":[],"edges":[],"metadata":{"value":999999999999999999999999999999}}')
    with pytest.raises(WeightedAlphaSchemaError, match="integer"):
        load_graph(path)


def test_extract_binds_graph_to_exact_staged_input(tmp_path: Path) -> None:
    staged = stage_slab_for_engine(_slab(), tmp_path / "slab.POSCAR")
    graph = _graph([_semantic_node("p0_top", "P0", [2], [2.5, 0.0, 5.0])])
    graph["metadata"]["staged_input_sha256"] = hashlib.sha256(staged.path.read_bytes()).hexdigest()
    assert extract_candidates(
        graph,
        staged.atoms,
        staged.engine_to_ase_index,
        expected_staged_input_sha256=hashlib.sha256(staged.path.read_bytes()).hexdigest(),
    )

    graph["metadata"]["unique_atom_count"] = 999
    with pytest.raises(WeightedAlphaSchemaError, match="unique_atom_count"):
        extract_candidates(graph, staged.atoms, staged.engine_to_ase_index)
    graph["metadata"]["unique_atom_count"] = len(staged.atoms)
    graph["metadata"]["cell"] = [[6.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 15.0]]
    with pytest.raises(WeightedAlphaSchemaError, match="metadata.cell"):
        extract_candidates(graph, staged.atoms, staged.engine_to_ase_index)
    graph["metadata"]["cell"] = staged.atoms.cell.array.tolist()
    with pytest.raises(WeightedAlphaSchemaError, match="staged_input_sha256"):
        extract_candidates(
            graph,
            staged.atoms,
            staged.engine_to_ase_index,
            expected_staged_input_sha256="f" * 64,
        )


def test_validate_graph_rejects_bad_classification_cardinality_and_placement() -> None:
    p0 = _semantic_node("p0_bad", "P0", [0, 1], [0.0, 0.0, 5.0])
    with pytest.raises(WeightedAlphaSchemaError, match="exactly 1"):
        validate_graph(_graph([p0]))

    p1 = _semantic_node("p1_bad", "P1", [0, 1], [0.0, 0.0, 5.0])
    p1["classification"] = 7
    with pytest.raises(WeightedAlphaSchemaError, match="classification"):
        validate_graph(_graph([p1]))

    p1["classification"] = "regular"
    p1["placement"] = "not-an-object"
    with pytest.raises(WeightedAlphaSchemaError, match="placement"):
        validate_graph(_graph([p1]))


@pytest.mark.parametrize(
    "name",
    [".", "..", "slab.POSCAR", "weighted_alpha.stdout.log", "weighted_alpha.stderr.log"],
)
def test_config_rejects_reserved_graph_filename(tmp_path: Path, name: str) -> None:
    with pytest.raises(WeightedAlphaConfigError, match="graph_filename"):
        resolve_weighted_alpha_config(_config(tmp_path, graph_filename=name))
