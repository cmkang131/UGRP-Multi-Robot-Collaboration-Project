# 자기 카메라 관측 기억 memory_v3 — 개발 후보

2026-09-27, issue #217. 기준 worktree HEAD `367b40da`의 v2와 기록은 보존한다.
이 문서는 단위 시나리오로 확인한 구현 설계다. 코호트·물리 성공·속도 개선을 뜻하지 않는다.
PR #234 적대 리뷰 이후 변경은 [1차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review-fixes/README.md), [2차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review2-fixes/README.md)에 분리했다. [3차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review3-fixes/README.md)에 추가 변경을 남겼다. 아래는 3차 수정까지 반영한 계약이다.

## 변경

| 파일 | 역할 |
|---|---|
| `harness/owncam_pose_guard_v3.py` | 명령 누적 이동·자기 추정 궤적, likelihood/innovation 일관성, 보고 공분산 보강 |
| `harness/owncam_memory_v3.py` | 존재 확률 트랙, far 회피, 시야 기반 부재·빈 바닥 증거, 별도 동료 주장 |
| `harness/owncam_visibility_v3.py` | 연속 yaw 구간의 가시성 포괄 영역, 자기 팔 가림의 보수적 거부 |
| `harness/owncam_drive_mem_v3.py` | 주행 중 새 회피 영역 반영, 도착 재관측과 유한 재시도 |
| `harness/m1_owncam_memory_v3.py` | 파지·배치 재확인, 탐색 사각지대의 두 번째 관측점 순회 |
| `harness/owncam_sweep_collision.py` | EXECFIX에서도 import 가능한 정적 몸체·전환·pan·복귀 충돌 검사 |
| `harness/owncam_search_projection_v3.py` | 지도 차체 여유와 연결성을 만족하는 사각지대 관측점 투영 |
| `harness/owncam_slot_inspection_v3.py` | 하중 유지 슬롯 관측점·복귀·유한 실패 및 실행기 handoff |
| `scripts/run_m1_owncam_memory_v3.py` | off / memory_v2 / memory_v3 선택, DRAFT 실행 거부, 입력 소스 해시 기록 |

기존 기하·상자 KF·대응·기본 스킬을 상속/호출하고 v2 파일은 변경하지 않는다.
표준 workflow는 `zone-m1-owncam-memory-v3-run`이다. 새 의존성은 없다.

