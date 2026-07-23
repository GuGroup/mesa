from __future__ import annotations

from types import SimpleNamespace
import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms

import slabuilder.adsorption as adsorption
import slabuilder.site_map as site_map
import slabuilder.structure_understanding as understanding
from slabuilder.adsorption import AdsorptionSite
from slabuilder.weighted_alpha_backend import WeightedAlphaCandidate, WeightedAlphaConfig


def _slab() -> Atoms:
    return Atoms(
        "Pt4",
        positions=[[0, 0, 1], [2, 0, 1], [0, 2, 1], [2, 2, 1]],
        cell=[4, 4, 12],
        pbc=[True, True, False],
    )


def _site(source: str = "catkit") -> AdsorptionSite:
    return AdsorptionSite(
        site_type="top",
        position=np.asarray([1.0, 1.0, 1.0]),
        surface_atom_idx=[0],
        priority=0,
        sources=[source],
    )


def test_weighted_site_map_uses_true_skew_mic_without_changing_legacy_helpers() -> None:
    root3 = float(np.sqrt(3.0))
    cell = np.asarray([[1.0, 0.0, 0.0], [0.5, root3 / 2.0, 0.0], [0.0, 0.0, 10.0]])
    atoms = Atoms("Pt", positions=[[0.0, 0.0, 0.0]], cell=cell, pbc=[True, True, False])
    origin = np.zeros(3)
    target = np.asarray([0.49, 0.49, 0.0]) @ cell
    legacy_vector = np.asarray([0.49, 0.49, 0.0]) @ cell
    true_vector = np.asarray([-0.51, 0.49, 0.0]) @ cell
    legacy_distance = float(np.linalg.norm(legacy_vector))
    true_distance = float(np.linalg.norm(true_vector))

    assert np.allclose(site_map._mic_vector(atoms, origin, target), legacy_vector, atol=1.0e-12)
    assert understanding._mic_norm(atoms, origin, target) == pytest.approx(legacy_distance)
    left = AdsorptionSite("top", origin, [0], 0)
    right = AdsorptionSite("top", target, [0], 0)
    assert adsorption._site_xy_distance(atoms, left, right) == pytest.approx(legacy_distance)
    assert adsorption._position_xy_distance(atoms, origin, target) == pytest.approx(legacy_distance)

    weighted_left = site_map.SiteRecord(
        id="weighted:0", site_type="top", position=tuple(origin), sources=("weighted_alpha",)
    )
    weighted_right = site_map.SiteRecord(
        id="weighted:1", site_type="top", position=tuple(target), sources=("weighted_alpha",)
    )
    assert site_map._site_distance(atoms, weighted_left, weighted_right) == pytest.approx(
        true_distance
    )


def test_weighted_multi_site_separation_uses_true_skew_mic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root3 = float(np.sqrt(3.0))
    cell = np.asarray([[3.0, 0.0, 0.0], [1.5, 1.5 * root3, 0.0], [0.0, 0.0, 12.0]])
    atoms = Atoms("Pt", positions=[[0.0, 0.0, 1.0]], cell=cell, pbc=[True, True, False])
    target = np.asarray([0.49, 0.49, 0.0]) @ cell
    weighted = AdsorptionSite("top", target, [0], 0, sources=["weighted_alpha"])
    legacy = AdsorptionSite("top", target, [0], 0, sources=["catkit"])
    spec = adsorption.AdsorbatePlacementSpec("H")

    monkeypatch.setattr(adsorption, "identify_adsorption_sites", lambda *_args, **_kwargs: [weighted])
    with pytest.raises(ValueError, match="at least 1.80"):
        adsorption._select_multi_adsorption_site(
            atoms,
            spec,
            backend="weighted_alpha",
            weighted_alpha_config=None,
            selected_positions=[np.zeros(3)],
            min_site_separation=1.8,
        )

    monkeypatch.setattr(adsorption, "identify_adsorption_sites", lambda *_args, **_kwargs: [legacy])
    selected = adsorption._select_multi_adsorption_site(
        atoms,
        spec,
        backend="auto",
        weighted_alpha_config=None,
        selected_positions=[np.zeros(3)],
        min_site_separation=1.8,
    )
    assert selected[1] is legacy


