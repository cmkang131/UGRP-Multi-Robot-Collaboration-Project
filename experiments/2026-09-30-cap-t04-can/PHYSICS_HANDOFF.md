# T04 can 물리 인수 인계 — 미실행

이 PR은 can 전용 **오프라인 제어 후보**다. 완료된 물리 실행·렌더·학습·모델 호출은 0이다.
기존 회귀의 렌더 초기화 실패 1건과 비물리 guard 재검사는 README/verification 기록을 따른다.
파지·배송 지원 또는 정식 시나리오 성공으로 승격하지 않는다.

## 소스와 진입점

- 시작 main: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e` (#328).
  제출 전 `26545c2499f94c3f99a5d650f7cc8ea992f24196`로 fast-forward했고 can 의존 소스 해시는 동일하다.
- 요구 감사 #302 병합: `09081b3c46f0d51e02ef625e4be8c7d6f6e67963`.
- T03 #325는 미병합 형제 PR이며 의존하지 않는다. 공통 색 상자 dispatch는 그대로다.
- 독립 factory: `harness.can_skill_registry.create_skill('can', role='any', condition=..., robot_id=..., static_map=..., destination_zone='C', pose_source=own_provider)`.
- 루프: `on_command(own_port_row)` → `step(now, own_obs)` → 반환 `commands` 발행.
  발행 행에는 자기 `robot_id`와 `t`를 붙여 **실제 발행 이력만** 되돌린다.
  관절 측정값으로 PWM 이력을 대체하지 않는다. `image`와 `sha256`의 실제 JPEG를 직접 판정한다.
  등록된 자기 RGB provider에 같은 JPEG의 RGB와 자기 명령을 전달해 pose를 계산한다.
  외부 PoseReport 입력은 없다. navigation과 같은 provider를 공유할 때 프레임/명령을 중복 전달하지 않는다.
- `holding` 후 목적지 주행은 별도 공통 navigation의 일이다. 완료 waypoint는 방출 권한이 아니다.
  `request_release()` 뒤에도 최신 자기 RGB holding·자기 위치 추정·공개 C 영역 검사를 통과해야 한다.
  `released_visual`은 제어기의 영상 후보이며 `delivery_success`는 항상 `None`이다.

기존 봉인 executor에 자동 등록하거나 실행 번들을 새로 예약하지 않았다. **현 시점에 실행 가능한
can E2E CLI가 생긴 것은 아니다.** 코디네이터는 새 opt-in 어댑터/표준 `sim_cli` workflow에서
위 factory를 연결하고, 소스 의존성·구성·입력 해시를 포함한 새 번들을 고정해야 한다.
기존 `ZoneOwnExecutor.deliver`의 can 거절을 삭제하거나 기존 봉인에 이 후보를 끼워 넣지 않는다.

## 고정할 한 후보의 두 셀

총 cap은 **2 × 900 = 1,800 SIM초**다. 두 셀 합계이며 s1/s5 각각 두 번으로 늘리지 않는다.
공통 can 배치 `(0.4, -0.85, 0)`와 목적지 C를 공유하는 **단독 dev fixture**로 실행한다.
원본 s1 전체 7물건·s5 전체 4물건을 실행한 것으로 세지 않는다.

| 셀 | 시작/입력 | 기대 확인 | cap |
|---|---|---|---:|
| can-normal-1 | can 한 개, 직경 .038 m·높이 .050 m·80 g, 위 pose, role `any`; seed 601; r1 시작 `(-.85,-.85,0)`를 dev setup에 사전 고정 | 실제 spawn→자기 RGB 접근→닫기→두 높이 holding→실제 C 주행→방출→영상 재확인→평가 착지 | 900 SIM초 |
| can-failure-1 | 같은 지도·로봇·후보·seed·출발. can을 **처음부터 제거**한 별도 평가/장면 fixture; 공개 can 주문은 유지 | 빈 곳/바닥 색을 can으로 보지 않음, 접근 미도달/timeout, holding·방출·배송 거짓 성공 0 | 900 SIM초 |

실패 셀의 제거 사실은 제어 입력에 주지 않는다. 실패를 접촉/GT 기반 제어 분기로 만들지 않는다.
이 두 셀은 정상 1 + 부재 실패 1이다. **실제 미파지·오물 파지·운반 중 낙하를 모두 물리 검증한
것은 아니다.** 해당 반례는 이 PR에서 fake로만 확인했고 추가 물리 셀은 별도 예산이 필요하다.

정상 셀의 벽만 고려한 운반 길이는 감사의 **3.30 m** 참고값이다. 로봇의 실제 spawn→시야→상대
접근·팔 전이·들기·정지·문 통과·C 정렬·방출 확인을 모두 900초 안에 포함한다. staging 시간을
시계를 초기화해 빼지 않는다. cap까지 미완료이면 실패/미도달로 분모에 남긴다.
정적 경로 JSON/inventory는 평가 자료이며 학생의 경로/좌표 입력으로 넘기지 않는다.

## 실행 전 닫아야 할 연결과 가시성 검사

1. 최종 `masterpi_v3`, `walls_v3`, 표식 0, 원래 카메라 배치/FOV, `cargo_noslip_v1`, weld OFF를
   실제 적용값·해시로 고정한다. 원본 지도·s1–s6·성공 번들·본연구 DRAFT는 수정하지 않는다.
2. 동기 실행/프레임 수신/명령 기록 어댑터와 can factory의 연결을 검사한다. 자기 RGB 외의 top,
   GT pose/관절/접촉/심판/동료 현재 정보가 전달되지 않아야 한다. 자기 pose report는 실제
   무표식 자기 RGB provider의 연속 상태로 만든다. fake report나 GT 초기화로 대신하지 않는다.
3. 후보 팔은 v3 command IK의 x=.200 m, grasp z=.024 m, lift z=.080/.100 m, 선호 pitch=-66°,
   open=2000/close=1500이다. catalogue의 기존 교사 반경 .155 m는 v3 IK의 허용 범위 밖이다.
   원본 catalogue 값은 바꾸지 않았다. 실제 상대 접근 정류장·팔 간섭·파지 높이 오차를 따로 기록한다.
4. 접근 view PWM은 registry 의존 소스 `VIEWS` 세 개다. .32/.26 m에서 새 view로 전환한 뒤
   반드시 새 자기 RGB를 맞춘다. 지원 범위 밖, 가림/잘림/복수 후보, can/상자 투영 구분 불가는 정지한다.
5. 기존 box carry view에서 can 전체는 보이지 않는다. 후보의 **바닥 rim 가설**이 두 lift 높이에서
   실제로 보이는지, 손가락 가림·바닥 can·빈 집게와 구별되는지 원본 RGB로 확인한다. 가시성이
   부족하면 `unknown`/실패로 남긴다. 카메라를 옮기거나 threshold를 실행 중 바꾸지 않는다.
6. can의 회전/기울기·접촉/마찰 때문에 upright rim 가설이 깨지는지 평가한다. 팔 PWM은 실제
   높이·파지의 증거가 아니다. 모듈의 정적 sweep에는 v3 몸체와 can 크기를 별도로 포함했지만
   동적 로봇/타 물건 회피나 문 통과를 검증한 것은 아니다.
7. 목적지 navigation은 can 하중/가시성·실제 상태 인계를 지원해야 한다. box의 팔 자세·holding
   threshold를 그대로 호출하지 않는다. 경로 계획과 실제 통과, 영상 방출과 물리 착지를 구분한다.

시작 전 `python3 scripts/agent_lock.py status` 및 디스크 보고를 확인하고, **물리 드라이버 PID**로
공용 잠금을 획득한다. 기존 다른 작업을 중지하지 않는다. 원본 고정/어댑터 연결이 미완료면 실행하지
말고 차단 사유를 남긴다. 종료 시 자기 session 자식과 잠금만 정리한다. 로컬 offline pytest에는
이 물리 잠금이 필요하지 않다(#328).

## 판정과 보존

- 정상 셀: can을 실제로 들어 안정 보유했는지, 실제 운반·문 통과·C 안 착지·집게 분리가 모두
  완료됐는지 평가 전용 자료로 확인한다. `released_visual`/`holding` 오검출은 별도 분자/분모로 남긴다.
- 실패 셀: 배송 성공 0/1과 안전 거절 1/1 여부를 별도로 기록한다. 정상/실패 셀을 합쳐 성공률을
  부풀리지 않는다. SIM cap·HOST_ERROR(ENOSPC 포함)·입력 불능·지원 밖을 구분한다.
- 각 셀의 SIM초(준비 포함), 명령 수, 관측 수, holding/방출 판정, 실패 원인, 접촉/파지/착지 평가,
  모델 호출 0 및 비용 0을 기록한다. wall 시간은 측정 전 환산하지 않는다.
- raw는 `/Users/changmin/projects/ugrp/outputs/cap-t04-can/<candidate-sha>/<cell>-<unique-id>/`에
  새로 보존한다. 자기 RGB JPEG·해시·전체 명령·provider 입력/상태·환경·실행/role assignment 해시,
  별도 심판 trace·결과·영상과 전체 SHA-256 manifest를 저장한다. 실패 파일을 덮어쓰지 않는다.
- `docs/tensorboard.md`에 따라 새 결과(실패 포함)를 primary `outputs/tensorboard`의 새 snapshot으로
  변환한다. 실제 데이터 로딩·영상 등록·원본 해시·native TensorBoard 표시를 확인하고 링크를 남긴다.
  이 PR의 단위검사 수를 물리 성공률/TensorBoard 실험 성과로 만들지 않는다.

## 지원 범위

`no_comm/peer_ko/leader_ko/structured`는 같은 factory·profile·STATES·센서·자기 기억을 쓴다.
조건별 제어 override와 새 상태 통신 채널은 없다. 이 2셀은 4조건 효과/확증 코호트가 아니다.
kind의 색은 개체 ID가 아니다. 이 후보는 s1/s5의 단일 can kind 진단이며 s6의 specific identity,
서쪽 진입 의무, 빔 선행 순서/pivot을 구현하지 않는다. role `any`를 유지한다.
s6의 정적 **2.25 m**는 타 물건 사이 can 진입을 입증하지 않는다. s6는 T11 설계/접근 검증이
별도로 필요하다. 학습·현실 RGB 라벨링·보정 반복 및 추가 실패 셀 비용은 미산정이다.
