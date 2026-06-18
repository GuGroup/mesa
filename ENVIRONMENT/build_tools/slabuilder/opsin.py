"""OPSIN name-to-structure wrapper for chemical name inputs."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess


_UNSET = object()
py2opsin = _UNSET


@dataclass(frozen=True)
class OpsinRequest:
    """Request model for OPSIN chemical name conversion."""

    name: str | list[str]
    output_format: str = "SMILES"
    allow_acid: bool = True
    allow_radicals: bool = True
    allow_bad_stereo: bool = False
    wildcard_radicals: bool = True


@dataclass(frozen=True)
class OpsinResponse:
    """Response model for OPSIN chemical name conversion."""

    result: str | list[str] | bool
    error: str | None = None


def _java_error() -> str | None:
    """Return a user-facing Java/JRE error, or None when Java runs."""
    if shutil.which("java") is None:
        return "Java Runtime Environment (JRE) not found. Please install Java 8+."

    try:
        subprocess.run(
            ["java", "-version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Bound the probe so a hung/bad `java` wrapper cannot stall agent-tool
            # import (the registry evaluates OPSIN availability at import time).
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return "Java version check timed out. Please verify your Java installation."
    except subprocess.CalledProcessError:
        return "Java found but failed to run. Please install Java 8+."
    except Exception:
        return "Error checking Java version."

    return None


def opsin_unavailable_reason() -> str | None:
    """Return why OPSIN is unavailable, or None when it can run."""
    # Check the optional Python package FIRST (resolving the lazy _UNSET import),
    # so a default install without py2opsin never probes Java just to decide the
    # OPSIN tool is unavailable, and the more direct reason is not masked by a
    # missing/slow JRE (EXTERNAL-2).
    if _get_py2opsin() is None:
        return "py2opsin not installed"

    java_error = _java_error()
    if java_error:
        return java_error

    return None


def opsin_available() -> bool:
    """Return True only when py2opsin is installed and Java runs."""
    return opsin_unavailable_reason() is None


def _get_py2opsin():
    """Import py2opsin lazily so package import does not require Java."""
    global py2opsin
    if py2opsin is not _UNSET:
        return py2opsin

    try:
        from py2opsin import py2opsin as imported_py2opsin
    except ImportError:
        py2opsin = None
    else:
        py2opsin = imported_py2opsin
    return py2opsin


def name_to_structure(request: OpsinRequest) -> OpsinResponse:
    """Convert IUPAC/common chemical names through py2opsin."""
    unavailable_reason = opsin_unavailable_reason()
    if unavailable_reason:
        return OpsinResponse(result=False, error=unavailable_reason)

    py2opsin_fn = _get_py2opsin()

    try:
        result = py2opsin_fn(
            chemical_name=request.name,
            output_format=request.output_format,
            allow_acid=request.allow_acid,
            allow_radicals=request.allow_radicals,
            allow_bad_stereo=request.allow_bad_stereo,
            wildcard_radicals=request.wildcard_radicals,
        )
    except Exception as exc:
        return OpsinResponse(result=False, error=f"Internal Error: {exc}")

    if result is False:
        return OpsinResponse(result=False, error="OPSIN failed to parse name")

    return OpsinResponse(result=result)


def name_to_smiles(name: str) -> tuple[str | None, str | None]:
    """Convert a single chemical name to SMILES.

    Returns:
        ``(smiles, error)``. Exactly one value is non-None.
    """
    response = name_to_structure(OpsinRequest(name=name, output_format="SMILES"))
    if response.error:
        return None, response.error

    result = response.result
    if isinstance(result, str) and result.strip():
        return result.strip(), None
    if isinstance(result, list) and result and isinstance(result[0], str):
        return result[0].strip(), None

    return None, "OPSIN failed to parse name"
