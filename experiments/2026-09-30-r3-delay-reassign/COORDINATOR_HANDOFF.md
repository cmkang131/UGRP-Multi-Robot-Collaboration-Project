# T12 코디네이터 인계 — 최소 물리 진단 2 × 900 SIM초

**이 문서는 실행 결과가 아니다.** 이 worktree에서는 물리·렌더·모델을 실행하지 않았다. T07/P01/P03/T08b 등의 합성·고정이 끝나기 전에는 아래 두 셀을 시작하지 않는다. 본연구 DRAFT·seed·성공 기준과 원본 s1–s6를 수정하지 않는다.

## 1. 소스·입력 고정

- T07 #323의 `1a17829e` 역할→로봇 mapping과 PairTeam/상태/명령 routing을 의존 소스로 연결했다. `RoleAwareOwnPairPort.submit(request)`는 명시된 actor·partner·role 그대로 자기 `pair_carry`를 호출하고 ack의 order/zone/role을 검사한다. 상대 요청은 생성하지 않는다. 코디네이터 합성 시 이 의존 SHA와 T12 최종 SHA를 고정하고 독립 검토/필수 CI를 확인한다.
- recovery를 로봇별 study/policy 경계에 연결한다. `submit/replace/cancel/poll`은 자기 SIM clock에서만 호출하고, low-level 제어보다 앞선 안전 순서에서 poll/cancel 결과를 처리한다. `poll`의 `active`는 **양측 제출 참여**이며 집결/파지/배송 성공이 아니다. 실제 접근 ready/GO는 기존 M2 상태 채널을 유지한다.
- 공개 역할 요청에 대한 원인(공개 주문/자기 RGB·기억/자기 명령/허용 inbox)을 각 actor 기록에 남긴다. r3 hold 예정 여부로 상대를 선택하거나 52초에 맞춘 재요청을 host가 예약하지 않는다. 미래 event 시각, GT placement/holder/referee, P09 feasibility/inventory 경로는 제어 입력 금지다.
- P01 최종 지도·P03 최종 모델/provider/카메라/보정·T08b 원본 남북 빔 접근이 미지원이면 **UNSUPPORTED/NOT_RUN**으로 남긴다. 기존 make_plan이 받는 수평 dev 빔이나 teacher staging으로 원본 지원을 대신하지 않는다. 이번 모듈에는 새 executable workflow나 봉인 ID가 없다. 합성한 실행 경로를 기존 `zone-study-integration-run` 관리 계층의 새 버전/번들로 고정해야 한다.
- source commit, 실제 runtime source closure/hash, recovery 모듈 hash, 역할 mapping/hash, 지도·공개 주문·정적 coarse sheet·실제 setup manifest의 각각의 hash, final 3D 모델·카메라·provider/센서/자기 기억 버전을 기록한다. setup item identity는 장면/평가 전용이다. 네 조건별 controller/config override는 금지한다. leader와 pair role은 별도 열로 남긴다.
- 원본 `s3_late_rendezvous_v2`는 `r3_hold_late`, trigger=12.0, robot=r3, duration=40.0을 보존한다. `HiddenEventPhysics` 실제 적용시간과 until(실제 적용시간+40)은 별도 평가 로그에 기록한다. 정상 대조는 **별도 dev fixture**에 사건만 비활성화하고 그 변경을 manifest에 명시한다. 원본을 덮어쓰거나 hold 시간을 접근 시간에 맞춰 옮기지 않는다.

## 2. 셀과 예산

| 셀 | 공통 입력과 유일 차이 | 종료/실패 판정 | cap |
|---|---|---|---:|
| N: 정상 집결 1회 | final v3, walls_v3 0.40m, 표식0, cargo_noslip_v1, weld OFF. 같은 seed/실제 spawn·공개 주문/빔 배치·역할·controller. dev event 없음 | 실제 spawn부터 양쪽 접근→own RGB 준비→같은 GO→후속 진행을 확인. 자기 claim만으로 통과하지 않음 | 900초 |
| H: r3 hold 1회 | N과 같은 설정. 원본 r3 event 12초/40초만 적용 | 실제 바퀴 억제, own 인지, partner 대기, 종료 뒤 재개 또는 명시적 취소/재요청을 각각 판정 | 900초 |

