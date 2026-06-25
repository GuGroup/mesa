# 연구 프롬프트 작성

SearchAgent는 소재와 반응만이 아니라 연구 컨텍스트를 함께 제공할 때 가장 잘
동작합니다. 프롬프트는 `run_manifest.json`에 저장되고, 검색 쿼리 확장에 쓰이며,
opportunity 리포트(풀 모드에서는 LLM 랭킹과 리포트)의 우선순위 결정에 사용됩니다.

## 인라인 또는 파일

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --prompt "Prioritize durability and alkaline-stability gaps."
```

긴 컨텍스트는 마크다운 파일로 전달합니다.

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --prompt-file research-prompt.md
```

```markdown
We are choosing follow-up DFT calculations for a joint experimental/computational
HER project. The experimental team can synthesize RuO2-rich surfaces but needs
guidance on which facets have enough activity evidence and which ones lack
descriptor or stability data. Prioritize tractable slab calculations that close a
clear literature gap.
```

CLI 프롬프트 값은 `config.yaml`의 `research.prompt`를 덮어씁니다.

## 설정의 구조화된 컨텍스트

반복 사용하는 컨텍스트는 `config.yaml`의 `research` 블록에 설정합니다.

```yaml
research:
  prompt: >
    Prioritize DFT-feasible surfaces where HER activity is reported but
    descriptor and stability data are missing.
  decision_criteria:
    - prioritize surfaces with activity evidence but missing descriptors
  target_properties:
    - activity
    - descriptor
    - stability
  constraints:
    - full-text evidence only
  calculation_preferences:
    - adsorption/free-energy descriptors
    - surface stability under reaction-relevant conditions
```

이 필드들은 쿼리 확장과 우선순위 산정 근거를 유도하며, 산출물의 `research_context`에
나타납니다.
