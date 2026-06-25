# 배포

문서는 GitHub Actions를 통해 GitHub Pages로 배포됩니다.

## 워크플로

- `.github/workflows/docs.yml` — `mkdocs build --strict`로 MkDocs Material을 빌드하고
  `site/`를 GitHub Pages에 배포합니다.
- `.github/workflows/tests.yml` — `uv sync --frozen`으로 설치하고 push 및 pull request에서
  단위 테스트 스위트를 실행합니다.

문서 워크플로:

1. 저장소 체크아웃,
2. `uv` 설치,
3. `uv.lock`에서 docs extra 설치,
4. `mkdocs build --strict`로 MkDocs Material 빌드,
5. 생성된 `site/` 디렉터리를 Pages 아티팩트로 업로드,
6. 해당 아티팩트를 GitHub Pages로 배포.

## 저장소 설정

GitHub에서 다음을 설정합니다.

```text
Settings -> Pages -> Build and deployment -> Source -> GitHub Actions
```

문서 워크플로는 문서, MkDocs, 워크플로, 의존성 파일이 변경된 `main` push에서
배포됩니다. `workflow_dispatch`로 수동 실행도 가능합니다.

## 로컬 사전 점검

문서 변경을 push하기 전에:

```bash
uv run --extra docs mkdocs build --strict
```

## 참고

- [MkDocs deployment guide](https://www.mkdocs.org/user-guide/deploying-your-docs/)
- [GitHub Pages custom workflows](https://docs.github.com/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)
