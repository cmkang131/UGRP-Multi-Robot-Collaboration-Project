# s3fix7: 문 임대·근접 RGB 정렬·입자 고갈 (사전 등록)

등록 시점: 2026-10-10, 후보 재생 및 새 물리 실행 전. 기준 소스 3bb4f4c8,
main 속도 변경 merge 7362820. speedctrl2의 공통 가속/기록 모듈은 수정하지 않는다.

## 고정 비교·선택 규칙

원본은 s3fix6과 같은 네 실행: S3 v149/v150 seed14201의 r1–r3,
자기 지도 55001/55002 (총 8개 궤적). 영상과 발행 명령 고정, GT는 평가 프로세스만 읽는다.
동일 원본 재생은 폐루프 임무 성공이 아니다. seed, 관측 우도, 수렴 문턱을 바꾸지 않는다.

| 후보 | 추적 중 재표본 조건 | 재표본 뒤 처리 |
|---|---|---|
| B off | 역사적 구현 그대로 | 그대로 |
| R1 ess_v1 | ESS < N/2 | 없음 (자기 지도는 이미 같은 조건) |
| R2 roughen_v1 | ESS < N/2 | Gordon Gaussian jitter, 각 축 σ=0.2 E N^(-1/3) |
| R3 roughen_floor_v1 | ESS < N/2 | R2 + 실제 posterior covariance 하한: XY 각 축 0.02m, yaw 1° |

전역 시작 분포/능동 pan은 보존하고 추적 단계에만 적용한다. yaw 범위는 원형 평균에 대한
wrap 잔차로 계산한다. R2는 논문의 예시 K=0.2를 그대로 고정한다. R3의 2cm/1°는
미리 정한 개발용 하한이며 보정된 정확도나 논문 권장값이라고 주장하지 않는다.
하한은 보고 숫자만 부풀리는 대신 S3 입자 분포, RBPF 조건부 covariance에 적용한다.
RBPF의 지도/입자 조상 연결은 유지한다. ESS와 고유값, 고유 입자 수를 전후 기록한다.

유효성: 모든 원본 프레임/명령 완료, 비유한 수 0, B 원본 동등성. 선택은 일관성 우선이나
8개 **각 궤적** RMSE와 마지막 위치 오차가 B+1e-9 이하이고 >3σ 비율이 비악화해야 한다.
그중 pooled >3σ가 엄격히 줄어드는 후보만 채택하며 pooled >3σ, pooled RMSE,
R1/R2/R3 순으로 결정한다. 일치하는 전체 covariance가 있는 자기 지도만 full NEES를 낸다.
모두 탈락하면 smoke는 off. 본 자료로 하한/계수 재튜닝하지 않는다.

재생 시작 전 계산 절약: B 네 개는 s3fix6의 봉인된 결과를 유지한다. 해당 소비 경로의
바이트/AST 동일성을 검사하고, main 이후 차이는 재생에서 호출하지 않는 물리 backend의
reset/close/write_receipt뿐임을 별도 AST로 증명한다. 추가 PF 옵션 off는 identity다.
symlink와 원래 SHA/receipt를 남기며 새 실행이라고 세지 않는다. 후보12회만 새로 재생한다.

## 통합 수정과 단일 smoke

문: 문 근처에서만 요청, 양쪽 동시 요청은 공개 팀 순서로 결정. 임대/진행 타임아웃은
이전 epoch의 차체 명령을 먼저 차단한다. 점유 중이면 자동으로 다른 팀에 문을 주지 않고
자기 추정 기준 문 밖 이탈을 확인해야 다음 팀을 허용한다. GT 위치는 사용하지 않는다.
기존 whole-job 예약은 off 경로에 보존한다. 문 밖 집기/접근은 진행한다.
DEV에서는 σ 확장만으로 문을 점유했다고 간주하지 않는다. nominal 자기 추정 형상으로
통과/양보하고 추가 σ 여유 때문에 막혔을 경우 `DOOR_POSE_UNCERTAIN`을 기록한다.
정식 경로는 σ 여유를 유지한다. lease 점유/epoch 상호배제 자체는 DEV에서도 유지한다.

