# S3 v147 수정·재시험 사전 기록 (2026-10-09)

19:22 KST, **아래 후보 결과를 보기 전 결정**: `s3_dev_light=continue_estimate_v1`, `global_diversity=kld_augmented_v2`, `mode_head_look=mode_information_v1`을 새 v147/7.40.0 혼합 스모크에 켠다. 모두 독립 옵션·기본 off이며 v142/v146 원본과 기존 hash-pinned 소스는 보존한다. seed14201(로봇별 기존 +0/+1/+2), 수렴 σxy≤0.05m/yaw≤5° 및 posterior 인증 기준은 바꾸지 않는다. 정확성은 eval_only XY≤0.25m/yaw≤15°. 실패를 보고 seed나 수치를 골라 바꾸지 않는다. 구현 버그는 별도 기록 후 고칠 수 있다.

## 표준 방법과 고정 후보

- [Fox 2003 KLD-sampling](https://www.robots.ox.ac.uk/~cvrg/hilary2005/adaptive.pdf) §3.2: 점유 bin 수로 표본 근사 오차를 제한한다. 기존 .5m/.5m/10° bin, epsilon .05, confidence .99 유지. 초기/상한을100000→400000, 최소를2000→8000으로4배 확장한다. 두 모드에 더 많은 표본을 배분하려는 자원 설정이며 두 모드 보존을 수학적으로 보장하지 않는다. 처음100000개를 보존하고 같은 RNG의 독립 map-uniform300000개를 추가한다. seed 선택·GT 주변 샘플링·모드별 임의 quota 없음. 움직임 시작 후 기존2000 tracking handoff 유지.
- [Nav2 AMCL pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)의 Augmented MCL: alpha_slow=.001/alpha_fast=.1, 주입확률max(0,1-w_fast/w_slow), map-uniform pose. 기존 EMA 수치 유지, 새 옵션에서는 Nav2/Probabilistic Robotics Table8.3의 매 관측 재표본화와 KLD 종료 규칙을 사용해 ESS가 높아도 recovery를 우회하지 않는다. 우도 바닥값·고정 주입률 추가0. Probabilistic Robotics §8.3.5 본문 직접 열람은 미확인, 공개 Nav2의 p258 주석과 실제 식은 확인했다.
- [Burgard/Fox/Thrun IJCAI1997 active localization](https://www.ijcai.org/Proceedings/97-2/Papers/080.pdf) §3: 예상 posterior entropy가 작아지는 센서 방향을 선택한다. 기존 자기 posterior/정적 지도/카메라 보정만 사용한다. 최대512개 가중 대표 표본, 보이는5개 열의 예측 벽 경계 센서로 모드와 관측의 상호정보량 합을 순위 proxy로 쓴다. 원래5 pan 완료 후 연결 모드가 여럿이면 기존 허용 wrist pan700/2300 중 미관측 방향을 최대2개 추가한다. 전체 기존120초 관측 예산 유지. 예측 시야는 필터 관측으로 주입하지 않는다. 새 RGB를 실제로 받아야 위치 개선 근거가 된다.
- DEV 진단은 검사값을 그대로 저장하고 veto만 우회하는 log-only 정책이다. 기존 pair own estimate·상태·발행 명령으로 진행하며 GT나 성공 인증을 만들지 않는다. σ 예산/관측 시한/위치 불확실/재관측 횟수 소진과 가드는 기록 후 진행, GO 합의·실제 명령/프레임 오류·짐 낙하/기울기/집게 이탈의 기존 실제 실패 감시 경계는 유지한다. 정식 경로는 옵션off로 기존 보수적 정지를 유지한다. 새로운 물리 감지기를 GT로 제어에 넣지 않는다.

## 고정 검증 집합과 실행 예산

저장 입력 재생은 v146 r1 seed14201 및 S2 v141 graduation seed1065–1070 전부, 원본 자체 seed/명령/영상 그대로, 처음14.00 절대SIM초까지만 비교한다. 모드 head 관측은 원본에 없는 새 영상을 만들 수 없으므로 저장 관측에 대한 선택 순위만 검증하고, 위치 수렴의 전후 비교는 동일 RGB/명령에서 입자 옵션 효과로 구분한다. baseline/candidate 첫 σ 수렴 시각·오차·yaw·허위수렴 수, 마지막오차와σ, sample/injection counts를 보존한다. 재생은 simulation0·GT 평가만. 보정한v142 원본 r1도 필요시 같은14초 범위의 보조 진단으로만 사용한다.

새 물리 스모크는 **1회**, v3 host binding on·heading 기본on·main#420 relay-cache-v1·dev_light. no dock prior/weld/top/GT control. 본 연구와 agent_lock 순서 공유, SIM1800초/wall10800초·raw3GiB+10GiB reserve. ENOSPC는HOST_ERROR, 자동 재시도 없음. 관련 시험초록→커밋/push→실행, CI 완료 대기 없음. [전체 번호 예약](reservation.json), 최신main6813f8a1 포함. 결과는 실패도 로컬raw와TensorBoard에 기록한다.

## 검증 진행 기록

변경2파일 시험27 passed(27.72초), 추가 head/소진 회귀 뒤 해당 파일10 passed(25.99초). 테스트용 균일 이미지가 이미지 gate에서 거부된 것과 diagnostic provider를M1로 계속 먹인 fixture 오류를 수정했다; 실 제어기의 입력 검사는 완화하지 않았다. 코드/사전 기록은main merge commit `a8707692`로push했다.

첫 오프라인 baseline 재생은 reset raw시각1.3000000000000178과 첫 frame1.3의 순서로 servo초기화보다 영상이 먼저 처리되어KeyError3으로 실패했다(관측 결과 생성 전). 기존s3diag 재생기의round(t,9)와 동일하게 초기 명령 시각을 정규화했다. 실패폴더`outputs/s3fix-20261009-a8707692/baseline-r1`은 보존하고새폴더`outputs/s3fix-20261009-replay-v2`에서 재생한다. 필터 수치·seed·문턱 변경0.

## 저장 입력 전후 (14.00 SIM초까지, 물리 실행0)

첫 σ수렴은 XY≤.05m/yaw≤5°, 인증은 기존 posterior 검사 추가. `—`는 고정 관측창 내 미수렴이다. 시각은 절대SIM초, 첫프레임1.30초를 빼면 관측 경과 시간이다. 각 셀 `시간 / 그때 XY오차m`, 마지막 열은14초의 오차/σ다.

|원본 seed|첫 σ수렴 전→후|posterior 인증 전→후|마지막 XY오차 전→후(m)|마지막 σxy 전→후(m)|허위 첫수렴 전→후|
|---|---|---|---|---|---|
|r1 (14201)|— → —|— → —|4.259 → 0.052|1.479 → 0.287|0 → 0|
|1065 (1065)|6.95 / 0.068 → 13.95 / 0.042|6.95 / 0.068 → —|0.047 → 0.042|0.037 → 0.049|0 → 0|
|1066 (1066)|10.55 / 0.042 → 13.65 / 0.048|10.55 / 0.042 → 13.65 / 0.048|0.052 → 0.049|0.030 → 0.041|0 → 0|
|1067 (1067)|— → —|— → —|0.042 → 0.024|0.093 → 0.098|0 → 0|
|1068 (1068)|12.70 / 0.159 → —|— → —|0.152 → 0.060|0.016 → 0.213|0 → 0|
|1069 (1069)|8.45 / 0.093 → —|10.55 / 0.094 → —|0.083 → 0.040|0.005 → 0.097|0 → 0|
|1070 (1070)|— → —|— → —|0.034 → 0.020|0.087 → 0.118|0 → 0|

S3 r1 최선 추정 오차4.259→.052m/yaw179.35→2.16°지만 수렴 인증0→0. S2 첫 σ수렴4/6→2/6, posterior 인증3/6→1/6, 전체 허위 첫수렴0→0; 입자 다양성과 매 관측 재표본화 묶음은 점 추정 정확도를 개선했으나 σ 수렴은 늦췄다. 둘을 분리한 인과 검증은 하지 않았다. 모든14재생의 무작위 주입0개로 주입 효과는 주장하지 않는다. 능동 head는 순위만 오프라인 검증했고 새 시야 효과는 물리 스모크 대상이다. 사후 수치/seed/문턱/ON 옵션 변경0. [원본 경로·해시·정밀 수치](replay-summary.json).

스모크 전 DEV 감사에서 진행 재관측 횟수 소진과 도착 영상확인 veto도 같은 log-only 정책에 포함했다. 고정 지도 경로가 막혔을 때는 기존 S2 DEV와 같이 현재 추정에서 목적지 직행을 시도하고 충돌 가드를 기록한다. 물리 충돌을 피한다고 보장하지 않으며 eval_only로 판정한다. 누적 소진 횟수는 지우지 않는다. GO/명령 오류는 계속 정지한다.

## v147 단일 스모크 결과

실행 SHA `0a6908215e7788f697d3d7c616846e9f6b82e608`, seed14201, workflow7.40.0, **물리 시뮬레이터1회**. 실제 종료는 **HOST_ERROR**(`ValueError: calibrated motion requires one axis`), S3 통과 아님. 추가 시뮬레이션/seed/튜닝0. 관련 시험 마지막10 passed(26.41초), 코드 push 후 agent_lock·nice0으로 실행했다. ordinary foreground 관리 실행기를 썼고 다른 작업 프로세스를 종료하지 않았다. lock 해제와 자기 세션 종료를 확인했다.

### 첫 위치와 단계

13.50 절대SIM초(첫프레임 뒤12.20초)에 초기 관측을 마치고 임무 제어로 넘겼다. 아래는 그 시각의 **현재 최선 추정**이며 수렴 선언이 아니다. 고정 σ/후방분포 인증은 셋 모두 미통과, 첫 인증 시각 없음, 허위 σ수렴0이다. GT는 종료 뒤 평가에만 썼다.

|로봇|초기 XY오차m / yaw오차°|σxy m / σyaw°|최선 모드 질량|첫 위치 인증|도달 단계 / B배달|
|---|---|---|---|---|---|
|r1|0.026297 / 2.011|1.840407 / 67.561|0.749531|실패(다중모드2개)|pair 접근 진입(22.50초); 목표 접근·집기·문 통과·놓기 미도달 / 실패|
|r2|0.039537 / 1.612|0.208610 / 7.346|0.996000|실패(다중모드2개)|pair 접근 진입(22.50초); 목표 접근·집기·문 통과·놓기 미도달 / 실패|
|r3|0.003887 / 0.576|0.058307 / 1.368|0.999875|실패(다중모드2개)|초기 관측 후 문 예약 대기; 접근·집기·문 통과·놓기 미진입 / 실패|

- 최선 위치의 평가 정확성3/3, 정확한 **인증 수렴0/3**, 로봇 임무0/3, 주문 B0/2. r1의 두 모드 질량이 약75%/25%이므로 작은 점 오차가 넓은 σ를 틀렸다고 증명하지 않는다. r2/r3도 잔여 모드가 남는다. 결과를 보고 σ/인증 문턱을 낮추지 않았다.
- 마지막 오차는 r1/r2/r3=0.027524/0.040873/0.008016m, σxy=1.840407/0.261974/0.058307m. 세 로봇 모두7방향을 실제 명령하고 자기 RGB를 받았다. r1은 augmented 주입727개, r2/r3는0개다. 저장 재생(주입0)과 새 능동 관측(주입 발생)의 결과를 구분하며 입자 수/재표본화/능동 시야의 개별 기여를 분리했다고 주장하지 않는다.
- r1/r2의 초기 `look_around`는 `LOOKED_POSE_UNCERTAIN`·unconfirmed로 마치고 실제 pair API가 접수되어 접근에 진입했다. r2가23.20/23.30초에 비영 차체 명령2회를 냈다. 나머지 비영 차체 명령0. 최대 초기 위치 변위4.335/2.504/3.658mm는 팔 움직임에 따른 정착도 포함하므로 성공 주행거리로 세지 않는다.

### would_stop과 실제 정지

기존 localizer89 + 새 pair 훅421 + 기존 pair CommandGuard1 = **511회 검사 발생**. 같은 상황의 연속 검사/서로 다른 훅을 포함하며 독립 실패511건을 뜻하지 않는다. 중첩 record에 복제된 event는 더하지 않았다.

|코드|횟수|
|---|---:|
|SWEEP_TRANSITION_BLOCKED|375|
|SELF_UNCERTAIN|4|
|POSE_UNCERTAIN|45|
|PAIR_COLLISION_GUARD|1|
|ARM_COLLISION_GUARD|23|
|POSE_CLUSTER_UNCERTAIN|60|
|GLOBAL_START_UNRESOLVED|3|

`LOOK_RECOVERY_EXHAUSTED` 자체는 이번 실행에서 발생0; 소진을 강제로 만든 실제 pair 회귀에서 계속 진행을 검증했다. 원본 σ, gate, posterior 인증은 수정하지 않고 검사와 veto를 분리했다. GO 실패·실제 입력/명령 오류는 계속 정지한다. 기존 감시 범위를 넘어 새 집게 이탈 감지기를 구현했다고 주장하지 않는다.

실제 종료 원인은 **혼합 축 pair 명령 ↔ 단일 축 S2 PF 보정 계약 불일치1건**이다. r2 첫 명령은 `(forward=.1157591675, left=.0210799025, turn=0, duration=.15)`이고 둘째에는 turn까지 포함된다. 저장된2명령을 `zone_solo_cyan_pulse_cal.profile_key`에 그대로 재입력하면 같은 ValueError를 물리0회로 재현한다. 기준상 실제 실행 오류이므로 DEV에서 계속 넘기지 않는다. 첫 명령은 이미 발행됐고 지연 입력 처리 중 예외가 드러났다. `commands_complete=false`를 보존한다.

기존 공통 `path_tangent_v1`은 bundle/result와 세 localizer에 실제 적용됐지만, `heading_scope`에 명시된 별도 coupled pair controller는 기존 연속 혼합 명령을 유지했다. **pair 주행까지 heading/pulse 호환을 검증한 것은 아니다.** DEV가 앞 가드를 통과시키며 이 잠재 통합 오류가 처음 노출됐다. 이번 요청의 단일 실행을 반복하지 않았으며, 이 새 오류를 수정 완료로 표시하지 않는다. 다음 후보는 단일 selector만 바꾸는 것으로 충분한지부터 접근·정렬·loaded carry 전 명령 어휘/시간 계약을 저장 입력으로 검사해야 한다. 참고 표준은 [공통 heading 구현의 Nav2 RPP 근거](../../2026-10-09-s2-heading/README.md) 및 `harness/zone_solo_cyan_path_heading.py`의 회전→전진·측정 pulse·coast·새 영상 피드백이다.

인과 실패 집계는 HOST_ERROR1건. 미완료 평가 기준(위치 인증3·배달3)은 원인6건과 구분한다. 문 REQUEST episode는 각각1, 대기0.05/0.05/9.85 robot-s, 충돌 episode0·120초 교착 episode0. 관측창이22.1초여서 긴 교착 부재를 보장하지 않는다. 낙하·기울기·집게 이탈·GO 실패가 실제 종료 원인은 아니었다.

### 시간·적용값·보존

wall **170.610534초 / SIM22.10초 = 7.719934 wall/SIM**. reset1.30초를 제외한 1.30→23.40 구간이며 오류 종료로 추가 정착 없음. 명령2490, 모델/HTTP0. v146의45.25초 종료와 관측 수/입자/실패 시점이 달라 속도 효과 비교로 쓰지 않는다. disk29.16GiB, raw 예산3GiB+10GiB reserve 확인. 별도 disk_report의 잘못된 section 이름 호출은 수정 후 `--sections fs`로 실제 여유 공간을 기록했다; 관리 실행기의 자체 디스크 검사도 통과했다.

호스트 실제 render_camera **로봇별443프레임 전부**를 S2 첫 프레임 보정 fixture와 대조해 local_position/local_quat 동일, 촬영 시각 대응도 동일했다. `v3_persistent_v1` 호스트 바인딩 유지, 제어기 외부 파라미터 맞춤 없음. #420 `relay-cache-v1` 적용enabled/physics_changed=false. no dock prior/weld/top/GT control 유지. 공통 장면 누락 조사표는 [기존 호스트/S4/자기 지도 표](../s3next/README.md)에 있다.

원본 `/Users/changmin/projects/ugrp/outputs/s3-continue-0a690821-s14201-v147`, 전체1360파일/44,068,436bytes 해시 일치. manifest SHA256 `d45be5056969043fc64aa914bfb97313b34882af1142e60e7c3ef1deb7eff30c`. raw 로컬 보관은 원격 백업이 아니다. 새 실험 기록/파생 결과만 Git 보존, 원본 덮어쓰기·삭제0.

- [정밀 결과/명령 계약 재현](smoke-report.json), [원본 해시](raw-verification.json), [영상 검증](video-verification.json), [TensorBoard 검증](tensorboard-verification.json), [오프라인 event 재로딩](tb-offline-readback.json).
- [대표 영상4배속](http://127.0.0.1:6007/video/55e09581104f18e7687e): 자기 RGB3개 병렬, 새 렌더0. 로컬 `/Users/changmin/projects/ugrp/outputs/s3fix-20261009-replay-v2/views/v147/execution.mp4`,1920×480,111프레임/20fps/5.55초. 모든 프레임 디코딩·브라우저 끝까지 재생·Range206 확인.
- [TensorBoard v146/v147 비교](http://127.0.0.1:6006/?runFilter=%5E1009-s3-v14%5B67%5D%2F&smoothing=0#timeseries), [같은 원본14회 오프라인 비교](http://127.0.0.1:6006/?runFilter=%5E1009-s3fix-replay%2F&smoothing=0#timeseries). 새 snapshot은 각각26scalar/14runs를 원본과 재로딩 대조,8pins와 HParams 지정 열 확인. 기존 서버/다른 공용 설정 키는 유지했다.

다음 물리 실행 제안: pair 전 단계의 heading·단일 축 측정 pulse 계약을 먼저 오프라인 연결·검증한 뒤 새 번들 동일seed 혼합DEV1회만 제안한다(이번에는 추가 실행 없음).

보고서 추가 뒤 off 바이트/새 번들 계약2 passed(24.28초),8 deselected. 실행 원본/설정은0a690821 그대로이며 보고서 커밋을 새 실행 SHA로 소급하지 않는다. PR#416 본문에 최신 실패와 다음 제안을 반영하고 CI를 기다리지 않는다.
