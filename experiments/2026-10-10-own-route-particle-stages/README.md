# egomap60 — oracle-x86 단계별 자기 위치 후보 비교

2026-10-10 사용자 승인: Mac 물리/재생0, 임시 oracle-x86 서버만 사용, egomap 동시 최대8개(S3와 공유). 기존 egomap59와 호스트가 다르므로 그 wall 시간/물리 숫자는 직접 전후 비교하지 않는다. 기본값은 기존이고 heading on·검출기·지도·motion v122 rotL·Manhattan·switchable·dev_light는 동결한다. PR405 DRAFT, 병합은 감독. 서버 임대 연장/구매0, 1시간 진전 없으면 중단·보고한다.

## 사전등록 (실행·후보 구현 전)

- 단계 seed60011/60012. 같은 oracle-x86에서 baseline 탐색 중 첫 자기 B 확인 시점의 전체 controller+physics 체크포인트를 만든다(최대150SIM초). B 미관측이면 준비 실패로 분모에 남기며 GT로 B를 주입하지 않는다. 기존 `scripts/dev_pair_checkpoint.py`의 전체 상태/스트림/RNG 보존 방식을 재사용한다. GT가 포함된 physics 상태는 환경 소유자에만, 제어기는 자기 상태만 사용한다.
- 각 동일 체크포인트에서 baseline/a/b/c 네 조건×2seed=8회, 각각 B 접근60SIM초 후 **단계 시험용 귀환**60SIM초. 후자는 자기 그래프의 시작 노드로 돌아가도록 명시적으로 전환한 DEV 진단이며, 상자+B를 모두 마친 전체 임무 성공으로 보고하지 않는다. 귀환 경로 단축0·강제 위치 잊기0. 270초 기존 전체 구간 예산은 변경하지 않는다.
- a `rbpf_population=particles_500_v1`: 단계 시작 시 기존 가중 경험분포를5개씩 분할(동일 pose/map, 가중치1/5)하여100→500. 즉시 새로운 정보를 만들지 않으며 후속 운동/관측에서 독립 표본을 얻는다. 전체 경로에서는 출발부터500. N_eff<N/2·기존 motion noise 비율 불변.
- b `rbpf_local_search=cartographer_window_v1`: 예측 주변 XY±0.1m·yaw±20°(Cartographer 원본 수치), 측정점의 예상 위치/검색창/기존 오차 여유만 포함한 로컬 reference. 기존은 이미±0.5m/±20° 및6m radius이므로 ‘새로 처음 로컬화’라고 주장하지 않는다. 격자/센서범위4m/기존 수락 문턱 불변.
- c `rbpf_candidate_gate=observed_sample_v1`: 현재도 전역 무작위 주입은 없다. Gaussian proposal에서 실제 뽑힌 pose가 기존 overlap/residual/search 조건을 만족하는지 검사한다(현재는 mode만 검사). 부적합 표본은 정합 거부로 처리, 센서 가중/재표본 생략·기존 odometry fallback 유지. prior 예측을 관측 검증 pose라고 부르지 않는다. GT/지도 외부 배열0, 문턱 재적합0.
- 점수: 단계별 실제 B 도착·거짓 선언, 귀환 선언 및 GT 시작점 거리≤기존0.20m, 종료오차/σ, 프레임>3σ 비율, 접촉, 표본 프레임/맵칸/관측영역 덮음. 실제 B 영역/GT 시작점은 평가 전용. 두 조건 모두 표본 누락·HOST/물리 실패 포함, 제외하지 않는다.
- 후속 자격: 두 seed 모두 유효 종료; paired 평균>3σ 비율이 baseline보다 상대10% 이상 감소; 평균 종료오차≤baseline×1.2; B 도착/귀환 선언 열세 없음; 거짓 선언0·접촉 baseline 이하. 자격 후보 중 >3σ 평균→종료오차 순으로 하나 선택(동률 a,b,c). 후보 조합은 이 단계에서 결과 후 새로 만들지 않는다. 자격0이면 전체 실행0으로 종료.
- 자격1개 이상일 때만 선택 구성으로 새60021/60022 전체 경로 각1회, 기존270SIM초/구간·상자/B/시작 귀환 판정. 짧은 단계와 합산 금지. 모두 예산/HOST 상태와 실패 원인을 기록한다. 결과 후 문턱·옵션 변경0.
- 서버 stage HOST 상한30분/회, 전체60분/회, one-hour-no-progress 감시. raw는 서버 `~/ugrp-sim/runs/egomap60-*`, 회수는 Mac `outputs/oracle-runs/egomap60-*`; 실행 소스 committed HEAD·host=oracle-x86·OSMesa·환경/동시실행 수·raw hash 기록. Mac은 편집/합성 단위시험/결과 표시만 수행한다.

