# T03: red/green M1 색 상자 논리 후보

브랜치 `codex/red-green-m1`, PR #325. **DRAFT / 병합하지 않음 / 물리 인수 미완료.**
최신 두 P2 수정은 [REVIEW_325B_FIXES.md](REVIEW_325B_FIXES.md)와
`review_325b_fixes_verification.json`을 따른다. 이전 봉인 복원은
[REVIEW_FIXES.md](REVIEW_FIXES.md)에 보존한다.
초기 기준 main은 `c1279667`; Batch G 검토 대상은 `be97d9dd`, 후속 325B 검토
대상은 `9db1bbb6`다. 이번 수정은 main
`394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`까지 합성했다.

## 현재 선택 경로

- 봉인된 `owncam_delivery_shared`, `zone_own_deliver`, `zone_own_executor`, `zone_own_status`, `zone_own_team_host`는 origin/main과 바이트 동일하다. 기존 등록 JSON·해시도 그대로다.
- 색 기능은 **봉인되지 않은 호출자가 `harness.zone_color_box_executor.ZoneColorBoxExecutor`를 명시적으로 생성**해야 한다. `skill_factory`에는 `harness.wrist_color_boxes.WristColorBoxDelivery` 또는 같은 `box_perception_profile=m1_color_boxes_v1`을 명시한 factory를 전달한다. 기존 host에서 `student.skill_module`만 바꾸면 red/green이 활성화되지 않는다. host/runner 선택 연결과 새 실행 번들 등록은 후속 통합 관문이다.
- `WristColorBoxDelivery`의 기본 모드는 M1이며 진단은 `mode='diagnostic'`를 명시해야 한다. custom factory가 반환한 색 skill의 mode는 executor와 일치해야 한다. 진단 executor와 factory는 양쪽에서 명시적으로 선택한다.
- 새 `ColorSharedPoseDelivery`와 `ColorDeliverController`가 자기 RGB 검색, coarse bay 주문, 화면 잘림 재관찰을 같은 kind로 연결한다. 기존 경로에서 새 모듈을 import하지 않고 module/class 전역을 바꿔치기하지 않는다. 이동·정지·불확실성 gate와 수명 관리는 기존 코드를 상속한다.
- 새 실행기는 cyan/red/green만 지원한다. 잘못된 factory/profile/kind, 다른 색의 holding/placement를 거절하고 종료된 job의 마지막 kind를 보존한다. 조건별 분기는 없다. can/tile/crate, specific item/count2, 최종 환경·provider·혼합 재고의 실제 연결은 범위 밖이다.
- `controller_source_record()`는 새 실행기와 선택 색 skill의 전이 의존 소스를 기록한다. 실행자는 자기 진입점·설정·provider·모델·환경을 별도로 포함해야 한다. 이 코드 해시는 실행 번들 또는 성공 자격을 대신하지 않는다.

## RGB fixture와 검증 경계

`tests/fixtures/m1_color_boxes_v1/labels.json` SHA-256은
`99f74aa7ce7c8565697da8a3d6f621c98677eed542054ddaed72e0bf59e03ff4`다.
25개 PNG의 라벨은 detector 출력이 아니라 합성 도형의 kind/가림/밝기로 정했다.
PNG·라벨·q95 JPEG 전달본과 출처 해시를 그대로 보존했다. fixture와 최초 구현은
같은 커밋 `ae9726a3`에 있으므로 **Git 이력만으로 구현 전 고정 순서를 입증할 수 없다.**
최종 v3 카메라·조명의 독립 실측 라벨, 인식 보정 또는 일반 인식 정확도 근거가 아니다.

첫 JPEG-only 입력 실패(109 failed, 23 passed), 초기 회귀의 guard 차단,
`a4f75f8a`의 897 passed / 291 subtests / 7 deselected는 과거 기록 `verification.json`에
보존한다. 그 검사는 현재 v6e 소스 봉인 보존을 입증하지 못했다. Batch G는 실제
등록 회귀 5개 실패를 확인했고 이전 봉인 복원에서 다뤘다. 당시 추가한 provider 두 파일의
명시적 successor 목록은 main의 이미 병합된 바이트를 반영하는 bookkeeping이며
새 물리 성능 근거가 아니다.

현재 검사는 세 색 × 저장 RGB, 다른 kind의 검색/holding/placement 거절, 그림자·가림·
저채도·검은 화면, 잘못된 입력, clipping, coarse slot 밖 검출 제거, 실제 controller 생성,
네 조건 동일 API·private 입력 비간섭, 봉인 의존성 격리와 기존 cyan 회귀를 포함한다.
최신 명령·결과·변이·원본 해시는 `review_325b_fixes_verification.json`에 기록한다.
오프라인 검사는 #328에 따라 호스트 잠금 없이 실행한다. MuJoCo/Torch import와
네트워크 연결은 guard로 차단한다. 물리·SIM·렌더·실제 모델 호출은 0회다.

## 남은 인계

[PHYSICS_CHECKS.md](PHYSICS_CHECKS.md)와 과거 `physics_proposal.json`의
red→B/green→C 정상·오인식 도전 4셀은 staging 포함 **4×900=3,600 SIM초** 제안이다.
이번 수정의 별도 executor 진입점을 새 구성에 연결하고 새 소스·bundle/workflow를
고정해야 한다. 과거 proposal의 `candidate_code_sha`는 초기 후보를 가리키며 재사용할
실행 봉인이 아니다. 기존 시나리오 s1–s6·지도·보정·성공 기록을 바꾸지 않았다.

v3 FK/IK·카메라·provider admission, P02 distractor 표현, 실제 negative 가시성 라벨,
독립 재검토·정상 CI·물리 인수가 남아 있다. 기존 v3 consumer gate는 계속 거절한다.
`dependencies.json`은 초기 조회의 역사 기록이다. 이번 main 합성에 포함된 선행 작업의
검증을 T03 성공 수에 더하지 않는다.

새 실험 코호트가 없으므로 TensorBoard 성능 snapshot이나 viewer를 만들지 않았다.
실제 결과를 회수하면 새 snapshot·원본 hash·scalar/video readback까지 별도 확인해야 한다.
raw는 primary `outputs/cap-t03-redgreen/`의 로컬 보관이며 원격 백업이 아니다. Drive 작업 없음.

참고: Refs #219, #221, #223; Batch G 검토 `01edc483`; P09 요구·배정 #302;
`AGENTS.md`, `CONTRIBUTING.md`, `docs/execution_versioning.md`, `docs/tensorboard.md`.
