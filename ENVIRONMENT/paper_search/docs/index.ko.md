# SearchAgent

SearchAgent는 촉매/소재 표면 모델링을 위한 전문(full text) 문헌 **에이전트**입니다.
연구 프롬프트를 받으면 논문을 검색하고, 오픈액세스/TDM source를 먼저 사용한 뒤 설정
가능한 Sci-Hub fallback으로 usable full text를 resolve합니다. 이후 LLM과 PaperQA2로
학습하고, 근거를 인용과 대조해 검증하고, 데이터 공백을 찾아, 다음에 수행할 표면 모델링
계산을 제안합니다.

LangGraph `StateGraph`(9개 노드)로 오케스트레이션되며, `llm.provider` 설정에 따라 두
가지 모드로 실행됩니다.

| 모드 | 필요 조건 | 하는 일 |
| --- | --- | --- |
| Deterministic (기본) | API 키 불필요 | 규칙 기반 쿼리 계획, 정규식 표면-클레임 추출, 규칙 기반 opportunity 리포트 |
| Full agent | `anthropic` / `openai` 키 또는 `openai-oauth` 프록시 | LLM 쿼리 확장 + sub-question, 관련성 grading, **gap-driven 반복 재검색**, PaperQA2 에이전트 근거 + 인용 기반 검증, LLM gap 랭킹, 인용 기반 `report.md` |

## 어디서 시작할까

| 역할 | 문서 |
| --- | --- |
| 처음, 최소 흐름으로 실행 | [빠른 시작](quickstart.md) |
| 커맨드라인에서 실행 | [CLI 사용](user/cli.md) |
| LLM + PaperQA 에이전트 켜기 | [풀 에이전트 모드](user/full-agent.md) |
| 프롬프트로 에이전트 유도 | [연구 프롬프트 작성](user/research-prompt.md) |
| 결과 읽고 해석 | [출력물](user/outputs.md) |
| 그래프를 시각적으로 확인 | [LangGraph Studio](user/studio.md) |
| 아키텍처 이해 | [에이전트 그래프](architecture/agent-graph.md) |
| 설치 및 설정 | [설치 & 설정](admin/setup.md) |
| 개발 및 테스트 | [개발](admin/development.md) |
| 문서 사이트 배포 | [배포](admin/deployment.md) |

처음 사용해 본다면 [빠른 시작](quickstart.md)부터 따라가면 됩니다.

## 핵심 정책

- 1차 전문 source는 Unpaywall OA location, Crossref TDM link, 설정된 Elsevier 같은
  출판사 full-text API입니다.
- Sci-Hub fallback은 기본 활성화되어 있고, 1차 source로 usable full text를 얻지 못한
  논문에만 마지막으로 시도합니다.
- 출판사 스크레이핑, 사용자 업로드 PDF, 초록만으로의 근거 추출은 사용하지 않습니다.
