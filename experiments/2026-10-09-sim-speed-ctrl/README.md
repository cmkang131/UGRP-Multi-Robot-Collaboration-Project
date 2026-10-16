# speedctrl — 저장 입력 재생의 결과 불변 가속

S3 비계측 제어기 재생은 **2.644480→1.974557 wall/SIM(25.33% 절감)**,
egomap59 55003은 **4.326361→4.092809(5.40% 절감)**이다.
여섯 off/on 비교의 입력 해시·완료 프레임·행동 산출물 직접 바이트가 모두 일치했다.
**전체 온라인 wall/SIM ≤1.5는 미달·미검증**이다. 새 임무 완주나 물리 성공은 실행하지 않았다.

실행 소스 `33f8f182f070b7ab7ca5547e92cfb77aca58b5de`, main 기준
`6813f8a15930bbf3a039887219c76a7acb863648`.
공통 가속 모듈 SHA-256은 `06b498a2348e42fae46114c055e6745a81dc44f1d276ba54665e6ef46de7b8b9`이다.
수치 구현이 같은 이전 측정의 실제 SHA·경로·해시는 [재사용 출처](results/reuse-provenance.json)에 각각 남겼다.
마지막 egomap59 55003 off/on만 새 고정 SHA 측정이다. 같은 seed의 추가 native30SIM 표본은 S3 C3/v151 우선 순번의 명시적 완료 신호가 없어 미실행이다.

## 전후 측정

| 입력 / 조건 | SIM초 | off wall/SIM | on wall/SIM | 절감 | 바이트 |
|---|---:|---:|---:|---:|---|
| s3 | 21.9 | 2.873118 | 2.175074 | 24.30% | 3개 / 18,400,720 B 동일 |
| ego58-55001 | 270.0 | 1.492697 | 1.441508 | 3.43% | 20개 / 379,981,088 B 동일 |
| ego58-55003 | 492.2 | 4.335035 | 4.084480 | 5.78% | 20개 / 1,158,265,693 B 동일 |
| ego59-55001 | 270.0 | 1.486397 | 1.433669 | 3.55% | 20개 / 379,981,088 B 동일 |
| ego59-55003 | 491.8 | 4.326361 | 4.092809 | 5.40% | 20개 / 1,157,720,368 B 동일 |
| s3-unprofiled | 21.9 | 2.644480 | 1.974557 | 25.33% | 3개 / 18,400,720 B 동일 |

제어기-only 표이며 물리·렌더0. native 표본과 합산한 수치는 온라인 측정이 아니다.

| 네이티브 입력 | SIM초 | wall/SIM | 물리 | 렌더 | 렌더 횟수 | 원본 RGB/평가 접두 바이트 |
|---|---:|---:|---:|---:|---:|---|
| s3 | 21.9 | 1.703951 | 0.962632 | 0.572189 | 1317 | 일치 |
| ego58-55001 | 30.0 | 1.025441 | 0.917574 | 0.056272 | 151 | 일치 |
| ego58-55003 | 30.0 | 1.027265 | 0.920041 | 0.055466 | 151 | 일치 |
| ego59-55001 | 30.0 | 1.021475 | 0.914358 | 0.055520 | 151 | 일치 |

S3 `s3`는 cProfile 창 포함, `s3-unprofiled`는 비계측 조건이다. 나머지 제어기 재생은 cProfile 창 포함이다.
구간 타이머는 전 구간, cProfile은 초기화와 처음/마지막 100프레임에 적용했다.
controller-only의 물리·렌더는 0이며, native는 원본 명령·장면·물리·관측 주기로 별도 실행한 구간이다.
S3 native는 전체 21.9초, 완료된 자기 지도 native 세 건은 최초 30 SIM초다. egomap59 55003의 native는 미측정이다. native loop 시간은 초기화 setup_s를 제외하며 setup은 별도 result에 보존한다. 두 표를 합한 값은 온라인 실측이 아니다.
이 Mac의 S3 native 표본 자체가 약 1.70이지만 다른 환경의 보편적 하한이라고 주장하지 않는다.

### 구성요소별 비용

아래는 on의 exclusive wall/SIM이다. 모든 off/on·native 구성요소, 경계 호출 수·렌더 횟수·물리 스텝 수는
[components.csv](results/components.csv)에 있다. inclusive 시간을 중복 합산하지 않는다.
`setup/proof`는 초기화만이 아니라 타이머 밖 초기화·증명·분류되지 않은 잔여 작업이다.
PF/정합의 타이머 경계 호출 수는 실제 새 관측 수나 독립 정합 수와 같다고 해석하지 않는다.

