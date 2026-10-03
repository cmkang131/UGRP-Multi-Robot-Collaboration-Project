# PR #363 독립 검토 — BLOCK

2026-10-03, Codex. **검토 SHA `081f18d86b61322c94ede8c926936b5471052596`**,
번들 `zone-final-pair-highpose-v93`, workflow `3.5.0`.
검토 브랜치 `codex/review-363`; 구현 파일은 수정하지 않았다.

**P0 0건, P1 4건, P2 1건.** 관측의 GT 분리와 기본 OpenCV 경로, 번호 예약은 확인했지만,
실측 없는 실행 진입, 달성 불가능한 인수 시간, 하강 후 영상 기준, 상승 중 파지 상실 처리에
수정이 필요하다. 현재 SHA의 병합·학생 실행 인수 모두 승인하지 않는다.
무렌더 정지 자세 재현은 학생 운반 성공이나 v92 보정 완료가 아니다.

## 검토 기준과 범위

- `git fetch origin`부터 시작하고 AGENTS.md, README.md, docs/current_status.md,
  CONTRIBUTING.md를 읽었다. 종료 전 다시 fetch하고 후보 HEAD가 그대로임을 확인했다.
- [D1–D5](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204),
  [결정적 궤적의 held-out 중복 교훈](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966536405)을 gh API로 읽었다.
- 금지된 `/Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-*`는 읽지 않았다.
  시뮬레이터 렌더링 0, 모델 호출 0. 기존 프로세스를 종료·변경하지 않았다.
- 물리 검사는 원 후보 코드에 고정한 **3조건×52 SIM초**의 staged 명령 진단이다.
  자신의 `codex/review-363` 잠금을 취득·해제했고 시작/끝 부하 평균을 조건별 기록했다.
  렌더러·worker·자식 서버를 시작하지 않았다. 결과의 기하 가시성을 RGB 검출로 해석하지 않는다.

## 한 묶음의 수정 요청

### P1-1. 임의 보정 JSON으로 실행 관문이 열리고, 실제 D5 계약은 거부된다

위치: `harness/zone_pair_highpose_contract.py:67–77`, `scripts/run_pair_highpose.py:47–59,72–74`,
`configs/zone_pair_highpose_v93.json:7`.

`loaded_schedule_sha256`, `criterion_sha256`, `assembler_sha256`, 측정 manifest와 소스는
16진수 길이만 검사한다. 호출자가 준 파일 해시는 파일 자체와만 비교한다. 등록의
`runnable:false`는 확인하지만 `plan()`은 이를 실행 거부 조건으로 사용하지 않고
`runnable = not blocked`로 다시 계산한다.

**반례:** PR 자신의 `tests.test_zone_final_pair_highpose.synthetic()`를 만들고 그 파일 해시를
`--calibration/--calibration-sha256`에 주었다. 실제 측정 없이 출처가 `a×40`, manifest `b×64`,
일정 `c×64`, 기준 `d×64`, 조립기 `e×64`인 파일로 `plan.runnable=true`,
`bundle.runnable=false`가 동시에 나왔다. 직접 `run_case()` 호출도 보정 검사를 지나
출력을 만들고 backend 생성자에 도달했다. backend는 검토용 예외만 던지게 해 실제 물리를
실행하지 않았다. missing-file/NaN/legacy schema 거부 회귀의 통과로 이 반례는 막히지 않는다.

반대로 #361의 D5 출력은 `ugrp.final_environment_measured_calibration.v92`,
`loader_contract_version=2`와 `configs/calibration/zone_final_pair_v92_contract.json` 해시를 쓴다.
현재 학생 로더는 별도 v93 schema/hash를 요구하므로 그대로 받을 수 없다. #361의
`45e92085` 및 종료 시 `07c497410fb469b10f9899a1df9a1c742ac097ef`에서 이 계약은 같다.
그 로더는 일정·B″의 **실제 등록 해시**도 비교하고, 세 수집 소스도 요구한다.

