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

측정 전 원본 runner와 비교하여 자기 지도 JSONL 기록을 명령 기억보다 먼저 하도록
맞췄다. own-inputs/return-navigation/frontend-poses/active-events를 포함한 제어기 산출물을
모두 보존하고 원본처럼 비유한 JSON을 거부한다. 순서 반례 검사4개 통과(0.17초).
S3 extract의 pan offset도 부호 있는 0을 구분하는 비트 key로 바꿨다. 관련 검사7개
통과(0.68초). 최종 후보는 물리/렌더/관측/RNG 변경0이며 전체 재생 증명은 아직 대기다.
v5 역시 S3 우선 gate 대기에서만 종료했으며 실행/측정은 없었다.

최초 실행 실패는 숨기지 않는다. v6 CLI 파일 호출은 package root 없이 시작해 worker에
도달하지 못했다. v7 S3는 profiler를 이미 켠 상태에서 재활성화하여 439 중0프레임에서
실패했고, 자기 지도는 export의 third_party 표준 native 탐색 소스 누락으로 초기화에
실패했다. 유효 성능/동등성 결과가 아니다. profiler는 창 경계에서만 toggle하며 불완전
재생은 result.json을 보존하고 workflow를 실패 처리한다. 관련 5개 검사0.20초 통과.
S3 원본의 Unicode 기록 형식도 유지한다. native 소스는 같은 기록 SHA에서 새 export에
추가하고 양쪽 측정 전에 동일한 build를 준비한다. 과거 export와 실패 로그는 보존한다.

## 첫 측정: 전체 S3 저장 입력 (v8)

439/439 프레임 양쪽 완료. 프로파일 창 포함 제어 재생 wall/input-SIM은
2.854897→2.522566(62.522251→55.244186 wall초/21.9 SIM초)이다.
physics/render0이므로 온라인4.270629와 직접 비교하지 않는다. 명령268,794 bytes와
입자/가중치/RNG/포즈5,109,822 bytes는 직접 비교와 SHA-256 모두 같았다.
record.json13,023,004 bytes는 실제 inference_wall_ms가 달라 전체 bytes gate는 실패했다.
그 값은 새 비교에서 timing-provenance.json으로 분리·보존한다. 성능값을 0으로 만들거나
원본을 수정하지 않는다. 비교 경계는 기록의 수치 상태와 실제 시간계측 출처의 분리이며,
기존 전체 원본 record의 바이트 일치를 주장하지 않는다.

남은 S3 비용은 OwnCam estimate의 반복된 동일 입자 모멘트와 OpenCV refine의
스칼라 정수 np.clip이다. 창 프로파일에서 각각4.086초/2603회,
클립 관련 약2.4초/70만회가 보였다(inclusive, 서로 단순 합산하지 않음).
같은 px/logw 모멘트만 재사용하고 t/since_tag_s는 매번 원문 식으로 갱신한다.
정수64 bit+Python 정수 경계의 clamp만 표준 min/max로 대체한다.
배열·부동소수·NaN·out/기타 dtype은 원래 NumPy 호출이다.
[NumPy clip](https://numpy.org/doc/stable/reference/generated/numpy.clip.html)의 표준 정의를
따르며 역전 경계도 원문과 일치한다. 변경 모듈15개 검사0.83초 통과.

자기 지도의 추가 vendor도 같은 SHA의 third_party 전체로 새 export에 포함했다.
두 adapter의 실제 actor/controller 초기화와 필요한 native build가 완료됐고
이 확인의 관측 프레임/물리 실행은0이다. 이전 export와 모든 실패는 보존했다.

v9는 추가 타이머의 Observer API 이름 오류로 worker 초기화에서 실패했다(프레임0/물리0).
실제 OpenCVObserver 메서드 경계로 수정하고 import 표면까지 포함한 관련7개 검사0.76초
통과했다. 각 실패의 managed manifest·로그·부분 출력은 primary outputs에 유지한다.

## 완전 S3 재생과 슬롯 경계 (10/10)

`bdaf46815620b919a8f61b69d301ca88547f1589`, raw `outputs/speedctrl-20261009-v10`의
S3 439/439 프레임에서 cProfile 포함 제어기-only wall/SIM은 off 2.873118 → on 2.332310이다.
명령 268,794 B, timing 분리 후 제어 기록 13,022,104 B, 입자/가중치/RNG 상태 5,109,822 B는
직접 바이트·SHA 비교로 동일하다. 실제 inference_wall_ms는 `timing-provenance.json`에 각각 보존한다.
원본 전체 기록의 타이밍 바이트까지 같다고 주장하지 않는다. 물리·렌더 0이며 전체 online 목표는 미달/미검증이다.
원본 egomap58 55001 off 1,351/1,351 프레임은 403.028187 wall /270 SIM =1.492697이다.
원본 heading/decisions/frontend-ledger/navigation/return-navigation/utility-events/own-inputs JSON과 의미값이 같다.

v10 후속 on은 다른 작업이 status 확인과 acquire 사이에 잠금을 잡아 실행 전 거부됐다(재생/물리0).
기록은 보존했다. 원자적 acquire의 유한 대기와 같은 작업 큐의 살아 있는 조상 PID 잠금 상속을 추가한다.
상속은 owner/branch/timing_sensitive/실제 프로세스 조상 관계가 모두 맞아야 하며 자식은 잠금을 해제하지 않는다.
후속 큐는 S3 먼저, 순차 재생이며 연구 슬롯 종료까지 기다린다. 다른 작업을 종료하거나 잠금을 빼앗지 않는다.

cProfile에서 기존 scalar clip 가속은 install()의 private globals만 바꿔 실제 detector까지 전달되지 않은 것으로 확인했다.
소스 해시가 고정된 원래 detector와 geometry-cache factory에 직접 private np를 연결하고,
실제 fast-path 호출 수를 provenance에 기록한다. 정수 clamp 결과/type는 유지하고 float/array는 NumPy 그대로다.
설치 복원·실제 detector globals와 신규 factory 연결을 회귀로 검사한다.

네이티브 비용용 `saved-physics-profile`도 표준 관리 계층에 등록한다. 원본 backend/발행 명령/장면 자산을 쓰고
최대30 SIM초의 물리·렌더·저장 I/O만 측정한다. 제어/모델0, 원본 RGB SHA·장면 XML 자산 해시를 비교하며
실패도 기록한다. 이 구간 비용과 전체 저장 입력 제어기 비용을 합한 추정치를 실제 online 측정으로 부르지 않는다.
