# S3 s3fix3 — 공동 운반 예외와 공통 명령 계약 (2026-10-09)

사용자 확정: **두 로봇이 함께 빔을 드는 구간은 heading 제외, 기존 옆걸음 경로 유지**. 단독·접근은 heading 기본ON, 집기·놓기·문 정렬 lateral은 최종0.10m만 허용한다. 기존 GO 상호 확인·실제 물리/실행 오류는 정지하며 DEV σ/관측/충돌 가드는 기록 후 계속한다.

공통 최소 명령 길이·단일 축 수정은 main 대상 PR #422 (`6ffa74df`)로 먼저 분리한 뒤 S3에 merge했다(`93f648a3`, rebase0). 같은 `zone_solo_cyan_path_heading` 선택기와 v145 factory를 사용하며 S3 전용 duration 보정을 만들지 않는다. 0.06초 제안은 늘리거나 합성하지 않고 생략한다. 유효한 최종 lateral이 없으면 기존3cm 반경까지 회전·전진 후 최종 yaw; 기존 도착/σ 문턱 그대로다. [저장 명령/회귀/표준 근거](../../2026-10-09-heading-command-contract/README.md).

`HEADING_EXCEPTIONS`의 유일한 항목은 `coupled_beam_carry`다. r1/r2 자기 집기 명령 이력·carry 단계·살아 있는 peer carry enum을 요구하고 기존 GO를 우회하지 않는다. 승인된 기존 route/연속 축 혼합/시간 schedule은 바꾸지 않는다. 호스트는 두 자기 발행 gripper 명령이 닫힌 경우 기존 CameraRobotPort의 명령 경로를 사용한다. 실제 파지 여부는 제어에 몰래 넣지 않고 기존 독립 물리 판정으로 검사한다.

r1/r2 PF는 같은 posterior와 AMCL odometry 적분을 유지하며 자기 집기/놓기 명령 시각에만 S2 pulse ↔ 기존 pair 연속 모델을 전환한다. loaded 모델은 `door_schedule`과 같은 정적 pair calibration을 사용하고, 새 보정·측정이라고 주장하지 않는다. S2 loaded pulse 전용 flow buffer는 공동 연속 운반에 사용하지 않는다. 자기 RGB wall update와 카메라 보정은 유지한다. r3/S2 및 옵션off는 이 예외를 적용하지 않는다. v7 공동 loaded 정확도는 여전히 미인수다.

새 실행 전 고정: 전체 main/열린 PR의 최대147/7.40 확인 후 **v148/7.41.0**. seed14201 고정, DEV1회, SIM1800/wall10800초, 원본3GiB+10GiB reserve, ENOSPC=HOST_ERROR. v3 호스트 binding·heading on·main #420 relay-cache on. S3 정확 posterior 캐시/JSONL 버퍼ON은 이전442프레임의 명령·상태·RNG 동일성에 근거하고, cProfile을 먼저 끝낸 후 실제 profiler 없이 wall/SIM을 측정한다. 입자/seed/수렴 문턱은 바꾸지 않는다. 임계값이나 활성화 결정을 새 smoke 결과를 본 뒤 바꾸지 않는다. [등록](registration.json), [번호 확인](reservation.json).

사전 회귀: 공통2파일30 PASS; S3 관련2파일18 PASS + 표준 카탈로그 plan1 PASS. 공통 원본 명령3개 계약 거부→수정 출력3개 허용은 모터 stub 오프라인이며 물리 성공이 아니다. S3 예외는 역할/자기 grasp/peer enum 거부 경로, native motor 값/만료의 기존 일치, 실제 PF의 loaded 혼합→release→unloaded pulse 전환, off 포즈/입자/RNG 동일성을 확인했다.

이 문서를 기록한 시점의 새 물리 실행은0회다. cProfile와 새 smoke 결과는 별도 파일로 추가하며 원본 v147 및 s3fix2 비교는 덮어쓰지 않는다.

## 완료한 cProfile와 v148 DEV 1회

