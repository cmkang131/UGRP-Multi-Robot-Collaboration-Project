# carry1 — solo 목적 구역 운반 진단 준비 (2026-10-15)

상태: 구현·오프라인 검증 완료, 물리 실행 0/8, 원격 접속·제출·학습 없음.
77개 테스트 통과는 코드/가짜 backend 검증이며 실제 운반·새 구역 놓기 성공 근거가 아니다.

## 소스와 범위

- 지정 기반: `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8` (#502).
- 구현 SHA: `5b1fe9246bda0609019bee869f181ace9d67fe33`. 이후 기록 커밋은 실행 코드를 바꾸지 않는다. 최종 실행 SHA는 대기열 `sha`에 고정한다.
- 기반에 v6 장면 로더/자료가 없어 main `c72a2b50628e549fee8032378f4c7cf709fe688c`을 병합했다(`4e387d39`).
  실행 결정 문서는 렌더 토글의 기본 off 제한과 새 crate 색/v6 결정을 함께 보존했고, GCP 문서는 solo 기록 준비 절을 보존했다.
- 시작 시 fetch·열린 PR을 확인했고 [#502 범위 알림](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/502#issuecomment-6182798557), [#504 범위 알림](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/504#issuecomment-6182798863)을 3줄로 남겼다.
- 새 Python/CLI 토글 `solo_carry_to_zone_v1` / `--solo-carry-to-zone-v1`은 기본 off.
  `solo-carry-to-zone-v1` 공통 workflow 어댑터도 등록했으며 실행기는 Linux gcp1만 허용한다.

## 구현과 입력 경계

1. 기존 visible-only 교사가 집고, 자기 명령·RGB lookback으로 들기를 확인한다.
2. 공용 top RGB의 노란 차체 부분을 고정 보정으로 검출한다. 자기 발행 이동과 일치하는 단 하나의 움직임으로 지도 자세를 초기화한다.
   이후 RGB로 위치를 보정하고 방향은 자기 명령을 적분한다. spawn·실시간 자기 정답·화물 좌표로 초기화하지 않는다.
3. 정적 지도 후보 자리 중 추정 자기 위치에서 도달 가능한 자리를 고르고, 기존 `zone_teacher.plan_path` A*와
   `grasp_act_visible_route`의 구간 검사를 사용한다. 26 cm 원형 여유, 2초 넘은 RGB 위치·막힌 경로는 정지/실패다.
4. 선택한 자리 15 cm 앞에서 자기 RGB로 실제 목적 구역 바닥 색을 0.3초 연속 확인한다.
   held 가림을 포함한 기존 lookback FK/광선 마스크를 사용하며 예상 가시성만으로 통과시키지 않는다.
   이어 자기 명령으로 15 cm 접근, 고정된 자기 기준 낮은 팔 자세로 놓기, 열기·후퇴·실제 RGB 둘러보기를 수행한다.
5. held 구간은 close부터 open 완료까지다. 화물 상대 측정 콜백도 이 구간에는 호출하지 않으며,
   지도 코드에는 보이는 물체의 정답 측정도 전달하지 않는다. held 가시성/좌표/접촉은 평가 출력 소유자가 읽는다.
   기존 정답+오차 둘러보기 초기화는 새 토글에서 차단한다.
6. `carry_prepare/carry_to_zone`: `local_skill_sample=false`, `zone_place_view/zone_place_advance`와 놓기·후퇴: true.
   writer도 같은 라벨과 `destination_zone=A/B/C`를 지원하며 지도 추정/top RGB를 ACT 관측에 넣지 않는다.
   이번 진단에서는 학습 RGB를 강제로 금지한다. 새 관문 전에는 학습 기록/채택을 허용하지 않는다.

## 별도 평가

- 기존 clearance≥12 mm·기울기≤10°·양쪽 손가락≥0.5 N·3초 들기 기준을 보존한다.
- 목적 구역 안 놓기: 모든 collision box의 8꼭짓점 XY가 구역 경계 안, 바닥 오차≤5 mm,
  기울기≤3°, 속도≤0.01 m/s, open 명령 및 화물/손가락 접촉 없음, 종료 시 연속 2초 안정.
  집은 자리로부터 5 cm 제한은 새 평가에 적용하지 않는다.
- 운반 시작~lower 시작 전 모든 10 Hz 표본에서 clearance≥12 mm·양쪽 손가락≥0.5 N.
  한 번의 이탈도 실패로 유지하며, 재파지/최종 성공이 지우지 않는다. 100 ms 미만 사건은 이 표본으로 배제할 수 없다.
- 전체/운반 SIM초, 추정 자기 위치·방향 오차, 구역 배치와 무낙하를 분리 기록한다. 평가 결과는 제어기로 돌아가지 않는다.

## 검증

```text
.venv-sim-worker-mac/bin/python -m pytest -q --tb=short \
  tests/test_grasp_act_solo_carry.py tests/test_grasp_act_solo_teacher.py tests/test_grasp_act_solo_run_path.py
77 passed in 33.91s
```

실제 사용한 Python은 기본 checkout의 기존 환경이다. 테스트 파일은 위 3개로 제한했다.
기본 off, 단일 움직임 식별/둘 이상 거부, 위치 stale, 막힌 지도, 들고 있는 화물 측정 거부,
운반/놓기 전체 명령 흐름, 실제 FK floor mask, 라벨·목적 구역, 구역 경계/낙하/기울기/접촉 반례,
실행기 stub의 기록/평가 분리를 검사했다. 결과 로그와 파일 SHA-256은 `summary.json`에 있다.
추가한 통합 검사에서 발견한 NumPy bool JSON 직렬화 문제를 수정했다.
둘러보기 이벤트와 물리 평가 행을 구분하지 않은 테스트 assertion도 수정했다.

## GCP 대기열과 남은 확인

`diagnostic-plan.json`: cyan/red/green/yellow ×2, seed 93200–93207, v6 장면의 실제 주문 목적지 A/B/C.
정적 지도/장면 파일 해시를 고정한다. 로컬 대기열의 정확한 seed 중복은 0건, 원격 미사용 여부는 미확인이다.
최종 push SHA로 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-solo-carry-<SHA8>.json`을 만든다.
`coordinator_approval.approved=false`, `runs_enabled=false`, 각 run `enabled=false`,
`gate_promotion_authorized_if_all_conditions_pass=false`, 학습 RGB off. 8개 모두 승인 전 실행하지 않는다.

- GCP project `ugrp-act-train-1014`, gcp1 n4-highcpu-64 지정(실제 상태 확인 안 함), 첫 진단 동시 1개, 최대 300 SIM초.
  같은 머신/동시 수 첫 30 SIM초 속도·budget-stop·8시간 STOP·유휴 20분·저장공간은 조정자가 확인한다.
- 원본 예약 256 MiB/개, 합계 2,048 MiB는 미실측 추정이다. top 위치추정 프레임/명령/평가/검토 영상과 해시를 보존한다.
- top 차체 중심의 9 cm 평면 가정, 노란 상자와의 혼동, 최초 움직임 식별, 적분 방향 드리프트,
  loaded 주행과 floor mask의 실제 영상 적합성은 아직 확인하지 않았다.
- 현재 경로는 정적 장애물만 피한다. 움직이는 장애물·다른 화물의 온라인 회피는 검증 범위 밖이며,
  parked robot/화물이 경로를 막는지도 첫 원본에서 확인한다. solo 교사 성공/ACT 학생 성공을 합산하지 않는다.
- 각 실행 처음·중간·끝 최소 6프레임 및 60 SIM초마다 최소 1프레임 확인.
  공통 결함 확인 시 같은 결함의 진행/대기 실행을 즉시 정지한다. 기존 40/40을 승계하지 않는다.
- 모든 8개와 실패/HOST_ERROR/미회수 상태를 분모에 남기고, 원본 회수·해시 확인 전 완료로 보고하지 않는다.

## 참고 자료

- [Nav2 Smac 공식 문서](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/planners_plugins/smac/):
  2D A* 및 원형 전방향 로봇 경로 계획 방식 확인(이번 세션 열람). 이 작업은 Nav2를 새로 설치하지 않고 기존 A*·footprint/구간 검사를 재사용한다.
- [OpenCV HSV inRange 공식 예제](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html):
  HSV 범위 분할 사용법 확인(이번 세션 열람). 기존 `KnownMapNavigator`의 차체 색/고정 높이 투영 방식을 적용했다.
- 로컬 선행 구현: `harness/known_map_navigation.py`, `harness/zone_perception.py`, `scripts/zone_teacher.py`,
  `sim/grasp_act_visible_route.py`, `sim/grasp_act_solo_lookback.py`를 직접 확인했다.
  새 움직임 연계의 실제 로봇 식별 정확도와 26 cm 여유의 물리 인수는 **미확인**이다.
