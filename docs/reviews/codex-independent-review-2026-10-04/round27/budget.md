# 27차 — 등록 파일럿의 preflight → cohort admission → 명시 정산

**판정: 이 범위의 새 확정 결함 0건.** main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 등록 `zone-study-pilot`을 확인했다. 이는 저장된 관측을 이용하는 v63 실어댑터 연결 파일럿이며, 현재 PR #363 HIGH / #371 pair live와 별도다. 실제 모델·프록시·물리·기존 실험 자료를 실행하거나 재평가하지 않았다.

## 선택 이유와 중복 경계

Registry는 이 CLI를 명시적 `--execute`, 기존 공유 예산 파일, 검증된 proxy PID, 대조 완료 preflight를 요구하는 지원 경로로 등록한다. R12가 읽은 `zone_pilot_ledger.proxy_profile/runtime_identity`는 프록시 소스·PID/listener 경계다. 이번에는 그 뒤의 **원래 CLI가 작성한 preflight manifest와 trial → `require_preflight` → 같은 파일의 명시 정산**을 좁혀 확인했다.

R11의 `PairLiveLedger`/`MainStudyBudget`은 #371의 `condition-seed#a1` 전역 키와 별도 usage-recording 계약이다. 이번 `PilotBudget`은 UUID reservation, output 이름의 run ID, 보수적 최대 upstream 예약과 명시 환급 감사를 사용한다. R11의 동일 seed 재사용 제약, cap 원자성, unknown 차감 보존을 새 발견으로 재집계하지 않았고, 실제 예산 파일의 재생성·우회·정산을 제안하지 않는다.

## 실제 source 연결

- [CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_zone_study_pilot.py#L367-L406)는 source identity와 snapshot을 대조한 뒤 cohort에서 `require_preflight`를 호출한다. 이후 runtime identity, 새 run, adapter를 연결한다.
- [원래 writer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_zone_study_pilot.py#L410-L455)는 조건별 trial hash·completion과 최종 manifest hash를 저장하고, `finish_run`에 최종 hash를 기록한다.
- [cohort admission](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_pilot_reconcile.py#L144-L200)은 billing reconciliation, source/revision, limitation 인정의 정확한 boolean, 네 조건의 단일 정상 호출, budget에 봉인된 manifest, 원본 trial hash와 ledger completion을 다시 확인한다.
- [명시 정산](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_pilot_settlement.py#L149-L200)은 reviewed report/state를 write transaction 안에서 확인하고 telemetry와 원문을 다시 대조한다. 원래 reservation JSON은 보존하고 SQL 차감과 append-only 감사 행을 함께 기록한다.

## authored fixture와 확인 결과

`pilot-admission-repro.py`는 고정 source의 **원래 `main`·`write_new` AST**, 원래 budget/reconcile/settlement 함수와 completion predicate를 실행한다. `AdapterTrial`의 결과, source/proxy/runtime identity, 시나리오, terminal provider telemetry만 저작한 작은 대역이다. 입력과 SQLite는 새 임시 디렉터리에 만들며 네트워크 연결은 실패하도록 막는다. 모델 응답의 프로토콜 parser, 실제 모델 입력 구성, 전송, provider telemetry 수집, PID 검증을 시험한 것은 아니다.

| 경계 | 관측 결과 | 해석 범위 |
|---|---|---|
| 네 조건의 synthetic 정상 completion을 원래 CLI writer에 전달, telemetry 없음 | `status=recorded`, accepted 4, reconciliation 미완료, CLI exit 2 | 기록 완료와 과금 대조 완료를 구분함. 실제 네 조건 실험 완료가 아님 |
| 동일 저작 요청·응답에 terminal telemetry 작성 후 원래 reconcile/admission 호출 | 대조 완료, admitted true | fixture의 hash/identity 연결이 수락됨. 실제 provider 사용량의 정확성 검증이 아님 |
| 실제 cohort CLI 분기 | 원래 `require_preflight` 통과 직후 sentinel로 중단 | runtime identity·새 cohort run 생성·모델 이전에 멈춤. cohort 실행 검증이 아님 |
| 인정값 문자열, source revision 변경, 조건 누락, 봉인 manifest 편집 | 4개 모두 거절 | 정확한 인정값·조건·source·manifest binding 확인 |
| billing 미완료, ledger completion 불일치, trial bytes 변경 | 3개 모두 거절 | 요약 성공 수만으로 admission하지 않음 |
| 명시 정산 dry-run | DB bytes 불변, 감사 행 없음 | 원래 dry-run의 read-only 결과 확인 |
| 동일 synthetic 자료의 명시 적용 | 원래 sends/runs JSON 유지, reserved 8,000 유지, charged 140, attempts 4, 감사 4행 | 저작한 4 × total_tokens 35에 대한 회계 동작. 실제 과금·상한 측정이 아님 |
| 이전 state hash로 정산 재시도 | 거절 | 이 stale review를 이용한 중복 차감 반환 방지 |

이 확인은 일반 cap stress test, 여러 프로세스 경쟁, 모든 crash/power-loss, source migration, interrupted run 복구를 추가 인증하지 않는다. `tests/test_zone_pilot_settlement.py`의 dry-run·중복·해시 변경 검사와 `test_zone_pilot_source_migration.py`의 이관 검사를 읽었지만 전체 pytest를 재실행하지 않았다. 기존 충분한 cap 검사를 반복하는 대신 위 실제 writer/consumer 연결만 실행했다.

## 재현과 제한

```sh
python pilot-admission-repro.py
```

스크립트 옆에 `pilot-source/`와 `pilot-source-manifest.json`이 필요하며 Pillow가 필요하다. Pillow의 이미지 decoder는 이 fixture에서 실행하지 않는다. 11개 source 파일의 SHA-256을 시작 시 검사한다. source/data 분리용 AST 축약 모듈은 원래 completion 함수와 조건 선언만 사용하며 원래 함수 몸체를 변경하지 않았다.

첫 작성 시 fixture loader가 `CONDITIONS`를 일반 대입 AST라고 가정해 `StopIteration`으로 중단했다. 원본의 annotated assignment에 맞춰 loader를 수정한 뒤 exit 0으로 완료했다. 이 fixture 작성 오류를 저장소 결함으로 세지 않았다.

결과는 `pilot-admission-result.json` (Mac 전달본 증거), source hash는 `pilot-source-manifest.json` (Mac 전달본 증거)에 있다. 실제 raw/outcome/heldout·가중치를 의도적으로 열거나 분석하지 않았으며, 구현 변경·원격 쓰기·실제 예산 변경은 없다. 독립 QA의 판정은 별도 기록을 따른다.
