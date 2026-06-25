# 출력물

실행하면 출력 디렉터리 아래에 기계가 읽을 수 있는 산출물이 기록됩니다 — 기본값은
세션 폴더 `~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/`이고, `--out`을
주면 그 경로입니다([설치 → 저장 구조](../admin/setup.md#storage-layout) 참고).

```text
<output dir>/
  papers.json
  run_manifest.json
  surface_claims.json
  opportunity_report.json
  report.md            # 풀 모드 전용
  llm_cache.db         # 풀 모드 전용 (SQLite 응답 캐시)
  paperqa/             # 풀 모드 전용 (영속화된 PaperQA 인덱스)
  papers/<paper_id>/
    metadata.json
    sources/
      resolved_links.json
      source_manifest.json
    parses/
      parse_manifest.json
      *.blocks.json
    extraction/
      surface_claims.json
```

## `surface_claims.json`

표면 클레임은 특정 표면을 대상 반응과 연결하는 근거 스니펫입니다(deterministic 모드는
규칙 추출, 풀 모드는 LLM 추출).

```json
{
  "paper_id": "paper1",
  "material": "RuO2",
  "reaction": "HER",
  "surface_text": "(110)",
  "evidence_text": "RuO2(110) surface shows HER activity at 42 mV.",
  "claim_type": "activity",
  "value": "42",
  "unit": "mV",
  "confidence": 0.8
}
```

## `opportunity_report.json`

핵심 의사결정 지원 산출물입니다. 주요 필드:

- `research_context`: 사용자가 제공한 연구 방향.
- `prioritization_basis`: 랭킹·제안에 사용된 신호.
- `candidate_surfaces`: 표면별 묶음 레코드와 커버리지 공백.
- `calculation_suggestions`: 제안된 다음 계산.
- `run_level_gaps`: 실행 전체에 영향을 주는 문제.
- `llm_ranking`(풀 모드): LLM이 정제한 표면 랭킹과 제안.

제안 예시:

```json
{
  "material": "RuO2",
  "reaction": "HER",
  "surface": "(110)",
  "calculation_type": "descriptor_calculation",
  "reason": "Activity evidence exists, but descriptor evidence was not extracted.",
  "suggested_next_step": "Compute adsorption/free-energy descriptors for the reported active surface.",
  "priority": "high"
}
```

## `report.md` (풀 모드)

풀 에이전트 모드에서 `report_writer`는 인용 기반 마크다운 표면 모델링 제안서를
생성합니다: 랭킹된 후보 표면, 권장 계산(facet, descriptor, stability, selectivity),
열린 데이터 공백 — 모두 검증된 클레임과 PaperQA 근거에 기반합니다.

## `run_manifest.json`

프로비넌스가 풍부한 산출물입니다.

- `mode`(`deterministic` / `full`)와 `provider`,
- `rounds`(실행된 gap-driven 검색 라운드 수)와 `coverage`(루프를 구동한 공백 요약),
- 쿼리 목록과 검색 오류,
- 논문별 resolver/download/parse 상태,
- 추출된 클레임,
- `validated_claims` — 각 클레임과 PaperQA `validation`(deterministic 모드나 검증 상한
  초과 시 `null`),
- opportunity 리포트(풀 모드에서는 `llm_ranking` 포함),
- 재시도·재개 harness 이벤트.

논문이 포함/제외되었거나 `full_text_unavailable`로 표시된 이유를 디버깅할 때 이 파일을
사용하세요. 파싱된 본문이 `parsers.min_full_text_chars`보다 짧을 때도
`full_text_unavailable`로 표시됩니다(콘텐츠 품질 게이트): 제목만 있거나 메타데이터
스텁인 다운로드 — 예: 인증되지 않은 Elsevier `coredata` 응답 — 은 전문인 척하며 근거 0을
내는 대신 거부됩니다(`parsed_char_count`에 측정된 길이가 기록됨). `harness` 섹션은 resume
재사용, HTTP 재시도 대기, 실행을 멈추지 않은 논문별 단계 오류를 기록합니다.

```json
{
  "harness": {
    "resume": true,
    "resume_events": [
      {"stage": "parse", "paper_id": "paper1", "status": "reused_successful_parse"}
    ],
    "http_retry": {
      "event_count": 1,
      "events": [
        {"url": "https://api.semanticscholar.org/...", "attempt": 1, "status": 429, "sleep_seconds": 60}
      ]
    },
    "error_count": 1,
    "errors": [
      {"stage": "extract", "paper_id": "paper2", "error_type": "JSONDecodeError", "error": "Expecting value..."}
    ]
  }
}
```
