#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

case "$(uname -s)" in
  Linux|Darwin)
    ;;
  *)
    echo "Unsupported OS for this bootstrap script. Use DEPENDENCY/bootstrap.ps1 on Windows." >&2
    exit 1
    ;;
esac

add_uv_paths() {
  if [ -n "${HOME:-}" ]; then
    if [ -d "$HOME/.local/bin" ]; then
      PATH="$HOME/.local/bin:$PATH"
    fi
    if [ -d "$HOME/.cargo/bin" ]; then
      PATH="$HOME/.cargo/bin:$PATH"
    fi
    export PATH
  fi
}

install_uv() {
  echo "uv not found. Installing uv with the official standalone installer..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    echo "curl or wget is required to install uv automatically." >&2
    echo "Install uv manually, then rerun: bash DEPENDENCY/bootstrap.sh" >&2
    exit 1
  fi
}

add_uv_paths
if ! command -v uv >/dev/null 2>&1; then
  install_uv
  add_uv_paths
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was installed, but it is not on PATH yet." >&2
  echo "Open a new terminal or add ~/.local/bin to PATH, then rerun this script." >&2
  exit 1
fi

cd "$REPO_ROOT"
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap "$@"
