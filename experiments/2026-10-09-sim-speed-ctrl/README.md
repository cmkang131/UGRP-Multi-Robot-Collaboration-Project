# speedctrl — 물리 밖 실행 비용

감독 요청(2026-10-09): main `6813f8a15930bbf3a039887219c76a7acb863648` 기반,
S3 v148와 자기 지도 저장 입력의 비용 분해·결과 불변 가속. v7 물리/롤러 근사 변경0.
현재 S3 v149 smoke를 우선하며 연구 잠금/진행 코호트의 소스는 수정하지 않는다.
원본·raw는 primary outputs에 보존하고 Google Drive는 사용하지 않는다.

## 원본 확인

| 입력 | source SHA | SIM 구간 | 기존 wall/SIM |
|---|---|---|---|
| `outputs/s3-motion-533329b5-s14201-v148` | `533329b51a3eb0e6d940a8d2f4c187af46781805` | 1.3–23.2 (21.9초) | 4.270629 |
| `outputs/goal-route-preflight-v1/seed55001` | `1f5269db3eb06f0db529941e3e3a95519c099cd0` | 1.3–271.3 (270초) | 3.102169 |
| `outputs/goal-route-preflight-v1/seed55003` | 동일 | 1.3–493.5 (492.2초) | 6.373242 |
| `outputs/goal-route-motion-audit-v1/seed55001` | `5b33094635804662a8a604718aead132c420b5ba` | 1.3–271.3 (270초) | 2.446377 |

3.1/6.4 원본은 **egomap58**, egomap59 55003은 시작 시 미발견이다.
기존 온라인 수치와 새 저장 입력 재생을 혼합하지 않는다. S3 원본은 HOST_ERROR이며
자기 지도는 DEV budget_exhausted; 임무 성공이나 확증 연구 근거가 아니다.

## 실행·검증 계획

`controller-replay-profile` 표준 workflow에 기록 도구를 등록했다.
별도 Git export에서 해당 원본 SHA의 adapter를 실행하고 타이머/가속만 명시적으로 덧댄다.
원본 입력 manifest 및 모든 소비 JPEG의 sha256을 확인한다. eval_only는 제어기로 전달하지 않는다.
agent_lock 안에서 cProfile와 구간 타이머로 입력 전체를 재생한다. 중첩 exclusive 시간을
분해 표에 쓰고 inclusive 시간을 합산하지 않는다. 프레임별 지도 칸 수·입자 수·원장 길이와
누적 시간을 보존한다. 프로파일과 profiler 없는 전후 시간은 별도 조건이다.
동등성은 모든 프레임 명령·포즈·입자·가중치·RNG 및 재생 산출물의 직접 bytes 비교로 판단한다.
저장 입력 재생은 물리/렌더0이므로 이것만으로 온라인 wall/SIM ≤1.5를 주장하지 않는다.
기존 S3 기록의 물리20.620449초·render13.361863초/1317회·JSONL0.190778초는 역사 수치다.
소비되는 JPEG를 생략하거나 PF 갱신·KLD·입자/RNG·동작/관측 주기를 변경하지 않는다.

## 참고 자료

- [Thrun, Burgard, Fox, Probabilistic Robotics (MIT Press, 2005)](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/):
  4장 비모수 필터, 6장 센서/likelihood field, 8장 Monte Carlo 위치추정.
  출판사 서지 확인; 챕터 전체 원문은 이번 조사에서 열람하지 않았다.
- [Nav2 AMCL likelihood_field_model.cpp](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp),
  [map_cspace.cpp](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/map/map_cspace.cpp):
  거리장 준비와 반복 센서 likelihood 조회를 분리한다. 센서식·분포를 바꾸는 근거로 사용하지 않는다.
- [Olson 2009, Real-Time Correlative Scan Matching](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf):
  사전 계산한 조회표와 탐색 계산 재사용. 근사·탐색 축소는 이번 바이트 동등성 경계 밖이다.
