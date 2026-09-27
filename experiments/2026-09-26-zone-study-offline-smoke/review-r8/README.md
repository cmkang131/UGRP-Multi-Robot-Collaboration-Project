# PR 194 R8 수정·오프라인 검증 (2026-09-27)

기준 HEAD `3b86842cf745410021ab5c937e56b6ed74682f12`, 브랜치 `kiro/zone-study-core`.
coordinator가 커밋하는 작업이므로 Git ref/index를 변경하지 않았다.
R8 리뷰 원문 전체와 필수 pre-flight 7항목을 읽고 구현했다.
실제 LLM/HTTP 호출 0회, 물리 실행 0회, 설치 프록시 수정 0회다.

## 변경

- `harness/zone_study_llm_transport.py:63`: private opener의 모든 HTTP redirect 거절,
  client/장부 identity 확인, 네트워크 fence, live 장부의 영속 예산 필수화.
- `harness/zone_pilot_network.py:47`: ledger capability 밖 Python socket/opener/child process
  거절, TCP 기존 연결의 송신도 차단. 악의적인 native code를 격리하는 sandbox는 아니다.
- `harness/zone_event_scheduler.py:333`, `harness/zone_send_ledger.py:115`:
  생성 스레드에서만 예약·전송·정산하도록 강제. 비동기 전송 지원을 주장하지 않는다.
- `harness/zone_pilot_budget.py:99`: SQLite의 전송 전 영속 예약, 파일럿 전체
  600 attempts/5M tokens, POST당 upstream 최대 2회분 차감, 무환불,
  재시작·동시 프로세스 상한 및 source/settings seal.
- `harness/zone_pilot_ledger.py:90`: 원문/이미지 hash, 실효 설정, proxy URL/소스 hash,
  PID/runtime 검사, per-call correlation header·response ID, proxy 로그 구간,
  실패·늦은 응답·정산 저장 실패 시 응답 폐기.
- `harness/zone_pilot_reconcile.py:15`: call→ledger→proxy→upstream→usage 대조와
  원본 trace hash 검사. 익명 POST/429 로그로 완료 판정을 만들지 않는다.
- `scripts/run_zone_study_pilot.py:167`: dry-run 기본 CLI, 명시적 `--execute`와 기존
  budget/PID가 있어야 실호출. 4조건×1회 pre-flight 후 증거 대조를 통과해야
  4조건×3 actor×1회 코호트(최대 1 retry/actor). 동일 전체 예산 사용.
- `harness/zone_study_offline.py:444`: fixture 출력 비용 hook을 분리했다.
  실어댑터는 실제 응답의 고정 tokenizer 비용을 사용하고 제공자 usage와 분리한다.
  기존 fixture 비용·조건 격리·v1–v6 frozen 결과는 그대로 보존했다.
- `configs/simulation_workflows.json`: `zone-study-pilot` 표준 관리 adapter 등록.
  `docs/zone_study_pilot.md`: 실효 설정, 보수적 선택 (b), 7개 gate, 실행/대조/복구 절차.

프록시 파일 hash는 전후 동일하다:
`7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556`.
`max_tokens=1400 → 8192`, `none → LOW`, 모델 `gemini-3.8-flash-low`를
매 call/manifest에 기록한다. 9/25 한국어 파일럿도 같은 경로의 실효 설정을 썼다는
주석을 새 문서에 추가했으며 과거 기록 자체를 고치지 않았다.

## fail-before / pass-after

| 검사 | 결과 |
|---|---|
| 수정 전 두 재현 테스트 | 2 failed. redirect가 후속 요청을 허용했고 cap=2에서 sends=3 재현 |
| 같은 두 회귀 + 기존 r7 adapter | 40 passed |
| 최종 R8 전용 | 51 passed |
| R8 + 기존 Gemini transport/reasoning | 85 passed, 26 subtests passed (중복 합산 금지) |
| 첫 확장 회귀 | 835 passed, 기존 process cleanup의 `ps` 존재 확인 1 failed |
| 최종 확장 회귀 | 845 passed, 위 환경 제한 테스트 1 deselected |
| 전체 runner 모의 흐름 강화 확인 | pre-flight 4 successes + cohort 12 successes, 공유 예약 32 upstream attempts |
| 실제 CLI dry-run / 로컬 budget init / workflow plan | 네트워크 0회, 초기 4회 예약 상한 949,268 tokens / 8 upstream attempts |

모든 pytest는 `OMP_NUM_THREADS=1`, 지정 Python,
`--basetemp=.tmp/r8/<검사명>`으로 실행했다. 타이밍 수치는 성능 비교가 아니다.
최종 명령:

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study*.py tests/test_zone_event_scheduler.py tests/test_zone_sim_cost.py \
  tests/test_simulation_workflow_manager.py -q \
  -k 'not test_parent_exit_cleans_background_child' --basetemp=.tmp/r8/final-regression
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_review_r8.py -q --basetemp=.tmp/r8/final-r8
```

추가한 실패 주입은 네 조건의 429/503/전송 후 timeout/깨진 응답,
request·response·SQLite settlement 저장 실패, wall/SIM 늦은 응답,
다른 thread 전송, 전체 cap 직전 8개 DB connection 경쟁,
5M 토큰 거절, 사용량 상한 초과 후 추가 전송 차단, 기록 재열람/무환불을 포함한다.
네트워크는 socket 수준에서 실패시키거나 HTTP handler/오프라인 wire를 주입했다.
`--execute` 분기 통합 테스트도 fake wire만 사용했다.

기존 process cleanup 테스트의 실패는
`PermissionError: [Errno 1] Operation not permitted: 'ps'`다.
cleanup 함수가 반환된 다음 존재를 조회하는 환경 제한이며, 통과로 표시하지 않는다.
coordinator는 제한 없는 환경에서 이 테스트를 포함해 재실행한다.

## coordinator에게 남기는 실행 작업

1. 변경을 검토하고 커밋한다. primary checkout 갱신·PR 병합은 이 작업에서 하지 않았다.
2. 위 `ps` 테스트를 포함한 회귀를 재실행한다.
3. `docs/zone_study_pilot.md`에 따라 실제 proxy PID/listener/소스 버전을 확인하고
   공용 잠금·프로세스 소유권을 확보한다. 이번 작업에서는 실제 runtime PID 검증도 하지 않았다.
4. 커밋 후 **새 파일럿을 처음 시작할 때 한 번만** budget을 생성한다. 검증용
   `.tmp/r8/init-validation.sqlite`는 미커밋 소스를 봉인한 로컬 테스트 파일이므로
   실제 파일럿에 사용하지 않는다. 실 raw는 primary `outputs/`에 저장한다.
5. 명시적 `--execute --budget-file ... --proxy-pid ...`로 초기 4회를 수행하고
   실제 call→upstream→usage를 대조한다. 현 proxy 일반 로그에는 식별자가 없어
   이 로그만으로는 코호트 gate가 열리지 않는다. 실제 trace 증거를 얻기 전에는
   확대하지 않는다. 모든 실패·재시도·재시작에서 같은 budget을 계속 쓴다.
6. 새 실호출 결과가 생긴 뒤 TensorBoard 새 snapshot·실제 데이터 재열람을 수행한다.

이번 수정은 오프라인 연결/회계 검증이다. 제공자 실제 과금, 실호출 성공,
물리 성공, TensorBoard 실결과 표시를 확인했다는 의미가 아니다.
raw 테스트 출력은 worktree `.tmp/r8/`에 보존하며 Git 대상에서 제외했다.
작은 fail/pass 로그와 source/raw hash는 이 디렉터리에 저장했다.
