# PR #234 4차 리뷰 수정

기준 HEAD `c02db4d55510a5936dadebef6ef6ddf5dd5592fb`, 브랜치 `codex/zone-owncam-memory-v3`.
제공된 `codex-234-review4.md`의 P1·P2를 수정했다. 단위/저장 입력 회귀 검사이며 새 물리 실행·코호트·성공률 검증은 아니다. 커밋·push·병합은 하지 않았다.

## 변경

- **P1:** `LegDriverMemV3`가 이동량/과거 fix와 독립적으로 현재 xy·yaw σ를 검사한다. 주행 허용 상한은 loaded 0.07 m / unloaded 0.05 m, yaw 3°이며 도착은 fix 상한 loaded 0.06 m / unloaded 0.05 m, yaw 2°를 사용한다. 유한한 비음수 σ만 허용하며 초과 시 hold·재관측으로 진행한다. `_arrive()`도 현재 시각으로 예측 후 별도 검사하므로 이미 도착 look을 마쳤어도 큰 σ로 `arrived`를 반환하지 않는다. 기존 look 신선도·일관성·유한 재시도·충돌 검사도 유지한다.
- **P2:** v3 `_gate_look()`이 sweep 생성 성공을 확인한 뒤 mode/target·view reset·reanchor를 설정한다. 거부 시 정상 `LOOK_COLLISION_UNVERIFIED` 또는 기존 슬롯 handoff를 반환한다. v2 부모 파일은 보존 대상이므로 v3에 거부 가능한 gate 호출 처리를 두었으며, short/full/조작 경계 full 정책은 유지한다.
- 새 회귀를 `scripts/run_ci_tests.py`에 등록했다. 기존 runner 테스트의 thread 환경은 이미 `mock.patch.dict`로 1에 고정되어 있음을 확인했으며, 외부 cap 2를 mock한 별도 실행에서도 통과했다. runtime의 cap 1 요구는 변경하지 않았다.

## 수정 전/후 근거

| 검사 | 결과 | 로그 |
|---|---|---|
| runtime 수정 전 핵심 반례 | **14 failed, 22 deselected** | `before.txt` |
| 최종 테스트 + 원본 c02db4d5 runtime의 메모리 내 재현 | **14 failed, 22 deselected** | `before-confirmed.txt` |
| 새 4차 회귀·경계 전체 | **36 passed** | `after.txt` |
| 기존 관련 회귀 + 4차 테스트 | **322 passed, 382 subtests passed** | `related-tests.txt` |
| mock CI cap 2에서 runner 환경 격리 | **4 passed** | `ci-caps.txt` |

P1 실패 12개는 최근 fix 시각 1.8 s, 현재 2.0 s, 이동량 0/0.099 m 및 `(σxy, σyaw)=(0.20, 0.15)/(0.20, 0.005)/(0.02, 0.15)`를 사용한다. 수정 전 이동 분기에서 0.12 m/s 전진, 도착 분기와 `_arrive()` 직접 호출에서 `arrived`가 확인됐다. 수정 후 모두 hold하며 완료를 승인하지 않는다.

P2 실패 2개는 실제 0.40 m 정적 벽 지도·자기 추정 `(2.00, −0.50)`·carry 자세에서 `post_manipulation`과 일반 gate look을 요청한다. 수정 전 `self.sweep['mode']`에서 `TypeError`, 수정 후 팔 명령·view reset·reanchor 없이 정상 종료한다. 충돌 검사 자체를 mock하지 않았다.

추가 경계 검사는 loaded/unloaded의 xy·yaw 허용 상한과 직후, NaN/Inf, 안전한 full/short/조작 경계 sweep을 포함한다. 기존 memory_v2 및 기록 23개 SHA-256 보존 검사도 통과했다.

## 실행 방법

기존 환경 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다.
모든 pytest 프로세스는 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`로 시작했고 `--basetemp=./.pytest_tmp`를 사용했다. OpenCV GCD는 `setNumThreads(0)`으로 병렬 영역을 끄고 `getNumThreads()==1`을 확인했다. 종료 후 `.pytest_tmp`를 삭제했다.

- `review-fixes/run_review_tests.py -q --basetemp=./.pytest_tmp tests/test_owncam_memory_v3_review4.py`: 새 테스트.
- 같은 wrapper에 다음 `tests/*.py` 12개를 전달: `test_owncam_memory_v3_review4`, `test_owncam_memory_v3_review3`, `test_owncam_memory_v3_review2`, `test_owncam_memory_v3_review`, `test_owncam_memory_v3`, `test_owncam_memory`, `test_m1_owncam`, `test_owncam_localizer`, `test_visual_attachment`, `test_wrist_zone_skill_v9`, `test_map_goto`, `test_visual_box_skill`.
- 이 폴더의 `reproduce_baseline.py`: 두 v3 runtime 모듈만 `git show`로 메모리에 읽는다. checkout/index/소스는 바꾸지 않으며 exit 1 / 14 failed가 기대 결과다.
- 이 폴더의 `check_ci_caps.py`: 수치 라이브러리를 cap 1로 초기화한 뒤 `mock.patch.dict`로 외부 환경을 cap 2로 설정하여 기존 runner 테스트의 내부 cap 1 patch가 독립적으로 작동하는지 확인한다. patch 종료 후 환경 복원도 확인한다.

## 검증 범위와 남은 사항

전체 프로젝트/원격 CI와 실제 로봇/시뮬레이션 주행은 실행하지 않았다. `git fetch origin`은 샌드박스의 FETCH_HEAD 쓰기 제한, `gh pr list`는 GitHub 네트워크 접근 실패로 최신 원격 상태를 확인하지 못했다. 최종 검증은 제공된 로컬 HEAD와 미커밋 수정에만 적용된다.

v2 원본·과거 리뷰 기록·fixture·DRAFT를 유지한다. 노출된 v2 test fixture는 개발 회귀용이며 v3 미개봉 test로 세지 않는다. 새 실험 결과가 없으므로 TensorBoard snapshot/영상은 만들지 않았다. UGRP 예외에 따라 Google Drive 작업은 없다. 코드·로그 해시는 `verification.json`에 보존한다.
