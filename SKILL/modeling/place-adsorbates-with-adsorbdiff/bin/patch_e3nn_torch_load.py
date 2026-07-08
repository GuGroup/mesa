#!/usr/bin/env python3
"""Patch e3nn 0.4.x for PyTorch versions that default torch.load to weights_only=True."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    spec = importlib.util.find_spec("e3nn.o3._wigner")
    if spec is None or spec.origin is None:
        raise SystemExit("e3nn.o3._wigner was not found in this Python environment")

    path = Path(spec.origin)
    text = path.read_text(encoding="utf-8")
    if "weights_only=False" in text:
        print(f"Already patched: {path}")
        return 0

    old = "_Jd, _W3j_flat, _W3j_indices = torch.load(\n    os.path.join(os.path.dirname(__file__), 'constants.pt')\n)"
    new = "_Jd, _W3j_flat, _W3j_indices = torch.load(\n    os.path.join(os.path.dirname(__file__), 'constants.pt'),\n    weights_only=False,\n)"
    if old not in text:
        raise SystemExit(f"Could not find the expected torch.load block in {path}")

    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"Patched: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
