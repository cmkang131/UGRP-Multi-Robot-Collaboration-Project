# T10b — 자기 RGB 복도 제어 후보

구현 준비와 물리 인수는 별도다. 새 actor-side controller는 T10a 정적 경로를 따라
진입·후퇴·bay 대기·재진입·출구 확인 결정을 하고 짧은 자기 명령을 발행한다.
**물리/렌더/실모델 호출 0**이다. real RGB observer와 보정 actuator adapter는 이 PR에
등록하지 않았고 기존 study 실행기의 `CORRIDOR_RUNTIME_UNSUPPORTED`를 유지한다.
봉인 소스, 원본 s1–s6, 기존 지도·성공 번들·DRAFT 기준은 수정하지 않는다.

## 선행 소스와 범위

- 작업: `codex/corridor-yield-control`, 지정 worktree `cap-t10b-corridor-ctl`.
- 시작 HEAD `894f5984dceecb74f03b69f8365d13321d91cc02`.
- #310 HEAD `5d363335a286247a58d19652771b7ecddb21ef05`를 fast-forward 반영.
  원격 PR은 당시 **OPEN/draft, mergeCommit=null**. main 병합 완료가 아니다.
- 초기 main `687c30e04c53845faa5c55ad6e6123b65a0108d9` 통합 HEAD는
  `e1876c7e28acaffc61347330ce7e71022e7dca09`다. 재개 후 #328 main 병합 SHA
  `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`를 반영한 로컬 통합 HEAD는
  `2e279768952e39c073646bce306708ee4eb5bc6a`다. 아래 테스트 receipt는 이 HEAD와
  당시 미커밋 신규 파일의 실제 SHA-256을 함께 기록한다.
- 요구: #302 `codex/scenario-capabilities`의 `REQUIREMENTS.md`, `TASKS.md` T10b
  (조회 SHA `5d31f6c822a569b195ad7d0ea15a7d95de840974`).
  P09 inventory/feasibility 출력은 제어 입력으로 사용하지 않는다.
- T10a의 정적 전체 편대 sweep·bay stop/evacuation/reentry를 재사용한다.
  그 PR의 검증 결과를 이 PR의 신규 검사 수에 더하지 않는다.
- 신규 파일: `harness/zone_corridor_control_plan.py`, `harness/zone_corridor_control.py`,
  `tests/test_zone_own_executor_corridor_control.py`, 이 기록 폴더.
  테스트 이름은 기존 `test_zone_own_executor*.py` CI glob에 이미 포함된다.
  `.github/workflows`·CI 설정을 바꾸지 않으며 수동 cancel/skip을 하지 않는다.

## 입력·동작 경계

`CorridorController(robot_id, plan, task_id, observe, issue).tick(OwnFrame, now_s, delivered)`:

- `observe(frame, static_geometry, tuple(own_issued_commands))`가 자기 RGB만 읽는다.
  원본 지도 dict 대신 허용 기하만 복사한 `Geometry`를 전달하므로 setup/events/inventory/
  private peer keys가 관측기에 넘어가지 않는다. 반환 `OwnView`는 자기 영상에서 추정한
  화물 reference·자기 heading·오차 경계·자기 grip·이동/대피 공간의 가시성이다.
  관측기 반환의 source frame 번호·촬영 시각·RGB SHA가 실제 입력과 모두 같아야 한다.
  frame 번호만 늘리고 같은 촬영 시각을 재사용해도 거절한다.
  파트너 좌표/실시간 진실이나 top RGB 포트는 없다. 어댑터의 실제 출처 검증은 후속 필수다.
- `issue(Command)`는 지정 actor에 robot-relative 속도와 0.05초 이하 lease를 발행한다.
  성공적으로 발행한 명령만 자기 이력에 남긴다. 이동/그립 성공을 명령 이력으로 만들지 않는다.
  actuator 호출 오류는 hold 재시도와 terminal failure로 기록하며 hold 실패도 노출한다.
- T10a의 지원 경로만 수락하고 실제 own estimate→목표 연결과 한 번의 실제 명령 sweep을
  다시 검사한다. 미관측/불확실 경로·그립 상실·불가능 경로·오류를 안전하게 거절한다.
- solo는 이미 관측한 route prefix를 되짚어 자기에게 가능한 bay로 후퇴한다. bay에 들어간
  후 새 own clear frame/자기 timer 조건을 충족해야 재진입한다. host의 양보자/partner 선택은 없다.
- pair는 기존 `zone_pair_status_v5`/`carry_ready_N`·`carry_go_N`를 그대로 사용한다.
  각 endpoint는 자체 채널에서 실제 받은 enum만 읽는다. job nonce·route·role hash를 묶는다.
  파트너 이탈/실패·heartbeat 단절에는 종료한다. 센서와 메시지 TTL을 연장하는 우회는 없다.
