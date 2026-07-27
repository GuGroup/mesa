from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from ase import Atoms
from ase.io import write

import slabuilder.weighted_alpha_backend as weighted_backend


ROOT = Path(__file__).resolve().parents[1]
PLACE_SCRIPT = (
    ROOT
    / ".codex"
    / "skills"
    / "place-surface-adsorbates"
    / "scripts"
    / "place_surface_adsorbates.py"
)
INSPECT_SCRIPT = (
    ROOT
    / ".codex"
    / "skills"
    / "inspect-surface-sites"
    / "scripts"
    / "inspect_surface_sites.py"
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "backend": "weighted_alpha",
        "site_backend": "weighted_alpha",
        "weighted_alpha_executable": "engine.exe",
        "weighted_alpha_radius_file": "UFF.rad",
        "weighted_alpha_expected_sha256": "a" * 64,
        "weighted_alpha_expected_radius_sha256": "b" * 64,
        "weighted_alpha_runtime_sha256_manifest": None,
        "weighted_alpha_expected_runtime_manifest_sha256": None,
        "weighted_alpha_allow_unpinned_runtime": False,
        "weighted_alpha_alpha_factor": None,
        "weighted_alpha_probe_radius": None,
        "weighted_alpha_placement_gap": None,
        "weighted_alpha_placement_step": None,
        "weighted_alpha_placement_max_distance": None,
        "weighted_alpha_timeout_s": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli"), (INSPECT_SCRIPT, "inspect_cli")],
)
def test_cli_config_preserves_zero_for_runtime_validation(script: Path, name: str) -> None:
    module = _load(script, name)
    config = module.weighted_alpha_config_from_args(
        _args(
            weighted_alpha_alpha_factor=0.0,
            weighted_alpha_probe_radius=0.0,
            weighted_alpha_placement_gap=0.0,
            weighted_alpha_placement_step=0.0,
            weighted_alpha_placement_max_distance=0.0,
            weighted_alpha_timeout_s=0.0,
        )
    )
    assert config.alpha_factor == 0.0
    assert config.probe_radius == 0.0
    assert config.placement_gap == 0.0
    assert config.placement_step == 0.0
    assert config.placement_max_distance == 0.0
    assert config.timeout_s == 0.0


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli_defaults"), (INSPECT_SCRIPT, "inspect_cli_defaults")],
)
def test_cli_config_uses_documented_defaults(script: Path, name: str) -> None:
    module = _load(script, name)
    config = module.weighted_alpha_config_from_args(_args())
    assert config.alpha_factor == 3.5
    assert config.probe_radius == 1.52
    assert config.placement_gap == 0.5
    assert config.placement_step == 0.0125
    assert config.placement_max_distance == 8.0
    assert config.timeout_s == 120.0


@pytest.mark.parametrize(
    ("script", "name", "backend_field"),
    [
        (PLACE_SCRIPT, "place_cli_auto", "backend"),
        (INSPECT_SCRIPT, "inspect_cli_acat", "site_backend"),
    ],
)
def test_nonweighted_backend_does_not_resolve_config(
    script: Path,
    name: str,
    backend_field: str,
) -> None:
    module = _load(script, name)
    args = _args()
    setattr(args, backend_field, "auto")
    assert module.weighted_alpha_config_from_args(args) is None


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli_missing"), (INSPECT_SCRIPT, "inspect_cli_missing")],
)
def test_explicit_cli_config_requires_both_paths(script: Path, name: str) -> None:
    module = _load(script, name)
    with pytest.raises(SystemExit, match="requires both"):
        module.weighted_alpha_config_from_args(
            _args(weighted_alpha_radius_file=None)
        )


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli_first_party"), (INSPECT_SCRIPT, "inspect_cli_first_party")],
)
def test_numeric_cli_overrides_use_first_party_runtime(
    monkeypatch: pytest.MonkeyPatch,
    script: Path,
    name: str,
) -> None:
    module = _load(script, name)
    marker = object()
    observed: dict[str, str] = {}

    def resolve(*, environ):
        observed.update(environ)
        return marker

    monkeypatch.setattr(weighted_backend, "resolve_weighted_alpha_config", resolve)
    result = module.weighted_alpha_config_from_args(
        _args(
            weighted_alpha_executable=None,
            weighted_alpha_radius_file=None,
            weighted_alpha_expected_sha256=None,
            weighted_alpha_expected_radius_sha256=None,
            weighted_alpha_alpha_factor=2.25,
            weighted_alpha_probe_radius=1.7,
        )
    )
    assert result is marker
    assert observed["MESA_WEIGHTED_ALPHA_ALPHA_FACTOR"] == "2.25"
    assert observed["MESA_WEIGHTED_ALPHA_PROBE_RADIUS"] == "1.7"


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli_pbc"), (INSPECT_SCRIPT, "inspect_cli_pbc")],
)
def test_weighted_cli_preserves_pbc_from_extxyz(
    tmp_path: Path, script: Path, name: str
) -> None:
    module = _load(script, name)
    path = tmp_path / "bulk.extxyz"
    atoms = Atoms("Pt", positions=[[0.0, 0.0, 0.0]], cell=[4.0, 4.0, 4.0], pbc=True)
    write(path, atoms)
    loaded = module.load_atoms(path, backend="weighted_alpha")
    assert loaded.pbc.tolist() == [True, True, True]


@pytest.mark.parametrize(
    ("script", "name"),
    [(PLACE_SCRIPT, "place_cli_pins"), (INSPECT_SCRIPT, "inspect_cli_pins")],
)
def test_cli_config_propagates_runtime_pins(script: Path, name: str) -> None:
    module = _load(script, name)
    config = module.weighted_alpha_config_from_args(
        _args(
            weighted_alpha_runtime_sha256_manifest="runtime.json",
            weighted_alpha_expected_runtime_manifest_sha256="c" * 64,
        )
    )
    assert config.expected_sha256 == "a" * 64
    assert config.expected_radius_sha256 == "b" * 64
    assert config.runtime_sha256_manifest == Path("runtime.json").resolve()
    assert config.expected_runtime_manifest_sha256 == "c" * 64
    assert config.allow_unpinned_runtime is False
