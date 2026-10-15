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
