# Baseline 실행 재개 — MiniMax 코드 보충 서면 확인

DeepSeek 문서 PASS 이후의 코드 보충이 추론 길이 제한으로 본문 없이 끝나, 사용자 지정 대체 절차로 MiniMax-M3에 읽기 전용 검토를 요청했습니다. 아래는 반환 본문 무수정 이관입니다. GPU/원격 검증을 대신하지 않습니다.

## 0. 검토 방식

Read 전용으로 지정 4개 파일(동결 문서 + future_driver.py + audit_cpu.py + verify_baseline.py)과 지정된 DeepSeek 교차검토 1개만 직접 읽었습니다. 수정·실행·테스트·위임 없음, 원격/GPU 미접근, **SHA-256 재계산 없음**(해시 주장은 상속이지 독립 재계산이 아닙니다). DeepSeek 판정은 **문서만** 검토했고 코드를 못 읽었으므로, 아래는 MiniMax가 그 보충을 대신한 **코드 수준 서면 확인**입니다.

---

## 1) 서면 최종판정: **CONDITIONAL_PASS — 차단결함 0**

- **코드·설계 판정 자체는 PASS**입니다. 3개 코드 파일과 동결 문서 사이에 차단성 불일치를 찾지 못했습니다.
- CONDITIONAL인 이유는 **설계 결함이 아니라 전부 외부·실행 전 선행조건**입니다: C-07 재확인, 원격 33/33 + S/T/R/A HEAD + tracked clean, RUN_META 실제값 봉인, 실행 소스 Git 보존. 동결 문서 스스로 이를 "동결 차단이 아니라 실행 직전 조건"으로 규정합니다(frozen:20, 449).
- **이 조건들이 완료·기록되기 전까지 GPU 실행은 금지**합니다. VM 확보(L4)·서울/Tokyo 인프라 준비는 프로토콜 변경이 아니며, 동일 snapshot/code/model g2-standard-8/L4 복원은 인프라 복원이고 ABORTED 종결·10분 간격 재시도 규칙을 따릅니다.

## 2) 차단결함 수/이유: **0건**

근거: (a) 계획 모드가 GPU 소비 0이고 L을 import/exec하지 않음(future_driver.py:149-151, 131의 `execute=False`·`budget_authorized_by_this_plan=False`), (b) 훅 카운트 불일치 시 즉시 예외로 fail-loud(future_driver.py:50-51), (c) 게이트·속도·최종 판정이 모두 거절 기본값(fail-closed)(future_driver.py:84-96, 102-118), (d) 동결 문서의 C-07은 명시적 실행 직전 조건.

| 확인 항목 | 결과 | 근거(파일:줄) |
|---|---|---|
| first4 completed ArmC 콜백 | 일치 | future_driver.py:69-81 (`len==4`에서 pilot_gate, 4번째 motion까지 먼저 적재) |
| 다음 physics 전 pilot 검사 | 코드상 일치 (L 스코프는 미검증) | future_driver.py:30-32(완료 직후), 45-46(progress write 직후) 주입, 80-81 stop→`return` |
| <4 finalize failclosed | 일치 | future_driver.py:102-112(`pass_gate=false`, `reason=fewer_than_four_completed_episodes`), 115-118(SPEED_GATE_FAIL), 171-179(exit 3) |
| pilot 파일 부재 → S/재시도 금지 | 문서 규정 존재, **코드 강제 아님(절차 의존)** | frozen:302, 304, 437(E-03) |
| 평가전용 XY 임계 0.03082987502070276 m | 일치(엄격 초과) | audit_cpu.py:19, 148, 186-187 / frozen:260 |
| infer=discard=issue=ticks / skill=grasp / state225=0 | 일치(+ 로봇 2개 부재도 실패) | audit_cpu.py:158-169 |
| 30 SIM median>6 failclosed | 일치(측정 불가·빈 clocks도 실패) | future_driver.py:84-96, 115-118 |
| 33파일+HEAD+tracked clean | 코드 일치, **33 카운트 단언 없음** | verify_baseline.py:20-29, 33-39 / future_driver.py:154-156 |
| 20 GPU-h / 신규 5.3 / C wall>9,180s → 후속 취소 | 문서 일치, 코드 강제 아님 | frozen:314-331, 439(E-04) |
| C→게이트 명시 PASS→S | 문서 일치(순서 C→S) | frozen:304, 382 |
| C 재시도 시 S 폐기 + 압축검증 선행 | 문서 일치 | frozen:325, 382 |

