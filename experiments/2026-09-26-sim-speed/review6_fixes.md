# PR #236 6차 P1 수정·검증 — 2026-09-27

기준 HEAD: `56697ab25a35858a5e5f61b8a14aeae9644783c8`. 지정된
`codex-236-review6.md`의 마지막 소유권 조회와 개별 PID 신호 사이 TOCTOU를 수정했다.
이 기록은 미커밋 수정본의 기능 검증이며 새 연구 실험·성능 비교 결과가 아니다.

## 변경과 수명 보장

- `start_new_session=True`인 직접 자식이 PID = PGID = SID인 리더가 된다.
  루프는 `waitid(WEXITED | WNOHANG | WNOWAIT)`로 종료를 관측한다.
  그룹에 보낼 신호가 끝날 때까지 종료한 리더도 회수하지 않아 PID/PGID를 고정한다.
- 후손 조회는 이상 상태 진단에만 쓴다. 최종 조회 뒤 후손 PID가 재사용돼도
  실제 신호는 고정된 원래 그룹의 `killpg()`에만 전달된다.
  `scripts/sim_slots.py`의 개별 PID `os.kill()` 호출은 제거했다.
- 신호 핸들러는 요청만 보류한다. 정상 경로는 그룹 종료 확인 뒤 `wait()`로,
  오류 경로는 이후 신호 전달이 불가능한 `finally`의 비차단 `poll()`로 회수한다.
  회수 도중/직후 신호를 주입하는 기존 반례도 보존했다.
- 살아 있던 리더가 waitid와 libproc 조회 사이에 종료한 경우도 중단 요청을
  유지해 다음 루프에서 후손에게 전달한다. SIGINT/SIGTERM 각각 반례를 추가했다.
- 관측한 후손이 `setsid`·`setpgid`로 그룹을 벗어나면 해당 PID에는 신호를
  보내지 않고 오류 70으로 끝낸다. CLI `finally`는 래퍼의 슬롯 FD를 모두 닫는다.
  첫 관측 이전의 detach는 발견을 보장할 수 없어 시작 시 명시적으로 경고한다.
  다른 프로세스가 상속한 FD는 계속 예약을 유지하며 강제 `LOCK_UN`하지 않는다.
- 기본 SIGCHLD와 직접 자식의 독점 wait 소유권이 전제다. 외부 reaper,
  다른 스레드의 waitpid, C 코드의 `SA_NOCLDWAIT` 설정은 지원하지 않는다.
  waitid의 ECHILD는 정상 종료로 처리하지 않는다.

## macOS 지원 확인

실제 호스트는 Darwin 27.2.0 arm64다. 프로젝트의 Python 3.12.13에는
`os.waitid`가 없지만 OS libc가 이를 지원한다. SDK의 `sys/signal.h`와
`sys/wait.h`를 확인해 `siginfo_t`와 waitid를 ctypes로 연결했다.
이 호스트의 구조체 크기는 104바이트다. Python 3.13.5에서는 네이티브
`os.waitid` 경로를 사용했다. [Python 공식 문서](https://docs.python.org/3.13/library/os.html#os.waitid)도
macOS의 Python 노출이 3.13에서 추가됐음을 명시한다.

두 Python에서 모두 실제 자식의 종료를 반복 관측하고 `Popen.returncode=None`을
확인한 뒤 마지막 `wait()`가 원래 종료 코드 7을 반환했다. 회수 뒤에는 ECHILD였다.
즉 API 존재 확인뿐 아니라 실제 커널의 미회수 상태 유지를 검사했다.

## 반례·회귀검사

| 범위 | 결과 |
|---|---|
| `56697ab2` 원본에 마지막 조회 **전** PID 재사용 주입 | SIGINT/SIGTERM 2 passed |
| 같은 원본에 마지막 조회 **후** PID 재사용 주입 | **2 failed**, 두 신호 모두 다른 작업 PID 333에 전달됨 |
| 수정본 전체 관련 검사 | **222 passed, 122 subtests passed**, 14.97초, skip 없음 |
| 실제 macOS 후손 중단 | 리더 종료·미회수 확인 → SIGINT/SIGTERM 수신 → 래퍼 130/143 → 리더 회수·held=0 |
| 실제 macOS `setsid`/`setpgid` 이탈 | 중단 요청을 받은 래퍼가 오류 70, 후손 신호 미수신·계속 생존, held=0; 후손은 stop 파일로 종료 |

3차·5차의 기존 테스트 이름과 반례 조건을 유지했다. 조기 `poll()`을 전제로 한
mock과 실제 OS 관측 장치만 새로운 미회수 관측/최종 회수 경계로 옮겼다.
개별 PID 신호 금지, 신호 전달 시 리더 미회수, 종료 후 최종 회수 assertion을
추가했다. 2차·4차 테스트 파일은 변경하지 않았다. 5차의 조회 오류·미관측 후손·
식별자/그룹/세션 변경 14조건에서 신호 0회·오류 70·전체 슬롯 FD 해제 검사를 유지했다.
새 6차 파일은 13개 검사이며 offline CI 목록에도 등록했다.

실제 OS 통합검사는 임시 슬롯 디렉터리와 격리된 admission census를 사용한다.
프로세스 생성·세션·그룹·waitid·libproc·신호·flock은 실제 macOS 동작이다.
실제 OS의 PID 공간을 소진해 재사용을 강제한 시험은 아니다. 재사용 경합은
메모리 주입으로 재현했다. 첫 실행의 4개 실패는 새 테스트 장치의 두 문제
(종료한 mock 리더가 live로 남음, detached 자식이 stderr pipe를 계속 보유함)였고,
장치를 수정한 뒤 95개 관련 검사와 최종 전체 검사가 통과했다. 실패 로그도 보존했다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_sim_speed_review6.py tests/test_sim_speed_review5.py \
  tests/test_sim_speed_review4.py tests/test_sim_speed_review3.py \
  tests/test_sim_speed_review2.py tests/test_sim_speed_tools.py \
  tests/test_sim_slots.py tests/test_exact_speedups.py \
  tests/test_sim_speed_runtime.py::ProfileRestoreTests tests/test_m1_owncam.py \
  --basetemp=./.pytest_tmp
```

기록: [기존 HEAD 반례](review6_validation/pytest_56697ab2.txt),
[반례 실행기](review6_validation/check_baseline.py),
[첫 검사](review6_validation/pytest_targeted.txt),
[장치 수정 후 검사](review6_validation/pytest_targeted_after.txt),
[최종 검사](review6_validation/pytest_final.txt),
[환경·소스·기록 해시](review6_validation/provenance.json).

모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 적용했다.
완료 후 `.pytest_tmp`를 삭제했다. `git diff --check`를 통과했고 커밋·push·병합은
하지 않았다. 기존 실험 기록·raw·기본 체크아웃을 수정하지 않았다.

시작 시 `git fetch origin`은 공용 Git 메타데이터 쓰기 제한으로,
`gh pr list`는 네트워크 제한으로 실패했다. GitHub 커넥터 대체 조회도
301/422 오류여서 원격 PR HEAD·열린 PR 상태는 이번 작업에서 재확인하지 못했다.
전체 CI·실제 Linux 통합·새 전체 에피소드·성능 비교는 실행하지 않았다.
공용 agent lock의 시작 시 상태는 비어 있었으며, 이번 검사는 격리된 임시 예약을
쓰는 기능 회귀검사다. 공유 physics 잠금을 획득한 성능 측정으로 해석하지 않는다.
새 연구 결과가 없어 TensorBoard 변환은 하지 않았고 Drive는 사용하지 않았다.
