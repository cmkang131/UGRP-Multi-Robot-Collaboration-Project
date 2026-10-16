# 자기 카메라 관측 기억 memory_v3 — 개발 후보

2026-09-27, issue #217. 기준 worktree HEAD `367b40da`의 v2와 기록은 보존한다.
이 문서는 단위 시나리오로 확인한 구현 설계다. 코호트·물리 성공·속도 개선을 뜻하지 않는다.
PR #234 적대 리뷰 이후 변경은 [1차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review-fixes/README.md), [2차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review2-fixes/README.md), [3차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review3-fixes/README.md), [4차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review4-fixes/README.md), [5차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review5-fixes/README.md), [6차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review6-fixes/README.md)에 분리했다. 아래는 6차 초기화 예산 분리와 coordinator의 안전 조건 통일 결정을 반영한 계약이다.

## 비교 조건 — 5차 수정

비교 질문은 **기억 기반 재관측 결정의 효과**다. `run_m1_owncam_memory_v3.py`의 `off`는 이제 `M1OwnCamDeliveryOffV3`, ON은 `memory_v3`이다. OFF는 ON과 같은 제어기를 상속하고 `memory_look_enabled=False`만 선택한다. 자기 pose source/일관성, 트랙과 회피, 목표 선택, 조작 스킬, 빈 슬롯 검증은 양쪽에 남는다. OFF에도 추적 기억이 있으므로 이 비교를 **전체 기억 유무 효과**로 해석하지 않는다. 6차 초기화 예산 분리 역시 양쪽에 같은 구현과 한도를 적용한다.

| 조건 | 재관측 결정 | 안전/조작 |
|---|---|---|
| `off` | 고정 travel/no-tag/door trigger, full sweep, coverage로 탐색 관측점·pan 생략 안 함 | 공통 v3 |
| `memory_v3` | 기억의 예상 시야·σ 기반 trigger, 계획 short/full·조기 종료, coverage 기반 탐색 관측점·pan 선택 | 공통 v3 |
| `off_legacy`, `memory_v2` | 동결된 과거 구현 재현 | 과거 안전 조건; matched 효과 추정에서 제외 |

두 비교 조건은 `owncam_safety_v3`의 같은 메서드로 σ, fix, 도착, 충돌 sweep/명령, 재시도, 정체, 초기화 복구를 검사한다. 출처 해시·안전 계약·조건 역할·ON/OFF 플래그를 runner 기록에 남긴다. 기존 REGISTERED 파일의 `off` 의미를 조용히 바꾸지 않도록 `safety_contract=ugrp.owncam_safety.v3`가 없는 비교 실행은 거부한다. 과거 OFF/v2 소스와 기록은 바이트 그대로 유지한다. [prereg 초안](../../experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json)은 계속 DRAFT이며 실행 허가는 없다.

### 공통 fix·정체·초기화 기준