| 입력 / on 조건 | PF | 사후 요약 | 정합 | 지도 삽입 | 경로 계획 | 기록 I/O | graph | 영상 | 기타 | setup/proof |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| s3 | 0.240949 | 0.115006 | 0.000000 | 0.000000 | 0.000000 | 0.134184 | 0.000000 | 0.556226 | 1.048344 | 0.079969 |
| ego58-55001 | 0.047524 | 0.000578 | 0.392573 | 0.059028 | 0.000994 | 0.071376 | 0.030451 | 0.000000 | 0.838205 | 0.000779 |
| ego58-55003 | 0.063451 | 0.000590 | 2.422647 | 0.095898 | 0.000503 | 0.124204 | 0.078384 | 0.000000 | 1.297983 | 0.000821 |
| ego59-55001 | 0.048709 | 0.000571 | 0.391257 | 0.058082 | 0.000999 | 0.070677 | 0.027993 | 0.000000 | 0.834635 | 0.000746 |
| ego59-55003 | 0.061634 | 0.000588 | 2.426669 | 0.094966 | 0.000505 | 0.123646 | 0.079401 | 0.000000 | 1.303530 | 0.001870 |
| s3-unprofiled | 0.240889 | 0.111419 | 0.000000 | 0.000000 | 0.000000 | 0.066516 | 0.000000 | 0.502908 | 1.002111 | 0.050309 |

### 시간이 길어질 때

egomap59 55003 on의 앞/뒤 프로파일 창 비교다. 100개 입자는 변하지 않았다.
지도 칸은 100개 입자 지도 전체의 합계이며 고유 공간 칸 수가 아니다.
기록 bytes는 그 시점까지 생성한 기록 스트림의 합계다.

| egomap59 55003 on | 초기 80프레임 | 마지막 100프레임 |
|---|---:|---:|
| 스캔 정합 초/프레임 | 0.015645 | 1.988571 |
| PF 갱신 초/프레임 | 0.004712 | 0.016871 |
| 지도 삽입 초/프레임 | 0.019505 | 0.053800 |
| 기록 I/O 초/프레임 | 0.002507 | 0.006991 |
| 입자 수 | 100–100 | 100–100 |
| 지도 칸 합계 | 16,119–95,356 | 267,555–268,029 |
| 원장 행 | 3–16 | 401–419 |
| 기록 bytes | 1,127,051–10,499,272 | 559,786,737–596,775,906 |

스캔 정합이 on 전체 시간의 약 59%를 차지한다. 지도·원장·기록 크기 증가와 후반 정합 비용 증가가 함께
관찰됐으나, 크기에 대한 선형 비례나 인과관계는 검증하지 않았다. S3 개별 분포의 400,000→8,001 입자 변화는
기존 bootstrap 정책이며 새 KLD 가속이 아니다. 모든 조건의 구간 값은 [growth.json](results/growth.json)에 있다.

## 공통 구현과 사용

`harness/controller_exact_speedups.py` 한 곳에서 backend reset 때 설치하고 close 때 실제 사용 통계를 기록·복원한다.
새 실행 기본은 `UGRP_CONTROLLER_EXACT_SPEEDUPS=exact-v1`, 원래 계산은 `UGRP_CONTROLLER_EXACT_SPEEDUPS=off`다.
`controller-speedups.json` 등에 실제 설치 항목·fallback·hit/miss·모듈 SHA·유한 캐시 한도를 보존한다.
지원하지 않는 source SHA·dtype·라이브러리 조건이나 mutable schema는 원래 구현을 쓴다.
새 번들에서 실제 적용 기록을 확인해야 하며 고정 연구 코호트나 과거 성공 판정을 갱신하지 않는다.

- 동일 입자/가중치의 순수 사후 모멘트와 요약을 비트 기준으로 재사용한다. 시각·health 행은 매번 갱신한다.
- 동일 후보 격자·센서 σ·거리장을 유한 LRU로 재사용하고 mutable 반환 배열은 소유한 복사본으로 분리한다.
- SciPy 1.17.1 float64 order0만 확인된 원문 좌표 반올림·constant 경계·+0 누산을 유지하는 NumPy 조회를 쓴다.
- virtual forecast의 읽기 전용 과거 행만 공유하고 history 목록·cells·입자·공분산·RNG 변경은 격리한다.
- 확인된 정수 scalar clip만 같은 값·타입의 clamp로 바꾼다. 배열·float·NaN·기타 인자는 원래 NumPy다.

