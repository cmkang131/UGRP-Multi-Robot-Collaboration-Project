# 통합 러너의 PairTeam·자기 영상·인식 지연 연결

2026-09-27, PR #229의 #194 + #235 통합. `tags_temporary`는 **임시, 표식 사용, 연구 결과 아님**이다. 이 변경은 비물리 테스트로 검증하며 새 물리 성공이나 실제 LLM 코호트를 뜻하지 않는다.

## 결정과 공동 운반

`IntegratedTrial`은 #194의 입력 계약·한국어 프롬프트·메시지 bus·SIM 비용·재질문 스케줄러를 재사용한다. `claim`의 주문이 단독이면 `deliver`, 2인 `long_beam`이면 `pair_carry(order_id, zone, partner_id)`를 호출한다. `HostRobotLink.call`은 #235의 `OwnCamTeamHost.call`을 사용하므로 PairTeam의 독립 제출·짝 매칭·취소·예약 명령 정리가 실제 적용된다. 한 로봇의 claim으로 상대 작업을 자동 시작하지 않는다.

현재 #235가 지원하는 짝은 **r1=end_neg, r2=end_pos**다. 다른 역할·r3 짝·heavy_crate·3인 주문은 거절하며 단독 배송으로 바꾸지 않는다. 이 고정 역할 제한은 네 조건에 동일하다. 일반 역할 할당 연구로 확대하려면 실행기 지원 범위를 먼저 넓혀야 한다.

`zone_pair_status_v4`가 유일한 짝 상태 채널이다. `PairStatusBus`는 실제 `PairTeam.records()`의 감사 기록만 반환하며 별도의 사용되지 않는 채널을 만들지 않는다. 상태 enum과 촬영 시각·프레임 ID·유효시한만 짝 동기화에 사용한다. 모델 입력·연구 스케줄러에는 짝 상태를 넣지 않고, GT·접촉·측정 관절·동료 작업 종료로 깨우지 않는다. 모델 사고 중에는 진행 중인 자기 작업을 계속하고, 유휴 로봇만 대기한다.

`configs/zone_study_integration/i2_pair_long_beam.json`과 `pair_dev_DRAFT.json`은 2대 빔 주문의 실행 설정이다. coarse sheet는 실행 전에 고정하며 runtime 좌표에서 재생성하지 않는다. #235의 표준 `TaggedCargoZoneScene` 준비 함수를 재사용한다. 이 draft는 실행되지 않았고 source/bundle pin과 실행 예산 확정이 남아 있다. 기존 `prereg.json`과 과거 결과는 보존했다. 앞선 `zone-study-integration-v2-pair-delay`의 기록은 그대로 보존한다. 현재 후보는 `zone-study-integration-v64-source-closure`이며 과거 실행의 성공을 승계하지 않는다.

## 실행 소스 고정 (PR #229 P1 수정)

번들의 `runtime_files_sha256`은 러너·지원 모델 transport의 전이 import closure에서 만든다. 함수 안의 import, 상대 import, package initializer도 읽으며 모듈을 실행하지 않는다. `student.skill_module`과 provider `factory`의 설정 선택 모듈도 시작점에 포함한다. provider 등록 파일·추가 source_files·실제 보정·지도·시나리오 해시는 함께 고정한다. `visual_arm.py`, `llm_completion.py`, `session_scenes.py`를 포함한 의존 소스 변경은 번들 해시를 바꾼다.

비-dev 실행은 물리 모듈 import·host 생성·출력 디렉터리 생성 전에 `prereg.source_sha` 또는 `--expected-source-sha`를 Git commit으로 해석하여 HEAD와 대조한다. 둘 다 있으면 모두 일치해야 한다. 누락·미해결/다른 SHA·dirty 실행 소스·번들 불일치를 거절한다. dev는 미등록 배선 진단을 허용하지만 명시한 SHA는 dev에서도 검사한다. `--bundle`은 실행 없이 현재 후보의 해시를 출력한다. 이번 작업은 미커밋이므로 DRAFT의 source/bundle pin을 확정하지 않는다.

