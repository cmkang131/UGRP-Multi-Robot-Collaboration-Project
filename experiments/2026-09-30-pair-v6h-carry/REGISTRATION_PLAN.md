# b-v6h 등록 구현 계획 (초안 — 아직 등록·봉인·실행하지 않았다) (2026-09-30, Claude)

Refs #216. 이 문서는 `experiments/2026-09-30-b-v6h-gain`의 탐색 결과를 **등록된 제어기 변경**으로 옮기는 방법을 정한다. b-v6h1 구현 후보는 PR #292에 있고 아직 봉인하지 않았다. 과거 v6e 등록 바이트는 보존한다. 사전 등록 초안은 같은 폴더의 `PREREG_DRAFT.md`. **독립 검토(Opus) 전에는 봉인하지 않는다.**

## 1. 번호 예약

| 항목 | 예약 값 | 근거 |
|---|---|---|
| 실행 번들 | `zone-pair-v83-carry-door-gain` (번호 **v83**) | 2026-09-30 `git fetch` 뒤 `origin/main`과 열린 PR 브랜치(현재 #284 하나)에서 사용 중인 최댓값은 **v81**(`harness/zone_pair_v6_policy.py`, `configs/simulation_workflows.json`, `configs/zone_study_integration/llm_driver.json`, `harness/zone_study_integration.py`를 좁게 grep). v82/2.15.0/revision v6f는 v6e README가 "쓰지 않는 번호"로 명시했으므로 건너뛴다 |
| workflow | `2.16.0` | 2.15.0은 위와 같은 이유로 건너뜀. main과 열린 PR에서 2.15.0·2.16.0 사용 없음 |
| revision | `v6h` (`REVISION_POLICIES['v6h'] = ('v5h', 'b-only', <등록 정책 id>)`) | `CURRENT_REVISION = 'v6e'` 다음 |
| 등록 정책 id | **`b-v6h1`** (권장) | `b-v6h`는 이미 stage-probe의 opt-in 이름이다(`harness/zone_pair_door_relax.POLICY_ID`, 과거 raw와 TB 뷰가 이 이름을 쓴다). 같은 이름을 진짜 정책으로 재사용하면 과거 기록의 뜻이 바뀐다. 이름은 검토자가 바꿀 수 있다 |

실제 봉인 직전에 위 grep을 다시 돌려 다른 PR이 v83/2.16.0/v6h를 가져가지 않았는지 확인한다(가져갔으면 다음 번호로).

## 2. 무엇이 제어기 코드가 되나

탐색에서 프로세스 내부 패치였던 다섯 변경군을 `PairPolicy` 플래그로 만든다(기본값 = 등록 값 = 끔). 값은 탐색 코호트 그대로이며 이 값들이 확증 대상이다.

| 플래그(안) | 기본(끔) | b-v6h1 값 | 탐색 패치와의 대응 | 쓰이는 곳 |
|---|---|---|---|---|
| `carry_fwd_gain` | 1.0 | **0.9483378899463337** | `harness/zone_pair_carry_gain_fix.py`(`scaled_gain`, `enable_provider` 뒤에 한 번) | `harness/owncam_carry_v6e.enable_provider` 안, 든 PF의 `motion_loaded.gain[0][0]` 복사본 |
| `loaded_k_xy`, `loaded_k_yaw` | 2.0, 2.0 | **1.0, 1.0** | `relaxed_margin`(`SweepGuard.margin`의 σ 배수) | `harness/zone_own_guards.SweepGuard.margin` |
| `loaded_gate_yaw_deg` | `None`(3.0/2.5) | **(5.0, 4.0)** | `GATE_LOADED` 재바인딩(4개 모듈) | `zone_own_guards`, `zone_own_driver`, `zone_own_sweep`, `zone_pair_guards`의 `GATE_LOADED` 참조 |
| `progress_arm_on_moved_fix` | False | **True** | `install_p2f`(`MovedFixMonitor`) | 쌍 감시기의 모든 `not approach` 단계 |
| `carry_axial_lag` | False | **True** | gain 보정 후 axial lag 역산 | `zone_pair_executor.RoutedM2.door_schedule` |

- `κ = 0.94834`의 출처: PR #284 `proposed_carry_fwd_gain_fit.json`(sha256 `02884b59…6a2f56`). 봉인 파일 목록에 **적합 입력 파일을 추가**한다(v6e의 `carry_dr_fit.json`처럼). 값에 손을 대지 않고 파일 해시를 고정한다.
- 정책 값은 `PairPolicy`(동결 dataclass)의 필드로 두고, 다른 정책(`v5h`, `b-only`, `b-v6g`, …)의 필드는 전부 기본값이어야 한다.

### 결정이 필요한 점 (검토자에게)

1. **σ 배수 완화의 범위.** 등록 값 1/1은 파지 확인(confirmed grasp)이 있는 쌍의 **base motion**에만 적용한다. 접근·preclose·팔 스윕(든 팔 포함)은 2/2다. 탐색은 `SweepGuard.margin`을 프로세스 전체에서 풀었지만 등록은 이 범위를 좁혔다. 연쇄는 최초 접근을 생략하고 teacher lift에서 시작해도 L0 뒤 **lower → open → 재파지 → lift**의 팔 동작을 실제로 실행한다. 그러므로 2σ arm/preclose 가드로 강화한 것이 원본 명령을 바꾸지 않았는지는 **인수 재생에서 확인해야 한다**. 시작이 loaded라는 이유로 팔 스윕 동등성을 주장하지 않는다.
   **yaw gate와 p2f는 별도 범위다.** `PairCommandGuard.approach`가 거짓인 모든 단계(`not approach`)에 적용한다. 파지 receipt가 없는 align과 재파지도 포함된다. σ의 confirmed-grasp base-motion 조건과 혼동하지 않는다. 빈 몸 접근 `GuardedDriver`의 감시기는 기존대로다.
2. `GlobalPairSweepGuard`의 `K_SIGMA`(빔 상대 모드에서만 사용)와 `zone_pair_guards`의 정합 검사(`K_SIGMA` 309–340줄)는 **바꾸지 않는다.** 탐색도 이것들을 건드리지 않았다(클래스 상수 `K_SIGMA`는 그대로 2).
3. 진행 감시 규칙 p2f는 실제로는 **무장하지 않았다**(208건 중 0건). 등록하면 "든 쌍에는 사실상 정지 감지가 없다"는 성질을 코드에 굳히는 것이다. 이를 수용하거나(전제: fail-open 명시, 사전 등록에 적음), 정지 감지를 다른 방식으로 복원하기 전까지 등록을 미루는지는 검토자가 정한다. 이 계획은 수용 + 명시를 전제로 쓴다.
4. **`carry_axial_lag=True`는 2026-09-30 조정자 결정으로 포함했다.** gain 보정을 필수로 하며 같은 plant 복사본으로 축 방향 시간을 역산한다. lateral과 전역 `LAG_AXES`는 보존한다. 과거 탐색 물리 결과는 이 구현의 인수 통과가 아니다.

## 3. 봉인 파일 중 바뀌는 것

`experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json`의 85개 해시 중 다음이 바뀐다(정확한 목록은 재봉인 때 스크립트가 만든다):

| 파일 | 변경 |
|---|---|
| `harness/zone_pair_v6_policy.py` | `PairPolicy` 다섯 변경군, `b-v6h1` 정책, `REVISION_POLICIES['v6h']`, `EXECUTION_BUNDLE_ID` |
| `harness/owncam_carry_v6e.py` | `enable_provider`에서 gain 배수 적용, 프로필/입력 해시 기록 |
| `harness/zone_own_guards.py` | 든 상태 σ 배수 인수, 게이트 프로필 선택 |
| `harness/zone_pair_guards.py` | 든 쌍 감시기의 fix 시각 규칙(`progress_arm_on_moved_fix`), 게이트 조회 |
| `harness/zone_pair_geometry.py`, `harness/zone_own_sweep.py`, `harness/zone_own_driver.py`, `harness/zone_own_executor.py`, `harness/zone_pair_executor.py` | 정책 값을 가드에 전달(방식은 위 결정 1에 따름) |
| `harness/zone_study_integration.py` | 번들 ID, `RETIRED_BUNDLE_IDS`에 v81 추가 |
| `scripts/zone_pair_v6_contract.py` | `CURRENT_REVISION = 'v6h'`, 봉인 해시 재생성, v6e를 historical로 |
| 새 파일 | κ 적합 입력(PR #284 파일 사본과 sha256), `experiments/2026-09-30-pair-v6h-carry/prereg_v6h.json`, `build_prereg_v6h.py` |

봉인 밖에 남는 것: 탐색 패치 모듈(`zone_pair_door_relax.py`, `zone_pair_progress_relax.py`, `zone_pair_carry_gain_fix.py`)은 stage-probe 전용으로 남기되 `b-v6h` 이름 그대로 두고, 등록 정책과 겹치지 않게 한다(정책 id `b-v6h1`).

## 4. 재봉인 절차 (`docs/execution_versioning.md`, 선례: 커밋 `e510779d` v6e 등록)

1. 새 브랜치 `claude/pair-v6h-register`를 최신 `origin/main`에서 만든다(이 초안 브랜치를 그대로 봉인하지 않는다: 탐색 코드와 등록 코드를 분리).
2. 위 번호가 아직 비어 있는지 재확인, PR 본문에 사용한 ID를 적는다.
3. 위 플래그 구현. 모든 플래그는 끔이 기본이고 끔이면 출력이 바이트 동일.
4. `build_prereg_v6h.py`를 `build_prereg_v6e.py`를 본떠 만든다. 확증 코호트 계획(`PREREG_DRAFT.md`의 검토 반영본)을 `prereg_v6h.json`에 담고 `scripts/zone_pair_v6_contract.py`가 검사하는 봉인 해시를 기록한다.
5. `CURRENT_REVISION = 'v6h'`. v6e는 historical로 내리고 그 봉인 커밋(`e510779d` 계열)과의 일치를 감사한다. v81은 `RETIRED_BUNDLE_IDS`로.
6. 갱신: `configs/simulation_workflows.json`(2.16.0), `configs/zone_study_integration/llm_driver.json`, `docs/zone_study_integration.md`, `docs/current_status.md`, 그리고 v81/2.14.0을 언급하는 테스트(`test_owncam_bootstrap_v6b.py`, `test_zone_pair_v6d.py`, `test_zone_study_integration_pair.py`, `test_zone_study_llm_driver.py`, `test_zone_study_multiturn_properties.py`, `test_zone_study_referee.py`, `test_zone_study_source_pinning.py`, `test_zone_pair_registered_source.py`, `test_zone_pair_v6.py`).
7. `scripts.run_pair_stage_probes --prereg`에서 72건 admission과 실제 worker 설정 일치를 검사한다. `run_zone_pair_dev`의 과거 6건 경로로 실행하지 않는다. README의 준비 명령과 지적 2의 병합/pin TODO를 먼저 확인한다.
8. 로컬 검증 → 독립 검토 → PR(초안 → CI 통과 → 검토) → **병합·확증 코호트 실행은 별도 결정**.

## 5. 단위 시험 (새 파일 `tests/test_zone_pair_v6h.py` 안)

- 모든 기존 정책(`v5h`, `b-only`, `b-v6c`, `b-v6d`, `b-v6e*`, `b-v6g*`)의 새 필드가 기본값이다. `b-v6h1` = `b-v6g` + 다섯 변경군 외 차이가 없다.
- 끔 상태에서 든 PF·`SweepGuard.margin`·`GATE_LOADED`·`PairCommandGuard`의 출력이 main의 골든과 `1e-9` 안에서 같다(`test_flags_off_localizer_is_bit_identical_*` 선례).
- 켜짐 상태: `carry_fwd_gain`은 `gain[0][0]`만 곱하고 다른 항목·다른 PF·원본 dict를 건드리지 않으며 두 번 곱하지 않는다. σ 배수는 confirmed grasp의 base motion에서만 1/1, 접근·팔 스윕은 2/2(결정 1의 권장안). yaw 게이트와 p2f는 모든 not approach 단계(align·재파지 포함)에 적용한다. 진행 감시는 이동 시작 이후의 fix만 기준선을 세우고, 시각이 없거나 NaN이면 세우지 않는다. 빈 몸 `GuardedDriver`의 감시기는 등록 규칙 그대로다.
- 정책 조합: 등록 정책 목록·번들 ID·workflow 버전·봉인 해시(`test_zone_pair_registered_source.py`)가 서로 일치한다.

## 6. 인수 시험 (등록 뒤, 확증 코호트 전, 물리 필요)

**bit-for-bit 재생은 필수다.** #294의 같은 gain+p2f+k1g+axial ON 참조 **5건**으로 통일한다: **tS S01·S07, tR hR2_04, tX1 X01, tX1b X06; 모두 seed 911**. 정확한 목록은 `analysis/acceptance_replay_DRAFT.json`, 실행용 case 사본은 `acceptance_reference_DRAFT.json`이다. #294 원문에서 X01의 출처는 tX1이다(tX1b X01 raw는 없다). 요청의 tS/tR/tX1b 약칭으로 출처를 바꾸지 않는다. OFF sB/cA와 과거 PR #292의 6건 목록은 현재 기준이 아니다.

동일 배치·prior·환경·설정·SIM 타이밍으로 다시 실행해 `commands.json` **바이트 및 SHA-256 완전 동일**, leg 판정 동일, **연쇄 전체 접촉/하드 한계 판정 동일**을 모두 요구한다. 정렬/반올림/필드 제거/수치 허용오차로 바이트 비교를 대체하지 않는다. 강화된 2σ arm/preclose 가드의 영향도 이 재생에서 확인한다. 최종 분류기 반영은 `REVIEW_RESPONSE.md`의 지적 2 TODO를 따른다. 하나라도 다르면 원인 검토 전 확증을 시작하지 않는다. 물리 잠금과 실행은 조정자 소관이며 이 수정 작업에서는 실행하지 않았다.

## 7. 알려진 위험

- 탐색 통과가 "정지 감시가 없어서"일 수 있다(§2 결정 3). 등록 정책의 든 상태 안전성은 충돌 가드와 σ 게이트에만 의존한다.
- σ가 x에서 약 6배 보수적이라(gain 패치 뒤 z² 0.03) 게이트·여유는 실제 오차 대비 넉넉하다. 앞으로 σ를 다시 보정하면(보수성을 줄이면) 이 완화가 필요한지가 달라질 수 있다.
- 등록의 2σ arm/preclose 가드는 탐색보다 강하다. 연쇄에도 팔 동작이 있으므로 인수 재생 전 명령 동등성을 가정하지 않는다.