요청: D5의 정확한 계약·검증기를 연결하고 고정된 일정/B″/조립기/완료 측정 증거와 대조한다.
연결 전에는 CLI와 직접 실행 진입점 모두 명시적으로 막는다. synthetic 허용은 test-only
경로로 한정한다. 정상 D5 산출물 수락, 임의 출처·PARTIAL·미승인 조립물 거부를 같은 회귀로 확인한다.
이 지적은 D5 보정이 이미 완료됐다는 주장이 아니다.

### P1-2. HIGH의 새 시간 비용으로 P03 120초 인수가 구조적으로 불가능하다

위치: `harness/zone_pair_highpose.py:19–29`, `harness/zone_pair_highpose_contract.py:113–123`,
`harness/zone_final_pair_contract.py:177–181`, `harness/zone_final_pair_skill.py:59–61`,
`scripts/run_m2_pair.py:561–569`.

한 HIGH 상승은 **17.2초**, 한 하강은 **13.6초**다. 기존 low lift 1.5초도 매번 남는다.
`zone_wide_door_geometry_v3`의 체크포인트 segment는 **1/3/7**이다. checkpoint receipt는
해당 segment까지 이전 leg를 실제 운반하고 lower/open 뒤 다시 HIGH로 올라가야 생긴다.

| P03 체크포인트 | segment n | HIGH 상승/하강만 `(n+1)×17.2+n×13.6` | low lift도 포함 | open/hover도 포함한 하한 |
|---|---:|---:|---:|---:|
| 문 앞 | 1 | 48.0초 | 51.0초 | 52.6초 |
| 문 뒤 | 3 | 109.6초 | 115.6초 | **120.4초** |
| 목적지 전 | 7 | **232.8초** | 244.8초 | **256.0초** |

마지막 열은 중간 checkpoint마다 `_wait_open()`의 0.4+0.5+0.6+0.1=1.6초만 더했다.
접근, 정렬, 닫기, base 이동, barrier, edge reference 획득은 모두 **0초로 친 하한**이다.
reset은 별도라 120초 예산을 늘리지 않는다. 따라서 최소한 문 뒤/목적지 전은 완벽한 센서와
물리에서도 인수 불가다. `carry`도 같은 120초 cap을 물려받는다.

요청: 고정 P03 3×120초 요구와 새 자세 일정의 충돌을 조정자에게 명시하고 인수 프로토콜을
재설계·고정한다. cap을 몰래 늘리거나 staged teleport로 P03를 대신하면 안 된다.
시간 하한 검사를 추가하고, 현실적인 이동/재관측 시간을 포함한 계획으로 다시 독립 검토한다.

### P1-3. 하강 뒤에도 HIGH hold anchor로 바닥 영상을 검사하여 release가 막힌다

위치: `harness/zone_pair_highpose_runtime.py:48–52,73–77`,
`scripts/study_owncam_pair_beam.py:362–376,441–450`, `scripts/run_m2_pair.py:561–569`.

상승 때는 자세가 달라져 anchor를 다시 잡지만, 하강 때는 `high_ready=false`만 설정한다.
상속된 `_lower()`는 바로 `wait_open`으로 가며, `_wait('open',...)`은 바닥 자기 RGB를
HIGH의 `anchor_full`과 IoU 비교한다. 실제 어댑터는 `fullframe_v3`를 선택한다
(`harness/zone_pair_executor.py:247–249`). HIGH 자세에서 유효한 기준이 바닥 자세에서도
유효하다는 보장은 없다. 이 문제는 중간 checkpoint의 재파지와 최종 release 양쪽에 적용된다.

**반례:** 서로 다른 화면 높이에 놓인 두 synthetic 빔 mask로 같은 자세 IoU=1.0을 확인한 뒤,
실제 `_lower/_wait_open/hold_state`를 실행했다. 하강 후 IoU=0.0으로 `ready=false`를 계속
발행하다 **`BARRIER_OPEN_TIMEOUT`**에 도달했다. 실제 렌더 프레임에 대한 실패율을 뜻하지
않지만, 자세 변화만으로 정상 release를 거부하는 제어 경로를 재현한다.

