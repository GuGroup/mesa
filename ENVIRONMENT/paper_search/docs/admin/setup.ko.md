# 설치 & 설정

## 설치

```bash
uv sync
```

선택적 extra:

```bash
uv sync --extra docs              # MkDocs Material (사이트 빌드)
uv sync --extra studio            # langgraph-cli (LangGraph Studio)
uv sync --extra local-embeddings  # sentence-transformers (로컬 PaperQA 임베딩)
```

`torch`는 코어 설치에 **포함되지 않습니다** — `local-embeddings`에만 따라옵니다.
deterministic 모드와 OpenAI 임베딩 풀 모드는 이를 필요로 하지 않습니다.

## 저장 구조 { #storage-layout }

기본적으로 각 실행은 `~/.SearchAgent` 아래에 자체 격리 세션 폴더를 만듭니다(base는
`$SEARCHAGENT_HOME`으로 변경):

```text
~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/
  run_manifest.json  surface_claims.json  opportunity_report.json
  report.md  llm_cache.db  paperqa/  papers/<paper_id>/{sources,parses,extraction}
```

- 세션은 **완전히 격리**됩니다 — 다운로드한 논문·캐시는 세션 간 공유되지 않습니다.
- `--out <dir>`을 주면 그 경로에 저장하며, 같은 `--out`으로 재실행하면 resume됩니다.
- `--session <id>`로 base 아래 이름 있는 세션 폴더를 재사용합니다(resume용).

## 설정 레이어

- `config.yaml`: 비밀이 아닌 런타임 설정. OmegaConf로 로드.
- `.env`: 로컬 시크릿. `python-dotenv`로 로드.

`config.yaml`은 선택 사항이며, 작업 디렉터리에 있으면 자동 로드됩니다. `--config`로 다른
경로를 지정할 수 있습니다.

```text
CLI 인자 > --config YAML > ./config.yaml > 구조화된 기본값
```

셸 환경 변수가 `.env` 값보다 우선합니다(`.env`는 `override=False`로 로드).

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

## 시크릿

```env
PAPER_SEARCH_EMAIL=you@example.com
SEMANTIC_SCHOLAR_API_KEY=
ELSEVIER_API_KEY=
ELSEVIER_INSTTOKEN=
OPENAI_API_KEY=
OPENAI_EMBEDDING_KEY=
OPENAI_BASE_URL=
ANTHROPIC_API_KEY=
```

YAML에서 `oc.env` 보간으로 시크릿을 참조합니다.

```yaml
semantic_scholar:
  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
```