def test_legacy_site_map_omits_weighted_only_validation_notes() -> None:
    legacy = site_map.SiteRecord(
        id="legacy:0",
        site_type="top",
        position=(0.0, 0.0, 0.0),
        sources=("catkit",),
        validation_notes=("catkit_only",),
    )
    weighted = site_map.SiteRecord(
        id="weighted:0",
        site_type="top",
        position=(0.0, 0.0, 0.0),
        sources=("weighted_alpha",),
        validation_notes=("weighted_alpha_only",),
    )
    assert "validation_notes" not in site_map._site_to_jsonable(legacy)
    assert site_map._site_to_jsonable(weighted)["validation_notes"] == [
        "weighted_alpha_only"
    ]


def test_weighted_dispatch_is_dedicated_and_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _site("weighted_alpha")
    config = object()
    calls: list[tuple[Atoms, str, object]] = []

    def weighted(slab: Atoms, adsorbate: str, *, config: object) -> list[AdsorptionSite]:
        calls.append((slab, adsorbate, config))
        return [expected]

    monkeypatch.setattr(adsorption, "_identify_sites_weighted_alpha", weighted)
    for name in ("_identify_sites_catkit", "_identify_sites_pymatgen", "_identify_sites_acat"):
        monkeypatch.setattr(
            adsorption,
            name,
            lambda *_args, _name=name, **_kwargs: pytest.fail(f"legacy detector called: {_name}"),
        )

    result = adsorption.identify_adsorption_sites(
        _slab(), "H", backend="weighted_alpha", weighted_alpha_config=config
    )
    assert result == [expected]
    assert calls == [(calls[0][0], "H", config)]


def test_weighted_exception_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> list[AdsorptionSite]:
        raise RuntimeError("strict weighted failure")

    monkeypatch.setattr(adsorption, "_identify_sites_weighted_alpha", fail)
    for name in ("_identify_sites_catkit", "_identify_sites_pymatgen", "_identify_sites_acat"):
        monkeypatch.setattr(
            adsorption,
            name,
            lambda *_args, _name=name, **_kwargs: pytest.fail(f"legacy detector called: {_name}"),
        )
    with pytest.raises(RuntimeError, match="strict weighted failure"):
        adsorption.identify_adsorption_sites(_slab(), "H", backend="weighted_alpha")


def test_weighted_empty_result_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adsorption, "_identify_sites_weighted_alpha", lambda *_a, **_k: [])
    with pytest.raises(RuntimeError, match="no accepted adsorption sites"):
        adsorption.identify_adsorption_sites(_slab(), "H", backend="weighted_alpha")


def test_legacy_auto_never_touches_weighted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adsorption,
        "_identify_sites_weighted_alpha",
        lambda *_a, **_k: pytest.fail("weighted backend touched by auto"),
    )
    monkeypatch.setattr(adsorption, "_identify_sites_catkit", lambda *_a: [_site("catkit")])
    monkeypatch.setattr(adsorption, "_identify_sites_pymatgen", lambda *_a: [])
    monkeypatch.setattr(adsorption, "_identify_sites_acat", lambda *_a: [])
    result = adsorption.identify_adsorption_sites(_slab(), "H", backend="auto")
    assert len(result) == 1
    assert result[0].sources == ["catkit"]