소비하지 않는 프레임이라는 근거가 없어 렌더 생략은 적용하지 않았다. 새 관측 skip, 새로운 KLD/입자 축소,
sampling/RNG, scan search window/순서/동점 처리, 물리·롤러 근사, 기록 bytes/형식 변경은 0이다.
표준 관리 workflow `controller-replay-profile`와 `saved-physics-profile`을 사용한다.
새 실행 예시는 `python -m scripts.sim_cli workflow plan <workflow>`와 각 profiler의 `--help`에 있다.
원본 Git export adapter·모든 입력 이미지 해시·완료 callback 경계·source 고정·배타 잠금을 검사한다.

## 동일성의 범위

[comparison.json](results/comparison.json)은 S3 3개 파일/18,400,720 B, 각 자기 지도 20개 파일의 직접
바이트·SHA 비교와 입력 해시를 보존한다. 프레임별 명령·추정 자세·입자/가중치 배열의 SHA 지문·RNG 상태,
최종 모든 입자 지도 및 제어기 산출물을 비교했다. 프레임별 입자 배열 원본 파일을 모두 직접 비교했다고
주장하지 않는다. 실제 시간계측·프로파일·출처 파일만 제외하며 실제 지연 값은 별도 provenance에 유지한다.

[source-fidelity.json](results/source-fidelity.json)은 원본 대조다. S3는 `inference_wall_ms`와
해시를 확인한 calibration 경로 6개만 분리하고 나머지 기록이 같다. egomap58 두 seed와 egomap59 55001의
원본 행동 파일 16개가 직접 bytes 같다. egomap59 55003은 원본 HOST_BUDGET이 기록 전 위치추정 도중
중단되어 캡처 2,461개 중 setup 10+완료 callback 2,450=2,460개/491.8초만 재생했다.
완료 callback 파일 5개는 원본과 직접 bytes 같지만 **원본 부분 terminal 상태 전체는 재구성하지 않았다**.
마지막 센서 입력을 만들거나 GT로 채우지 않았으며 예기치 않은 입력 누락은 실패한다.

[native-fidelity.json](results/native-fidelity.json)은 모든 표본 RGB의 해시와 원본 평가 로그 접두 bytes가 같다.
전체 적분 상태 체인이나 임무 성공을 검증한 결과는 아니다. eval_only는 제어기에 전달하지 않았다.
egomap58/59의 공통 입력 접두는 중복되어 독립 연구 코호트로 합산하지 않는다.
사용자가 제시한 기존 3.1/6.4는 egomap58이며 원본 온라인 수치와 새 controller-only 수치를 직접 혼합하지 않는다.

## 검증·보존·남은 작업

소스 `33f8f182`의 GitHub CI 33개가 모두 SUCCESS다. 마지막 변경 모듈의 로컬 17개 검사가 통과했으며
앞선 공통 가속/재생 22개 검사도 통과했다. 반복된 검사를 새 독립 증거로 합산하지 않는다.
역사 receipt와 frozen fixture SHA는 유지했다. 원래 Git producer와 현재 off를 같은 수치 환경에서 전체
canonical bytes로 대조하고, current source 해시·행동 필드는 별도로 확인한다. 플랫폼 간 bytes 일치는 주장하지 않는다.

원본·실패·실험 raw는 `/Users/changmin/projects/ugrp/outputs/speedctrl-20261009-v1`–`v15`와 원래 실행 경로에
보존한다. 로컬 raw를 원격 백업이라고 표현하지 않는다. Git에는 작은 표·해시·검증 기록만 넣으며 Drive는 사용하지 않는다.
v12 egomap58 55003 off worker는 완전하지만 관리 manifest는 당시 EPERM 최종화 실패다. 이 실패 기록은 유지했다.
관리자는 자기 자식이 이미 종료된 EPERM만 허용하고 살아 있는 자식의 오류는 계속 거부한다.
v13의 마지막 누락 입력 실패와 v14의 실행 전 대기도 보존했다. v15는 완료 on 경계에서 자기 잠금을 반환하여
S3 C3·이번 v151 연구 순번을 먼저 수행하도록 했으며 큐 부모만 정지하고 완료 on 경계에서 정리했다. active worker나 타 작업을 종료하지 않았다. 전체 v15 큐를 완료로 표시하지 않으며 queue-cancellation.json에 미실행 native를 기록했다.
경계 판단에서 개별 release를 전체 연구 완료로 잘못 해석했던 점도 외부 기록에 정정했다.

