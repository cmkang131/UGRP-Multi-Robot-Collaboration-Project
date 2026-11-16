# T10b 코디네이터 물리 인수 계획 — 미실행

이 문서는 **한 후보의 최소 진단 제안**이다. 이 작업의 물리/렌더/모델 호출은 0이다.
새 RGB 관측 어댑터·속도 보정·공통 workflow/번들 봉인과 독립 검토 전에는 실행 준비가 아니다.
기존 `zone-study-integration-run`의 복도 거절을 지우거나 문으로 위장해서 실행하지 않는다.
아래 검사를 실행할 수 없으면 해당 셀은 `NOT_REACHED/ADAPTER_UNAVAILABLE`로 남긴다.
이를 성공이나 완료된 물리 검증으로 세지 않는다.

## 먼저 고정할 것

1. 이 PR 최종 커밋과 #310 실제 반영 HEAD를 고정한다. #310은 아직 미병합이면
   `mergeCommit=null`로 적고 branch ancestry만 확인한다. 봉인 등록의 원래 파일은 유지한다.
2. final `zone_wide_corridor_final_v1` 지도 **파일 전체 SHA-256**, `walls_v3`,
   최종 `masterpi_v3` 모델·geometry/actuator/calibration SHA, 표식 0,
   `cargo_noslip_v1`, weld OFF, 초음파 OFF를 manifest에 기록한다.
3. `CorridorPlan.record()`의 route/geometry SHA와 역할 mapping SHA,
   두 신규 controller 파일 및 추이적 의존성의 SHA, `ControlConfig` 전체 값을 고정한다.
   새 actor 입력은 own RGB + 정적 지도 + own issued command history + 실제 delivered status뿐이다.
   네 조건에 같은 observer/controller/config/센서/기억/`zone_pair_status_v5`를 사용한다.
   첫 8셀은 `no_comm` + 동일한 공통 enum 채널로 고정한다. 새 모델 호출 예산은 0이다.
   다른 3조건 효과 검증이나 확증 코호트를 이 8셀에 합산하지 않는다.
4. 읽기 adapter는 각 actor의 raw RGB에서 `OwnView`를 만들어야 한다. held item reference,
   자기 heading, 위치/방향 오차, **자기 grip**, 이동·대피 swept volume의 가시/차단/unknown을
   각각 보존한다. 정답·접촉·성공·상대 좌표를 넣는 fake observer는 물리에 사용할 수 없다.
   가려진 상대/경로를 `clear`로 바꾸지 않는다. 거짓 clear 여부는 평가자만 비교한다.
5. 쓰기 adapter는 `Command`의 robot-relative m/s·rad/s를 실제 보정 명령으로 변환하고
   **0.05초 lease 뒤 명시적으로 정지**해야 한다. `.035 m/s`, `.10 rad/s`,
   base `.05 m/s` 상한과 side-slip/heading 오차를 확인한다. 호출 성공은 실제 이동 성공이 아니다.
   hold 발행 실패는 `ACTUATOR_ISSUE_FAILED`, 정지 미확인으로 남긴다.
6. 표준 `Scene`/`sim_cli`에 새 버전을 등록하고 이 입력 경계를 연결한다. 이 PR은
   물리 진입점을 등록하지 않는다. `sim_cli workflow plan <새 ID> ...`의 dry plan과
   등록 검사를 통과한 뒤에만 `ugrp_session.py run`으로 실행한다. 임의 직접 runner 우회 금지.
7. 공용 잠금을 driver PID로 획득하고 디스크 >=10 GiB를 확인한다. raw는 primary
   `/Users/changmin/projects/ugrp/outputs/<새 T10b 후보>/<cell>-<attempt>/`에 쓴다.
   셀 시작 전에 immutable manifest를 저장하고 실행 뒤 변경하지 않는다. 재시도는 새 폴더다.

## 고정 경로·배치와 8셀

정적 waypoint는 물건 reference `(x,y,yaw)`이며 실제 측정값이 아니다.
`W=(1.5,1.175,0)`, `J=(3.2,1.175,0)`, `E=(4.6,1.175,0)`,
`B=(3.2,.625,0)`. 서→동 `W,J,E`, 동→서 `E,J,W`, solo refuge `J,B`,
재진입 `B,J`. yaw 0을 유지하므로 동→서는 후진 병진이다.