- 주행 상한은 unloaded xy 0.05 m / loaded 0.07 m, yaw 3°를 유지한다. short/full 모두 fix 인정은 unloaded xy 0.04 m / loaded 0.05 m, yaw 2° 이하로 좁혀 carry 복귀의 예측 σ 증가에 여유를 둔다. 도착 look은 yaw 1.3° 이하를 요구하고 복귀 뒤 기존 도착 상한(xy 0.05/0.06 m, yaw 2°)을 다시 검사한다. σ를 잘라 줄이거나 이동량으로 차단을 우회하지 않는다.
- fix 실패는 2회에 `pose_unverified`. 이와 독립적으로 목표 진전 없는 look은 최대 4회 또는 60 SIM s이며 다음 look/시간 한도에서 `look_stagnation`으로 끝난다. 정상 fix는 정체 횟수를 지우지 않는다. 주행 상태에서 발행된 비영 이동 명령과 자기 추정의 목표 거리 0.10 m 이상 감소가 함께 있어야 정체 예산을 초기화한다. hold/stop은 이동 명령 증거를 지운다. 이는 추정 진전이며 실제 이동 성공이 아니다.
- 초기 sweep이 자기 pose 불확실성/충돌 검사에서 거부되면 팔·pan·차체를 움직이지 않고 hold와 capture만 수행한다. 정지 재촬영 예산은 **누적 8 SIM s**(`INIT_RECOVERY_S`), 요청 총 20회, 간격 0.2 SIM s이다. 첫 거부부터 시간을 차감하되 충돌 검사를 통과한 sweep 생성 시 남은 시간을 보존하고 정지 deadline을 비활성화한다. sweep 완료 또는 명령 재검사 거부 후에는 **남은 시간만** 재개한다. 재거부·새 프레임·sweep 생성으로 시간/촬영 횟수를 새로 지급하지 않는다. 새 시각의 신선한 프레임만 재시도하며 같은 시각 capture를 반복하지 않는다. 계획 단계의 거부는 실제 look 횟수에 넣지 않으며, 시작 후 중단된 sweep은 실제 look 횟수에 남는다.
- 재개된 sweep은 정지 재촬영 8초와 독립적으로 실행하되, **전체 초기화 30 SIM s**(`INIT_TIMEOUT_S`) 안에서만 진행한다. 최초 초기화 `decide` 시각부터 정지·sweep·복귀·판단 시간을 모두 포함하며 pause/reset하지 않는다. 명령이 진전하지 않는 sweep에도 적용한다. 기본 6-pan의 0.1초 명령 처리 회귀에서 sweep 하나는 9.0 SIM s를 사용한다. 기존 30초 상한을 유지하는 설계 근거는 정지 8초 + 이런 sweep 두 번 18초 + 전환/판단 여유 4초다. 이는 유한한 개발 예산이며 실제 물리 소요 시간의 보장이 아니다. 기존 실제 look 최대 3회와도 함께 적용하고, 모든 시도를 완주시키기 위해 전체 상한을 늘리지 않는다. 각 한도 소진은 `NOT_INITIALIZED`이며 초기화 밖의 충돌 거부는 기존 종료/handoff를 유지한다.

6차 반례는 양 조건에 같은 합성 자기 추정을 넣어 1.8 s 거부 → 2.0 s σxy=0.09 m에서 6-pan 시작 → 2.8 s부터 σxy=0.02 m → 11.0 s sweep 완료 → 11.1 s `search_leg`를 확인한다. 수정 전에는 9.8 s의 정지 deadline이 sweep을 중단했다. 실제 충돌 검사·상태기계·발행 명령 처리를 사용하는 오프라인 회귀이며, 자기 카메라의 실제 수렴률이나 물리 성공·기억 효과를 측정한 결과는 아니다.

이 문턱들은 dev 후보이며 실제 carry 복귀·슬롯 관측·성공률은 새 dev에서 검증한 뒤 양쪽 동일하게 동결한다.

## 변경

| 파일 | 역할 |
|---|---|
| `harness/owncam_pose_guard_v3.py` | 명령 누적 이동·자기 추정 궤적, likelihood/innovation 일관성, 보고 공분산 보강 |
| `harness/owncam_memory_v3.py` | 존재 확률 트랙, far 회피, 시야 기반 부재·빈 바닥 증거, 별도 동료 주장 |
| `harness/owncam_visibility_v3.py` | 연속 yaw 구간의 가시성 포괄 영역, 자기 팔 가림의 보수적 거부 |
| `harness/owncam_drive_mem_v3.py` | 주행 중 새 회피 영역 반영, 도착 재관측과 유한 재시도 |
| `harness/owncam_safety_v3.py` | ON/OFF 공통 σ·fix·충돌·재시도·정체·초기화 복구 |
| `harness/m1_owncam_memory_v3.py` | 파지·배치 재확인, 탐색 사각지대의 두 번째 관측점 순회 |
| `harness/owncam_sweep_collision.py` | EXECFIX에서도 import 가능한 정적 몸체·전환·pan·복귀 충돌 검사 |
| `harness/owncam_search_projection_v3.py` | 지도 차체 여유와 연결성을 만족하는 사각지대 관측점 투영 |
| `harness/owncam_slot_inspection_v3.py` | 하중 유지 슬롯 관측점·복귀·유한 실패 및 실행기 handoff |
| `scripts/run_m1_owncam_memory_v3.py` | off / memory_v2 / memory_v3 선택, DRAFT 실행 거부, 입력 소스 해시 기록 |

