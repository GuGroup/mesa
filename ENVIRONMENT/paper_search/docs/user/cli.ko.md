# CLI 사용

진입점은 `paper-search run` 하나입니다. `CatalystLiteratureGraph`를 빌드·실행하며,
provider가 설정되지 않으면 deterministic으로 동작합니다.

```bash
uv run paper-search run \
  --material RuO2 \
  --reaction HER \
  --out data/runs/ruo2-her
```

## 옵션

| 플래그 | 설명 |
| --- | --- |
| `--material` | 대상 소재 (필수). |
| `--reaction` | 대상 반응/응용 (필수). |
| `--out` | 출력 디렉터리. 선택 — 생략 시 `~/.SearchAgent` 아래 세션 폴더 ([설치 → 저장 구조](../admin/setup.md#storage-layout) 참고). |
| `--session` | base 아래 이름 있는 세션 폴더 재사용(resume용); `--out`을 주면 무시. |
| `--config` | YAML/OmegaConf 설정 파일. 없으면 `./config.yaml` 사용. |
| `--email` | OpenAlex/Crossref/Unpaywall 예의 바른 사용을 위한 이메일. |
| `--limit` | 쿼리당 검색 개수. |
| `--max-papers` | 처리할 중복 제거 논문 수 상한. |
| `--timeout` | HTTP 타임아웃(초). |
| `--prompt` | 연구 방향 / 의사결정 질문. |
| `--prompt-file` | 상세 연구 컨텍스트가 담긴 텍스트/마크다운 파일. |
| `--provider` | `none`(기본) / `anthropic` / `openai` / `openai-oauth`. [풀 에이전트 모드](full-agent.md) 참고. |
| `--model` | 선택한 provider의 채팅 모델 id 재정의. |
| `--extra-term` | 추가 쿼리 용어 (반복 가능). |
| `--no-resume` | 캐시된 산출물을 무시하고 가능한 단계를 재계산. |
| `--grobid-url`, `--grobid-start-cmd`, `--opendataloader-cmd` | 파서 재정의 ([설치](../admin/setup.md) 참고). |

CLI 값은 `config.yaml`을 덮어씁니다. 우선순위는 [설치 & 설정](../admin/setup.md)을
참고하세요.

## 출력

완료되면 모드, 논문/클레임 수, 산출물 경로를 출력합니다.

```text
mode=deterministic
papers=12
surface_claims=23
manifest=data/runs/ruo2-her/run_manifest.json
```

풀 모드에서는 `report=...report.md` 줄도 출력됩니다. 산출물 레퍼런스는
[출력물](outputs.md)을 참고하세요.

## Resume

실행은 기본적으로 재개 가능합니다. `resume`가 켜져 있으면 성공한 산출물(`papers.json`,
resolved links, 다운로드 소스, 성공한 파싱 블록, 논문별 `surface_claims.json`, 그리고
풀 모드의 PaperQA 인덱스)을 재사용합니다. 실패하거나 미완료된 단계는 재시도하며,
논문별 실패는 실행을 멈추지 않고 기록됩니다. `--no-resume`로 재계산을 강제할 수
있습니다. 자세한 내용은 [설치 & 설정](../admin/setup.md#retry-and-resume)을 참고하세요.
