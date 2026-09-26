# 자기 카메라 로봇별 실행기 API (패키지 F)

한국어 대화 연구의 LLM 층(또는 no-LLM 스크립트)이 로봇 한 대에 작업을 맡기는 다리다.

| 파일 | 역할 |
|---|---|
| `harness/zone_own_executor.py` | 작업 API·사건·작업 수명 (`ZoneOwnExecutor`) |
| `harness/zone_own_guards.py` | 자기 입력 안전장치: 위치 불확실도 게이트, 둘러보기 충돌 검사, 진행 감시·제한된 복구, 위치별 막힘 누적, `GuardedDriver` |
| `harness/zone_own_deliver.py` | M1 배송 사슬 어댑터 (`_DeliverController`) |
| `harness/zone_own_status.py` | 자기 카메라 판단·`status()`·`belief_projection()` |
| `harness/zone_own_contract.py` | 지도 어휘와 패키지 A/D 어댑터(main의 계약 모듈을 import) |
| `harness/zone_own_team_host.py` | 3대 물리 소유자 `OwnCamTeamHost`(시뮬레이터는 여기서만 import) |

테스트는 `tests/test_zone_own_executor*.py` 네 파일이고 모두 `scripts/run_ci_tests.py`에 수집된다. 스모크 기록은 [`experiments/2026-09-26-zone-own-executor/`](../experiments/2026-09-26-zone-own-executor/README.md)에 있다.

**재사용.** PR #201(M1 제어기·위치 추정·계약, 스킬 v9 `04a5e3c` 포함)과 PR #193(자기 RGB 판단)의 파일은 읽기 전용으로 쓴다. 패키지 A/D 계약(`harness/zone_study_contract.py`, `harness/zone_event_scheduler.py`, `harness/zone_map_schematic.py`)은 main에서 import하며 복사하지 않는다.

## 입력 경계

실행기가 받는 것은 다음뿐이다.
- 자기 `robot_cam` 관측(JPEG, 자기 발행 PWM)과 자기 발행 명령 이력
- 정적 태그 지도와 고정 교정값(카메라·운동, 자기 몸체 모델 `body_model_calibration.json`)
- 정적 배치 keep-out(대기 spawn 원판)
- 시나리오 설정에서 만든 주문서: 종류·수량·목적 구역·개략 pickup 슬롯 `P{열}-{행}`. 좌표는 거부한다.

실행기는 시뮬레이터를 import하지 않는다. world·포트·다른 로봇·호스트 참조도 없다. 다른 로봇의 관측, `nav_cam`, 오래된 프레임, 해시가 맞지 않는 프레임은 거부한다. 실행기에는 연구 조건 인자가 없으므로 모든 조건에서 같게 동작한다.

## 작업 API

| 호출 | 동작 | 끝 사건 |
|---|---|---|
| `deliver(item_ref, zone_slot)` | 주문 줄 하나를 구역 슬롯(`A2`)이나 구역(`A`: 자기 기록상 다음 슬롯)으로 옮긴다. 먼저 넓게 둘러본 뒤 M1 사슬을 따른다(자기 RGB 탐색 → 파지 → 문 통과 운반 → 배치 → 다시 보기). 탐색은 주문 pickup 슬롯(+0.15 m) 안의 청록만 쓴다. 먼 bay(P2)는 통로 관측점을 더한다. 탐색 프레임에서 청록이 어안 테두리 아래에 잘리면(너무 가까움) 관측점마다 한 번 물러나 다시 본다 | 다시 보기 IN_SLOT이고 게이트 ok → `job_done(own_camera_confirmed)`; 확인 불가 → `job_done(unconfirmed)`; 그 밖 → `job_failed(reason)` |
| `goto(target)` | `[x, y]`, 구역 `A`, 구역 슬롯 `A2`, pickup 슬롯 `P1-2`, 문 `door_1`. `GuardedDriver`(loop driver v2 + 안전장치) | 게이트 ok와 5 s 안의 고정된 자기 둘러보기가 있어야 `ARRIVED`(confirmed). 아니면 `GOTO_arrival_unconfirmed`·`GOTO_pose_uncertain`·`GOTO_lost`·`GOTO_blocked`·`GOTO_no_path` |
| `look_around()` | LOOK_P20 둘러보기. pan은 충돌 없는 구간만, 필요하면 먼저 물러난다 | 게이트 ok이고 둘러보기 중 태그를 봤으면 confirmed, 아니면 unconfirmed |
| `hold(sim_s)` / `wait(sim_s)` | 0–3600 SIM s 멈춤 | `job_done(unconfirmed, HOLD_ELAPSED)` |
| `abort(reason_code)` | 현재 작업 취소. 호스트가 예약 명령을 버리고 즉시 hold한다 | `job_failed('ABORTED:<reason>')` |
| `status()` | 자기 상태와 자기 카메라 판단만 | — |

작업은 한 번에 하나다. 바쁠 때의 호출, 모르는 주문·목적지 불일치·청록 외 종류, 잘못된 인자(`[]`, `None`, NaN/Inf, bool, 빈 문자열, 범위 밖 시간)는 예외 없이 `command_rejected`로 거부한다. 제어기 예외로 멈춘 로봇은 이후 모든 호출을 `ROBOT_STOPPED`로, 에피소드가 끝난 뒤의 호출은 `EPISODE_ENDED`로 거부한다.

## 한 가지 취소 경로 (호스트)

다음 네 경우 모두 (1) 그 로봇의 예약된 macro 명령을 버리고, (2) 즉시 hold하고, (3) 작업을 종료 사건 정확히 1회로 끝낸다.