요청: 자세별로 근거가 있는 하강/바닥 grip·release 검사와 명시적인 anchor 수명 규칙을 둔다.
단순히 현재 화면을 무조건 정상 기준으로 덮어쓰지 말고, 정상 하강과 하강 중 slip을 모두
구별하는 end-to-end 상태 회귀를 추가한다. 기존 새 테스트는 lower 진입까지만 검사한다.

### P1-4. 상승 중 관측 공백 뒤 edge 존재만으로 파지 기준을 새로 승인한다

위치: `harness/zone_pair_highpose_runtime.py:36–56`, `harness/zone_pair_highpose.py:38–39`.

17.2초 상승/정착 동안 `_lift(..., arm_idle=False)`는 즉시 반환한다. 마지막에는 HIGH 명령
일치와 `edge_line != None`만 검사하고 현재 화면을 정상 hold anchor로 채택한다.
`at_high()`는 팔 PWM만 비교한다. 문서의 “transit grip/hold checks 유지”와 달리 새 상승
구간에 RGB load-loss 판정이 없다. 상태 heartbeat/partner abort와 정적 sweep guard는
파지 상실 검사가 아니다.

**반례와 범위:** 344회 busy 상승 호출의 `look()` 호출 수는 0이었다. low-lift 성공을
stand-in으로 놓고, 집게/공동 지지가 확인되지 않는 synthetic edge-only 영상을 실제
HIGH 검사에 주면 90열 검출→`high_ready=true`, `wait_carry`가 된다. 또한 무렌더 물리
진단에서 12초에 r2 집게를 열어 계속 열린 채로 두면 HIGH 유지 **0/136**인데도 30/32초의
기하 edge는 r1 **90열**, r2 **34열**이다. 가장자리 존재가 파지 유지와 동치가 아님을 보인다.
이 주입은 접촉 상실의 민감도 진단이며 자연 slip 빈도나 실제 RGB detector 통과를 측정한 것은 아니다.

요청: 자기 RGB·명령 이력으로 검증한 전이 중 파지/상대 동기화 감시와 실패 시 중단 경로를
넣고, HIGH anchor를 승인하기 전 held 관계를 검증한다. 접촉/GT를 학생에게 넣으면 안 된다.
정상, 한쪽 지연, 한쪽 grip loss를 raise/lower 양쪽에서 검사하고 준비/운반 신호의 오탐을 확인한다.

### P2-1. P03 반복은 동일 시작/seed이며 확증용 E2E 시작·궤적 분리가 등록되지 않았다

위치: `scripts/run_pair_highpose.py:43,93–95`, `scripts/run_final_pair_v3.py:64–80`,
`experiments/2026-10-03-pair-carry-highpose/README.md:51–72`.

세 P03 사례 모두 seed **911**, 동일 dock 배치, 동일 task/route/PF seed를 쓴다. 독립
`make_scene()`의 전체 config hash도 세 번 모두
`9e86ea3c82a26501fa3db377249de74a8e287cefa5f250a3b4b69ba9cc6fb75a`로 같았다.
checkpoint 이름은 사후 receipt를 고를 뿐 runtime 입력에 들어가지 않는다.
따라서 분모 3은 **체크포인트별 3회 실행**이지 독립된 새 출발 3개나 일반화 표본이 아니다.

이 PR에는 개발 시작/궤적 목록, 확증용 seed/start 목록과 중복 거부 규칙이 없다. 금지 raw는
읽지 않았으므로 과거 데이터와 실제 바이트 중복을 판정하지 않는다. #219의 교훈대로 E2E
확증 전 시작 pose/trajectory를 별도로 고정하고 개발 자료와 중복되지 않음을 평가자가 감사해야 한다.
seed 숫자나 지도 이름 변경만으로 충분하지 않다. 현재 P03를 기능 인수용 dev 재생으로
명시하고, 확증 성능의 표본으로 합산하지 않는다.

## 7개 요청의 판정과 전체 입력 추적

