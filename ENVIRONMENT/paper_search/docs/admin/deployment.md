# Deployment

Documentation is deployed to GitHub Pages through GitHub Actions.

## Workflows

- `.github/workflows/docs.yml` — builds MkDocs Material with
  `mkdocs build --strict` and deploys `site/` to GitHub Pages.
- `.github/workflows/tests.yml` — installs with `uv sync --frozen` and runs the
  unit test suite on pushes and pull requests.

The docs workflow:

1. checks out the repository,
2. installs `uv`,
3. installs the docs extra from `uv.lock`,
4. builds MkDocs Material with `mkdocs build --strict`,
5. uploads the generated `site/` directory as a Pages artifact,
6. deploys that artifact with GitHub Pages.

## Repository setting

In GitHub, set:

```text
Settings -> Pages -> Build and deployment -> Source -> GitHub Actions
```

The docs workflow deploys on pushes to `main` when documentation, MkDocs,
workflow, or dependency files change. It can also be run manually with
`workflow_dispatch`.

## Local preflight

Before pushing docs changes:

```bash
uv run --extra docs mkdocs build --strict
```

## References

- [MkDocs deployment guide](https://www.mkdocs.org/user-guide/deploying-your-docs/)
- [GitHub Pages custom workflows](https://docs.github.com/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)