정렬: 기존 자기 RGB 빔 오차의 폐루프 정렬을 실제 tick까지 통과시킨다. dev_light에서
PF 재관측 가드가 재진입 루프를 만들면 would_stop 후 동일 RGB 정렬을 진행한다.
영상 정렬 성공을 조작하지 않는다. 일찍 관측→고정 hover→가려진 마지막 하강·닫기 순서를 유지한다.
기존 calibrated arrival silhouette 검사도 PF 목표 도달 전의 접근 중부터 검사한다.
기존 drive 자세·명령 안정화·프레임 신선도·pixel bands를 모두 만족할 때만 같은 `_arrive`로 넘긴다.
별도 거리/픽셀 문턱을 만들지 않는다. PF가 잘못된 목표 도달을 주장할 때까지 상자를 밀며 진행하는
경로를 줄이려는 후보이며 새 물리 효과는 아직 미확인이다.

회귀: 양쪽 동시 요청, 임대 만료, 무진행, 오래된 epoch, reset/재시도, 실제 motor stub port.apply,
PF σ가 크거나 fix가 오래돼도 RGB 정렬에 도달, hover 이전 관측과 blind 하강 순서.
관련 시험만 초록 후 commit/push. 이후 최댓값 다음 번들로 dev_light smoke **1회**.
v3 마운트/heading 기본 on, 공동 운반 옆걸음 예외 유지. agent_lock 순서, CI 대기 없음.
raw는 primary outputs, ENOSPC=HOST_ERROR, 10GiB 여유 유지. 기존 실행/영상 보존.

## 표준 방법 조사

