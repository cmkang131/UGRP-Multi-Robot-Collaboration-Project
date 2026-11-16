# T08b 실제 접근·정렬 인계 — 코디네이터 실행 계약

이 기록은 **미실행**이다. 작성 작업은 fake/offline만 수행했고 물리·SIM·렌더·추론/LLM은 0회다.
구현 준비와 물리 준비를 분리한다. 현재 후보는 자동 등록/실행되지 않으며 `physical_ready=false`다.

## 실행 전 닫아야 할 연결

1. 이 PR의 최종 코드 SHA, T08a #315의 실제 사용 SHA, 공개 sheet/order/map, 역할 배정,
   controller/config/memory/STATUS, v3 RGB 보정과 command guard 의존성 전체를 고정한다.
   #315가 업데이트되면 병합 후 offline·봉인 검사부터 다시 실행한다. #315의 정적 PASS를
   spawn→prestation 경로/물리 성공으로 승계하지 않는다.
2. P03 담당은 자기 RGB 전용 provider 인스턴스를 공급한다. `report/on_frame/on_command` API와
   `PoseReport`를 사용하며 report의 source는 `owncam_pf...`다. final v3 카메라/모델/보정 해시와
   표식 0 환경을 확인한다. 초기 관측으로 허용 오차에 못 들어오면 그대로
   `SELF_POSE_UNCERTAIN` 실패다. GT `init_prior`, posterior 교체, probe prepared pose는 금지한다.
3. **v3 보정 RGB beam observer와 full-body command guard 어댑터는 아직 연결·인수되지 않았다.**
   `observe_beam(BGR, issued_servo, role)`은 자기 JPEG에서만 v3 chassis-frame
   `grip_base_m`, `axis_heading_rad`, `visible/end_visible`, 추정 표준편차를 반환한다.
   `.0482 m` 팔 mount + `.155 m` reach = `.2032 m`가 목표다. legacy v2의 `.155 m`와
   카메라 ray를 그대로 성공 근거로 쓰지 않는다. `command_clear(action, report, servo, phase)`는
   v3 차체·팔의 전체 병진/회전/서보 sweep, 정적 벽/지형, 자기 영상에서 관측한 장애물을 검사한다.
   False/예외이면 정지한다. 테스트의 FakeBeam/Guard를 실제 실행에 쓰지 않는다.
   보정/충돌 검증이 없으면 **실행 준비 미완료**로 보고한다.
4. #292 담당은 정렬 이후 인계 API를 연결할 때 `BeamApproach.handoff()`가 반환하는
   **동일 `OwnApproachMemory`**(동일 provider/posterior·servo dict·issued history·frame history)를
   넘긴다. `_stage`, `run_pair_stage_probes`, `world.qpos`, prepared pose, 새 PF/servo/history
   초기화는 쓰지 않는다. 이번 T08b에는 close/lift/carry/pivot을 연결하지 않는다.
5. P05는 네 조건의 수신 정책만 소유한다. `receive_status`에는 이미 배달된 기존 고정 enum
   `zone_pair_status_v5` 레코드만 전달한다. host/peer 객체를 전달하지 않는다.
   P06은 eval/raw/terminal 기록과 TensorBoard를 소유한다. 평가 좌표·접촉·정답·숨은 사건은
   제어기에 전달하지 않는다. 새 adapter/실행 경로는 표준 `sim_cli` 관리에 별도로 등록·검증한다.
   이 PR이 기존 runnable/bundle을 조용히 교체하지 않는다.

## 여섯 셀: 한 후보 합계 최대 5,400 SIM초

원본 s1/s3/s6의 세 빔 배치다. s4는 빔 pose가 s1과 같지만 환경이 달라 이 6셀의 성공을
s4 성공으로 대신하지 않는다. 원본 설정/배치/타 화물/숨은 사건을 유지한다.
아래 공개 coarse sheet는 실행 전 선언된 상수이며 eval pose를 읽어 런타임 생성하지 않는다.

