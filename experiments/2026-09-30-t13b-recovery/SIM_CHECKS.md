# T13b 코디네이터 인계 — 사건 4분기, 4×900 = 3,600 SIM초

이 문서는 **미실행 최소 진단 제안**이다. 이 PR에서는 fake 제어·평가 분리만 검사한다.
렌더/물리/모델 호출은 0이며, fake 통과나 CI 통과는 물리 인수 통과가 아니다.

## 실행 전 준비 판정

1. #320(T13a)의 실제 병합 SHA와 specific identity의 시각적 근거를 확인한다. 현재 #320은
   공개 이름/색/초기 slot으로 specific identity를 확정하지 않는다. 원본 s5 cyan은
   `specific_item`이므로 **현재 정상 복구 실행은 차단**이다. GT lookup, cyan 한 개라는
   이유, 옛 local token 재사용으로 해소하지 않는다.
2. T03 red·T04 can의 하위 접근/파지/방출, T02의 원본 4물건 보존, P01 최종 장면/provider,
   P03 자기 RGB, P05 통신/원장, P06 평가, P07 manifest의 실제 연결·검토 범위를 확인한다.
   현재 T13b는 `RecoveryJobs`와 fake target backend만 연결했다. 기존 native executor는
   새 API에 연결되지 않았다. `PickupView`의 전체 region 가시성/ROI/빈 영역 판단과
   frame별 tracking·holding/resting도 실제 RGB adapter에서 검증해야 한다.
3. 연결한 **새 후보**를 커밋하고 표준 `sim_cli` workflow·bundle을 등록한다. sealed source나
   원본 s1–s6, DRAFT seed/성공 기준을 수정하지 않는다. 이 PR은 runnable bundle을 만들지
   않았으므로 현재 실행할 수 없는 CLI 옵션을 제시하지 않는다.
4. 최종 MasterPi 3D v3, walls_v3 0.40 m, 표식0, 원래 카메라/FOV, weld OFF,
   cargo_noslip_v1를 고정한다. 원본 s5/v2의 seed 641을 이번 4셀의 공통 seed로 사전 선택한다.
   v1의 다른 seed를 641로 바꾸지 않는다. v1/v2 원본은 별도로 보존한다.
5. no_comm/peer_ko/leader_ko/structured는 동일 controller/config/센서/자기 기억/enum을 쓴다.
   기본 센서는 off를 유지하고, 이번 최소 4셀은 no_comm의 고정 actor action으로 진단한다.
   다른 통신 조건의 성공이나 효과로 복제하지 않는다. actor assignment는 실행 전에 고정하고
   **role_assignment_sha256**과 **controller/config_sha256**을 따로 기록한다. host가
   holder truth로 대상·파트너·양보·재시도를 고르지 않는다.
6. 공용 잠금(`scripts/agent_lock.py acquire`)·여유공간 10 GiB·부하·소유 PID 확인 뒤 자기
   worktree에서 관리 session으로 실행한다. raw는 primary
   `/Users/changmin/projects/ugrp/outputs/t13b-recovery-<candidate>-<new-run>/`에 쓴다.
   실패 파일을 재사용하지 않는다. 다른 작업의 프로세스/잠금은 건드리지 않는다.

## 사건 시계와 사전 고정

원본의 **cyan_1 이동 30.0초**, **red_1 낙하 62.5초**를 모든 셀에서 그대로 사용한다.
두 사건을 모두 켜고, 표의 focal event를 1차 판정 대상으로 삼으며 나머지 사건도 보존한다.
의도한 분기가 성립하지 않아도 시각 변경/강제 낙하/재실행 대체를 하지 않는다.

동일한 초기 배치·seed·공통 구성에서 분기 유도용 사전 action script만 명시적으로 다르게
고정한다. 예를 들어 U는 해당 물체에 close를 발행하지 않고, H는 고정 actor가 사건 전
접근·close를 시도한다. **close 발행은 held 보장이 아니다.** 실제 holder는 사건 직전
평가 기록으로만 확인한다. H에 실패하면 `branch_not_established`이며, 지연/teleport/GT
보정으로 H를 만들지 않는다. 별도의 teacher staging을 추가하려면 별도 진단·예산으로
분리하고 원본 E2E 결과에 섞지 않는다. staging/reset/팔 전이의 SIM 시간도 cap에 포함한다.

## 네 셀의 검사

