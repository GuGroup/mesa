# Project Review Issues

Review date: 2026-06-18

Status: resolved in the current working tree.

## Resolved Items

1. Install documentation now uses the dependency constraint file required on this HPC toolchain.
   - Updated `README.md`, `docs/admin/hpc-server.md`, `docs/quickstart.md`, and `docs/user/step-by-step.md`.
   - `constraints.txt` remains part of the working tree and should be tracked with the install docs.

2. The user-facing example spec now has its referenced POSCAR file.
   - Added `examples/POSCAR`.
   - `examples/input.yml` can keep using `structure.path: POSCAR`.

3. Scratch input directories were removed from the working tree.
   - Removed root-level `test/` and `tmp/`.
   - Added `test/` and `tmp/` to `.gitignore`.

4. Skill prompt assets now prefer the path-based POSCAR workflow.
   - Updated `skills/vasp-job/agents/openai.yaml`.
   - Updated `skills/vasp-job/examples/prompts.md`.
   - Synchronized the installed copies under `/home/mesa/.codex/skills/vasp-job/`.

5. The skill description no longer advertises a non-existent result fetch command.
   - It now describes inspecting result files on the cluster.

6. The schema and installed CLI remain aligned on current user-facing fields.
   - `vasp-job schema` includes `structure.path`.
   - `vasp-job schema` does not expose the removed no-op collection field.

## Verification

Commands used:

```bash
PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v
uv tool run --from mkdocs-material mkdocs build --strict
vasp-job schema
diff -q skills/vasp-job/SKILL.md /home/mesa/.codex/skills/vasp-job/SKILL.md
diff -q skills/vasp-job/agents/openai.yaml /home/mesa/.codex/skills/vasp-job/agents/openai.yaml
diff -q skills/vasp-job/examples/prompts.md /home/mesa/.codex/skills/vasp-job/examples/prompts.md
```
