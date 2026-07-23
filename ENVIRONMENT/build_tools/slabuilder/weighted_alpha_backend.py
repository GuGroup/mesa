"""Strict external weighted-alpha backend for MESA surface-site generation.

The C++ executable remains an external, checksummed geometry provider.  This
module owns staging, process isolation, schema validation, source-index
remapping, surface filtering, and deterministic de-duplication.  It does not
place adsorbates; MESA's existing chemistry and placement layer remains the
single owner of that operation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

import numpy as np
from ase import Atoms
from ase.geometry import find_mic
from ase.io import read, write

EXPECTED_PBC = (True, True, False)
EXPECTED_MODE = "pbc_masked_image_aware"
DEFAULT_ALPHA_FACTOR = 3.5
DEFAULT_PROBE_RADIUS = 1.52
DEFAULT_PLACEMENT_GAP = 0.5
DEFAULT_PLACEMENT_STEP = 0.0125
DEFAULT_PLACEMENT_MAX_DISTANCE = 8.0
DEFAULT_TIMEOUT_S = 120.0
MAX_GRAPH_BYTES = 32 * 1024 * 1024
MAX_ENGINE_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_GRAPH_NODES = 100_000
MAX_GRAPH_EDGES = 500_000
MAX_JSON_DEPTH = 64
MAX_JSON_STRING_BYTES = 1024 * 1024
MAX_RUNTIME_MANIFEST_BYTES = 1024 * 1024
SEMANTIC_NODE_TYPES = {"P0", "P1", "P2"}
TYPE_RANK = {"P0": 0, "P1": 1, "P2": 2}


class WeightedAlphaError(RuntimeError):
    """Base error for the weighted-alpha backend."""


class WeightedAlphaConfigError(WeightedAlphaError):
    """Invalid or incomplete external-engine configuration."""


class WeightedAlphaSchemaError(WeightedAlphaError):
    """The engine output does not satisfy the pinned graph contract."""


class WeightedAlphaExecutionError(WeightedAlphaError):
    """External-engine process failure with retained diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        returncode: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        details = message
        if returncode is not None:
            details += f" (return code {returncode})"
        if stderr:
            details += f"\nstderr:\n{stderr}"
        super().__init__(details)


@dataclass(frozen=True)
class WeightedAlphaConfig:
    """Pinned external-engine configuration.

    ``alpha_factor`` is the weighted-alpha construction parameter and is not an
    adsorbate radius. ``probe_radius`` is a compatibility field name for the
    contact-anchor radius passed to C++ ``-a`` and used by Tool 4 placement.
    """

    executable: Path
    radius_file: Path
    alpha_factor: float = DEFAULT_ALPHA_FACTOR
    probe_radius: float = DEFAULT_PROBE_RADIUS
    placement_gap: float = DEFAULT_PLACEMENT_GAP
    placement_step: float = DEFAULT_PLACEMENT_STEP
    placement_max_distance: float = DEFAULT_PLACEMENT_MAX_DISTANCE
    timeout_s: float = DEFAULT_TIMEOUT_S
    expected_sha256: str | None = None
    expected_radius_sha256: str | None = None
    runtime_sha256_manifest: Path | None = None
    expected_runtime_manifest_sha256: str | None = None
    first_party_release: str | None = None
    mesa_base_commit: str | None = None
    private_source_manifest_sha256: str | None = None
    allow_unpinned_runtime: bool = False
    construction_mode: str = EXPECTED_MODE
    graph_filename: str = "weighted_alpha_graph_geompy_normals.json"

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", Path(self.executable).expanduser().resolve())
        object.__setattr__(self, "radius_file", Path(self.radius_file).expanduser().resolve())
        if self.runtime_sha256_manifest is not None:
            object.__setattr__(
                self,
                "runtime_sha256_manifest",
                Path(self.runtime_sha256_manifest).expanduser().resolve(),
            )


@dataclass(frozen=True)
class StagedSlab:
    path: Path
    atoms: Atoms
    engine_to_ase_index: tuple[int, ...]
    ase_to_engine_index: tuple[int, ...]