- `no_comm/peer_ko/leader_ko/structured`를 고르는 인자가 controller에 없다. 모든 조건은
  같은 class/config/기억/status 채널을 쓴다. 이 후보는 고수준 자연어 메시지를 해석하지 않는다.
  정책 route hash·controller source hash·role assignment hash는 서로 구분한다.
- waypoint는 `PASSED`가 아니다. 마지막 전체 편대 출구 관측을 서로 다른 새 frame들로
  확인해야 `passage_observed`를 내며 `delivery_complete`는 항상 false다. 이것도 평가자의
  물리 통과 판정을 대체하지 않는다.

지원은 **이미 화물을 든 cyan solo / long_beam pair의 corridor leg**다.
최종 지도 pair bay가 맞지 않으면 pair는 기다리고 가능한 solo가 자기 기준으로 양보한다.
넓은 dev bay가 pair 정적 검사를 통과해도 v1 pair bay 정책은 미지원이다.
큰 pair pivot, unloaded 복귀, red/green/can/tile/crate 확대, pickup/release는 별도 작업이다.
이들 요구가 있는 경로를 묵시적으로 직선으로 바꾸지 않고 거절한다.
이 제한 때문에 원본 s4 E2E 완료를 주장하지 않는다.

## 검증·기록

초기 중단과 수정 전 진단은 아래에 보존한다. 재개 후 검증은 다음 절에서 구분한다.

- `red-01`: **66 passed, 1 failed**. 교통 고장 주입 시점이 이동 중이 아니라 정류장 대기였다.
  고장 시점을 첫 GO 직후로 고쳤다. 정상적으로 대기·재출발한 것을 실패라고 요구하지 않는다.
- `red-02`: **67 passed, 6 failed**. 살아 있지만 준비하지 않는 pair 대기 상한,
  잘못된 visibility 값, 촬영 시각 재사용, bay junction 도착과 차단 동시 관측,
  bay 점유 재확인 경계를 추가한 뒤의 반례다. 이후 소스를 수정했다.
  bay drift fixture도 실제 전체 footprint가 밖으로 나가도록 x=.7에서 x=1.0으로 바로잡았다.
- 현재 v6e 봉인 **85파일의 SHA 불변**은 정적 대조했다. 요청된 두 source-pinning pytest의
  최종 실행과 6개 mutation은 아직 미확인이다. 새 own-view provenance·phase 이탈 반례도
  최종 실행에 포함되므로 과거 67 pass를 최종 검사 수로 승계하지 않는다.
- 2026-09-30 14:06 UTC 이후 공용 잠금은 `claude/v6h1-confirm-run`의 확증실험이 사용했다
  (PID 21249, 예상 150분). 당시 `CONTRIBUTING.md`의 직접 pytest 잠금 규칙에 따라 대기했다.
  다른 작업을 종료하거나 잠금을 지우지 않았고, 테스트 미통과 상태에서 신규 구현을 커밋하지 않았다.
- `green-01` 이름으로 예약한 최종 검사는 **20분 잠금 대기 후 pytest 시작 전에 종료**했다.
  `validation/blocked-before-pytest.json`에 후보 소스 SHA·잠금·미실행을 기록했다.
  해당 폴더 이름은 통과 결과가 아니다. 최종 pytest/mutation, 신규 코드 commit/push/draft PR은
  남아 있으며 이 작업이 시작한 테스트/대기 프로세스는 모두 종료됐다.

원본 로그는 primary
`outputs/2026-09-30-t10b-corridor/`의 실행별 새 디렉터리에 보존한다.
`validation/red-01/`, `validation/red-02/`에 로그·receipt·실제 driver를 원본과 바이트 대조해
복사했고 `validation/checksums-red.json`에 SHA-256/크기를 기록했다.

