# b-v6h 등록 구현 계획 (초안 — 아직 등록·봉인·실행하지 않았다) (2026-09-30, Claude)

Refs #216. 이 문서는 `experiments/2026-09-30-b-v6h-gain`의 탐색 결과를 **등록된 제어기 변경**으로 옮기는 방법을 정한다. 이번 갱신은 초안·분석만 바꾸며 등록 소스·봉인 파일을 수정하지 않았다. 사전 등록 초안은 같은 폴더의 `PREREG_DRAFT.md`. **다섯 플래그 조합의 독립 검토(Opus) 전에는 봉인하지 않는다.** 2026-09-30 조정자의 축 방향 지연 포함 결정을 반영했으며 등록 구현·물리 인수 시험은 별도 작업이다.

## 1. 번호 예약

| 항목 | 예약 값 | 근거 |
|---|---|---|
| 실행 번들 | `zone-pair-v83-carry-door-gain` (번호 **v83**) | 2026-09-30 `git fetch` 뒤 `origin/main`과 열린 PR 브랜치(현재 #284 하나)에서 사용 중인 최댓값은 **v81**(`harness/zone_pair_v6_policy.py`, `configs/simulation_workflows.json`, `configs/zone_study_integration/llm_driver.json`, `harness/zone_study_integration.py`를 좁게 grep). v82/2.15.0/revision v6f는 v6e README가 "쓰지 않는 번호"로 명시했으므로 건너뛴다 |
| workflow | `2.16.0` | 2.15.0은 위와 같은 이유로 건너뜀. main과 열린 PR에서 2.15.0·2.16.0 사용 없음 |
| revision | `v6h` (`REVISION_POLICIES['v6h'] = ('v5h', 'b-only', <등록 정책 id>)`) | `CURRENT_REVISION = 'v6e'` 다음 |
| 등록 정책 id | **`b-v6h1`** (권장) | `b-v6h`는 이미 stage-probe의 opt-in 이름이다(`harness/zone_pair_door_relax.POLICY_ID`, 과거 raw와 TB 뷰가 이 이름을 쓴다). 같은 이름을 진짜 정책으로 재사용하면 과거 기록의 뜻이 바뀐다. 이름은 검토자가 바꿀 수 있다 |

실제 봉인 직전에 위 grep을 다시 돌려 다른 PR이 v83/2.16.0/v6h를 가져가지 않았는지 확인한다(가져갔으면 다음 번호로).

## 2. 무엇이 제어기 코드가 되나

탐색에서 프로세스 내부 패치였던 **다섯 변경군**을 `PairPolicy` 플래그로 만든다(기존 정책의 기본값 = 끔/기존 값; `b-v6h1`은 아래 ON 값). σ의 xy/yaw는 두 필드지만 한 변경군으로 센다. 값은 탐색 코호트 그대로이며 이 값들이 확증 대상이다.

| 플래그(안) | 기본(끔) | b-v6h1 값 | 탐색 패치와의 대응 | 쓰이는 곳 |
|---|---|---|---|---|
| `carry_fwd_gain` | 1.0 | **0.9483378899463337** | `harness/zone_pair_carry_gain_fix.py`(`scaled_gain`, `enable_provider` 뒤에 한 번) | `harness/owncam_carry_v6e.enable_provider` 안, 든 PF의 `motion_loaded.gain[0][0]` 복사본 |
| `loaded_k_xy`, `loaded_k_yaw` | 2.0, 2.0 | **1.0, 1.0** | `relaxed_margin`(`SweepGuard.margin`의 σ 배수) | `harness/zone_own_guards.SweepGuard.margin` |
| `loaded_gate_yaw_deg` | `None`(3.0/2.5) | **(5.0, 4.0)** | `GATE_LOADED` 재바인딩(4개 모듈) | `zone_own_guards`, `zone_own_driver`, `zone_own_sweep`, `zone_pair_guards`의 `GATE_LOADED` 참조 |
| `progress_arm_on_moved_fix` | False | **True** | `install_p2f`(`MovedFixMonitor`) | `harness/zone_pair_guards.PairCommandGuard`(든 쌍의 감시기만) |
| `carry_axial_lag` | False | **True** | `harness/zone_pair_carry_axial_lag.py`(`--carry-axial-lag axial`, κ 적용 보정 사본으로 시간 역산) | `harness/owncam_carry_v6e.leg_duration`와 `PairTeam.door_schedule`의 축 방향 시간 계산; `carry_fwd_gain` 필수 |

- `κ = 0.94834`의 출처: PR #284 `proposed_carry_fwd_gain_fit.json`(sha256 `02884b59…6a2f56`). 봉인 파일 목록에 **적합 입력 파일을 추가**한다(v6e의 `carry_dr_fit.json`처럼). 값에 손을 대지 않고 파일 해시를 고정한다.
- 정책 값은 `PairPolicy`(동결 dataclass)의 필드로 두고, 다른 정책(`v5h`, `b-only`, `b-v6g`, …)의 필드는 전부 기본값이어야 한다.

### 결정 기록과 남은 검토

1. **σ 배수 완화의 범위.** 탐색 패치는 `SweepGuard.margin`을 **클래스 수준으로**(프로세스 전체) 바꿨다. 등록에서 같은 범위로 하면 접근 단계와 팔 스윕의 충돌 여유도 얇아진다. 그런데 **연쇄 코호트는 든 상태에서 시작하는 teacher 준비 상태이므로 접근·팔 스윕 여유의 완화는 한 번도 시험되지 않았다.** 권장: 든 상태(loaded)일 때만 완화한다(스윕 가드가 `loaded`를 알 때만 배수 적용; `PairSweepGuard.motion_clear(..., loaded=)` 경로). 든 상태 재생에서는 두 범위의 명령이 동일해야 하므로 인수 시험은 그대로 유효하다. 접근·팔 스윕은 등록 값(2/2)을 유지한다. 이 선택은 탐색 코호트 밖의 동작을 늘리지 않는 쪽이다. (`SweepGuard.margin(pose, lever)`는 지금 든 상태를 모르므로, 든 상태 여부를 생성 시점 인자로 넘기는 구현이 실제로 가능한지는 등록 브랜치에서 코드로 확인해야 한다. 어려우면 프로세스 전체 범위로 등록하되 위험으로 명시한다.)
2. `GlobalPairSweepGuard`의 `K_SIGMA`(빔 상대 모드에서만 사용)와 `zone_pair_guards`의 정합 검사(`K_SIGMA` 309–340줄)는 **바꾸지 않는다.** 탐색도 이것들을 건드리지 않았다(클래스 상수 `K_SIGMA`는 그대로 2).
3. 진행 감시 규칙 p2f는 실제로는 **무장하지 않았다**(208건 중 0건). 등록하면 "든 쌍에는 사실상 정지 감지가 없다"는 성질을 코드에 굳히는 것이다. 이를 수용하거나(전제: fail-open 명시, 사전 등록에 적음), 정지 감지를 다른 방식으로 복원하기 전까지 등록을 미루는지는 검토자가 정한다. 이 계획은 수용 + 명시를 전제로 쓴다.
4. **결정 완료(2026-09-30 조정자): `carry_axial_lag=True`를 b-v6h1에 포함한다.** 표의 다섯 번째 플래그이며 **`carry_fwd_gain=0.9483378899463337` 보정과 함께** 축 방향 시간 역산에 사용한다. 보정 없는 ON 조합은 거부한다(P1a는 L1 약 43 mm 부족). probe ON은 tS 12/12 + tR 10/10 + 추가 7/7 = **29/29 배치, 58/58 케이스**, 벽 접촉·하드 위반 0건이며 OFF는 sB 11/12, rB 7/10, 추가 3/7이다. 출처는 gain README "carry_axial_lag 물리 확인"과 `results/axial_lag_physical_check.{txt,json}`다. **29개는 확증 60개가 아니고**, 시드 의존성을 고려한 배치 분모 29/29의 Wilson 95 % 하한은 **0.8830≈88 %**다. 이 근거와 조정자 결정을 기록하되 **독립 검토는 미완료**이며 등록 구현·새 배치 완주를 검증한 것으로 쓰지 않는다. 현재 `LAG_AXES=('lateral',)`인 등록 소스를 이 작업에서 바꾸지 않는다.

## 3. 봉인 파일 중 바뀌는 것

`experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json`의 85개 해시 중 다음이 바뀐다(정확한 목록은 재봉인 때 스크립트가 만든다):

| 파일 | 변경 |
|---|---|
| `harness/zone_pair_v6_policy.py` | `PairPolicy` 다섯 변경군(σ 두 필드 포함), `b-v6h1` 정책, `carry_axial_lag`의 gain 보정 필수 조건, `REVISION_POLICIES['v6h']`, `EXECUTION_BUNDLE_ID` |
| `harness/owncam_carry_v6e.py` | `enable_provider`에서 gain 배수 적용, 축 방향 lag 시간 계산에 같은 κ를 한 번만 적용한 사본 사용, 프로필/입력 해시 기록; 옆 방향/기존 정책은 그대로 |
| `harness/zone_own_guards.py` | 든 상태 σ 배수 인수, 게이트 프로필 선택 |
| `harness/zone_pair_guards.py` | 든 쌍 감시기의 fix 시각 규칙(`progress_arm_on_moved_fix`), 게이트 조회 |
| `harness/zone_pair_geometry.py`, `harness/zone_own_sweep.py`, `harness/zone_own_driver.py`, `harness/zone_own_executor.py`, `harness/zone_pair_executor.py` | 정책 값을 가드에 전달(방식은 위 결정 1에 따름) |
| `harness/zone_study_integration.py` | 번들 ID, `RETIRED_BUNDLE_IDS`에 v81 추가 |
| `scripts/zone_pair_v6_contract.py` | `CURRENT_REVISION = 'v6h'`, 봉인 해시 재생성, v6e를 historical로 |
| 새 파일/봉인 입력 | κ 적합 입력(PR #284 파일 사본과 sha256), 축 방향이 사용하는 기존 lag 보정(`calibration_loop_v2.json`의 gain/τ/τ_stop)과 정책 ON 값, `prereg_v6h.json`, `build_prereg_v6h.py`; 이번 초안·배치·분류 정의·평가 스크립트 해시도 실행/평가 계획에 고정 |

봉인 밖에 남는 것: 탐색 패치 모듈(`zone_pair_door_relax.py`, `zone_pair_progress_relax.py`, `zone_pair_carry_gain_fix.py`, `zone_pair_carry_axial_lag.py`)은 stage-probe 전용으로 남기되 `b-v6h` 이름 그대로 두고, 등록 정책과 겹치지 않게 한다(정책 id `b-v6h1`). probe 패치 자체를 등록 제어기가 import해 프로세스 전체를 바꾸는 방식은 쓰지 않는다. `carry_axial_lag`는 해당 정책의 시간 계산 경로로 전달한다.

## 4. 재봉인 절차 (`docs/execution_versioning.md`, 선례: 커밋 `e510779d` v6e 등록)

1. 새 브랜치 `claude/pair-v6h-register`를 최신 `origin/main`에서 만든다(이 초안 브랜치를 그대로 봉인하지 않는다: 탐색 코드와 등록 코드를 분리).
2. 위 번호가 아직 비어 있는지 재확인, PR 본문에 사용한 ID를 적는다.
3. 위 플래그 구현. 모든 플래그는 끔이 기본이고 끔이면 출력이 바이트 동일.
4. `build_prereg_v6h.py`를 `build_prereg_v6e.py`를 본떠 만든다. 확증 코호트 계획(`PREREG_DRAFT.md`의 검토 반영본)을 `prereg_v6h.json`에 담고 `scripts/zone_pair_v6_contract.py`가 검사하는 봉인 해시를 기록한다. 현재 기본값은 60곳·≥48/60 관측 기준이며, 모집단 주장을 택하면 §3.4의 표본 수·정확 이항 규칙을 **봉인 전에** 별도로 확정한다. 분류 정의 11개(§5.1), 특히 OPEN 6·7을 먼저 해결한다.
5. `CURRENT_REVISION = 'v6h'`. v6e는 historical로 내리고 그 봉인 커밋(`e510779d` 계열)과의 일치를 감사한다. v81은 `RETIRED_BUNDLE_IDS`로.
6. 갱신: `configs/simulation_workflows.json`(2.16.0), `configs/zone_study_integration/llm_driver.json`, `docs/zone_study_integration.md`, `docs/current_status.md`, 그리고 v81/2.14.0을 언급하는 테스트(`test_owncam_bootstrap_v6b.py`, `test_zone_pair_v6d.py`, `test_zone_study_integration_pair.py`, `test_zone_study_llm_driver.py`, `test_zone_study_multiturn_properties.py`, `test_zone_study_referee.py`, `test_zone_study_source_pinning.py`, `test_zone_pair_registered_source.py`, `test_zone_pair_v6.py`).
7. 등록 정책을 stage-probe 러너의 정책 목록에 넣는다(`b-v6h1`, 준비 상태 chain 지원).
8. 로컬 검증 → 독립 검토 → PR(초안 → CI 통과 → 검토) → **병합·확증 코호트 실행은 별도 결정**.

## 5. 단위 시험 (새 파일 `tests/test_zone_pair_v6h.py` 안)

- 모든 기존 정책(`v5h`, `b-only`, `b-v6c`, `b-v6d`, `b-v6e*`, `b-v6g*`)의 새 필드가 기본값이다. `b-v6h1` = `b-v6g` + 위 **다섯 변경군** 외 차이가 없다.
- 끔 상태에서 든 PF·`SweepGuard.margin`·`GATE_LOADED`·`PairCommandGuard`·축 방향 leg 시간 출력이 고정 main 골든과 같다. 수치 항목은 기존 `1e-9` 검사도 하되, "bit identical" 검사는 배열/명령 파일의 **바이트 동일**을 요구한다(수치 허용오차를 바이트 동일의 대용으로 쓰지 않음).
- 켜짐 상태: `carry_fwd_gain`은 `gain[0][0]`만 곱하고 다른 항목·다른 PF·원본 dict를 건드리지 않으며 두 번 곱하지 않는다. σ 배수는 든 상태에서만 1/1, 접근·팔 스윕은 2/2(결정 1의 권장안). 게이트는 든 게이트만 5.0/4.0도. 진행 감시는 이동 시작 이후의 fix만 기준선을 세우고, 시각이 없거나 NaN이면 세우지 않는다. 빈 몸 `GuardedDriver`의 감시기는 등록 규칙 그대로다.
- **축 방향 지연:** `carry_axial_lag=True`인데 gain이 미보정이면 거부한다. ON의 시간은 `lag_duration(distance, abs(1.4004×κ×forward_command), τ, τ_stop)`와 일치하며 PF와 계획의 이득이 같다. κ 중복 적용·원본 보정 dict 변이·다른 정책으로의 전역 누출을 막는다. lateral 시간/τ/τ_stop와 OFF axial 시간은 기존 값 그대로다. 0.85 m L1, 다른 길이의 L0, 0 거리·잘못된 입력을 시험한다. probe의 `tests/test_b_v6h_gain.py` axial 검사 선례를 등록 경로로 옮기되 기존 probe 결과를 등록 시험 통과로 승계하지 않는다.
- 정책 조합: 등록 정책 목록·번들 ID·workflow 버전·봉인 해시(`test_zone_pair_registered_source.py`)가 서로 일치한다.

## 6. 인수 시험 (등록 뒤, 확증 코호트 전, 물리 필요)

**bit-for-bit 재생은 필수다.** 기준은 **gain+alag ON probe**여야 한다. OFF sB/cA 원본과 새 ON b-v6h1은 시간/명령이 달라지므로 그 둘을 바이트 동일 기준으로 쓰지 않는다. 최소 5건을 고정한다: tS S01·S07, tR hR2_04, tX1 X01, tX1b X06의 **시드 911**. 모두 axial lag ON인 기준으로 L0/L1 및 재파지 창을 포함한다. 실제 case id·소스 SHA·`commands.json` 원본 sha256은 `analysis/acceptance_replay_DRAFT.json`에 기록한다. S07은 OFF sB에서 실패했지만 ON tS에서는 통과한 배치다.

등록 구현을 동일한 배치·시드·사전분포·시트·환경/물리·설정·SIM 타이밍으로 실행해 **원본/새 `commands.json` 바이트와 전체 SHA-256이 둘 다 동일**한지, leg 검사 결과와 전체 하드/접촉 판정이 같은지 확인한다. JSON 정렬/반올림/필드 제거/수치 허용오차 비교로 대체하지 않는다. 어느 케이스든 명령이 다르면 독립 검토로 원인을 해결할 때까지 확증 코호트를 시작하지 않는다. 이 시험은 물리 잠금(`agent_lock`)을 잡아야 하며 **이번 작업에서는 실행하지 않았다**. 골든 목록/해시 저장은 인수 재생 통과가 아니다. 구현 검토자가 다른 기준 케이스를 요구하면 확증 봉인 전에 목록과 해시를 다시 확정한다.

## 7. 알려진 위험

- 탐색 통과가 "정지 감시가 없어서"일 수 있다(§2 결정 3). 등록 정책의 든 상태 안전성은 충돌 가드와 σ 게이트에만 의존한다.
- σ가 x에서 약 6배 보수적이라(gain 패치 뒤 z² 0.03) 게이트·여유는 실제 오차 대비 넉넉하다. 앞으로 σ를 다시 보정하면(보수성을 줄이면) 이 완화가 필요한지가 달라질 수 있다.
- 접근·팔 스윕에 대한 완화 영향은 (권장안대로) 범위에서 뺀 만큼만 안전하다. 프로세스 전체로 등록하면 그 부분은 시험된 적이 없다.
- **p2f 0/208: loaded 상태의 믿을 만한 정지 감지는 없다.** D1(손목 영상 밝기 차이) 검출기는 PR #291의 별도 탐색 제안이며 b-v6h1에 포함하지 않는다. b-v6h1 성공을 안전한 끼임/정지 대응(safe stall handling)으로 보고하지 않는다. 일반 setdown 관문·teacher 준비 기록 경계의 OPEN 정의와 모형의 옆 방향 전이 위험도 봉인 전에 검토한다.

## 분류 입력의 후속 검토 반영

분류기 v2는 봉인된 정확 60+12 목록, 계획/배치/사전분포/소스/정책/번들 해시, HOST_ERROR 연결 및 전체 trace/접촉 추적 범위 증거를 요구한다([입력 계약](analysis/SEALED_INPUT.md)). 기존 러너의 접촉 step 수는 전체 추적 범위가 아니므로 새 기록 어댑터와 독립 검토가 필요하다. 이번 작업은 제어기·러너·실제 봉인 파일을 수정하거나 실행하지 않았다. L0 handover/재파지, 의도된 L1 첫 wait_lower 종료, teacher 포함 전체 안전 창 및 941 주 σ 가중 정의는 PREREG_DRAFT.md §4–5.1과 같다.

#299 독립 검토의 R1/R2도 입력 계약에 반영했다. 주기 trace·비동기 끝점·저장 GT의 안전 최대값을 합치며, HOST_ERROR 대체는 성공률/σ의 단일 선택에만 적용한다. 원 시도·재시도·보조 시드의 저장 안전 증거와 파일 해시를 모두 보존한다. 이미 관측한 하드 위반은 A/B 완전성과 무관하게 코호트 안전 거부로 남는다. HOST_ERROR 안전 면제는 기존 계획에 없었으며 PREREG_DRAFT.md §4·§5.1의 보수적 해석을 명시한 것이다. 실제 봉인 전에 새 `evaluation_protocol`의 안전 범위/시도 규칙도 고정해야 한다.
