`offline-regressions`가 약 19분 49초까지 늘어 20분 제한에 걸린다는 사용자 제보에 따라, 기존 테스트 파일 목록을 8개 병렬 shard로 분할했습니다. 이 작업에서 실제 CI 실행 시간을 측정한 것은 아닙니다.

- 기준 소스: `7f649959f486699f90292361beba1c3610ec50ae`, 브랜치 `codex/ci-offline-split`.
- `TEST_PATTERNS`는 그대로입니다. 기존 glob 확장·중복 제거·정렬 결과인 **302개 파일**을 모두 유지합니다. 새 분할 단위 테스트는 공통 job에서 별도로 한 번 실행합니다.
- 정렬된 파일을 결정적으로 분배합니다. 적용 가능한 파일별 시간 기록이 없어 기본은 파일 수 기준입니다. `--durations-json`에 측정 초를 넣으면 긴 파일부터 누적 시간이 가장 짧은 shard에 배치하고, 미측정 파일에는 현재 목록의 측정 중앙값을 적용합니다.
- 모든 shard 실행 전에 전체 분할의 누락·중복·예상 밖 파일을 검사합니다. 단위 테스트는 실제 workflow의 matrix 번호와 실행/목록 출력의 shard 수가 일치하는지도 검사합니다.
- `offline-regression-shards`는 `fail-fast: false`, 0–7번 matrix, 각 job 제한 10분, `OMP_NUM_THREADS=2`입니다. 파일 경로와 테스트별 시간이 담긴 JUnit 결과를 `offline-shard-*` artifact에 14일 보존합니다.
- `offline-regression-checks`에 기존 bundle `verify-current`, `verify-registry`, 미디어 경고, 3개 protocol fixture 실행과 2개 evidence artifact 단계를 원문 그대로 한 번씩 보존했습니다. checkout/Python/dependency 설치만 shard별로 반복합니다. 다른 기존 job은 변경하지 않았습니다.
- **required status check `offline-regressions`는 이름과 job ID를 유지한 집계 job입니다.** `needs: [offline-regression-shards, offline-regression-checks]`와 `if: always()`를 사용하며, 두 결과가 모두 `success`일 때만 통과합니다. shard 실패·취소·건너뜀 또는 공통 검사 실패는 통과시키지 않습니다. `CONTRIBUTING.md`에 적힌 보호 규칙 이름을 그대로 유지하며, 실시간 branch protection 설정은 조회하지 않았습니다.
- 실행 번들 등록·수정은 없으며 새 bundle ID도 사용하지 않았습니다.

검증 결과:

```text
OMP_NUM_THREADS=2 ../../ugrp/.venv-sim/bin/python -m pytest -q -p no:cacheprovider --basetemp=./.pytest_tmp tests/test_ci_sharding.py
66 passed in 3.43s
```

실행 뒤 `.pytest_tmp`를 삭제했습니다. 테스트는 분할·합집합 검사, 시간 가중치·동률 결정성, 잘못된 입력/빈 shard의 실행 차단, 선택 파일만 pytest에 전달, 기존 잠금 경로와 종료 코드 보존, 집계 결과 16개 조합을 포함합니다. runner의 실제 전체 pytest 실행 대신 호출 경계는 mock으로 검증했습니다.

```text
PYTHONDONTWRITEBYTECODE=1 ../../ugrp/.venv-sim/bin/python scripts/run_ci_tests.py --shard-count 8 --list-shards
기존 파일: 302 / shard 합계: 302
shard 0..7: [38, 38, 38, 38, 38, 38, 37, 37]
누락: 0 / 중복: 0 / 추가: 0
기존 목록 == shard 합집합: true
정렬한 파일 경로를 개행으로 연결한 목록의 SHA-256:
47787906fca8b37774ea00b7393cb9de72d05eab6650c1f0fe051180e224af7c
```

YAML 파싱과 기준 workflow 대조를 통과했습니다. 다른 job과 workflow 최상위 설정은 같고, 기존 공통 검사·fixture·artifact 8단계가 각각 정확히 한 번 남아 있습니다. `git diff --check`도 통과했습니다.

로컬 근거는 이 worktree의 `outputs/ci-split-verification/old-list.json`, `shards.json`, `verification.json`에 저장했습니다. `outputs/`는 Git 제외 경로이며 원격 백업으로 취급하지 않습니다. 이 코멘트 초안은 아직 게시하지 않았습니다.

남은 확인: 관리자가 지정 명령을 재실행하고 커밋·push한 뒤 실제 Actions에서 8개 shard 모두 10분보다 충분히 짧게 끝나는지 확인해야 합니다. 파일 수 균등은 시간 균등을 보장하지 않으므로 편중이 있으면 JUnit 측정값을 파일별로 합산해 모든 shard에 동일한 duration JSON을 적용해야 합니다. 전체 302개 파일의 실제 회귀 실행과 공통 fixture 실행은 로컬에서 수행하지 않았고 시뮬레이션·모델 호출도 하지 않았습니다.

사용자 지시에 따라 Git metadata 수정·fetch·GitHub 호출·커밋·push·댓글 게시·병합은 하지 않았습니다. 로컬 origin은 `https://github.com/kcm0127-dotcom/ugrp.git`으로, 요청에 적힌 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`와 다르므로 관리자가 push 전에 대상 저장소를 확인해야 합니다. 커밋 메시지는 worktree 루트의 `COMMIT_MSG_CODEX.txt`에 준비했습니다.
