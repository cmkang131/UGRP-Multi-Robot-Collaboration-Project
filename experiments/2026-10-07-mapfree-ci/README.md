# PR409 CI 복구 — 과거 번들 해시 검사

2026-10-07, 원 head `a43afb7550795411f95412d200247b3cba8530ec`.
[실패 job](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37600011432/job/112722375542):
shard2/8의 `RegisteredAsANewBundle.test_the_manifest_has_nothing_else_new` 한 건 실패
(1277 passed/23 skipped/41 subtests). 집계 offline-regressions 실패는 이 실패의 전파다.

`self-map-own-prob-v1` manifest는 당시 `self_wall_memory.py` SHA256
`0e5d0ef85ae6eb787de6387de40baef4507a47e3bdeeea17154cb2318482d57f`를 봉인했다.
그 뒤 positive-depth/pose graph 옵션이 추가된 현재 파일 SHA는 `d44666fd...`여서
역사 번들을 현재 파일에 대조하면 실패한다. 기존 `self_wall_memory_before_projection_guard.py.txt`와
당시 구현 commit `0c3a7142:harness/self_wall_memory.py`가 모두 원 해시와 정확히 일치한다.
다른6개 파일은 현재도 manifest와 일치한다.

이미 쓰고 있는 odom/CSM/v2의 역사 fixture 검사와 같은 방법으로 해당1파일만
**기존 pre-guard fixture**를 검사한다. expected hash/manifest/fixture/runtime/public_ros_v8은
수정하지 않는다. [pytest-golden 원본](https://github.com/oprypin/pytest-golden)의 버전 관리된
기대 자료를 비교하는 방식과 같으며 플러그인 설치/스냅샷 자동 갱신0.

PR405 worktree와 분리된 `/Users/changmin/projects/ugrp-wt/mapfree-explore`에서 작업한다.
worktree 생성기의 기존15개 등록/cap8 때문에 첫 생성은 거부됐다. 사용자 명시적 분리 작업
요청에 따라 `--allow-over-cap --reason`으로 새 sparse worktree만 추가했다. 기존 worktree
삭제/retire/강제 전환0. 물리·모델·잠금0, PR409 DRAFT 유지.

수정 전 동일1시험 실패를 로컬 재현했다. 수정 후
`tests/test_coela_runtime_self_walls.py tests/test_wall_projection_guard.py` **32시험 통과**.
현재 runtime의 guard off 골든도 포함하므로 역사 fixture 해시 검사만으로 기존 동작 검증을
대체하지 않는다. 원본 manifest/fixture/제어기 변경0. 원격 CI는 push 뒤 별도 확인한다.