| 항목 | 확인 결과 |
|---|---|
| 1. 관측 경계 | 표준 v93 경로에서 실시간 pose/joints/contacts/성공값이 제어기로 들어가는 경로를 찾지 못했다. 아래 입력 표 참조. |
| 2. OpenCV | 기본 `Runtime → build_provider → HighPoseSource → OpenCVObserver` 확인. seg worker 생성이나 예외 시 학습망 fallback 없음. 실제 RGB 정확도는 미검증. |
| 3. 재사용 | 새 instance subclass/함수 binding으로 이전 v3/P03/beam tracker/가드 재사용. OpenCV는 10/3 결정의 별도 허용 변경. 카메라·FOV·외형·물리 파일은 diff에 없고 계약 해시 일치. 전이 로직에는 P1-3/4가 남는다. |
| 4. 게이트 | 기본 보정 없음은 output/backend 전에 차단. 그러나 synthetic 파일로 우회 가능(P1-1). 과거 성공 승계 필드는 false/null 유지. |
| 5. 번호 | main+열린 모든 PR 재조회. v93/3.5.0은 #363만 사용; #361 v92/3.4.0, #339 v86/3.0.0. 아래 SHA 표 참조. |
| 6. headless | 정상 HIGH/edge/목표 관절 제한 재현. 2초 상대 지연 및 한쪽 grip loss 추가 검사. 물리 진단과 학생 검증은 분리. |
| 7. 인수 계획 | staged→P03 순서, GT staging의 평가 분리, reset≤5초, 미도달 분모 유지, 실패/ENOSPC 보존은 타당. 시간 하한과 개발/확증 분리는 수정 필요(P1-2/P2-1). |

| 제어 입력 | 출처와 도착 경로 | 확인한 경계 |
|---|---|---|
| 자기 RGB·frame ID/hash·capture 시각 | `CameraRobotPort.capture:100–118` → `sim/final_pair_v3.py:capture` → `Runtime.on_frames` → `ZoneOwnExecutor`/HIGH detector | 자기 `robot_cam` JPEG만 반환. shared top·다른 로봇 RGB·초음파를 이 경로는 사용하지 않음. |
| 자기 발행 명령/초기 PWM | `backend.commands`와 `runtime.on_command` → own servo/ArmSequence/provider | `CameraRobotPort._actuator_state:268`은 명령 캐시. 실제 qpos나 actuator 측정값이 아님. HIGH 일치도 명령 상태이며 실제 도달 증명이 아님. |
| 공개 지도·고정 작업·역할 | `contract.resolve` → `task/make_plan`, static dock의 공통 영역 prior | 정확한 seeded robot→row를 주입하지 않음. 정적 주문서·beam pickup template·경로는 고정 task이며 현재 beam pose를 관측한 값이 아님. |
| 고정 보정 파일 | 명시한 파일/hash → motion/unloaded/fine/loaded·camera·pan·pair 모델 | 오프라인 eval-derived 보정 허용. loaded camera HIGH만 허용, transit에는 절대 위치 측정을 건너뜀. 실측 출처 검증은 P1-1 실패. |
| own command 예측/PF belief | `HighPoseSource` → P03 지연 wrapper → `PoseReport` → driver/guard | 0.16초 지연 및 동일 PF 유지. `pair_plan.partner`는 역할·공통 정적 leg에서 계산한 예정 명령이며 실시간 상대 pose/명령 측정이 아님. |
| SIM 시계·seed | runtime scheduler / CLI seed | 시각은 stamp/deadline/lease에 사용. seed는 PF RNG·장면 설정에 사용하고 GT state는 전달하지 않음. |
| 기존 고정 enum 상태 통신 | `zone_pair_status.FIELDS/STATES` → readiness/barrier/abort | 로봇·작업·seq·state·sent/observed 시각·frame ID·TTL만 전송. 상대 pose/joint/contact/image/free-text는 금지. 새 통신 필드 없음. 즉 센서 외 기존 동기화 신호도 받는다는 점을 명시한다. |
| 평가 전용 값 | physics owner의 `eval_sample`/camera labels/trajectory/contacts/setup → `eval_only/` | `eval_sample()` 반환값을 selector가 소비하지 않음. controller의 `eval_hook`은 no-op. checkpoint는 자기 상태 receipt의 사후 기록이고 `physical_success=None`. |