- **고정 신선도:** 잠정 개발값은 8 SIM s와 0.12 m다. 직선 변위뿐 아니라 명령 적분 거리와 자기 추정 누적 경로 중 큰 값도 제한한다. 왕복으로 원위치에 돌아와도 신선해지지 않는다. 이 거리는 실제 이동의 측정값이 아니다.
- **과신:** PF 재설정 전 특징당 log-likelihood와 예측→관측 갱신의 정규화 혁신을 검사한다. 일관된 새 프레임 2개가 필요하고, 불일치/만료 때 xy 0.12 m·yaw 8°의 불확실성 하한을 공분산에 반영한다. 이미 보강된 보고서를 다시 읽어도 중복 팽창하지 않는다. 짧은 look은 현재 dwell의 두 근거가 있어야 조기 종료한다. PF 입자 자체는 수정하지 않는다. 정규화 혁신의 χ² 문턱은 진단 근사이며 보정된 확률 보장이 아니다.
- **far 회피:** near 확정 전부터 `slot_blocking`인 관측 트랙을 반경 `0.03 + 2σ`의 회피 사각형으로 반영한다. v2의 5 cm 추가 여유 상한을 쓰지 않는다. 반복 far 프레임으로 거리 불확실성이 부당하게 작아지지 않게 하한을 둔다. far 목표 관측점도 이 영역과 로봇 여유 밖에 둔다.
- **존재:** `p ← p exp(−λΔt)` 후 검출은 `p(1−P_M)/(p(1−P_M)+(1−p)P_F)`, 보였어야 할 미검출은 `pP_M/(pP_M+(1−p)(1−P_F))`로 갱신한다. λ=0.005/s, near `(P_M,P_F)=(0.25,0.10)`, far `(0.60,0.25)`, absent ≤0.10, confirmed ≥0.95가 개발 초기값이다. 0.4초보다 가까운 프레임은 독립 증거로 누적하지 않는다. confirmed에는 near 2회·자세 일관성·σ≤0.05 m도 필요하다.
- **부재:** 위치·상자 크기뿐 아니라 yaw ±2σ 전체가 신뢰 거리·FOV 안에 있어야 한다. 회전의 최대 현 길이로 연속 구간을 감싸며, 끝점 몇 개만 검사하지 않는다. 정적 벽·검출 전경 상자와 가능한 모든 시선의 사각 포괄 영역이 겹치면 miss를 보류한다. 자기 팔은 열린 SEARCH 자세의 제한된 안전 시선만 허용하고 나머지 자세·집게 아래 방향은 보류한다. 아래 수정 기록의 기하 근거와 한계를 따른다. 이 거부에서는 시간 생존 사전분포만 적용하고 부재 확률을 추가 갱신하지 않는다.
- **행동 직전:** 도착은 새 look, 파지는 새 자기 목표 관측+자세 확인을 요구한다. 배치는 **새 빈 슬롯 관측과 해제 준비 확인을 모두** 요구한다. 하중 LOOK에서 바닥이 안 보이면 집게를 닫은 채 슬롯 서쪽 0.95/1.05 m 관측점으로 이동해 SEARCH 자세로 확인한다. 바닥은 최대 60 SIM s의 별도 근거이며 복귀 후 현재 점유·나이·새 pose fix·화물 RGB·해제 자세를 재검사한다. 이 TTL과 관측점은 dev 전용 후보로, 물리 왕복/가시성은 새 dev에서 검증한다. 최대 두 관측점 또는 120 SIM s 뒤에도 unknown이면 `SLOT_UNVERIFIED`와 `requires_upper_level_decision`을 실행기에 반환한다. occupied도 차단한다. 성공 판정은 기존 해제 후 자기 RGB 확인을 그대로 거친다. 주행 재관측은 xy와 yaw를 모두 확인하고 실패 2회 뒤 종료한다.
- **점유 유지:** 트랙의 시간 감쇠 존재 확률과 별도로, 관측만으로 갱신하는 확률 및 슬롯 차단 상태를 기록한다. 주행 keep-out과 슬롯 게이트는 `blocking_tracks` 하나의 기준을 쓰며, 시간만 지나거나 placed 상태가 되어서는 차단이 풀리지 않는다. 자기 held/명시적 제외 대상만 제외한다. 전체 시야가 보장된 miss로 관측 확률 ≤0.10이 된 경우에만 해제하며 새 검출은 다시 차단한다. 상자 uncertainty와 겹치는 바닥도 free로 갱신하지 않는다.
- **바닥과 재촬영:** free 셀도 셀 전체·xy·yaw ±2σ·벽/전경·자기 팔 기준을 track miss와 공유한다. 하중 SEARCH는 현재 RGB 화물 마스크의 상단과 기존 상단 시야 제한을 함께 적용한다. 같은 SIM 시각 새 frame ID는 정상 처리하지만 PF·일관성·free 격자에 독립 증거로 중복 누적하지 않는다. 이전 시각/재사용 frame ID는 거부한다.
- **탐색:** 기존 관측점에서 못 찾으면 서쪽 0.45 m 후퇴를 목표로 두 번째 순회를 한 번만 한다. 목표 주변 0.45 m 안에서 최소 0.10 m 후퇴하면서 차체 여유·장애물·현재 추정과의 연결성을 만족하는 가장 가까운 셀로 투영한다. 같은 planner로 경로를 확인하며 없으면 `SEARCH_BLIND_SPOT_UNREACHABLE`로 종료한다. 기본 지도에서 투영한 점의 경로와 기존 사각 영역의 기하 가시성을 검사했다. 실제 검출·도달은 미검증이다.
- **둘러보기 충돌:** `499e4fd6`의 보정된 몸체 구 모델을 공용 함수로 분리했다. 자기 pose 불확실성과 정적 벽/문기둥 높이를 사용해 자세 전환·pan의 전체 경로·복귀를 검사한다. 발행 PWM 보간의 관절 조합을 구의 이동 상한으로 감싸고 애매하면 거부한다. 불확실성은 상한으로 잘라 줄이지 않는다. 안전한 pan이 없거나 자기 pose가 없으면 임의 home pan 대신 명시적으로 종료한다. 명령 발행 직전에도 재검사한다.
- **왕복 화물·종료:** outbound/return의 매 새 RGB에서 기존 `box.decide`의 external_navigation carry 검사를 실행한다. look/팔 전환 중에도 낙하/가림/검사 요구가 나오면 중단한다. 오래된 프레임으로는 이동하지 않는다. 외부 SIM 한도가 먼저 끝나도 v3 runner가 pending handoff를 `result.json`에 보존하며 원래 SIM_LIMIT 판정은 유지한다.
- **들은 주장:** 자유 한국어 문자열과 정형 내용에 똑같이 `(sender, observed_at)` 참조를 붙여 `peer_claims`에 보관한다. 관측 시각 기준 TTL 12 s, 같은 참조 재수신은 나이나 확신을 늘리지 않는다. 자기 KF·존재 확률·조작 허가에는 합치지 않는다. 메시지 생성/전송·평가 파서는 이번 구현에 없다.