| 셀 | 원본 배치/seed | 공개 sheet XYyaw | 조건 | cap |
|---|---|---|---|---:|
| N1 | s1_normal_mixed_v2 / 601 | (1.3, .4, 1.570796) | 정상 | 900 s |
| F1 | 같은 원본/601 | 같은 sheet | 첫 정렬 진입 다음 자기 frame 무효 | 900 s |
| N3 | s3_late_rendezvous_v2 / 621 | (.1, .4, 1.570796) | 정상 | 900 s |
| F3 | 같은 원본/621 | 같은 sheet | 첫 정렬 진입 다음 자기 frame 무효 | 900 s |
| N6 | s6_novel_relation_v2 / 651 | (1.1, -.8, 1.570796) | 정상 | 900 s |
| F6 | 같은 원본/651 | 같은 sheet | 첫 정렬 진입 다음 자기 frame 무효 | 900 s |

- 한 셀은 **두 끝 로봇을 함께** 실제 arena spawn에서 시작한다. 기본 역할은 공개 요청에서
  `end_neg=r1/end_pos=r2`로 고정하고 제3 로봇 r3도 원본 장면에 보존한다. host는 private
  상태를 보고 역할/짝/양보를 고르지 않는다. 여섯 role mapping 인수는 T07의 별도 예산이다.
- 원본 seed는 변경하지 않는다. reset 때 실제 배정된 spawn은 eval에 기록하되 robot 입력으로
  보내지 않는다. `(−.85,−2.25,0)`, `(−.85,−.85,0)`, `(−.85,.55,0)`는 후보 위치이며
  로봇 ID별 배정은 원본 shuffle에 따른다. 초기화/카메라/팔 준비를 포함한 **scene reset t0부터**
  `started_at`을 설정한다. 시간 0을 정류장 도착 뒤로 옮기지 않는다.
- 각 실패 셀은 end_neg의 `phase=aligning` 진입 후 첫 수신 RGB만 사전 정의한 featureless
  black JPEG로 바꾼다(별도 진단 센서 fault). 원본 RGB와 전달 RGB·각 SHA·주입 시점을
  둘 다 보존한다. 조작 조건을 본연구/자연 실패로 표시하지 않는다. GT를 보며 주입 시점을
  고르지 않는다. 정렬에 미도달하면 fault 미발동과 원래 실패를 그대로 기록한다.
- 정상/실패에 동일 controller/config/sensor/기억/STATUS 버전을 쓴다. 진단 조건은 no_comm으로
  고정하고, peer_ko/leader_ko/structured의 통신 효과나 전체4조건 검증으로 표시하지 않는다.
- 최종 3D MasterPi v3, walls_v3, 표식0, weld OFF, cargo_noslip_v1. 원본 물건을 지우거나
  준비 자세로 재배치하지 않는다. 미지원 장면/provider 조합은 실행 전 refusal로 남긴다.
- 900초는 두 로봇의 공통 scene SIM 시간이며 준비·팔 전이·관측·대기를 전부 포함한다.
  900초 경계에서 성공 판정이 먼저 적용되지 않아야 한다. cap은 실패/미도달, ENOSPC는
  HOST_ERROR. 실행별 별도 출력 디렉터리, 모든 할당6셀·시도·취소·미도달을 분모에 보존한다.
  시작 전 `agent_lock.py acquire`, `disk_report.py`, 소스/입력 봉인과 10 GiB 여유를 확인하고
  세션 도구로 자기 프로세스만 정리한다. 외부 모델 호출 예산은 0이다.

## 정확한 로봇 경로와 검사

표준 관리 adapter는 자기 frame→provider→decision→허용된 own port→발행 ACK 순서로 호출한다.
provider는 생성 시 이미 소비한 과거 history를 재생하지 않는다. `on_command`는 제안 시각의
실제 발행 레코드에 한 번만 호출한다. pending proposal이 있으면 새 동작을 발행하지 않는다.
RGB 프레임은 실제 arm/motion settle 종료 뒤의 프레임이어야 하며, 같은 frame ID는 arrival/
alignment streak를 올리지 않는다. 두 로봇의 상태는 같은 enum 채널로 배달한다.