`vp.load_vis3()`는 고정 `vision_loc/vision_pf`와 OpenCV 기하 코드를 불러온다.
`seg_model.py`는 파일 무결성 검사 대상에는 남지만 import/모델 생성 대상은 아니다.
새 provider 생성·transit skip·black-frame 관측 검사는 torch/worker/network를 막은 fixture로 통과했다.
`provider_factory/worker`는 명시적 Python DI seam이며 CLI의 silent fallback이 아니다.

## 독립 검증 결과

후보 SHA를 checkout한 clean 검토 브랜치에서 기존 Mac `.venv-sim-worker-mac` 환경을 사용했다.

```text
python -m pytest -q tests/test_zone_final_pair_highpose.py tests/test_zone_final_pair_v3.py
  tests/test_zone_final_pair_review_fixes.py tests/test_zone_pair_v6e_yaw.py
  tests/test_vision_loc_provider_lifecycle.py
  -k 'not test_tracker_on_recorded_frames_matches_the_recorded_replay_rows'
138 passed, 1 deselected in 62.63s
```

제외 1개는 PR이 공개한 기존 v6e raw JPEG 의존 재생 검사다. 해당 실제 RGB 재생을 통과로
보고하지 않는다. 첫 시도는 잘못 추정한 테스트 파일명으로 수집 전 종료(0 tests)했고 로그를 보존했다.
synthetic release 반례의 첫 드라이버도 `version` fixture 누락으로 중단되어 별도 로그/폴더를
보존하고 수정본에서 재현했다. 구현 소스는 바꾸지 않았다. `git diff --check` 통과.
최종 gh 조회에서 후보 SHA의 CI **33개 SUCCESS**, PR OPEN이었다. CI 통과와 위 P1은 별개다.

| 52 SIM초 조건, 각 1,041표본 | 상승 [10,27.2) lifted/344 | HIGH [27.2,34) lifted/136 | 하강 [34,47.6) lifted/272 | HIGH 기하 열 r1/r2 | 상승/HIGH 최대 tilt |
|---|---:|---:|---:|---:|---:|
| 원 일정 독립 재현 | 344 | 136 | 257 | 90/90 | 0.04271° |
| r2 raise/lower 명령 2초 지연 | 344 | 136 | 258 | 90/90 | 1.67907° |
| 12초 r2 open, 이후 closed 명령 생략 | 42 | 0 | 0 | 90/34 | 11.46836° |

`lifted`는 빔 바닥≥10mm·네 집게 접촉·외부 지지 없음·weld OFF의 **사후** 판정이다.
하강 마지막 not_lifted는 정상 바닥 도달도 포함하므로 하강 성공률로 읽지 않는다.
grip-loss 상승 구간은 lifted 42 / missing_bilateral_grip 2 / not_lifted 300으로 전부 보존했다.
2초 지연 진단은 heartbeat 상실이나 학생의 대응까지 검사하지 않는다.

정상 재현은 PR의 849 lifted / 192 not_lifted, HIGH 바닥 최소 114.849253mm,
low 양쪽 0열/HIGH 양쪽 90열, 발행 1,948명령과 일치했다. 목표 관절 2,352개 제한 위반 0.
실제 qpos도 별도 검사해 세 조건의 arm yaw/shoulder/elbow/wrist 범위 이탈 0을 확인했다.
집게 slide의 수치적 최대 이탈은 4.14e-8m 미만이며 목표 제한 위반과 구분한다.
모든 조건 weld OFF, renderer/model 0. 총 156 SIM초 + 세 reset, E2E 수행 0이다.

## 번호·출처·기록

