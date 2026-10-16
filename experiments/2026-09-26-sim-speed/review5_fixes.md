# PR #236 5차 P1 수정·검증 — 2026-09-27

기준 HEAD는 `db8ed92140b4cb15b8530c35f7a189d7ec4046fc`다. 지정된
`codex-236-review5.md`의 직접 자식 종료 후 SIGINT·SIGTERM 누락을 수정했다.
커밋·push·병합과 기본 체크아웃 변경은 하지 않았다. 시작 시 `git fetch origin`은
공용 Git 메타데이터 쓰기 제한, `gh pr list`는 네트워크 제한으로 실패했다.

## 변경

- `scripts/sim_slots.py`: `poll()`이 직접 자식을 회수하기 전에 후손의
  PID·시작 식별자·프로세스 그룹·세션을 기록한다. `start_new_session=True`로
  생성한 미회수 자식이 PID/PGID 수명을 유지할 때만 이 목록을 신뢰한다.
  macOS libproc은 미회수 좀비 리더를 목록에서 생략할 수 있으므로,
  살아 있을 때 확보한 시작 식별자와 아직 회수하지 않은 Popen 소유권을 사용한다.
- 리더 회수 후에는 숫자 PGID에 `killpg()`를 보내지 않는다. 현재 그룹의 후손을
  저장된 시작 식별자 및 자기 세션/그룹과 대조하고, 각 PID에 신호를 보내기 직전
  다시 대조한다. macOS에서는 `getsid()` 전후의 libproc 식별자도 확인한다.
  신호 핸들러는 신호만 보류하고, 실제 전달은 이 검증을 거친 루프에서 한다.
- 리더 식별자 없음, 후손 미관측, PID 재사용, 세션/그룹 불일치, 조회 실패는
  해당 프로세스에 신호를 보내지 않는 명시적 오류로 끝낸다. CLI는 오류를 출력하고
  **70**을 반환하며 `finally`에서 자기 슬롯 FD를 모두 닫는다.
  리더 회수 뒤 새로 나타난 PID는 그룹 번호만으로 후손이라고 인정하지 않는다.
- 기존 상속 FD 보호는 유지한다. 슬롯을 강제 `LOCK_UN`하지 않으므로,
  다른 살아 있는 자식이 상속한 슬롯 FD는 그 자식이 닫을 때까지 유지된다.
  오류가 후손의 종료나 상속 예약의 강제 해제를 뜻하지는 않는다.
- `tests/test_sim_speed_review5.py`의 신규 22개 검사를 offline CI 목록에 등록했다.
  기존 테스트 파일은 변경하지 않았다.

## 반례 및 검증

동일한 메모리 반례 2개(SIGINT/SIGTERM)를 Git blob에서 직접 로드한 소스에 적용했다.
Git checkout과 이력은 바꾸지 않았다.

| 실행 소스 | 결과 |
|---|---|
| `78945a3c` | **2 passed** — 중단 전달 후 130/143 종료 |
| `db8ed921` | **2 failed** — 반복 신호에도 후손에게 전달하지 않아 대기 상한 assertion 실패 |
| 수정본 | **209 passed, 122 subtests passed** — 신규 22개와 기존 관련 회귀검사 전체 |

- 기존 3차 PGID 재사용 반례(`during_poll`, `after_reap`)와 live poll의 식별자
  일치/불일치 검사를 수정 없이 통과했다. 2·4차 반례, 슬롯·도구·exact-v1 커널,
  실제 MuJoCo 마지막 상태/복원 반례, M1 계약 검사도 포함했다.
- **실제 macOS 프로세스 통합 2건:** 실행기가 후손을 시작하고 먼저 종료하며,
  후손은 슬롯 FD를 상속하지 않는다. Popen의 실제 `poll()` 완료 마커로
  리더 회수를 확인한 뒤 래퍼에 SIGINT/SIGTERM을 보냈다. 후손이 실제 수신한
  신호, 래퍼의 **130/143**, 최종 **held=0**을 확인했다.
  admission census만 임시 fixture로 격리했다. 세션·그룹·libproc·flock·신호는 실제다.
- 소유권 부정/조회 실패 14조건에서 신호 0회, **70**, 추가 슬롯을 포함한 FD 해제,
  신호 핸들러 복원과 무한 대기 방지를 검증했다. Linux stat의 시작/세션 필드와
  macOS `getsid()` 도중 식별자 변경도 fixture로 검사했다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_sim_speed_review5.py tests/test_sim_speed_review4.py \
  tests/test_sim_speed_review3.py tests/test_sim_speed_review2.py \
  tests/test_sim_speed_tools.py tests/test_sim_slots.py tests/test_exact_speedups.py \
  tests/test_sim_speed_runtime.py::ProfileRestoreTests tests/test_m1_owncam.py \
  --basetemp=./.pytest_tmp
```

모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 사용했다.
최종 검사 14.70초, 실패·skip 없음. 완료 후 `.pytest_tmp`를 삭제했고
`git diff --check`를 통과했다.

기록: [이전 통과](review5_validation/pytest_78945a3c.txt),
[HEAD 실패](review5_validation/pytest_db8ed921.txt),
[수정 후 전체 검사](review5_validation/pytest_final.txt),
[Git blob 반례 실행기](review5_validation/check_baseline.py).
반례 실행기는 프로젝트 루트에서 마지막 인자로 `78945a3c` 또는 `db8ed921`을 받으며,
동일한 OMP 환경 설정을 적용한다.

실제 Linux 호스트 프로세스 통합·전체 CI·새 전체 에피소드·성능 비교는 실행하지 않았다.
Git 커밋을 만드는 `PairProfSourceTests`도 실행하지 않았다.
새 연구 실험 결과가 없어 TensorBoard 변환은 하지 않았고 Drive는 사용하지 않았다.
