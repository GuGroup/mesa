# Heterostructure 기능 조사 및 Skill 전환 계획

## 목적

현재 `build_tools` 저장소가 Ru/RuO2, RuO2/Ru, Pt 등의 clean slab 및 adsorbate workflow를 skill 형태로 제공하고 있으므로, 원본 slabuilder 프로젝트에 있던 heterostructure/interface 기능을 다시 가져와 별도 skill로 분리할지 검토한다.

이 문서는 구현 전 조사 결과와 이식 계획이다. 코드 구현은 포함하지 않는다.

## 확인한 경로

- 현재 저장소: `/Users/mingi/compchem/build_tools`
- 현재 vendored slabuilder: `/Users/mingi/compchem/build_tools/slabuilder`
- 원본 slabuilder 후보: `/Users/mingi/compchem/slab_build/slabuilder`
- 사용자가 말한 `../slabuilder`는 현재 cwd(`/Users/mingi/compchem/build_tools`) 기준으로는 존재하지 않았다.

## 현재 build_tools 기능 보유 여부

현재 `build_tools/slabuilder`에는 heterostructure/interface 전용 기능이 없다.

확인된 현재 기능:

- `slabuilder/slab_gen.py`: clean slab generation
- `slabuilder/adsorption.py`: adsorption site detection 및 adsorbate placement
- `slabuilder/site_map.py`, `structure_understanding.py`: saved structure/site inspection
- `slabuilder/cell_shape.py`: 2D cell transform/scoring utilities
- `SKILL/TASK_BUILD_SLAB_MODELS`: clean slab skill
- `SKILL/TASK_PLACE_SURFACE_ADSORBATES`: adsorbate placement skill
- `SKILL/TBD_INSPECT_SURFACE_SITES`: read-only inspection skill

현재 저장소에 없는 것:

- `slabuilder/interface.py`
- `screen_interfaces`
- `build_bulk_like_interface`
- `build_heterostructure` CLI/script
- interface-specific settings/defaults
- heterostructure metadata/export workflow
- heterostructure 전용 skill

따라서 현재 저장소는 RuO2/Ru 같은 periodic coherent interface를 직접 만들 수 없고, clean slab를 만든 뒤 수동 조합하는 수준만 가능하다.

## 원본 slabuilder의 hetero 기능 요약

원본 구현의 핵심 파일은 `/Users/mingi/compchem/slab_build/slabuilder/interface.py`이다.

주요 API:

- `screen_interfaces(substrate_structure, film_structure, max_miller, max_matches, lowest, max_area)`
  - pymatgen `SubstrateAnalyzer`를 사용한다.
  - substrate/film Miller pair 후보를 ZSL matching으로 스크리닝한다.
  - 결과는 `InterfaceScreenMatch` dataclass로 반환한다.
  - 반환 필드: `substrate_hkl`, `film_hkl`, `von_mises_strain`, `match_area`, `score`, `film_transformation`, `substrate_transformation`, area multiple.

- `build_bulk_like_interface(...)`
  - pymatgen `CoherentInterfaceBuilder`와 `ZSLGenerator`를 사용한다.
  - bulk structure 두 개와 Miller index 두 개를 직접 받아 3D-periodic coherent interface를 만든다.
  - pre-generated slab는 필요하지 않다.
  - 기본 결과는 vacuum 없는 bulk-like periodic interface이다.

중요한 품질 제어:

- strain bucket 기반 정렬: <=2%, <=5%, <=10%, >10%
- matched area 및 lateral length 제한
- target atom count 근처 선호
- cell shape score: in-plane shape, normal angle, c/lateral ratio, component thickness balance, atom count penalty
- gap retry: 기본 `[0.8, 1.1, 1.4, 1.7] Angstrom`
- termination scan: 요청 termination 실패 시 다른 termination pair 자동 시도
- minimum film-substrate MIC distance guard: 기본 1.0 Angstrom
- max atoms: DFT cap 기본 200
- layer search: 요청 layer pair 주변에서 더 compact한 layer count 조합 탐색

원본 설정:

- `interface.screen.max_miller`: 2
- `interface.screen.max_matches`: 20
- `interface.screen.max_area`: 160.0 Angstrom^2
- `interface.screen.hard_max_area`: 250.0 Angstrom^2
- `interface.build.n_layers_a`: 6
- `interface.build.n_layers_b`: 6
- `interface.build.target_atom_count`: 125
- `interface.build.atom_count_tolerance`: 50
- `interface.build.gap`: 0.8 Angstrom
- `interface.build.min_interface_distance`: 1.0 Angstrom
- `interface.build.vacuum`: 0.0 Angstrom
- `interface.build.max_lateral_length`: 25.0 Angstrom
- `interface.build.hard_max_lateral_length`: 35.0 Angstrom

