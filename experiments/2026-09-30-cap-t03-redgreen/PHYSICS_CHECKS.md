# T03 물리 인계 — DRAFT, 아직 실행할 수 있는 봉인 아님

이 PR은 R2의 **색 상자 논리만** 다룬다. 로컬 physics/시뮬레이션/렌더/새 모델 호출은 0회다. 아래 4셀은 한 후보의 최소 진단 제안이며 4조건 효과 검증·확증·본연구 완료가 아니다. 정상/실패 목표 셀을 통과한 offline RGB 검사로 대신하지 않는다.

## 실행 전에 조정자가 고정할 것

1. P01 #305, P02 #307, P03 #312, P05 #308, P07 #311의 실제 통합 SHA와 독립 검토를 기록한다. 이 작업 시작 때는 모두 OPEN/DRAFT, merge SHA 없음이었다. P01/P03의 최종 로봇 v3·walls_v3·무표식 provider/카메라/모델 보정 admission은 아직 미지원이다. 이 PR 색 skill도 기존 M1 geometry를 재사용하며 v3 consumer 선언이 없으므로 `require_v3_consumers`가 물리 생성 전에 거절한다. 새 색 skill의 v3 FK/IK/카메라 연결을 독립적으로 고정·검증해야 한다. 이 상태에서 v2/태그로 바꿔 실행하지 않는다.
2. 최종 로봇 3D 모델, walls_v3, 표식 0, weld OFF, cargo_noslip_v1 및 적용된 timestep/contact/camera/FOV/pose-provider/모델/보정 hash를 고정한다. 정식 s1–s6와 seed·주문·성공 기준 원본을 그대로 두고 **별도 dev fixture**를 등록한다. 새 camera/view 조작이나 GT 재측위·위치 이동으로 준비 단계를 생략하지 않는다.
3. 새 후보의 세 종류 모두 봉인되지 않은 호출자가 `harness.zone_color_box_executor.ZoneColorBoxExecutor`를 명시적으로 생성하고 `harness.wrist_color_boxes.WristColorBoxDelivery` factory를 전달해야 한다. 기존 host의 `student.skill_module`/`skill_class`만 바꾸는 경로는 red/green을 허용하지 않는다. 별도 host/runner 선택과 새 실행 번들 연결을 먼저 검증한다. factory의 `box_perception_profile=m1_color_boxes_v1`가 M1/검색/clip recovery까지 전달돼야 한다. 기존 `wrist_zone_skill_v9`는 legacy cyan만 허용한다. 새 후보는 N7 단독 cyan 실행의 성공 판정을 승계하지 않는다.
4. no_comm/peer_ko/leader_ko/structured에 같은 student·controller/config·센서·자기 기억·고정 상태 enum을 쓰고 그 hash가 같은지 검사한다. role assignment hash는 따로 기록한다. 아래 4셀을 조건별로 복제해 16회 돌리는 예산이 아니다. 통신 비교 cohort는 별도 사전 등록한다. 모델 호출 예산은 이 작업에 없다.
5. 새 bundle/workflow 번호는 조정자가 main+열린 PR의 최댓값을 확인해 예약한다. `sim_cli` 공통 기록에 source·설정·입력·결과를 연결한다. 실행 전 code/input/config를 커밋하고 그 SHA 동안 고정한다. 공용 lock, 디스크 10 GiB 이상, 새 primary outputs 경로를 확인한다. 다른 소유자의 실행/서버를 종료하지 않는다.

## 4셀과 종료 기준

| 셀 | 고정 공개 주문과 정상 시작 범위 | 검사 | cap (staging 포함) |
|---|---|---|---:|
| red-normal | s1/s3의 P2:P2-1 범위, red `(1.00,-2.45,0)` → B | 실제 spawn부터 own RGB 탐색→올바른 kind 접근/파지→문 통과→B 방출/확인 | 900 SIM초 |
| red-negative | P2:P2-1, red `(1.60,-2.45,0)` → B, 앞쪽 green distractor `(1.00,-2.45,0)` | 다른 kind 후보를 올바른 대상으로 세지 않는 오인식 도전. 아래 fixture 검증 관문을 먼저 닫는다 | 900 SIM초 |
| green-normal | s1 P1:P1-3 범위, green `(-0.20,0.75,0)` → C | 실제 spawn부터 own RGB 탐색→올바른 kind 접근/파지→문 통과→C 방출/확인 | 900 SIM초 |
| green-negative | P1:P1-3, green `(0.40,0.75,0)` → C, 앞쪽 red distractor `(-0.20,0.75,0)` | 다른 kind 후보/holding/placement를 성공으로 세지 않는 오인식 도전. 아래 fixture 검증 관문을 먼저 닫는다 | 900 SIM초 |