재개 후 실행 명령(기존 환경 재사용, #328에 따라 host lock 없이 실행):

```sh
T10B_BATCH_MUTATIONS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-corridor-control/validate_offline.py \
  /Users/changmin/projects/ugrp/outputs/2026-09-30-t10b-corridor/NEW-FINAL-ID \
  tests/test_zone_own_executor_corridor_control.py \
  tests/test_zone_own_executor_corridor_contract.py \
  tests/test_zone_pair_status.py \
  tests/test_zone_pair_registered_source.py \
  tests/test_zone_study_source_pinning.py
```

`validate_offline.py`는 공용 잠금을 획득·해제·대기하지 않는다. MuJoCo·torch·모델 SDK
import와 네트워크를 막고 pytest를 실행한다. `receipt.json`은 정확한 소스 SHA·검사 인자·
Python·동시 실행 잠금의 조회값·부하와
현재 v6e 봉인 85파일의 전후 해시를 저장한다. 테스트 중 반례도 삭제하지 않는다.
`mutation_variants.py`는 소스 파일을 변경하지 않고 별도 프로세스의 메모리에서만
제어 삭제/양보 삭제/heartbeat 삭제/timeout 삭제/출구 검사 삭제/정적 거절 삭제를 만든다.
각 변형에서 관련 기능 검사가 실제 실패해야 통과이며 baseline 통과와 별도로 보존한다.

#310의 과거 CI run `36719543454`는 workflow를 main으로 복원한 뒤 남은
`test_new_push_preserves_queued_and_running_ci` 때문에 ci-preflight에서 실패했다.
[구체적 반례와 잔여 테스트/문서 복원 요청](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/310#issuecomment-5912709471)을
선행 PR에 남겼다. 이번 재개에서도 해당 실패를 재현한 뒤 `tests/test_ci_fast_path.py`와
`CONTRIBUTING.md`를 main 바이트로 복원했다. `.github/workflows`와 CI 설정은 main과
차이가 없다. 기존 P08 기록의 '정상 CI 허용' 정정만 선행 PR에서 그대로 승계한다.

### #328 이후 재개 검증

- `resume-red-01`: 기존 수정본 **78 passed**. 폴더의 red 이름은 재현 단계 이름이며
  실제 결과는 통과다. 이전 작업을 다시 만들지 않고 그대로 검사했다.
- `resume-ci-red-01`: 상속된 CI concurrency 테스트 **1 failed, 10 passed,
  280 subtests passed**. 사용자 지시로 보존할 main workflow와 테스트 기대가 충돌했다.
- `resume-ci-green-01`: main 복원 후 CI fast path/host lock/sharding 검사
  **96 passed, 280 subtests passed**. workflow 자체 변경·수동 취소·skip 없음.
- `resume-related-01`: 복도 제어/선행 복도 계약/상태 채널/요청된 두 source-pinning
  파일 **204 passed**. v6e 봉인 **85파일의 검사 전후 SHA 불변**도 확인했다.
- 변이 **6/6 검출**: 제어 삭제 2개 실패, 양보 삭제 1개 실패, heartbeat 삭제 2개 실패,
  wait timeout 삭제 2개 실패, full-exit 검사 삭제 1개 실패, 정적 경로 거절 삭제 1개 실패.
  각 변형은 원래 통과한 검사에서 assertion failure를 냈고 setup/teardown 오류는 없었다.
  변형은 자식 프로세스 메모리에서만 적용했으며 원본 코드 바이트 불변을 재확인했다.
- 재개 원본 로그/receipt/실행 driver 및 변이 로그를 `validation/resume-*/`로 복사하고
  전체 바이트·SHA를 [checksums-resume.json](validation/checksums-resume.json)과 대조했다.
  이들은 성능 측정이 아니므로 잠금 없는 wall 시간으로 속도 비교하지 않는다.
  raw 작업 폴더 자체는 로컬 보관이며, GitHub에는 여기 선별한 작은 검증 기록만 보존한다.

최종 판정: **오프라인 구현 검토에 제출 가능**, 물리 실행 준비/인수 완료는 아니다.
실제 observer·actuator 연결, 새 workflow/번들 등록·독립 검토, 8셀 물리는 남았다.
정상 GitHub CI는 초안 PR에서 실행하며 원격 결과는 PR checks로 별도 확인한다.

새 물리/학습/evaluation cohort를 실행하지 않았으므로 TensorBoard 물리 snapshot을 만들지
않았다. fake 단위검사의 green을 물리 성공률로 표시하지 않는다. 후속 실제 결과는 실패도
포함해 native TensorBoard snapshot·raw hash·표시 검증이 필요하다.

## 코디네이터 물리 검사

[정확한 8셀·고정 배치·판정·adapter 인수 조건](PHYSICS_HANDOFF.md).
solo/pair × 서/동 × 정상/대치 실패 = 8셀, 각 900초, **7,200 SIM초 최대**다.
이는 최종3D·walls_v3·표식0·weld OFF·cargo_noslip_v1에서 새로 실행할 제안이다.
원본 s4 정적 운반 4.05–9.35 m·beam 90°·green 120°, 빈 복귀·bay/지연 미산정 범위를
대신하지 않는다. 구현 검토, 실제 8셀 인수, 원본 E2E, 4조건 효과의 준비 판정을 나눈다.

## 참고 자료

- [#310 T10a](https://github.com/kcm0127-dotcom/ugrp/pull/310)
- [#302 capability audit](https://github.com/kcm0127-dotcom/ugrp/pull/302)
- [#328 오프라인 테스트의 기본 host lock 제거](https://github.com/kcm0127-dotcom/ugrp/pull/328)
- [T10a 기록](../2026-09-30-corridor-bay-contract/README.md)
- [T10a 수정·한계](../2026-09-30-corridor-bay-contract/REVIEW_FIX.md)
- [실행 버전 관리](../../docs/execution_versioning.md)
- [물리 결과 TensorBoard](../../docs/tensorboard.md)
