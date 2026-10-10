# e2e1 — 입력·상태 계약 (2026-10-11)

사용자 제공 e2eplan의 종료 조건은 **실제 LLM 작동 + 자기 지도 + 최초 위치부터 B까지 운반이 같은 실행에서 성립**하는 것이다. 이번 PR은 1단계만 구현하며 E2E 성공·운반 실행·과거 s1–s8 성공 승계를 선언하지 않는다. 기준은 main `cabb9777848491af02a105f5bb39811ebb33c5bf`, S4 `7b25757369d0a069d9c5fa47d916caec35681382`, S3 #416 `5337ff750455cc3de925a8a625a1d5184bc0508f`, egomap #405 `282717dc8ad1652d7845394aab8240247a0cb887`. S4에는 해당 S3가 이미 포함돼 있다. 병합 충돌은 퇴역/실험 기록과 CI 목록을 양쪽 보존하는 방식으로 해소했다. 다른 worktree의 후속 egomap67·s3fix23·s4live8은 수정하지 않는다.

최종 구조는 S4 한 호스트의 자기 지도 탐색 → 수신 대화에 의한 경로 합의 → S3 공동 운반 → B 재관측 후 내려놓기다. 세계·시계·지도·자기 명령 이력을 연속 유지하고 초기화는 최초 1회만 한다. 이번 단계는 입력 생성과 승인 상태만 제공하며 기존 단계 복원 실행기는 E2E 실행기로 등록하지 않는다.

`e2e_own_inputs_v1=off`가 기본이다. `on_v1`인 S4 Trial은 기존 `build_inputs`, `belief`, stop adapter의 정적 PF 추정과 지도 그림을 읽지 않는다. 새 `own_inputs_at(t)`의 폐쇄 스키마, 실제 자기 frame/JPEG sha256, 과거 자기 RGB 출처, 자기 시작 좌표계의 지도/pose/covariance, 자기 명령 및 실제 채널 inbox를 입력으로 묶는다. 목적지는 화물 종류·인원·역할과 **파란 바닥 B의 시각 설명**만 제공한다. 정적 B 좌표·경로·pickup slot·평가 상태는 제공하지 않는다. 기존 scenario/map은 실행 출처 감사용으로만 남고 제어 payload의 원천으로 사용하지 않는다. 기존 reply/ledger 프로토콜의 `own_belief` 근거 enum으로 자기 지도를 표시한다.

`OwnRoute`는 robot_id·frame_id·map_version·자기 지도(pose/covariance 포함)·B RGB 출처·waypoints·route_hash를 갖는다. planner·guard·provider 입력은 동일한 검증된 자기 스냅샷에서만 나온다. `zone_final_pair_skill.make_plan(..., on_v1)`은 정적 map/sheet를 전혀 읽지 않고 이 계약을 반환한다. 단순 정적 route overlay 및 기존 S3 Runtime의 정적 planner/guard/provider 구성은 ON에서 거부한다. `transport_admitted=false`이며 이 계약을 실제 기존 펄스/수명 루프에 적용하는 일은 3단계다. S4 ON의 `continue` 이외 실행 action은 `E2E_STAGE1_MOTION_NOT_CONNECTED`로 차단된다. 이 차단을 운반 성공 또는 연결 완료로 보고하지 않는다.

`PeerRoute`는 r2의 B 직접 관측을 요구하지 않는다. 수신 어댑터가 고정한 보고 전체 해시·실제 배달 시각을 확인하고 r1의 B 출처를 peer_report로 유지한다. 두 로봇의 자기 RGB에서 얻은 동일 빔 pose 두 개로만 peer→own 변환을 계산하며 spawn/world transform 필드는 거부한다. r2 provider·guard는 r2 자기 지도이며, r2 goal이 unknown인 상태를 보존한다. 이 수신 어댑터를 실제 S4 채널에 연결하는 것은 4단계이고 현재 운반 허가는 계속 false다.

`Agreement`는 실제 수신 proposal ID·route_hash와 r2 모델 승인 응답 ID의 일치를 요구한다. `(order_id, route_hash, grip_epoch, seg)`에 양쪽 GO와 ACK이 모두 있어야 ready다. 새 epoch/seg는 이전 투표를 지우며 과거 epoch/다른 해시/미수신 승인·미확인 모델 응답을 거부한다. 이 상태를 실제 claim·heartbeat·재집기·최종 내려놓기까지 연결하는 일은 4단계다. 호스트 spawn 좌표로 두 자기 지도를 맞추지 않으며, 향후 같은 빔의 자기 RGB에서 얻은 변환과 수신 `peer_report`를 별도 출처로 다룬다.

