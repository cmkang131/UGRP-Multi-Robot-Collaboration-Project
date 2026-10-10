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