@dataclass(frozen=True)
class WeightedAlphaCandidate:
    engine_node_id: str
    position: np.ndarray
    site_kind: str
    coordination: int
    hollow_subtype: str | None
    source_atom_indices: tuple[int, ...]
    normal: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WeightedAlphaRun:
    graph: dict[str, Any]
    candidates: tuple[WeightedAlphaCandidate, ...]
    provenance: dict[str, Any]
    engine_to_ase_index: tuple[int, ...]
    stdout: str
    stderr: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_float(name: str, value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise WeightedAlphaConfigError(f"{name} must be a number, got {value!r}") from exc


def _parse_bool(name: str, value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise WeightedAlphaConfigError(f"{name} must be a boolean, got {value!r}")


def _validate_sha256(label: str, expected: str | None, path: Path) -> str | None:
    if expected is None:
        return None
    normalized = expected.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise WeightedAlphaConfigError(f"{label} must be 64 lowercase hex characters")
    actual = _sha256(path)
    if actual != normalized:
        raise WeightedAlphaConfigError(
            f"{label} mismatch: expected {normalized}, got {actual}"
        )
    return normalized


def _runtime_dlls(executable: Path) -> list[Path]:
    return sorted(
        (
            item for item in executable.parent.iterdir()
            if item.is_file() and item.suffix.lower() == ".dll"
        ),
        key=lambda item: item.name.lower(),
    )


def _load_runtime_sha256_manifest(path: Path) -> dict[str, str]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate runtime manifest key {key!r}")
            result[key] = value
        return result

    try:
        size = path.stat().st_size
        if size > MAX_RUNTIME_MANIFEST_BYTES:
            raise ValueError(
                f"runtime manifest is {size} bytes; limit is {MAX_RUNTIME_MANIFEST_BYTES}"
            )
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WeightedAlphaConfigError(f"cannot read runtime SHA-256 manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise WeightedAlphaConfigError("runtime SHA-256 manifest must be a JSON object")
    digest_payload: Mapping[str, Any] = payload
    if "schema_version" in payload:
        if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
            raise WeightedAlphaConfigError("unsupported runtime manifest schema_version")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            raise WeightedAlphaConfigError("release runtime manifest must contain an artifacts object")
        digest_payload = {
            name: digest
            for name, digest in artifacts.items()
            if isinstance(name, str) and name.lower().endswith(".dll")
        }
    result: dict[str, str] = {}
    for name, digest in digest_payload.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise WeightedAlphaConfigError("runtime SHA-256 manifest keys must be basenames")
        if not isinstance(digest, str):
            raise WeightedAlphaConfigError("runtime SHA-256 manifest values must be strings")
        normalized = digest.lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise WeightedAlphaConfigError(
                f"runtime SHA-256 manifest has invalid digest for {name!r}"
            )
        result[name] = normalized
    return result



def _verify_runtime_artifacts(config: WeightedAlphaConfig) -> None:
    _validate_sha256("weighted-alpha executable SHA-256", config.expected_sha256, config.executable)
    _validate_sha256("radius file SHA-256", config.expected_radius_sha256, config.radius_file)
    if config.runtime_sha256_manifest is not None:
        _validate_sha256(
            "runtime manifest SHA-256",
            config.expected_runtime_manifest_sha256,
            config.runtime_sha256_manifest,
        )
    dependencies = _runtime_dlls(config.executable)
    if config.runtime_sha256_manifest is None:
        return
    manifest = _load_runtime_sha256_manifest(config.runtime_sha256_manifest)
    expected_names = {item.name for item in dependencies}
    if set(manifest) != expected_names:
        raise WeightedAlphaConfigError(
            "runtime SHA-256 manifest entries must exactly match adjacent DLLs"
        )
    for dependency in dependencies:
        actual = _sha256(dependency)
        if actual != manifest[dependency.name]:
            raise WeightedAlphaConfigError(
                "runtime dependency SHA-256 mismatch for "
                f"{dependency.name}: expected {manifest[dependency.name]}, got {actual}"
            )


def _stage_runtime_bundle(
    config: WeightedAlphaConfig,
    workdir: Path,
) -> tuple[WeightedAlphaConfig, Path]:
    """Copy an audited runtime into a private, reverified execution directory."""

    if config.allow_unpinned_runtime:
        raise WeightedAlphaConfigError("unsafe unpinned runtimes are not staged as audited bundles")
    _verify_runtime_artifacts(config)
    runtime_dir = workdir / ".weighted_alpha_runtime"
    if runtime_dir.exists():
        if runtime_dir.is_symlink() or not runtime_dir.is_dir():
            raise WeightedAlphaConfigError("private runtime path is not a regular directory")
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    sources = [config.executable, config.radius_file, *_runtime_dlls(config.executable)]
    if config.runtime_sha256_manifest is not None:
        sources.append(config.runtime_sha256_manifest)
    names = [source.name for source in sources]
    if len(names) != len(set(names)):
        shutil.rmtree(runtime_dir)
        raise WeightedAlphaConfigError("runtime artifact basenames must be unique")
    try:
        for source in sources:
            shutil.copy2(source, runtime_dir / source.name)
        # Detect source mutation during the copy, then verify only the private copy used below.
        _verify_runtime_artifacts(config)
        staged = replace(
            config,
            executable=runtime_dir / config.executable.name,
            radius_file=runtime_dir / config.radius_file.name,
            runtime_sha256_manifest=(
                runtime_dir / config.runtime_sha256_manifest.name
                if config.runtime_sha256_manifest is not None
                else None
            ),
        )
        _verify_runtime_artifacts(staged)
        return staged, runtime_dir
    except BaseException:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        raise


def resolve_weighted_alpha_config(
    explicit: WeightedAlphaConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> WeightedAlphaConfig:
    """Resolve and validate explicit configuration or environment variables."""

    if explicit is None:
        env = os.environ if environ is None else environ
        executable_value = env.get("MESA_WEIGHTED_ALPHA_EXE")
        radius_value = env.get("MESA_WEIGHTED_ALPHA_RADIUS_FILE")
        if bool(executable_value) != bool(radius_value):
            missing = (
                "MESA_WEIGHTED_ALPHA_RADIUS_FILE"
                if executable_value
                else "MESA_WEIGHTED_ALPHA_EXE"
            )
            raise WeightedAlphaConfigError(
                f"{missing} is required when overriding the first-party weighted-alpha runtime"
            )

        runtime_manifest: Path | None
        if executable_value and radius_value:
            executable = Path(executable_value)
            radius_file = Path(radius_value)
            expected_sha256 = env.get("MESA_WEIGHTED_ALPHA_EXPECTED_SHA256")
            expected_radius_sha256 = env.get("MESA_WEIGHTED_ALPHA_EXPECTED_RADIUS_SHA256")
            runtime_manifest = (
                Path(env["MESA_WEIGHTED_ALPHA_RUNTIME_SHA256_MANIFEST"])
                if env.get("MESA_WEIGHTED_ALPHA_RUNTIME_SHA256_MANIFEST")
                else None
            )
            expected_runtime_manifest_sha256 = env.get(
                "MESA_WEIGHTED_ALPHA_EXPECTED_RUNTIME_MANIFEST_SHA256"
            )
            allow_unpinned_runtime = _parse_bool(
                "MESA_WEIGHTED_ALPHA_ALLOW_UNPINNED_RUNTIME",
                env.get("MESA_WEIGHTED_ALPHA_ALLOW_UNPINNED_RUNTIME", "false"),
            )
            first_party_release = None
            mesa_base_commit = None
            private_source_manifest_sha256 = None
        else:
            from slabuilder.weighted_alpha_runtime import (
                WeightedAlphaRuntimeError,
                resolve_first_party_runtime,
            )

            try:
                runtime = resolve_first_party_runtime(environ=env)
            except WeightedAlphaRuntimeError as exc:
                raise WeightedAlphaConfigError(
                    f"cannot resolve verified first-party weighted-alpha runtime: {exc}"
                ) from exc
            executable = runtime.executable
            radius_file = runtime.radius_file
            expected_sha256 = runtime.expected_executable_sha256
            expected_radius_sha256 = runtime.expected_radius_sha256
            runtime_manifest = runtime.runtime_manifest
            expected_runtime_manifest_sha256 = runtime.expected_runtime_manifest_sha256
            allow_unpinned_runtime = False
            first_party_release = runtime.release
            mesa_base_commit = runtime.mesa_base_commit
            private_source_manifest_sha256 = runtime.private_source_manifest_sha256

        explicit = WeightedAlphaConfig(
            executable=executable,
            radius_file=radius_file,
            alpha_factor=_parse_float(
                "MESA_WEIGHTED_ALPHA_ALPHA_FACTOR",
                env.get("MESA_WEIGHTED_ALPHA_ALPHA_FACTOR", str(DEFAULT_ALPHA_FACTOR)),
            ),
            probe_radius=_parse_float(
                "MESA_WEIGHTED_ALPHA_PROBE_RADIUS",
                env.get("MESA_WEIGHTED_ALPHA_PROBE_RADIUS", str(DEFAULT_PROBE_RADIUS)),
            ),
            placement_gap=_parse_float(
                "MESA_WEIGHTED_ALPHA_PLACEMENT_GAP",
                env.get("MESA_WEIGHTED_ALPHA_PLACEMENT_GAP", str(DEFAULT_PLACEMENT_GAP)),
            ),
            placement_step=_parse_float(
                "MESA_WEIGHTED_ALPHA_PLACEMENT_STEP",
                env.get("MESA_WEIGHTED_ALPHA_PLACEMENT_STEP", str(DEFAULT_PLACEMENT_STEP)),
            ),
            placement_max_distance=_parse_float(
                "MESA_WEIGHTED_ALPHA_PLACEMENT_MAX_DISTANCE",
                env.get(
                    "MESA_WEIGHTED_ALPHA_PLACEMENT_MAX_DISTANCE",
                    str(DEFAULT_PLACEMENT_MAX_DISTANCE),
                ),
            ),
            timeout_s=_parse_float(
                "MESA_WEIGHTED_ALPHA_TIMEOUT_S",
                env.get("MESA_WEIGHTED_ALPHA_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)),
            ),
            expected_sha256=expected_sha256,
            expected_radius_sha256=expected_radius_sha256,
            runtime_sha256_manifest=runtime_manifest,
            expected_runtime_manifest_sha256=expected_runtime_manifest_sha256,
            first_party_release=first_party_release,
            mesa_base_commit=mesa_base_commit,
            private_source_manifest_sha256=private_source_manifest_sha256,
            allow_unpinned_runtime=allow_unpinned_runtime,
        )

    config = explicit
    if not config.executable.is_file():
        raise WeightedAlphaConfigError(
            f"weighted-alpha executable does not exist: {config.executable}"
        )
    if not config.radius_file.is_file():
        raise WeightedAlphaConfigError(f"radius file does not exist: {config.radius_file}")
    numeric_values = {
        "alpha_factor": config.alpha_factor,
        "probe_radius": config.probe_radius,
        "placement_gap": config.placement_gap,
        "placement_step": config.placement_step,
        "placement_max_distance": config.placement_max_distance,
        "timeout_s": config.timeout_s,
    }
    for name, value in numeric_values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise WeightedAlphaConfigError(f"{name} must be a finite number")
    if config.alpha_factor <= 0.0:
        raise WeightedAlphaConfigError("alpha_factor must be positive")
    if config.probe_radius <= 0.0:
        raise WeightedAlphaConfigError("probe_radius must be positive")
    if config.placement_gap < 0.0:
        raise WeightedAlphaConfigError("placement_gap must be non-negative")
    if config.placement_step <= 0.0 or config.placement_max_distance <= 0.0:
        raise WeightedAlphaConfigError("placement step and maximum distance must be positive")
    if config.timeout_s <= 0.0:
        raise WeightedAlphaConfigError("timeout_s must be positive")
    if config.construction_mode != EXPECTED_MODE:
        raise WeightedAlphaConfigError(
            f"construction_mode must remain pinned to {EXPECTED_MODE!r}"
        )
    graph_name = Path(config.graph_filename)
    normalized_graph_name = config.graph_filename.rstrip(" .").casefold()
    reserved_graph_names = {
        ".",
        "..",
        "slab.poscar",
        "weighted_alpha.stdout.log",
        "weighted_alpha.stderr.log",
        ".weighted_alpha_runtime",
    }
    device_stem = normalized_graph_name.split(".", 1)[0]
    windows_device_names = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{number}"
        for prefix in ("com", "lpt")
        for number in range(1, 10)
    }
    if (
        graph_name.is_absolute()
        or graph_name.name != config.graph_filename
        or normalized_graph_name in reserved_graph_names
        or device_stem in windows_device_names
        or normalized_graph_name != config.graph_filename.casefold()
    ):
        raise WeightedAlphaConfigError("graph_filename must be a non-reserved plain basename")
    if type(config.allow_unpinned_runtime) is not bool:
        raise WeightedAlphaConfigError("allow_unpinned_runtime must be boolean")
    source_provenance = (
        config.first_party_release,
        config.mesa_base_commit,
        config.private_source_manifest_sha256,
    )
    if any(value is not None for value in source_provenance):
        if not all(isinstance(value, str) and value for value in source_provenance):
            raise WeightedAlphaConfigError("first-party source provenance must be complete")
        assert config.mesa_base_commit is not None
        assert config.private_source_manifest_sha256 is not None
        if (
            len(config.mesa_base_commit) != 40
            or any(character not in "0123456789abcdef" for character in config.mesa_base_commit)
            or len(config.private_source_manifest_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in config.private_source_manifest_sha256
            )
        ):
            raise WeightedAlphaConfigError("first-party source provenance hashes are invalid")
    if not config.allow_unpinned_runtime and config.expected_sha256 is None:
        raise WeightedAlphaConfigError(
            "expected_sha256 is required; set allow_unpinned_runtime=True only for unsafe local development"
        )
    if not config.allow_unpinned_runtime and config.expected_radius_sha256 is None:
        raise WeightedAlphaConfigError(
            "expected_radius_sha256 is required; set allow_unpinned_runtime=True only for unsafe local development"
        )

    dependencies = _runtime_dlls(config.executable)
    if dependencies and config.runtime_sha256_manifest is None and not config.allow_unpinned_runtime:
        raise WeightedAlphaConfigError(
            "a runtime SHA-256 manifest is required for adjacent DLL dependencies"
        )
    if (
        config.runtime_sha256_manifest is not None
        and config.expected_runtime_manifest_sha256 is None
        and not config.allow_unpinned_runtime
    ):
        raise WeightedAlphaConfigError(
            "expected_runtime_manifest_sha256 is required when a runtime manifest is used"
        )
    _verify_runtime_artifacts(config)
    return config


def _require_pbc110(atoms: Atoms) -> None:
    actual = tuple(bool(value) for value in atoms.pbc)
    if actual != EXPECTED_PBC:
        raise WeightedAlphaConfigError(
            "weighted-alpha MESA phase-1 supports only pbc=[True, True, False]; "
            f"received {list(actual)}"
        )


def _require_axis_aligned_surface(atoms: Atoms) -> None:
    normal = np.cross(atoms.cell.array[0], atoms.cell.array[1])
    magnitude = float(np.linalg.norm(normal))
    if magnitude <= 1.0e-12:
        raise WeightedAlphaConfigError("slab cell a/b vectors do not define a surface")
    normal /= magnitude
    if not np.allclose(normal, [0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-8):
        raise WeightedAlphaConfigError(
            "weighted-alpha MESA phase-1 requires a flat axis-aligned +z surface"
        )


def stage_slab_for_engine(atoms: Atoms, path: str | Path) -> StagedSlab:
    """Write a grouped VASP file and preserve a tested atom-index bijection."""

    _require_pbc110(atoms)
    _require_axis_aligned_surface(atoms)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    from slabuilder.utils import stable_element_group_order

    symbols = atoms.get_chemical_symbols()
    engine_to_ase = tuple(stable_element_group_order(symbols))
    ase_to_engine_values = [0] * len(atoms)
    for engine_index, ase_index in enumerate(engine_to_ase):
        ase_to_engine_values[ase_index] = engine_index
    ase_to_engine = tuple(ase_to_engine_values)

    staged_atoms = atoms[list(engine_to_ase)].copy()
    staged_atoms.pbc = EXPECTED_PBC
    write(destination, staged_atoms, format="vasp", direct=False, sort=False, vasp5=True)

    roundtrip = read(destination, format="vasp")
    if isinstance(roundtrip, list):
        raise WeightedAlphaConfigError("POSCAR round-trip returned multiple structures")
    if roundtrip.get_chemical_symbols() != staged_atoms.get_chemical_symbols():
        raise WeightedAlphaConfigError("POSCAR round-trip changed chemical-symbol ordering")
    if not np.allclose(roundtrip.positions, staged_atoms.positions, rtol=0.0, atol=1.0e-8):
        raise WeightedAlphaConfigError("POSCAR round-trip changed atom positions")
    if not np.allclose(roundtrip.cell.array, staged_atoms.cell.array, rtol=0.0, atol=1.0e-8):
        raise WeightedAlphaConfigError("POSCAR round-trip changed the cell")
    if sorted(engine_to_ase) != list(range(len(atoms))) or sorted(ase_to_engine) != list(
        range(len(atoms))
    ):
        raise WeightedAlphaConfigError("engine/ASE atom-index map is not bijective")

    return StagedSlab(
        path=destination,
        atoms=staged_atoms,
        engine_to_ase_index=engine_to_ase,
        ase_to_engine_index=ase_to_engine,
    )


def _format_float(value: float) -> str:
    return format(float(value), ".15g")


def build_engine_command(
    config: WeightedAlphaConfig,
    slab_path: str | Path,
    staged_input_sha256: str,
) -> list[str]:
    """Construct the pinned argument vector; never a shell command string."""

    normalized_input_sha256 = staged_input_sha256.lower()
    if len(normalized_input_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_input_sha256
    ):
        raise WeightedAlphaConfigError("staged_input_sha256 must be 64 hex characters")
    return [
        str(config.executable),
        "-f",
        str(Path(slab_path)),
        "-a",
        _format_float(config.probe_radius),
        "--alpha-factor",
        _format_float(config.alpha_factor),
        "--pbc",
        "1,1,0",
        "--voro-construction-mode",
        config.construction_mode,
        "--radius-file",
        str(config.radius_file),
        "--placement-gap",
        _format_float(config.placement_gap),
        "--placement-step",
        _format_float(config.placement_step),
        "--placement-max-distance",
        _format_float(config.placement_max_distance),
        "--input-sha256",
        normalized_input_sha256,
        "--emit-geompy-normals",
    ]


def _require_finite_vector(node: Mapping[str, Any], key: str, node_id: str) -> np.ndarray:
    value = node.get(key)
    if not isinstance(value, list) or len(value) != 3:
        raise WeightedAlphaSchemaError(f"{node_id}.{key} must be a length-3 list")
    if any(
        isinstance(component, bool) or type(component) not in {int, float}
        for component in value
    ):
        raise WeightedAlphaSchemaError(f"{node_id}.{key} must contain JSON numbers")
    vector = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(vector)):
        raise WeightedAlphaSchemaError(f"{node_id}.{key} must be finite")
    return vector


def _load_graph_and_sha256(path: str | Path) -> tuple[dict[str, Any], str]:
    """Load and hash the same bounded strict-JSON byte sequence exactly once."""

    graph_path = Path(path)

    def reject_constant(token: str) -> None:
        raise ValueError(f"nonfinite JSON constant {token!r}")

    def parse_finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(f"nonfinite JSON number {token!r}")
        return value

    def parse_bounded_int(token: str) -> int:
        value = int(token)
        if value < -(2**63) or value > 2**63 - 1:
            raise ValueError(f"JSON integer is outside the signed 64-bit range: {token[:80]!r}")
        return value

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if len(key.encode("utf-8")) > MAX_JSON_STRING_BYTES:
                raise ValueError(f"JSON object key exceeds {MAX_JSON_STRING_BYTES} bytes")
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        with graph_path.open("rb") as handle:
            raw = handle.read(MAX_GRAPH_BYTES + 1)
        if len(raw) > MAX_GRAPH_BYTES:
            raise ValueError(
                f"graph exceeds the {MAX_GRAPH_BYTES}-byte limit"
            )
        text = raw.decode("utf-8")
        graph = json.loads(
            text,
            parse_constant=reject_constant,
            parse_float=parse_finite_float,
            parse_int=parse_bounded_int,
            object_pairs_hook=reject_duplicate_keys,
        )
        stack: list[tuple[Any, int]] = [(graph, 1)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError(f"JSON nesting depth exceeds {MAX_JSON_DEPTH}")
            if isinstance(value, str) and len(value.encode("utf-8")) > MAX_JSON_STRING_BYTES:
                raise ValueError(f"JSON string exceeds {MAX_JSON_STRING_BYTES} bytes")
            if isinstance(value, dict):
                stack.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                stack.extend((item, depth + 1) for item in value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError, OverflowError) as exc:
        raise WeightedAlphaSchemaError(f"cannot parse weighted-alpha graph: {exc}") from exc
    return validate_graph(graph), hashlib.sha256(raw).hexdigest()


def load_graph(path: str | Path) -> dict[str, Any]:
    """Load bounded strict JSON, rejecting duplicates and all nonfinite numbers."""

    graph, _ = _load_graph_and_sha256(path)
    return graph


def validate_graph(graph: Any) -> dict[str, Any]:
    """Validate the pinned additive graph contract and semantic node fields."""

    if not isinstance(graph, dict):
        raise WeightedAlphaSchemaError("weighted-alpha graph must be a JSON object")
    expected_envelope = {
        "directed": False,
        "multigraph": False,
        "graph_type": "undirected_hierarchical",
    }
    for field_name, expected_value in expected_envelope.items():
        actual_value = graph.get(field_name)
        if type(actual_value) is not type(expected_value) or actual_value != expected_value:
            raise WeightedAlphaSchemaError(
                f"graph {field_name} must be {expected_value!r}"
            )
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    metadata = graph.get("metadata")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(metadata, dict):
        raise WeightedAlphaSchemaError("graph must contain list nodes/edges and object metadata")
    if len(nodes) > MAX_GRAPH_NODES or len(edges) > MAX_GRAPH_EDGES:
        raise WeightedAlphaSchemaError(
            f"graph exceeds node/edge limits ({MAX_GRAPH_NODES}/{MAX_GRAPH_EDGES})"
        )
    if metadata.get("geometry_schema_version") != "pbc_debug_v1":
        raise WeightedAlphaSchemaError(
            "graph geometry_schema_version must be 'pbc_debug_v1'"
        )
    if metadata.get("geometry_uses_full_cell_matrix") is not True:
        raise WeightedAlphaSchemaError("graph geometry_uses_full_cell_matrix must be true")
    unique_atom_count = metadata.get("unique_atom_count")
    if type(unique_atom_count) is not int or unique_atom_count < 0:
        raise WeightedAlphaSchemaError("graph unique_atom_count must be a non-negative integer")
    metadata_cell = metadata.get("cell")
    if (
        not isinstance(metadata_cell, list)
        or len(metadata_cell) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in metadata_cell)
        or any(
            isinstance(component, bool) or type(component) not in {int, float}
            for row in metadata_cell
            for component in row
        )
    ):
        raise WeightedAlphaSchemaError("graph metadata.cell must be a finite 3x3 matrix")
    try:
        cell_array = np.asarray(metadata_cell, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WeightedAlphaSchemaError("graph metadata.cell must contain finite numbers") from exc
    if not np.all(np.isfinite(cell_array)):
        raise WeightedAlphaSchemaError("graph metadata.cell must contain finite numbers")
    staged_input_sha256 = metadata.get("staged_input_sha256")
    if (
        not isinstance(staged_input_sha256, str)
        or len(staged_input_sha256) != 64
        or any(character not in "0123456789abcdef" for character in staged_input_sha256.lower())
    ):
        raise WeightedAlphaSchemaError("graph staged_input_sha256 must be 64 hex characters")

    raw_pbc = metadata.get("pbc")
    if (
        not isinstance(raw_pbc, list)
        or len(raw_pbc) != 3
        or any(type(value) is not bool for value in raw_pbc)
    ):
        raise WeightedAlphaSchemaError(
            "graph metadata pbc must contain exactly three JSON booleans"
        )
    pbc = tuple(raw_pbc)
    if pbc != EXPECTED_PBC:
        raise WeightedAlphaSchemaError(
            f"graph metadata pbc must be {list(EXPECTED_PBC)}, got {list(pbc)}"
        )
    requested_mode = metadata.get("requested_construction_mode")
    resolved_mode = metadata.get("voro_construction_mode")
    if requested_mode != EXPECTED_MODE:
        raise WeightedAlphaSchemaError(
            f"graph requested construction mode must be {EXPECTED_MODE!r}, got {requested_mode!r}"
        )
    allowed_resolved_modes = {
        EXPECTED_MODE,
        "pbc_masked_mixed_periodic_image_aware",
    }
    if resolved_mode not in allowed_resolved_modes:
        raise WeightedAlphaSchemaError(
            "graph resolved construction mode must be the pinned mode or its mixed-periodic "
            f"implementation alias, got {resolved_mode!r}"
        )

    expected = {"P0": ("top", 1), "P1": ("bridge", 2), "P2": ("hollow", 3)}
    seen_ids: set[str] = set()
    node_types: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise WeightedAlphaSchemaError("each graph node must be an object")
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id:
            raise WeightedAlphaSchemaError("every graph node requires a non-empty string id")
        if node_id in seen_ids:
            raise WeightedAlphaSchemaError(f"duplicate graph node id: {node_id}")
        seen_ids.add(node_id)
        if not isinstance(node_type, str) or node_type not in {"P0", "P1", "P2", "P3"}:
            raise WeightedAlphaSchemaError(f"unknown node type {node_type!r} for {node_id}")
        node_types[node_id] = node_type
        _require_finite_vector(node, "position", node_id)
        atoms = node.get("atoms")
        if not isinstance(atoms, list) or not all(
            isinstance(index, int) and not isinstance(index, bool) and index >= 0
            for index in atoms
        ):
            raise WeightedAlphaSchemaError(f"{node_id}.atoms must contain only non-negative ints")
        if len(atoms) != len(set(atoms)):
            raise WeightedAlphaSchemaError(f"{node_id}.atoms must not contain duplicates")
        if node_type == "P0" and len(atoms) != 1:
            raise WeightedAlphaSchemaError(f"{node_id}.atoms must contain exactly 1 source atom")
        if node_type == "P1" and not (1 <= len(atoms) <= 2):
            raise WeightedAlphaSchemaError(
                f"{node_id}.atoms must contain one or two unique source atoms"
            )
        if node_type == "P2" and not (1 <= len(atoms) <= 3):
            raise WeightedAlphaSchemaError(
                f"{node_id}.atoms must contain one to three unique source atoms"
            )
        if node_type == "P3" and not (1 <= len(atoms) <= 4):
            raise WeightedAlphaSchemaError(
                f"{node_id}.atoms must contain one to four unique source atoms"
            )
        classification = node.get("classification")
        allowed_classifications = {"atom"} if node_type == "P0" else {"regular", "interior", "exterior"}
        if not isinstance(classification, str) or classification not in allowed_classifications:
            raise WeightedAlphaSchemaError(
                f"{node_id}.classification must be one of {sorted(allowed_classifications)}"
            )
        placement = node.get("placement")
        if placement is not None:
            if not isinstance(placement, dict):
                raise WeightedAlphaSchemaError(f"{node_id}.placement must be an object or null")
            for vector_key in ("anchor_position", "direction", "position"):
                _require_finite_vector(placement, vector_key, f"{node_id}.placement")
            if float(np.linalg.norm(np.asarray(placement["direction"], dtype=float))) <= 1.0e-12:
                raise WeightedAlphaSchemaError(f"{node_id}.placement.direction must be nonzero")
            for numeric_key in (
                "distance",
                "clearance_at_position",
                "target_clearance",
                "precursor_radius",
                "gap",
            ):
                value = placement.get(numeric_key)
                if isinstance(value, bool) or type(value) not in {int, float}:
                    raise WeightedAlphaSchemaError(
                        f"{node_id}.placement.{numeric_key} must be a finite non-negative number"
                    )
                numeric_value = float(cast(int | float, value))
                if not math.isfinite(numeric_value) or numeric_value < 0.0:
                    raise WeightedAlphaSchemaError(
                        f"{node_id}.placement.{numeric_key} must be a finite non-negative number"
                    )
            reached = placement.get("target_clearance_reached")
            if type(reached) is not bool:
                raise WeightedAlphaSchemaError(
                    f"{node_id}.placement.target_clearance_reached must be boolean"
                )
            status = placement.get("status")
            if placement.get("distance_type") != "ray_clearance" or status not in {
                "target_clearance_reached",
                "max_clearance_fallback",
            }:
                raise WeightedAlphaSchemaError(f"{node_id}.placement policy is invalid")
            if reached is not (status == "target_clearance_reached"):
                raise WeightedAlphaSchemaError(
                    f"{node_id}.placement status/reached fields are inconsistent"
                )
        if node_type == "P3":
            continue
        expected_kind, expected_coordination = expected[node_type]
        if node.get("site_kind") != expected_kind:
            raise WeightedAlphaSchemaError(
                f"{node_id}.site_kind must be {expected_kind!r}, got {node.get('site_kind')!r}"
            )
        coordination = node.get("coordination")
        if type(coordination) is not int or coordination != expected_coordination:
            raise WeightedAlphaSchemaError(
                f"{node_id}.coordination must be {expected_coordination}"
            )
        if "hollow_subtype" not in node:
            raise WeightedAlphaSchemaError(f"{node_id}.hollow_subtype is required")
        if "subsurface_ref_dist" not in node:
            raise WeightedAlphaSchemaError(f"{node_id}.subsurface_ref_dist is required")
        subsurface_distance = node.get("subsurface_ref_dist")
        if subsurface_distance is not None and (
            not isinstance(subsurface_distance, (int, float))
            or isinstance(subsurface_distance, bool)
            or not math.isfinite(float(subsurface_distance))
        ):
            raise WeightedAlphaSchemaError(
                f"{node_id}.subsurface_ref_dist must be a finite number or null"
            )
        normal_key = "normal" if node_type == "P2" else "surface_normal"
        present_key = "has_normal" if node_type == "P2" else "has_surface_normal"
        if type(node.get(present_key)) is not bool:
            raise WeightedAlphaSchemaError(f"{node_id}.{present_key} must be boolean")
        normal = None
        if normal_key in node:
            normal = _require_finite_vector(node, normal_key, node_id)
        if node[present_key]:
            if normal is None:
                raise WeightedAlphaSchemaError(f"{node_id}.{normal_key} is required")
            if float(np.linalg.norm(normal)) <= 1.0e-12:
                raise WeightedAlphaSchemaError(f"{node_id}.{normal_key} must be nonzero")
        if node_type in {"P1", "P2"}:
            atom_images = node.get("atoms_with_images")
            expected_image_count = 2 if node_type == "P1" else 3
            legacy_two_source_p1 = node_type == "P1" and atom_images is None and len(atoms) == 2
            if not legacy_two_source_p1:
                if not isinstance(atom_images, list) or len(atom_images) != expected_image_count:
                    raise WeightedAlphaSchemaError(
                        f"{node_id}.atoms_with_images must contain {expected_image_count} image identities"
                    )
                image_identities: set[tuple[int, tuple[int, int, int]]] = set()
                for image in atom_images:
                    if not isinstance(image, dict):
                        raise WeightedAlphaSchemaError(
                            f"{node_id}.atoms_with_images entries must be objects"
                        )
                    atom_id = image.get("atom_id")
                    offset = image.get("image_offset")
                    if not isinstance(atom_id, int) or isinstance(atom_id, bool) or atom_id < 0:
                        raise WeightedAlphaSchemaError(
                            f"{node_id}.atoms_with_images atom_id must be a non-negative int"
                        )
                    if (
                        not isinstance(offset, list)
                        or len(offset) != 3
                        or any(not isinstance(value, int) or isinstance(value, bool) for value in offset)
                        or offset[2] != 0
                    ):
                        raise WeightedAlphaSchemaError(
                            f"{node_id}.atoms_with_images image_offset must be three ints with z=0"
                        )
                    image_identities.add((atom_id, tuple(offset)))
                if len(image_identities) != expected_image_count:
                    raise WeightedAlphaSchemaError(
                        f"{node_id}.atoms_with_images identities must be unique"
                    )
                if {atom_id for atom_id, _ in image_identities} != set(atoms):
                    raise WeightedAlphaSchemaError(
                        f"{node_id}.atoms_with_images atom ids must match node atoms"
                    )
        if node_type == "P2":
            hollow_subtype = node.get("hollow_subtype")
            if not isinstance(hollow_subtype, str) or hollow_subtype not in {
                "fcc",
                "hcp",
                "undefined",
            }:
                raise WeightedAlphaSchemaError(
                    f"{node_id}.hollow_subtype must be 'fcc', 'hcp', or 'undefined'"
                )
            if hollow_subtype == "undefined" and subsurface_distance is not None:
                raise WeightedAlphaSchemaError(
                    f"{node_id}.undefined hollow_subtype requires null subsurface_ref_dist"
                )
            if hollow_subtype in {"fcc", "hcp"} and subsurface_distance is None:
                raise WeightedAlphaSchemaError(
                    f"{node_id}.{hollow_subtype} hollow_subtype requires a finite subsurface_ref_dist"
                )
            if type(node.get("topology_valid_for_benchmark")) is not bool:
                raise WeightedAlphaSchemaError(
                    f"{node_id}.topology_valid_for_benchmark must be boolean"
                )
            if type(node.get("benchmark_blocking")) is not bool:
                raise WeightedAlphaSchemaError(f"{node_id}.benchmark_blocking must be boolean")
        elif node.get("hollow_subtype") is not None:
            raise WeightedAlphaSchemaError(f"{node_id}.hollow_subtype must be null")

    for edge in edges:
        if not isinstance(edge, dict):
            raise WeightedAlphaSchemaError("each graph edge must be an object")
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise WeightedAlphaSchemaError("graph edge requires string source/target")
        if source not in seen_ids or target not in seen_ids:
            raise WeightedAlphaSchemaError(f"dangling graph edge {source!r}->{target!r}")
        relationship = edge.get("relationship")
        weight = edge.get("weight")
        allowed_edge_types = {
            ("contains", "P3", "P2"),
            ("contains", "P3", "P1"),
            ("contains", "P2", "P1"),
            ("endpoint", "P1", "P0"),
        }
        edge_type = (relationship, node_types[source], node_types[target])
        if type(weight) is not int or weight != 1 or edge_type not in allowed_edge_types:
            raise WeightedAlphaSchemaError(
                "graph edge must match a pinned relationship/source/target type with integer weight 1"
            )
    return graph


def _surface_normal(atoms: Atoms) -> np.ndarray:
    normal = np.cross(atoms.cell.array[0], atoms.cell.array[1])
    magnitude = float(np.linalg.norm(normal))
    if not math.isfinite(magnitude) or magnitude <= 1.0e-12:
        raise WeightedAlphaConfigError("slab cell a/b vectors do not define a surface normal")
    return normal / magnitude


def _surface_layers(atoms: Atoms, gap: float = 0.8) -> list[list[int]]:
    normal = _surface_normal(atoms)
    heights = np.asarray(atoms.positions, dtype=float) @ normal
    order = np.argsort(heights, kind="stable")
    if len(order) == 0:
        return []
    layers: list[list[int]] = [[int(order[0])]]
    for raw_index in order[1:]:
        index = int(raw_index)
        layer_min = heights[layers[-1][0]]
        if heights[index] - layer_min > gap:
            layers.append([index])
        else:
            layers[-1].append(index)
    return layers


def _top_layer_indices(atoms: Atoms, gap: float = 0.8) -> set[int]:
    layers = _surface_layers(atoms, gap)
    return set(layers[-1]) if layers else set()



def _validate_graph_against_staged_input(
    graph: Mapping[str, Any],
    staged_atoms: Atoms,
    expected_staged_input_sha256: str | None,
    expected_config: WeightedAlphaConfig | None = None,
) -> None:
    metadata = graph["metadata"]
    if metadata["unique_atom_count"] != len(staged_atoms):
        raise WeightedAlphaSchemaError(
            "graph unique_atom_count does not match the staged slab atom count"
        )
    if not np.allclose(
        np.asarray(metadata["cell"], dtype=float),
        np.asarray(staged_atoms.cell.array, dtype=float),
        rtol=0.0,
        atol=5.0e-5,
    ):
        raise WeightedAlphaSchemaError("graph metadata.cell does not match the staged slab cell")
    if expected_staged_input_sha256 is not None:
        normalized = expected_staged_input_sha256.lower()
        if metadata["staged_input_sha256"].lower() != normalized:
            raise WeightedAlphaSchemaError(
                "graph staged_input_sha256 does not match the exact staged slab input"
            )
    if expected_config is not None:
        expected_parameters = {
            "alpha_parameter": expected_config.alpha_factor,
            "placement_precursor_radius": expected_config.probe_radius,
            "placement_gap": expected_config.placement_gap,
            "placement_step": expected_config.placement_step,
            "placement_max_distance": expected_config.placement_max_distance,
        }
        for key, expected_value in expected_parameters.items():
            actual_value = metadata.get(key)
            if (
                isinstance(actual_value, bool)
                or type(actual_value) not in {int, float}
                or not math.isfinite(float(actual_value))
                or not math.isclose(float(actual_value), float(expected_value), rel_tol=0.0, abs_tol=1.0e-12)
            ):
                raise WeightedAlphaSchemaError(
                    f"graph metadata.{key} does not match the requested run configuration"
                )

def _validated_candidate_placement(
    node: Mapping[str, Any],
    position: np.ndarray,
    normal: np.ndarray,
    graph: Mapping[str, Any],
    atoms: Atoms,
    expected_config: WeightedAlphaConfig | None,
) -> dict[str, Any] | None:
    node_id = str(node.get("id"))
    placement = node.get("placement")
    if not isinstance(placement, dict):
        raise WeightedAlphaSchemaError(f"{node_id}.placement is required for an accepted candidate")

    anchor = _require_finite_vector(placement, "anchor_position", f"{node_id}.placement")
    if float(np.linalg.norm(_minimum_image_delta(position, anchor, atoms))) > 1.0e-8:
        raise WeightedAlphaSchemaError(
            f"{node_id}.placement.anchor_position is not periodic-equivalent to node.position"
        )

    direction = _require_finite_vector(placement, "direction", f"{node_id}.placement")
    direction_magnitude = float(np.linalg.norm(direction))
    if not math.isclose(direction_magnitude, 1.0, rel_tol=0.0, abs_tol=1.0e-6):
        raise WeightedAlphaSchemaError(f"{node_id}.placement.direction must be normalized")
    direction = direction / direction_magnitude
    if not np.allclose(direction, normal, rtol=0.0, atol=1.0e-6):
        raise WeightedAlphaSchemaError(
            f"{node_id}.placement.direction does not match the accepted outward normal"
        )

    metadata = graph.get("metadata")
    if not isinstance(metadata, dict):
        raise WeightedAlphaSchemaError("graph metadata must be an object")
    expected_radius = (
        expected_config.probe_radius
        if expected_config is not None
        else metadata.get("placement_precursor_radius")
    )
    expected_gap = (
        expected_config.placement_gap
        if expected_config is not None
        else metadata.get("placement_gap")
    )
    for field_name, actual, expected in (
        ("precursor_radius", placement.get("precursor_radius"), expected_radius),
        ("gap", placement.get("gap"), expected_gap),
    ):
        if (
            isinstance(expected, bool)
            or type(expected) not in {int, float}
            or isinstance(actual, bool)
            or type(actual) not in {int, float}
            or not math.isclose(
                float(cast(int | float, actual)),
                float(cast(int | float, expected)),
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        ):
            raise WeightedAlphaSchemaError(
                f"{node_id}.placement.{field_name} does not match the requested graph parameter"
            )

    radius = float(cast(int | float, placement["precursor_radius"]))
    gap = float(cast(int | float, placement["gap"]))
    target_clearance = float(cast(int | float, placement["target_clearance"]))
    if not math.isclose(target_clearance, radius + gap, rel_tol=0.0, abs_tol=1.0e-12):
        raise WeightedAlphaSchemaError(
            f"{node_id}.placement.target_clearance must equal precursor_radius + gap"
        )
    clearance = float(cast(int | float, placement["clearance_at_position"]))
    if (
        placement.get("target_clearance_reached") is not True
        or placement.get("status") != "target_clearance_reached"
        or clearance + 1.0e-12 < target_clearance
    ):
        return None

    distance = float(cast(int | float, placement["distance"]))
    ray_position = _require_finite_vector(placement, "position", f"{node_id}.placement")
    expected_position = anchor + direction * distance
    if float(np.linalg.norm(_minimum_image_delta(expected_position, ray_position, atoms))) > 2.0e-4:
        raise WeightedAlphaSchemaError(
            f"{node_id}.placement.position does not match anchor_position + direction * distance"
        )
    return dict(placement)


def extract_candidates(
    graph: Any,
    staged_atoms: Atoms,
    engine_to_ase_index: Sequence[int],
    *,
    expected_staged_input_sha256: str | None = None,
    expected_config: WeightedAlphaConfig | None = None,
    include_undefined_hollow_precursors: bool = False,
) -> list[WeightedAlphaCandidate]:
    """Convert valid open-max P0/P1/P2 nodes to MESA-neutral candidates."""

    graph = validate_graph(graph)
    _validate_graph_against_staged_input(
        graph, staged_atoms, expected_staged_input_sha256, expected_config
    )
    if len(engine_to_ase_index) != len(staged_atoms) or sorted(engine_to_ase_index) != list(
        range(len(staged_atoms))
    ):
        raise WeightedAlphaSchemaError("engine_to_ase_index must be a complete bijection")

    surface_layers = _surface_layers(staged_atoms)
    top_engine_indices = set(surface_layers[-1]) if surface_layers else set()
    if len(surface_layers) > 1:
        complete_layer_population = max(len(layer) for layer in surface_layers[:-1])
        if len(top_engine_indices) != complete_layer_population:
            raise WeightedAlphaConfigError(
                "weighted-alpha phase-1 rejects stepped or incomplete upper terraces"
            )
    outward = _surface_normal(staged_atoms)
    atom_heights = np.asarray(staged_atoms.positions, dtype=float) @ outward
    top_heights = [float(atom_heights[index]) for index in top_engine_indices]
    if top_heights and max(top_heights) - min(top_heights) > 0.25:
        raise WeightedAlphaConfigError(
            "weighted-alpha phase-1 rejects corrugated top layers with height spread > 0.25 A"
        )

    candidates: list[WeightedAlphaCandidate] = []
    for node in graph["nodes"]:
        node_type = node.get("type")
        if node_type not in SEMANTIC_NODE_TYPES:
            continue
        source_engine = tuple(node["atoms"])
        if (
            node_type == "P2"
            and node.get("hollow_subtype") == "undefined"
            and not include_undefined_hollow_precursors
        ):
            continue
        if not source_engine:
            continue
        if node_type == "P1":
            images = node.get("atoms_with_images") or []
            if images:
                image_identities = {
                    (int(image["atom_id"]), tuple(image["image_offset"])) for image in images
                }
                image_atom_ids = {identity[0] for identity in image_identities}
                if len(image_identities) != 2 or set(source_engine) != image_atom_ids:
                    continue
            elif len(source_engine) != 2:
                continue
        if node_type == "P2":
            image_atom_ids = {int(image["atom_id"]) for image in node["atoms_with_images"]}
            if set(source_engine) != image_atom_ids:
                continue
        if any(index >= len(staged_atoms) for index in source_engine):
            raise WeightedAlphaSchemaError(f"{node['id']} contains an out-of-range atom index")
        if not set(source_engine).issubset(top_engine_indices):
            continue
        if node_type in {"P1", "P2"} and node.get("classification") != "regular":
            continue
        if node_type == "P2" and (
            node.get("topology_valid_for_benchmark") is not True
            or bool(node.get("benchmark_blocking", False))
        ):
            continue

        normal_key = "normal" if node_type == "P2" else "surface_normal"
        present_key = "has_normal" if node_type == "P2" else "has_surface_normal"
        if node.get(present_key) is not True:
            continue
        normal = _require_finite_vector(node, normal_key, node["id"])
        magnitude = float(np.linalg.norm(normal))
        if magnitude <= 1.0e-12:
            continue
        normal = normal / magnitude
        if float(np.dot(normal, outward)) <= 0.0:
            continue

        position = _require_finite_vector(node, "position", node["id"])
        placement = _validated_candidate_placement(
            node,
            position,
            normal,
            graph,
            staged_atoms,
            expected_config,
        )
        if placement is None:
            continue
        source_ase = tuple(int(engine_to_ase_index[index]) for index in source_engine)
        source_atom_images: list[dict[str, Any]] = []
        if node_type in {"P1", "P2"}:
            for image in node.get("atoms_with_images") or []:
                atom_id = int(image["atom_id"])
                if atom_id >= len(staged_atoms):
                    raise WeightedAlphaSchemaError(
                        f"{node['id']} contains an out-of-range image atom index"
                    )
                source_atom_images.append(
                    {
                        "ase_atom_index": int(engine_to_ase_index[atom_id]),
                        "image_offset": list(image["image_offset"]),
                    }
                )
        metadata = {
            "engine_node_id": node["id"],
            "engine_node_type": node_type,
            "classification": node.get("classification"),
            "topology_valid_for_benchmark": node.get("topology_valid_for_benchmark"),
            "benchmark_blocking": bool(node.get("benchmark_blocking", False)),
            "subsurface_ref_dist": node.get("subsurface_ref_dist"),
            "placement": placement,
            "source_atom_images": source_atom_images,
        }
        candidates.append(
            WeightedAlphaCandidate(
                engine_node_id=node["id"],
                position=position,
                site_kind=node["site_kind"],
                coordination=int(node["coordination"]),
                hollow_subtype=node.get("hollow_subtype"),
                source_atom_indices=source_ase,
                normal=normal,
                metadata=metadata,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            TYPE_RANK[{"top": "P0", "bridge": "P1", "hollow": "P2"}[candidate.site_kind]],
            candidate.engine_node_id,
        ),
    )


def _minimum_image_delta(
    reference: np.ndarray,
    position: np.ndarray,
    atoms: Atoms,
) -> np.ndarray:
    delta = np.asarray(position, dtype=float) - np.asarray(reference, dtype=float)
    try:
        minimum, _ = find_mic(delta, cell=atoms.cell, pbc=atoms.pbc)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise WeightedAlphaConfigError("slab cell is singular or invalid for minimum-image geometry") from exc
    return np.asarray(minimum, dtype=float)


def _mic_distance(first: np.ndarray, second: np.ndarray, atoms: Atoms) -> float:
    return float(np.linalg.norm(_minimum_image_delta(first, second, atoms)))

def deduplicate_candidates(
    candidates: Sequence[WeightedAlphaCandidate],
    atoms: Atoms,
    tolerance: float = 0.35,
) -> list[WeightedAlphaCandidate]:
    """Deterministically merge only candidates from the same site family."""

    if tolerance < 0.0:
        raise ValueError("deduplication tolerance must be non-negative")
    retained: list[WeightedAlphaCandidate] = []
    for candidate in sorted(candidates, key=lambda item: item.engine_node_id):
        duplicate = any(
            existing.site_kind == candidate.site_kind
            and existing.coordination == candidate.coordination
            and existing.hollow_subtype == candidate.hollow_subtype
            and _mic_distance(existing.position, candidate.position, atoms) <= tolerance
            for existing in retained
        )
        if not duplicate:
            retained.append(candidate)
    return sorted(
        retained,
        key=lambda candidate: (
            {"top": 0, "bridge": 1, "hollow": 2}[candidate.site_kind],
            candidate.engine_node_id,
        ),
    )


def _candidate_image_identities(
    candidate: WeightedAlphaCandidate,
) -> set[tuple[int, tuple[int, int, int]]] | None:
    raw = candidate.metadata.get("source_atom_images")
    if not isinstance(raw, list):
        return None
    identities: set[tuple[int, tuple[int, int, int]]] = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        index = item.get("ase_atom_index")
        offset = item.get("image_offset")
        if not isinstance(index, int) or not isinstance(offset, list) or len(offset) != 3:
            return None
        image_offset = cast(tuple[int, int, int], tuple(int(value) for value in offset))
        identities.add((index, image_offset))
    return identities


def _align_periodic_position(
    reference: np.ndarray,
    position: np.ndarray,
    atoms: Atoms,
) -> tuple[np.ndarray, np.ndarray]:
    cell = np.asarray(atoms.cell.array, dtype=float)
    try:
        inverse = np.linalg.inv(cell)
    except np.linalg.LinAlgError as exc:
        raise WeightedAlphaConfigError("slab cell is singular") from exc
    delta = np.asarray(position, dtype=float) - np.asarray(reference, dtype=float)
    minimum = _minimum_image_delta(reference, position, atoms)
    fractional_shift = (delta - minimum) @ inverse
    lattice_shift = np.rint(fractional_shift).astype(int)
    if not np.allclose(fractional_shift, lattice_shift, atol=1.0e-8, rtol=0.0):
        raise WeightedAlphaConfigError("minimum-image translation is not a lattice vector")
    return np.asarray(reference, dtype=float) + minimum, lattice_shift


def _fourfold_source_positions(
    first: WeightedAlphaCandidate,
    second: WeightedAlphaCandidate,
    aligned_second_images: set[tuple[int, tuple[int, int, int]]] | None,
    center: np.ndarray,
    atoms: Atoms,
) -> np.ndarray | None:
    first_images = _candidate_image_identities(first)
    cell = np.asarray(atoms.cell.array, dtype=float)
    if first_images is not None and aligned_second_images is not None:
        identities = first_images | aligned_second_images
        if len(identities) != 4:
            return None
        positions = []
        for atom_index, offset in sorted(identities):
            if atom_index < 0 or atom_index >= len(atoms):
                raise WeightedAlphaSchemaError("fourfold source image atom index is out of range")
            positions.append(np.asarray(atoms.positions[atom_index], dtype=float) + np.asarray(offset) @ cell)
        image_points = np.asarray(positions, dtype=float)
        aligned_centroid, lattice_shift = _align_periodic_position(
            center, image_points.mean(axis=0), atoms
        )
        image_points = image_points - lattice_shift @ cell
        if not np.allclose(
            image_points.mean(axis=0), aligned_centroid, atol=1.0e-8, rtol=0.0
        ):
            raise WeightedAlphaSchemaError("fourfold source-image gauge alignment failed")
        return image_points

    source_indices = sorted(set(first.source_atom_indices) | set(second.source_atom_indices))
    if len(source_indices) != 4:
        return None
    aligned_points: list[np.ndarray] = []
    for atom_index in source_indices:
        if atom_index < 0 or atom_index >= len(atoms):
            raise WeightedAlphaSchemaError("fourfold source atom index is out of range")
        aligned, _ = _align_periodic_position(center, atoms.positions[atom_index], atoms)
        aligned_points.append(aligned)
    return np.asarray(aligned_points, dtype=float)


def _cross2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _valid_fourfold_geometry(
    first: WeightedAlphaCandidate,
    second: WeightedAlphaCandidate,
    aligned_second_images: set[tuple[int, tuple[int, int, int]]] | None,
    center: np.ndarray,
    atoms: Atoms,
    center_tolerance: float,
) -> bool:
    points = _fourfold_source_positions(first, second, aligned_second_images, center, atoms)
    if points is None or points.shape != (4, 3):
        return False
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, singular_values, axes = np.linalg.svd(centered, full_matrices=False)
    if singular_values[1] <= 1.0e-10:
        return False
    plane_normal = axes[2]
    if float(np.max(np.abs(centered @ plane_normal))) > 0.05:
        return False
    if abs(float((center - centroid) @ plane_normal)) > 0.05:
        return False

    plane_coordinates = centered @ axes[:2].T
    center_coordinates = (center - centroid) @ axes[:2].T
    order = np.argsort(np.arctan2(plane_coordinates[:, 1], plane_coordinates[:, 0]))
    polygon = plane_coordinates[order]
    turns = [
        _cross2d(polygon[(index + 1) % 4] - polygon[index], polygon[(index + 2) % 4] - polygon[(index + 1) % 4])
        for index in range(4)
    ]
    if any(abs(value) <= 1.0e-10 for value in turns) or not (
        all(value > 0.0 for value in turns) or all(value < 0.0 for value in turns)
    ):
        return False

    radial = np.linalg.norm(polygon - center_coordinates, axis=1)
    if float(np.max(radial) - np.min(radial)) > max(center_tolerance, 1.0e-8):
        return False

    first_diagonal = polygon[2] - polygon[0]
    second_diagonal = polygon[3] - polygon[1]
    denominator = _cross2d(first_diagonal, second_diagonal)
    if abs(denominator) <= 1.0e-12:
        return False
    between = polygon[1] - polygon[0]
    first_parameter = _cross2d(between, second_diagonal) / denominator
    second_parameter = _cross2d(between, first_diagonal) / denominator
    if not (0.0 < first_parameter < 1.0 and 0.0 < second_parameter < 1.0):
        return False
    intersection = polygon[0] + first_parameter * first_diagonal
    return float(np.linalg.norm(intersection - center_coordinates)) <= center_tolerance

def aggregate_fourfold_hollows(
    candidates: Sequence[WeightedAlphaCandidate],
    atoms: Atoms,
    center_tolerance: float = 0.1,
) -> list[WeightedAlphaCandidate]:
    """Merge PBC-coincident P2 pairs sharing a physical edge into fourfold hollows."""

    ordered = sorted(candidates, key=lambda item: item.engine_node_id)
    used: set[int] = set()
    result: list[WeightedAlphaCandidate] = []
    for first_index, first in enumerate(ordered):
        if first_index in used or first.site_kind != "hollow" or first.coordination != 3:
            if first_index not in used:
                result.append(first)
            continue
        partner_index: int | None = None
        partner_position: np.ndarray | None = None
        partner_images: set[tuple[int, tuple[int, int, int]]] | None = None
        for second_index in range(first_index + 1, len(ordered)):
            if second_index in used:
                continue
            second = ordered[second_index]
            if second.site_kind != "hollow" or second.coordination != 3:
                continue
            normal_dot = float(np.dot(first.normal, second.normal))
            if normal_dot < math.cos(math.radians(5.0)):
                continue
            aligned_position, lattice_shift = _align_periodic_position(
                first.position, second.position, atoms
            )
            if float(np.linalg.norm(first.position - aligned_position)) > center_tolerance:
                continue

            first_images = _candidate_image_identities(first)
            second_images = _candidate_image_identities(second)
            aligned_second_images: set[tuple[int, tuple[int, int, int]]] | None = None
            if first_images is not None and second_images is not None:
                aligned_second_images = {
                    (
                        atom_index,
                        cast(
                            tuple[int, int, int],
                            tuple(
                                image_offset[axis] - int(lattice_shift[axis])
                                for axis in range(3)
                            ),
                        ),
                    )
                    for atom_index, image_offset in second_images
                }
                if (
                    len(first_images & aligned_second_images) != 2
                    or len(first_images | aligned_second_images) != 4
                ):
                    continue
            else:
                first_sources = set(first.source_atom_indices)
                second_sources = set(second.source_atom_indices)
                if len(first_sources & second_sources) != 2 or len(first_sources | second_sources) != 4:
                    continue
            candidate_center = (first.position + aligned_position) / 2.0
            if not _valid_fourfold_geometry(
                first,
                second,
                aligned_second_images,
                candidate_center,
                atoms,
                center_tolerance,
            ):
                continue
            partner_index = second_index
            partner_position = aligned_position
            partner_images = aligned_second_images
            break
        if partner_index is None or partner_position is None:
            result.append(first)
            continue
        second = ordered[partner_index]
        used.update({first_index, partner_index})
        normal = first.normal + second.normal
        normal_magnitude = float(np.linalg.norm(normal))
        if normal_magnitude <= 1.0e-12:
            raise WeightedAlphaSchemaError("fourfold normal sum is zero")
        normal /= normal_magnitude
        merged_position = (first.position + partner_position) / 2.0
        first_placement = first.metadata.get("placement")
        second_placement = second.metadata.get("placement")
        if not isinstance(first_placement, dict) or not isinstance(second_placement, dict):
            raise WeightedAlphaSchemaError("fourfold aggregation requires validated placement metadata")
        for key in ("precursor_radius", "gap", "target_clearance"):
            first_value = first_placement.get(key)
            second_value = second_placement.get(key)
            if (
                isinstance(first_value, bool)
                or type(first_value) not in {int, float}
                or isinstance(second_value, bool)
                or type(second_value) not in {int, float}
                or not math.isclose(
                    float(cast(int | float, first_value)),
                    float(cast(int | float, second_value)),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise WeightedAlphaSchemaError(
                    f"fourfold constituent placements disagree on {key}"
                )
        for key in ("distance_type", "status", "target_clearance_reached"):
            if first_placement.get(key) != second_placement.get(key):
                raise WeightedAlphaSchemaError(
                    f"fourfold constituent placements disagree on {key}"
                )
        distance = (
            float(cast(int | float, first_placement["distance"]))
            + float(cast(int | float, second_placement["distance"]))
        ) / 2.0
        clearance = (
            float(cast(int | float, first_placement["clearance_at_position"]))
            + float(cast(int | float, second_placement["clearance_at_position"]))
        ) / 2.0
        metadata = dict(first.metadata)
        metadata.update(
            {
                "aggregation": "coincident_p2_pair",
                "engine_node_ids": [first.engine_node_id, second.engine_node_id],
                "fourfold_geometry_validated": True,
                "placement": {
                    "anchor_position": merged_position.tolist(),
                    "direction": normal.tolist(),
                    "position": (merged_position + normal * distance).tolist(),
                    "distance": distance,
                    "clearance_at_position": clearance,
                    "target_clearance": float(
                        cast(int | float, first_placement["target_clearance"])
                    ),
                    "precursor_radius": float(
                        cast(int | float, first_placement["precursor_radius"])
                    ),
                    "gap": float(cast(int | float, first_placement["gap"])),
                    "target_clearance_reached": first_placement[
                        "target_clearance_reached"
                    ],
                    "distance_type": first_placement["distance_type"],
                    "status": first_placement["status"],
                },
            }
        )
        first_images = _candidate_image_identities(first)
        if first_images is not None and partner_images is not None:
            metadata["source_atom_images"] = [
                {"ase_atom_index": atom_index, "image_offset": list(image_offset)}
                for atom_index, image_offset in sorted(first_images | partner_images)
            ]
        result.append(
            WeightedAlphaCandidate(
                engine_node_id=f"{first.engine_node_id}+{second.engine_node_id}",
                position=merged_position,
                site_kind="hollow",
                coordination=4,
                hollow_subtype=None,
                source_atom_indices=tuple(
                    sorted(set(first.source_atom_indices) | set(second.source_atom_indices))
                ),
                normal=normal,
                metadata=metadata,
            )
        )
    return sorted(result, key=lambda item: item.engine_node_id)


def _minimal_engine_environment(executable: Path) -> dict[str, str]:
    environment = {
        "PATH": str(executable.parent),
        "LANG": "C",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    for required_key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        for source_key, value in os.environ.items():
            if source_key.upper() == required_key:
                environment[required_key] = value
                break
    return environment


def _read_bounded_log(path: Path) -> str:
    size = path.stat().st_size if path.exists() else 0
    if size > MAX_ENGINE_OUTPUT_BYTES:
        raise ValueError(
            f"engine output {path.name} is {size} bytes; limit is {MAX_ENGINE_OUTPUT_BYTES}"
        )
    return path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""


def _read_log_diagnostic(path: Path) -> str:
    try:
        return _read_bounded_log(path)
    except (OSError, ValueError) as exc:
        return f"<diagnostic unavailable: {exc}>"


def _runtime_dependency_hashes(executable: Path) -> dict[str, str]:
    return {
        dependency.name: _sha256(dependency)
        for dependency in _runtime_dlls(executable)
    }


class _WindowsKillOnCloseJob:
    def __init__(self, handle: int) -> None:
        self._handle = handle

    def close(self) -> None:
        if not self._handle:
            return
        import ctypes

        handle, self._handle = self._handle, 0
        if not ctypes.windll.kernel32.CloseHandle(handle):
            raise OSError(ctypes.get_last_error(), "CloseHandle(job) failed")


def _attach_windows_kill_job(
    process: subprocess.Popen[Any],
) -> _WindowsKillOnCloseJob | None:
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    try:
        information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        information.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle, 9, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise OSError("Windows process handle is unavailable")
        if not kernel32.AssignProcessToJobObject(
            handle, wintypes.HANDLE(int(process_handle))
        ):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        return _WindowsKillOnCloseJob(int(handle))
    except BaseException:
        kernel32.CloseHandle(handle)
        raise


def _resume_windows_process(process: subprocess.Popen[Any]) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    process_handle = getattr(process, "_handle", None)
    if process_handle is None:
        raise OSError("Windows process handle is unavailable")
    status = int(ntdll.NtResumeProcess(wintypes.HANDLE(int(process_handle))))
    if status < 0:
        raise OSError(status, "NtResumeProcess failed")


def _capture_bounded_stream(
    stream: Any,
    path: Path,
    label: str,
    exceeded: list[str],
    exceeded_event: threading.Event,
    failures: list[BaseException],
) -> None:
    written = 0
    try:
        with path.open("wb") as output:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                remaining = max(0, MAX_ENGINE_OUTPUT_BYTES - written)
                if remaining:
                    kept = chunk[:remaining]
                    output.write(kept)
                    output.flush()
                    written += len(kept)
                if len(chunk) > remaining:
                    if label not in exceeded:
                        exceeded.append(label)
                    exceeded_event.set()
    except BaseException as exc:
        failures.append(exc)
        exceeded_event.set()
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _terminate_process_tree(
    process: subprocess.Popen[Any],
    job: _WindowsKillOnCloseJob | None = None,
) -> None:
    try:
        if os.name == "nt":
            if job is not None:
                job.close()
            else:
                system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
                taskkill = (
                    Path(system_root) / "System32" / "taskkill.exe"
                    if system_root
                    else Path("taskkill.exe")
                )
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    shell=False,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10.0,
                )
        else:
            try:
                killpg = getattr(os, "killpg")
                sigkill = getattr(signal, "SIGKILL")
                killpg(process.pid, sigkill)
            except ProcessLookupError:
                pass
    except (OSError, subprocess.SubprocessError):
        if process.poll() is None:
            process.kill()
    finally:
        try:
            if process.poll() is None:
                process.wait(timeout=10.0)
        except (OSError, subprocess.SubprocessError):
            if process.poll() is None:
                process.kill()


def _canonical_path_key(path: Path) -> str:
    resolved = path.resolve(strict=False)
    text = os.path.normcase(str(resolved))
    if os.name == "nt":
        text = str(Path(*[part.rstrip(" .") for part in Path(text).parts])).casefold()
    return text


def _preflight_workdir_paths(config: WeightedAlphaConfig, workdir: Path) -> None:
    runtime_dir = workdir / ".weighted_alpha_runtime"
    mutation_targets = {
        _canonical_path_key(workdir / config.graph_filename),
        _canonical_path_key(workdir / "slab.POSCAR"),
        _canonical_path_key(workdir / "weighted_alpha.stdout.log"),
        _canonical_path_key(workdir / "weighted_alpha.stderr.log"),
    }
    runtime_key = _canonical_path_key(runtime_dir)
    artifacts = [config.executable, config.radius_file, *_runtime_dlls(config.executable)]
    if config.runtime_sha256_manifest is not None:
        artifacts.append(config.runtime_sha256_manifest)
    for artifact in artifacts:
        artifact_key = _canonical_path_key(artifact)
        if artifact_key in mutation_targets or artifact_key == runtime_key:
            raise WeightedAlphaConfigError(
                f"workdir output path collides with a runtime artifact: {artifact}"
            )
        try:
            artifact.resolve(strict=False).relative_to(runtime_dir.resolve(strict=False))
        except ValueError:
            pass
        else:
            raise WeightedAlphaConfigError(
                f"runtime artifact may not be located inside the private staging directory: {artifact}"
            )


def _run_in_directory(atoms: Atoms, config: WeightedAlphaConfig, workdir: Path) -> WeightedAlphaRun:
    _preflight_workdir_paths(config, workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    graph_path = workdir / config.graph_filename
    stdout_path = workdir / "weighted_alpha.stdout.log"
    stderr_path = workdir / "weighted_alpha.stderr.log"
    for stale in (graph_path, stdout_path, stderr_path):
        if stale.exists():
            stale.unlink()

    staged = stage_slab_for_engine(atoms, workdir / "slab.POSCAR")
    staged_input_sha256 = _sha256(staged.path)
    _verify_runtime_artifacts(config)
    runtime_config = config
    runtime_dir: Path | None = None
    if not config.allow_unpinned_runtime:
        runtime_config, runtime_dir = _stage_runtime_bundle(config, workdir)
    command = build_engine_command(runtime_config, staged.path, staged_input_sha256)
    environment = _minimal_engine_environment(runtime_config.executable)
    process: subprocess.Popen[Any] | None = None
    job: _WindowsKillOnCloseJob | None = None
    capture_threads: list[threading.Thread] = []
    capture_failures: list[BaseException] = []
    exceeded_streams: list[str] = []
    exceeded_event = threading.Event()
    timed_out = False
    try:
        process_options: dict[str, Any] = {}
        if os.name == "nt":
            process_options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004  # CREATE_SUSPENDED
            )
        else:
            process_options["start_new_session"] = True
        process = subprocess.Popen(
            command,
            cwd=workdir,
            env=environment,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **process_options,
        )
        if process.stdout is None or process.stderr is None:
            raise OSError("failed to create engine output pipes")
        if os.name == "nt":
            job = _attach_windows_kill_job(process)
            _resume_windows_process(process)
        for stream, path, label in (
            (process.stdout, stdout_path, "stdout"),
            (process.stderr, stderr_path, "stderr"),
        ):
            thread = threading.Thread(
                target=_capture_bounded_stream,
                args=(stream, path, label, exceeded_streams, exceeded_event, capture_failures),
                daemon=True,
            )
            thread.start()
            capture_threads.append(thread)

        deadline = time.monotonic() + float(config.timeout_s)
        while process.poll() is None:
            if exceeded_streams or capture_failures:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                timed_out = True
                break
            exceeded_event.wait(min(0.05, remaining))
        if timed_out or exceeded_streams or capture_failures:
            _terminate_process_tree(process, job)
            job = None
        else:
            returncode = process.wait(timeout=10.0)
            if os.name != "nt":
                _terminate_process_tree(process, None)
            if job is not None:
                job.close()
                job = None
        for thread in capture_threads:
            thread.join(timeout=10.0)
        if any(thread.is_alive() for thread in capture_threads):
            raise OSError("engine output capture thread did not terminate")
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        if process is not None:
            _terminate_process_tree(process, job)
            job = None
        raise WeightedAlphaExecutionError(
            f"weighted-alpha engine could not be launched or monitored: {exc}",
            command=command,
            returncode=None,
            stdout=_read_log_diagnostic(stdout_path),
            stderr=_read_log_diagnostic(stderr_path),
        ) from exc
    finally:
        if job is not None:
            job.close()

    stdout = _read_log_diagnostic(stdout_path)
    stderr = _read_log_diagnostic(stderr_path)
    if capture_failures:
        raise WeightedAlphaExecutionError(
            f"weighted-alpha engine output capture failed: {capture_failures[0]}",
            command=command,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
        )
    if exceeded_streams:
        streams = ", ".join(sorted(set(exceeded_streams)))
        raise WeightedAlphaExecutionError(
            f"engine output {streams} exceeded {MAX_ENGINE_OUTPUT_BYTES} byte limit",
            command=command,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
        )
    if timed_out:
        raise WeightedAlphaExecutionError(
            f"weighted-alpha engine timed out after {config.timeout_s:g} s",
            command=command,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
        )

    try:
        stdout = _read_bounded_log(stdout_path)
        stderr = _read_bounded_log(stderr_path)
    except (OSError, ValueError) as exc:
        raise WeightedAlphaExecutionError(
            str(exc),
            command=command,
            returncode=returncode,
            stdout="",
            stderr="",
        ) from exc
    if returncode != 0:
        raise WeightedAlphaExecutionError(
            "weighted-alpha engine failed",
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    if not graph_path.is_file():
        raise WeightedAlphaExecutionError(
            f"weighted-alpha engine did not create {config.graph_filename}",
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    _verify_runtime_artifacts(runtime_config)
    final_staged_input_sha256 = _sha256(staged.path)
    if final_staged_input_sha256 != staged_input_sha256:
        raise WeightedAlphaExecutionError(
            "staged slab input changed during weighted-alpha execution",
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    graph, parsed_graph_sha256 = _load_graph_and_sha256(graph_path)
    candidates = extract_candidates(
        graph,
        staged.atoms,
        staged.engine_to_ase_index,
        expected_staged_input_sha256=staged_input_sha256,
        expected_config=config,
        include_undefined_hollow_precursors=True,
    )
    candidates = aggregate_fourfold_hollows(candidates, atoms)
    candidates = [
        candidate
        for candidate in candidates
        if not (candidate.coordination == 3 and candidate.hollow_subtype == "undefined")
    ]
    candidates = deduplicate_candidates(candidates, atoms)
    if not candidates:
        raise WeightedAlphaExecutionError(
            "weighted-alpha engine produced no accepted adsorption sites",
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    provenance = {
        "backend": "weighted_alpha",
        "first_party_release": config.first_party_release,
        "mesa_base_commit": config.mesa_base_commit,
        "private_source_manifest_sha256": config.private_source_manifest_sha256,
        "executable": str(config.executable),
        "executed_executable": str(runtime_config.executable),
        "executable_sha256": _sha256(runtime_config.executable),
        "runtime_artifacts_pinned": not config.allow_unpinned_runtime,
        "runtime_staged_private": runtime_dir is not None,
        "executable_hash_pinned": config.expected_sha256 is not None,
        "expected_executable_sha256": config.expected_sha256,
        "runtime_dependency_sha256": _runtime_dependency_hashes(runtime_config.executable),
        "runtime_sha256_manifest": (
            str(config.runtime_sha256_manifest)
            if config.runtime_sha256_manifest is not None
            else None
        ),
        "runtime_sha256_manifest_hash": (
            _sha256(runtime_config.runtime_sha256_manifest)
            if runtime_config.runtime_sha256_manifest is not None
            else None
        ),
        "executed_runtime_sha256_manifest": (
            str(runtime_config.runtime_sha256_manifest)
            if runtime_config.runtime_sha256_manifest is not None
            else None
        ),
        "expected_runtime_manifest_sha256": config.expected_runtime_manifest_sha256,
        "radius_file": str(config.radius_file),
        "executed_radius_file": str(runtime_config.radius_file),
        "radius_file_sha256": _sha256(runtime_config.radius_file),
        "expected_radius_sha256": config.expected_radius_sha256,
        "staged_input_sha256": final_staged_input_sha256,
        "graph_sha256": parsed_graph_sha256,
        "graph_type": graph.get("graph_type"),
        "geometry_schema_version": graph["metadata"].get("geometry_schema_version"),
        "command": command,
        "alpha_factor": config.alpha_factor,
        "contact_anchor_radius": config.probe_radius,
        "probe_radius": config.probe_radius,
        "placement_gap": config.placement_gap,
        "placement_step": config.placement_step,
        "placement_max_distance": config.placement_max_distance,
        "timeout_s": config.timeout_s,
        "pbc": list(EXPECTED_PBC),
        "construction_mode": config.construction_mode,
        "engine_to_ase_index": list(staged.engine_to_ase_index),
        "ase_to_engine_index": list(staged.ase_to_engine_index),
    }
    return WeightedAlphaRun(
        graph=graph,
        candidates=tuple(candidates),
        provenance=provenance,
        engine_to_ase_index=staged.engine_to_ase_index,
        stdout=stdout,
        stderr=stderr,
    )


def run_weighted_alpha(
    atoms: Atoms,
    config: WeightedAlphaConfig | None = None,
    *,
    workdir: str | Path | None = None,
) -> WeightedAlphaRun:
    """Run the external engine and return filtered candidates plus provenance."""

    resolved = resolve_weighted_alpha_config(config)
    _require_pbc110(atoms)
    requested_workdir = Path(workdir).resolve() if workdir is not None else None
    with tempfile.TemporaryDirectory(prefix="mesa-weighted-alpha-") as temporary:
        execution_dir = Path(temporary)
        result = _run_in_directory(atoms, resolved, execution_dir)
        if requested_workdir is not None:
            _preflight_workdir_paths(resolved, requested_workdir)
            requested_workdir.mkdir(parents=True, exist_ok=True)
            for name in (
                "slab.POSCAR",
                resolved.graph_filename,
                "weighted_alpha.stdout.log",
                "weighted_alpha.stderr.log",
            ):
                source = execution_dir / name
                if source.is_file():
                    shutil.copy2(source, requested_workdir / name)
    if not result.candidates:
        command = result.provenance.get("command") or [str(resolved.executable)]
        raise WeightedAlphaExecutionError(
            "weighted-alpha engine produced no accepted adsorption sites",
            command=command,
            returncode=0,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result
