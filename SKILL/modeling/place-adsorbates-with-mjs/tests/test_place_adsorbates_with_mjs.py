from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "place_adsorbates_with_mjs.py"


def load_module():
    spec = importlib.util.spec_from_file_location("place_adsorbates_with_mjs", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_pbc_mask_accepts_compact_and_comma_forms():
    mod = load_module()
    assert mod.parse_pbc_mask("111") == [True, True, True]
    assert mod.parse_pbc_mask("110") == [True, True, False]
    assert mod.parse_pbc_mask("000") == [False, False, False]
    assert mod.parse_pbc_mask("1,1,1") == [True, True, True]
    assert mod.pbc_mask_to_cli([True, True, False]) == "1,1,0"
    assert mod.pbc_mask_to_label([True, True, False]) == "110"


def test_parse_pbc_mask_rejects_invalid_values():
    mod = load_module()
    for raw in ["11", "112", "abc", "1,1", "1,1,2"]:
        try:
            mod.parse_pbc_mask(raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {raw!r}")


def test_regular_policy_accepts_top_bridge_hollow_and_rejects_invalid_nodes():
    mod = load_module()
    cases = [
        ({"type": "P0", "classification": "atom", "surface_normal": [0, 0, 1], "position": [0, 0, 0]}, True, "top"),
        ({"type": "P1", "classification": "regular", "surface_normal": [0, 1, 0], "position": [0, 0, 0]}, True, "bridge"),
        ({"type": "P1", "classification": "singular", "surface_normal": [0, 1, 0], "position": [0, 0, 0]}, False, "bridge"),
        ({"type": "P2", "classification": "regular", "normal": [1, 0, 0], "position": [0, 0, 0], "topology_valid_for_benchmark": True}, True, "hollow"),
        ({"type": "P2", "classification": "regular", "normal": [1, 0, 0], "position": [0, 0, 0], "topology_valid_for_benchmark": False}, False, "hollow"),
        ({"type": "P3", "classification": "regular", "position": [0, 0, 0]}, False, "unknown"),
    ]
    for node, expected_ok, expected_kind in cases:
        result = mod.regular_site_policy(node)
        assert result.accepted is expected_ok
        assert result.site_kind == expected_kind


def test_select_sites_limits_each_kind_to_requested_count():
    mod = load_module()
    sites = []
    for kind in ("top", "bridge", "hollow"):
        for i in range(8):
            sites.append({"site_kind": kind, "site_id": f"{kind}_{i}", "min_clearance": 10 - i})
    selected = mod.select_sites_for_html(sites, per_kind=5)
    assert {kind: len([s for s in selected if s["site_kind"] == kind]) for kind in ("top", "bridge", "hollow")} == {
        "top": 5,
        "bridge": 5,
        "hollow": 5,
    }
    assert [s["site_id"] for s in selected if s["site_kind"] == "top"] == [f"top_{i}" for i in range(5)]


def test_finite_vec_rejects_nan_and_wrong_length():
    mod = load_module()
    assert mod.finite_vec([1, 2, 3]) == [1.0, 2.0, 3.0]
    assert mod.finite_vec([1, 2]) is None
    assert mod.finite_vec([1, math.nan, 3]) is None


def test_wrap_position_to_pbc_cell_wraps_periodic_axes_for_orthogonal_slab():
    mod = load_module()
    wrapped, image_shift, was_wrapped = mod.wrap_position_to_pbc_cell(
        [16.25, -1.5, 12.0],
        cell=[[10.0, 0.0, 0.0], [0.0, 8.0, 0.0], [0.0, 0.0, 20.0]],
        box=[10.0, 8.0, 20.0],
        pbc=[True, True, False],
    )
    assert wrapped == [6.25, 6.5, 12.0]
    assert image_shift == [1, -1, 0]
    assert was_wrapped is True


def test_wrap_position_to_pbc_cell_uses_fractional_coordinates_for_nonorthogonal_cell():
    mod = load_module()
    cell = [[2.0, 0.0, 0.0], [1.0, 2.0, 0.0], [0.0, 0.0, 5.0]]
    # Cartesian position for fractional [1.25, -0.25, 1.40].
    wrapped, image_shift, was_wrapped = mod.wrap_position_to_pbc_cell(
        [2.25, -0.5, 7.0],
        cell=cell,
        box=None,
        pbc=[True, True, False],
    )
    # Only periodic fractional axes wrap: [0.25, 0.75, 1.40].
    assert wrapped == [1.25, 1.5, 7.0]
    assert image_shift == [1, -1, 0]
    assert was_wrapped is True


def test_extract_regular_sites_wraps_nonorthogonal_graph_positions_before_output():
    mod = load_module()
    graph = {
        "metadata": {
            "cell": [[2.0, 0.0, 0.0], [1.0, 2.0, 0.0], [0.0, 0.0, 5.0]],
            "pbc": [True, True, False],
        },
        "nodes": [
            {"id": "p0_atom", "type": "P0", "classification": "atom", "position": [20.0, 20.0, 0.0], "element": "C", "atom_radius": 0.0},
            {
                "id": "p1_oblique",
                "type": "P1",
                "classification": "regular",
                "position": [0.0, 0.0, 0.0],
                "surface_normal": [0.0, 0.0, 1.0],
                "placement": {"position": [2.25, -0.5, 7.0], "status": "synthetic"},
            },
        ],
    }
    result = mod.extract_regular_sites(
        graph,
        adsorbate_radius=0.0,
        gap=-100.0,
        pbc=[True, True, False],
        normal_source="current",
        dedup_distance=0.01,
    )
    bridge = [site for site in result["sites"] if site["source_node_id"] == "p1_oblique"][0]
    assert bridge["raw_adsorption_position"] == [2.25, -0.5, 7.0]
    assert bridge["adsorption_position"] == [1.25, 1.5, 7.0]
    assert bridge["pbc_image_shift"] == [1, -1, 0]
    assert bridge["pbc_wrapped"] is True


def test_extract_regular_sites_can_filter_zmax_side_for_slab_outputs():
    mod = load_module()
    graph = {
        "metadata": {
            "cell": [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 20.0]],
            "pbc": [True, True, False],
        },
        "nodes": [
            {"id": "p0_bottom_atom", "type": "P0", "classification": "atom", "position": [20.0, 20.0, 0.0], "element": "Pt", "atom_radius": 0.0},
            {"id": "p0_top_atom", "type": "P0", "classification": "atom", "position": [20.0, 20.0, 8.0], "element": "Pt", "atom_radius": 0.0},
            {
                "id": "p1_bottom_site",
                "type": "P1",
                "classification": "regular",
                "position": [1.0, 1.0, 0.0],
                "surface_normal": [0.0, 0.0, -1.0],
                "placement": {"position": [1.0, 1.0, -2.0], "status": "synthetic"},
            },
            {
                "id": "p1_top_site",
                "type": "P1",
                "classification": "regular",
                "position": [1.0, 1.0, 8.0],
                "surface_normal": [0.0, 0.0, 1.0],
                "placement": {"position": [1.0, 1.0, 10.0], "status": "synthetic"},
            },
        ],
    }
    result = mod.extract_regular_sites(
        graph,
        adsorbate_radius=0.0,
        gap=-100.0,
        pbc=[True, True, False],
        normal_source="current",
        dedup_distance=0.01,
        open_axis_side="zmax",
    )
    source_ids = {site["source_node_id"] for site in result["sites"]}
    assert "p1_top_site" in source_ids
    assert "p1_bottom_site" not in source_ids
    assert result["rejected"]["open_axis_side_filter"] == 1


def test_extract_regular_sites_can_filter_open_axis_side_for_tilted_slab():
    mod = load_module()
    cell = [[10.0, 0.0, 30.0], [0.0, 10.0, 0.0], [0.0, 0.0, 20.0]]
    # Cartesian z is misleading because periodic vector a has a large z component.
    # bottom fractional c = 0.1 but Cartesian z = 29; top fractional c = 0.9 but z = 21.
    bottom_cart = [9.0, 1.0, 29.0]
    top_cart = [1.0, 1.0, 21.0]
    graph = {
        "metadata": {"cell": cell, "pbc": [True, True, False]},
        "nodes": [
            {"id": "p0_bottom_atom", "type": "P0", "classification": "atom", "position": bottom_cart, "element": "Pt", "atom_radius": 0.0},
            {"id": "p0_top_atom", "type": "P0", "classification": "atom", "position": top_cart, "element": "Pt", "atom_radius": 0.0},
            {
                "id": "p1_bottom_fractional_c",
                "type": "P1",
                "classification": "regular",
                "position": bottom_cart,
                "surface_normal": [0.0, 0.0, -1.0],
                "placement": {"position": bottom_cart, "status": "synthetic"},
            },
            {
                "id": "p1_top_fractional_c",
                "type": "P1",
                "classification": "regular",
                "position": top_cart,
                "surface_normal": [0.0, 0.0, 1.0],
                "placement": {"position": top_cart, "status": "synthetic"},
            },
        ],
    }
    result = mod.extract_regular_sites(
        graph,
        adsorbate_radius=0.0,
        gap=-100.0,
        pbc=[True, True, False],
        normal_source="current",
        dedup_distance=0.01,
        open_axis_side="open-max",
    )
    source_ids = {site["source_node_id"] for site in result["sites"]}
    assert "p1_top_fractional_c" in source_ids
    assert "p1_bottom_fractional_c" not in source_ids
    top_site = [site for site in result["sites"] if site["source_node_id"] == "p1_top_fractional_c"][0]
    assert top_site["open_axis_side"] == "open-max"
    assert top_site["open_axis_index"] == 2
    assert top_site["open_axis_fractional"] == 0.9
    assert result["rejected"]["open_axis_side_filter"] == 1


def test_verify_engine_pin_matches_mismatches_and_warns(tmp_path):
    mod = load_module()
    import hashlib

    exe = tmp_path / "weighted_alpha_complex.exe"
    exe.write_bytes(b"ENGINE-BINARY-BYTES")
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    # Correct pin verifies.
    assert mod.verify_engine_pin("exe", exe, digest, allow_unpinned=False) is True
    # Uppercase / whitespace-padded pin still verifies (normalized).
    assert mod.verify_engine_pin("exe", exe, f"  {digest.upper()}  ", allow_unpinned=False) is True
    # Mismatch is fail-closed.
    for bad in ["0" * 64, "nothex"]:
        try:
            mod.verify_engine_pin("exe", exe, bad, allow_unpinned=False)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for pin {bad!r}")
    # No pin + allow_unpinned returns False without raising.
    assert mod.verify_engine_pin("exe", exe, None, allow_unpinned=True) is False


def test_resolve_engine_artifacts_flag_env_and_missing(tmp_path, monkeypatch):
    mod = load_module()
    from types import SimpleNamespace

    exe = tmp_path / "weighted_alpha_complex.exe"
    exe.write_bytes(b"ENGINE-BINARY-BYTES")
    rad = tmp_path / "UFF.rad"
    rad.write_bytes(b"H 1.0\n")

    def args(**kw):
        base = dict(
            exe=None,
            radius_file=None,
            expected_exe_sha256=None,
            expected_radius_sha256=None,
            allow_unpinned_runtime=True,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_EXE", raising=False)
    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_RADIUS_FILE", raising=False)
    # Explicit flags resolve; unpinned -> pinned False.
    exe_path, rad_path, status = mod.resolve_engine_artifacts(args(exe=str(exe), radius_file=str(rad)))
    assert exe_path.name == "weighted_alpha_complex.exe" and rad_path.name == "UFF.rad"
    assert status["pinned"] is False
    # Environment fallback when flags absent.
    monkeypatch.setenv("MESA_WEIGHTED_ALPHA_EXE", str(exe))
    monkeypatch.setenv("MESA_WEIGHTED_ALPHA_RADIUS_FILE", str(rad))
    exe_env, rad_env, _ = mod.resolve_engine_artifacts(args())
    assert exe_env.name == "weighted_alpha_complex.exe" and rad_env.name == "UFF.rad"
    # Neither flag nor env -> ValueError.
    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_EXE", raising=False)
    monkeypatch.delenv("MESA_WEIGHTED_ALPHA_RADIUS_FILE", raising=False)
    try:
        mod.resolve_engine_artifacts(args())
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when neither flag nor env provided")