def test_adapter_preserves_geometric_site_and_contact_anchor_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = WeightedAlphaCandidate(
        engine_node_id="p2_85",
        position=np.asarray([1.1, 1.2, 3.4]),
        site_kind="hollow",
        coordination=3,
        hollow_subtype="fcc",
        source_atom_indices=(3, 1, 2),
        normal=np.asarray([0.0, 0.0, 1.0]),
        metadata={
            "placement": {
                "anchor_position": [1.1, 1.2, 3.4],
                "direction": [0.0, 0.0, 1.0],
                "position": [9.0, 9.0, 9.0],
                "precursor_radius": 1.52,
            }
        },
    )
    provenance = {
        "backend": "weighted_alpha",
        "executable_sha256": "a" * 64,
        "graph_sha256": "b" * 64,
        "alpha_factor": 1.0,
        "probe_radius": 1.52,
    }
    monkeypatch.setattr(
        "slabuilder.weighted_alpha_backend.run_weighted_alpha",
        lambda *_a, **_k: SimpleNamespace(candidates=(candidate,), provenance=provenance),
    )

    sites = adsorption._identify_sites_weighted_alpha(_slab(), "H", config=object())
    assert len(sites) == 1
    site = sites[0]
    assert site.site_type == "fcc_hollow"
    np.testing.assert_allclose(site.position, [1.1, 1.2, 3.4])
    assert site.surface_atom_idx == [3, 1, 2]
    assert site.sources == ["weighted_alpha"]
    assert site.validation_score == 0.0
    assert "weighted_alpha_only_not_cross_backend_scored" in site.validation_notes
    assert site.placement_method == "weighted_alpha_contact_anchor"
    assert site.metadata["weighted_alpha"]["engine_node_id"] == "p2_85"
    assert site.metadata["weighted_alpha"]["run"]["graph_sha256"] == "b" * 64
    assert site.metadata["weighted_alpha"]["placement"]["precursor_radius"] == 1.52
    assert site.position.tolist() != [9.0, 9.0, 9.0]


def test_weighted_placement_uses_contact_point_plus_normal_times_radius() -> None:
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([1.0, 1.0, 1.0]),
        surface_atom_idx=[0],
        priority=0,
        placement_method="weighted_alpha_contact_anchor",
        sources=["weighted_alpha"],
        metadata={
            "weighted_alpha": {
                "placement": {
                    "anchor_position": [1.0, 1.0, 1.0],
                    "direction": [0.0, 0.0, 1.0],
                    "position": [1.0, 1.0, 8.0],
                    "precursor_radius": 1.5,
                }
            }
        },
    )
    placed = adsorption.add_adsorbate_to_slab(_slab(), "H", site, height=9.0)
    np.testing.assert_allclose(placed.positions[len(_slab())], [1.0, 1.0, 2.5])
    assert placed.info["min_distance_passed"] is True


def test_weighted_contact_anchor_rotates_molecule_to_surface_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adsorption,
        "_build_adsorbate_atoms",
        lambda _name: Atoms("CO", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 1.1]]),
    )
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([1.0, 1.0, 3.0]),
        surface_atom_idx=[0],
        priority=0,
        placement_method="weighted_alpha_contact_anchor",
        sources=["weighted_alpha"],
        metadata={
            "weighted_alpha": {
                "placement": {
                    "anchor_position": [1.0, 1.0, 3.0],
                    "direction": [1.0, 0.0, 0.0],
                    "precursor_radius": 1.0,
                }
            }
        },
    )
    placed = adsorption.add_adsorbate_to_slab(_slab(), "CO", site)
    binding = placed.positions[len(_slab())]
    molecular_axis = placed.positions[len(_slab()) + 1] - binding
    np.testing.assert_allclose(binding, [2.0, 1.0, 3.0], atol=1.0e-12)
    np.testing.assert_allclose(molecular_axis, [1.1, 0.0, 0.0], atol=1.0e-12)


def test_weighted_multi_placement_uses_contact_anchor_and_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adsorption,
        "_build_adsorbate_atoms",
        lambda _name: Atoms("CO", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 1.1]]),
    )
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([1.0, 1.0, 3.0]),
        surface_atom_idx=[0],
        priority=0,
        placement_method="weighted_alpha_contact_anchor",
        sources=["weighted_alpha"],
        metadata={
            "weighted_alpha": {
                "placement": {
                    "anchor_position": [1.0, 1.0, 3.0],
                    "direction": [1.0, 0.0, 0.0],
                    "precursor_radius": 1.0,
                }
            }
        },
    )
    monkeypatch.setattr(
        adsorption,
        "_select_multi_adsorption_site",
        lambda *_args, **_kwargs: (0, site),
    )
    placed = adsorption.add_multiple_adsorbates_to_slab(
        _slab(),
        [adsorption.AdsorbatePlacementSpec("CO", "top", 0, height=9.0)],
        backend="weighted_alpha",
    )
    binding = placed.positions[len(_slab())]
    molecular_axis = placed.positions[len(_slab()) + 1] - binding
    np.testing.assert_allclose(binding, [2.0, 1.0, 3.0], atol=1.0e-12)
    np.testing.assert_allclose(molecular_axis, [1.1, 0.0, 0.0], atol=1.0e-12)
    records = json.loads(placed.info["multi_adsorbate_metadata_json"])
    assert records[0]["placement_method"] == "weighted_alpha_contact_anchor"
    assert "height" not in records[0]
    np.testing.assert_allclose(records[0]["contact_anchor"]["binding_position"], binding)