실행 소스 `533329b51a3eb0e6d940a8d2f4c187af46781805`, seed14201, clean/push 후 표준 `sim_cli workflow run zone-s3-motion-v148`로 실행했다. nice0·배타 잠금 획득/해제 확인, 시뮬1회, 재실행0, CI 기다림0. 결과는 **HOST_ERROR이며 S3 통과/병합 준비 완료가 아니다.**

잠금 내 독립 프로세스에서 v147 저장 입력442프레임/로봇을 캐시 전후 재생했다([프로파일](profile-summary.json), [잠금](profile-lock.json)). 생성 명령 SHA `95c7bb1b…838d4065`, 전체 pose/최종 입자·가중치·RNG SHA `6138376f…6762bb8a`가 같다. 과거 혼합 축 오류에서 동일하게 끝나는 가속 전용 비교다. cProfile 자체 비용을 포함하고 렌더/물리가 없으므로 wall/SIM이 아니다. 누적 시간은 중첩되므로 합산하지 않는다.

|오프라인 비용|전(초/호출)|캐시 후(초/호출)|
|---|---:|---:|
|전체 cProfile wall|141.774|62.076|
|전역 posterior 요약|82.638 / 5694|0.829 / 27|
|best-cluster 요약|6.616 / 4396|1.244 / 475|
|KLD resample|0.863 / 24|0.848 / 24|
|능동 head 후보 점수|0.328 / 21|0.305 / 21|
|pair would_stop audit|0.001194 / 421|0.001116 / 421|

주요 병목은 고정 posterior의 반복 요약/정렬이다(NumPy argsort self74.416초). would_stop511회 동기 I/O 가설과는 맞지 않는다. 초기400k 입자는 기존 KLD가 유효 관측 후8001, 이동 handoff에서2000으로 이미 줄인다. 이번 가속은 분포·RNG·문턱을 바꾸지 않는 내용 캐시와 같은 JSONL 바이트의 버퍼링이다. 캐시 내용 해시는 후 조건에서8.492초로 남는다. S2 6seed의 σ4/6→2/6과 실제 XY오차6/6 개선은 [기존 고정14초 비교표](../s3fix2/README.md)에 보존하며, S2 기본off/활성 범위는 바꾸지 않았다.

첫 관측 종료13.50 SIM초(첫프레임 후12.20초) 현재 최선 위치와 인증을 구분했다([평가 원장](smoke-report.json)).

|로봇|첫 XY오차m / yaw오차°|σxy m / σyaw°|첫 위치/인증|단계별 도달|
|---|---|---|---|---|
|r1|0.026297 / 2.011|1.840407 / 67.561|점 정확 / 인증 실패|초기 관측→pair 접근; 집기·carry·문 통과·놓기·B 미도달|
|r2|0.039537 / 1.612|0.208610 / 7.346|점 정확 / 인증 실패|초기 관측→pair 접근 첫 heading 제안에서 호스트 거부; 이후 미도달|
|r3|0.003887 / 0.576|0.058307 / 1.368|점 정확 / 인증 실패|초기 관측→문 예약 대기; 집기 이후 미도달|

정확 점3/3, 기준 인증0/3·허위 인증0, 로봇 임무0/3·B 배송0/2. 세 로봇 모두 실제 발행된 비영 차체 명령0; 최대 변위4.3/2.5/3.7mm는 팔 움직임에 따른 settling을 포함하므로 주행 성공이 아니다. 첫 렌더를 포함439×3 camera pose의 local 위치/quaternion이 S2 v3와 모두 동일했다. **호스트 마운트 바인딩 수정**이며 제어기 외부 파라미터 맞춤이 아니다.

DEV would_stop **501개 검사 훅**: SWEEP_TRANSITION_BLOCKED374, POSE_CLUSTER_UNCERTAIN60, POSE_UNCERTAIN36, ARM_COLLISION_GUARD23, SELF_UNCERTAIN4, GLOBAL_START_UNRESOLVED3, PAIR_COLLISION_GUARD1. 서로 다른 훅 집계이며 물리 실패 수/파일 쓰기 수가 아니다. 실제 정지는 아래 HOST_ERROR1건뿐이다. 문 REQUEST 진입은 각1회, 대기0.05/0.05/9.70 robot-s, 충돌0·120초 교착0; 관측21.90초이므로 장기 교착 부재는 미입증이다.

