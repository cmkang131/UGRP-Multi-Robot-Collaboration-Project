# S3 v149 — 단계별 오프라인 통합 검사 후 DEV 1회

2026-10-09 s3fix4 요청. v148은 reset이 포트를 다시 만들어 21.9 SIM초에 HOST_ERROR로 끝났다. 물리를 다음 오류 탐색에 쓰기 전에 합성 단계 시작 상태에서 실제 S3 runtime, pair controller, fixed-enum GO, arm queue, native port.apply와 모터 stub을 연결한다. 영상 인식의 고정 응답과 합성 자기 위치는 시험 fixture이며 위치 추정·파지·운반 성공 근거가 아니다. 모델 호출0, sweep 물리0.

범위는 세 로봇의 startup/접근/포트 reset·재시도, r1/r2 정렬·hover·하강·집기·HIGH·GO·모든 axial/lateral leg·하강·놓기·후퇴, r3 단독 집기·운반 자세 전환·heading·놓기, 문 대기와 소유권 인계다. 기존 S3 호스트에는 놓기 이후 출발지 귀환이 없다. 귀환은 미구현으로 별도 표시하며 통과/완주에 합산하지 않는다. 원래 주문의 B 운반 범위를 유지한다.

실행 전 선택: 새 번들 `zone-s3-sweep-v149` / `7.42.0`, seed14201 고정, v3 **호스트 렌더** 마운트 on, 공통 heading 기본 on(#422 포함), 두 로봇 공동 파지 carry만 기존 옆걸음 허용, DEV light, 기존 v98 exact speedups와 기록 버퍼링 유지. `posterior_content_v2`를 명시적으로 켠다. σ/수렴/성공 문턱·입자·RNG·관측 순서는 변경하지 않는다. 전체 단계 검사 오류0과 변경 시험 초록 후 커밋/push한 SHA로 스모크1회. CI를 기다리지 않고 main 병합하지 않는다. agent_lock 현재 실행이 끝나면 S3 우선, nice0. ENOSPC는 HOST_ERROR, raw 예산과 물리 실패 정지는 기존 계약 그대로다.

첫 통합 오류: `carry_go_N`은 채널에서 `lift`로 정규화된다. 두 GO가 소비된 뒤 첫 carry 제어 틱의 선행 로봇은 후행 로봇의 GO enum을 보므로 기존 `carry` 전용 예외가 거부했다. 같은 segment와 시각의 **실제 소비 GO**를 받은 경우만 허용한다. 일반 lift, 다른 segment, 미소비 GO, stale/abort는 허용하지 않는다. 기존 PairExecution.check의 두 GO 상호 확인은 유지한다.

캐시는 순수 posterior/cluster 요약만 변경된 배열에서 다시 계산한다. 관측이 없더라도 명령 예측으로 입자가 바뀌면 반드시 무효화한다. 배열 identity/시각만으로 캐시하지 않으며 uint64 비트 비교와 소유한 snapshot으로 제자리 변경·부호 있는0까지 확인한다. 반복 암호학적 digest 계산을 제거한다. 시각·health·pan offset·프레임 기록은 원래 호출마다 갱신한다. 이전82.6초는 **캐시 전** cProfile 수치이며 v148 후보는 이미0.83초였다. 추가 절감 대상은 남은 내용 해시 비용8.49초다.

표준 방법: 실제 구성요소를 stub 하드웨어에 연결하는 통합/lifecycle 검사는 [ROS launch_testing](https://docs.ros.org/en/ros2_packages/iron/api/launch_testing/)과 같은 경계 분리이며, 본 검사에서는 동기 Python 상태 주입으로 구현한다. 캐시 범위는 [Python functools](https://docs.python.org/3/library/functools.html)의 순수 계산 원칙을 따르며 가변 posterior 결과는 복사해 반환한다. GO 해석은 저장소 `harness/zone_pair_status.py`의 기존 fixed-enum 규약을 그대로 따른다.

결과는 완료 후 별도 JSON/표로 추가한다. 오프라인 명령·상태 동일성과 새 물리 성공 여부를 구분한다.

## 실행 전 오프라인 결과

단계 검사 **55건 / 실제 native issue 3161건 / 예상 밖 오류0**. 동시 GO 첫 carry 오류1건을 기존 승인 조건에서 재현한 뒤 수정했다. 고정 시야·합성 단계 진입으로 생성한 명령이며 실제 파지/운반 성공이 아니다. GO 미소비는 실제 endpoint에서 `PARTNER_MISSED_GO`로 계속 정지한다. reset 재시도는 세 로봇 모두 검사했고 최종 record도 strict JSON 직렬화를 통과했다. [검사별 결과](sweep-cases.json), [원본/소스 해시](sweep-green.json).

저장 v147 원본442프레임/로봇 재생에서 명령 SHA `95c7bb1babc22263fd45c83e16f352b6ba746a5f97a9cf8ecf93bcca838d4065`, 포즈/입자/가중치/RNG SHA `6138376fcdab9317a77c4ef47ac1625beaa71b4f4d04311f0b0160e06762bb8a`가 기존 off/v1 결과와 동일하다. 비교창 끝의 옛 혼합 축 오류도 그대로이며 새 오류가 아니다. [동일성](replay-equality.json). 로컬 S3 변경 시험26개 및 공통 PR422 시험34개 PASS, CI 대기0. 잠금 내 새 cProfile과 물리 결과는 아직 미완료다.

## 대기 중 추가 경계 검사 — 물리 전

첫 후보3d04ff32는 물리0이며 잠금 대기 실행기를 자체 종료하고 추가 검사했다. 최종 RGB 옆오차1cm/2cm에서 경로용3cm 반경 때문에 pair 명령이0이었고, solo step은 최종10cm 안의 불법0.06초 제안을 반복 생략했다. 공통 PR422 `256a1b0c6633609f2fb91584e01f77f133afb642`에서 호출자의 기존 position 허용치를 받으며, 실제 solo step도 현재 RGB 목표가 있으면 적법한 펄스로 대체한다. S3 pair는 기존 ALIGN_TOL_X/Y(3mm)를 넘긴다. 경로3cm·집기3mm·σ/인증 문턱 모두 그대로이며 모델 보정/seed 교체0. 단독과 pair 각1cm/2cm를 실제 native 포트까지 통과시키는6건을 sweep에 추가했다. 최소 펄스보다 작은 오차의 양자화 한계·실제 파지는 별도 관찰 대상이다.

## v149 종료 뒤 추가 오프라인 수정 — 재실행 없음

v149 `b73ce193`은 집기 전 `wait_approach`의150초 제한으로 끝났다. 종료 후 그 경계를 확인했으며, 다음 후보의 DEV에서 살아 있는 상대의 **GO 전** 접근 대기 시간 초과만 would_stop 후 재대기하도록 수정한다. 실제 GO 조건은 유지하며 readiness/GO를 만들거나 align 단계로 강제 진입하지 않는다. 소비 GO가 이미 있거나 상대가 silent/abort면 기존 정지를 유지한다. 기본 off는 그대로이며 이번 v149 결과에 이 수정을 소급하지 않는다. 다음 물리는 새 번들이 필요하다.

[Python Condition.wait_for](https://docs.python.org/3/library/threading.html#threading.Condition.wait_for)의 표준 원칙처럼 timeout과 조건 충족을 구별하고, 재대기에서도 실제 조건을 다시 확인한다. 수렴·정렬·성공 문턱 변경0. 두 갱신 창을 실제 상태 메서드→모터 stub까지 검사하고, 소비한 GO 이후 timeout은 계속 hard임을 함께 검사한다.

후속 변경 시험11개 PASS, 확장 sweep **58건 / native issue3165건 / 예상 밖 오류0**. 실제 GO 미확인과 소비 GO 뒤 timeout hard 정지도 포함한다. [후속 소스/원본 해시](post-smoke-sweep.json), [검사 내역](post-smoke-cases.json). 이 후속 소스의 물리 실행은0회다.

## v149 실제 DEV 결과 — 집기 이후 미도달

실행 SHA `b73ce1931dae5d803bf2562ad5fa090cb71d2dfb`, seed14201, v149 단1회. 초기 위치 찾기 뒤 차체 이동은 시작했지만 **세 로봇 성공0/3, 집기0, 배송0/2**다. HOST_ERROR0. r1은125.8 SIM초에 자기 추정 사전 합류 지점 도달을 주장했지만 r2는 접근 미완료였다. r1의150.1초 대기가275.9초에 `BARRIER_APPROACH_TIMEOUT`으로 끝나고 r2가 `PARTNER_ABORT`; r3는 문 양보 중이었다. 종료 안정화까지277.6 SIM초다. 접근 GO 자체가 발행되지 않았으므로 실제 GO 소비 불일치나 물리 파지 실패로 분류하지 않는다. 위 후속 패치가 이 보수적 종료를 오프라인으로 고쳤으며, 원래 실패 결과는 그대로 보존한다.

| 로봇 | 첫 위치 XY 오차 / σ (m) | 첫 위치 시간 (첫 영상 이후) | 후속 인증 | 실제 도달 단계 / 최대 이동 | B 배송 |
|---|---|---|---|---|---|
| r1 | 0.02630 / 1.84041 | 12.20 s | 첫 정확 인증36.95 SIM s, 오차0.02551m | 접근 → 사전 합류 대기 / 1.376m | 실패 |
| r2 | 0.03954 / 0.20861 | 12.20 s | 첫 인증112.30 SIM s, 오차0.32010m로 허위 | 접근 → 접근 재시도 / 2.708m | 실패 |
| r3 | 0.00389 / 0.05831 | 12.20 s | 인증 없음 | 문 양보 대기 / 자연 미끄러짐0.00366m, 이동 명령0 | 실패 |

초기 점 위치 정확3/3과 인증0/3은 별개다. 전체 창에서 정확 인증1/3·허위 첫 인증1건이다. r2 마지막 오차0.38796m·σ0.00540m로 **이동 후 실제 추정 오차**가 있으며, σ가 엄격해서만 실패한 것이 아니다. r1 마지막 오차0.17245m, r3 0.00751m. 이 자료만으로 r2 오차의 모델/관측 원인을 확정하지 않는다. 집기·공동 운반·놓기·문 통과는 실제 실행에서 미도달이며 합성 단계 검사를 실제 성공으로 승계하지 않는다. 귀환은 여전히 미구현이다.

would_stop 총5788 hook회: ARM_COLLISION_GUARD23, POSE_CLUSTER_UNCERTAIN60, GLOBAL_START_UNRESOLVED3, POSE_UNCERTAIN2459, SWEEP_TRANSITION_BLOCKED431, SELF_UNCERTAIN4, PAIR_COLLISION_GUARD79, PAIR_REOBSERVE_TIMEOUT2726, APPROACH_ARRIVAL_UNCONFIRMED1, APPROACH_TIMEOUT1, APPROACH_LOST1. hook 횟수이며 물리 실패/I/O 횟수가 아니다. 문 대기 각각1회·0.05/0.05/262.4초, 사전 정의 교착0·로봇 접촉 episode0. r3의 장시간 차례 대기는 교착0과 별도로 남긴다. 명령11037건 중 주행509건(r1 135/r2 374/r3 0), 최소0.10초 미만0·혼합 축0. 공동 파지 옆걸음 예외는 이번 물리에서는 미도달이다.

세 카메라 각각5493프레임의 렌더 local pose가 모두 고정 S2 v3 마운트와 같고 frame 시각도 일치한다. GT는 종료 후 평가에만 사용했다. 모델 호출0, raw16512개·527247937bytes의 해시 전부 일치. [평가와 단계](smoke-summary.json), [원래 종료 결과](smoke-result.json), [raw 검증](raw-verification.json).

## 속도 — 동일 입력 재생과 물리 창을 분리

| 측정 | 이전 v1 | 새 v2 |
|---|---:|---:|
| 같은 저장442프레임 cProfile wall | 65.3804 s | 51.5094 s |
| 내용 검사 | digest9.16345 s | snapshot0.38836 s |
| 실제 posterior 요약 | 27회 / 0.91960 s | 27회 / 0.81876 s |
| 명령·포즈·입자·가중치·RNG 해시 | 동일 | 동일 |

잠금 내 별도 프로세스 측정에서21.2% 감소했다. profiler overhead 포함, 물리·렌더 제외이며 단일 비교다. 82.6초/5694회 반복 요약은 이전 캐시 도입 때 이미 제거됐고 이번에는 그 후 남은 내용 digest를 줄였다. 관측 외 명령 예측으로 posterior가 변해도 무효화해야 하므로 단순히 카메라 프레임 시각만으로 캐시하지 않는다. [새 profile](profile-summary.json), [독점 잠금](profile-lock.json).

실제 v149는 **875.0666 wall / 277.6 SIM = 3.15226**, 목표≤3 **미달**. v148의4.27063과 실행 구간·행동이 달라 동일 작업 속도 개선율로 계산하지 않는다. 실제 비용은 physics289.67s, capture195.82s(그 안 render170.71s), JSON append2.35s다. 중첩 timer는 합산하지 않는다. 후속 물리 속도나 완료를 추정해 채우지 않는다.

4배속 대표 영상: `/Users/changmin/projects/ugrp/outputs/s3fix4-20261009/views/v149/execution.mp4` (1374프레임/68.7s), [재생](http://127.0.0.1:6007/video/d194007738b1179bdcdc). native TensorBoard 새 스냅샷 `1009-s3-v149`와 `1009-s3-cache-verified`, v148 baseline을 구분했다. [저장 뷰 링크](tensorboard-link.json), [실제 scalar 검증](tensorboard-values.json). 원본은 로컬 보존이며 GitHub에는 기록·해시만 올라간다. 테스트 합성 자료는 공용 TensorBoard에 게시하지 않았다.

다음 물리 제안: 먼저 저장 v149에서 r2의 이동 후0.388m 오차와 접근 재시도를 오프라인 분리하고, 후속 pre-GO 재대기 sweep을 포함한 새 번들로 집기 이후 진행을 한 번 확인한다.