기존 기하·상자 KF·대응·기본 스킬을 상속/호출하고 v2 파일은 변경하지 않는다.
표준 workflow는 `zone-m1-owncam-memory-v3-run`이다. 새 의존성은 없다.

- **고정 신선도:** 잠정 개발값은 8 SIM s와 0.12 m다. 직선 변위뿐 아니라 명령 적분 거리와 자기 추정 누적 경로 중 큰 값도 제한한다. 왕복으로 원위치에 돌아와도 신선해지지 않는다. 이 거리는 실제 이동의 측정값이 아니다.
- **현재 불확실도 차단:** 최근 일관성·look fix와 이동량 기반 재관측 억제와 별도로 현재 σ를 검사한다. 주행은 loaded xy ≤0.07 m / unloaded xy ≤0.05 m 및 yaw ≤3°, 도착은 loaded xy ≤0.06 m / unloaded xy ≤0.05 m 및 yaw ≤2°를 요구한다. σ는 유한한 비음수여야 한다. 초과하면 정지·재관측하고 기존 유한 재시도/충돌 거부를 따른다. 도착에는 새 look의 신선도도 계속 필요하다.
- **과신:** PF 재설정 전 특징당 log-likelihood와 예측→관측 갱신의 정규화 혁신을 검사한다. 일관된 새 프레임 2개가 필요하고, 불일치/만료 때 xy 0.12 m·yaw 8°의 불확실성 하한을 공분산에 반영한다. 이미 보강된 보고서를 다시 읽어도 중복 팽창하지 않는다. 짧은 look은 현재 dwell의 두 근거가 있어야 조기 종료한다. PF 입자 자체는 수정하지 않는다. 정규화 혁신의 χ² 문턱은 진단 근사이며 보정된 확률 보장이 아니다.
- **far 회피:** near 확정 전부터 `slot_blocking`인 관측 트랙을 반경 `0.03 + 2σ`의 회피 사각형으로 반영한다. v2의 5 cm 추가 여유 상한을 쓰지 않는다. 반복 far 프레임으로 거리 불확실성이 부당하게 작아지지 않게 하한을 둔다. far 목표 관측점도 이 영역과 로봇 여유 밖에 둔다.
- **존재:** `p ← p exp(−λΔt)` 후 검출은 `p(1−P_M)/(p(1−P_M)+(1−p)P_F)`, 보였어야 할 미검출은 `pP_M/(pP_M+(1−p)(1−P_F))`로 갱신한다. λ=0.005/s, near `(P_M,P_F)=(0.25,0.10)`, far `(0.60,0.25)`, absent ≤0.10, confirmed ≥0.95가 개발 초기값이다. 0.4초보다 가까운 프레임은 독립 증거로 누적하지 않는다. confirmed에는 near 2회·자세 일관성·σ≤0.05 m도 필요하다.
- **부재:** 위치·상자 크기뿐 아니라 yaw ±2σ 전체가 신뢰 거리·FOV 안에 있어야 한다. 회전의 최대 현 길이로 연속 구간을 감싸며, 끝점 몇 개만 검사하지 않는다. 정적 벽·검출 전경 상자와 가능한 모든 시선의 사각 포괄 영역이 겹치면 miss를 보류한다. 자기 팔은 열린 SEARCH 자세의 제한된 안전 시선만 허용하고 나머지 자세·집게 아래 방향은 보류한다. 아래 수정 기록의 기하 근거와 한계를 따른다. 이 거부에서는 시간 생존 사전분포만 적용하고 부재 확률을 추가 갱신하지 않는다.
- **행동 직전:** 도착은 새 look, 파지는 새 자기 목표 관측+자세 확인을 요구한다. 배치는 **새 빈 슬롯 관측과 해제 준비 확인을 모두** 요구한다. 하중 LOOK에서 바닥이 안 보이면 집게를 닫은 채 슬롯 서쪽 0.95/1.05 m 관측점으로 이동해 SEARCH 자세로 확인한다. 바닥은 최대 60 SIM s의 별도 근거이며 복귀 후 현재 점유·나이·새 pose fix·화물 RGB·해제 자세를 재검사한다. 이 TTL과 관측점은 dev 전용 후보로, 물리 왕복/가시성은 새 dev에서 검증한다. 최대 두 관측점 또는 120 SIM s 뒤에도 unknown이면 `SLOT_UNVERIFIED`와 `requires_upper_level_decision`을 실행기에 반환한다. occupied도 차단한다. 성공 판정은 기존 해제 후 자기 RGB 확인을 그대로 거친다. 주행 재관측은 xy와 yaw를 모두 확인하고 실패 2회 뒤 종료한다.
- **점유 유지:** 트랙의 시간 감쇠 존재 확률과 별도로, 관측만으로 갱신하는 확률 및 슬롯 차단 상태를 기록한다. 주행 keep-out과 슬롯 게이트는 `blocking_tracks` 하나의 기준을 쓰며, 시간만 지나거나 placed 상태가 되어서는 차단이 풀리지 않는다. 자기 held/명시적 제외 대상만 제외한다. 전체 시야가 보장된 miss로 관측 확률 ≤0.10이 된 경우에만 해제하며 새 검출은 다시 차단한다. 상자 uncertainty와 겹치는 바닥도 free로 갱신하지 않는다.
- **바닥과 재촬영:** free 셀도 셀 전체·xy·yaw ±2σ·벽/전경·자기 팔 기준을 track miss와 공유한다. 하중 SEARCH는 현재 RGB 화물 마스크의 상단과 기존 상단 시야 제한을 함께 적용한다. 같은 SIM 시각 새 frame ID는 정상 처리하지만 PF·일관성·free 격자에 독립 증거로 중복 누적하지 않는다. 이전 시각/재사용 frame ID는 거부한다.
- **탐색:** 기존 관측점에서 못 찾으면 서쪽 0.45 m 후퇴를 목표로 두 번째 순회를 한 번만 한다. 목표 주변 0.45 m 안에서 최소 0.10 m 후퇴하면서 차체 여유·장애물·현재 추정과의 연결성을 만족하는 가장 가까운 셀로 투영한다. 같은 planner로 경로를 확인하며 없으면 `SEARCH_BLIND_SPOT_UNREACHABLE`로 종료한다. 기본 지도에서 투영한 점의 경로와 기존 사각 영역의 기하 가시성을 검사했다. 실제 검출·도달은 미검증이다.
- **둘러보기 충돌:** `499e4fd6`의 보정된 몸체 구 모델을 공용 함수로 분리했다. 자기 pose 불확실성과 정적 벽/문기둥 높이를 사용해 자세 전환·pan의 전체 경로·복귀를 검사한다. 발행 PWM 보간의 관절 조합을 구의 이동 상한으로 감싸고 애매하면 거부한다. 불확실성은 상한으로 잘라 줄이지 않는다. 안전한 pan이 없거나 자기 pose가 없으면 초기화에서만 위의 유한 정지·재촬영을 수행하고, 그 밖에서는 임의 home pan 대신 명시적으로 종료한다. 명령 발행 직전에도 재검사한다. v3 gate 호출자도 sweep 생성 여부를 먼저 확인하여 거부 시 메타데이터 접근 없이 `LOOK_COLLISION_UNVERIFIED`(슬롯 검사 중에는 기존 handoff)로 종료한다.
- **왕복 화물·종료:** outbound/return의 매 새 RGB에서 기존 `box.decide`의 external_navigation carry 검사를 실행한다. look/팔 전환 중에도 낙하/가림/검사 요구가 나오면 중단한다. 오래된 프레임으로는 이동하지 않는다. 외부 SIM 한도가 먼저 끝나도 v3 runner가 pending handoff를 `result.json`에 보존하며 원래 SIM_LIMIT 판정은 유지한다.
- **들은 주장:** 자유 한국어 문자열과 정형 내용에 똑같이 `(sender, observed_at)` 참조를 붙여 `peer_claims`에 보관한다. 관측 시각 기준 TTL 12 s, 같은 참조 재수신은 나이나 확신을 늘리지 않는다. 자기 KF·존재 확률·조작 허가에는 합치지 않는다. 메시지 생성/전송·평가 파서는 이번 구현에 없다.

