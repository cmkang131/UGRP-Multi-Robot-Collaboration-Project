# release20 — 최소 펄스 양자화 정착 (2026-10-15)

요청: release18 `a3bbc90e` 관문40의 seed110613 r2 재정렬 진동을 고치고 gcp1에서 직접 4회 확인한다.
release19 `b2d2d33f`·`549ac12a`의 대기 재사용은 이 결함을 고치지 않았으므로 과거 결과와 합산하지 않는다.

`release20_settle_v1` 하나를 기본 off로 추가했다(API `release20_settle`, CLI `--release20-settle`).
release18_v1(A), release19_v1(B: 동일 정착+완료된 look 대기 재사용)에서 사용할 수 있다.
공통 `sim/settle_pulse.py`는 자기 RGB 오차와 자기 발행 명령 모형의 최소 펄스 효과 δ만 받는다.
도착 허용=max(기존,.6δ), 비례 펄스 크기/최소 펄스, 실제 발행 뒤 연속 부호 반전 3회에 한해
2δ 이내에서 정착, 25% 이탈 히스테리시스를 사용한다. 큰 교번 오차·수동 캡처만으로 정착하지 않는다.
release 정렬은 고정 카메라·명령 PWM으로 계산한 영상 Jacobian과 실제 wheel allocator/40ms floor의
명령 적분으로 δ를 계산한다. 정답·접촉·측정 관절·시뮬레이터 상태는 읽지 않는다.
누락/잘린 영상은 정착 상태를 초기화하며 원래 FOV·지도·18도 이동 상한·0.3초 새 RGB 안정 확인을 유지한다.
다른 crate/selfmap 흐름에는 아직 연결하지 않았다. 공통 모듈만 후속 이관용으로 제공한다.

## 비물리 검증과 저장 원본 재생

`tests/test_settle_pulse.py tests/test_release17.py tests/test_release19.py`: **56 PASS**, 18.43초.
오차=이전 오차−실제 회전+잡음의 폐루프 모의(부호 양쪽, 6개 초기 오차×3개 plant gain)가 정착한다.
옛 .025 허용/최소 .06 효과에서는 16회 중 15회 반전하는 주기2를 재현했다.
기본 off 원장·명령 회귀, 대기 조합/검증, 없는 영상/거부된 명령의 정착 금지도 검사했다.

`release20-replay-110613.json`: 기존 r2 마지막 단계 15펄스/14반전 → **추가 0펄스에서 정착 선언**.
첫 오차 rho=−.03169795, 명령 모형 δrho=.05792595, 새 허용=.03475557(기존 .025), theta=.00794649.
다른 세 정렬도 0펄스 정착. 저장된 특징열에 대한 조건부 판단 재생이며 새 물리·후속 .3초 안정 성공을 뜻하지 않는다.
원본은 `gcp1:/home/ugrp/ugrp-sim/runs/r18g-13-a3bbc90e/raw`, Mac fetch-lite는
`/Users/changmin/projects/ugrp/outputs/gcp1-runs/r18g-13-a3bbc90e/raw`다.
result·양쪽 teacher manifest의 압축/복원 SHA-256을 모두 확인했다(재생 JSON source 항목).

## GCP 직접 실행 계획

`release20-dev4-plan.json`: 110613(A), 74976(B), 78526(B), 성공했던110600(A), 각180 SIM초·동시4·DEV/PR491.
정확히 같은 실행 입력을 release18 관문/진단 계획에서 복사했다. A/B 개발 진단만 합계 n/4로 보고하며
후속 관문은 각각 n/40으로 분리한다. 코드·입력은 실행 전에 커밋/push하고 실행 중 고정한다.
기존 GCP-aware 진입점 `/Users/changmin/projects/ugrp-wt/gcp-sim-host/scripts/remote_run.py`의
`--host gcp1 --detach --class dev --pr 491`를 사용한다(이 checkout의 구형 runner에는 GCP 지원이 없다).
프로젝트 `ugrp-act-train-1014`, 기존 gcp1/n4-highcpu-64만 사용. 새 VM/크기 변경·모델 호출/키 전송 없음.
8시간 STOP·유휴20분·budget-stop은 유지. 기존 다른 작업을 정지하거나 임대 파일을 정리하지 않는다.
예산: 4×96 MiB=384 MiB/round, 최대3round=1152 MiB. 요약/원장/해시/대표 영상은 영구보존,
DEV 무거운 원본은 열린 PR 동안 보존. 전체 raw 회수 없이 fetch-lite와 검토용 대표 프레임만 회수한다.
시작 관측: VM load .12/3.05/4.90, available≈123 GiB, 디스크198 GiB 여유, 활성 시뮬레이션0.
실제 결과·원본 hash·검토 범위는 실행 완료 뒤 이 문서와 `release20-summary.json`에 추가한다.

## 참고 자료 (2026-10-15 확인)

- De Persis & Mazenc, [Stability of quantized time-delay nonlinear systems](https://arxiv.org/abs/0812.2683v2):
  초록에서 양자화 제어의 chattering 방지용 hysteresis를 확인했다. 본 제어기의 수치/안정성을 보증하는 인용은 아니다.
- Papadopoulos et al., [Switched control for quantized feedback systems: invariance and limit cycle analysis](https://arxiv.org/abs/1701.07482v2):
  입력·관측 양자화를 명시적으로 고려하며 단순 적분기의 주기해를 분석한다는 초록을 확인했다.
- Miguel-Escrig et al., [Regular quantisation with hysteresis](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-cta.2020.0128):
  출판 원문 페이지의 초록에서 limit-cycle 회피를 확인했다. 본 프로젝트에 직접 적용하는 정리는 미확인이다.
- δ/2 기준은 잡음 없는 단일 축의 두 점 `e, e−δ`에서 직접 유도한다: 허용≥δ/2면 둘 중 가까운 점을 받아들인다.
  허용<δ/2는 주기2가 가능한 조건이지 모든 초기 오차/모든 계에서 반드시 진동한다는 뜻은 아니다.
  .6 배수·반전3회·25% 이탈 여유는 사용자 제안/이 구현의 설계값이며 외부 문헌의 보편 상수로 인용하지 않는다.
