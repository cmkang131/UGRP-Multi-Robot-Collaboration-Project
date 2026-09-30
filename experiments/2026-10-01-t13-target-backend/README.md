# T13 target-aware backend — 오프라인 구현, 물리 미검증

PR #337에서 확인한 #320/#329의 연결 공백을 새 opt-in 경로로 연결한다. 기준 소스는
`394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`이다. 기존 제어기·identity/recovery 모듈·봉인된
테스트·s1–s6 원본은 변경하지 않았다. 이 PR의 코드는 커밋 SHA와 새 번들 해시로 실행한다.

## 연결과 정보 경계

- `TargetRecoveryJobs`는 공개 주문의 `order_id`/`requested_item_id`와 **완전한 공개 시각
  catalogue**의 색·형상·치수를 연결한다. catalogue에는 위치·상태가 없다. own RGB에서
  알려진 34×40×32 mm 상자 모델에 맞는 유일한 성분이 있어야 한다. 이는 단안 모델에
  조건부인 시각 추론이며 실측 치수나 개체 정답이 아니다. 같은 색의 다른 물건이 공개
  catalogue에 있거나 영상 성분이 중복/잘림/미적합이면 specific을 거부한다.
- unique public cue의 재식별은 이전 job을 중단한 뒤 새 자기 프레임에서 새 job으로
  제출한다. specific token은 유지하고 fungible의 불확실한 과거 token은 재활용하지 않는다.
  공개 item 이름이나 초기 slot만으로 선택하지 않는다.
- `TargetOwnExecutor.deliver(order, zone, target=TargetJob)` → `TargetDelivery` → `TargetSkill`
  전체에 명시 표적을 전달한다. 저장 own JPEG에서 고른 성분만 같은 픽셀 위치에 남긴
  PNG를 사용한다. frozen cyan v9 공간 skill을 위해 선택 성분의 hue를 92로 바꾸고 S/V는
  유지한다(`target_cube_attention_v1`). 카메라/FOV/크기는 변경하지 않는다. 원본 JPEG,
  변환 PNG, 양쪽 hash와 target/job/token/frame/detection 연결을 각각 보존한다.
- pose는 원본 full RGB와 자기 명령을 받는다. skill은 target view를 받는다. GT·접촉·실제
  관절·peer private state는 executor에 들어가지 않는다. cancellation callback은 해당
  로봇의 예약 명령 제거와 HOLD만 수행한다. 들고 있던 대상의 관측 상실/낙하/모호성은
  refresh 전에 중단한다. 하위 done은 identity/count 성공을 만들지 않는다.
- `RecoveryJobs`의 held→open→두 destination 관측과 보수적인 count 규칙을 유지한다.
  **전체 pickup region의 clear-empty 인식은 아직 구현하지 않았다.** 탐지가 없으면
  unknown이며 정적 pickup 위치를 유한하게 재탐색한다. 따라서 T13b M-U의
  `OWN_PICKUP_ABSENT` 항목은 이 후보로 충족했다고 판정할 수 없다.

## 실행 등록과 범위

새 번들은 `config/rgb_execution_bundles/zone-target-v85.json`, 표준 workflow는
`zone-target-checks` v`2.18.0`이다. 별도 서비스/대시보드가 없고 `scripts/sim_cli.py`에서
관리한다. 전이 import closure, 명시 동적 provider, XML/보정/지도/모델 hash,
명령·관측/접촉 프로필과 config를 고정하고 clean HEAD + 기대 SHA를 실행 시 요구한다.
기존 RGB dispatcher의 `RUNNABLE_ID`는 바꾸지 않는다.