**wall93.526772초 / SIM21.90초 = 4.270629**, 목표≤3 미달. v147의7.719934와 종료 시점/명령 경로가 달라 정확 가속비로 주장하지 않는다. 호스트 물리20.620초, capture15.345초(그중 렌더13.362초), JSONL append0.191초, eval0.148초다. 중첩 타이머를 합산하지 않는다. 초기화/제어/정리 잔여 시간은 이 계측만으로 세분할 수 없다.

## 스모크 후 reset 계약 수정 — 오프라인만

원인 한 줄: **생성자에서 붙인 S2 포트를 `IntegerClock.reset()`이 기본 CameraRobotPort로 다시 만들어, r2 단일 축 .35/0.10초 heading 명령을 옛 ±.15 상한으로 거부했다.** 실제 reset 호출에서 저장 명령의 같은 오류를 재현했다. 스모크의 `pair-motion-ports.json`은 reset 이전 영수증이어서 실제 실행 포트 증거로 사용할 수 없다. 공통 #422의 최소 길이/단일 축 수정과는 별도 S3 생명주기 누락이다.

기존 `sim/s2_real_output_reset.py`/`sim/s2_align_pulse.py`의 reset 후 capability 연결을 재사용했다. `sim/s3_motion_ports.PhysicsBackend.reset()`에서 clock snap 후 r1/r2 PairPhasePort와 r3 FinePulsePort를 연결하고 그 뒤 영수증을 기록한다. off는 기존 reset/상한을 유지한다. 시뮬레이터 없이 **실제 IntegerClock.reset→S3 reset→host.issue→native motor/expiry**와 저장 실패 명령을 시험했다([fixture](../../../../tests/fixtures/path_heading/s3-v148-reset.json), [회귀 범위](reset-regression.json)). 변경 시험 파일16개가 모두 통과했다. 한 시험의 float 만료 assertion을 실제 다음 physics substep으로 바로잡은 후 해당2개를 재확인했다. 추가 물리0; 수정 뒤 소스는 v148 실행 SHA와 다르다.

원본1350파일/43,724,813bytes 전체 SHA 일치([검증](raw-verification.json)). 로컬 `/Users/changmin/projects/ugrp/outputs/s3-motion-533329b5-s14201-v148`, 표준 원장 `/Users/changmin/projects/ugrp/outputs/s3fix3-20261009/workflow-v148/manifest.json`; 원격 raw 백업은 아니다. 대표4배속110프레임/5.5초 영상은 `/Users/changmin/projects/ugrp/outputs/s3fix3-20261009/views/v148/execution.mp4`([해시](video-verification.json), [재생](http://127.0.0.1:6007/video/e39cb3621ab347b755e8))이다. 새 렌더 없이 저장 자기 RGB3개를 연결했다.

TensorBoard `1009-s3-v148`30scalar·`1009-s3-profile-verified`2runs/20scalar를 실제 재로딩해 대조했다([값](tensorboard-values.json), [고정 링크/설정](tensorboard-link.json)). v147 실패와 비교하며 오프라인 equality success1과 로봇 임무 success0을 구분한다. 최초 profile 변환은 잘못된 하위 폴더명으로0개 변환됐고 실패 manifest를 보존한 뒤 올바른 경로를 새 snapshot으로 변환했다. Chrome 강에서 비교4runs·9pins와 HParams case/policy/seed/source_sha를 확인했고, 기존 다른 작업 서버를 유지했다.

다음 물리 실행 제안: reset 이후 포트 수정 SHA를 새 번들로 고정한 동일seed DEV1회에서 첫 heading 명령부터 공동 carry까지 확인하고, σ/속도 기준은 그대로 보고한다.
