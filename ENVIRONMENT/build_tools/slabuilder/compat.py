"""Compatibility shims for older atomistic toolkits."""

from __future__ import annotations


def apply_numpy_compat() -> None:
    """Patch NumPy symbols removed in 2.x but still used by older dependencies."""
    import numpy as np

    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # type: ignore[attr-defined]
