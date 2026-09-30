# D1 사전 등록 초안과 오프라인 참조 구현

Refs #216, 병합 연구 #291, 관련 열린 초안 #285. **DRAFT / 미봉인 / 확증 실행 없음**.
기준 main SHA `a8094cc14e098a55483f53a3c49bf6a0b116043d`에서 시작했다.
이 폴더의 코드는 제어기에 연결하지 않는다. 물리·시뮬레이션·렌더 실행 **0**, 모델 호출 **0**.

| 파일 | 내용 |
|---|---|
| [PREREG_DRAFT.md](PREREG_DRAFT.md) | 주 `(0.4,2)`·보조 `(0.5,3)` D1, 5종 정체 30건·이동 60구간 **계획**, 라벨·통계·잡음·시간/디스크·실패/주장 경계 |
| [d1_detector.py](d1_detector.py) | NumPy만 쓰는 배열/시각/자기 명령 구간 입력, 1초/0.1초 블록 차이·잡음 보정·구간별 기준·연속 경보 |
| [STAGING_PLAN.md](STAGING_PLAN.md) | 기존 probe 옵션으로 만들 수 있는 후보와 부족한 장애물·마찰·속도 지원. 후속 수정할 파일/함수만 열거 |
| [단위 테스트](../../tests/test_stall_detector_d1.py) | 합성 이동/정지/읽기 잡음/노출/시각 지터·기준/결측·명령 경계·입력 경계·기존 작은 표 집계 재계산 |
| [verification.json](verification.json) | 테스트 수·명령·환경·파일 해시·재현/미검증 범위 |

입력은 호출자가 이미 보유한 `frames`, `timestamps_s`, 자기 이력에서 만든
`CommandInterval(start_s,end_s,command_id)`이다. 이 모듈을 import할 수 있는 경로에 넣고
`detect(frames,timestamps_s,commands,PRIMARY)` 또는 `SECONDARY`로 계산한다.
자기 이력의 병진 방향/속도가 바뀌면 구간을 나눈다. GT로 구간·정체 시작을 고르지 않는다.
영상 저장/해독·명령 이력 adapter·GT 채점·physics runner는 이 모듈에 없다.

## 확인한 것 (2026-09-30)

- 최종 관련 테스트 **98/98 통과**: D1 **32개** + CI 분할 **66개**.
  Python 3.12.13, NumPy 2.5.2, pytest 9.1.1; OMP/BLAS 스레드 1.
  공용 잠금이 비어 있음을 확인하고 `run_ci_tests.run_locked`로 짧게 획득해 실행·해제했다.
- CI 목록 `TEST_PATTERNS`에 등록했고, **329개** 오프라인 파일의 8분할에서 새 파일이 정확히 1회 포함된다.
  전체 로컬 회귀/시뮬레이터 테스트를 실행한 뜻이 아니다.
- 연구 폴더의 작은 JSON 두 개에서 **108개 로봇 명령 구간**, **18개 정체 구간/9개 케이스**,
  **90개 비정체 구간·오경보 0**, 주/보조 깨끗한 영상의 지연 중앙값 **1.6/1.2 s**를
  `per_run`으로부터 다시 집계해 저장 `summary`와 대조했다. 새 검출 성능 측정이 아니다.
- 문서의 로컬 링크·Python 문법과 `git diff --check`를 확인했다. raw·공용 TensorBoard/설정·harness는 수정하지 않았다.

테스트는 기존 Mac 환경을 재사용한다. 재현할 때도 공용 잠금이 비어 있어야 한다.
잠금 보유 중에는 실행되지 않고 코드 3으로 끝난다.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PY'
import os
import sys
from scripts.run_ci_tests import local_lock_root, run_locked
command = [sys.executable, '-m', 'pytest', '-q',
           'tests/test_stall_detector_d1.py', 'tests/test_ci_sharding.py']
raise SystemExit(run_locked(command, dict(os.environ), local_lock_root()))
PY
```

첫 테스트 실행은 기대값 오류 **4개 실패/91개 통과**였다. ROI 열 시작 100의 블록 정렬과
1초 창이 부분 정체만으로 비율 문턱을 넘는 시각을 계산해 기대값을 고쳤다.
추가 느린 영상 변화 대조 3개와 관측 실패 문서를 반영한 최종 실행이 98/98이다.
같은 문제로 두 번 막히지 않아 반복 실패 조사 규칙은 발동하지 않았다.

## 재현하지 못한 것과 남은 결정

작은 표에는 프레임과 시간별 `f(t)`가 없으므로 **D1 경보 자체의 원본 영상 재계산은 하지 못했다**.
`f_noisy`/`f_noisy_corr`에는 구간별 표가 없어 그 집계도 새로 재현했다고 주장하지 않는다.
원본 영상과 `flow_rows_lag1.json`을 로딩하지 않고 기존 자료/해시만 읽었다.
색 변환·인과적 프레임 선택·모든 조건에서의 잡음 보정은 명시적 새 후보이므로 탐색 코드와 바이트 동일 재생이 아니다.

시작부터 막힘은 알려진 기준 획득 실패다. 계획 30건 중 시작 정체 6건을 모두 놓치면 최대 감도는
**24/30=80%**여서 전체 ≥90% 기준을 실패한다. 이들을 사후 제외하지 않는다.
봉인 전 전체 범위, 새 조작 지원, 독립 배치/물리 시드, 60셀/예비 셀 manifest,
동결 SHA·해시·독립 검토·후속 실행 승인을 결정해야 한다.
32개 단위 테스트 통과는 30/60 확증·실물·안전·E2E·제어기 성공을 검증하지 않는다.
새 실험 결과가 없어 TensorBoard snapshot 변환·대시보드 재오픈은 하지 않았다.

## 참고 자료

- [병합 연구](../2026-09-30-stall-detection-research/README.md) §2.5·§3,
  `results/stall_detector_offline_r0.4_k2.json`(34,911 bytes),
  `results/stall_detector_offline_r0.5_k3.json`(34,867 bytes); 전체 SHA-256은 verification.json에 보존.
- [문 완화의 실제 양성 대조](../2026-09-30-door-relax-envelope/README.md) §3.
- 통계 참고 공식/원 논문 링크는 [사전 등록 수용 기준](PREREG_DRAFT.md)에 있다.