번호 충돌 수정 전 main `fb8ee9fb`를 병합하고 열린 PR **25개 전체**를 다시 조회했다.
`RUNNABLE_ID` 최댓값은 v63, 전체 번들 최댓값은 v84, 통합 workflow의 2.x 최댓값은
**2.17.0**이었다. 기본 목록과 `configs/simulation_workflows.d/`를 모두 검사했다.
조정자 결정에 따라 #338은 `zone-final-environment-v84` / 2.17.0을 유지하고,
이 PR은 다음 빈 번호 **zone-target-v85 / 2.18.0**을 쓴다. 모든 workflow의 단순
최댓값은 수정 전 이 PR의 3.1.0이며, 별도 memory workflow의 3.0.0도 존재한다.
두 버전을 통합 2.x 번호의 최댓값으로 혼동하지 않는다.
각 ref/SHA와 검색 결과는 [renumber_id_reservation.json](renumber_id_reservation.json)에 있다.
조정자가 기존 `zone-target-v84`의 실행이 없음을 확인했으므로 이름만 바꾸며
retired 항목은 만들지 않는다. 최초 조회 [id_reservation.json](id_reservation.json)은
당시의 기록으로 보존한다.
#337의 [범위 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/337#issuecomment-5915779686),
[번호 예약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/337#issuecomment-5915972264)을 남겼다.

환경은 **개발용 MasterPi v2 / geometry_v2 / vision_zero_tag_v2**이며 표식0,
기존 카메라, floor_light_v1, cargo_noslip_v1, weld OFF, 센서 OFF다. 최종 v3/0.40 m walls
환경은 이 경로에 이관되지 않았다. #320/#329의 최종 환경 기준을 바꾸거나 과거 성공을
승계하지 않는다. can은 원래 배치대로 보존하지만 이번 actor의 운반 대상은 아니다.

네 통신 조건은 동일 controller/config/관측/입력 변환을 쓴다. 이 유한 진단은 no_comm의
고정 actor로 수행하며 메시지 송신/LLM 호출은 없다. 다른 조건 선택도 같은 제어기를
실행하므로 이 결과는 통신 효과 비교나 4조건 성공 근거가 아니다. actor assignment와
controller/config hash는 별도로 기록한다.

공용 workflow 목록 추가 때문에 현재 **미실행 DRAFT** `prereg_v6e.json`의 목록 hash 한
항목을 갱신했다. `status=DRAFT`, `runnable=false`, `execution_source_sha=null`을 유지한다.
과거 v6/v6b/v6c/v6d 봉인 JSON, 실행 소스, 두 source-pinning 테스트는 그대로다.

## 검증과 인계

[renumber_verification.json](renumber_verification.json)에 번호 변경 후의 오프라인
명령·결과·hash를 기록한다. 기존 [verification.json](verification.json)과
`pytest-offline-acceptance.txt`, `mutations.json`은 변경 전 `e29abdbc`의 기록이며
v85 검증 결과로 소급 변경하지 않는다.
번호 변경 후 관련 오프라인 검사는 **224 passed, 1 skipped**다. 건너뛴 항목은 실제
물리 host 검사이고, guard의 물리 step·실제 vision worker·네트워크 시도는 모두 0이다.
기존 RGB registry 불변·v63 현재 hash 검사와 T13a/b의 실행 없는 plan도 통과했다.
동작 소스는 그대로이며 번들 ID·workflow version·이들 입력 hash만 바뀌었다.
`mutation_checks.py`는 자식 프로세스 메모리에서만 8개 로직을 제거/변경하고 해당 테스트가
실패하는지 검사한다. worktree 소스·테스트는 바꾸지 않으며 임시 추출 디렉터리는 만들지 않는다.
저장 RGB fixture의 픽셀과 자기 발행 PWM만 읽었다. 원래 fixture의 GT label은 쓰지 않는다.

[PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)의 명령은 조정자용이며 T13 SIM checks는 실행하지
않았다. 추가 회귀 묶음에 기존 `test_team_host_isolation_abort_and_horizon_on_the_real_world`
항목을 잘못 포함하여 World/renderer 생성까지 진입했고 `invalid CoreGraphics connection`으로
종료됐다(220 passed, 1 failed). 테스트 선택 오류이며 물리 성공 근거로 쓰지 않는다.
이후 nonphysical guard를 켜서 다시 검사했다. fake native clock의 900초 기록은 물리 SIM
실행이 아니다. 실험 결과가 없으므로 TensorBoard 결과 snapshot도 아직 없다.