## 참고 자료·적용 범위

- Grisetti/Stachniss/Burgard, T-RO2007 [원문](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa13/optreadings/GrisettiStachnissBurgard_gMapping_T-RO2006.pdf), §III-B Eq15–19: 현재 관측×운동 prior를 이용한 입자별 Gaussian proposal, §IV local convolved grid, selective resampling. 입자 수 증가가 과신을 해결한다고 보장하지 않는다. S3 500개 수치는 별도 PF/자료의 동기이며 자기 지도 결과에 합산하지 않는다.
- Cartographer [기본 설정 L35–39](https://github.com/cartographer-project/cartographer/blob/master/configuration_files/trajectory_builder_2d.lua#L35)와 [실시간 CSM 원본](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/scan_matching/real_time_correlative_scan_matcher_2d.cc): 예측 주변 고정 탐색창. Olson2009를 구현한 원본 구조를 따르며 기존 own-map 격자·카메라 벽점·motion prior는 보존한다. Cartographer 전체/서브맵90스캔 수명주기를 이식했다는 뜻은 아니다.
- c는 새 위치 생성법이 아니라 기존 정합 수락 검사를 실제 proposal 표본에 적용하는 기하적 검증이다. 실패 관측에서 억지로 일치하는 표본을 반복 추출하지 않는다(분포를 임의로 잘라 과신하지 않음). 대안 선택/문턱 튜닝 없이 고정 비교한다.
- 전체 상태 snapshot은 기존 DEV checkpoint의 source/stream hash와 renderer/lock 재생성 규약을 따른다. 재개 단계는 DEV_RESUMED_DIAGNOSTIC이며 본 연구/연속 완주 증거가 아니다.

## 구현·실행 전 확인

사전등록 f0ba9ee1. 합성 변경 모듈3파일25시험 통과(물리/녹화 재생0), legacy proposal off 결과/샘플 bytes 동일. stage seed는 동일 P1 시작 위치·지도에 새 난수seed만 사용한다. 서버 공유 venv에 cloudpickle이 없어 pure-Python cloudpickle3.1.2를 전용 `~/ugrp-sim/egomap60-deps`에 `--no-deps` 설치하고 해당 작업 PYTHONPATH에만 연결한다. 공용 venv/물리 의존성 변경0.

## x86 입장 오류와 이식 수정 (물리 전, 2026-10-10)

`prepare-60011/60012`는 launcher가 이미 만든 출력 root를 넘겨 `PRESERVE_EXISTING_OUTPUT`로 물리0 거부. 후속 `prep-60011/60012-r1`은 `P1_ASSET_LAYOUT_MISMATCH`로 물리0 거부. 네 시도 모두 원본 로그 보존, 성능 분모와 분리하며 성공 실행으로 대체 표기하지 않는다.

Mac/x86 layout 대조: patch 꼭짓점11개 값만 최대5.551115123125783e-17m(1 ULP) 다름. 벽 기하·길이·배치·PNG는 동일하며 libm sin/cos 마지막 비트 차이다. [Python math ULP/isclose](https://docs.python.org/3/library/math.html#math.ulp)의 표준 부동소수 비교를 따라 `wall_asset_numeric=libm_ulps_v1`(기본 off)에서는 patch 꼭짓점만4 ULP 허용, 다른 필드는 exact·PNG SHA exact를 유지한다. 재생성/이미지/XML 변경0. 성능 문턱과 무관한 서버 admission 수정이며 baseline/a/b/c 전부 동일하게 켠다. 허용범위 밖·다른 metadata·PNG 변조 거부 및 off exact·on XML bytes 동일을 합성시험으로 고정한다. 새 서버 실행 전 커밋한다.

첫 r2(60011)는 XML 통과 후 C++ compiler 부재로 RGB0·reset1.3SIM초에서 HOST_ERROR. 서버 Ubuntu 공식 g++ 패키지를 설치(공용 venv 변경0), 동일 NavFn 원본을 빌드한다. 전송/입장 반복을 줄이기 위해 checkpoint 객체를 정적 점검하여 stateless ctypes library의 표준 pickle reducer와 등록된 sensor stream alias 복원을 추가했다([Python pickle 재구성 규약](https://docs.python.org/3/library/pickle.html#object.__reduce__)). 센서 기록은 prefix hash 검증/새 출력으로 복사·append하며 판독/state/RNG 변경0, 별도 truth 입력0. 기존 checkpoint restore 기본값은 alias 복원 off. 합성 시험으로 원본 planner 경로 bytes·sensor alias를 고정, 물리 성능 결과가 아니다.

r3(60011)는14.2SIM초/72RGB에서 upstream PythonRobotics의 plot import 의존성 누락으로 종료. matplotlib3.11.2와 부속 패키지를 같은 전용 deps 폴더에 `--no-deps` 설치, numpy/physics/shared venv 불변; 원본 pursuit 단독 입력 검사를 통과했다. 60012-r2는67.6SIM초 자기B 확인 직후 checkpoint가 v7 exact relay의 local `lru_cache` closure 직렬화를 거부했다. 순수 memoization cache만 empty로 재구성하는 표준 `__reduce__`를 추가: DriveParameters·wheel direction·MjData/RNG 유지, cache hit/miss 진단만 새 프로세스에서 리셋되므로 초기 wall 시간에는 cold cache 비용 포함. 명령 결과 bytes 동일을 합성시험으로 고정. 이 실패도 raw/분모 별도 보존, 물리 결과를 성공으로 소급하지 않는다.

## 감독의 묶음 실행 규칙 반영 (2026-10-10 09:18 UTC, 후보 결과 전)

개별 실행→수정→다음 실행을 중단한다. 새 규칙 도착 전 시작된 두 준비 실행은 그대로 종료·보존한다. 60011-r4는150SIM초/751RGB에서 B미관측(준비 실패), seed 교체/예산 연장/다시 탐색0. 60012-r3는 진행 중이다. 준비 실패도 등록2seed 분모에 남기므로 **이번 후보가 하나의 유효 seed에서 좋아도 전체2회 자격 기준을 통과할 수 없다**. 이미 등록한 관문을 낮추지 않는다.

물리/후보 코드 고정 SHA=`0fa397aaed3797a6cc27823959de1dcfe1b49af8`. 이후 README-only 커밋은 동결 runtime을 바꾸지 않는다. oracle launcher SOURCE_SHA는 문서 포함 현재HEAD, 실제 자식의 source_sha/실행 cwd는 위 runtime SHA로 함께 보존한다. x86 archive의 이 SHA에서만 실행한다. Mac 물리/재생0. 코드 변경 파일 합성15시험 통과(이전 asset22시험 포함 관련37), CI대기0.

60012 체크포인트 저장 성공 후 복원 경로를 **8SIM초 스모크1회**로 확인한다. `bind(run,bundle=cap8_bundle)`로 budget만8초, 나머지 stage baseline동일. 스모크는 후보분모에서 제외하며 raw보존. 실패하면 후보 묶음을 보내지 않고 연결 수정·관련 시험을 한 묶음으로 한다.

다음 목록 전체가 이번 단계 묶음이다. 스모크 통과 후 실행 가능한 네 개를 한꺼번에 detached 발행한다(각 egomap server-slot,최대8). 미관측 seed의 네 개는 `BLOCKED_PREPARE_B_UNOBSERVED`로 명시해 실행하지 않는다. 묶음 중 계획/코드/문턱 변경0, 전부 terminal 후 raw를 함께 채점한다.

|이름|seed|profile|명령/상태|
|---|---:|---|---|
|egomap60-smoke-60012|60012|baseline|아래8초 복원 검사, 후보분모 제외|
|egomap60-stage-60011-baseline|60011|baseline|BLOCKED_PREPARE_B_UNOBSERVED|
|egomap60-stage-60011-a|60011|a|BLOCKED_PREPARE_B_UNOBSERVED|
|egomap60-stage-60011-b|60011|b|BLOCKED_PREPARE_B_UNOBSERVED|
|egomap60-stage-60011-c|60011|c|BLOCKED_PREPARE_B_UNOBSERVED|
|egomap60-stage-60012-baseline|60012|baseline|`-m scripts.run_own_route_particle_stages --mode stage --seed 60012 --profile baseline --checkpoint CP --output outputs/egomap60-stage-60012-baseline/data`|
|egomap60-stage-60012-a|60012|a|동일 명령, `--profile a --output outputs/egomap60-stage-60012-a/data`|
|egomap60-stage-60012-b|60012|b|동일 명령, `--profile b --output outputs/egomap60-stage-60012-b/data`|
|egomap60-stage-60012-c|60012|c|동일 명령, `--profile c --output outputs/egomap60-stage-60012-c/data`|

CP는 `egomap60-prep-60012-r3/data/checkpoints/manifest.jsonl`의 첫 자기B 확인 행(하나)의 file·sha256이다. 이름을 결과에 따라 고르는 것이 아니라 이 유일한 행을 기계적으로 사용한다. 공통 prefix: `ORACLE_HOST=oracle-x86 $S/oracle_run.sh WT NAME -- /usr/bin/time -v /usr/bin/env UGRP_EXECUTION_HOST=oracle-x86 MPLBACKEND=Agg PYTHONPATH=/home/ubuntu/ugrp-sim/egomap60-deps /bin/bash -c 'cd /home/ubuntu/ugrp-sim/src/0fa397aaed3797a6cc27823959de1dcfe1b49af8 && exec .venv-sim/bin/python ...'`. 출력을 각 run 절대 경로에 저장(동결 runtime 안의 symlink 유무에 의존하지 않음).

### 실행 목록 정정·코드 일괄 완료 (후보 결과 없음)

60012-r3의 첫B(67.6초) 저장도 local own-mask lru_cache 직렬화에서 실패했다. 이전 절의 old-runtime 스모크/후보 명령은 **미입장 취소**한다. 직렬화의 표준 reducer를 local lru wrapper 전체에 opt-in 적용하고, **전체 실제 제어기 객체**를 MuJoCo/녹화 없이 serialize→restore→지도/그래프 bytes 비교하는 시험을 추가했다. 원본 메모리/RNG/정책은 유지하고 순수 memoization만 cold cache. 단편 캐시별 긴 물리 재시도는 끝낸다.

최종 소스는 이 절과 코드가 포함된 새 커밋으로 전체 동일하게 고정한다. 기본 off/기존 physical 경로는 불변. 실행 목록:

|이름|seed/조건|고정 명령|
|---|---|---|
|egomap60-checkpoint-smoke-v2|60012/baseline|`python -m scripts.run_own_route_particle_stages --mode smoke --seed 60012 --output outputs/egomap60-checkpoint-smoke-v2/data` (4SIM초 저장+4SIM초 복원, reset포함≤10초)|
|egomap60-fixed-batch-v2|등록8슬롯/4실행 가능|`python -m scripts.run_own_route_particle_batch --output outputs/egomap60-fixed-batch-v2/data --smoke /home/ubuntu/ugrp-sim/runs/egomap60-checkpoint-smoke-v2/data/smoke-summary.json`|

batch는 `egomap60-prep-60012-batch`(자기B 시작 상태 생성, 기존150초 상한)와 앞 표의 stage8슬롯을 한꺼번에 등록한다. 시작 상태 생성은 후속 조건의 필수 선행 의존성이며, 완료 후 사람이 결과를 보고 수정하지 않고 **baseline/a/b/c4개를 즉시 모두 동시에** 발행한다. 60011은 이미 B미관측으로 확정됐으므로 물리 재실행 없이4슬롯 차단 유지. 60012 준비가 다시 실패하면4개 모두 차단, 자동재시도0. 모든 결과가 끝난 뒤에만 raw 공동판정, 유효seed 부족이면후속전체0. 이는 사용자 새 묶음 규칙에 맞춘 실행 어댑터 수정이며 실험 문턱 변경0이다.

旧 inline smoke 발행은 launcher의 중첩 shell quoting 문법 오류로 **프로세스/물리0** 거부됐다(후보 실행 아님). 원격 launcher는 수정하지 않고, 새 등록 CLI `--mode smoke`만 사용하여 복잡한 inline command를 없앴다. 변경 모듈 합성40시험 초록; whole-controller pickle, native handle, sensor stream, local cache, asset exact/off, batch8슬롯·비대체 규칙 포함. 이번 묶음은 이 코드/README SHA 한 개만 사용한다.

## 저장·복원 검증 및 호스트 중단 (후보 코드 동결)

실행 SHA **88efcd85bb8e8525a625cc0b508396faf7fbba04**, host=oracle-x86. 스모크는 저장4+복원4SIM초(초기 reset 포함9.3초), 두 단계 RECORDED·EXIT0. 이후 준비60012는 자기B를67.6초/338RGB에 확인하고 checkpoint를 저장했다(sha256 `9a5a4b28a1f59954681402b0b2924fd7659fd6db67e166d4bb768946cdb9db32`). 구 입장오류 실행과 같은 준비 구간의 제어·접촉·공분산·GT평가·프레임 원장5개와 RGB338/338장이 **bytes 동일**([검사](results/prefix-equivalence.json)). 이것은 준비 구간 동일성이지 완주 성공이나 연속 실행 전체와의 동등성 증명이 아니다. 스모크의 공용 checkpoint trigger 문자열은 `first_own_B_confirmation`으로 남았지만 실제 저장 원인은4초 시간 제한이고 B 선언은 false다. 후보 준비 checkpoint만 실제 자기B 관측으로 생성됐다.

감독 확인: **09:32:44Z 자동 전원 장치의 idle 판정 버그로 서버 정지**,09:39Z 재시작·장치 수정. EXIT143은 감독이 사후 표시한 호스트 중단이며 시뮬 실패가 아니다. baseline/b/c는 단계22.2SIM초, a는16.8초에서 중단(최종 result 없음). 네 원본은 그대로 보존하고 성능 표본과 합산하지 않는다([중단 기록](results/host-interruption.json)). 준비·스모크는 완료돼 반복하지 않았다.

감독의 같은 SHA/명령 재제출 지시에 따라 기존4조건을 **동시에 한 묶음** 재제출했다. 새 이름은 `egomap60-stage-60012-{baseline,a,b,c}-hostretry1`, 출력만 각각 `outputs/<이름>/data`로 분리했다. seed60012·profile별 옵션·기존 준비 checkpoint·120SIM초·SHA88efcd85는 불변이다. 명령은 앞 표의 `python -m scripts.run_own_route_particle_stages --mode stage --seed 60012 --profile <profile> --checkpoint <기존 checkpoint> --output <새 출력>` 그대로이며, 조건/코드/문턱 수정0·추가 스모크0·60011 대체0. 재제출 직전 MemAvailable61GiB, launcher의6GiB 미만 거부 규칙을 사용했다. 원본 및 재시도는 서로 다른 실행 이력으로 보존한다. 사전등록2seed 중 유효 준비1seed이므로 이번 비교로 후속 전체2회를 승인하지 않는다.

## 결과 — oracle-x86, 유효 seed60012 한 개 (확증 아님)

등록2seed×4조건=8슬롯 중60011의4슬롯은150SIM초 B미관측으로 차단,60012의4슬롯만 재제출 후 모두120SIM초/EXIT0 종료했다. 호스트 정지4건은 별도 이력이며 성능 표본에 합산하지 않았다. 모든 조건은 같은 자기B checkpoint에서 시작했고, GT는 아래 채점에만 썼다. 옵션/문턱 사후 변경0·후속 전체경로0회. [전체 수치·원본 경로·해시](results/comparison.json).

|조건|>3σ 프레임/601|종료오차 m|종료 σXY m|종료 오차/σ|경로 RMSE m|B 도착/귀환|거짓 선언/벽·로봇 접촉|wall s (wall/SIM)|최대RSS GiB|
|---|---:|---:|---:|---:|---:|---|---|---:|---:|
|기준선100|122/601 (20.3%)|0.437|0.084|5.21|0.320|0/1 · 0/1|0 / 0·0|513.3 (4.28)|1.581|
|a:500입자|10/601 (1.7%)|0.145|0.077|1.88|0.243|0/1 · 0/1|0 / 0·0|685.2 (5.71)|1.709|
|b:로컬창|122/601 (20.3%)|0.437|0.084|5.21|0.320|0/1 · 0/1|0 / 0·0|495.1 (4.13)|1.580|
|c:관측 표본 검증|233/601 (38.8%)|0.164|0.068|2.40|0.326|0/1 · 0/1|0 / 0·0|512.0 (4.27)|1.581|

σXY는 XY 공분산 최대 고유값의 제곱근이며 **NEES와 다르다**. 프레임은 시간상 상관돼601개 독립 시행이 아니다. 접근/귀환 >3σ는 기준선0/300→122/301, a0/300→10/301, b0/300→122/301, c70/300→163/301이다. a는 이번 한 seed에서 과신 비율이91.8% 감소하고 끝오차가66.8% 감소했지만 wall 시간은1.33배였다. b의 시간3.6% 차이는 반복 속도 확증이 아니며 위치 결과는 반올림 오차 수준으로 동일했다. c는 마지막 오차만 줄고 전체 과신은 악화했다.

영역은 **이번 단계 실제 경로에서1m 이내**로 사전 정의했다. 벽 표본은0.1m 격자 중복 제거, 정밀도/벽 recall 허용거리0.15m. 최종 지도에는 앞선 탐색 지도도 포함되므로 아래 전체 점유칸은 이번 단계 신규 삽입 수가 아니다. 영역 R은 그 영역의 벽 덮음이며 전체 경기장 R과 같지 않다.

|조건|영역 P/R(덮음) %|영역 점유칸/전체 점유칸|덮은 벽 표본/영역 분모|영역 벽 분모/전체349|영역 벽RMSE m|종료 실제 시작점 거리 m|
|---|---:|---:|---:|---:|---:|---:|
|기준선100|49.3/100.0|67/500|34/34|34/349 (9.7%)|0.168|2.051|
|a:500입자|91.7/100.0|60/457|36/36|36/349 (10.3%)|0.088|1.410|
|b:로컬창|49.3/100.0|67/500|34/34|34/349 (9.7%)|0.168|2.051|
|c:관측 표본 검증|84.3/100.0|51/460|25/25|25/349 (7.2%)|0.088|1.540|

판정은 **a/b/c 모두 유효2seed 관문 미달(0/3 자격)**이다. 좋은 한 seed를 근거로 문턱을 낮추거나 새 조합/전체2회를 실행하지 않는다. 귀환은60초 단계 예산 내0/4이고 끝에 시작점까지1.410–2.051m 남았다. 저장된 자기 경로 길이는17.52–20.20m, 반복 정합11–15회로, 이 결과가 기존270초 귀환 완주 실패를 확정하는 것도 아니다. 남은 문제는 귀환 달성 미확인과 유효seed 부족이다. 다음 추천은 **a500만 새로운 B 관측 준비가 확보되는 seed에서 기준선과 독립 비교**이며, 이번에는 추가 실행하지 않았다. 검출기·모션모델·return controller 재튜닝0.

### 전달·검증

- 변경 모듈2파일 **41시험 통과**(off proposal/RNG/export bytes, checkpoint 전체 제어기·native·센서·캐시, XML/배치, 고정8슬롯, raw 누락/변조 거부). Mac 물리/녹화재생0, 모델 호출0, 다른 프로세스 종료0.
- 현재 준비+4단계 raw **2,930파일 SHA 일치**, 스모크118파일 및 이전 준비 후속1,538파일 별도 일치. 서버 중단 자료는 원본 상태 그대로 보존; 완료 manifest가 없는 중단 프레임을 완료 기록으로 봉인하지 않는다. [환경](results/environment.json), [스모크](results/smoke-checkpoint.json), [입장 이력](results/preparation-errors.json), [후속 준비](results/preparation-followups.json).
- raw: `/Users/changmin/projects/ugrp/outputs/oracle-runs/egomap60-*`; 계산/선택 원본은 `egomap60-postreboot-evaluation`. host=oracle-x86. Mac은 JSON 채점 결과 병합·해시 확인·표시만 했다. 원본은 서버에도 보존됐지만 별도 영구 백업으로 주장하지 않는다.
- TensorBoard 새 snapshot: `/Users/changmin/projects/ugrp/outputs/tensorboard/1010-egomap60`,8뷰(완료4+미관측 차단4), 후보 비교와 차단을 분리한다. `outputs/egomap60-delivery/`에 파생 뷰·재제출 명령표를 보존한다. CI 대기/병합0, PR405 DRAFT 유지.

TensorBoard 검증: event8/8 로딩·float32 허용오차 내 원본 수치 일치, 차단4건의 미측정 오차를0으로 만들지 않음. Chrome 강 탭964002057에서8실행 선택·9핀, >3σ(.0166/.203/.203/.3877)·종료오차(.1452/.4375/.4375/.1636) 표시 확인. HParams case/policy/seed/source_sha 적용; HParams는 공용4482그룹 한계가 있어 실제 비교는 Time Series의 자기8실행 필터를 사용한다. [표시·원본 대조](results/tensorboard-check.json), [대시보드](http://127.0.0.1:6006/?runFilter=%5E1010-egomap60%2F#timeseries). 새 영상은 이번 요청 범위에 없어 생성0.
