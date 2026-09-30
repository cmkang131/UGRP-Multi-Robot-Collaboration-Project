# 연구 관리 v2: 작은 CI·sparse 개선

2026-09-30, Codex. 작업 경로는 `ugrp-wt/proc-v2`, 브랜치는
`codex/process-v2`다. 시작 시 깨끗한 HEAD와 `origin/main`은 모두
`d17ca4345affef8cf027e121cf1f3197b36c23e0`이었다. 구현 소스는 이 기록을
포함한 PR의 commit으로 식별한다. 기존 측정·raw·봉인·모델은 변경하지 않았다.

입력은 병합된 [MEASUREMENTS.md](MEASUREMENTS.md)(PR #296)와
PR #295의 `LITERATURE.md`(조회한 원격 HEAD
`1cc21b8f877c28b3f45ecea996b1d4963ec65aeb`)다. 문헌 PR은 초안이며
제안 전체를 채택하지 않는다. 이번에는 중복 CI·문서 경로·작은 fixture만
구현하고 짧은 진행 규칙을 추가한다. 봉인 의존성·번호 자동화는 후속 설계다.

## 변경과 경계

- feature branch push 전체 실행을 없애고 `pull_request`와 `main` push를
  유지한다. 같은 PR ref의 이전 실행만 취소한다. main 실행은 개별 run ID로
  나누어 취소하지 않는다. PR merge-ref checkout과 기존 검사 이름을 유지한다.
- `ci-preflight`가 checkout 직후 fixture·CI 분기/집계의 정적 회귀검사를
  한다. Python 표준 라이브러리만 쓰므로 모델·시뮬레이터 설치가 필요 없다.
- Git의 base→head merge-base diff 전체를 NUL 구분으로 읽으며 API 페이지나
  300파일 경로 제한에 의존하지 않는다. rename 탐지를 끄고 이전/새 경로를
  모두 검사한다. root Markdown, `experiments/` Markdown,
  `docs/`의 `.md/.rst/.txt/.pdf/.png/.jpg/.jpeg/.gif/.webp/.svg`만
  문서 전용으로 허용한다. 코드·설정·테스트, 모르는 경로·빈 diff·비교 실패,
  main push는 전체 검사다. 사전 등록·판정 문서 검토는 그대로 필요하다.
- workflow 전체에 `paths-ignore`를 넣지 않는다. `offline-regressions`는
  `always()`로 실행하고, preflight 성공과 명시적인 문서 판정이 있을 때만
  suite의 의도된 건너뜀을 허용한다. 전체 경로의 실패·취소·건너뜀, preflight
  실패·취소·건너뜀과 누락/잘못된 출력은 통과시키지 않는다.
- 기존 suite job 9개의 명령·matrix·환경·artifact를 유지한다. 코드 PR은
  새 preflight 뒤 기존 전체 검사를 실행한다. 현재 보호 API의 필수 검사
  `offline-regressions`(GitHub Actions app 15368, strict=true)는 변경하지 않는다.
- #265에서 빠졌던 v3/v4/v5의 `example_trial_record.json.gz` 3개를
  sparse 예외에 넣고 로컬 pytest·공용 잠금 전에 누락을 거부한다. 합계
  **158,676 bytes = 155.0 KiB**다. 현재 worktree도 `git sparse-checkout add`
  로 이 파일만 복원했으며 각 원래 `raw_index.json` SHA-256과 일치했다.
  누락을 성공/skip으로 숨기지 않는다. `--list-shards`의 무실행 경로는 유지한다.
- AGENTS에 9줄을 추가했다. 검토/인수 병렬화, 지적 묶음 처리, 먼저 작은
  알려진 사례 확인, 문서 CI, 제어기·사전 등록 PR 약 3개 제한, 탐색/확증
  분리다. 추가 절을 제거하면 기존 AGENTS와 바이트가 같다. 병합 권한·가드와
  실제 실행 권한·잠금은 그대로이며 이번 PR은 Draft 유지·병합하지 않는다.

## 검증

- `python3 scripts/run_ci_tests.py --shard-count 8 --list-shards`: **329개 파일,
  8개 shard(42/41/41/41/41/41/41/41), 중복·누락 0**. 기존 328개 파일에
  CI fast-path 회귀 파일 1개가 추가됐으며 pytest·잠금을 시작하지 않았다.