새 `e2e_one_beam_ownmap`은 0.60m·300g 빔 1개, r1/r2, r3 idle, 숨은 사건 없음이다. `zone_wide_door_e2e_b80_v1`은 원래 `zone_wide_door_geometry_v3`에서 B 바닥 half extent x만 .30→.40m(전체 .80×1.40m), map ID/version만 변경했다. 중심과 전체 벽·물리·카메라·weld OFF를 보존한다. 무회전 빔의 동서 착지 여유는 `(0.80−0.60)/2=0.10m`다. 평가 전용 시작 `(1.275,.05)`과 B 중심 `(4.6,−2.1)` 사이 축 경로 길이는 `3.325+2.15=5.475m`이며 실행 경로로 제공하지 않는다. 새 맵의 기존 정적 위치 제공자는 거부하고 calibration은 `UNMEASURED_NEW_MAP`으로 표시한다.

초기 RGB 검사는 표준 ScenarioFinalV3Scene/setup과 v7 world를 재사용한다. oracle-x86 영속 `~/ugrp-sim/runs`의 새 경로에서 기준+A+B의 r1 배치를 동시에 렌더한다. 기본 접힌 팔/카메라/FOV를 유지한다. 첫 자기 JPEG·frame ID·SIM 시각·해시를 저장하고, 평가 전용 segmentation을 같은 카메라 및 fisheye 변환으로 계산해 r1 B≥100픽셀·r2 B=0을 판정한 뒤 원본 JPEG를 육안 확인한다. 제어기/LLM은 없으므로 정지 배치는 의도된 상태이고 명령 반복·단계 진입 검사는 해당 없음이다. 모든 실행/오류는 summary.json에 포함하고 종료 즉시 원본을 Mac 기본 outputs로 회수·전체 해시 확인한다. ENOSPC는 HOST_ERROR다.

후속 단계: (2) r1 B 기억→빔 귀환, receive 연결 수정과 실제 도착, (3) 무하중→적재 위치 추정 연속성과 S3 다구간·최종 해제, (4) 수신 경로 승인·claim·epoch GO/ACK·heartbeat, (5) 고정 SHA·새 seed·전체 예산의 실제 E2E 1회. 심판은 실행 뒤에만 B 안 전체 외곽·바닥 지지·그리퍼 해제·속도<.01m/s 2초·weld OFF를 판정한다.

## 출처와 조사 범위

- 사용자 제공 통합 설계/e2eplan(이번 대화)이 기능 범위와 접점의 직접 출처다. `goal_route_continuous.GoalRoute`, `own_teach_capture.TeachGraph`, `zone_s3_route_binding`, `zone_s3_synchronized_carry`, `zone_s3_route_resume`, `s4_llm_host.Trial`, `zone_scenario_scene.ScenarioFinalV3Scene`을 읽었다. 선행 egomap66의 B 접근2/6·귀환0/6, S3 첫 구간6/6·전체0/6은 사용자 제공 설계의 당시 기록이며 이번 결과에 합산하지 않는다.
- [Nav2 behavior trees](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/): 공식 문서의 계획/추종 및 행동 트리 구조를 확인했다. 이번 분리 계약은 이를 기존 코드에 적용한 설계 추론이며 Nav2 실행/성능 검증은 아니다.
- [VT&R3 공식 코드](https://github.com/utiasASRL/vtr3): README의 관측 기반 teach/repeat 경로 구조를 확인했다. 코드 이식·새 주행은 이번 범위가 아니다.
- [CoELA](https://arxiv.org/abs/2307.02485): 논문 초록의 모듈형 기억·통신·실행 구성을 확인했다. 전체 실험 재현은 하지 않았다.
- [Hi Robot (2025)](https://arxiv.org/abs/2502.19417): 논문 초록의 상위 판단/하위 VLA 실행 계층을 확인했다. 이 PR은 모델/VLA 교체가 아닌 입력·상태 경계 설계다.

- 첫 렌더 3건의 HOST_ERROR는 평가용 segmentation API 오기였다. MuJoCo 설치 구현의 `Renderer.enable_segmentation_rendering`/`disable_segmentation_rendering`을 직접 확인하고 [공식 Python 렌더링 문서](https://mujoco.readthedocs.io/en/stable/python.html#rendering)의 동일 GL 소유 스레드 규칙을 유지해 수정했다. 물리·카메라·제어 입력 변경은 없다. 실패 원본을 회수하고 같은 3후보를 새 SHA로 재제출한다.
