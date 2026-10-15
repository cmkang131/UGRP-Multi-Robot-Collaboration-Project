# search26 — 남은 정렬 정지와 connector 관측 불일치

시작 HEAD a413fb0f, 마지막 실행 1effa9b266b44ac716b9808b95eb6aa938e42702.
수정 전에 gcp1 원본을 재집계했다. 순차 후보/프레임/이벤트 표는
`search26-baseline-rejection-table.json`, 원격 `/home/ugrp/ugrp-sim/outputs/search26-baseline/`.
현재기하15622, connector 시야4584, 계산예산3730(반복 행; 독립 표본 아님).
가장 큰 기하는 이전 search25에서 수정한 경로의 실제 겹침 검사로 보존한다.
남은 두 결함을 수정하며 기하·ready·jaw·IK 한계를 낮추지 않는다.

## A: 공통 펄스와 막힌 축 대안

`search26_alignment=search26_pulse_v1` 기본off. `sim/settle_pulse.py`는
release20의 097e53da 버전을 바이트 그대로 재사용한다. 기본 비례이득 .5,
.6양자/3반전/25% hysteresis는 그 모듈의 기존 설계값이며 실기 보장값이 아니다.
최소 양자는 이 경로의 기존 speed35·40ms와 issued 명령 모형으로 계산한다.
정렬 상태만 정착시키고 ready 수용은 기존 IK·jaw·팔·위치·60mrad 그대로다.
정답 위치·관절·접촉 정보는 들어가지 않는다.

R3 마지막 yaw 기본 모형의 tile_1 틈 −0.116mm, 보정 모형 틈 .365mm /
보간 여유 .500mm가 차단한다. `search26-baseline-alignment.json`은 원본
visible+issued 재구성(교사 cache 전체 재생 아님)의 각 축/모형/팔 검사를 담는다.
재현: `python -m scripts.analyze_grasp_act_search26_alignment <raw> --out <json>`.
선택한 실제 goal 좌표의 자기 상대 오차로 명령을 만들고, yaw가 막히면 정착된 축도
동일한 두 명령 모형의 goal/yaw 제곱오차 감소와 몸체/팔 검사를 통과할 때만 쓴다.
기존 merit의 .1m/rad 환산·3SIM초 진전 시한·.25 개선값은 유지한다.
최종 안전 필터 뒤 실제 발행만 공통 반전 원장에 반영한다.

## B: 관측 기반 재계획과 connector 실패 캐시

`search26_observation=search26_observed_v1` 기본off. 현재 자기 관측에 맡은 band가
fresh(기존 seen_t 판정)이며 기존 입력 admission을 통과하면 예측 5/15를 거부 조건으로
쓰지 않는다. 다음 틱에도 자기 관측을 다시 확인한다. 안 보이거나 관측이 오래되면
기존 예측을 적용한다. 몸체·후퇴·팔·발행 명령 충돌 검사는 유지한다.
동일 입력 snapshot의 connector 성공/실패를 교사 수준에서 공유하고 새 관측/명령
기하/시각에는 cache를 전부 비운다. 좌표 rounding·새 TTL·근거 없는 수치 문턱 없음.
98304 논리검사/틱·60SIM초 실행 상한 유지, wall30초는 별도 host safety cap_end.

참고(2026-10-15 공식 문서 확인):
- [Nav2 관측 레이어](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/obstacle/): 센서 관측으로 상태 갱신.
- [Nav2 경로 유효성·재계획](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/trees/nav_to_pose_with_consistent_replanning_and_if_path_becomes_invalid/): 유효 경로를 유지하고 무효 시 재계획.
- [Nav2 controller](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/): 갱신된 costmap에서 다음 제어 계산.
관측 우선과 매 명령 재검증은 이 원칙을 우리 가시 입력에 맞춘 적용이며,
Nav2가 색 band 또는 5/15 규칙을 규정한다는 주장은 아니다.

## 검증 계획

실패8311709 base,315709 v6/base 우선인 동결6장면, gcp1 n4-highcpu-64·동시6,
60SIM초·최대3라운드, 서버 합계40 이하. 학습RGB/학습/모델 호출0.
4/6 이상이면 실패 시드 우선32회·동시16의 검토 대기열만 만든다.
대기열은 전체 source_sha와 실제 존재하는 절대경로 rejection_table을 요구한다.

## R1 결과 — 4/6, 검토용 32회 기준 충족

실행 **`f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb`**. 원본
`gcp1:/home/ugrp/ugrp-sim/runs/search26-r1-short6-f92b07aa`.
완료6·성공4·HOST_ERROR0·**cap_end1**. 4/6 기준을 충족해 추가 물리 라운드 없이
32회 검토 대기열을 준비했다. 두 실패가 모두 해결됐다는 판정은 아니다.

|seed / 장면|결과|SIM초|남은 사유|
|---|---|---:|---|
|8311709 base|성공|39.3|이전 yaw 정지 해소|
|315709 v6|cap_end|37.1|planning_wall_safety_cap (PlanningSafetyCap), HOST_ERROR와 별도|
|315709 base|실패|42.5|approach_blocked_handoff|
|8311709 v6|성공|36.2|—|
|8312300 base|성공|22.5|—|
|8312301 base|성공|25.8|—|

