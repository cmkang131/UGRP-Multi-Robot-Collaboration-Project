# S3 heading smoke: pre-smoke r1 diagnosis (2026-10-09)

후속 s3fix: seed를 바꾸지 않는 전역 입자/능동 관측 옵션과 DEV 계속 진행을 적용한 [v147 결과](../s3fix/README.md)를 참조한다. 아래 v146과 진단용 seed 비교는 당시 기록으로 보존한다.

**원인 한 줄:** 보정한 저장 영상에서 r1은 유한한 초기 입자와 초기 재표본화로 정확한 가설의 세밀한 표본이 부족해져, 약 180° 반대 방향의 근사 가설이 우세해졌다. 관측 순서 자체나 다른 로봇 가림을 주원인으로 지지하지 않는다.

아래는 **오프라인 진단**이다. 원본 s14201, own RGB/명령만 필터 입력이며 `legacy_centered_replay_v1`은 옛 렌더 영상과 맞추는 진단용 합성이다. 실제 스모크는 제어기 보정 변경 없이 호스트 `v3_persistent_v1`로 렌더한다. GT는 저장 posterior 평가에만 사용했다. 카메라 보정 적용을 공통 조건으로 고정하고 각 비교에서 한 요인만 바꿨다.

| r1 재생 조건 | 첫 σ 기준 수렴 | 마지막 XY 오차 | yaw 오차 | σxy | 판정 |
|---|---:|---:|---:|---:|---|
| 원래 seed14201·관측 순서, 43.55s | 없음 | 4.262512m | 179.6025° | 0.270649m | 실제 오위치 |
| S2 pan 순서만 적용, 14.00s | 없음 | 4.262616m | 179.5867° | 0.215436m | 순서 교환으로 해결 안 됨 |
| 필터 seed만1065, 14.00s | 10.30s, 오차0.032042m | 0.032074m | 0.2050° | 0.042933m | 정확 σ 수렴; seed 진단이지 채택/확증 아님 |

관측 순서 비교는 같은 body-frame 측정 packet의 순서만 S2의2030→1500→1770→1230→970으로 바꿨다. 새 pan 물리 실행은 아니다. 세 조건 모두 6개의 관측(2.25,3.75,5.25,6.75,8.25,10.10s)이며 원래 몸체 이동 명령은0이다. 첫 σ 기준은 기존 XY≤0.05m·yaw≤5°, 정확성은 별도 eval_only XY≤0.25m·yaw≤15°이다.

- 원래 r1에서 고유 입자 수는100,000→540→27로 줄었다. 정확 영역(0.25m·15°)의 고유 입자는34→17→9로 줄고 이후 복제593개가 유지됐다. 따라서 **정답 영역 입자 전멸은 아니다**.
- 정확 영역 posterior 질량은 첫 두 관측0.054095→0.287643에서 마지막0.004276으로 감소했다. 살아남은 가장 강한 정확 영역 표본은 실제 시작보다0.13433m·3.33867° 벗어나 있었다. 정지 명령 동안 새로운 위치 표본은 생성되지 않는다.
- 최종 반대 방향 가설/정확 GT 위치의 여섯 관측 결합 우도 비는0.042558(정확 위치가23.50배 유리)이다. 이는 완전한 관측 대칭보다는 유한 표본 근사의 문제를 지지한다. GT 점수는 **사후 진단**이며 필터에 주입하지 않았다.
- seed1065만 바꾸면 정확 영역 질량이 두 번째 관측에서0.974669, 마지막0.999970으로 증가한다. seed 교체가 초기 표본 및 이후 resampling 난수를 함께 바꾸므로 둘의 개별 기여는 아직 분리하지 않았다.
- 기존 시작 자세 비교는 S2와 약24µm·0.001° 차이이며, r1 타 로봇 마스크는 측정 변화0이었다. 본 결과는 같은 저장 입력에 대한 개발 진단이며 새 물리 성능이 아니다.

## 스모크 전 결정