def test_legacy_multi_metadata_does_not_add_weighted_placement_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adsorption,
        "_build_adsorbate_atoms",
        lambda _name: Atoms("H", positions=[[0.0, 0.0, 0.0]]),
    )
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([1.0, 1.0, 1.0]),
        surface_atom_idx=[0],
        priority=0,
        sources=["catkit"],
    )
    monkeypatch.setattr(
        adsorption,
        "_select_multi_adsorption_site",
        lambda *_args, **_kwargs: (0, site),
    )
    placed = adsorption.add_multiple_adsorbates_to_slab(
        _slab(),
        [adsorption.AdsorbatePlacementSpec("H", "top", 0, height=2.0)],
        backend="auto",
    )
    record = json.loads(placed.info["multi_adsorbate_metadata_json"])[0]
    assert record["height"] == 2.0
    assert "placement_method" not in record


def test_weighted_contact_anchor_records_final_wrapped_binding_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adsorption,
        "_build_adsorbate_atoms",
        lambda _name: Atoms("CO", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 1.1]]),
    )
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([2.5, 1.0, 3.0]),
        surface_atom_idx=[0],
        priority=0,
        placement_method="weighted_alpha_contact_anchor",
        sources=["weighted_alpha"],
        metadata={
            "weighted_alpha": {
                "placement": {
                    "anchor_position": [2.5, 1.0, 3.0],
                    "direction": [1.0, 0.0, 0.0],
                    "precursor_radius": 1.0,
                }
            }
        },
    )
    placed = adsorption.add_adsorbate_to_slab(_slab(), "CO", site)
    payload = json.loads(placed.info["weighted_alpha_contact_anchor_json"])
    np.testing.assert_allclose(payload["binding_position"], placed.positions[len(_slab())])


def test_weighted_contact_anchor_rejects_collision() -> None:
    site = AdsorptionSite(
        site_type="top",
        position=np.asarray([0.0, 0.0, 1.0]),
        surface_atom_idx=[0],
        priority=0,
        placement_method="weighted_alpha_contact_anchor",
        sources=["weighted_alpha"],
        metadata={
            "weighted_alpha": {
                "placement": {
                    "anchor_position": [0.0, 0.0, 1.0],
                    "direction": [0.0, 0.0, 1.0],
                    "precursor_radius": 0.1,
                }
            }
        },
    )
    with pytest.raises(ValueError, match="close atomic contact"):
        adsorption.add_adsorbate_to_slab(_slab(), "H", site)


def test_explicit_weighted_batch_placement_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _site("weighted_alpha")
    site.placement_method = "weighted_alpha_contact_anchor"
    monkeypatch.setattr(
        adsorption,
        "identify_adsorption_sites",
        lambda *_args, **_kwargs: [site],
    )
    monkeypatch.setattr(
        adsorption,
        "add_adsorbate_to_slab",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("placement failed")),
    )
    with pytest.raises(ValueError, match="placement failed"):
        adsorption.generate_all_adsorption_structures(
            _slab(), "H", backend="weighted_alpha"
        )