## 검증과 다음 단계

`tests/test_owncam_memory_v3.py`는 s161/s166의 **실패 기제**와 과신·miss·사각지대를 합성 입력으로 재현한다. 실제 seed 궤적 재생이 아니다. CI의 `TEST_PATTERNS`에 등록했다. [검증 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/README.md)을 따른다.

현재 제어기 연결은 **interim tag provider**다. PR #227 어댑터는 아직 연결하지 않았다. 보수적 회피·가림 보류·게이트 거부에 따른 성공률은 새 dev에서 확인해야 한다. v2 **test split** s162/s164/s165 fixture는 이미 v3 개발·회귀에 사용한 노출 자료이며 v3 test/성능 표본이 아니다. [DRAFT](../../experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json)에 출처·용도를 명시했다. 미래 test는 새 미개봉 seed만 사용하고 coordinator가 개봉 전에 조건과 소스를 동결한다.

## 참고 자료

- 몸체 모델: `499e4fd6445614a8b647eaea11f7bb9c77e5e2bd:harness/zone_own_guards.py` (Kiro 실행기). 정적 보정 원본과 출처 해시는 [3차 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/review3-fixes/README.md)에 보존했다. 새 물리 측정값이 아니다.

- PR #230, [로봇 기억 문헌 조사](https://github.com/kcm0127-dotcom/ugrp/blob/3174c2f8882bf3dfbfb211be64f3f02023d762d8/docs/design/2026-09-26-memory-literature.md), 특히 4.2·4.4·4.5절. 해당 원격 참조를 `git show`로 읽었다. coordinator의 #217 결정에 따라 양 조건 모두 발신자·관측 시각 참조만 사용한다.
- Rosen·Mason·Leonard, *Towards Lifelong Feature-Based Mapping in Semi-Static Environments*, ICRA 2016, [DOI](https://doi.org/10.1109/ICRA.2016.7487237). 지수 생존 Bernoulli 모형은 PR #230의 유도를 독립 구현했으며 LGPL 코드는 복사하지 않았다.
- Wong·Lozano-Pérez·Kaelbling, *Not seeing is also believing*, ICRA 2014, [MIT](http://hdl.handle.net/1721.1/100724); Liu 외, *DynaMem*, [arXiv](https://arxiv.org/abs/2411.04999). PR #230에서 정리한 ‘부재 증거와 증거 부재 구분’ 설계를 참고했다.
- [v2 결과·실패 분석](../../experiments/2026-09-26-zone-owncam-memory/README.md), `harness/owncam_memory_kf.py`의 기존 MIT KF/대응 구현, `harness/owncam_localizer.py`의 기존 PF 진단값. 새 성능 근거로 합산하지 않는다.