## 3) 실행 전 미검증 범위 (**설계 결함 아님** — 단, 완료 전 실행 금지)

원격/런타임 미검증을 새 결함으로 세지 않되, 다음은 **아직 확인되지 않았습니다**.
- **원격 재검증**: 33/33 SHA, S/T/R/A HEAD 일치, tracked clean(verify_baseline.py:33-39은 원격 gcp6 경로를 가정), L4·VM 확보 후 실측 8 GiB 바닥·동시 잔여 쓰기·GPU 원장/크레딧/budget-stop, RUN_META(class=study) 실제 commit/PR/batch/source head 봉인, 실행 소스 Git 보존, 소스 Git 보존.
- **C-07**: `--all-hosts` 실제 대상·접속(과거 oracle-x86 SSH exit 255로 전체 미검증), gcp6 전체 쓰기 예산·동시 작업 여유.
- **L 런타임 스코프**: 계획 모드는 AST parse/compile까지만(future_driver.py:148)이라, 주입된 `report`/`a`/`i` 이름이 실제 스코프에 resolve되는지, `return`이 **단일 lane이 아닌 배치 전체**를 중단하는지는 L 원본 바이트 확인 없이 판정 불가. 실패 시에는 NameError/FileNotFoundError로 중단되고 finalize가 fail-closed를 남기므로 오염은 없지만 GPU 시간 손실입니다.
- **참조 파일**: `baseline-reference.json`의 실제 행 수(=33 여부), `launch-template.json`의 argv·cwd는 제 지정 읽기 범위 밖이라 독립 확인하지 못했습니다.
- **에피소드 실물**: `eval-only.jsonl[.zst]` 구조·`zstd` 바이너리 존재·`episode_origin_t` 정합은 실측 미확인(부재 시 UNMEASURED→게이트 실패, fail-closed).
- **L4/VM**: 서울 a/b는 용량 부족, 서울SSD520/TokyoSSD260 할당량 승인·snapshot READY·b/Tokyo a 디스크 복원 후 다음 TokyoVM 19:16 UTC. 동일 snapshot/code/model g2-standard-8/L4 복원은 **인프라 변경이며 프로토콜 변경이 아님**, ABORTED 종결 금지·10분 간격 다른 존재 시도. VM 간 부분 결과 합산 금지.

## 4) 비차단 리스크 3개

1. **파일럿 게이트의 늦은 검출(비용 회수 불가)** — 20-lane 병렬에서 4번째 완료가 배치 끝 무렵이면 절약 GPU-h≈0입니다(frozen:308, 294). fail-closed는 정확성을 지키지만 예산 회수를 얻지 못합니다.
2. **1.70 GPU-h 과소추정 + 9,180s escalation의 성격** — r2는 사실상 정지 실행(비영 wheel 60/72,000, physics는 wall의 ~34.5%)이므로 Arm C wall이 1.70을 넘을 수 있고, 9,180s 규칙은 **배치를 멈추지 않고 후속 예약만 취소**합니다(frozen:314, 329). 누적 20 GPU-h 상한은 별도 관리 대상입니다.
3. **계획 모드 검출 한계 + 재실행 메타 충돌** — AST compile은 L 런타임 이름/스코프 오류를 잡지 못합니다(future_driver.py:148-151). 또한 `save_new`가 `'x'` 단독 생성(future_driver.py:56-59)이라 동일 `--out` 재사용 시 FileExistsError로 중단되고, `speed_checked`가 저장보다 먼저 설정되어(future_driver.py:84-91) 저장 실패 시 1차30 감사 파일이 갱신되지 않은 채 남을 수 있습니다(115-118). 참고: CPU 전용 판정은 `CUDA_VISIBLE_DEVICES=''`만 거부(future_driver.py:162-163)하여 **미설정 환경은 걸리지 않습니다**.
