# 저장소 리뷰: 개선점과 잠재 오류

작성일: 2026-06-24
대상 상태: 현재 작업트리 기준. 직전 `openai-oauth` 관련 미커밋 변경과 기존 `.agents/`
untracked 항목이 보이는 상태에서 리뷰했다.

## 요약

이 저장소의 큰 방향은 타당하다. 기존 retrieval/parsing 코드, LangGraph orchestration,
PaperQA2 evidence QA를 조합하는 구조는 재사용 중심 설계와 맞다. 다만 지금 상태에서 가장
먼저 정리해야 할 문제는 세 가지다.

1. PaperQA async bridge가 이미 실행 중인 event loop 안에서 실패한다.
2. search loop가 `max_papers`로 잘라낸 논문까지 `seen_paper_ids`에 넣어 후속 round에서
   후보를 영구히 잃을 수 있다.
3. type-check baseline과 full-mode 핵심 노드 테스트가 부족해 회귀를 놓칠 수 있다.

그 다음은 큰 파일 분리, config 중복, 문서 drift를 차례로 정리하는 것이 맞다. 이 리뷰 중
확인한 정책 전제는 OA-only가 아니라 “1차 OA/TDM/설정된 publisher full text 우선,
Sci-Hub fallback 기본 활성화”이다.

## 검증 결과

| 항목 | 결과 | 메모 |
| --- | --- | --- |
| Unit tests | 통과 | `uv run --frozen python -m unittest discover -s tests` → 63 tests, 1 skipped |
| Ruff | 통과 | `uvx ruff check src tests` |
| Build | 통과 | `uv build` |
| Docs | 통과 | `uv run --extra docs mkdocs build --strict`; Material/MkDocs 2.0 경고만 출력 |
| basedpyright | 실패 | 52 files, 76 errors, 1397 warnings |
| Vulture | 큰 dead code 없음 | context-manager 인자 미사용만 감지 |

## Findings

### P1. PaperQA async bridge가 running event loop 안에서 실패한다

근거:

- `src/paper_search/agent/paperqa_index.py:106-115`는 `asyncio.run(coro)` 실패 시 새
  event loop를 만들어 `run_until_complete`를 호출한다.
- 이미 event loop가 실행 중인 같은 thread에서는 이 fallback도 실패한다.

재현:

```text
RuntimeWarning: coroutine 'sample' was never awaited
RuntimeError Cannot run the event loop while another loop is running
```

영향 범위:

- `build_docs`, `extend_docs`, `ask`, `agent_ask`, `ask_many`가 모두 `_run_async`를 탄다.
- LangGraph Studio, notebook, async host, MCP host가 같은 thread event loop 위에서
  실행되면 full-mode PaperQA path가 깨질 수 있다.

권장 조치:

- PaperQA adapter를 sync/async로 명확히 분리한다.
- sync graph에서 async PaperQA를 계속 써야 한다면 “별도 worker thread에서 event loop를
  만들고 결과를 join”하는 방식으로 바꾼다.
- `RuntimeError` catch 뒤 기존 coroutine을 방치하지 않도록 테스트를 먼저 추가한다.

### P1. `max_papers`로 제외된 논문도 seen 처리되어 후속 round에서 사라진다

근거:

- `src/paper_search/agent/nodes/search.py:52-57`: deduped paper를 보자마자
  `seen_ids.add(...)`를 수행한다.
- `src/paper_search/agent/nodes/search.py:59`: 그 뒤에야 `max_papers`로 `papers`를 자른다.
- `src/paper_search/agent/nodes/search.py:66-69`: 잘린 항목까지 포함된 `seen_ids`를 state에
  반환한다.

재현:

```text
papers= ['p0', 'p1']
seen= ['p0', 'p1', 'p2', 'p3', 'p4']
```

위험:

- `max_papers`가 작은 exploratory run에서 후보 일부가 “발견됐지만 처리되지 않은 상태”로
  남고, 다음 round에서 같은 논문이 다시 발견되어도 skip될 수 있다.

권장 조치:

- persisted/processed candidate만 `seen_paper_ids`에 넣는다.
- 또는 `seen_paper_ids`와 `deferred_paper_ids`를 분리하고, `max_papers` 여유가 생긴 round에서
  deferred 항목을 재검토한다.