- [Python cProfile](https://docs.python.org/3/library/profile.html),
  [functools.lru_cache](https://docs.python.org/3/library/functools.html#functools.lru_cache):
  프로파일 자체 오버헤드를 별도로 표시하고 순수 계산만 유한 캐시로 재사용한다.

새 결과·실패·남은 인수는 이 기록의 results에 추가한다. 원본을 덮어쓰지 않는다.

## 공통 후보

`harness/controller_exact_speedups.py` 한 곳에서 host reset 시 설치한다.
`UGRP_CONTROLLER_EXACT_SPEEDUPS=exact-v1` 기본, `off`는 원본 계산이다.
별도 runtime 출처 파일 2개에 실제 항목·fallback·모듈 SHA·캐시 한도를 남긴다.
자기 지도 adapter가 없는 main에서는 없는 모듈을 기록하고 기존 S2/S3 순수 요약만 적용한다.
자기 지도/신규 S3 branch는 다음 새 실행 전에 main merge 후 같은 공통 reset을 사용한다.
현재 고정 코호트의 source/admission을 갱신하거나 과거 성공을 승계하지 않는다.

- 사후분포: 소유한 배열 snapshot의 비트 비교. 제자리 변경은 무효화하고 mutable 결과는 복사한다.
  PR416의 S3 v148 요약 경계를 재사용하며 audit option/hit/miss/health/시각 행은 유지한다.
- 지도: 동일 입력의 likelihood field/후보 격자/센서 σ를 유한 LRU로 재사용한다.
  query·필터식·search window·후보 순서·동점 처리·sampling/RNG는 바꾸지 않는다.
- virtual information-gain forecast: 읽기 전용 과거 원장·진단과 history 행의 중복 deepcopy를 생략한다.
  history 목록·cells·particle/covariance 배열은 계속 복사하여 virtual rollout 변경을 격리한다.
  지원 함수의 원문 SHA가 같을 때만 설치한다. 기존 함수를 그대로 재호출하며 arithmetic을 바꾸지 않는다.
- 아직 소비하지 않는 프레임이라는 증거가 없으므로 렌더 생략은 적용하지 않았다.
  KLD/입자 수 변경0, 새로운 관측 skip0, 로그 bytes/형식 변경0이다.

잠금 대기 중 후보를 준비했으며 프로파일에서 비용을 확인한 뒤 채택 범위를 정한다.
이 절의 후보 코드·초록 단위검사는 wall/SIM ≤1.5 또는 전체 재생 동등성의 완료 증거가 아니다.

측정 시작 전 정적 검토에서 `ledger is histories[best]`의 alias를 확인했다.
virtual clone의 ledger 목록은 별도 복사하고 clone 안에서만 history와 alias를 유지하도록 수정했다.
기존 행은 읽기 전용이고 append·cells/입자 변경은 원본에 도달하지 않는 회귀를 확인했다.
[Python copy/deepcopy](https://docs.python.org/3/library/copy.html)의 memo/공유 객체 원칙을 따르며,
forecast와 실제 entropy·resample·propagate 함수 원문 SHA까지 함께 guard한다.
첫 v1 managed session은 잠금 대기 중 자기 프로세스만 종료했다(재생/물리0); 기록은 유지한다.

CI에서 과거 v91 synthetic fixture가 현재 AST closure에 새 모듈을 섞어 Git archive가
실패했다. 고정 acquisition SHA의 코드·설정으로 정적 bundle을 생성하도록 바꾸고,
v87 역사 검사는 기록 당시 Git blob/closure를 검증하도록 바로잡았다. 오래된 receipt와
등록 파일은 수정하지 않았다. 관련 3개 검사 70.78초 통과; 넓은 로컬 재실행은 하지 않았다.
v3는 측정 전 잠금 대기에서 종료했고 원본 queue-state와 별도 interruption 기록을 남겼다.