| 검사 | 남쪽 end_neg | 북쪽 end_pos | 기록/판정 |
|---|---|---|---|
| heading | +π/2 | −π/2 | 자신의 posterior로 회전 명령; GT 회전/텔레포트 0 |
| prestation | T08a station에서 뒤로 .25 m | 동일 | 두 fresh frame에서 XY≤.035 m, yaw≤.06 rad라는 **자기 판단** |
| 전역 posterior | 같은 provider/PF | 같은 provider/PF | 평가 전용 GT와 XY/yaw 오차, covariance, fix age, 입력 image SHA를 비교 |
| 정렬 인계 | 실제 issued PWM/history 유지 | 동일 | entry 전후 provider/PF 객체·입자 상태·history prefix/해시·서보·시각 비교; reset 0 |
| 상대 정렬 | grip 목표 (.2032,0), beam heading0 | 동일 body frame 목표 | 두 fresh frame의 x≤.012 m, y≤.008 m, yaw≤.035 rad 자기 주장과 GT 평가 분리 |
| 무효 영상/uncertain | 즉시 hold, 조건 지속 시 terminal | 동일 | failure reason·abort enum·잔여 proposal/명령과 마지막 발행 시각; 숨은 재초기화0 |
| 충돌/경로 | full v3 sweep | 동일 | 경로 거절, 상대 정류장 교차, 벽/타 화물/로봇 접촉을 eval에 보존 |

평가자는 실제 prestation→정렬 진입 시 각 로봇의 posterior XY 오차≤.05 m, yaw 오차≤.06 rad인지
따로 판정하고 모든 값과 위반을 남긴다. 이 수치는 **이번 진단 제안의 관문**이며 기존 연구
성공 기준을 수정하지 않는다. 두 끝이 scene cap 안에 실제 spawn에서 정렬로 이어지고,
벽/타 화물/로봇 충돌·reset 없이 이 관문을 만족해야 `approach_entry_success=true`다.
미도달·posterior 오차 초과·필수 raw 누락은 false/insufficient_evidence로 남긴다.
`relative_aligned`는 로컬 시각 주장이다. 독립 평가 없이 물리 정렬 성공으로 올리지 않는다.
정렬 후 파지·carry·방출을 실행하지 않으므로 **delivery_success는 unknown/null**이다.
실패 셀의 안전 정지를 배송 성공이나 정상 접근 성공 분자에 넣지 않는다.

## 결과 보존과 제출

primary `/Users/changmin/projects/ugrp/outputs/t08b-<후보SHA>-<새ID>/`에 source/input/environment,
raw JPEG(원본/전달본), commands/ACK, decisions/status, provider posterior·servo·history 인계,
각 단계 SIM초와 terminal/failure, 평가 전용 GT/접촉, 영상, manifest SHA-256을 남긴다.
실행 후6셀 전체 판정표와 미발동 fault·미도달 분모를 `experiments/` 새 기록으로 연결한다.
P06의 기록 계약과 `docs/tensorboard.md`에 따라 새 snapshot을 primary `outputs/tensorboard`에
만들고 실제 data loading·영상 등록·표시·원본 해시를 확인한다. 성공/실패, SIM runtime,
command count, model calls=0 및 단계 오차를 표시한다. 다른 viewer/실험 프로세스는 종료하지
않으며 raw를 덮어쓰거나 기존 snapshot을 재등록하지 않는다. 로컬 raw는 원격 백업이 아니다.

직선 하한 약1.03–3.78 m는 evaluator의 참고값이다. 충돌 없는 실제 접근 경로·팔 전이 시간·
wall 시간 환산은 미측정이다. 이번 6셀만으로 원본 혼합 임무·4조건 효과·확증·실물을 승인하지 않는다.