LLM 키(`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) 또는 로컬 `openai-oauth`
프록시가 풀 에이전트를 활성화합니다. PaperQA OpenAI 임베딩은 별도의
`OPENAI_EMBEDDING_KEY`를 사용합니다 — [풀 에이전트 모드](../user/full-agent.md)를 참고하세요.

## 검색

```yaml
search:
  per_query_limit: 10
  max_papers: 30
  max_concurrency: 4    # 동시 (query, client) 검색 요청 수
```

### Semantic Scholar rate limit

Semantic Scholar는 API 키가 있어도 모든 엔드포인트 합산 **초당 1회**만 허용합니다(키는
`x-api-key` 헤더로 전송). 클라이언트가 요청을 직렬화하고 간격을 띄웁니다 —
`min_request_interval`은 `1.0` 이상으로 두세요:

```yaml
semantic_scholar:
  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
  min_request_interval: 1.1
```

다른 클라이언트(Crossref/OpenAlex)는 계속 동시 실행되고, Semantic Scholar만
throttle됩니다.

### Elsevier 전문 (선택) { #elsevier-full-text }

Elsevier 논문의 Crossref TDM 링크는 `api.elsevier.com`을 가리킵니다. 인증 없이
받으면 이 엔드포인트는 본문이 없는 **coredata** 스텁(제목·DOI·저널만)을 돌려주고,
이는 제목 1블록짜리 문서로 파싱되어 근거가 0이 됩니다.
[Elsevier API 키](https://dev.elsevier.com/)와 기관 엔타이틀먼트(기관 IP 또는 inst
token)가 있으면 같은 링크가 전문 XML을 반환합니다. SearchAgent는 자격증명을
`api.elsevier.com` 요청에만 붙이므로 비-Elsevier 다운로드에는 영향이 없습니다.

```yaml
elsevier:
  api_key: ${oc.env:ELSEVIER_API_KEY,""}
  inst_token: ${oc.env:ELSEVIER_INSTTOKEN,""}   # 키가 IP로 엔타이틀되지 않은 경우만
```

```env
ELSEVIER_API_KEY=your-key
ELSEVIER_INSTTOKEN=
```

둘 다 비우면 Elsevier 인증을 건너뜁니다(coredata 스텁은 여전히 다운로드되지만 근거에는
기여하지 않음). Elsevier API를 통한 TDM은 소속 기관의 ScienceDirect 계약과 Elsevier API
정책을 따릅니다.

## 파서

지원 파서 경로:

- `oa_xml` → 내장 XML/JATS/TEI 블록 파서.
- `oa_pdf` → OpenDataLoader(기본)와 GROBID(opt-in).

OpenDataLoader는 일반 의존성입니다. 표준 디지털 PDF는 어댑터가 Python API를 먼저
시도하고, 다음으로 설정된 CLI 형식을 시도합니다.

GROBID는 **선택 사항**이며 기본적으로 절대 시작되지 않습니다. 서비스를 직접 운영하거나
관리형 start 명령을 제공할 때만 설정하세요.

```yaml
parsers:
  grobid:
    url: ${oc.env:PAPER_SEARCH_GROBID_URL,""}
    start_cmd: ${oc.env:PAPER_SEARCH_GROBID_START_CMD,""}
    startup_timeout: 120
    shutdown_timeout: 10
  opendataloader:
    cmd: ${oc.env:PAPER_SEARCH_OPENDATALOADER_CMD,"opendataloader-pdf {input} {output_dir}"}
```

GROBID URL이나 start 명령이 설정되면 PDF 파싱은 GROBID를 lazily 시도한 뒤
OpenDataLoader로 이어집니다.

## 재시도와 재개 { #retry-and-resume }

일시적 API 실패는 `http.retry`의 상태 코드를 재시도합니다. `429`의 경우 `Retry-After`가
있으면 이를 존중하고, 없으면 backoff 시퀀스를 사용합니다.

```yaml
http:
  timeout: 30
  retry:
    max_attempts: 4
    backoff_seconds: [5, 15, 60]
    retry_statuses: [429, 500, 502, 503, 504]
    respect_retry_after: true
    max_sleep_seconds: 120
```

실행은 기본적으로 재개 가능합니다.

```yaml
execution:
  resume: true
  checkpoint: false   # opt-in LangGraph 체크포인터 (스트리밍/검사)

agent:
  max_search_rounds: 3          # gap-driven 재검색 루프 (1 = 단일 패스)
  min_new_papers_to_continue: 1 # 신규 관련 논문이 없으면 라운드 종료
  relevance_filter: lenient     # strict | lenient(주제 일치 + 애매하면 통과) | off
```

`agent` 블록은 gap-driven 루프를 제어합니다.
[풀 에이전트 모드](../user/full-agent.md#iterative-gap-driven-loop)를 참고하세요.

`resume`가 켜지면 성공한 산출물이 재사용됩니다: `papers.json`, resolved links, 다운로드
소스, 성공한 파싱 블록, 논문별 `surface_claims.json`, 그리고 (풀 모드) PaperQA 인덱스.
실패하거나 미완료된 단계는 재시도되며, 논문별 실패는 실행을 멈추지 않고
`run_manifest.json`에 기록됩니다. JSON 산출물은 atomic replacement로 기록됩니다.
`--no-resume`로 재계산을 강제할 수 있습니다.

풀 모드에서는 SQLite 응답 캐시(`llm_cache.db`)가 두 번째 레이어를 더합니다. `--no-resume`
상태여도 동일한 LLM 프롬프트는 재과금 대신 캐시에서 제공됩니다.
[풀 에이전트 모드](../user/full-agent.md#caching)를 참고하세요.
