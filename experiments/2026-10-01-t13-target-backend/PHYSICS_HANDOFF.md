# 조정자 실행 인계 — zone-target-v85

등록 workflow는 `zone-target-checks` **2.18.0**이다.

**오프라인 구현만 검증했다. 물리 미실행이며 최종 v3 인수 완료가 아니다.**
이 후보는 MasterPi v2 + geometry_v2 + vision_zero_tag_v2의 개발 진단이다.
#320/#329의 최종 MasterPi v3/walls_v3(0.40 m) 요구는 별도 이관·인수 전까지 미충족이다.
RGB 기반 전체 pickup region의 clear-empty 판정도 미구현이므로 M-U의 absence 항목은
unknown/미지원으로 남긴다. 이 제한을 해소했다고 보고하지 않는다.

## 고정 조건

- `configs/t13_target_checks.json`의 seed641, 원본 s5의 cyan/red/red/can 배치와 두 사건을 쓴다.
  I2만 공개 catalogue와 setup에 두 번째 cyan을 추가하고 30초에 반대 이동을 시도한다.
- 표식0, 원래 카메라/FOV, 640×480 own RGB, floor_light_v1, cargo_noslip_v1, weld OFF,
  센서 OFF. raw full JPEG는 pose/인식에, target-only PNG는 skill에 사용한다.
- no_comm 고정 actor, LLM 호출0. H는 사건 전 파지를 **시도**하며 GT staging이 없다.
  H 불성립은 `branch_not_established`. U의 시작은70초다. 이벤트 시각을 변경하거나
  재실행으로 실패를 대체하지 않는다. 다른 통신 조건의 결과로 복제하지 않는다.
- 모든 셀은 setup/settling/관측/이동/대기/복구를 포함해900 SIM초에서 끝난다.
  T13a 할당2/총1800초, T13b 할당4/총3600초. 아래 두 group은 각각 한 번만 실행한다.
  셀별 `--cell`은 조정자가 기존 할당에서 한 셀을 분리할 때만 쓰며 추가 반복 예산이 아니다.

## 실행 전

후보 PR의 **검증한 커밋**을 자기 worktree에 둔다. `git status --porcelain`이 빈 결과인지,
선택 SHA와 번들 검사가 일치하는지 확인한다. source를 고친 경우 새 후보/새 번들을 정한다.
`python3 scripts/agent_lock.py status`로 공용 잠금을 먼저 확인하고 기존 소유 작업을 중지하지
않는다. 실행기는 잠금을 직접 acquire/release하므로 바깥에서 중복 acquire하지 않는다.
10 GiB 이상 여유 공간이 필요하며 load average와 환경을 manifest에 기록한다.

아래 변수의 SHA를 PR의 검증 SHA와 대조한다. `date` suffix는 새 경로를 만드는 용도이며
실패 결과를 덮어쓰지 않는다. 모델 파일은 `configs/vision_loc_worker.json`의 체크포인트
SHA와 실행 Python을 사용한다. 모델 파일/환경 누락은 사전 차단으로 기록한다.

```sh
cd /Users/changmin/projects/ugrp-wt/integ-target-backend
T13_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
T13_SOURCE_SHA="$(git rev-parse HEAD)"
T13_RUN_STAMP="$(date +%Y%m%dT%H%M%S)"
T13_OUT="/Users/changmin/projects/ugrp/outputs/t13-target-v85-${T13_SOURCE_SHA}-${T13_RUN_STAMP}"
"$T13_PY" -m scripts.run_zone_target_checks --group t13a --condition no_comm
"$T13_PY" -m scripts.run_zone_target_checks --group t13b --condition no_comm
"$T13_PY" -m scripts.sim_cli workflow plan zone-target-checks --input configs/t13_target_checks.json --input config/rgb_execution_bundles/zone-target-v85.json -- --group t13a --condition no_comm --execute --expected-source-sha "$T13_SOURCE_SHA" --output "$T13_OUT/t13a"
"$T13_PY" -m scripts.sim_cli workflow plan zone-target-checks --input configs/t13_target_checks.json --input config/rgb_execution_bundles/zone-target-v85.json -- --group t13b --condition no_comm --execute --expected-source-sha "$T13_SOURCE_SHA" --output "$T13_OUT/t13b"
```

위 plan은 물리를 실행하지 않는다. 실제 실행은 다음 두 명령이다(`--lock-owner claude`는
실행 조정자의 소유명이며 다른 주체가 실행하면 자기 소유명으로 바꾼다).

```sh
"$T13_PY" scripts/ugrp_session.py run t13a-target-v85 -- "$T13_PY" -m scripts.sim_cli workflow run zone-target-checks --record "$T13_OUT/managed-t13a" --input configs/t13_target_checks.json --input config/rgb_execution_bundles/zone-target-v85.json -- --group t13a --condition no_comm --execute --expected-source-sha "$T13_SOURCE_SHA" --lock-owner claude --output "$T13_OUT/t13a"
"$T13_PY" scripts/ugrp_session.py run t13b-target-v85 -- "$T13_PY" -m scripts.sim_cli workflow run zone-target-checks --record "$T13_OUT/managed-t13b" --input configs/t13_target_checks.json --input config/rgb_execution_bundles/zone-target-v85.json -- --group t13b --condition no_comm --execute --expected-source-sha "$T13_SOURCE_SHA" --lock-owner claude --output "$T13_OUT/t13b"
```

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