def test_site_map_serializes_weighted_metadata_and_propagates_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = object()
    site = _site("weighted_alpha")
    site.metadata = {"weighted_alpha": {"engine_node_id": "p0_1"}}
    observed: dict[str, object] = {}

    def identify(*_args: object, **kwargs: object) -> list[AdsorptionSite]:
        observed.update(kwargs)
        return [site]

    monkeypatch.setattr(site_map, "identify_adsorption_sites", identify)
    graph = site_map.build_site_map(
        _slab(), backend="weighted_alpha", weighted_alpha_config=marker
    )
    encoded = site_map.site_map_to_jsonable(graph)
    assert observed["weighted_alpha_config"] is marker
    assert encoded["sites"][0]["metadata"]["weighted_alpha"]["engine_node_id"] == "p0_1"


def test_surface_packet_reraises_weighted_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("engine unavailable")

    monkeypatch.setattr(understanding, "build_site_map", fail)
    with pytest.raises(RuntimeError, match="engine unavailable"):
        understanding.analyze_surface_sites_packet(
            _slab(), backend="weighted_alpha", weighted_alpha_config=object()
        )


def test_surface_packet_keeps_legacy_empty_map_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        understanding,
        "build_site_map",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("legacy detector failed")),
    )
    packet = understanding.analyze_surface_sites_packet(_slab(), backend="acat")
    assert packet["sites"] == []
    assert any("legacy detector failed" in warning for warning in packet["warnings"])