- `python3 -m unittest -q tests.test_ci_fast_path`: 10개 통과. 기존 공식 환경
  Python 3.12.13에서도 같은 10개가 통과했다. 실제 임시 Git
  저장소에서 문서 추가/삭제, 코드→문서 rename, 공백·개행 경로를 확인했다.
  필수 집계 shell의 preflight/선택값/shard/check 결과 **256조합**에서
  정상 전체 검사와 의도된 문서 경로만 통과한다.
- 변경 관련 pytest: **89 passed, 4.14초**(로컬 Python 3.13.5 / pytest 8.3.4).
  CI 분기·sharding·공용 잠금, 실제 새 sparse worktree의 예외 보존,
  archive 예외 목록과 추적 파일 일치, 복원 fixture 3개 원래 버전의 감사가
  모두 통과했다. 실행은 공용 잠금을 획득한 `run_ci_tests.run_locked`를
  거쳤으며 완료 후 자신의 잠금·자식을 정리했다.
  Python 3.12/pytest 9.1.1로 89개를 다시 확인하려던 실행은 다른 작업의
  공용 잠금 때문에 시작되지 않고 종료 코드 3을 반환했다. 이 재검사는
  통과로 세지 않으며, 잠금을 우회하거나 다른 작업을 중지하지 않았다.
- 더 넓은 첫 검사: **97 passed, 10 failed, 14.36초**. 실패 10개는
  `test_agent_worktree.py`의 기존 정리·유휴 검사에서 샌드박스가 `ps` 실행을
  거부한 `PermissionError: Operation not permitted`다. 정리 가드를 변경하거나
  우회하지 않았다. 이 실행을 전체 통과로 표시하지 않는다.
- actionlint는 설치되지 않아 Python/PyYAML로 workflow를 파싱했다.
  기존 suite job에서 새 `needs/if` 두 키를 제거한 객체가 원본과 같은지,
  필수 이름·PR 이벤트·main push가 유지되는지 확인했다. `git diff --check`
  통과. GitHub workflow 실행기의 실제 표현식·job 상태 보고는 원격 확인 대상이다.

## 예상 절감과 확인하지 않은 것

| 기존 관찰 | 이번 변경의 예상 효과 | 한계 |
|---|---|---|
| 동일 SHA push/PR 중복 13쌍, push job 합계 **16.71 runner-hours** | 같은 유형의 feature push 점유 제거 | 제거 대상 계산량이다. 16.71시간 연구 지연 절감이나 이번 PR의 실측 효과가 아니다. main push는 유지 |
| Markdown-only PR 3개 전체 CI **450/490/613초**, 합계 **25분 53초** | 문서 경로에서 회당 **7.5–10.2분**의 전체 실행 대신 가벼운 preflight+집계만 실행 | 새 경로의 checkout·러너 대기·집계 시간은 차감해야 한다. 실제 절감은 후속 문서 PR에서 확인 |
| #265 전체 검사 **853+831초**, 같은 fixture 누락 3건 반복 | 누락이면 pytest 전에 즉시 명확히 실패, 새 sparse worktree에는 fixture 포함 | 합계 28분 4초가 모두 낭비였거나 전부 절약된다는 뜻은 아니다 |

새 physics/sim·렌더·학습·모델 호출·코호트를 직접 실행하지 않았다.
이 PR 자체는 코드/CI 변경이므로 GitHub에서는 기존 전체 workflow 대상이다.
원격 CI의 통과·실제 dedup·문서-only 상태 보고·개선된 시간은 이 로컬 검사로
확정하지 않는다. 구현 전의 성공 cohort를 새 구현의 성능으로 승계하지 않는다.
새 연구/학습/평가 결과가 없어 TensorBoard 변환은 하지 않으며, UGRP 예외에
따라 Drive 조회·업로드도 하지 않는다. 기록은 이 로컬 프로젝트와 PR에 보존한다.

## 참고 자료

- Refs [PR #295](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/295),
  [PR #296](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/296).
- GitHub Docs, [Handling skipped but required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks):
  workflow 경로 필터는 필수 검사를 Pending으로 남길 수 있다. job 조건과
  `always()` 집계를 사용하되 선택한 검사의 성공 여부를 명시적으로 대조한다.
- GitHub Docs, [Workflow concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency):
  workflow와 PR ref로 그룹을 나누고 PR 실행에만 취소를 적용한다.