첫 구조화 재조회는 main `89ea80d5`와 열린 PR 9개(신규 #364 포함)의 configs 전체 JSON 및
`harness/rgb_execution_bundle.py`를 읽었다. 이후 fetch 뒤 main `9bc348a8`와 열린 PR 8개를
다시 grep하여 v93/3.5.0이 #363에만 있음을 확인했다(#358은 그 사이 병합됨).

| 최종 ref | SHA |
|---|---|
| main | `9bc348a8708a997bd950f073c4aa8320d984a88c` |
| #364 | `5b61d5b21f0107ed38a9d404ad2c2c877a42469b` |
| #363 | `081f18d86b61322c94ede8c926936b5471052596` |
| #361 | `07c497410fb469b10f9899a1df9a1c742ac097ef` |
| #359 | `f2fc0cc3d2315e8b4441028a1713a1ba5af23175` |
| #353 | `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f` |
| #339 | `9912bb15bb492bab0f9278fc493feed1547ff8ee` |
| #309 | `c8379bbe16492687af9d7b2d04f85e4ae4c610cc` |
| #293 | `d86cc82eedbe0c6693eaf808c54ce43387723f1d` |

로컬 원본: `/Users/changmin/projects/ugrp/outputs/review-363-20261003/`.
`headless_review.py`, 조건별 `commands.json/bundle.json/scene.xml/eval_only/` 및
`artifacts.sha256.json`, 세 `*_summary.json`, `actual_joint_and_tilt.json`,
`offline_review.py/offline_counterexamples.json/edge_only_counterexample.json`,
pytest 로그/JUnit, 번호 재조회와 최종 CI JSON을 보존했다. raw 원격 백업은 하지 않았다.
검토용 headless 드라이버는 후보의 `probe_headless.py` 함수와 원 명령 배열을 그대로 호출하고,
두 실패 조건만 사전 고정 명령 배열에서 변경했다. 루프 안 GT 보정은 없다.

| 로컬 증거 manifest | SHA-256 |
|---|---|
| `review_evidence.sha256.json` (검토 드라이버·반례·요약·검증 로그) | `c7c6b235851a645d863f96ab0667949d033ef6efb5b6486b5496feda66f5ec75` |
| `nominal/artifacts.sha256.json` | `b229fda0bc2a351d6f11e60cdd0999ea5ba672ca76c51b5babeef79bf3403fc6` |
| `partner_delay_2s/artifacts.sha256.json` | `136c22ae308e6b6549ebe77c6244f2df5c59e7947c379bad75af61aa61ab5ae0` |
| `raise_grip_loss/artifacts.sha256.json` | `777ce333a8219b03260619b49d63e1d1f67e40dd738f5a32c0c68d4848f4705b` |

TensorBoard 새 snapshot `1003-pair-highpose-review363/{nominal,partner_delay_2s,raise_grip_loss}`를
기존 공유 viewing root에 추가했다. 원 snapshot은 유지하고 새 영상 등록은 0이다.
27개 scalar를 EventAccumulator와 기존 서버 API 양쪽에서 대조했다. Chrome 강의 기존 탭에서
기준 실행까지 네 run, edge 90/90/34/90, HIGH 표본 136/136/0/136을 확인했다.
HParams 네 열(outcome/wall_s/commands/model_calls)을 재적용했다. 개별 새 HParams 행 및
나머지 카드의 UI 전수 확인은 하지 않았으며, 미측정 wall/model 응답 시간을 만들지 않았다.
대시보드 고정 링크는 `tensorboard_review.json`과 공유 view의 `pair_highpose_review363_20261003`에 있다.
[TensorBoard 비교](http://127.0.0.1:6006/?runFilter=%5E1003-pair-highpose-%28review363%2F%7Cv93%2Fhigh-hold%24%29&scalarSmoothing=0#timeseries).
서버의 공유 logdir는 API로 확인했고 기존 서버 프로세스에는 손대지 않았다.

## 재검토 조건

P1 네 항목을 같은 수정 묶음으로 해결한 새 SHA가 필요하다. D5의 정확한 실측 계약 연결과
실행 전 차단, 가능한 P03 시간/경로 계획, 자세별 hold/release, 전이 중 slip/desync 거부를
우선 검증한다. 이후 OpenCV 실제 RGB stage 인수→수정·고정된 P03→별도 start/trajectory를
가진 E2E 순서로 진행한다. 이번 BLOCK은 과거 후보 성능이나 실물 결과를 판정하지 않는다.
