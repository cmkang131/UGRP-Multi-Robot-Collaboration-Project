# search19 — 막힌 발행 펄스와 원판 오거부 (기본 OFF)

2026-10-15, PR #484, 기준 search18 `00620d7ace67ae1b7f39aa0a20d990aff11cf861`.
**OFFLINE_CHECKED / PHYSICAL_NOT_READY**. Mac 물리·렌더·학습·원격 호스트 접속·모델 호출 0.
search18의 재현 1/4·신규 11/12를 새 성공률로 바꾸거나 합산하지 않는다.

## 로봇 관계와 원인

실패마다 저장된 개요·r1·r2 영상 6시점씩 **72장**을 직접 검토했다.
선택 시각: 315709=0/3/5/8/10/13, 8311709=0/1/2/4/5/6,
8311711=0/5/10/15/20/25, 8311723=0/1/2/4/5/6 SIM초.
배정과 실제 배치를 구분했다: 315709·8311709는 처음·중간·끝 모두 두 로봇의 최근접 끝이 청록이다.
r1의 배정·관찰 대상은 파랑이다. 8311711·8311723은 r1이 청록, r2가 파랑에 더 가까운 맞교환 시작이다.
8311711은 마지막에 각자 배정 끝에 도달하고, 8311723은 맞교환 관계가 남는다.
공용 영상·GT 거리는 관계·오차 평가 전용이다(`relationship-eval-only.json`).

| 실패 | 확인한 원인 | search19 판정 변화 |
|---|---|---|
| 315709 r1 | SIM7.9부터 경로·waypoint는 존재하나 x/y가 다른 주행 이득이 경로 접선을 왜곡해 실제 발행 펄스가 상대 여유를 침범. 기존 사후 검사가 hold로 바꾸고 3초 무진행 두 번 뒤 인계 | 안전한 이동 펄스 49틱, 경로/목표 변경 없음 |
| 8311709 r1 | 첫 계획118후보=목표 원판 차단24·집게각64·IK30. A* 전에 탈락하므로 격자/시작 노드가 직접 원인 아님 | 5mm 차체 복구로 경로없음 3틱 해소 |
| 8311711 r2 | 교차 접근 중 peer 대기 진입, 이후 오래된 상대 기억이 남음. SIM24.8 평가상 기억 위치 오차614mm, 실제 상대→정적 목표874mm. 자기 카메라에는 상대 미관측. 새 후보도 기억된 상대의 팔 sweep을 거부 | 0틱. 새 빈 공간 관측 없이 기억을 삭제하지 않음 |
| 8311723 r1 | 첫 계획118후보 분류는 8311709와 같지만, 가능한 집게각의 차체도 can과 겹침. 0mm에서도 전체 검사 통과 후보0 | 0틱. 안전한 handoff 유지 |

두 6초 실패의 **후보별 이유·원판/차체 여유(mm) 전체 944행**은 로컬 `arm-latch-analysis/candidate-clearance.csv`의 해당 시드다.
네 실패 전체 반복 후보는 1,189행이며, `arm-latch-analysis/report.md`에 첫 계획의 고유 후보 표가 있다.
예: 8311709의 +10°/208mm는 원판 −29.41mm / 차체 +15.52mm,
8311723의 +15°/208mm는 원판 −55.88mm / 차체 −29.10mm다.
crate15 `d3571214`의 196/196은 독립 검증하거나 빔 결과로 승계하지 않았다.
빔의 두 즉시 차단은 목표 검사 이전/이후 순서를 확인했으며 새 격자 해상도 수정은 하지 않았다.

## 변경과 마진 근거

- `--search19-motion search19_motion_v1`: 기존 사후 검사에서 거부될 접근 펄스에만 유한 속도 후보를 시험한다.
  자기 발행 모델 두 종류로 전체 펄스 구간·경로 진행·기존 팔 sweep을 검사한다. 정렬·집기·준비 기준은 유지한다.
- `--search19-footprint search19_footprint_v1`: 기존 후보가 전부 실패하고 재관측이 끝났을 때만 차체185×160mm+5mm로 전체 후보를 다시 검사한다.
  IK·집게·퇴로·가시성·팔/집게 연결 sweep을 모두 통과해야 활성화하며, 이후 같은 차체 형상으로 경로와 실제 펄스를 검사한다.
  재계획 실패로 sampled 상태가 풀려도 전체 팔/연결 검사를 계속 강제한다(별도 회귀시험).
  search18 footprint는 계속 OFF이고 그 프로필의 65mm 상수는 바꾸지 않는다. 모든 새 토글의 기본은 OFF다.

