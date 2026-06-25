# 빠른 시작

처음 **deterministic** 실행(키 불필요)을 위한 최소 흐름입니다. 풀 LLM + PaperQA
에이전트는 [풀 에이전트 모드](user/full-agent.md)를 참고하세요.

## 1. 설치

```bash
uv sync
```

OpenDataLoader(PDF 파싱)는 기본 포함입니다. GROBID는 선택 사항입니다 —
[설치 & 설정](admin/setup.md)을 참고하세요.

## 2. (선택) 로컬 파일

```bash
cp config.example.yaml config.yaml
cp .env.example .env       # 예의 바른 API 사용을 위해 PAPER_SEARCH_EMAIL 설정
```

두 파일 모두 선택 사항이며, 없으면 구조화된 기본값이 사용됩니다.

## 3. 실행

```bash
uv run paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her
```

`--out`은 선택입니다 — 생략하면 `~/.SearchAgent/sessions/<material>_<reaction>_<timestamp>/`
세션 폴더에 저장됩니다([설치 → 저장 구조](admin/setup.md#storage-layout) 참고).

Crossref / OpenAlex / Semantic Scholar를 검색하고, usable full text를
resolve·다운로드하고, 파싱한 뒤, 표면 근거를 추출합니다 — 모두 규칙 기반으로요.

## 4. 결과 확인

```bash
python -m json.tool data/runs/ruo2-her/opportunity_report.json
```

먼저 `candidate_surfaces`, `calculation_suggestions`, `run_level_gaps`를 보세요.
전체 산출물은 [출력물](user/outputs.md)을 참고하세요.

## 다음

- [CLI 사용](user/cli.md) — 모든 플래그와 resume 동작
- [풀 에이전트 모드](user/full-agent.md) — LLM + PaperQA 활성화
- [연구 프롬프트 작성](user/research-prompt.md) — 에이전트 유도
