#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"
skills_dir="$codex_home/skills"
apply=0

usage() {
  cat <<'EOF'
Usage: DEPENDENCY/sync_codex_skills.sh [--apply]

Synchronize this repository's SKILL/*/*/SKILL.md folders into
$CODEX_HOME/skills (or ~/.codex/skills) as symbolic links.

Default mode is a dry run. Pass --apply to create/update symlinks.
Existing non-symlink paths are left untouched and reported as SKIP.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply)
      apply=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$apply" -eq 1 ]; then
  mkdir -p "$skills_dir"
fi

echo "repo_root=$repo_root"
echo "skills_dir=$skills_dir"
echo "mode=$([ "$apply" -eq 1 ] && echo apply || echo dry-run)"

find "$repo_root/SKILL" \
  \( -path "$repo_root/SKILL/legacy" -o -path "$repo_root/SKILL/legacy/*" \) -prune -o \
  -mindepth 2 -maxdepth 4 -name SKILL.md -print | sort | while IFS= read -r skill_file; do
  skill_dir="$(dirname "$skill_file")"
  name="$(basename "$skill_dir")"
  link="$skills_dir/$name"

  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "SKIP $name: existing non-symlink at $link"
    continue
  fi

  current=""
  if [ -L "$link" ]; then
    current="$(readlink "$link")"
  fi

  if [ "$current" = "$skill_dir" ]; then
    echo "OK   $name -> $skill_dir"
    continue
  fi

  if [ "$apply" -eq 1 ]; then
    ln -sfn "$skill_dir" "$link"
    if [ -n "$current" ]; then
      echo "UPD  $name: $current -> $skill_dir"
    else
      echo "ADD  $name -> $skill_dir"
    fi
  else
    if [ -n "$current" ]; then
      echo "WOULD-UPDATE $name: $current -> $skill_dir"
    else
      echo "WOULD-ADD    $name -> $skill_dir"
    fi
  fi
done
