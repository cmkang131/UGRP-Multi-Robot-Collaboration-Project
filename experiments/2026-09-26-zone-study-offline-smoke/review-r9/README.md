# PR 194 R9 P1 수정·오프라인 검증 (2026-09-27)

기준 HEAD `59bb3435570235efc5f8c3c6111e5ad42984127e`, 브랜치 `kiro/zone-study-core`.
coordinator가 커밋한다. 실 LLM/HTTP 호출·물리 실행·설치 프록시 수정·Git 커밋은 0회다.
R9 리뷰 전체를 읽었고, 기존 v1–v6 및 R8 기록은 변경하지 않았다.

## 변경과 위치

- `harness/gemini_proxy.py:156`: 문자열을 반환/거절하기 전에 종료 이유·본문·usage를 보존한다.
  연구 client의 strict 모드와 transport에서 `stop` 외 종료를 거절한다.
- `harness/zone_completion.py:55`: 공통 종료 판정. 빈/불완전/fenced JSON, 필수 필드
  누락/추가, refusal·tool call·본문의 차단 신호도 거절한다. `:127`의 성공 판정은
  call status `ok`와 정상 completion을 모두 요구한다. 과거 reason 누락은 unknown이다.
- `harness/zone_study_llm_transport.py:127`: 행동·메시지 파서/relay 전에 종료 판정.
  비정상 완료, 늦은 응답, 응답 저장·SQLite 정산·pipeline 예외에서도 관측한 reason과
  생성 토큰/발화 비용·usage를 보존하고 실패 호출로 반환한다.
- `harness/zone_event_scheduler.py:166`, `harness/zone_sim_cost.py:405`:
  불변 reply metadata → scheduler ledger → call `cost_terms.completion` 전달.
  SIM horizon의 censored 호출도 종료 이유를 보존한다.
- `harness/zone_pilot_ledger.py:114`, `harness/zone_pilot_budget.py:170`:
  원문 응답에서 completion·생성 비용을 먼저 추출하고 영속 정산에 보존한다.
  비정상 완료는 `completion_rejected`, 예약 차감은 그대로다. 정산 저장 자체가 실패하면
  기존 `reserved_unknown` 차감을 남기고 행동을 차단한다.
- `harness/zone_study_eval.py:525`, `scripts/run_zone_study_pilot.py:270`:
  평가와 파일럿이 같은 종료 판정으로 성공을 집계한다. 기존 `completed_calls`는
  비검열 호출 수로 실패도 포함하며 성공 수와 구별한다.
- `harness/zone_pilot_reconcile.py:113`: 코호트 진입 시 hashed trial 원문과 영속 ledger의
  정상 완료를 확인한다. 과금 대조가 끝났거나 `successful_calls=1`이라는 요약만으로
  비정상 응답을 성공으로 취급할 수 없다.
- `docs/zone_study_pilot.md:61`: proxy 종료 이유 손실과 판정 범위를 설명하고 모든
  dry/실행 manifest·source identity·proxy profile·reconciliation에 한계를 표시한다.
  `scripts/run_ci_tests.py`에 R9 테스트를 등록했다.

## fail-before / pass-after

| 검사 | 결과 |
|---|---|
| 기준 SHA에서 유효한 JSON + usage + `length` | **4 failed**. 네 조건 모두 행동 1개가 채택됨 |
| 동일 반례, 수정 후 | **4 passed**, 행동·메시지 0, 사용량/예약 보존 |
| 최종 R9 회귀 + 기존 R8 | **157 passed** (R9 106개 + R8 51개) |
| 확장 study/scheduler/cost/workflow/Gemini 회귀 | **1,039 passed, 26 subtests passed**, 환경 제한 검사 1개 제외 |
| 실제 CLI 기본 dry-run | model/network calls **0**, 네 조건 요청 준비 및 completion limitation manifest 확인 |
| 기존 자료·SIM 비교 | frozen hash/버전별 감사, v5 SIM trace·입력 hash parity 회귀 통과 |

수정 전 실행 로그와 당시의 독립 반례 소스는 `fail-before.txt`, `counterexample_before.py`다.
최종 집중 검사는 확장 검사 도중 보완한 기존 `not_sent` 중단 조건까지 포함한다.
두 검사 집합은 중복되므로 테스트 수를 합산하지 않는다. 시험 시간은 성능 비교가 아니다.
R8에서 확인된 sandbox `ps` 권한 제한 때문에 `test_parent_exit_cleans_background_child`는
이번 확장 검사에서 제외했으며, 통과했다고 보고하지 않는다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_review_r9.py tests/test_zone_study_review_r8.py -q \
  --basetemp=.tmp/r9/final-focused
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study*.py tests/test_zone_event_scheduler.py tests/test_zone_sim_cost.py \
  tests/test_simulation_workflow_manager.py tests/test_gemini*.py -q \
  -k 'not test_parent_exit_cleans_background_child' --basetemp=.tmp/r9/final-regression
```

R9 실패 주입은 네 조건의 length/content_filter/tool_calls/SAFETY/MAX_TOKENS/누락,
빈·잘린·필드 누락 JSON, refusal, 본문 SAFETY 차단 신호, SIM/wall 늦은 응답,
저장·SQLite·pipeline 예외, 고장 난 usage, client strict flag 우회,
실제 runner 분기의 성공 집계/중단, 거짓 성공 요약의 코호트 진입 거절을 포함한다.
모두 socket 송신을 금지한 offline wire다. tests의 `--execute` 분기는 fake runtime/wire만 쓴다.

## 남는 한계와 coordinator 작업

설치 프록시 hash는 감사 버전
`7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556`와 일치한다.
프록시는 `MAX_TOKENS`만 `length`로 보존하고 `SAFETY` 등은 `stop`으로 바꾼다.
**원래 이유와 추가 실패 신호가 모두 사라진 유효한 JSON은 식별할 수 없다.**
따라서 manifest의 `upstream_finish_reason_verified=false`를 유지한다.
집계 성공은 proxy stop + 유효한 연구 응답이며 upstream STOP·물리 성공의 증거가 아니다.
9/25 기록에도 같은 한계가 적용되지만 frozen 파일은 소급 수정하지 않았다.

coordinator는 변경을 검토·커밋하고, 위 회귀와 제한 없는 환경의 제외 검사까지 재실행한다.
그 뒤 `docs/zone_study_pilot.md:117`의 기본 dry-run부터 수행한다. 실호출은 명시적
`--execute --budget-file ... --proxy-pid ...`, 공용 잠금·runtime 검증 후 초기 4회부터다.
upstream 시도/usage를 대조하기 전에는 코호트를 확대하지 않는다.
이미 송신한 기존 budget을 새 파일로 교체하여 차감을 초기화하면 안 된다.
R8 소스로 봉인한 기존 budget은 R9 소스가 달라 거절되므로 송신 이력이 있으면
기존 비용을 보존하는 별도 검토·이관 전까지 중단한다.

작은 로그·파일 hash는 이 디렉터리, test raw와 dry-run 원문은 worktree `.tmp/r9/`에
보존했다. 새 학습/물리/실호출 결과가 없어 TensorBoard snapshot이나 Drive 작업은 하지 않았다.
