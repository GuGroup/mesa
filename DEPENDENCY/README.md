# MESA Dependency Layer

`DEPENDENCY/` is the bootstrap and runtime-dispatch layer for this repository.
It does not replace `ENVIRONMENT/`; it points to the existing environment specs
and adds a small common runtime plus preflight tooling.

Fresh-clone entry points:

```bash
python3 DEPENDENCY/tools/mesa_env.py list
python3 DEPENDENCY/tools/mesa_env.py doctor --all
python3 DEPENDENCY/tools/mesa_env.py check mesa-modeling
python3 DEPENDENCY/tools/mesa_env.py install mesa-general --yes
```

The helper is stdlib-only. It can run before any project environment exists.

Runtime policy:

- Use `mesa-general` for lightweight common scripts and OpenAI API wrappers.
- Use `mesa-modeling` for structures, slabs, adsorbates, trajectories, and ASE.
- Use `mesa-manuscript` for manuscript work, figure export, Pandoc, Playwright,
  and publication plotting.
- Keep `mesa-paper-search` and `paper-search-mcp` separate because they expose
  similar commands but are different packages.
- Keep UMA, AdsorbDiff, and VASP isolated because their runtime assumptions are
  machine-specific.
