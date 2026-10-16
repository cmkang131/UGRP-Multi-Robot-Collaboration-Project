# PR #236 4차 P1 수정·검증 — 2026-09-27

기준은 `codex/sim-speed-fix@ff5754671919a6dc43662a5e4b86bfc4b1b65957`이다. 지정 리뷰 `codex-236-review4.md`의 정상 M1 로그 거부를 재현하고 수정했다. 파일 편집만 했으며 커밋·push·병합은 하지 않았다. `git fetch origin`은 Git 메타데이터 쓰기 제한, `gh pr list`는 네트워크 제한으로 실패했다. 기본 체크아웃은 변경하지 않았다.

## 변경 파일과 판정

- `scripts/sim_equivalence.py`: 전체 M1 비교에서 `manifest.json`의 `recording_start_sim_s`와 `controller_events.jsonl`의 `recording_started` 시각을 읽는다. 둘 다 있으면 일치를 요구한다. 잘못된 값·중복 이벤트·충돌은 fallback 없이 `insufficient_evidence`다.
- 명시된 시각이 없으면 첫 프레임과 첫 GT의 유한한 비음수 SIM 시각이 일치할 때만 공통 시작점으로 사용한다. 보고서 `recording_start.A/B`에 시각·출처·`inferred`·첫 샘플 이전을 검증할 수 없다는 한계를 기록한다. `initial_servo_command.t=0`이나 profiler의 물리 초기 시각은 기록 시작점으로 쓰지 않는다.
- 프레임/GT 초기 샘플을 해당 시작점과 비교한다. 첫 스텝 및 로그 반올림 허용치는 기존 timestep과 0.00011초를 사용한다. 기존 중간 간격·종료 범위·개수·인덱스·단계·원본 바이트/해시 검사는 유지한다. 시작점 불명 또는 A/B 시작점 불일치는 `insufficient_evidence`다. prefix 비교의 기존 계약은 그대로다.
- `scripts/run_m1_owncam.py`: 장면 초기화 후 기록용 첫 물리 스텝의 SIM 시각을 샘플 목록과 독립적으로 저장하고 manifest에 내보낸다. 제어 입력·물리 설정·명령·기본 speedup은 변경하지 않았다. 새 전체 에피소드를 실행해 manifest 출력을 재검증한 것은 아니다.
- `tests/sim_speed_fixtures.py`: 프레임/GT 시작을 실제 dev-a8처럼 **1.3003초**로 변경했다. 명령·단계·종료·프로파일 시각도 맞췄으며 초기 servo 명령의 0초는 유지했다.
- `tests/test_sim_speed_review2.py`, `tests/test_sim_speed_review3.py`: 연관 profile fixture와 prefix 창을 조정했다. qpos 반례는 정상 전체 로그에 qpos만 변조하도록 유지했다.
- `tests/test_sim_speed_review4.py`: 명시/추론 시작점 양성, 누락·비정상값·충돌·A/B 불일치·동일한 초기 구간 절단 등 **39개**를 추가했다. `scripts/run_ci_tests.py`의 offline 검사 목록에 등록했다.

## 테스트

최종 신규 테스트를 보존한 수정 전 검사기 모듈에 메모리상으로 로드해 적용하면 **32 failed, 7 passed**다. 수정 후 신규 39개를 포함한 관련 검사는 **187 passed, 122 subtests passed**, 실패·skip 없이 통과했다. 기존 2·3차 반례, 도구·슬롯, exact-v1 커널, profile 복원, M1 계약 검사를 포함한다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/tmp/round4-tests/test-env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_sim_speed_review4.py tests/test_sim_speed_review3.py \
  tests/test_sim_speed_review2.py tests/test_sim_speed_tools.py \
  tests/test_sim_slots.py tests/test_exact_speedups.py \
  tests/test_sim_speed_runtime.py::ProfileRestoreTests tests/test_m1_owncam.py \
  --basetemp=./.pytest_tmp
```

모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 사용했고 완료 후 `.pytest_tmp`를 삭제했다. 슬롯 테스트는 임시 경로와 격리된 census fixture를 사용했다. 실제 호스트 census·전체 CI·새 전체 A/B·성능 비교는 실행하지 않았다. `git diff --check`도 통과했다.

- [최종 테스트를 수정 전 코드에 적용](review4_validation/pytest_before_final_tests.txt)
- [수정 후 전체 관련 테스트](review4_validation/pytest_final.txt)
- [초기 신규 테스트의 수정 전 실패](review4_validation/pytest_before.txt), [1차 수정 후 핵심 검사](review4_validation/pytest_targeted.txt)

## 보존 원본의 실제 compare()

`scripts.sim_equivalence.compare(path, path)`를 원본 디렉터리에 직접 적용했다. 원본은 수정하지 않았다.

| 원본 (`/Users/changmin/projects/ugrp/outputs/m1-owncam-20260926/dev-a8/`) | 수정 전 | 수정 후 | 확인한 JPEG |
|---|---|---|---:|
| `m1dev-s93` | `insufficient_evidence` | `equivalent` | 2,080 |
| `m1devdiag-s95` | `insufficient_evidence` | `equivalent` | 2,309 |

두 원본의 기존 manifest에는 시작점 필드가 없으므로, 일치하는 첫 프레임/GT 시각 **1.3003초**를 추론 기준으로 사용했다. 수정 전에는 네 개의 초기 샘플 오류(A/B × frame/GT)가 있었고 수정 후 `evidence_errors=[]`다. 필수 로그·result 원본 바이트·JPEG 및 완전성 검사를 통과했다. 원본에는 qpos 체크포인트가 없어 해당 항목은 **미비교**로 명시된다. 자기 비교의 회귀 검증이며 새로운 물리 성공이나 속도·A/B 동등성 결과가 아니다. 새 실험 결과가 없어 TensorBoard 재변환은 하지 않았다. Drive도 사용하지 않았다.

- s93: [수정 전](review4_validation/s93_before.json), [수정 후](review4_validation/s93_after.json)
- s95: [수정 전](review4_validation/s95_before.json), [수정 후](review4_validation/s95_after.json)
- [소스·원본 식별 SHA-256](review4_validation/provenance.json)

명시적 시작점이 없는 과거 로그가 두 샘플 스트림 모두 같은 앞부분을 잃고 개수·인덱스·manifest까지 재작성된 경우, 첫 샘플 이전의 누락은 입증할 수 없다. 이는 허용된 fallback의 한계로 결과에 남는다. 새 manifest의 독립 시작점은 같은 절단을 초기 누락으로 거부한다. 기존 전체 A/B 및 누적 상태 체인 미완료·기본값 채택 보류 상태는 유지한다.