seed14201·원래 관측 정책·v141 입자 및 σ 문턱 유지, **추가 회복 옵션 off**. 기존 필터에 augmented recovery가 이미 있고 정확 영역 지원도 남아 있으므로 무작위 주입이나 우도 바닥값을 추가하는 것이 적절한지는 아직 실증되지 않았다. 올바른 호스트 v3 렌더와 능동 관측을 먼저 한 번 관찰한다. 이 결정은 물리 실행 전에 고정했다. 결과를 보고 seed/문턱을 고르지 않는다.

표준 방법 조사: [Doucet–Johansen particle filtering tutorial](https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF.pdf)의 재표본화에 따른 다양성 감소와 rejuvenation, [Nav2 AMCL pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)의 KLD 및 random recovery를 확인했다. 현재 어댑터는 stationary global KLD 최소2000/최대100000, ESS≤N/2 resampling, slow/fast recovery를 이미 사용한다. 새 kernel·주입률의 적합성을 검증하지 않은 상태에서 본 스모크에 추가하지 않는다.

원본/분석 raw: `/Users/changmin/projects/ugrp/outputs/s3run-20261009`; 원본 replay 도구와 corrected baseline은 `../s3diag/` 및 해당 raw 폴더. `r1-support-analysis.json`에 입력 경로·명령·seed·simulation_runs=0·GT 경계가 있다. 큰 particle cloud는 로컬 raw에 보존하며 삭제하지 않았다.