def test_explicit_weighted_packet_rebuilds_instead_of_using_legacy_cached_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    rebuilt = {
        "sites": [{
            "id": "weighted:0",
            "site_type": "top",
            "position": [0.0, 0.0, 1.0],
            "surface_atom_indices": [0],
            "sources": ["weighted_alpha"],
        }],
        "neighbors": [],
    }

    def build(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append("weighted")
        return rebuilt

    monkeypatch.setattr(understanding, "build_site_map", build)
    monkeypatch.setattr(understanding, "site_map_to_jsonable", lambda value: value)
    packet = understanding.analyze_surface_sites_packet(
        _slab(),
        record={"site_map": {"sites": [{"id": "legacy:0"}], "neighbors": []}},
        backend="weighted_alpha",
        weighted_alpha_config=object(),
    )
    assert calls == ["weighted"]
    assert packet["source"] == "rebuilt"
    assert packet["backend"] == "weighted_alpha"
    assert packet["sites"][0]["sources"] == ["weighted_alpha"]


def test_explicit_weighted_packet_preserves_input_pbc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slab = _slab()
    slab.pbc = [True, True, True]

    def build(observed: Atoms, **_kwargs: object) -> dict[str, object]:
        assert observed.pbc.tolist() == [True, True, True]
        return {"sites": [], "neighbors": []}

    monkeypatch.setattr(understanding, "build_site_map", build)
    monkeypatch.setattr(understanding, "site_map_to_jsonable", lambda value: value)
    packet = understanding.analyze_surface_sites_packet(
        slab, backend="weighted_alpha", weighted_alpha_config=object()
    )
    assert packet["sites"] == []


def test_weighted_packet_remaps_noncontiguous_subset_indices_to_full_atoms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_map = {
        "sites": [{
            "id": "weighted:0",
            "site_type": "bridge",
            "position": [1.0, 1.0, 1.0],
            "surface_atom_indices": [0, 1],
            "sources": ["weighted_alpha"],
            "metadata": {
                "weighted_alpha": {
                    "source_atom_images": [
                        {"ase_atom_index": 0, "image_offset": [0, 0, 0]}
                    ],
                    "candidate": {
                        "source_atom_images": [
                            {"ase_atom_index": 1, "image_offset": [1, 0, 0]}
                        ]
                    },
                    "run": {"engine_to_ase_index": [0, 1]},
                }
            },
        }],
        "neighbors": [],
        "metadata": {
            "weighted_alpha_run": {"engine_to_ase_index": [0, 1]}
        },
    }
    monkeypatch.setattr(understanding, "build_site_map", lambda *_a, **_k: local_map)
    monkeypatch.setattr(understanding, "site_map_to_jsonable", lambda value: value)
    packet = understanding.analyze_surface_sites_packet(
        _slab(),
        record={"slab_atom_indices": [1, 3]},
        backend="weighted_alpha",
        weighted_alpha_config=object(),
    )
    assert packet["slab_atom_indices"] == [1, 3]
    site = packet["sites"][0]
    assert site["surface_atom_indices"] == [1, 3]
    weighted = site["metadata"]["weighted_alpha"]
    assert weighted["source_atom_images"][0]["ase_atom_index"] == 1
    assert weighted["candidate"]["source_atom_images"][0]["ase_atom_index"] == 3
    assert weighted["run"]["engine_to_original_ase_index"] == [1, 3]
    assert weighted["run"]["subset_to_original_ase_index"] == [1, 3]
    run = packet["site_map_metadata"]["weighted_alpha_run"]
    assert run["engine_to_original_ase_index"] == [1, 3]
    assert run["subset_to_original_ase_index"] == [1, 3]

def test_source_site_metadata_preserves_weighted_provenance() -> None:
    site = _site("weighted_alpha")
    site.metadata = {"weighted_alpha": {"graph_sha256": "c" * 64}}
    encoded = adsorption._source_site_metadata(site)
    assert encoded["metadata"] == site.metadata


def test_local_transform_propagates_backend_and_config(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    marker = object()

    def analyze(*_args: object, **kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"sites": [], "neighbors": [], "warnings": []}

    monkeypatch.setattr(understanding, "analyze_surface_sites_packet", analyze)
    understanding.propose_local_transform_packet(
        _slab(),
        backend="weighted_alpha",
        weighted_alpha_config=marker,
    )
    assert observed["backend"] == "weighted_alpha"
    assert observed["weighted_alpha_config"] is marker


def test_multi_site_selection_propagates_weighted_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    marker = object()

    def identify(*_args: object, **kwargs: object) -> list[AdsorptionSite]:
        observed.update(kwargs)
        return [_site("weighted_alpha")]

    monkeypatch.setattr(adsorption, "identify_adsorption_sites", identify)
    spec = adsorption.AdsorbatePlacementSpec("H")
    adsorption._select_multi_adsorption_site(
        _slab(),
        spec,
        backend="weighted_alpha",
        weighted_alpha_config=marker,
        selected_positions=[],
        min_site_separation=1.0,
    )
    assert observed["weighted_alpha_config"] is marker


def test_weighted_metadata_is_standard_json_and_handles_paths_and_sets() -> None:
    site = _site("weighted_alpha")
    site.metadata = {
        "weighted_alpha": {
            "path": Path("engine.exe"),
            "labels": {"beta", "alpha"},
        }
    }
    encoded = adsorption._source_site_metadata(site)
    assert encoded["metadata"]["weighted_alpha"]["path"] == "engine.exe"
    assert encoded["metadata"]["weighted_alpha"]["labels"] == ["alpha", "beta"]
    json.dumps(encoded, allow_nan=False)


def test_weighted_metadata_rejects_nonfinite_numbers() -> None:
    site = _site("weighted_alpha")
    site.metadata = {"weighted_alpha": {"bad": float("nan")}}
    with pytest.raises(ValueError, match="nonfinite"):
        adsorption._source_site_metadata(site)
    with pytest.raises(ValueError, match="nonfinite"):
        site_map._json_safe({"bad": float("inf")})


def test_site_map_hoists_identical_weighted_run_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = {"graph_sha256": "a" * 64, "engine_to_ase_index": [0, 1, 2, 3]}
    first = _site("weighted_alpha")
    second = _site("weighted_alpha")
    second.position = np.asarray([2.0, 2.0, 1.0])
    first.metadata = {"weighted_alpha": {"engine_node_id": "p0_0", "run": run}}
    second.metadata = {"weighted_alpha": {"engine_node_id": "p0_1", "run": run}}
    monkeypatch.setattr(site_map, "identify_adsorption_sites", lambda *_a, **_k: [first, second])
    encoded = site_map.site_map_to_jsonable(site_map.build_site_map(_slab()))
    assert encoded["metadata"]["weighted_alpha_run"] == run
    for site in encoded["sites"]:
        weighted = site["metadata"]["weighted_alpha"]
        assert "run" not in weighted
        assert weighted["run_ref"] == "site_map.metadata.weighted_alpha_run"