### P2. Type-check baseline이 없다

근거:

- `uvx basedpyright src tests --outputjson` 결과: 52 files, 76 errors, 1397 warnings.
- 주요 error rule: `reportArgumentType` 20건, `reportTypedDictNotRequiredAccess` 14건,
  `reportMissingTypeArgument` 11건, `reportAttributeAccessIssue` 10건,
  `reportOptionalMemberAccess` 8건.
- `src/paper_search/agent/__init__.py`에서 import cycle이 감지된다.
- `src/paper_search/agent/state.py:10-68`은 `total=False` TypedDict인데 여러 노드가
  `state["material"]`, `state["reaction"]`처럼 required처럼 접근한다.

CI gap:

- `.github/workflows/tests.yml:29-33`은 `uv sync --frozen` 후 unittest만 실행한다.
- ruff, build, docs strict, basedpyright가 PR gate에 없다.

권장 조치:

- 먼저 `src/`만 대상으로 type-check baseline을 만들고, tests는 다음 단계로 분리한다.
- `GraphState`를 “input state”, “runtime accumulated state”, “final result state” 등으로
  나누거나, required key를 별도 TypedDict로 분리한다.
- LangChain/PaperQA처럼 타입이 약한 외부 boundary는 좁은 adapter protocol로 감싼다.
- CI에 최소 `ruff check src tests`, `uv build`, `mkdocs build --strict`를 추가한다.
  basedpyright는 baseline 정리 후 gate로 올린다.

### P2. Sci-Hub fallback 정책은 계속 명시적으로 노출해야 한다

근거:

- `src/paper_search/config.py:70-75`: `ScihubConfig.enabled` 기본값이 `True`다.
- `config.example.yaml:17-22`: 예제 설정도 Sci-Hub를 기본 ON으로 둔다.
- `src/paper_search/agent/services.py:95-100`: `config.scihub_enabled`가 true면
  `SciHubResolver`가 resolver chain에 들어간다.
- `tests/test_core.py:1222-1235`: 기본값으로 fallback resolver가 1개 존재한다고 테스트가
  고정한다.

위험:

- 법적/정책적 판단이 필요한 기능이 default path에 들어와 있다.
- 운영자가 이 fallback을 모른 채 실행할 수 있으므로 README, setup docs, config example,
  CLI help에서 계속 눈에 띄게 유지해야 한다.

권장 조치:

- OA-only 표현을 다시 도입하지 않는다.
- `scihub.enabled: false` opt-out 방법과 지역별 법적 책임 caveat를 사용자-facing 문서에
  계속 유지한다.
- 향후 default를 바꾸려면 config, example YAML, tests, README/docs를 한 번에 바꾼다.

### P2. Full-mode 핵심 노드 테스트가 부족하다

CodeGraph blast-radius 기준으로 아래 노드는 직접 covering test가 없다.

- `claim_validation_node`
- `paperqa_index_node`
- `gap_ranking_node`

위험:

- full-mode의 핵심 가치인 PaperQA indexing, citation validation, gap-driven re-search가
  회귀해도 현재 unittest만으로는 놓칠 수 있다.
- 특히 `claim_validation_node`와 `paperqa_index_node`는 외부 PaperQA API surface에 의존해
  작은 버전 변경에도 깨질 가능성이 있다.

권장 조치:

- PaperQA adapter에는 fake Docs/Settings를 둔 unit test를 추가한다.
- graph-level e2e smoke는 작은 parsed_text fixture로 `paperqa_index -> claim_validation ->
  gap_ranking` 경로를 통과하게 만든다.
- LLM prompt tests는 문자열 snapshot이 아니라 parsed decision 구조를 검증한다.

### P2. 큰 파일이 책임을 많이 들고 있다

순수 LOC 기준:

| 파일 | 순수 LOC | 문제 |
| --- | ---: | --- |
| `tests/test_core.py` | 1520 | 모든 테스트가 한 파일에 모여 변경 충돌과 리뷰 비용이 큼 |
| `src/paper_search/config.py` | 303 | schema, env loading, CLI override, output path policy가 한 파일에 공존 |
| `src/paper_search/opportunities.py` | 288 | ranking, gap detection, suggestion generation, research context 변환이 섞임 |

권장 조치:

- `tests/test_core.py`를 영역별로 쪼갠다: `test_config.py`, `test_search.py`,
  `test_parse.py`, `test_graph_nodes.py`, `test_resolvers.py`.
- `config.py`는 `config/schema.py`, `config/load.py`, `config/paths.py` 정도로 나눌 수 있다.
- `opportunities.py`는 scoring/ranking과 suggestion builder를 분리한다.

### P2. 문서가 실제 그래프와 drift됐다

근거:

- `src/paper_search/agent/graph.py:23-35`의 실제 `NODE_SEQUENCE`는 11개다.
- `README.md:16-22`, `docs/index.md:8`, `docs/architecture/agent-graph.md:4` 등은 9개 노드라고
  설명한다.

권장 조치:

- 노드 개수는 수동 숫자로 쓰지 말고, 가능하면 “`NODE_SEQUENCE`에 정의된 단계”처럼 표현한다.
- 그래프 Mermaid나 node map은 코드에서 생성하거나 테스트로 문서와 동기화한다.

### P3. Config 모델이 중복 구조를 갖는다

근거:

- `AppConfig`는 nested YAML schema를 표현한다.
- `PipelineConfig`는 거의 같은 값을 runtime-friendly flat structure로 다시 들고 있다.
- `PipelineConfig.from_app_config`가 둘 사이의 수동 매핑을 담당한다.

위험:

- 새 config 필드를 추가할 때 schema, CLI override, example YAML, docs, flat config mapping을
  모두 함께 고쳐야 한다.
- 누락되어도 type-check/CI가 현재는 강하게 잡아주지 않는다.

권장 조치:

- 단기적으로는 새 config 필드마다 `from_app_config`와 `config.example.yaml`을 검증하는
  focused test를 추가한다.
- 중기적으로는 runtime이 nested config를 직접 참조하거나, flat view를 computed property로
  제공해 수동 필드 복제를 줄인다.

### P3. Dead-code 신호는 작지만 cleanup 여지는 있다

`uvx vulture src tests --min-confidence 80`은 context-manager `__exit__` 인자류만 unused로
잡았다.

- `src/paper_search/agent/services.py:112`
- `src/paper_search/parsers/router.py:31`
- `src/paper_search/servers.py:52`

이는 Python protocol signature 때문에 필요한 인자라 실제 dead code로 보기는 어렵다.
다만 `_exc_type`, `_tb`처럼 underscore 이름으로 바꾸면 정적 도구 소음은 줄일 수 있다.

## 불필요하거나 과한 구조 후보

- `mcp_server.py`와 Studio entrypoint는 얇은 adapter라 지금 삭제 대상은 아니다. 다만
  business logic이 이쪽으로 새어 나오면 중복 구현이 되므로 계속 thin wrapper로 유지해야 한다.
- `PipelineConfig`/`AppConfig` 이중 구조는 실제 중복 비용이 있으므로 정리 후보가 맞다.
- 단일 `tests/test_core.py`는 이미 유지보수 비용이 높다. 새 테스트는 별도 파일로 추가하는
  방침을 유지하는 편이 낫다.

## 권장 실행 순서

1. `_run_async` event-loop 실패를 회귀 테스트로 고정하고 adapter를 고친다.
2. `search_node`의 `seen_paper_ids`/`max_papers` 버그를 테스트와 함께 수정한다.
3. Sci-Hub default-on 정책과 opt-out 안내가 docs/config/tests에서 계속 일치하는지 확인한다.
4. CI에 ruff, build, docs strict를 추가한다.
5. basedpyright는 `src/`부터 error count를 0으로 낮춘 뒤 CI gate에 올린다.
6. full-mode 노드 테스트를 추가한다.
7. `tests/test_core.py`, `config.py`, `opportunities.py`를 책임 단위로 분리한다.

## 현재 강점

- `unittest`, ruff, package build, docs build는 현재 통과한다.
- retrieval/parsing stack과 LangGraph orchestration을 재사용하는 큰 구조는 적절하다.
- fallback/resume/cache에 대한 의식은 코드 전반에 있다.
- OpenAI OAuth proxy 추가는 별도 테스트 파일로 격리되어 있어 기존 oversized test file을 더
  키우지 않는 방향으로 들어갔다.