| 원인 | 사건 |
|---|---|
| 승인된 `abort` | `job_failed('ABORTED:…')` |
| 작업 SIM 한도(기본 720 s). macro 실행 중에도 검사하며, 한도 시각을 호스트의 다음 깨움 시각에 넣는다 | `job_failed('LOCAL_TIMEOUT')`, D trigger `timeout` |
| 에피소드 끝(SIM 한도·연구 층 종료·전원 정지) | `job_failed('EPISODE_END:<outcome>')`, D trigger `timeout` |
| 제어기 예외 | `job_failed('EXCEPTION:<type>')`, 로봇 영구 정지 |

## 안전장치 (`zone_own_guards.py`)

- **위치 불확실도 게이트.** 자기 PoseReport σ에 두 임계와 머묾 시간을 둔 Schmitt trigger다.
  - 빈손: HIGH σxy 0.08 m·σyaw 0.10 rad(M1 `nav_unloaded`), LOW 0.05 m·0.06 rad.
  - 짐: HIGH 0.07 m·3°(M1 `nav_loaded`), LOW 0.06 m·2.5°.
  - HIGH 초과가 0.6 s 이어지면 `uncertain`, LOW 이하가 0.4 s 이어지면 `ok`. 초기값은 `uncertain`.
  - `uncertain`이면 주행하지 않고(둘러보기만, 연속 3회 실패 시 `pose_uncertain`으로 끝), 어떤 작업도 `own_camera_confirmed`를 내지 않는다.
  - `pose_uncertain` 사건은 진입마다 1회이며 D trigger는 `failure`다.
- **둘러보기 충돌 검사.** 자기 팔·집게(열림/닫힘)·든 상자를 구로 모델링한다(`harness/visual_arm.py` 순기구학, 발행 PWM).
  - 정적 지도의 벽과 문설주를 높이와 함께 비교한다. 여유는 0.02 m + 몸체 모델 잔차 0.015 m + 2σxy + 2σyaw·팔 길이다.
  - 현재 pan에서 이어지는 충돌 없는 pan 구간만 방문한다. 줄어들면 섀시가 벽에 닿지 않는 뒤·옆 이동(0.08/0.15 m)을 한 번 먼저 해 본다.
  - M1 사슬 안의 둘러보기는 pan만 줄인다(물러나기 없음).
- **진행 감시와 제한된 복구.** Nav2 `SimpleProgressChecker`를 옮긴 것이다.
  - 믿을 만한 자기 추정(고정된 둘러보기 직후, 또는 0.3 s 안의 태그와 LOW 이하 σ)이 명령 주행 6 s 동안 0.10 m(목표 근처는 남은 거리의 절반) 움직이지 않으면 정체로 본다.
  - 정체하면 Nav2 `BackUp`처럼 0.08 m 물러나고, 진행 방향 0.20 m 앞에 keep-out을 두고, 다시 둘러보고 재계획한다.
  - 최대 2회 뒤 `<leg>_blocked`로 실패하고 `blockage_seen(source=own_progress_stall)`을 1회 낸다.
- **막힘 누적.** `judge_route_blockage`의 확신 yes를 위치 키(통로, 0.5 m 칸, 90° 방위)별로 센다. 같은 키에서 2.5 s 안에 2회면 `blockage_seen`이다. 그 키에서 `no`가 나와야 다시 무장한다.

## 사건과 패키지 A/D 연결

| 사건 | D trigger |
|---|---|
| `job_started` | 없음(기록만) |
| `job_done` | `idle` |
| `job_failed` | `failure`; `LOCAL_TIMEOUT`·`EPISODE_END:*`은 `timeout` |
| `blockage_seen` | `blockage` |
| `pose_uncertain` | `failure`(게이트 진입마다 1회) |

`action_record(...)`는 ack를 A의 `ugrp.zone_study_action.v1` 행으로 만들고 A의 `validate_log_record`로 검사한다. 조건은 A의 `CONDITIONS` 이름이어야 한다. v1 스모크가 쓴 `no_llm_scripted`는 거부된다. v2 스모크의 스크립트 층은 대화 채널이 없으므로 `no_comm`으로 기록한다.

## 짝 상태 채널

사용자 결정(2026-09-26)에 따라 공동 운반 상태 채널(`harness/team_carry_status.py`, 고정 enum `aligning/ready/lift/carry/put_down/abort`)은 모든 조건에 같게 들어간다. 이 실행기는 단독 운반만 하므로 채널을 발행하지 않는다. 실행기에 조건 인자가 없어 조건별 차이가 생길 수 없다. 실제 소비자와 비영 트래픽 검증은 공동 운반 실행기(M2) 몫이다.

## 한계

- deliver는 M1 사슬의 청록 상자·문 하나·정적 spawn keep-out 가정을 물려받는다. M1 파지 스킬 내부의 macro 동작(파지 접근 등)은 진행 감시 대상이 아니다. 작업 SIM 한도가 상한이다.
- 몸체 모델은 로봇 한 대의 MuJoCo 몸에서 한 번 교정했다. 0.40 m 벽 검증 자세는 5곳뿐이다. 실물 로봇 검증은 없다.
- 로봇끼리 조정하지 않는다. 문 대치와 충돌 회피는 연구 층(대화)의 몫이고, 실행기는 막힘을 보고만 한다.
- 막힘 판단의 실행 중 정확도는 이 패키지에서 채점하지 않았다(PR #193 오프라인 게이트 범위).
