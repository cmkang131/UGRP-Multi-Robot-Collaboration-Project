# T03: red/green M1 색 상자 논리 후보

기준 main `c12796676802ab54cad2f0635e3e96e911691c76`, 작업 브랜치 `codex/red-green-m1`. **DRAFT, 병합하지 않는다.** R2 중 cyan/red/green 색 상자 논리만 확장하며 can/tile/crate, specific item/count2, 최종 지도/provider/혼합 재고 지원은 별도 작업이다. 로컬 물리·시뮬레이션·렌더·새 모델 호출은 0회다.

## 변경

- 새 `harness.wrist_color_boxes.WristColorBoxDelivery`를 명시적으로 선택하면 세 색 모두 `m1_color_boxes_v1` 검출·공통 확신 거절 정책, 동일 v9 조작/복구 흐름, 명시적 kind의 holding/placement를 사용한다. `student.skill_module`/`skill_class`의 기존 동적 선택 경로를 재사용한다. 선택 module과 새 helper는 기존 runtime source closure로 해시에 포함된다.
- `ZoneOwnExecutor`는 선택 factory의 profile을 확인하고 주문 kind를 하위 M1/skill에 전달한다. 선택하지 않은 legacy skill은 cyan만 허용한다. 잘못된 factory/profile/kind와 can/tile/crate/unknown은 거절한다. 다른 kind의 placement를 배송 수에 더하지 않고, 종료된 job의 holding 판단도 마지막 kind를 보존한다.
- 활성 `SharedPoseDelivery`에 `ColorBoxDeliveryMixin`을 연결해 M1 자기 RGB 검색·coarse bay 주문서·근접 화면 잘림의 재관찰이 같은 kind를 사용한다. 동결 `M1OwnCamDelivery`의 직접 생성은 기존 cyan 계약을 유지한다. 원본 RGB를 cyan으로 바꾸거나 module 전역 함수를 바꿔치기하지 않는다. 색은 종류 단서이며 개별 item identity나 실제 접촉 증거가 아니다.
- frozen M1/N7/markerless/wrist v1–v9, 본연구 시나리오 s1–s6, 지도, calibration, 과거 성공 bundle/기록은 보존한다. N7의 decision body와 몇 가지 RGB 수학 함수를 새 모듈로 분리한 것은 그 원본 bytes를 바꾸지 않고 kind를 주입하기 위해서다. 기존 cyan v9 결과를 새 후보에 승계하지 않는다.

## RGB fixture와 검증 경계

`tests/fixtures/m1_color_boxes_v1/labels.json`은 지원 enum을 수정하기 전에 고정했다. SHA-256 `99f74aa7ce7c8565697da8a3d6f621c98677eed542054ddaed72e0bf59e03ff4`. 정답은 검출기 출력이 아니라 합성 도형 구성에서 정한 kind/가림/밝기 라벨이다. 정적 카메라 FK에서 계산한 좌표를 literal로 고정한 25개 PNG이며 physics/renderer는 사용하지 않았다. **최종 v3 환경의 독립 실측 라벨·인식 보정 자료가 아니다.**

첫 실행은 JPEG-only camera 경로에 보존 PNG를 전달해 `INVALID_BASE64_JPEG`로 실패했다(109 failed, 23 passed). 실패 로그는 보존한다. PNG와 라벨을 바꾸지 않고 q95 JPEG 전달본을 별도 저장하고 `transport.json`으로 source/전달본 해시를 연결했다. 프레임 SHA는 실제 전달하는 JPEG의 해시다.

확장 회귀에서 동결 M1 수정과 import 경계 위반이 발견돼 동결 파일을 복원하고 활성 어댑터로 이동했다. 같은 실행에서 발견한 provider 두 파일의 허용 해시 누락은 T03 이전 main에도 존재했다. `owncam_pose_source.py`의 `4fac772dbc6657937dea4486baf185ca85028abc`, `owncam_localizer.py`의 `cb21573263d851680b3637620fca35a5070026d5` 변경이 기준 main과 byte-identical임을 확인해 `test_owncam_memory.py`의 명시적 successor 목록에만 추가했다. provider 소스·기존 frozen manifest·원본 blob 검사는 그대로다. 이 bookkeeping은 해당 provider의 새 물리 검증을 뜻하지 않는다.

