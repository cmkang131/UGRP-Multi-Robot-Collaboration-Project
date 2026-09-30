# T13 최종 환경 인계 — zone-target-v86 / 2.19.0

**PR #338 의존, draft. 현재 실행 차단(`runnable=false`), 물리 미실행.**

#338의 `zone-final-environment-v84`에서 최종 MasterPi v3 + geometry_v3,
walls_v3 0.40 m, 표식0, default render, cargo_noslip_v1, weld OFF, 센서 OFF를
가져온다. 원본 s5 주문·물건 배치·30초 이동/62.5초 낙하 사건과 공개 시각 catalogue는
보존한다. 과거 v85 번들은 원본 그대로 남겨 두며 현재 실행용으로 사용하지 않는다.

다음 두 조건이 해결되기 전에는 조정자도 T13 실행을 시작하지 않는다.

1. v84 계약과 일치하는 v3 카메라·unloaded/loaded/fine 동작 측정 보정 및 출처·해시.
2. v3 표적 RGB projection/held 판단·조작 skill·host 연결의 별도 이관과 검증.
   현재 target backend는 v2 기하를 사용하므로 v3 입력을 명시 거절한다.
   `visual_arm_v3` 파일의 존재나 v3 pose provider만으로 이 조건을 충족하지 않는다.

이 작업에서 측정값을 만들거나 v2 보정을 승계하지 않았다. 이관 후 새 소스·번들을
등록하고 알려진 작은 사례의 물리 인수부터 진행해야 한다. 아래 셀별 판정과 예산은
미래 인수의 계약이며 현재 실행 승인이 아니다. T13a 2×900=1800초,
T13b 4×900=3600초의 기존 상한은 늘리지 않는다.

## 실행 없는 확인

```sh
cd /Users/changmin/projects/ugrp-wt/integ-target-backend
T13_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$T13_PY" -m scripts.run_zone_target_checks --group t13a --condition no_comm
"$T13_PY" -m scripts.run_zone_target_checks --group t13b --condition no_comm
"$T13_PY" -m scripts.sim_cli workflow plan zone-target-checks --input configs/t13_target_checks.json --input config/rgb_execution_bundles/zone-target-v86.json -- --group t13a --condition no_comm
```

두 runner plan에는 `runnable=false`와 두 `blocked_on` 항목이 나온다.
표준 workflow plan의 `execution_started=false`는 명령 계획만 확인한 것이며
물리 실행 가능/성공을 뜻하지 않는다. `--execute`와 직접 `execute_cell`도 출력 생성,
호스트 잠금, worker/World 생성 전에 `T13_FINAL_ENVIRONMENT_NOT_READY`로 거부한다.

## 셀별 판정

| 셀 | 고정 actor | 기대 효과/확인 사항 | 상한 |
|---|---|---|---:|
| I1 | r1, order-1, 0.5초 시작 | 유일한 공개 cyan cue로 specific 선택, 추적 상실 후 cancel·새 프레임 재식별·새 job. 실제 이동/재탐색/파지/정확 A 배송을 분리 | 900초 |
| I2 | I1과 같음, cyan2개 | public cue ambiguous → unknown/유한 재관측/실패. 잘못된 specific 제출/거짓 claim 0. 실제 교환 성립 여부 별도 | 900초 |
| M-U | r1, order-1, 70초 시작 | 30초 item_moved. own RGB 재발견·specific 선택·A 배송. clear-empty absence 미구현을 별도 기록 | 900초 |
| M-H | r1, order-1, 0.5초 시작 | 30초 none_item_held를 기대하되 실제 holder로 분기 판정. H 미성립은 실패/미성립으로 보존 | 900초 |
| D-H | r2, order-2, 0.5초 시작 | 62.5초 red_1 gripper_fault_open 기대. 실제 낙하와 fault를 분리하고 own RGB held→unheld/resting 시 refresh 전 cancel, 새 프레임 후 재시도 | 900초 |
| D-U | r2, order-2, 70초 시작 | 62.5초 none_item_not_held. 강제 open/이동, GT 기반 실패 통보 0 | 900초 |

원본 사건은 모든 셀에서30초/62.5초 그대로다. 사건 truth는 setup/평가 전용이다. 실행 중
평가가 학생 행동·종료·재시도를 선택하지 않는다. `result.json`은 고정 horizon의 `CAP`,
`physical_success=null`을 기록하며 성공/복구 판정은 저장 증거의 후처리로만 한다.
셋업/접촉 mismatch, 모델/호스트/수집 오류는 성공으로 바꾸지 않는다. ENOSPC는 HOST_ERROR다.

## 증거·수집 완료 조건

1. group `manifest.json`, 셀별 `inputs.json`, `own_frames/`, `target_inputs/`, 각 로봇의
   `commands/frames/perception/target_jobs/cancellations/decisions/provider/lower_jobs`를 보존한다.
   raw hash→detection→token→job→own open→claim 연결을 대조한다. cancel 뒤 해당 job의
   예약 arm/base 명령 잔류0, peer 명령 불변, raw와 target PNG 구분을 확인한다.
2. `eval_only/setup.json`, `truth.jsonl`, `hidden_events.jsonl`, `host.json`, `referee.json`에서
   actual holder·접촉·물체 pose·속도와 사건 effect/no-op를 확인한다. 이 입력은 controller에
   전달하지 않는다. own claim과 exact item 도착을 대조하고 거짓 identity/count를 센다.
3. 할당2/4, 실행·미실행, 실제 이동·실제 낙하·no-op·branch_not_established,
   발견·재파지·정확배송·자기 올바른 claim·거짓 claim·cap/오류를 각각 기록한다.
   실제 효과가 없는 셀은 복구율 분모에 넣지 않되 할당에는 남긴다. 분모0은 None,
   판정 누락은 incomplete다. 결과를 기존 성공/최종 v3/E2E/4조건 효과로 합산하지 않는다.
4. 각 셀 `artifacts.sha256.json`과 파일을 대조한다. SIGINT/디스크 오류 등으로 회수가
   끊기면 없는 결과를 완료로 표시하지 않는다. 재시도는 새 후보/예산/경로로 결정한다.
5. 실제 결과가 회수된 뒤 `docs/tensorboard.md`에 따라 native TensorBoard 새 snapshot에
   실패도 추가한다. source/hash 중복검사, event 실제 readback, raw 영상 변환/등록,
   값·pin/HParams를 대조하고 dashboard URL·미변환/미표시를 기록한다. 현재 snapshot 없음.
   자신이 시작한 session/자식만 정리하고 잠금 반환을 확인한다.