하중은 solo cyan 1개(`r3:west`), pair long_beam 1개(`r1:end_neg,r2:end_pos`)다.
각 carrier의 고정 정류장은 `sim.zone_model_conventions.station_offset(masterpi_v3,kind,role)`를
위 pose에 변환한 값으로 실행 전 숫자와 SHA를 manifest에 저장한다. 이는 scene/staging 전용이다.
controller에 실제 정류장 도착/파지 성공을 host가 통보하지 않는다. 원본 s4 주문/배치를 바꾸지 않는다.
독립 dev 진단이며, 원본 `beam_1=(1.275,.45,π/2)` 접근·파지·90° 회전 성공을 승계하지 않는다.

총 로봇은 항상 **r1/r2/r3 3대**다. 2pair=4대 구성은 사용하지 않는다.
정상 셀에는 주대상과 반대 방향의 다른 편대를 함께 둔다. 두 편대의 출발은 각각 W/E다.
양보자·진입 순서를 host가 선택하지 않는다. 두 로봇 정책이 자신의 가시성으로 대치하면
그대로 실패를 남긴다. 정상이라는 셀 이름이 성공을 뜻하지 않는다.

| 셀 | 주대상·방향 | 상대의 시작/방향 | 사전 고정 교통 조건 | 확인할 종료 | staging 포함 cap |
|---|---|---|---|---|---:|
| S-WE-N | r3/cyan W→E | r1/r2 beam E→W | 양쪽 autonomous controller, bay 비움 | r3 자율 대피→재진입→출구 확인, pair도 충돌 없이 통과 | 900 SIM초 |
| S-EW-N | r3/cyan E→W | r1/r2 beam W→E | 위와 같은 controller/config | 동쪽 접근의 후퇴 방향·대피·재출발 | 900 |
| P-WE-N | r1/r2 beam W→E | r3/cyan E→W | 양쪽 autonomous, bay 비움 | pair bay 진입 0; solo 자율 양보 뒤 pair 통과 | 900 |
| P-EW-N | r1/r2 beam E→W | r3/cyan W→E | 위와 같음 | 두 역할 body 명령 방향·역방향 통과 | 900 |
| S-WE-F | r3/cyan W→E | beam E에서 정지 | 상대 actor에 공개 high-level `hold` job; ready/grant 없음 | 주대상 안전 대기/대피 후 timeout, 잘못된 통과 성공 0 | 900 |
| S-EW-F | r3/cyan E→W | beam W에서 정지 | 위와 같은 정지 job | 반대쪽 대치의 안전 종료 | 900 |
| P-WE-F | beam W→E | r3/cyan E에서 정지 | 상대 actor 공개 `hold` job, bay로 자동 이동 없음 | pair 무리한 bay/교행 0, 대기 timeout/중도 차단 종료 | 900 |
| P-EW-F | beam E→W | r3/cyan W에서 정지 | 위와 같은 정지 job | 역방향 대치 안전 종료 | 900 |

`S-WE-N`과 `P-EW-N`, `S-EW-N`과 `P-WE-N`은 같은 상대 배치의 별도 주대상 진단이다.
표본을 독립 확증 8건으로 해석하지 않는다. 재생해서 다른 주대상 기록을 얻더라도 복제·대칭
관계를 기록한다. 셀마다 실제 actor 출발 순서/첫 frame/명령/enum 전달 시각을 보존한다.
`hold`는 사전에 고정한 상대 job이지 controller에 주는 미래 사건 시각/정답 상태가 아니다.
실패 셀의 정지 상대에 대한 관측도 오직 자기 RGB다.

## 셀마다 필요한 측정과 판정

- 모든 staging·팔 전이·파지·대기·본 주행을 SIM 시작부터 합산하여 900초에서 중단한다.
  8×900=**7,200 SIM초 상한**. 셀 간 남은 cap을 옮기거나 내부 재시도를 숨기지 않는다.
  timeout/미도달/ENOSPC(HOST_ERROR)/observer 미지원/정적 refusal을 각각 기록한다.