새 검사는 세 요청 kind × 저장 RGB를 대조한다. 다른 kind의 후보/holding/placement, 그림자·가림·저채도·검은 화면, 잘못된 payload, 미지원 kind, 작은 바닥 물체/단색 화면의 holding 거절, 현재 색 근거를 잃었을 때의 과거 방향 표 제거, 네 조건 동일 API/skill, private setup 변경의 공개 입력 비간섭을 포함한다. legacy cyan 회귀와 관련 executor/wrist 검사를 함께 수행한다. 정확한 최종 개수·명령·로그 해시는 `verification.json`에 기록한다.

최종 코드 `ae9726a3eb051cc6ef6c22f364216aa7badccca9`: **808 passed, 291 subtests passed, 3 deselected**, 83.75초. 신규 색 검사 142개가 포함돼 있다. 제외한 3개는 실제 world/physics를 생성하는 기존 host 검사다. 공유 잠금 아래 실행했으며 import guard가 로컬 MuJoCo/Torch와 네트워크를 차단했고 실행 전후 소스·fixture 해시는 동일하다. 현재 v63 bundle 정적 검증, 기준 main 대비 registry 불변성, 필수 CI fixture 3개와 diff 공백 검사도 통과했다. GitHub 정상 CI 결과는 PR에서 별도로 확인한다.

색 후보의 공통 S/V 거절은 보수적이다. 밝기·반사·실제 가림과 최종 카메라에서의 recall/정확도는 미측정이다. static 면적/색/형상·공이동이 실제 파지력이나 접촉을 보증하지 않는다. 이전 v4의 cyan-only self-occlusion shortcut은 새 후보에 적용하지 않고 세 색 모두 기존 v3의 정지/재검사 경로를 사용한다. 이 차이도 새 물리 인수 대상이다.

새 후보의 카메라 FK/IK/geometry는 기존 M1 보정을 재사용한다. 최종 v3 model_runtime를 검증했다고 선언하지 않으며 기존 `require_v3_consumers`가 물리 생성 전에 거절한다. P03 provider뿐 아니라 새 색 skill 자체의 v3 geometry/카메라 보정 연결도 조정자의 후속 합성 관문이다.

## 선행 작업과 인계

실제 조회한 PR 상태·head SHA·작성자가 보고한 검증 범위는 `dependencies.json`이다. #305 P01 map resolver, #307 P02 mixed inventory/orders, #308 P05 dialogue ledger, #312 P03 provider, #311 P07 manifest는 모두 OPEN/DRAFT이고 **merge SHA는 없다**. 선행 PR의 검사를 이 작업의 검사 수로 합산하지 않았다. 코드 합성/실행 검증은 아직 하지 않았다. host 공유 수정은 선택 skill의 profile을 factory로 전달하는 두 줄뿐이다. 지도 resolver·provider·원장·manifest·혼합 어댑터를 복제하지 않는다.

조정자는 `PHYSICS_CHECKS.md`와 `physics_proposal.json`의 red→B/green→C 정상·오인식 도전 4셀, 총 3,600 SIM초 제안을 검토한다. 최종 v3/provider/카메라/모델 보정, P02 distractor 장면 표현, negative 가시성 라벨, 새 source/bundle/workflow 고정·독립 검토·잠금이 남아 있다. 실행 가능한 봉인이나 등록번호를 만들지 않았다.

새 물리/학습/평가 cohort가 없으므로 이번 offline 회귀를 TensorBoard 성능 결과로 변환하거나 viewer를 시작하지 않는다. 실제 결과의 새 snapshot·원본 hash·scalar/video readback·표시 검증은 물리 인계의 필수 단계다. 모든 검사 raw는 primary outputs에 로컬 보존하며 Git 원격 백업으로 표현하지 않는다. UGRP 예외에 따라 Google Drive 작업은 없다. GitHub PR의 정상 CI는 실행한다.

## 참고 자료

- Refs #219, #221, #223
- P09 요구·배정: [PR #302](https://github.com/kcm0127-dotcom/ugrp/pull/302), `experiments/2026-09-30-scenario-capabilities/{REQUIREMENTS,TASKS}.md` (해당 branch)
- 기존 `zone_color_boxes`, `visual_attachment`, `visual_box_surface`, `wrist_zone_skill_v6/v9`, `m1_owncam_delivery`, `zone_own_executor`의 정적 계약·RGB 수학·제어 흐름을 재사용했다. 새 외부 의존성/논문/모델은 없다.
- `AGENTS.md`, `CONTRIBUTING.md`, `docs/execution_versioning.md`, `docs/tensorboard.md`
