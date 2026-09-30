# PR #300 미디어 검사 훅 회귀 수정

## 원인과 수정

- 원래 실행 SHA: `3f4864e64c13cca79473a2ebd201271d08b4b4e0`.
  [Actions run 36705619932](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36705619932)의
  shard 2/8은 `test_pre_commit_hook_warns_but_keeps_20_mib_block`에서 실패했다.
  최종 검사 집계는 통과 31개, 실패 2개(해당 shard와 `offline-regressions`)다.
- 훅 자체의 새 단계가 아니라 `check_media_size` → `agent_worktree` →
  `check_ci_fixtures`의 간접 import가 원인이다. 임시 저장소에 마지막 모듈이
  없어 `ModuleNotFoundError`가 발생했다. 훅의 `|| true`로 커밋은 됐지만
  미디어 경고가 없어져 테스트가 실패했다.
- 확장자 목록을 표준 라이브러리만 쓰는 `check_media_size.py`로 옮기고
  `agent_worktree.py`가 가져오도록 의존 방향을 바꿨다. 25개 확장자의 값과
  순서는 동일하다. 훅의 경고 전용 동작과 20 MiB 초과 차단은 유지한다.
  CI 실행기의 fixture 사전 검사는 그대로 유지한다.
- 임시 저장소 훅 검사는 검사기 단독, worktree 도구는 있으나 새 모듈은 없음,
  모든 도구는 있으나 실제 frozen fixture는 없음의 세 구성으로 보강했다.
  부모 `PYTHONPATH`를 제거하고 실제 Git commit에서 2 MiB 경고·21 MiB 차단과
  traceback 부재를 검사한다.
- `tests/`와 `scripts/`의 훅·복사·의존성을 검색했다. 실제 훅을 복사하는
  테스트는 `test_check_media_size.py`이며, `test_agent_worktree.py`는 임시
  worktree의 훅 설정을 검사한다. 확장자 목록의 다른 사용자인
  `test_disk_report.py`도 검증 대상에 포함했다.

## 검증 상태

- `git diff --check` 통과. AST로 이전·이후 확장자 목록 25개 일치 확인.
- Python 3.12.13 / pytest 9.1.1에서 공용 잠금을 획득한 실행기로 네 파일
  전체를 검사했다: **30 passed, 10 failed, 280 subtests passed, 17.80초**.
  `test_check_media_size.py` 8개, `test_ci_fast_path.py` 10개,
  `test_disk_report.py` 2개가 모두 통과했다. `test_agent_worktree.py`는
  10개 통과·10개 실패이며, 실패는 전부 샌드박스가 `ps` 실행을 거부한
  `PermissionError: [Errno 1] Operation not permitted: 'ps'`다.
  훅 설치·sparse 생성 검사는 통과했고, 정리·유휴 보호 검사는 환경 제한으로
  확인하지 못했다. 보호 코드를 바꾸거나 실패를 skip/통과로 바꾸지 않았다.
- 전체 로컬 통과 후 커밋하라는 조건은 아직 충족되지 않았다. 환경 제한을
  제외하고 푸시한 뒤 전체 CI로 검증해도 되는지 사용자 답변을 기다린다.
- 로컬 로그·JUnit·실행 명령은 기본 체크아웃의
  `outputs/pr300-hook-fix/`에 보존한다. 원본 CI 실패 로그도 같은 곳에 있다.
- 새 연구 실험·학습·평가 결과가 아니므로 TensorBoard 변환 대상이 아니다.
  UGRP 예외에 따라 Google Drive 작업은 하지 않는다.
