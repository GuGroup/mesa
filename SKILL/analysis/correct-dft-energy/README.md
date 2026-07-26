# MESA OER and NO3RR Energy-Correction Skills

첨부된 alkaline-HER descriptor Skill의 구조를 기반으로 만든 두 개의 독립
Codex Skill입니다.

## 구성

```text
skills/
├── assemble-oer-energy-corrections/
└── assemble-no3rr-energy-corrections/
```

- **OER Skill**: `*`, `*OH`, `*O`, `*OOH` four-step AEM, O2 H2O/H2 cycle,
  RHE/SHE CHE, closure, limiting potential, thermodynamic overpotential.
- **NO3RR Skill**: HNO3 molecular correction, gas/liquid/aqueous nitrate cycle,
  RHE/SHE CHE, custom single-N pathways, eight-electron closure, nitrate
  adsorption diagnostics.

## 로컬 설치

Repository 범위:

```bash
mkdir -p .agents/skills
cp -R skills/assemble-oer-energy-corrections .agents/skills/
cp -R skills/assemble-no3rr-energy-corrections .agents/skills/
```

사용자 범위:

```bash
mkdir -p "$HOME/.agents/skills"
cp -R skills/assemble-oer-energy-corrections "$HOME/.agents/skills/"
cp -R skills/assemble-no3rr-energy-corrections "$HOME/.agents/skills/"
```

명시적 호출 예:

```text
Use $assemble-oer-energy-corrections to audit this OER endpoint JSON.
```

```text
Use $assemble-no3rr-energy-corrections to apply the HNO3 nitrate reference
cycle and audit this NO3RR pathway.
```

## 전체 검증

```bash
python3 skills/assemble-oer-energy-corrections/scripts/validate_skill.py
python3 skills/assemble-no3rr-energy-corrections/scripts/validate_skill.py
python3 -m compileall -q skills
```

## 중요한 제한

- OER은 AEM 전용이며 LOM을 자동 해석하지 않습니다.
- NO3RR은 단일 N의 nitrate-to-NH3 전용입니다.
- 4.92 eV와 1.12 eV는 자동 기본값이 아닙니다.
- 예제 endpoint energy는 계산기 검증을 위한 합성 데이터입니다.
- thermodynamic ranking을 barrier, current, Tafel slope, FE/selectivity로
  해석하면 안 됩니다.

자세한 차이는 `SOURCE_SKILL_ANALYSIS.md`, 연구실 규칙 예시는
`AGENTS.snippet.md`를 참고하십시오.
