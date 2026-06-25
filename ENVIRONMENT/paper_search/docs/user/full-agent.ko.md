# 풀 에이전트 모드

기본적으로 SearchAgent는 deterministic(규칙 기반, 키 불필요)으로 동작합니다.
provider를 설정하면 풀 에이전트가 켜집니다: LLM 쿼리 확장, LLM 구조화 추출, 파싱된
전문의 PaperQA2 인덱싱, 인용 기반 클레임 검증, LLM 보강 gap 랭킹, 그리고 인용 기반
`report.md`.

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --provider openai --prompt "prioritize DFT-feasible HER surfaces"
```

LLM/PaperQA 노드는 provider에 따라 self-gate합니다. 키가 없는 노드는 deterministic
경로로 폴백하므로, 키가 빠져도 실행이 완전히 실패하지 않습니다.

## Provider와 키

| Provider | 키 (`.env`) | 기본 모델 |
| --- | --- | --- |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `OPENAI_API_KEY` | `gpt-5.4-mini` |
| `openai-oauth` | 없음; 로컬 `openai-oauth` 프록시 | `gpt-5.4` |

provider는 `--provider` 또는 `config.yaml`의 `llm.provider`로, 모델은 `--model` 또는
`llm.model`로 지정합니다.

```yaml
llm:
  provider: openai
  model: gpt-5.4-mini
  base_url:
  api_key_env:
  temperature: 0
  max_tokens: 4096
```

### OpenAI OAuth 프록시

`openai-oauth`는 커뮤니티 `npx openai-oauth` localhost 프록시를 통해 동작합니다.
`OPENAI_API_KEY`는 필요 없지만, 로컬 Codex/ChatGPT OAuth auth 파일이 있어야 하고
같은 머신에서 프록시 프로세스가 실행 중이어야 합니다.

```bash
npx @openai/codex login
npx openai-oauth

uv sync --extra local-embeddings
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --provider openai-oauth --model gpt-5.4
```

기본 OAuth 프록시 base URL은 `http://127.0.0.1:10531/v1`입니다. 프록시 위치가 다르면
`llm.base_url` 또는 `OPENAI_BASE_URL`로 바꾸세요. 이 프록시는 로컬 전용 호환 계층으로
두고, auth 파일을 공유하거나 프록시를 공용 네트워크에 노출하지 마세요.

## 캐싱 { #caching }

LLM 캐싱은 기본으로 켜져 있으며 `llm.cache`에서 끌 수 있습니다.

- `response_cache`: 프롬프트→응답 쌍을 `<out>/llm_cache.db`에 저장하는 SQLite 캐시
  (`response_cache_path`로 변경 가능). 동일한 재실행은 비용이 0입니다 —
  `execution.resume`와 같은 발상입니다.
- `prompt_cache`: 공유 corpus prefix에 대한 provider prompt 캐싱 — Anthropic은
  ephemeral `cache_control`, OpenAI는 prefix 캐싱이 자동입니다. 프롬프트는 크고
  안정적인 콘텐츠를 캐시 가능한 prefix에 두지만 효과는 제한적입니다(Anthropic은 최소
  크기 이상 prefix만 캐시). 실제 재실행 비용 절감의 주된 레버는 **응답 캐시**입니다.

## PaperQA2

PaperQA2(`paper-qa`)는 동일한 provider 키를 사용해 **로컬**에서 실행됩니다 —
FutureHouse 계정이나 API가 **필요 없습니다**. 파싱된 전문을 인덱싱하고 소재/표면
질문에 인용과 함께 답하며, 이는 클레임 검증과 리포트를 구동합니다.

```yaml
paperqa:
  enabled: true
  embedding:                  # 아래 참고
  evidence_k: 10
  answer_max_sources: 5
  validation_max_queries: 25  # 고유 표면당 1개 PaperQA 쿼리, 상한
  agentic: true               # 검증에 agent_query(multi-step gather) 사용
  agent_evidence_n: 5
  search_count: 8
```

클레임 검증은 클레임을 표면 단위로 중복 제거하고, 최대 `validation_max_queries`개의
PaperQA 쿼리(고유 표면당 1개)를 실행한 뒤, 각 판정을 해당 표면을 공유하는 클레임들에
매핑합니다. `agentic: true`이면 각 쿼리가 우리 코퍼스 위에서 PaperQA 에이전트
(`agent_query`, multi-step `gather_evidence`)를 사용하며, 오류 시 단일 `aquery`로
폴백합니다.

## gap-driven 반복 루프 { #iterative-gap-driven-loop }

에이전트는 근거 공백을 메우기 위해 재검색합니다. 랭킹 후 커버리지 공백이 남으면 gap을
조준한 쿼리(그리고 full 모드에서는 LLM이 분해한 sub-question과 LLM이 생성한 gap 쿼리)로
쿼리 계획으로 되돌아갑니다. 루프는 유계이며 멱등적입니다 — 각 라운드는 새로 찾은
논문만 처리합니다.

```yaml
agent:
  max_search_rounds: 3          # 1 = 단일 패스(루프 없음)
  min_new_papers_to_continue: 1 # 신규 관련 논문이 없으면 라운드 종료
  relevance_filter: lenient     # strict | lenient(주제 일치 + 애매하면 통과) | off
```

루프는 의미 있는 공백이 없거나, 라운드 예산이 소진되거나, 한 라운드가 신규 관련 논문을
추가하지 못하면 멈춥니다. `relevance_filter`는 다운로드 전에 hit을 채점합니다(deterministic
은 키워드, full은 LLM): `lenient`(기본)는 material/reaction 주제면 통과시키고 애매한 건
keep합니다(표면 세부는 보통 전문에만 있으므로); `strict`는 표면 근거 신호를 요구; `off`는
전부 통과.

### 임베딩

`OPENAI_EMBEDDING_KEY`가 있으면 임베딩은 OpenAI `text-embedding-3-small`을,
없으면 로컬 sentence-transformers 모델을 자동 선택합니다. 로컬 모델에는 선택적 extra가 필요합니다.

```bash
uv sync --extra local-embeddings
```

OpenAI 임베딩 키 없는 Anthropic 전용 또는 `openai-oauth` 환경이라면 이 extra를
설치하거나, `paperqa.embedding`을 명시(예: `st-multi-qa-MiniLM-L6-cos-v1`)하세요.

## 풀 모드에서 추가되는 산출물

- `report.md`: 인용 기반 표면 모델링 제안서.
- `run_manifest.json`의 `validated_claims`: 각 클레임과 PaperQA `validation`.
- `opportunity_report.llm_ranking`: LLM이 정제한 표면 랭킹.
- `llm_cache.db`, `paperqa/`: 응답 캐시와 영속화된 PaperQA 인덱스.

자세한 내용은 [출력물](outputs.md)을 참고하세요.