원본 agent guidance의 핵심:

- `build_heterostructure`는 clean slab 생성이 선행 조건이 아니다.
- 사용자가 plane을 둘 다 지정하지 않으면 `screen_interfaces`를 먼저 실행한다.
- 같은 bulk의 homo-interface도 `mpid_b` 생략으로 지원한다.
- 다른 물질 interface는 substrate/film MP-ID를 명시한다.
- 여러 후보를 만들 때는 top N <= 5로 제한한다.
- `vacuum=0.0`이 기본이며 slab/vacuum model이 필요할 때만 vacuum을 둔다.
- strain > 10%는 사용자에게 경고해야 한다.

## 현재 저장소로 이식할 때의 권장 아키텍처

현재 `build_tools`는 원본 demo app이 아니라 local skill + script 중심이다. 따라서 원본의 FastAPI/session/UI 코드를 그대로 옮기기보다는 core 기능과 thin CLI wrapper만 가져오는 방식이 적절하다.

### 1단계: core interface 모듈 이식

추가 후보:

- `slabuilder/interface.py`

함께 필요한 export:

- `slabuilder/__init__.py`에 `InterfaceScreenMatch`, `screen_interfaces`, `build_bulk_like_interface`, `interface_to_wrapped_ase` export 추가

의존성 확인:

- 이미 현재 저장소에 `slabuilder/cell_shape.py`, `slabuilder/config.py`, `slabuilder/utils.py`가 있다.
- 원본 `interface.py`는 `get_settings()`를 사용하지만 현재 trimmed 저장소에는 `settings.py/defaults.yml`이 없다.
- 이식 시 선택지는 두 가지다.
  - 간단한 방법: `interface.py` 내부에 현재 skill용 default constant를 직접 둔다.
  - 정돈된 방법: trimmed `config.py`에 interface defaults를 추가하고 `settings.py` 전체 이식은 피한다.

권장: 현재 저장소 목적이 skill runtime이므로 `settings.py/defaults.yml` 전체 이식은 과하다. `config.py`에 interface default constants만 추가한다.

### 2단계: standalone scripts 추가

새 skill이 사용할 스크립트는 두 개로 분리하는 것이 좋다.

- `skills/build-heterostructures/scripts/screen_interfaces.py`
  - 입력: `--substrate-formula` 또는 `--substrate-mpid`, `--film-formula` 또는 `--film-mpid`
  - 입력: `--max-miller`, `--max-matches`, `--max-area`, `--lowest/--all-matches`
  - 출력: JSON table 및 `screen_results.json`

- `skills/build-heterostructures/scripts/build_heterostructure.py`
  - 입력: substrate/film formula or MP-ID
  - 입력: `--substrate-miller h k l`, `--film-miller h k l`
  - 선택 입력: `--screen-results`, `--screen-index`
  - 선택 입력: `--substrate-layers`, `--film-layers`, `--substrate-termination`, `--film-termination`
  - 선택 입력: `--gap`, `--auto-gap/--no-auto-gap`, `--gap-retry-sequence`
  - 선택 입력: `--scan-terminations/--no-scan-terminations`
  - 선택 입력: `--min-interface-distance`, `--vacuum`
  - 선택 입력: `--max-area`, `--max-atoms`, `--max-lateral-length`
  - 출력: `.extxyz`, `_POSCAR.vasp`, `.metadata.json`

출력 metadata에는 최소한 다음을 포함한다.

- substrate/film formula, MP-ID, Miller index
- selected/requested layers
- selected/requested terminations
- strain tensor summary, von Mises strain
- match area
- film/substrate transformation matrices
- film/substrate area multiple
- selected gap, gap attempts
- min interface distance, validation metrics
- cell shape summary
- atom count, cell lengths
- exported path 및 POSCAR/extxyz index mapping

### 3단계: 신규 skill 추가

skill 이름 후보:

- `build-heterostructures`

트리:

```text
skills/build-heterostructures/
  SKILL.md
  scripts/
    screen_interfaces.py
    build_heterostructure.py
```

skill trigger:

- heterostructure
- hetero
- interface
- coherent interface
- Ru/RuO2 interface
- RuO2-Ru hetero
- periodic interface
- bulk-like interface

skill scope:

- 두 bulk phase 사이 coherent interface 후보를 screen한다.
- 선택된 Miller pair 또는 screened match로 bulk-like periodic heterostructure를 만든다.
- clean slab skill과 다르게, pre-generated slab를 요구하지 않는다.
- 결과는 DFT-ready starting geometry 후보이며, final relaxed interface는 아니다.

skill이 명시해야 할 정책:

- 먼저 bulk 후보를 확인한다.
- Miller index가 불명확하면 screen부터 한다.
- 기본값은 compact/low-strain 후보 우선이다.
- `max_area`, `max_atoms`, `max_lateral_length`를 무작정 키우지 않는다.
- strain > 5%는 주의, >10%는 강한 경고.
- `vacuum=0` 기본은 3D periodic bulk-like interface이다.
- slab/vacuum heterointerface가 필요하면 사용자가 명시해야 한다.
- 여러 후보 생성은 기본 top 3, 최대 5로 제한한다.
- 생성 후 반드시 metadata의 strain, atom count, min distance, cell shape, selected terminations를 요약한다.

## 사용자-facing 예시 프롬프트

짧은 테스트용:

```text
현재 폴더에 hetero_test를 만들고 RuO2/Ru coherent interface 후보를 screen해줘.
RuO2는 mp-825, Ru는 mp-33으로 두고 max_miller=2, top 10만 보여줘.
```

생성까지:

```text
RuO2(110)/Ru(0001) bulk-like periodic interface를 만들어줘.
결과는 hetero_test에 저장하고 strain, atom count, gap validation을 요약해줘.
```

screen 결과 기반:

```text
RuO2/Ru interface를 max_miller=2로 screen하고 가장 compact한 low-strain 후보 3개를 만들어줘.
각 후보의 Miller pair, strain, atom count, min distance를 비교해줘.
```

## 구현 순서 제안

1. `slabuilder/interface.py`를 원본에서 가져오되 `settings.py` 의존성을 `config.py` constants로 대체한다.
2. `slabuilder/__init__.py` export를 추가한다.
3. interface metadata와 VASP/extxyz export는 현재 `slabuilder/utils.py`의 POSCAR/export helper와 맞춘다.
4. `scripts/screen_interfaces.py`를 만든다.
5. `scripts/build_heterostructure.py`를 만든다.
6. `skills/build-heterostructures/SKILL.md`를 작성한다.
7. `scripts/sync_codex_skills.py`로 설치된 Codex skill symlink(`/Users/mingi/.codex/skills`)에도 반영한다.
8. 단위 테스트를 추가한다.
9. smoke test를 수행한다.

## 테스트 계획

단위 테스트:

- `screen_match_sort_key`: 낮은 strain bucket 우선인지 확인
- `interface_shape_score`: rectangular cell이 skewed cell보다 선호되는지 확인
- `_gap_attempt_values`: 요청 gap과 retry sequence 순서 확인
- `_termination_attempt_values`: 요청 termination 우선, 중복 제거 확인
- `_interface_min_mic_distance`: film-substrate pair 거리만 보는지 확인

스크립트 테스트:

- Pt/Pt homo-interface: local cubic structure로 network 없이 build smoke 가능
- RuO2/Ru MP 기반 screen: network/API key 필요
- RuO2(110)/Ru(0001) build: network/API key 필요

검증 기준:

- `.extxyz`, `_POSCAR.vasp`, `.metadata.json`가 모두 생성된다.
- metadata에 strain, match area, transformation matrices, gap attempts, selected layers가 들어간다.
- `min_interface_distance` guard가 통과한다.
- atom count가 `max_atoms` 이하이다.
- POSCAR reorder가 있다면 index mapping이 metadata에 저장된다.

## 예상 리스크

- pymatgen `CoherentInterfaceBuilder` API 버전 차이.
- 원본 `interface.py`가 `settings.py`에 의존하므로 trimmed repo에 맞게 constants 정리가 필요하다.
- Ru/RuO2처럼 금속/산화물 조합은 작은-area low-strain 후보가 없을 수 있다.
- termination label ordering은 pymatgen 내부 ordering에 의존하므로 metadata에 selected label을 반드시 저장해야 한다.
- magnetic moments는 species-uniform일 때만 안전하게 복원 가능하다. AFM처럼 site-dependent magmom은 자동 추정하면 안 된다.
- bulk-like periodic interface와 slab/vacuum interface를 혼동하기 쉽다. skill 문서에서 기본값을 명확히 해야 한다.

## 결론

현재 `build_tools`에는 heterostructure 기능이 없다. 원본 `/Users/mingi/compchem/slab_build/slabuilder`에는 pymatgen ZSL 기반 coherent interface screening/build 기능이 이미 있고, 이를 core 모듈 + two-script skill 형태로 옮기는 것이 가장 적절하다.

권장 방향은 `build-slab-models`에 억지로 합치지 않고 `build-heterostructures`라는 별도 skill로 분리하는 것이다. clean slab, adsorbate, interface는 입력 모델과 검증 기준이 다르므로 skill도 분리하는 편이 안전하다.
