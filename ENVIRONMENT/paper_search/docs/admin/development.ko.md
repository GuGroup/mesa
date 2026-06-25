# 개발

이 프로젝트는 의존성·환경 관리에 `uv`를 사용합니다.

## 설치

```bash
uv sync
uv sync --extra docs   # 문서 작업용
```

## 테스트

```bash
uv run python -m unittest discover -s tests
```

테스트는 완전히 오프라인으로 실행됩니다(deterministic 그래프, fixture 기반
search/resolver 파싱, fake-model LLM 경로). CI는 `.github/workflows/tests.yml`로 동일한
스위트를 실행합니다.

## 로컬 문서 빌드

```bash
uv run --extra docs mkdocs build --strict
uv run --extra docs mkdocs serve
```

## 의존성 업데이트

`pyproject.toml`을 수정한 뒤 lock 파일을 갱신하고 둘 다 커밋하세요.

```bash
uv lock
```

CI는 `uv sync --frozen`으로 설치하므로 lock이 항상 맞아야 합니다.

## 코드 구성

새 기능은 노드 / 모듈 경계에 맞게 배치하세요.

- 검색 provider는 `paper_search.search`,
- 전문 resolver는 `paper_search.resolvers`,
- 파서 어댑터는 `paper_search.parsers`,
- 근거 추출은 `paper_search.extraction`,
- opportunity 랭킹과 계산 제안은 `paper_search.opportunities`,
- 그래프 오케스트레이션과 LLM/PaperQA 노드는 `paper_search.agent`.

이들이 어떻게 조합되는지는 [에이전트 그래프](../architecture/agent-graph.md)를
참고하세요.