번호는 로컬 branch/remote refs 259개에서 공통 RGB 최대 v63·통합 최대 v2를 확인해 v64를 선택했다. fetch/PR 목록 갱신은 sandbox·네트워크 제한으로 실패했으므로 원격의 최신 번호 예약 확인은 별도다. [수정·검증 기록](../experiments/2026-09-27-pr229-source-delay/README.md)에 확인 범위와 번들 후보를 보존한다.

## 실제 M2와 지연 provider의 비물리 회귀 (P2 수정)

`tests/test_zone_study_pair_delay.py`는 실제 `PairTeam`·`M2DoorStudent`·`GuardedPairApproach`·`DelayedPoseSource`·태그 검출기/PF를 가짜 물리 시계에서 연결한다. 저장된 r1/r2 자기 RGB 18장과 발행 서보 명령만 사용하며, 평가 좌표는 fixture에 넣지 않는다. 입장 시 추정과 gate도 영상에서 만든다. 열린 checkpoint부터 M2가 PF를 교체하고 재관측·파지 영상 판정·readiness·동시 GO를 수행하는 구간을 검증한다. 추정·guard·readiness를 stub으로 바꾸지 않는다.

앞선 팔 안정화 대기가 6초 남은 r1 fixture에서는 두 로봇이 새 추정과 유효 readiness를 얻고 같은 시각에 `lift_go_1`을 발행한다. 대기 차가 없는 재생에서는 먼저 준비된 r1의 자세 불확실성이 상대 대기 중 커져 중단하며, 과거 readiness로 GO하지 않는 것도 검사한다. 두 경우 모두 PF 교체 후 0.16초 이전 추정 공개 차단을 확인한다. 이는 저장 영상의 시간·인터페이스 회귀이며 실제 접근·운반·물리 성공이나 네 조건 연구 비교가 아니다.

## 자기 손목 프레임과 다회 모델 호출

각 `HostRobotLink`는 자기 포트의 `robot_cam`만 받는다. robot ID·camera·JPEG SHA-256을 검사하고 호출 시작 시점까지의 최신 자기 프레임을 snapshot한다. `build_inputs`는 이 JPEG를 `CURRENT OWN WRIST RGB`로 실어 #194의 `ModelCallTransport`와 **실제 GeminiProxyCompleter**에 보낸다. 통합 경로는 `FrameLibrary`를 읽을 수 없다. 요청 이미지 원문과 해시는 `study/request_images/`, 요청·호출·입력 기록은 `study/`에, 실행기의 전체 촬영 원본은 `own_frames/<robot>/`에 보존한다.

CLI 기본은 fixture다. 실제 모델을 붙이는 프로그램 연결점은 `ModelAdapter(client_factory, send_ledger)`와 `run_trial(..., model_adapter=...)`다. `gemini_client_factory(..., study_json=True)`와 #194의 **기존 persistent budget을 소유한 PilotSendLedger**를 시행마다 만든다. 일반 live SendLedger는 transport가 거부한다. 새 예산이나 네트워크 우회 경로를 만들지 않는다. 모델·설정 해시는 bundle/provenance에 기록하고, 실제 adapter의 출력 SIM 비용은 응답 텍스트 토큰 수로 계산한다. 이 작업에서 실제 모델을 호출하지 않았다.

통신 3조건은 실제 전달된 메시지에 의한 `report` 호출과 inbox를 사용한다. `no_comm`에는 수신/송신이 없으며 자기 작업 사건과 자기 idle/busy 타이머로 반복 결정한다. 늦게 도착한 리더 메시지가 첫 결정 뒤의 재결정에 들어가는지 네 조건을 검사한다.

## 연구 전체 접촉 프로필

#190의 `s1`–`s6` 설정은 모두 `cargo_noslip_v1`, weld OFF다. 과거 실험 JSON은 덮어쓰지 않았다. 통합 러너는 시나리오·episode 중 어느 쪽이든 이 프로필과 다르면 시작 전에 거절한다.

