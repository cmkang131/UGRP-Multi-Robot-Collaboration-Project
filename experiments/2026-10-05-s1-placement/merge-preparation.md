# PR #392 최신 main 통합과 병합 준비 (2026-10-06)

작업 경로는 `/Users/changmin/projects/ugrp-wt/s1-placement`, 브랜치는
`codex/s1-placement`다. 기본 체크아웃의 `AGENTS.md`와 README·현재 상태·
CONTRIBUTING을 먼저 읽었다. 사용자 지시에 따라 PR은 DRAFT 유지·병합 금지다.

## 통합과 보존

- 시작 HEAD/원격: `a61be1da7c936169d4f2e57e6a9c13c6359eebb6`.
  작업 트리 clean, origin `https://github.com/kcm0127-dotcom/ugrp.git` 확인 후 fetch했다.
- 통합 main: `bc71cddc9c0835e0b35cac241aaad2a5fad0b0aa` (#391, S2 v106).
  `git merge --no-commit --no-ff origin/main`을 실행했으며 충돌은 없었다.
  rebase·강제 push·다른 worktree/PR 수정은 하지 않았다.
- main에서 추가·수정된 파일 중 공통 색인/시험 목록 외 22개는 main blob과
  바이트가 같음을 확인했다. S2 코드·설정·시험·기록을 수정하지 않았다.
- `experiments/README.md`의 main 모든 행을 보존하고 누락된 S1 링크를 추가했다.
  S2 색인 내용을 이번 작업의 증거로 사용하거나 갱신하지 않았다.
- `configs/ci_test_durations.json`은 시작 HEAD와 바이트 단위로 같다.
  `scripts/run_ci_tests.py`는 S1 장면 시험과 S2 두 시험 등록을 모두 보존했다.
  8 shard의 정확히 한 번 포함·합집합 검사 통과: 479개 파일.
  새 S2 두 파일은 기존 정책의 중앙값 0.76초를 사용한다.
  shard 예상 합계 1122.49–1122.50초는 실제 CI 시간 측정이 아니다.

## 관련 오프라인 시험

지정 Python으로 pytest 한 프로세스만 실행했다. 물리 잠금은 사용하지 않았다.

```sh
CI=true OMP_NUM_THREADS=2 PYTHONPATH=. \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_final_env.py tests/test_zone_environment_registry.py \
  tests/test_zone_scenario_scene.py tests/test_ci_sharding.py \
  --junitxml=outputs/pr392-main-merge-20261006/selected-tests.xml
```

결과: **263 passed in 47.38s**. 지도·registry·정적 혼합 배치·XML 변환·
CI 목록/시간 자료/shard 분할을 확인했다. 시험 성공 뒤 통합 커밋을 만든다.
`git diff --check`와 `git diff --cached --check`도 통과했다.
새 시뮬레이션·모델 호출·렌더는 수행하지 않았다.

## 기존 정지·렌더 근거 확인과 남은 범위

README 후속 기록의 실행 소스는 `35034c5bb13cc189d70d39c599de3c14c3eea03e`다.
dev_s1lite/전체 s1 raw의 `files-sha256.json` 각 29개, 총 58개 파일을
재해시해 전부 일치함을 확인했다. 두 summary의 source SHA·30 SIM초·
DEV screen PASS·placements_match·새 명령/모델 호출 0도 다시 확인했다.
이는 기존 결과의 무결성 검사이며 통합 HEAD에서 물리 성공을 재검증한 것이 아니다.

정지/렌더 범위·유한 바닥 침투·TensorBoard UI 미확인 항목은 README 마지막 절을
그대로 따른다. 실제 운반·파지 도달성·S1 졸업·S2 제어기 연결·본 연구 코호트는
미검증이다. PR 본문에는 기존 정지/렌더 결과와 이 통합 검증을 반영한다.
기존 실험 자료를 변환하거나 TensorBoard viewer를 다시 시작하지 않았다.

로컬 작업 증거는 이 worktree의 `outputs/pr392-main-merge-20261006/`에 둔다:
`selected-tests.log/xml`, `merge-preservation.json`, `shards.json`,
`existing-settle-evidence.json`, push 후 전체 CI 조회 결과 및 PR 본문/2줄 코멘트.
최종 CI 결과는 PR 본문·코멘트와 같은 로컬 경로에 남긴다.
Google Drive 작업·raw 삭제/덮어쓰기·다른 작업 프로세스 종료는 하지 않았다.
