# search9 — 화물·벽의 축방향 목표 집합과 재탐색

2026-10-15, PR #484. 부모 `793865d20475098f96f6966edf8ea1ccba058f6d`의
[search8](search8.md)을 이어서 수정했다. 운영 중인 부모 소스의 결과는 기다리거나
합산하지 않았다. **새 물리 실행은 0회이며, ≥38/40 관문 통과를 주장하지 않는다.**
새 커밋 SHA는 `outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<SHA8>.json`에 고정한다.

## 원인과 성공 비교

원본은 `/Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-gate-gcp-86367b4b/`.
계획·시작·완료40, 성공34, 접근 핸드오프5, timeout1, 중단/HOST_ERROR0이다.
40개 전체의 plan/result/양쪽 명령/eval 원장 **200파일의 manifest 해시와 decoded 해시**를
대조했다. eval 원장에서 현재 `visible_measurements`만 추출하고 평가 정답은 버린 뒤
자기 발행 명령으로 VisibleWorld를 재구성했다. [전체 비교·원본 해시](search9-causes.json).

search8의 분류를 유지한다. 동료 목표점 점유3/6은 부모 변경의 대상이고,
이번에는 화물1/6·벽1/6·재탐색1/6을 다룬다.

| 원인 | 실패 원장 | 성공34개 중 비교 사례 |
|---|---|---|
| 화물 목표점 여유 | idx3/r1, `green_1`. +6.8초부터 기본 목표의 여유가 최대5.050mm 부족하고, 가시 구간62tick에서 차단. 목표 하나만 반복 검사하고 핸드오프 | 화물 목표 여유50mm 미만은 idx9 하나(1/34). `can_1` 여유가 최대2.483mm 부족했던8tick 뒤 다시 열려 성공. 일시 차단과 지속 차단을 구분해야 함 |
| 벽 목표점 여유 | idx17/r2, 관측된 `zone_wall_divider_2`. +6.6초 여유1.466mm 부족에서 즉시 nominal 핸드오프. 직전 계획9회/no_path0, 정체 watchdog 원인이 아님 | 벽 목표 여유50mm 미만은 idx12 하나(1/34). 최소13.467mm **양의 여유**를 유지. 성공34개에는 같은 벽 목표 차단이 발생한 사례0/34 |
| 재탐색 | idx7/r1. +12.5–33.4초, +33.8–54.7초 각각20.9초 시야 상실. 첫 복귀는0.4초만 유지. 원래 `ever_seen` 분기에서 높이별 유한 스캔을 제외하고 같은 자세 회전을 반복 | 시야 상실≥0.5초 후 복귀한 성공7/34: idx9,10,20,21,31,34,36. 4개는 최대2–3초, 3개(9,10,36)는10.1–10.2초 후 복귀. idx7처럼20.9초를 두 번 소모한 성공은 없음 |

50mm·0.5초는 **비교 집계 기준**이며 제어 임계값이 아니다. 목표 여유는 제어기가
수용한 가시 측정·명령 좌표계의 값이다. 실제 물체 접촉이나 위치 정답의 오차를
증명하는 수치로 해석하지 않는다. 자기 빔을 다른 화물 집계에서 제외했다.

저장 overview/r1/r2의 처음·중간·끝을 다시 열었다. idx3 +0/2/5/7/10/12초,
idx7 +0/12/24/35/47/59초, idx17 +0/1/2/4/5/6초, **총54프레임**이다.
서로 다른 끝 배정, idx3의 상대 대기와 화물 앞 정지, idx7의 화면 아래 파랑 끝→바닥/벽
반복, idx17의 청록 끝 너머 벽을 확인했다. [원본 이미지 해시](search9-frame-review.json).
성공34개 JPEG는 로컬 미회수라 비교는 원장 범위다. 새 렌더·원격 회수는 하지 않았다.

## 표준 방법과 구현

2026-10-15 search8의 1차 자료를 재확인했다.