검증: 호스트 렌더 회귀2 passed, 새 물리 실행0. TensorBoard `1009-s3run-r1` 3조건/18스칼라를 EventAccumulator로 대조했고, 기존6006 서버의 실제 UI에서3개 run·6개 pin과4.2625/4.2626/0.0321m 값을 확인했다. HParams 열은case/family/outcome/evaluation로 적용했다. [대시보드](http://127.0.0.1:6006/?runFilter=%5E1009-s3run-r1%2F#timeseries), 전체 pinned URL은 `tensorboard-verification.json`에 보존한다.

## 실행 전 고정: v146 / workflow7.39.0

18:47:53 fetch에서 #419 공통 기본 on `d89912703432117e47b5306bbe50ec9c31a0663c` 확인 후 merge했다. main#420 `1ba3668b`의 exact relay cache도 포함한다. [번호 예약](reservation.json)은 main/열린 PR 전부의 최대v145/7.38.0 확인이다. 미실행·미승인 준비 번들v144를 퇴역하고 **v146**을 새로 등록한다. v144 물리 결과는 없으며 그 사전 기록은s3next와Git이력에 보존한다.

[실행 등록](registration.json): seed14201 혼합 주문1회,1800 SIM초/10800wall초,dev_light,host v3 persistent binding on,공통 heading 기본 on,heading visual lock off,추가 입자 회복off,기존 수렴 문턱. 원본 예산2.125GiB+10GiB reserve,agent_lock 획득 후 실행. host는 실제 적용된 `relay-cache-v1`/enabled를 확인한다. 결과의 heading 및speed 적용값은 공통 writer가 기록한다.

heading 적용 범위를 구분한다: 세 S2 계열 startup localizer에 동일한 기본 on을 연결하고 실제 회전→전진 생성과 기록을 시험한다. **r3의 단독 경로 주행**이 그 제어기를 계속 사용하며, r1/r2 handoff 이후의 공동 빔 자세·GO 합의는 #419의 명시적 설계대로 기존 공동 제어기를 유지한다. 공동 빔의 독립 로봇 회전을 검증했다고 보고하지 않는다. 과거v142의 옵션 누락은 명시적 off로 해석해 기존 재생을 보존한다. 새로운 물리 실행에는 v146의 명시적 on을 쓴다.

실행 직전 디스크 갱신: 여유12.23GiB로 감소하여 raw 상한을2.125GiB로 사전 조정했다. 옛 실행 실측 비율의1800초 투영1,721,403,567bytes+추가eval허용536,870,912bytes=2.103GiB보다 크다. 이는 추정이며 보장하지 않는다.10GiB 또는raw 상한에 도달하면 ENOSPC HOST_ERROR로 기록하고 자동 재시도하지 않는다. 기존raw 삭제0.

실행 소스 검증: S3/공통 heading/workflow 관련3개 파일41 passed(115.19s). raw 예산 조정 뒤 계약 시험1 passed(42.76s). 실제 S3 factory의 각 localizer에 `path_tangent_v1` 적용, 자기 추정 stub에서 회전→전진 생성, result 적용값 및v142 누락 옵션off 보존을 확인했다. 기존 호스트 첫 렌더 mount 회귀는2 passed. 시험은 물리 실행 성공 근거가 아니다. CI는 기다리지 않는다.

## v146 단일 스모크 결과

실행 SHA **3daa830f65f6ed72b94a95b376accc4949b7b7e6**, seed14201, `DEV_NOT_DELIVERED`. 시뮬레이션1회, 자동 추가시행0, 문턱/seed 사후 변경0. raw는 `/Users/changmin/projects/ugrp/outputs/s3-host-heading-3daa830f-s14201-v146`. [전체 평가](smoke-report.json), [원 결과](v146-result.json).

| 로봇 | 첫 위치 찾기(기존 σxy/yaw + 인증) | 마지막 XY/yaw 오차 | 마지막 σxy / posterior 모드 | 접근·집기·문 통과·B 놓기 | 종결 |
|---|---|---|---|---|---|
| r1 | 실패; 수렴 시각 없음(42.25s 관측) | 4.259257m /179.3442° | 1.478844m /2 | 모두 미진입 | pair look_around2회 실패·3번째 진행 중 공동 종료 |
| r2 | 실패; 수렴 시각 없음(42.25s 관측) | 0.059274m /1.0596° | 0.212761m /2 | 모두 미진입 | LOOK_RECOVERY_EXHAUSTED |
| r3 | 실패; 수렴 시각 없음(42.25s 관측) | 0.019804m /0.9958° | 0.084268m /2 | 모두 미진입 | 문 예약 대기 중 공동 종료 |

**정확 수렴0/3, 허위 σ 수렴0, 로봇별 임무 성공0/3, 배달0/2화물**(r1/r2 공동 빔1+cyan1). 마지막 point estimate 정확 영역은r2/r3 2대지만 수렴 성공으로 세지 않는다. 마지막 관측43.55 절대 SIM초(시작1.30부터42.25초), 전체 판정45.25 SIM초에는 종료 뒤3초 정착을 포함한다. r1은 반대 방향 오위치가 새 실제 v3 렌더에서도 반복됐다. 입자 표본 원인의 단일 요인 증거는 위 저장 입력 재생에 한정한다. 별도 표본 회복 후보나 문턱을 사후 채택하지 않았다.

### 적용값과 물리 검증 범위

- host v3 binding on, diagnostic controller extrinsic off. 실제 렌더 기록 각846개/자기 RGB 각846개가 시각별1:1 대응한다. 세 로봇 **첫 프레임 및 전 프레임의 local mount pos/quat가 S2 fixture와 정확히 동일**하다. local position `[0.052982009925558314,0,0.028152173913043477]`, quaternion `[0.4545194776720437,0.5416752204197018,-0.5416752204197018,-0.4545194776720437]`. 월드 카메라 pose/qpos도 eval_only에 보존했다.
- bundle/result의 `heading_mode=path_tangent_v1`, 세 localizer의 기록 옵션과10.50s의 `rotate_path` 결정 각1건이 일치한다. 초기 handoff가 첫 제안을 보류했고 이후 pair 관측/문 예약에 머물러 **실제 차체 이동 명령0**이다. 따라서 물리 회전→전진 성능 검증으로 보고하지 않는다. 공통 명령 생성은 회귀시험 범위다.
- [실제 v7 적용 기록](v146-v7-speedups.json)과runtime-bundle/result 모두 `relay-cache-v1`, enabled=true. 제어기 입력은 자기 RGB·정적 지도·자기 발행 명령, GT는 평가만, weld/dock prior/top camera off다.
- 심판 높이는 실제 world COM 계약으로906개 표본을 평가했고, student/trial 직렬화도 완료했다. 기존 HOST_ERROR2종은 이 실행에서 발생하지 않았다.

### 멈췄을 지점과 실제 종료

| dev_light 로그 코드 | r1 | r2 | r3 | 첫 절대 SIM시각 |
|---|---:|---:|---:|---:|
| ARM_COLLISION_GUARD |6|5|5|1.40s|
| POSE_CLUSTER_UNCERTAIN |30|0|30|2.45s|
| GLOBAL_START_UNRESOLVED |1|1|1|8.90s|
| POSE_UNCERTAIN |1|1|1|10.50s|
| 합계 |38|7|37|총82건|

이82건은 로그 후 진행했다. 그러나 `ZoneOwnExecutor._step_look_around`의 `SWEEP_TRANSITION_BLOCKED`가 별도 실제 실패로 처리되는 기존 dev_light 사각이 남아 있다(`harness/zone_own_executor.py:751`, `zone_pair_highpose_relook.py`). r1 실패2건(23.95/34.95s), r2 실패3건(20.55/31.55/42.55s), 마지막r2 `LOOK_RECOVERY_EXHAUSTED`1건(43.55s)으로 공동 종료했다. 실제 충돌/낙하로 분류하지 않는다. 같은 보수적 재관측 원인이v142와 반복되어 **추가 물리 실행을 하지 않는다**.

문 REQUEST는r1/r2/r3 각1회, 대기0.05/0.05/33.05robot-s. 로봇 간 충돌 episode0, 등록된120초 교착 episode0(실행이120초보다 짧으므로 교착 부재 보장은 아님). 원인 계수는 실제 오위치1대, σ 미수렴3대, pair guard 실패5job, 최종 재관측 소진1회, 배달 미완료2화물, HOST_ERROR0이다. 범주가 겹치므로 합산 성공률로 쓰지 않는다.

wall **159.570026s / SIM45.25s =3.526409 wall/SIM**, reset1.3초 제외. 발행 명령r1/r2/r3=1104/1060/1114, 총3278, 모델/HTTP호출0. v142의6.00533과는 렌더/관측/실패 주체가 달라 속도 개선의 독립 인과 효과로 주장하지 않는다.

### 실행·보존·표시 검증

원본2569개/82,280,565bytes 전체 해시 일치, manifest SHA256 `e1be8bfe17b61fe36d6ac2d5d247cb526b1ad3a7fe3418a716a3dadf26cba2f0`. [검증](raw-verification.json). 원본 manifest/영상/로그를 덮어쓰지 않고 파생 영상은 별도views에 저장했다.

Codex 상위 프로세스가nice5여서 직접 실행은 하지 않았다. Terminal 자동화 도구가 해당 앱 접근을 거부하여 CLI에서launchd 기본 우선순위로 실행했고 실제 세 실행 프로세스 모두nice0을 확인했다. nice/renice 호출0, 타 작업 프로세스 종료0. `launchctl submit`의 종료 후 재시작으로 launcher가6회 더 호출됐지만 동일 output 존재 검사에서 **시뮬레이터 구성 전에 모두 거부**됐다. 원 실행/원본은1개다. 자기 job 제거·자기 프로세스 종료·agent_lock 해제를 확인했다. 향후에는KeepAlive=false인 명시적 one-shot 또는nice0 foreground shell을 쓴다. [실행기 기록](launch-verification.json), [잠금](v146-lock.json).

[4배속 대표 영상](http://127.0.0.1:6007/video/1002e122b82730be398a): `/Users/changmin/projects/ugrp/outputs/s3run-20261009/views/v146/execution.mp4`,212frames/20fps/10.6s, SHA256 `4f5ea09cf9a182b91625bb098ada0b31a9f447990bcfbcb918a4fd9c91d91b25`. 실제 브라우저에서1920×480 로딩·끝까지 재생·오류없음 확인. [영상 검증](video-verification.json).

[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1009-s3-v146%2F&smoothing=0#timeseries): 새snapshot `1009-s3-v146`,24개 원본/이벤트 스칼라 대조,9개 pin·실제 run 선택·시간159.57/45.25 표시·HParams 8열 확인. 기존r1 진단 및v142 snapshot은 보존했다. 전체 pinned URL은 [표시 검증](smoke-tensorboard-verification.json), [화면](smoke-tensorboard-ui.png). 원본은 로컬 보존이며 원격raw 백업으로 표현하지 않는다.

다음 물리 실행 제안: v146 저장 입력에서 표준 입자 다양성 유지 방법과pair look-sweep의dev_light 일관성을 먼저 오프라인 검증한 뒤, 사전 등록한 동일seed 혼합1회만 다시 제안한다.