| 패딩 mm | 성공12건 중 저장 이동 추가 차단 | 8311709 전체 검사 통과 후보 | 8311723 |
|---:|---:|---:|---:|
| 0 | 0/12 | 8 | 0 |
| **5** | **0/12** | **8** | **0** |
| 10 | 1/12 | 8 | 0 |
| 15 | 7/12 | 4 | 0 |
| 30 / 45 / 65 | 9 / 10 / 11건 | 0 | 0 |

이는 기하 패딩 스윕이며 **5mm가 위치 오차를 덮는다는 보증은 아니다**.
실행 변경은 전체 16건 동일 상태 재생으로 별도 확인했다: **8,150틱 기준 불일치0, 실패 판정 변화2/4,
성공 판정 악화0/12·성공 명령/상태 변화0/12**. 실패 4건 모두 invisible/held 입력 읽기0.
새 명령 뒤의 미래는 저장 원본을 유지한 한 틱 분기이므로, 실제 궤적·성공 개선은 미측정이다.
관련 시험 3파일 **33 통과**(pytest 동시1개). 원본5파일×16과 실패 영상72장,
총 **152항목**을 episode manifest의 복원/파일 해시와 대조해 불일치0·필요 항목 누락0을 확인했다.
전체 원격 원본을 새로 회수·검증했다는 뜻은 아니다.

## 재현·증거·대기열

이 worktree에서 다음 순서로 실행한다. 기존 Mac 환경을 재사용하며 전부 저장 입력 계산이다.

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_search19 --variants search19 --margin-sweep --out /tmp/search19-review/replay
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.analyze_grasp_act_search19 --replay /tmp/search19-review/replay --out /tmp/search19-review
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_search19.py tests/test_grasp_act_batch.py tests/test_grasp_act_admission.py
```

원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search18-{repro4,novel12}-gcp-00620d7a/`.
이번 기록: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/beam-search19-00620d7a/`.
커밋에 `search19-replay-summary.json`으로 16건 전부·원본 해시·코드 파일 해시·시험 기록을 보존한다.
중간 탐색/중단 재생은 별도 디렉터리이며 최종 근거는 `arm-latch-replay/summary.json`이다.

새 큐 `outputs/e2e18-admin/vm3-queue/20261015-grasp-search19-<이 커밋 SHA8>-diag.json`:
재현315709/8311709/8311711/8311723 + 신규8311800–8311811, 승인·실행·관문·기록·학습·승격 모두 false.
신규는 로컬 explicit seed 필드가 있는 JSON2,197개(1,951개 시드)에서 충돌0을 확인한 뒤 생성했다.
원격 재고는 미확인이므로 운영 인수 전 다시 확인한다. 이전 큐를 수정하지 않는다.
`32437b9f` 미승인 후보 큐도 보존하며 최종 큐의 supersedes 항목으로 연결한다.
동일 GCP 머신 종류의 새 물리 진단, 8311711 빈 공간 재관측, 8311723 막힌 화물의 작업 수준 재배정,
독립 Claude 검토가 남는다. 새 ≥40회 교사 관문·데이터 기록·학습은 승인하지 않았다.

## 참고 자료 (수정 전 확인)

- [Fox·Burgard·Thrun, DWA (1997), 저자 초록](https://www.cs.cmu.edu/~dfox/abstracts/colli-ieee.abstract.html):
  속도 공간에서 허용 궤적·진행을 비교하는 원칙. 본 구현은 명령 운동학만 사용하며 동역학/제동 안전 보증은 아니다.
- [Nav2 footprintCostAtPose 공개 코드 본문](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_costmap_2d/src/footprint_collision_checker.cpp):
  자세에 따른 footprint 변환. 본 구현은 기존 search18의 유클리드 직사각형 검사를 재사용하며 Nav2 전체 planner 복제는 아니다.
- [Daniel 등, Theta*, JAIR39 (2010)](https://arxiv.org/abs/1401.3843): 저자·초록·서지 확인.
  격자 방향 제약을 참고했지만 이번에는 Theta*나 격자 해상도 변경을 추가하지 않았다.
