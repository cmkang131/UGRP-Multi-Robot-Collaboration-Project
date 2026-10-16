# R27 · 파일럿 기록→승인→명시적 정산의 독립 QA

**좁은 작성 fixture의 독립 재실행과 실제 caller 경계는 PASS다.** 실험·실제 proxy·과금 자료·기존 SQLite를 실행하거나 읽은 검증이 아니며, 새 결함은 발견하지 못했다.

`pilot-admission-repro.py`를 새 임시 디렉터리의 별도 Python subprocess에서 실행했다. exit 0, stderr 없음, 작성자 golden과 전체 JSON bytes가 같았다. 결과 SHA256은 `6190ea5df1365e54334dd79d0a85aac1996eb89d199e0213dc5f6fb824c689ae`, script SHA256은 `1617a4611cbf4f8015855b656cf5f3e6ffdf7dd5636d39e1a9dd9d576780e3fe`다. manifest의 source 11개를 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` Git object와 별도로 byte/hash 대조했다. `pilot-admission-independent-check.json` (Mac 전달본 증거).

## 실행한 경계

| 대조 | 독립 실행 결과와 정확한 범위 |
| --- | --- |
| 4조건 preflight writer | 원래 CLI `main`/`write_new` AST와 실제 budget/reconcile/completion 함수를 실행한다. Adapter 결과가 모두 성공 claim이어도 telemetry가 없으면 `status=recorded`, `reconciliation_complete=false`, exit 2다. `recorded`를 다음 단계 승인이나 물리 성공으로 읽지 않는다. |
| preflight→cohort admission | 작성한 terminal ID telemetry를 붙이면 원래 `require_preflight`가 승인한다. 실제 cohort CLI는 이 admission에 도달한 직후 sentinel로 중단되어 runtime identity 검사·새 run 생성·새 호출을 수행하지 않는다. |
| 7개 승인 음성 대조 | boolean 인정 대신 문자열, source revision 변경, 조건 누락, manifest 편집, 불완전 대조, ledger completion 불일치, trial bytes 변경을 거절한다. 모두 별개의 좁은 변조 대조이며 정상 writer가 이런 값을 냈다는 주장은 아니다. |
| 명시적 정산 dry-run | 실제 `settle_reconciled(..., dry_run=True)`가 DB bytes를 바꾸지 않고 audit 행도 만들지 않는다. CLI의 `--dry-run` 전체 실행을 별도로 한 것은 아니다. |
| 명시적 정산 apply | `reserved_tokens=8000`과 원래 sends/runs JSON은 보존하고 실제 차감 `charged_tokens=140`, `charged_attempts=4`, audit 4행이 된다. SQL 차감 칼럼이 바뀌지 않는다는 의미가 아니다. |
| stale review 재사용 | 같은 정산 review를 다시 적용하면 state 변경 때문에 거절한다. 이 한 대조를 모든 동시 실행·crash·DB 장애에 대한 보장으로 확대하지 않는다. |

원래 source identity/proxy/scenario 함수와 `AdapterTrial`, 제공자 telemetry는 명시적인 authored 협력자다. 실제 provider의 terminal·usage 진실성, network guard 전체, 프로토콜 파싱이나 실제 모델 응답은 이 재현이 증명하지 않는다. 초기 `CONDITIONS`는 원본의 annotated assignment에서 main 조건 이름을 추출하며, 전체 조건 registry를 실행한 것은 아니다. `llm_completion`도 사용한 원래 함수/상수 AST만 실행한다.

## source challenge

`run_zone_study_pilot.main:366–383`은 같은 budget의 snapshot에서 현재 telemetry로 `reconcile`을 계산하고, cohort일 때 `require_preflight`를 통과한 다음 `runtime_identity`로 넘어간다. 따라서 standalone 함수에 임의 `complete=true` report를 직접 주는 우회를 실제 지원 CLI의 결함으로 세지 않았다. fixture의 cohort sentinel 위치도 이 순서와 일치한다.

writer의 `finally:435–456`은 reconciliation과 manifest를 저장하고 그 manifest hash로 `finish_run`을 호출한다. `require_preflight:144–200`은 전체 대조·정확한 boolean 인정·source revision·4조건·원래 manifest hash·저장 trial hash·ledger completion을 다시 연결한다. 과금 대조 완료만으로 응답 성공을 인정하지 않는 계약이다. 여기서 정상 응답은 관측된 proxy stop과 사용한 completion 정책의 범위이며, 실제 upstream STOP나 물리 성공의 인증이 아니다.

`zone_pilot_settlement.settle_reconciled:149–200`는 DB write transaction 안에서 검토 report hash와 현재 state를 대조하고, telemetry 및 request/response 원문을 통해 report를 재계산한다. `_candidate`와 `_successful_exact_call`은 원래 저장된 정상 trial·exact usage·terminal run 연결을 확인한다. 명시적 정산은 send/reconcile/run이 자동으로 하는 환불과 별개다. 원래 reservation JSON과 변경되는 차감 칼럼을 audit chain으로 연결한다는 해석을 source에서 확인했다.

추가로 고정 Git의 `docs/zone_study_pilot.md` 중 예산·명시적 정산·응답 종료·preflight 인정 계약을 읽었다. 문서의 과거 실제 send/정산 수치는 이번 증거로 사용하지 않았다. 해당 문서는 기록된 wrist RGB를 사용하는 물리 미실행 파일럿을 설명하므로, registry의 일반 side-effect 이름이나 `real_adapter` 라벨만 보고 현재 HIGH 물리 실행으로 합치지 않는다.

R12의 `zone_pilot_ledger.proxy_profile/runtime_identity` 검토는 주 LLM proxy identity 경계였으며, 이번 shared pilot budget/preflight/정산 caller 연결과 구분한다. source migration은 fixture 실행 범위 밖이고 두 관련 test 파일은 Git hash만 대조했다. 11개 파일의 hash 일치를 11개 전체 동작의 감사 완료로 세지 않는다. GitHub 현재 상태는 이 QA에서 재조회하지 않았다.

## 최종 원고·coverage 대응 대조

최종 [파일럿 원고](budget.md) SHA256 `69a6d2ee9fe47942df3255a1adf18eb1a131190174defdbef64672630ba58a2f`와 [entrypoint 표](README.md) SHA256 `1ca115516f3160917e5e45e54fa7e8031352fb2d6cc7aa758c5774d70a6b608d`를 대조해 PASS로 판정했다. source identity는 admission 전, runtime identity는 후라는 호출 순서를 반영했고, 실행하지 않은 parser는 모델 응답의 프로토콜 parser로 특정했다. R26 공동 2대 범위도 source triage로 구분했다.

원래 catalog의 base + fragment 병합 규칙을 source로 읽고 Git JSON의 48개 고유 ID를 index와 16개 묶음의 합집합에 별도로 대조했다. 14개 catalog/source manifest hash, 48개 고유 entry/runner 파일의 hash 및 이전 main과의 byte 동일성도 확인했다. 이는 목록·정체성·문서 일관성 QA다. 모든 48개 CLI 실행·모든 dependency·인용한 모든 옛 감사의 재실행으로 확대하지 않는다. 공유 부품만 검토한 teacher/traffic/ACT 등 묶음을 wrapper 전체 완료로 승격하지 않은 표의 한정을 수용한다.