**합계 1,800 SIM초**는 후보 하나의 최소 진단 제안이다. 각 셀의 reset/안정화/팔 staging/접근/대기/취소/재요청/종료를 모두 cap에 넣는다. cap 도달은 실패/미도달이며 실행 시간을 초기화하거나 같은 결과 폴더로 재실행하지 않는다. 디스크 부족 ENOSPC는 HOST_ERROR로 남긴다.

권고 고정안은 두 셀 모두 `leader_ko`, 원본 후보 seed **623**(leader=r3), 역할 `end_neg=r1`, `end_pos=r3`다. leader=r3인 경우도 운반에서 제외하지 않는다. 실제 role 선택은 양쪽 로봇의 같은 공개 요청/허용 통신으로 재현하며 host 배정으로 바꾸지 않는다. 원본 주문 4행·물건 4개를 장면에서 숨기지 않는다. T12 관찰 범위는 focal pair의 집결/재개이며 다른 세 단독 주문을 완료 처리하지 않는다. 전체 s3 수행은 별도 작업이다.

위 고정안의 실제 접근이 event 구간과 겹치지 않으면 **짝 지연 미성립**으로 기록한다. 사후 seed·spawn·event 조정으로 성공 셀을 만들지 않는다. r3가 solo인 실행은 solo 지연으로만 기록하고 pair-delay 분모에 넣지 않는다. end_neg=r3와 leader=r1/r2 및 4조건 전체 비교는 T07/C6/C7 또는 추가로 승인된 확대 셀에 남긴다. 이 2셀을 역할 6종·4조건·3 leader 검증으로 복제하지 않는다.

## 3. 실행 직전/직후 명령 경계

코디네이터는 합성한 새 사전 기록/번들/episode 경로를 먼저 확정한다. 현재 원본 실행기에는 이 opt-in recovery와 T07/P01/P03이 자동 연결되어 있지 않으므로 **지금 실행할 수 있는 완성 명령이라고 주장하지 않는다.** 다음 명령은 준비 확인이다.

```sh
python3 scripts/disk_report.py
python3 scripts/agent_lock.py status
bash scripts/open_simulation.command workflow plan zone-study-integration-run -- \
  --prereg "$t12_prereg" --episode "$t12_episode" --condition leader_ko \
  --expected-source-sha "$t12_source_sha" --output "$t12_new_output"
```

`t12_prereg`는 horizon=900, 원본 seed/명세와 별도 dev ID, 정확한 source/bundle을 고정한 새 문서다. `t12_new_output`은 primary `/Users/changmin/projects/ugrp/outputs/` 아래 **기존에 없는 셀별 경로**다. `--dev-horizon-s`로 봉인/source 검사를 우회하지 않는다. `--llm`을 붙이지 않는다(새 모델 호출 예산 없음). 모델 없는 actor도 자기 입력에 따른 재요청 정책을 명시하고 event 시각을 script로 알고 행동하면 실패다.

실제 실행 드라이버 PID로 다음 공용 잠금을 획득한 뒤, 세션 관리 아래 같은 plan 인자의 `workflow run`을 실행한다. PID는 shell/종료된 임시 프로세스가 아닌 실행 수명을 소유한 드라이버여야 한다.

```sh
python3 scripts/agent_lock.py acquire --owner codex --branch "$t12_branch" \
  --purpose 'T12 N/H physical acceptance; max 2x900 SIM seconds' \
  --pid "$t12_driver_pid" --expected-minutes "$t12_wall_budget_minutes"
```

처리량을 재지 않아 wall minutes를 SIM초에서 추정하지 않았다. 코디네이터가 유한한 wall 예산을 정한다. 완료/실패 후 자신이 시작한 세션·자식의 종료와 raw 회수를 확인한 뒤에만 `python3 scripts/agent_lock.py release --owner codex`로 자기 잠금을 반환한다. 다른 작업의 잠금/프로세스는 건드리지 않는다.