후보 행: 현재기하21944, endpoint_feasible431, feasible11,
connector 예측시야 거부0·계산검사 예산 거부0. cap_end의 해당 틱은 아래 표와
분리하며, 원본 result의 이미 끝난 후보 로그만으로 그 틱의 탐색 단계를 추정하지 않는다.
모집단/궤적/완료 시간이 달라 기존4584행 대비 일반적인 개선율로 해석하지 않는다.
8311709 base는 tile_1에 막힌 yaw 검사를8회 기록하고 실제 정렬 펄스9틱 뒤 성공했다.
315709의 마지막 발행 몸체 검사는 band_blue가 막았고 v6 6회/base71회 기록됐다.
예측 시야 불일치는 제거됐지만 발행 후보와 관측된 화물 사이의 몸체 검사 차단은 다음 진단 과제다.
공통 펄스의 실기 반응이나 일반적인 파지 성공을 보증하지 않는다.

원본 전체 manifest와 회수한24개 실패 자기프레임+몽타주6개(총30항목) SHA256을 확인했다.
6몽타주·총72개 자기 영상 표본을 직접 확인했다. 실패 두 장면은 마지막에도 파랑 끝이 보인다.
영상만으로 충돌이나 성공을 재판정하지 않았고 결과는 평가 원장과 구분한다.
입력감사6/6 enabled·invisible_measurements0·held_world_reads0·GT자기위치비교off.
Mac 물리/렌더0·모델 호출0·학습RGB/ACT학습0·실물검증0.

첫30SIM초 기록4/6의 wall/SIM 중앙 **4.026**(>3.5 경고,6.0미만),
전체 실행 중앙4.372. 성공2회는30SIM초 전에 끝나 완전한 동시6 첫30 검증은 아니다.
동시16의 속도는 대기열 실제 실행 때 기록해야 하며 이번 결과를 승계하지 않는다.
비물리 사전22통과 + 회수 뒤 실제 connector 실패 캐시 재사용/입력변화 무효화1개 추가 통과
(변경된 search26 시험 파일7/7). 실행 핵심10파일은 이후 기록 커밋에서도 f92b07aa와 동일하다.

공유VM의 실제 maxRunDuration은24h·STOP, 유휴 타이머와 budget-stop 함수 ACTIVE였다.
다른 작업의 VM 설정은 바꾸지 않았다. 이번 실행은 기존 유한 실행기의1080wall초 감독 상한
안에서247.656wall초에 종료했다. 대기열에는 관측된24h와 프로젝트8h 문구의 정합 확인을
제출 전 조건으로 공개했다. 비용 정지 장치를 바꾸거나 우회하지 않았다.
자기 worker0·임대0·예약released를 확인했고 다른 작업/VM은 종료하지 않았다.
원본은GCP 영속 디스크에 남으며 호스트 밖 전체 raw 백업은 없다.

재집계(gcp1, 고정 소스 디렉터리에서):
```sh
.venv-sim/bin/python -m scripts.recount_grasp_act_search25 /home/ugrp/ugrp-sim/runs/search26-r1-short6-f92b07aa --out /home/ugrp/ugrp-sim/outputs/search26-r1-report
.venv-sim/bin/python -m scripts.analyze_grasp_act_search26_alignment /home/ugrp/ugrp-sim/runs/search25-r3-short6-1effa9b2/diagnostic/episode-000/raw --out /home/ugrp/ugrp-sim/outputs/search26-baseline/alignment-checks-reproduced.json
```
상세집계 재현 스크립트는 로컬 `search26-review.py` 사본과 GCP
`/home/ugrp/ugrp-sim/outputs/search26-review.py`에 보존했다(평가 자료만 읽음).

## 32회 대기열 — 미제출

`search26-queue.json` 및 운영 경로
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-grasp-search26-f92b07aa-diag.json`.
전체 source_sha=f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb,
동시16·서버합계40·60SIM초·base16/v6 16(합산 금지).
315709 v6/base,8311709 base/v6부터 시작한다. 나머지는 기존 비교 계획에서 정확히 복사했고
새로운 미관측 seed라고 주장하지 않는다. 이32회는DEV 비교이며 별도 교사95%/40 관문이 아니다.

`rejection_table`은 존재를 확인한 이 작업 디렉터리의
`experiments/2026-10-14-e2e18-grasp-rootcause/search26-r1-rejection-table.json` 절대경로다.
SHA와 재현 명령, 순차 후보/프레임/이벤트 관문 수가 들어 있다.
입력32계획은 GCP `/home/ugrp/ugrp-sim/outputs/search26-queue/plan32.json`으로 미리 보냈고
원격 SHA256=8f1552b8195a4dd7fb3600603c9b811c7398779ae037888e521d65e42723fb67을 확인했다.
실행 소스는 clean detached pin `/Users/changmin/projects/ugrp-wt/search26-src-f92b07aa`로
보존했다. 입력 계획은 실행 소스와 구분한 해시 고정 외부 파일이다.
approved/enabled/ready/submitted/execute는 모두false. 승인·실행·학습·기본값 전환은 하지 않았다.

추가 관문: 정렬 축 후보189 → 몸체/팔 안전181 → merit/IK 조건179 → 선택63 → 실제 발행63.
실행6 → terminal6 → HOST_ERROR없음6 → cap_end아님5 → 성공4.
cap_end1은 별도 비기하 사건(물체 해당없음·틈null)이며 중단 후보 단계를 추정하지 않는다.
`search26-funnel.py`는 gcp1에서 이 관문을 추가하고 재현 명령을 표에 남겼다.