## 검증과 다음 단계

`tests/test_owncam_memory_v3.py`는 s161/s166의 **실패 기제**와 과신·miss·사각지대를 합성 입력으로 재현한다. 실제 seed 궤적 재생이 아니다. CI의 `TEST_PATTERNS`에 등록했다. [검증 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/README.md)을 따른다.

현재 제어기 연결은 **interim tag provider**다. PR #227 어댑터는 아직 연결하지 않았다. 보수적 회피·가림 보류·게이트 거부에 따른 성공률은 새 dev에서 확인해야 한다. dev s151의 초기 RGB 재생과 v2 **test split** s162/s164/s165 fixture는 이미 v3 개발·회귀에 사용한 노출 자료이며 v3 test/성능 표본이 아니다. [DRAFT](../../experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json)에 출처·용도를 명시했다. 미래 test는 새 미개봉 seed만 사용하고 coordinator가 개봉 전에 조건과 소스를 동결한다.

## 참고 자료

- 몸체 모델: `499e4fd6445614a8b647eaea11f7bb9c77e5e2bd:harness/zone_own_guards.py` (Kiro 실행기). 정적 보정 원본과 출처 해시는 [3차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review3-fixes/README.md)에 보존했다. 새 물리 측정값이 아니다.

- PR #230, [로봇 기억 문헌 조사](https://github.com/kcm0127-dotcom/ugrp/blob/3174c2f8882bf3dfbfb211be64f3f02023d762d8/docs/design/2026-09-26-memory-literature.md), 특히 4.2·4.4·4.5절. 해당 원격 참조를 `git show`로 읽었다. coordinator의 #217 결정에 따라 양 조건 모두 발신자·관측 시각 참조만 사용한다.
- Rosen·Mason·Leonard, *Towards Lifelong Feature-Based Mapping in Semi-Static Environments*, ICRA 2016, [DOI](https://doi.org/10.1109/ICRA.2016.7487237). 지수 생존 Bernoulli 모형은 PR #230의 유도를 독립 구현했으며 LGPL 코드는 복사하지 않았다.
- Wong·Lozano-Pérez·Kaelbling, *Not seeing is also believing*, ICRA 2014, [MIT](http://hdl.handle.net/1721.1/100724); Liu 외, *DynaMem*, [arXiv](https://arxiv.org/abs/2411.04999). PR #230에서 정리한 ‘부재 증거와 증거 부재 구분’ 설계를 참고했다.
- [v2 결과·실패 분석](../../experiments/2026-09-26-zone-owncam-memory/README.md), `harness/owncam_memory_kf.py`의 기존 MIT KF/대응 구현, `harness/owncam_localizer.py`의 기존 PF 진단값. 새 성능 근거로 합산하지 않는다.