- [OMPL 목표 집합](https://ompl.kavrakilab.org/core/goalRepresentation.html): 단일 목표 대신 여러 실행 가능한 목표 상태를 검사하는 구조를 따른다. 기존 IK→목표 충돌→전체 경로 선분 검사 순서를 재사용했다.
- [Nav2 recovery tree](https://docs.nav2.org/jazzy/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough/): 대기·회전·후퇴와 유한한 재시도 후 실패 반환이라는 구조를 따른다. 여기서는 대기/자기 카메라 자세 복원/회전만 사용한다. 검증된 뒤쪽 관측 없이 후퇴하거나 관측 장애물을 지우지 않는다.
- [Nav2 MPPI ObstaclesCritic](https://api.nav2.org/nav2-lyrical/html/md_nav2_mppi_controller_README.html): 목표 근처에서 없애는 것은 선호 반발 비용이다. 현재 교사의 여유는 단일 금지 여유이므로 선호 비용으로 간주해 축소하지 않았다.

기본 OFF `--approach-recovery approach_recovery_v2`를 추가했다. v1과 off는 유지한다.
`visible_only`·`issued`·`align_relook_v1`·`search_body_scan_v2`·goal_set·progress가 필요하다.
CLI→자식→결과/resource-admission/관문→속도 재사용/기록모드의 기존 모드 일치 검사를
그대로 사용하므로 v1의 측정을 v2 인수로 승계하지 않는다.

1. **화물·벽:** nominal203mm가 막히면 같은 끝·같은 빔 축 방향에서 거리
   **196/198/203/208/210mm**만 검사한다. 현재 선택이 여전히 유효하면 유지하고,
   새 선택은 nominal 거리 변화가 작은 것부터, 동률이면 경로 비용으로 고른다.
   ±90도 등 기존 넓은 사선 집기 후보는 v2에서 사용하지 않는다. 이 축방향 집합은
   이번 사용자 요청에 따라 기존 즉시 nominal 핸드오프보다 먼저 검사하며, 기존
   토글만 켰을 때의 즉시 핸드오프는 그대로다.
2. 접힌 차체130mm·벽 추가40mm·동료340mm·화물/자기 빔 여유와 정상 물리는
   그대로다. 각 후보의 full descent/hover IK와 모든 선분을 검사한다. 실행 펄스의
   예상 선분도 다시 검사하고, 대안 목표의 READY는 현재 차체 위치의 여유도 확인한다.
   후보 전부 실패하면3초 안에 기존 clean approach 핸드오프. 시야 상실이 시한을
   지우지 않는다. 동료 앞 접근/관측 대기는 search8의12초 상한을 유지한다.
3. **재탐색:** 3.2초까지 기존 짧은 pan sweep을 유지한 뒤, 마지막으로 띠가 보였을
   때의 **자기 발행 PWM**을 복원한다(4.6초까지). 이후 기존 세 높이의 회전을
   가까움→중간→멀리 순서로 실행한다. 숨은 목표나 기억된 정답 위치로 방향을 정하지
   않는다. 각 높이의390도 회전량은 발행 명령 적분이며 실제 회전 측정이 아니다.
   복구 시작에서40초 또는 에피소드58초에 clean search 핸드오프한다. 0.5초 연속
   재관측 전에는 예산을 초기화하지 않아 짧은 깜빡임이 시한을 늘리지 못한다.
   이미 시작한 pick에는 이 탐색 시한을 적용하지 않는다.

이 거리 집합·3.2/4.6/40/58초는 프로젝트용 설계값이지 문헌이 보장하는 수치가 아니다.
카메라/FOV·IK·집기 시퀀스·접촉 성공 판정·weld OFF는 유지한다. 근거리 ACT 학생의
실행 경로는 수정하지 않았다. 새 GCP 입력 감사와 실제 회복 성능은 별도 검증이 필요하다.

## 검증

관련 **3파일94 passed**: `test_grasp_act_recovery.py`, `test_grasp_act_goal_set.py`,
`test_grasp_act_batch.py`. 실제 저장 화물/벽 단면의 충돌 없는 축방향 경로, 새 장애물의
READY 거부, 펄스 선분 차단, 전 후보 실패의 유한 핸드오프, 숨은 입력 없는 자기 자세
복원/근거리 스캔, 깜빡임에도 유지되는 시한, pick 중단 방지, v2 자식 전달을 검사했다.
진단18개를15+3 wave로 실행하면서 같은 FailureStop 객체를 사용하고 앞 wave의
동일 실패 원인이 뒤 wave에도 누적되는 것도 검사했다. 기존 단일 wave 경로는 유지한다.

[저장 단면 검사](search9-goal-checks.json): idx3은203→**196mm**, 최소 목표 여유
**0.942mm**; idx17은203→**198mm**, 여유**3.534mm**. 둘 다 기존 IK·전체 선분을
통과하고 이동 명령을 낸다. **경로/IK 가능성은 실제 파지 성공이 아니다.** 특히 작은
양의 여유와 command odometry 오차 때문에 새 물리 진단이 필수다.

[40개 명령 비교](search9-replay.json): 원본 `86367b4b`의 **23,842명령**을 모두
대조했다. GCP/Mac libm의 duration 차이만≤1e-12초 허용하고 시각·바퀴·PWM·phase·done은
정확 비교했다. 후보끼리는 같은 Mac에서 정확 비교했다.

- 원래 성공34개의 명령은21,326개. **29/34, 17,442명령은 전체 동일**.
  달라진5개는 idx2,9,10,20,36으로 search8의 변경 실행 집합과 같다.
- 전체 저장 입력과 실제 발행 명령 이력을 양 후보에 강제로 동일하게 공급한
  **shadow 비교**: 원래 기준 대비547/21,326명령, search8 대비**176/21,326명령**이
  다르다. search8 대비 변경 실행은4/34(idx2,9,10,36), 30/34는 같은 출력이다.
- 첫 다른 명령 **이후는 과거 경로의 영상/발행 이력을 넣은 가상 출력**이다. 그 뒤
  변화 수는 동작 영향 범위를 보는 값이며 새 실행 명령 수·성공·회복 결과가 아니다.
  양 후보가 원본과 이미 갈라진 뒤 생긴 idx2 등의 차이는 실제 방문 상태의 비교도 아니다.
- idx3/r1은 +6.8초에 새196mm 목표 이동, idx7/r1은 +15.7초에 새 자세 복원으로
  처음 달라진다. idx17/r2의 +6.6초 벽 단면은 별도 회귀시험에서198mm 이동을 확인했다.
  idx17 전체 재생은 r1의 기존 동료 복구 때문에 이미 +2.6초부터 원본과 갈라진다.
- 재생 감사 **invisible_measurements=0·held_world_reads=0**. 현재 보이는 측정의
  admission과 입력 mapping의 비시각 필드 접근 경계 범위다. 과거 원본에 없는
  held_world_reads를0으로 소급하지 않는다. 전체 Python/평가기의 정답 접근 계측은 아니다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_recovery.py tests/test_grasp_act_goal_set.py tests/test_grasp_act_batch.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.analyze_grasp_act_remaining --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-gate-gcp-86367b4b --out /tmp/search9-causes.json
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_remaining --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-gate-gcp-86367b4b --out /tmp/search9-replay.json
```

## 새 대기열

[진단18](teacher-search9-diagnostic-plan.json)은 이전15개를 그대로 두고 idx15/16/17에
화물87003·벽87017·재탐색87007을 같은 시작 조건으로 다시 넣는다. **18실행/15고유 시작**이며
중복3개를 새로운 독립 상황으로 세지 않는다. 동시15+3 wave. 정상0–5 실제 성공6/6,
동료 재현11/12/14 성공3/3, 남은 원인9/10/13 및 반복15/16/17은 **실제 성공6/6**을
요구한다. 어려운6은 clean approach 핸드오프, 이전7/8은 성공 또는 clean approach
핸드오프를 허용한다. 새 화물/벽/재탐색은 핸드오프만으로 통과시키지 않는다.

이후 같은 SHA/토글/GCP `n4-highcpu-64` 동시16×30 SIM초 속도(중앙 wall/SIM≤3.5),
그 뒤 **조정자의 새 SHA/시드 승인** 후 [새 관문40](teacher-search9-gate-plan.json),
**188000–188039**, 실제 성공≥38/40이다. 핸드오프는 실패 분모에 남긴다.
원래 시작 제외1/40(2.5%)·nominal 제안 거절1/41은 별도로 보고한다.
계획 파일의 오래된 pair1초 설명만 현재 평가기의3초·tilt≤10도와 맞췄으며 평가기는
바꾸지 않았다. [로컬 시드 충돌0 확인](search9-seed-reservation.json); 원격 예약은
운영자가 제출 직전 확인한다. 속도용 첫16개는 관문 분모에 넣지 않으며 속도 뒤 튜닝하지 않는다.

대기열 최상위/진단만 `ready=true`, 속도/관문은 대기다.
`gate_promotion_authorized_if_all_conditions_pass=false`, `coordinator_approval.approved=false`.
**793865d2 대기열은 수정하지 않았다**(이전 해시는 [요약](search9-summary.json)).
운영자가 두 대기열의 순서/정리를 맡는다. 비용/유휴/8시간/저장 공간 가드,
`repeated_cause_v1`, 공통 결함 확인 시 중단을 유지한다. 모든 단계는 원본 회수·영상·
감사 필드의 명시적0 확인 뒤 승인한다. 새 원격 접속/제출/감시와 Mac 물리·렌더는0회다.