bundle의 `contact_profile_expected`는 base + cargo XML 변환으로 계산한 `noslip_iterations=10`, `timestep_s=0.00025`와 프로필/소스 해시를 담는다. 물리 host 생성 뒤 실제 적용값과 대조한다. **manifest의 `applied_contact_profile`은 host의 실제 model option에서 읽은 기록**이며 예상값을 복사하지 않는다. host 생성 전 실패하면 null이다. XML 검사와 실제 접촉/운반 검증은 별개다.

## tags_temporary와 #237 교체 연결점

현재 registry의 선택 항목은 `tags_temporary`뿐이다. 모든 pose provider를 `DelayedPoseSource`로 감싸며 **촬영 SIM 시각 + 0.16 s** 이전에는 새 추정을 `report()`와 `loc.estimate()/predict_to()` 어느 쪽에도 공개하지 않는다. 입력 순서를 보존하려고 자기 명령·motion profile·프레임을 같은 지연된 필터 시계에서 재생한다. 추정 시각은 지연된 시각 그대로이며 현재 시각으로 위장하지 않는다. 로봇의 실제 명령 실행이나 LLM의 원시 JPEG 전달을 0.16 s 늦추는 정책은 아니다. provider 추론 wall 시간은 `robots/<id>/inputs/pose_timing.jsonl`에 따로 기록하고 SIM 지연 값으로 쓰지 않는다.

#237 `vision_zero_tag_v1` 교체 전 필요한 조건:

- registry의 factory를 `harness.vision_pose_source:VisionPoseSource`로 등록하고 소스·worker 설정·모델·실제 보정 해시를 고정한다. runner는 student에게 실제 전달한 보정을 provider 기록에도 사용한다.
- `zone_wide_door_walls_v3_notags`와 태그 없는 표준 Scene 연결을 추가한다. 현재 tags 장면 검사를 우회하거나 태그 지도로 비전 성능을 보고하지 않는다.
- 사전 등록 episode의 `pose_priors[robot_id]`에 **자기 출발 도크**의 mean/std/source를 넣는다. `StudyTeamHost`는 provider가 `init_prior`를 지원할 때 이를 호출하고 누락을 거부한다. runtime GT로 초기화하지 않는다.
- `StudyTeamHost.close()`는 각 provider의 `close()`를 호출해 worker를 정리한다. worker 실패 때 report와 loc 양쪽의 fail-closed 동작, 고정 지연, 명령 시간 정렬을 재검증한다.
- #235의 M2 재위치 추정은 태그 PF를 교체하는 경로가 있다. 현재 adapter는 이때도 지연 인터페이스를 유지하고 reset 전 대기 관측을 버린다. 비전 provider에서는 이 교체를 거절하므로, 교체 전에 태그 필터 생성 없이 비전 필터를 재초기화하는 명시적 adapter가 필요하다.
- VIS3 게이트 FAIL과 폐루프 dev 한계를 유지한다. provider 교체는 이 변경에서 하지 않는다.

## 검증과 남은 실행

`tests/test_zone_study_integration_pair.py`는 가짜 물리 시계·응답 wire만 대체하고 실제 연구 scheduler, 입력 builder, Gemini adapter, host API, PairTeam, 짝 상태 채널을 실행한다. 모델 호출과 물리 step은 없다. 기본 통합/격리·실행기/짝 회귀도 함께 검사한다.

남은 물리 검증은 고정 소스·예산·잠금 아래 새 draft의 4조건 전체 실행, 실제 자기 프레임 감사, 0.16 s 지연에서의 위치 불확실도와 짝 readiness/heartbeat, 파지·문 통과·방출·abort·거짓 확인, 실제 적용 프로필과 weld OFF 확인이다. 실제 LLM 파일럿과 태그 0개 provider 검증도 별도다. 물리/모델 결과가 생기면 기존 지침에 따라 새 TensorBoard snapshot으로 전달한다.

## 근거

- [참고 자료](references.md): cargo profile과 재사용 모듈의 출처.
- [이슈 #222](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222), [#223 fixture/다회 결정 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/223#issuecomment-5852769695).
- [#216 고정 인식 지연 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5852229650), [#237 provider 계약과 미완료 게이트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/237).
