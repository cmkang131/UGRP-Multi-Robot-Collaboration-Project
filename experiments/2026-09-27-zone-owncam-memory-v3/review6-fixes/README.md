# PR #234 6차 리뷰 P1 수정

기준 HEAD `7400c4262156f85ccdee946d8d96c075e0cdaa79`, 브랜치 `codex/zone-owncam-memory-v3`.
제공된 `codex-234-review6.md`의 초기화 deadline 회귀를 수정했다. 오프라인 상태기계 검사이며 물리 실행·모델 호출·새 코호트 결과가 아니다. 커밋·push·PR 댓글/수정·병합은 하지 않았다.

## 변경과 예산

- `harness/owncam_safety_v3.py`: 충돌 검사를 통과한 초기 sweep 생성 시 정지 재촬영 deadline을 비활성화하고 남은 시간을 보존한다. sweep 완료 또는 발행 직전 충돌 거부 후 남은 시간만 다시 활성화한다. 반복 거부는 deadline을 재설정하지 않는다.
- 정지 예산은 누적 8 SIM s, capture 총 20회, 요청 간격 0.2 SIM s다. sweep이 시작되어도 이미 사용한 시간·capture 횟수를 돌려주지 않는다. 실제 sweep 최대 3회는 유지한다.
- sweep 실행은 별도의 전체 초기화 **30 SIM s** 안에서 진행한다. 최초 초기화 `decide`부터 모든 시간을 포함하며, sweep 생성·완료·거부로 시계를 멈추거나 재설정하지 않는다. 명령 진전이 없는 sweep도 이 상한에 종료된다. 회귀의 최초 결정 1.8 s 기준 전체 deadline은 31.8 s다.
- [설계 문서](../../../docs/design/2026-09-27-owncam-memory-v3.md)의 근거는 정지 8초 + 기본 합성 sweep 두 번 각 9초 + 전환·판단 여유 4초다. 실제 물리 시간의 보장이나 세 sweep의 완주 보장이 아니다. DRAFT 사전등록에도 같은 예산 의미를 기록했으며 실행 미허가 상태를 유지한다.
- ON/OFF는 같은 안전 코드를 사용한다. OFF에도 추적 기억이 있으므로 비교 해석은 **기억 기반 재관측 결정의 효과**에 한정한다. **전체 기억 유무 효과**를 측정하는 비교가 아니다.

## 수정 전·후 검증

새 테스트는 `tests/test_owncam_memory_v3_review6.py`이며 CI 목록에 등록했다. 합성 자기 pose/프레임 시각을 입력하고 실제 정적 충돌 검사·sweep 상태기계·0.1초 발행 명령 처리를 사용한다. 제어기의 충돌 검사나 sweep 전환을 mock하지 않는다. 회귀 pose는 자유 공간의 (0, 0)이며 실제 위치/성공의 관측 근거가 아니다.

| 검사 | 결과 | 로그 |
|---|---|---|
| 원본 runtime, 반례 OFF/ON | 둘 다 9.8 s `NOT_INITIALIZED`, `stationary_deadline` | `before-confirmed.txt` |
| 최종 테스트 + 원본 7400c426 safety 모듈을 메모리에만 로딩 | 같은 원인으로 **2 failed** | `before-final-tests.txt` |
| 수정 후 새 회귀 전체 | **13 passed** | `after-expanded.txt` |
| 관련 10개 파일, 새 13개 포함 | **305 passed, 360 subtests passed** | `related-tests.txt` |

반례의 양 조건 공통 타임라인은 다음과 같다.

1. 1.8 s: 초기 추정이 없어 sweep 거부, 정지 deadline=9.8 s.
2. 2.0 s: σxy=0.09 m, 실제 충돌 검사를 통과해 기본 6-pan sweep 시작.
3. 2.8 s부터: σxy=0.02 m. 원본은 진행 중 9.8 s에 잘린다.
4. 수정 후 11.0 s: sweep 완료, 11.1 s: `search_leg` 진입.

추가 회귀는 새 프레임의 반복 거부에도 9.8초 종료, 재개 sweep의 명령 충돌 거부 시 남은 정지 시간/촬영 횟수 유지, 재개 전후를 합친 20회 촬영 상한, 최초 거부 유무 양쪽의 진행 불능 sweep을 30초 전체 상한으로 종료하는 경우다. 기존 5차 촬영 간격·프레임 신선도·촬영 예산 회귀도 관련 묶음에서 통과했다.

초기 fixture 보정 로그도 보존했다. `before.txt`는 벽에 가까운 합성 위치에서 sweep 자체가 거부되어 반례 재현에 실패한 검사다. 자유 공간으로 고친 `before-confirmed.txt`가 원인 확인 근거다. `after-initial.txt`의 4개 실패는 합성 입력에서 localizer 시계를 진행시키지 않은 fixture 오류였다. 실제 입력 시각에 맞춰 예측 시계도 갱신한 후 11개가 `after.txt`, 촬영 예산 보존 2개를 추가한 최종 13개가 `after-expanded.txt`에 통과했다. 최종 fixture로 원본을 다시 검사한 것이 `before-final-tests.txt`다.

## 재현

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. 모든 pytest 실행에 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`을 설정하고 `--basetemp=./.pytest_tmp`를 전달했다. 새 테스트의 thread cap은 `mock.patch.dict`로 고정·복원한다. 기존 wrapper가 OpenCV `setNumThreads(0)`으로 병렬 영역을 끄고 실제 thread 수 1을 확인한다.

- 새 회귀: 위 환경/Python으로 `experiments/2026-09-27-zone-owncam-memory-v3/review-fixes/run_review_tests.py -q -s --basetemp=./.pytest_tmp tests/test_owncam_memory_v3_review6.py`.
- 원본 반례: 같은 환경/Python으로 이 폴더의 `reproduce_baseline.py`. `git show 7400c426:harness/owncam_safety_v3.py`를 메모리에만 로딩하며 checkout/index를 바꾸지 않는다. exit 1과 두 실패가 기대값이다.
- 관련 묶음: 위 wrapper에 `tests/test_owncam_memory_v3{,_review,_review2,_review3,_review4,_review5,_review6}.py`, `tests/test_owncam_memory.py`, `tests/test_m1_owncam.py`, `tests/test_owncam_localizer.py`를 전달했다. 실제 명령에서는 각각의 파일명을 명시했다.
- 사용자가 허용한 물리·모델 호출 없는 검사이므로 잠금 없이 실행했다. `.pytest_tmp`는 종료 후 삭제했고 `git diff --check`를 확인했다. 파일/로그 해시는 `verification.json`에 보존한다.

## 범위와 남은 확인

실제 RGB 재촬영의 수렴률·물리 sweep·운반 성공·기억 효과는 검증하지 않았다. 새 실험/학습/평가 결과가 없어 TensorBoard 변환이나 서버 실행은 하지 않았다. UGRP 예외에 따라 Google Drive 작업도 없다.

Git fetch는 공용 Git `FETCH_HEAD` 쓰기 권한 제한, `gh pr list`는 GitHub 네트워크 연결 실패로 막혔다. 최신 원격 PR/CI 상태는 미확인이다. 기본 체크아웃의 clean main은 로컬 origin/main보다 84커밋 뒤였지만 쓰기 제한과 최신 fetch 실패로 갱신하지 않았다. 요청된 feature worktree의 로컬 HEAD는 제공된 SHA와 일치하며 그대로 유지했다.