## 4. 각 셀에서 대조할 실제 증거

1. **입력 경계:** robot payload/원본 요청 이미지·텍스트에 hidden event/실시간 정답·접촉·심판·상대 private state가 없는지 검사한다. 같은 자기 입력과 허용 wire를 유지한 private 변경의 fake 비간섭 결과를 함께 연결한다.
2. **실제 hold:** `[12,52]` 예정 구간, 실제 적용/해제시간, 발행 wheel commands, actuator override, 측정 wheel joint motion과 base 이동을 평가 전용으로 분리 저장한다. `effect=wheels_held`나 명령0만으로 실제 정지라고 하지 않는다. 움직임/미끄러짐·외력 유무를 원본 시계열과 영상에서 확인하고 미측정이면 unknown으로 남긴다.
3. **자기 인지:** r3의 첫 fresh own RGB/기억·발행명령에서 진전 없음/불확실성을 판정한 시각과 이유를 기록한다. 실제 fault 시각을 인지 시각으로 복사하지 않는다. partner는 자기 대기 시작/끝, 허용 readiness/heartbeat/abort, 실제 소비한 메시지만 근거로 남긴다.
4. **정상/재개:** 제출 ack, 접근 시작/도착은 분리한다. 양쪽 own readiness의 frame/hash·시각·TTL과 동일 GO 소비, 실제 다음 움직임을 확인한다. 52초 뒤에도 증거가 없으면 자동 ready로 바꾸지 않는다. 이미 집계된 과거 job/channel의 readiness로 GO가 나면 실패다.
5. **취소/재배정:** 선택한 경우 caller의 사유·요청, old job/channel, abort enum, 양쪽 host macro queue·arm events·controller schedule·buffered commands 삭제를 기록한다. 취소 시 hold를 제외한 old job 명령 발행 수는 **0**이어야 한다. 같은 옛 job ID 취소가 새 job을 지우지 않는지 확인한다. 재배정 상대는 actor가 고른 요청에만 따라야 한다. 이미 파지 가능성이 있으면 holding=unknown의 안전 거절/관측을 보존한다.
6. **분모:** 할당2/실행/완료/실패/HOST_ERROR/UNSUPPORTED/짝 지연 실제 성립 수를 각각 기록한다. r3가 pair 멤버가 아니거나 event 때 partner 대기가 없으면 짝 지연 성립으로 세지 않는다. 성공률 분모에서 cap 실패·미도달을 빼지 않는다. 40초는 주입량이며 makespan 증가 40초의 확정치가 아니다. N/H의 staging 포함 makespan 차이는 실제 측정 후 보고한다.

## 5. P06/TensorBoard 완료 조건

각 셀의 원본은 primary outputs에 보존한다. source/input/role hash, 사용한 observation·command·status·request/job/channel ID, 실제 종료와 실패 이유, 영상, 모든 source hash를 P06 raw manifest에 연결한다. API sequence_done, rendezvous 통과, 실제 운반/정식 주문 완료는 서로 다른 지표다. 확인하지 않은 배송 성공률은 null/미측정으로 둔다.

완료·회수한 N/H 및 실패를 **새** TensorBoard snapshot으로 변환한다. 기존 snapshot/source manifest의 경로·hash를 대조해 중복 변환하지 않는다. EventAccumulator readback으로 원본값/분모를 확인하고 primary `outputs/tensorboard`를 보는 서버의 PID·logdir·소유권을 확인한다. `outputs/tensorboard-view.json`을 쓰기 직전에 다시 읽고 자기 새 run 키만 추가한다. 영상 등록, pinned success/runtime/commands/model-calls/response-time(없는 값은 만들어 넣지 않음), 관련 baseline, HParams의 condition/leader/role/source를 확인한다. 실제 dashboard/영상 링크와 화면 표시 검증까지 보고해야 물리 결과 전달 완료다. 미실행/미회수 자료를 완료로 표시하지 않는다.