- normal 주대상 4셀은 `주대상 passage 성공 수 / 4 계획 셀`을 기본 분모로 적고,
  실행/진입/도달 수를 함께 낸다. failed 셀 4개는 안전 종료 검사의 분모로 따로 적는다.
  `PASSED`는 own-camera local belief다. 평가자의 full crossing과 불일치하면 성공으로 세지 않는다.
- 평가 전용 raw qpos/영상에서 **화물과 모든 carrier 전체 footprint**가 출구를 벗어났는지,
  corridor 양 입구/중심선 통과, bay 정지 경계와 후퇴·재진입 궤적을 확인한다.
  waypoint/명령 소모/시간 경과는 통과 판정이 아니다. 목적 구역 배달·방출 성공은 이 셀 범위 밖이다.
- 주행 중 매 step 병진 Δx/Δy, 누적 yaw, 각 carrier yaw/속도, cargo 상대 변위·기울기,
  접촉 상대·위치·힘/충격·지속 시간, grip 상실, 벽/상대 관통 여부를 평가 로그로 남긴다.
  접촉 지표를 실시간 controller 입력으로 돌려보내지 않는다. 금지 충돌 또는 낙하는 셀 실패다.
- `WAIT_LANE`·`WAIT_BAY`는 자기 시계 30초에서 실패; 전체 제어 240초; 진행 없음 10초;
  대치 세 번째는 종료; pair 최초 heartbeat 대기 2초; heartbeat age **>=.15초**는 종료다.
  마지막 motion lease .05초 만료 이후 잔류 이동이 없는지 확인한다. clock/SIM 변환을 봉인한다.
- 정상 solo 셀에서 후퇴와 bay 정지 후 lane clear가 새 프레임 3장 이상·.3초 유지되어야
  재진입한다. 가림/재진입 충돌은 정지한다. pair가 bay에 못 들어가므로 solo 자신이
  양보를 선택했는지 policy state·입력 해시로 감사한다. host의 grant/peer pose가 있으면 무효다.
- pair는 각 station의 `carry_ready_N`/`carry_go_N` 실제 전달·같은 job hash를 확인한다.
  한쪽 이탈/영상 invalid/abort/heartbeat 단절 뒤 양쪽 정지를 검증한다. 이 8셀의 실패 조건에
  해당 현상이 발생하지 않으면 **그 고장은 fake만 검증**으로 남긴다. 별도 고장 주입 실행은
  새 셀·새 예산/고정 계획이 필요하다. 정상 셀을 여러 고장시험으로 재활용하지 않는다.
- 본 후보는 **pair pivot·pair bay 후퇴·unloaded 복귀를 거절**한다. 요구된 자세 경로가
  이를 필요로 하면 셀을 `UNSUPPORTED`로 남긴다. 원본 s4 운반 4.05–9.35 m,
  beam 누적90°·green120°를 이 corridor leg 성공으로 충족했다고 쓰지 않는다.
  빈 로봇 복귀·bay 후퇴 거리·현장 지연 총량은 미산정이다.

## 결과 인계

원본 RGB/실제 모델 요청(있는 경우)/명령/전달 enum/평가 전용 기록을 역할별로 분리 보존한다.
소스·환경·입력·raw 파일 전체 SHA와 manifest를 `experiments/<새 ID>/`에 연결하고,
정상·실패·미도달을 모두 새 native TensorBoard snapshot으로 변환한다. 기존 manifest의
source hash를 확인해 중복 변환을 피하고 primary `outputs/tensorboard`를 사용한다.
실제 EventAccumulator 데이터 로딩·video 등록·기본 카드(success/runtime/commands/model calls/
response time)와 HParams를 원본과 비교하고 dashboard 링크를 남긴다.
모델 호출 0이면 그 값을 명시하고 실제 요청/latency가 있는 것처럼 만들지 않는다.
원본·이전 snapshot은 보존한다. 구현 PR, 물리 인수, 원본 s4 E2E, 4조건 효과는 별도 판정이다.