정합 비용과 전체 온라인 ≤1.5, S3 우선 순번 뒤 egomap59 55003 추가 native 표본은 남아 있다. 재개 시 새 고정 source로 별도 표본·snapshot을 추가하며 기존 이벤트를 재변환하지 않는다. Cartographer의 표준 branch-and-bound를 조사했으나 공식 uint8
확률 양자화·정수 합산은 원래 float64 점수·동점·분기 결과를 바꾸므로 이번 바이트 동등성 후보에 넣지 않았다.
독립 코드 검토와 실제 병합 상태는 PR #423에서 별도 확인한다.

## TensorBoard

[native TensorBoard](http://127.0.0.1:6006/?smoothing=0&runFilter=%5E1010-speedctrl-%2833f8f182%2F%28s3%28-unprofiled%29%3F%7Cego%2858%7C59%29-5500%5B13%5D%29-%28off%7Cexact-v1%7Cnative%7Cboundary-failure%29%24%7Chistory-33f8f182-v2%2F%29&pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22gate%2Fbytes_identical%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fwall_per_sim%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fscan_match_wall_per_sim%22%7D%5D#timeseries)에 제어기 12조건·native 4표본·역사 실패/예산종료 5건·재생 실패 1건을 표시했다.

`outputs/tensorboard/1010-speedctrl-33f8f182`와 역사 기록 분모 보정 전용 `1010-speedctrl-history-33f8f182-v2`에서 이벤트 로딩·HTTP 요약355개·시계열36개의 길이/양 끝값·화면을 검증했다.
초기 역사 파생5건은 S3 경과시간의 중복 차감/자기 지도 초기시간 미차감 오류였다. 원본과 기존 snapshot을 보존하고 보정한 5건만 새 snapshot에 넣어 기본 보기에서 대체했다. 이미 유효한17건은 재변환하지 않았다.
기존 서버·snapshot은 유지하며 새 video 등록은 0이다. success 카드는 임무 성공이 아니라 bytes gate를 뜻한다.
시간·명령 수·모델 호출·정합 비용을 pin하고 HParams의 case/outcome/policy/seed/source_sha/wall/SIM/선언 gate를 설정했다.
모델 응답 시간은 원본 model_calls=0이라 unavailable로 표시하며 0 지연을 만들어 넣지 않는다.
HParams는 공용 전체 로그를 표시하고 현재 새 offline/gate metric 열을 노출하지 않아 사용 가능한 메타데이터 5개·wall·SIM·선언 gate 8개를 설정했다. 조건별 비교는 선택된 Time Series 22개로 한다.
실제 조건·SHA·계측 출처와 표시 검증은 [tensorboard.json](results/tensorboard.json)에 있다.

## 참고 자료

- [Thrun, Burgard, Fox, Probabilistic Robotics (MIT Press, 2005)](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/),
  [저자 Stanford 강의](https://robots.stanford.edu/cs226-06/schedule.html): 4장 비모수 필터·6장 likelihood field·8장 MCL.
  서지·저자 강의 대응을 확인했다. 책 전체 챕터 원문은 이번 조사에서 열람하지 않았다.
- [Nav2 AMCL likelihood field](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp),
  [map_cspace](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/map/map_cspace.cpp): 거리장 준비와 반복 likelihood 조회 분리.
- [Olson 2009, Real-Time Correlative Scan Matching](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf): 조회표 사전 계산·탐색 계산 재사용.
- [SciPy 1.17.1 NI_GeometricTransform](https://github.com/scipy/scipy/blob/v1.17.1/scipy/ndimage/src/ni_interpolation.c#L452-L570): order0 반올림·경계·누산 원문.
- [Python cProfile](https://docs.python.org/3/library/profile.html), [lru_cache](https://docs.python.org/3/library/functools.html#functools.lru_cache),
  [copy](https://docs.python.org/3/library/copy.html), [NumPy clip](https://numpy.org/doc/stable/reference/generated/numpy.clip.html): 계측·유한 순수 캐시·mutable 소유권·동일 clamp.
- [Hess et al. 2016](https://research.google/pubs/real-time-loop-closure-in-2d-lidar-slam/),
  [Cartographer 공식 matcher](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/scan_matching/fast_correlative_scan_matcher_2d.cc): 잔여 정합의 표준 대안과 양자화 경계.
- [Python signal](https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions),
  [os.killpg](https://docs.python.org/3.12/library/os.html#os.killpg): 불완전 callback·이미 종료된 자기 프로세스 그룹 경계.
- [Git archive](https://git-scm.com/docs/git-archive), [NumPy RNG 호환성](https://numpy.org/doc/stable/reference/random/compatibility.html): 역사 소스 검증과 같은 build·환경·기계 조건.

초기 후보·각 실패·CI 수정의 당시 기록은 [HISTORY.md](HISTORY.md)에 보존했다. 그 문서의 대기·미확인은 기록 당시 상태다.