**총 제안 상한 = 2종 × 2셀 × 900 = 3,600 SIM초.** 정적 운반 거리 범위 red 6.55–9.35 m, green 3.30–7.50 m는 P09 정적 경로 수치이며 실제 접근/파지/재탐색/왕복 시간 추정치가 아니다.

고정 제안의 기계 판독본은 `physics_proposal.json`이다. r1/r2/r3 spawn은 각각 `(-.85,-2.25,0)`, `(-.85,-.85,0)`, `(-.85,.55,0)`이며 네 셀의 solo actor는 r1, 나머지는 idle이다. 이는 기존 spawn 후보를 고정한 dev 배정으로 host의 사후 선택이 아니다.

실패 fixture 검증 관문: 이 sandbox는 실제 자기 RGB를 수집/렌더하지 못한다. 조정자가 위 위치의 scene-only distractor를 P02 어댑터로 표현할 수 있는지, 초기 겹침과 실제 자기 RGB의 다른 kind 가시성을 평가 전용으로 검증하고 라벨을 고정해야 한다. current P02의 inventory admission을 우회하지 않는다. 합성 PNG를 물리 라벨로 간주하지 않는다. 다른 kind가 실제 관측되지 않은 셀은 `negative_challenge_not_observed`이며 실패 검증 통과가 아니다. 도전 물체를 거절한 뒤 실제 주문 물체를 찾아 배송한 경우는 거절 검증과 배송 결과를 따로 보고한다. 파지 실패가 발생하지 않았다면 파지 실패 검증은 미측정으로 남긴다. 부족한 셀의 추가 수집·보정·재학습·재실행 비용은 미산정이며 3,600초 안에 성공을 보장하지 않는다. 마찰/질량/집게/카메라를 몰래 변경해 실패를 만들지 않는다.

- 정상 셀 성공: 올바른 kind의 대상이 지정 구역에 방출됨을 **평가 전용** 심판이 확인하고, 별도 own-RGB claim도 기록한다. 색은 개별 item identity가 아니므로 specific item/count2 검증으로 확장하지 않는다. 부분 단계·staging·계산 경로는 배송 성공이 아니다.
- 실패 도전 셀: 다른 kind의 후보/holding/방출을 올바른 kind 배송으로 세지 않아야 한다. 가림/검은 프레임·확신 부족이면 미확인/중단이 관찰돼야 한다. 손에 든 다른 색 물건의 카메라 상대 공이동도 requested kind holding이 아니다. 접촉/심판을 제어 입력이나 복구 힌트로 보내지 않는다.
- 모든 셀은 cap에서 중단하고 `cap_reached=true`, `failure/not_reached`로 남긴다. cap 셀·HOST_ERROR(ENOSPC 포함)·negative 도전 미발생을 성공 분모에서 조용히 제외하지 않는다. 4개 계획 셀과 실제 시작/완료/실패/미실행 수를 각각 보고한다.

## 원본과 결과 인수

primary `/Users/changmin/projects/ugrp/outputs/cap-t03-redgreen/physical-<새 실행 ID>/<cell>/`에 각 시도별 새 경로를 사용한다. 실패 후 같은 파일을 덮지 않는다. raw own JPEG·전체 모델 요청/응답(호출이 별도 승인된 경우)·발행 명령·관측·servo/단계 전이·staging 포함 SIM초·벽시계 시간·실패 원인·평가 전용 GT/접촉·성공률 분모를 분리 보존한다. controller/config hash와 role assignment hash를 별도 기록하고 raw 전체 해시를 manifest에 연결한다.

실행 뒤 `docs/tensorboard.md`를 따라 **새** snapshot을 만든다. source path/hash 중복 여부, 실제 scalar readback(성공/시간/명령/모델 호출·응답 시간), 영상 등록, primary outputs/tensorboard logdir과 소유 viewer, pinned 링크/열/표시값을 검증한다. 기존 snapshot·raw·shared view의 다른 키는 보존한다. 구현 draft의 준비 판정과 물리 결과 판정을 따로 보고한다.