- [Gordon, Salmond, Smith 1993 §4.2](https://people.bordeaux.inria.fr/pierre.delmoral/gordon-salmond-smith-1993.pdf): 재표본 복제에 따른 다양성 손실과 Gaussian roughening, K=0.2 예시.
- [Musso, Oudjane, Le Gland 2001](https://link.springer.com/book/10.1007/978-1-4757-3437-9): regularized PF 장의 서지 확인. 전문 미확인; 세부 공식을 구현했다고 주장하지 않는다.
- [ROS AMCL pf.c](https://github.com/ros-planning/navigation/blob/noetic-devel/amcl/src/amcl/pf/pf.c): ESS 기반 selective resampling. 이 저장소 기존 ESS 구현 재사용.
- [Gray, Cheriton 1989](https://www.cs.cmu.edu/afs/cs.cmu.edu/academic/class/15712-s12/www/papers/gray89.pdf): 유한 lease. 물리적 통로의 비움은 lease 만료와 별개로 확인해야 한다.
- [Hutchinson의 visual servo 자료](https://faculty.cc.gatech.edu/~seth/res.php?u=vs): 영상 특징 오차 피드백. 이 작업은 기존 calibrated own-RGB 정렬 경로를 복구한다.

## 결과

등록 당시: 후보 재생/새 smoke 0회. 아래 완료 기록은 그 뒤에 추가했다.

기록 진단: v151 r1/r2 각각 재관측 8회, `beam_obs` 0회, `v3_grasp_target` 0회.
543.3초 align 진입 재관측 이후 `fix_gap`이 RGB handler 전에 재진입했다.
문은 r1/r2가13.55초부터 작업 끝까지 USING을 유지했고 r3 대기909.05초였다.
v149의34/254 접촉은102.4–119.2초 접근 중 r2 바퀴–빔 접촉이다. 당시 approach GO와
정렬은 시작되지 않았으므로 RGB 정렬 법칙의 접촉으로 합산하지 않는다. [수치](diagnosis.json).

main 병합은 v151 봉인에 포함된 `sim/final_environment_checks.py`를 변경했다.
v151 봉인을 완화하지 않고 현재 코드 unit 시험 구성과 과거 실행 번들을 분리했다.
과거 v151 실행은 원래 SHA3ec2d781에서만 재구성하며, 새 물리는 새 번들152를 쓴다.


### 통합 사전 등록 보완 (후보 재생·v152 물리 실행 전)

- 문 비움 형상은 기존 v3 arm sphere + chassis + 공동 운반 공개 형상의 합집합이다.
  자기 발행 servo만 사용하며, 정식 경로는 XY/yaw σ 여유를 더한다. DEV는 nominal
  형상으로 진행하며 σ/오래된 유한 포즈 때문에 막혔을 조건을 would_stop으로 남긴다.
- 기존 공동 집기는 S2 단독 `real_pregrasp_v1`과 달리 hover에서도 새 빔 영상을 요구했다.
  같은 look-then-move 순서로, 기존 RGB standoff가 만든 anchor를 보존하고 고정 hover와
  마지막 하강으로 이어 간다. hover 프레임을 새 물체 관측으로 기록하지 않는다.
  발행 명령이 정해진 창을 벗어나면 reference를 무효화하고 보이는 정렬 자세에서 다시 본다.
  기존 30초 anchor 기준, 고정 하강 범위/시간, fresh-frame 검사와 mutual close GO는 유지한다.
  re-fix hover GO 뒤 segment/발행 명령 창/자세가 깨지면 실행 계약 실패로 정지한다.
  age만 30초를 넘은 DEV 경우는 would_stop 후 기존 상대 추정으로 계속한다.
  새 프레임이 없으면 hold하며, 원래 visual 시각과 command-window 시작 시각을 별도로 기록한다.
  근거 없는 정렬/파지 성공은 만들지 않는다. 기본 off 경로는 바뀌지 않는다.
- 임대 epoch의 revoke/regrant가 대기 시간을 감추지 않게, 연속 REQUEST >=120 SIM초와
  마지막 다른 소유 팀의 해당 120초 정지(<1cm XY, <5° yaw)를 추가 평가한다.
  GT는 사후 평가에만 사용하며 기존 unchanged-state 지표도 별도로 보존한다.
- 기다리던 자체 재생 드라이버만 소스 갱신을 위해 종료했다. 후보 시작 0회이며,
  speedctrl2의 실행·잠금은 변경하지 않았다. PF 선택 규칙과 모든 후보 계수는 그대로다.


추가 공개 코드 대조(2026-10-10, 후보 결과 확인 전): [Nav2 main pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)의 현재 재표본 경로는 KLD 개수 제한과 fast/slow 평균에 따른 무작위 주입을 사용한다. 그 경로에 selective ESS 구현이 있다고 주장하지 않는다. 이번 ESS 조건의 직접 참고 코드는 위 ROS1 noetic AMCL이며, 기존 S3 전역 KLD/augmented 정책은 그대로다. 2cm/1° covariance 하한은 Nav2 기본값이 아니라 사전 등록한 실험 후보다.

### 공분산 출처 표기 정정 (선택 기준 변경 없음)

재생된 자기 지도 `5b330946`의 `CloudOdometry.pose`는 최고 가중치 입자를 보고한다.
`CloudOdometry.covariance`는 가중 평균 주위 입자 분산 + 조건부 공분산의 합이다
(`harness/self_map_rbpf.py:134–146`). 두 값은 같은 프레임이지만 동일 중심의
Gaussian 쌍은 아니다. 앞선 “일치하는 full covariance”라는 서술은 정확하지 않았다.

`xy_nees_mean`/`xy_nees_gt_11_829_fraction`의 기존 JSON 필드와 수치는 출처 연결을
위해 유지하되, 새 표에서는 **보고 위치·공분산의 이차 오차 eᵀP⁻¹e**로 표시한다.
Gaussian 일관성 인증·정상 chi-square 통과율이라고 해석하지 않는다.
S3 역시 최고 cluster 위치와 전체 XY 분산을 보고하므로 스칼라 >3σ를 보고값의
과신 진단으로만 해석한다. 실제 위치 오차·RMSE의 평가 좌표계는 바뀌지 않는다.

사전 등록된 각 궤적 RMSE/끝 오차/보고 >3σ 비악화 및 pooled >3σ 개선 규칙은
그대로다. 이 표기 정정으로 후보 계수·seed·평가식·채택 기준을 변경하지 않았다.

## 저장 재생 완료와 v152 실행 고정

고정 소스 `a6ff738f`의 후보 12회가 모두 원본 프레임을 끝까지 처리했고 실행 오류는 0이다.
B 네 결과는 새 실행이 아니라 기존 봉인 결과를 소비 경로 동일성으로 연결했다.
[32행 비교표](comparison-table.md), [선택/해시 원본](comparison.json),
[입자/공분산 감사](diversity-evidence.json)를 보존한다. 세 후보 모두 사전 거부 조건에
해당하여 v152의 `resampling_diversity=off`로 고정했다. 계수·seed·선택 규칙은 바꾸지 않았다.

- R1: v149/v150 r1의 보고 >3σ 비율이 소폭 악화했다. 자기 지도 두 사례는
  B와 포즈·입자·가중치·RNG 해시가 동일했다([동일성](ownmap-ess-baseline-identity.json)).
- R2: 55002 RMSE 0.265523→0.509045m, 끝 오차 0.510407→1.002727m로 악화했다.
- R3: 55001/55002 RMSE 0.307760→0.391927 / 0.265523→0.367364m로 악화했다.
  보고 >3σ는 48.55→41.61% / 38.53→33.94%로 줄었지만 정확도 비악화를 충족하지 못했다.
- 직접 고갈 사례: 55001 R2의 67.1 SIM초, ESS 1.002/100→고유 입자 1개,
  jitter 폭 0, 실제 오차 0.123755m와 보고 XY 공분산 약 1e-10m².
  [사례](roughening-collapse-example.json). 범위 기반 roughening만으로 완전 붕괴를
  복구하지 못한 경우이며, 과신 해결을 주장하지 않는다.

v151 자기 추정/발행 servo만 고정한 문 신호 재생은 18,182프레임에서 r3 차단 0프레임이었다
([신호 재생](door-saved-signals.json)); 기존 whole-job 예약의 909.05초 대기와 비교한
open-loop 프로토콜 근거이며 새 이동/통과 성공이 아니다.

새 번들 최대 번호를 main+열린 PR 10개에서 다시 확인해 **v152 /7.45.0**을 등록했다
([재확인](bundle-reservation-final.json), [실행 계획](registration.json)).
DEV smoke는 14201 **한 번**, 문 lease와 자기 RGB 정렬 on, 추가 PF 옵션 off,
v3 호스트 마운트·heading 기본 on·공동 운반 옆걸음 예외를 유지한다.
TensorBoard는 기준선 8개 기존 이벤트를 재사용하고 후보 24개만 새로 변환한다.
소스·관련 모듈 시험 초록·push 뒤 실행하며, CI 완료와 병합을 기다리지 않는다.

S3 r2의 R3 끝 오차는 v149 0.387965→0.108691m, v150 0.409033→0.093265m로
줄었지만 보고 >3σ 비율은 76.32→77.60% / 79.42→80.53%로 늘었다.
수치적 공분산 붕괴 억제와 실제 오차·전체 시간의 과신 개선은 같은 판정이 아니다.

실행 전 변경 3시험 파일 **34 PASS /129.82s**, 전체 단계 **68개·3190명령·오류0**,
양쪽 문 요청 **3경계·9 native motor 명령·오류0**.
[검증](preflight-v152.json), [전체 단계](offline-sweep-v152.json),
[문 경계](opposite-door-v152.json), [동일 입력 기본 off 바이트 비교](off-equivalence-v152.json).
PF 재생 소비 소스는 비교 봉인 뒤 바뀌지 않았고, 원본 워크플로 카탈로그는 main과 같다.

## 10/10 v152 단일 smoke 완료 — 문 대기는 해소, 집기는 미달

실행 SHA **981baa95e77aa78e5ffd6bc87c172cbb97aea7ed**, seed14201,
`zone-s3-recovery-v152 /7.45.0`, 물리 시뮬레이터 **1회**다.
문 lease·자기 RGB 정렬 on / 추가 PF diversity off의 적용값을 번들과 런타임 기록에서
대조했다. 결과는 **DEV_NOT_DELIVERED, HOST_ERROR0, 로봇 성공0/3, 배송0/2**.
903.05 SIM초(세계 시각904.35)에 끝났고 wall3184.674초, **wall/SIM3.527**이다.
v151의3.600보다 낮지만 목표≤3 미달이며 조건·궤적이 달라 속도 대조시험으로 해석하지 않는다.
[전체 요약·원본 해시](v152-result.json), [실행 전 검증](preflight-v152.json).

| 로봇 | 첫 handoff XY 오차 / σ(m) | 첫 관측부터 시간 | 첫 자체 수렴의 XY 오차 / 시각 | 도달 단계 | 최종 XY / yaw 오차 |
|---|---|---|---|---|---|
| r1 | 0.02630 /1.84041 | 12.20s | 0.02551m /36.95s, 정확 | 접근→자기 RGB 정렬531.2s; hover0 | 0.74269m /146.09° |
| r2 | 0.03954 /0.20861 | 12.20s | 0.32010m /112.30s, **허위 수렴** | 접근→정렬531.2s→재접근→정렬551.6s; hover0 | 1.28663m /143.44° |
| r3 | 0.00389 /0.05831 | 12.20s | 0.00429m /13.95s, 정확 | 탐색·이동 반복; 집기0 | 0.00884m /139.34° |

첫 handoff는 세계 시각13.50s이며 점 추정 정확3/3과 posterior 인증0/3을 구분한다.
r2는 나중451.8s에 XY0.249982m/yaw5.21°로 기존 평가 문턱을 한 번 통과했다.
따라서 기록의 `correct_convergence=3/3`은 **한 번 이상 정확한 수렴 표본 존재**일 뿐
첫 수렴3/3 또는 계속 정확함을 뜻하지 않는다. 최종 σ는 r1/r2/r3
0.05428/0.02776/0.02604m, yaw σ3.18/1.67/2.99°로 후반 과신은 남는다.

### 세 원인의 관측 결과

1. **문:** v151은 r1+r2 whole-job 예약이13.55s부터 끝까지 문을 점유해 r3를909.05s
   기다리게 했다. v152 대기 r1/r2/r3는0.05/1.85/0.05s, 대기 episode0/36/0,
   로봇 충돌0·교착0이다. lease 만료7, 진행 없음29, clear4, grant40을 기록했다.
   만료 후 점유자는 통로를 비우는 독점 recovery만 다시 받으며 만료를 비움으로 간주하지 않는다.
   r3 이동 명령1855회로 로컬 상자 접근이 열렸으나 **짐을 든 문 통과·대향 교행 성공은 미검증**이다.
   대향 동시 요청→만료 경계→다음 소유자 이전은 앞의9명령 오프라인 회귀 근거다.
2. **정렬:** v151의 PF 재관측 veto가 RGB `_align`보다 먼저 실행되는 경로를 우회한 뒤,
   실제 own-RGB `beam_obs`는 r1/r2 **0/0→915/866회**, 모두 visible이었다.
   하지만 `v3_grasp_target`·pregrasp reference·hover·집기·운반·놓기는 전부0이다.
   마지막 RGB 빔 축 잔차는 r1/r2 0.34871/0.32604rad로 기존0.035rad 문턱보다 크다.
   즉 이번 잔여 실패는 보이지 않는 hover 이후가 아니라 **가시 상태의 정렬 미수렴**이다.
   고개/회전 응답·heading 축 선택 중 어느 것이 원인인지는 이 실행만으로 확정하지 않는다.
   일찍 관측→고정 hover→blind descent→상호 close 순서는 회귀에서 통과했지만 물리 진입0이다.
   v149 접촉34/254회는 이미 분리한 r2 앞바퀴 roller–beam 접근 접촉이며 이번 정렬 성공 근거가 아니다.
3. **PF:** 저장4실행/8궤적·후보12재생은 모두 완료했으나 ESS·roughening·floor 후보 모두
   사전 기준 미달이다. 선택은 off이며 과신을 해결했다고 주장하지 않는다. 표·고갈 직접 사례는 위 링크에 있다.

실제 종료는 **r3 LOCAL_TIMEOUT(세계901.35s), 이후3초 settle**이다. r1/r2는 align 중이며
별도 LOCAL_TIMEOUT으로 끝난 것이 아니다. 짐 낙하·기울기·집게 이탈·GO 실패·HOST_ERROR는
이번 종료 사유가 아니다. 최종 성공 판정0/3, 배송 실패 분류3개(로봇 분모, 주문은2개),
LOCALIZATION 분류1개(r3)이고 이 분류와 후반 실제 오차를 함께 읽어야 한다.

would_stop은 **17,895 hook 발생**으로 I/O 횟수나 독립 실패 개수가 아니다.
POSE_UNCERTAIN8982, PAIR_REOBSERVE_TIMEOUT6132, DOOR_POSE_UNCERTAIN1077,
SWEEP_TRANSITION_BLOCKED750, UNMEASURED_V3_CAMERA_POSTURE582,
APPROACH_SWEEP_TRANSITION_BLOCKED163 등 전체19종은 `v152-result.json`에 보존했다.
NaN/None 평가 제외0, 0.10초 미만 이동 명령0, 혼합 축0이며, 3대 각18,002프레임의
v3 렌더 mount와 시각은 S2 동결 receipt/자기 관측에 모두 일치했다.

### 보존·전달·후속 범위

raw: `/Users/changmin/projects/ugrp/outputs/s3-recovery-981baa95-s14201-v152`.
54,040파일/1,724,296,204바이트 전체 SHA 일치, 원본을 덮어쓰지 않았다.
대표 영상은 `outputs/s3fix7-20261010/v152-report/views/v152/execution.mp4`:
자기 RGB3개만 이어 붙인1920×480·20fps·4501프레임·225.05초·**4배속**이다.
영상은 제어 종료까지이고 이후 settle3초는 포함하지 않는다.
[재생](http://127.0.0.1:6007/video/17269c1e0c0f1df97aef),
[TensorBoard](http://127.0.0.1:6006/#timeseries),
[정확한 핀·실행 필터 링크/이벤트 검증](tensorboard-verification.json),
[UI 검증](ui-verification.json).

후보24개·기존 baseline8개 및 새 v15231개 scalar를 EventAccumulator로 다시 읽어 원자료와
대조했다. Chrome 강 프로필에서 물리2개/재생32개 선택·핀8/5개·HParams 지정4열을 적용했다.
HParams는 공유4425개 session group을 보여 Time Series의 실행 필터를 그대로 따르지 않는
UI 한계가 있다. 영상의 실제 시간 증가와 일시정지를 확인했다. 서버·다른 작업은 중단하지 않았다.
시뮬레이터와 무거운 후처리가 끝나고 잠금을 반납했으며 #424/#405에 순서 반환을 기록했다.
CI는 기다리지 않고 PR #416은 독립 검토 전 draft로 유지한다.

다음 물리 제안: **v152 저장 RGB/명령에서 근접 정렬의 각도 잔차·heading pulse 응답을 먼저
분리하고 오프라인 정렬→hover probe를 통과한 뒤에만 dev_light 1회를 제안한다.**
이번 작업에서는 추가 물리 실행·seed/문턱 재조정 없이 마친다.