| 셀 | 사건 직전 기대 상태와 실제 적용 | 학생 입력과 행동에서 확인할 것 | 평가 성공/실패와 cap |
|---|---|---|---|
| M-U | cyan 미파지, 30초 `item_moved`, 원본 목적 pose (-0.2, 0.75, 0), 원래 z 유지·속도 초기화 | 공개 initial_location P1-1 불변. 사건 통보 없이 자기 RGB의 명확한 빈 pickup 관측으로 부재 믿음. 새 위치는 재탐색으로 찾고 T13a identity 후 다시 target job 제출 | 실제 이동, 최초 own 발견, 재탐색/재파지, 정확 cyan의 A 도착을 따로 검사. 900초에 미완료면 실패/미도달 |
| M-H | cyan 파지, 30초 `none_item_held` | host가 empty/failed/success를 통보하지 않음. 동일 own 영상·명령 이력일 때 사건 전후 정책을 이벤트만으로 바꾸지 않음 | item pose/속도 강제 변경0. 효과 없는 사건으로 기록. 이동 복구 분모에 제외하되 할당/no-op에는 포함. 900초 |
| D-H | red_1 파지, 62.5초 `gripper_fault_open`; 실제 모든 holder의 gripper에 1초 fault | 자기 발행 이력에 host open을 넣지 않음. 자기 연속 RGB에서 held→명확한 unheld/resting이면 하위 refresh 전 cancel. 새 own 프레임 후 재시도, 중복 red/count 방지 | fault 적용과 실제 낙하를 분리. 정상 접촉에서 실제 낙하한 뒤 발견→재파지→해당 red의 B 도착을 평가. open fault만으로 낙하 성공 표시 금지. 900초 |
| D-U | red_1 미파지, 62.5초 `none_item_not_held` | GT no-op 통보0, 강제 open/낙하/거짓 실패0. 학생의 absent/dropped는 자기 RGB 근거만 사용 | open fault0, 강제 이동0. 낙하 복구 분모에서 제외, 할당/no-op에는 포함. 900초 |

정상·실패 셀 모두 900초가 상한이다. 미지원/정체성 불명/cap 도달/host 오류/ENOSPC는
할당에서 제외하지 않는다(ENOSPC=HOST_ERROR). 한 후보 총 3,600 SIM초를 넘겨 반복하지
않는다. 새로운 후보나 추가 실패 재현은 새 예산·새 run이다. 모델 호출 예산은 포함하지 않는다.

## 남길 원본과 분모

- 사건 직전/직후의 eval-only 실제 holder/contact, item pose/속도, gripper actuator,
  물리 fault 지속시간, 발생 시각/효과/no-op 원문, 공통 seed·설정·입력/소스 hash를 남긴다.
  시뮬레이터 truth를 actor 입력·단계 전환·성공 통보·belief에 전달하지 않는다.
- own RGB 원본/해시, tracking association·ROI·가시성·holding/resting 추론, 공개 주문/정적 지도,
  자기 명령/수신/제출 action, 하위 job cancel/refresh/submit와 timestamp를 보존한다.
  cancel 후 기존 job 명령 잔류0, peer/private 변화 비간섭을 확인한다. 복구 명령 발행,
  자기 배송 믿음, 심판의 정확 개체 배송을 서로 다른 항목으로 남긴다.
- 할당 run 4, 실행/미실행, focal event별 의도/실제 분기, applied/no-op/미기록,
  실제 이동/실제 낙하 성립, 발견, 복구를 각각 센다. 두 사건을 전부 기록하므로 run 분모와
  event 분모를 혼동하지 않는다. `zone_recovery_eval.EventTrial`은 run/event당 한 행이다.
  focal 여부는 별도 manifest로 고정하고 중복 집계하지 않는다.
- 이동 복구율 = 실제 이동 효과가 확인된 focal 실행 중 복구 성공 / 실제 이동 효과 실행.
  낙하 복구율도 실제 낙하 효과 실행만 분모다. fault만 적용된 실행, no-op는 별도 수치다.
  효과 성립 후 cap/판정 누락은 분모에 남긴다. 분모0이면 `None/측정 불가`이며 0% 실패나
  100% 성공으로 바꾸지 않는다. 기대 M-U/D-H가 no-op이면 **사건 성립 부족**으로 보고한다.
  판정 누락이 있으면 비율은 확인된 성공의 비율이며 `recovery_verdict_complete=false`다.
  누락을 실패 판정으로 바꾸거나 최종 성공률로 확정하지 않는다.
  기대 4분기를 모두 채우지 못한 시험은 no-op가 많아도 복구 검증 완료가 아니다.
- cyan 6.35 m→5.15 m는 정적 예시다. 낙하 위치·재파지 경로·staging 비용은 미산정이다.
  성공률에 더해 전체/구간별 SIM초, 명령/관측 수, 모델 호출/응답시간/비용, 실패 원인을 기록한다.
- 코디네이터가 실제 결과를 받은 뒤 `docs/tensorboard.md`대로 native TensorBoard 새 snapshot을
  만든다. 원본 source/hash 중복 검사, event readback, 새 영상 등록, pin/HParams/표시 수치를
  원본과 대조하고 dashboard URL을 적는다. 미회수·미변환·미표시는 완료 처리하지 않는다.
  자기 session과 자식만 정리하고 잠금을 반환한다. 현재 이 PR에는 물리 결과/TensorBoard가 없다.
