# 일반 ACT 베이스라인: 실행 감독 해제 처치 사전등록 동결본

Codex, 2026-10-26 22:53:21 KST. **REGISTERED_FROZEN.** v3 동결 후보를 승계해 C-11 실제 서면 확인과 C-06 확정을 반영한 동결본이다. 이 동결은 아래 C-07의 실행 직전 재확인 없이 GPU 실행을 허용하지 않는다.

**동결 완료 근거와 실행 전 조건:**

1. **(a) C-11 본인 서면 확인 1회 수령.** 2026-10-26 21:04 KST `SHAREDMEMORY.md` 절의 실제 승인 문장을 아래 체크리스트와 P-11 대조표에 글자 그대로 인용한다. 역사적으로 **07:18 지시는 서면 확인을 충족하지 않았고**, v3 검토 시점까지 C-11은 미수령이었다. 07:18 이후 별도 승인 사실은 v3 검토 당시 기록에 없었으며 알 수 없었다.
2. **(b) C-06 escalation 1.5배(9,180s) 동결 확정.** v3에 승계된 예산·중단 규칙을 변경하지 않는다.
3. **(c) C-07 실행 직전 디스크·예약 재확인.** 동결 차단 사유가 아니라 기동 전 조건이다. 오프피크 KST 01:30–09:30에 gcp6를 기동한 뒤 all-hosts·디스크·원장·예약 재확인을 기록하기 전에는 GPU 실행을 시작할 수 없다. `SHAREDMEMORY.md` 2026-10-26 21:06 KST 기록상 gcp6는 TERMINATED이며, 비용 규칙상 실행할 때만 기동하고 종료 즉시 정지한다.

## 동결 체크리스트

- [x] **C-11 — 본인 서면 확인 1회 수령 및 P-11 실제 승인 근거 인용.** 2026-10-26 21:04 KST `~/.ductor/SHAREDMEMORY.md`의 실제 승인 문장:

  > "본 arm의 기준선은 재학습·게이트·선택 없이 동결 step-011000을 재사용하고(0-GPU 산출물 해시 검증으로 대체), 실행 감독(G1 close 게이트 + G5~G8 READY/permit 체인 + 공동 완료 AND)을 해제한다 — 이는 03:33 승인 '입력에서 조율 채널만 제거'와 07:18 지시의 '학습 → 게이트 → 선택·동결' 순서 유지를 대체한다"

  역사: MiniMax Q3가 확인한 대로 07:18 지시는 서면 확인을 충족하지 않았고, v3 검토 시점까지 이 확인은 미수령이었다. 당시 07:18 이후의 별도 승인 기록은 알 수 없었다.

- [x] **C-06 — escalation 1.5배(9,180s) 동결 확정.** 기존 제안과 예산·중단 규칙을 그대로 승계한다.
- [ ] **C-07 — 실행 직전 재확인.** 동결 차단이 아닌 기동 전 조건이다. 오프피크 KST 01:30–09:30에 gcp6를 기동한 뒤 `--all-hosts` 실제 대상·연결, gcp6 전체 쓰기 예산·8 GiB 바닥·동시 잔여 쓰기, GPU 원장·크레딧·예산 정지장치와 예약량을 모두 재확인해 기록하기 전에는 GPU 실행을 시작하지 않는다. 기존 측정은 제출 승인이 아니다. `SHAREDMEMORY.md` 2026-10-26 21:06 KST 기록상 gcp6는 TERMINATED이고, 비용 규칙상 실행할 때만 기동하며 종료 즉시 정지한다.

## v3 반영·승계 범위

이번 v3 작업은 **로컬 CPU 문서 편집·텍스트 대조·SHA-256 검사만** 수행했다. **GPU 실행 0회, 에피소드 실행 0회, 모델 forward 0회, 학습·평가·예약 0회**다. 기존 prereg-draft·prereg-v2·검토 문서·처치 코드·패키지·actor·동결 파일·S/T/R/A 소스는 수정하지 않는다.

승계 기준은 [사전등록 개정안 v2](2026-10-26-baseline-prereg-v2.md)와 v3 동결 후보다. 내용 변경은 C-11 실제 서면 확인 인용, C-06 확정, C-07의 동결/기동 시각 구분 및 그 상태·대조표·상호 참조에 한정한다. **C-01~C-05, C-08~C-10, C-12, C-13, E-01~E-07은 v3 내용을 그대로 승계**하며 새 판정·임계·실행 결과를 추가하지 않는다. [조건 반영 보고서](2026-10-26-baseline-conditions-fix-codex.md)의 v3 미결 항목 C-06·C-11은 이 동결로 해소됐고, C-07은 실행 직전 재확인으로 남는다. [v3 반영 보고서](2026-10-26-baseline-v3-codex.md)에 v3의 수정 위치와 승계 검증 범위를 기록한다.

**승계 본문의 시점:** 아래의 “이번 CPU 검증”, “이번에 수정/검사/계산” 및 52/52 PASS·33파일 대조·actor CPU readback·디스크 측정은 **v2 및 선행 구현 당시 기록을 승계한 것**이다. 이번 v3에서 이를 재실행하거나 최신 상태로 확인했다는 뜻이 아니다. v2의 CPU_VALIDATED 표기를 이번 v3의 새 런타임 검증으로 확대하지 않는다.

승계 근거는 [MiniMax 사전등록 검토 정본](2026-10-26-baseline-prereg-review-minimax.md), [원래 초안](2026-10-26-baseline-prereg-draft.md), [구현 보고서](2026-10-26-baseline-impl-codex.md), [MiniMax 최종판 v2](2026-10-26-baseline-treatment-review-minimax.md)의 C1–C8·A1–A12와 [gcp6 실측](2026-10-26-baseline-gcp6-measure-codex.md)이다. 이하 “MiniMax 최종판 v2”·“v2 C1~C8”은 처치 최종판 문서의 버전으로, 이 사전등록의 버전 v3와 구별한다. 기존 P-01–P-27 대조를 승계한다.

## 동결 전 조건 반영 내역 (C-01~C-13)

숫자 사이에 하이픈이 있는 C-01~C-13은 이번 사전등록 검토 조건이고, C1~C8은 앞선 처치 최종판 v2 조건이다. 아래의 v3 상태는 이 동결본에서 C-06·C-11 확정과 C-07 기동 전 조건으로 갱신한다.

| 조건 | 처리 | 반영 위치 | 변경 요지·남은 조건 |
|---|---|---|---|
| C-01 | 반영 | 사전 해석·통계 | (a) release의 grasp/B 혼입·place 해석 금지 반영. (b) [MiniMax Q1 최종 문구](2026-10-26-baseline-c01b-minimax.md)를 분기표 해당 행에 적용. stage 진행 병목 범위의 허용 결론과 stage-head 원인 확정 금지 유지 |
| C-02 | 반영 | 사전 해석·통계: 인과 루프·명시적 한계 | 미측정 카운터팩추얼, Arm S 판정 경로, 개선/악화·조율 필드 해석 한계 4건 |
| C-03 | 반영 | P-19 물리 이동 열·파일럿 ②·audit_cpu.py | `max_xy_excursion_m`와 r2 P100 근거를 특정. 비영 wheel만으로 통과 불가 |
| C-04 | 반영 | 파일럿·future_driver.Guard.finalize | 완료 0~3건도 `pilot-gate.json: pass_gate=false`. runner 예외에도 출력 디렉터리가 있으면 finalize |
| C-05 | 반영 | 파일럿 비용·P-22 | 현재 배치 비용 절약과 분리, 다음 Arm S·C 재시도 예약 취소 게이트로 명시 |
| C-06 | 확정 | GPU 예산과 재시도 | 1.70의 상방 위험·가정부 최악 명시. 9,180s escalation은 동결 확정값 |
| C-07 | 실행 직전 재확인 | 저장·디스크·실행 순서 | 0.5~1 GiB/arm·C→S·재시도 전 무손실 압축 명시. --all-hosts는 접속 실패로 전체 미검증이며, 오프피크 기동 뒤 all-hosts·디스크·원장·예약을 재확인·기록하기 전 GPU 실행 금지 |
| C-08 | 반영 | 처치 패키지 현재 해시 바인딩 | 지정 10파일 SHA와 외부 현재 매니페스트 고정. 기존 metadata는 과거판으로 보존 |
| C-09 | 반영 | 제거·유지 지점 | v2 C6·C7 번호와 G2 계측 유지(P-02 우선) 충돌 해소 근거 |
| C-10 | 반영 | 로더·외부 subclass·permit 삽입 지점 | 로더 바인딩, 호출부의 외부 subclass 대체와 기존 구현의 동치성([MiniMax Q2](2026-10-26-baseline-c01b-minimax.md)), TTL·지연·3-site 현물 확인. 과거 실행 시점 바이트 한계 별도 |
| C-11 | 확정 | 승인 프로토콜 변경 대조·동결 체크리스트·P-11 | [MiniMax Q3](2026-10-26-baseline-c01b-minimax.md): 07:18 지시는 서면 확인을 충족하지 않는다. 2026-10-26 21:04 KST 본인 서면 확인을 실제 승인 문장 그대로 체크리스트와 P-11에 인용; v3 검토 시점까지 미수령이었던 이력은 보존 |
| C-12 | 반영 | 비교 질문·사전 해석·통계 | Supervision 해제 라벨, 결과표 재현 의무, 산출물 고정/선택 재현 구분, 무장벽 재학습은 별도 미래 arm |
| C-13 | 반영(권고) | 동결 전 위험 대응 | 해시 누락 시 동결 보류, permit 3-site, S 최소 지표, READY<20% 및 teacher-forced 설계만 |

F-07·F-08 권고도 P-19·A8·구현 경계·저장 절과 CPU 검증 절에 함께 반영했다. E-01~E-07은 뒤 실행 절에 정본 그대로 편입했다. 이번 개정은 실행이 아니다.

## 비교 질문·승인 프로토콜 변경 (P-01, P-05, P-11)

**동일한 동결 step-011000과 이미 사용한 보류 과제 20개에서 실행 감독을 해제하면 폐루프 행동·stage 정체·성공이 달라지는가?** 주 분석은 Arm C, 기전 진단은 Arm S다. 여기서 “일반 ACT”는 upstream ACT와 구조가 같다는 뜻이 아니다. 기존 categorical wheel head·학습 stage head·done recovery·normalization을 모두 가진 같은 정책을 사용한다.

Arm C 한 문장 정의(C1): **동결 step-011000을 그대로 둔 채 r2 재평가 실행의 wheels=0 보류와 제안 거부를 제거하고, READY/permit의 행동 인과 경로와 공동 완료 전환의 양측 AND를 해제한다. GO/ACK 계산은 진단으로 남기며 매 틱 재추론·grasp 토큰·성공 판정·물리·퍼널 순서·role은 고정한다.**

**승인 프로토콜 변경:** 앞선 입력 마스킹 초안의 “dataset-v4에서 새 20,000-step 학습 → offline gate → 새 checkpoint 선택 → 동결 → 보류 평가”를 이번 확정 처치에는 적용하지 않는다. 전용 조율 입력 필드는 없고, 이번 처치는 평가 실행기의 감독에만 작용한다. 같은 학습을 반복하거나 기존 산출물을 다시 선택하는 것은 처치의 조작이 아니며 선택 자유도와 GPU 비용만 늘린다. 학습·게이트·선택을 생략하고, 기존 선택 step-011000·actor 3파일·inventory·로더 결합 소스·checkpoints·manifest·normalization·sidecar·selection의 해시 대조와 원래 `PairActActor.load(device='cpu')` readback으로 대체한다. 이는 새 정책의 게이트 통과나 물리 성공을 증명하지 않는다. 기존 승인 파일은 그대로 보존한다.

**처치 정의의 별도 변경 대조(C-11 / v2 R-10):** 학습·게이트·선택 생략과 아래의 처치 방식 변경은 별개다.

| 서면 근거 | 원래 범위 | 본 처치와의 관계 |
|---|---|---|
| 2026-10-26 03:33 본인 승인, `~/.ductor/SHAREDMEMORY.md:97`의 “채널만 제거” | 입력에서 상대 관측·통신 메시지·동기화/단계 신호 제거, 동일 학습·게이트·선택 프로토콜 | 전용 조율 입력 필드가 없으므로 실행층 감독 해제로 구체화한 정의와 문자 그대로 같지 않음 |
| 2026-10-26 07:18 본인 지시, `SHAREDMEMORY.md:109-111` | 처치 방식 결정을 MiniMax 검토에 위임하되 학습 → 게이트 → 선택·동결 순서 유지 | **07:18 지시는 서면 확인을 충족하지 않는다**([MiniMax Q3](2026-10-26-baseline-c01b-minimax.md)). 처치 계열 선택의 위임이며 재학습·게이트·선택 생략의 승인이나 “채널만 제거”와의 대조 확인을 대신하지 않음 |
| 본 Arm C 정의 | G1·G4·G5·G6·G7의 행동 경로 + G8의 행동 인과 경로 + `_sequence` 공동 완료 AND 제거. G2 계측·G9 cadence 유지 | 입력 마스킹과 실행층 감독 해제를 동치라고 추정하지 않음. G8은 계산 유지·행동 무효화 |

**C-11 과거 기록(v3 검토 시점):** 바로 다음 문단의 “현재”·“남아 있다”·“미수령”은 v3 검토 당시 상태를 원문 그대로 보존한 것이다. 동결 시점에는 2026-10-26 21:04 KST 확인을 수령했으며, 실제 승인 문장은 동결 체크리스트와 P-11에 인용했다.

**07:18 지시는 서면 확인을 충족하지 않는다(C-11, MiniMax Q3 판정).** 계열 선택의 위임은 학습·게이트·선택 생략을 승인하지 않으며, 03:33의 “채널만 제거”와 실행층 감독 해제의 대조 확인도 남아 있다. 필요한 확인 문장 원문은 문서 첫머리 동결 체크리스트의 첫 항목을 따른다. 본인 서면 확인 1회를 받은 뒤 실제 승인 문장·근거를 P-11 대조표에 인용해야 하며, 현재는 **미수령**이다. 이 문서의 후보 작성은 그 확인을 대신하거나 완료 처리하지 않는다([MiniMax Q3 원문](2026-10-26-baseline-c01b-minimax.md)).

이 arm은 **사전 등록 규칙으로 선택된 산출물을 바이트 고정**해 재사용했다. 이는 선택 절차의 재현이 아니라 산출물의 고정이며, 다른 체크포인트에 대한 비교·재선택은 하지 않는다(C-12(c)).

현재 지시는 이 변경의 **초안 작성·구현·CPU 검증** 범위다. 향후 GPU 실행의 최신 사용량·비용 정지 상태·자원 및 최종 문서 검토는 아직 확인하지 않았다. 재학습·새 데이터 수집·stage-head 변경·영상 마스킹·hybrid arm은 열지 않는다. **무장벽 상태에서 수집한 데이터로 재학습하는 것은 별도의 미래 arm으로 등록한다.** 그 수집·학습·게이트 비용이나 결과를 이번 arm으로 이월하거나 이번 승인 범위로 실행하지 않는다(C-12(d)).

이 비교는 **동일 정책·다른 감독·달라지는 입력 스트림**의 비교다(C4). 발행 명령이 달라져 state[0:224] 이력, 자기 PWM 시계 state[251], 자기 RGB가 달라진다. “동일 입력에 게이트만 달리 적용한 성능 비교”라고 쓰지 않는다. 학습된 조율 능력과 실행 감독의 효과를 이 arm만으로 분리하지 않는다.

## 제거·유지 지점 (P-02–P-07, C1–C7)

**v2 C6:** 두 arm은 다른 질문이므로 합산하지 않는다. v2 C6의 “Arm S = G1/G2만 제거”는 같은 문서 G표·P-02의 “G2 계측 유지”와 충돌한다. 본 개정은 P-02와 기존 확정 처치에 따라 **G2 계측 유지 + bypass 이벤트 분리**를 택한다(C-09).

Arm C의 “조율 해제”는 READY/permit/공동 완료 AND라는 제거 대상에 대한 기계적 서술이며, **해석 라벨은 “Supervision 해제”로 한정하고 “조율 불필요”는 허용 결론이 아니다**(C-12(a)).

| 지점 | Arm C: Supervision 해제, 주 arm | Arm S: Supervision 해제, 진단 arm |
|---|---|---|
| G1 close_before_learned_ready | 제거, approach/alignment/recover의 close 제안 발행 | 동일 제거 |
| G2 거부 계측 | 유지. 실제 proposal_rejected는 0이어야 함. 제거한 close 조건은 별도 bypass 이벤트로 기록 | 유지. G1 bypass와 남아 있는 실행 거부를 구별 |
| G3 issue의 wheels=0 보류 | blocked·무permit·pending에 의한 보류 제거 | G1의 blocked 항만 무효화. 나머지 원래 보류 유지 |
| G4 withdrawal의 행동 경로 | pending·started를 행동에 사용하지 않음 | 원본 withdrawal/rearm 유지 |
| G5 READY 생산 | 행동용 pending/READY 생산 제거 | 원본 READY/pending 유지 |
| G6 execute/complete, carry/place의 GO-ACK 차단 | 제거 | 원본 유지 |
| G7 permit→pending 해제·started 링크 | 제거 | 원본 유지 |
| G8 GO/ACK→permit 생산 | 원래 프로토콜 계산·로그는 유지하되 행동·토큰·chunk·전환에는 영향 없음 | 원본 행동 경로 유지 |
| 공동 done 전환 | 각 로봇 자신의 연속 done 3초로 그 로봇만 release. 이후 자신의 연속 done 1.5초로 독립 완료 | 원래 양측 연속 done AND·3초/1.5초 유지 |
| G9 cadence (C2) | 로봇별 매 propose 틱 `discard_pending()` 정확히 1회, fresh predict 1회, stage 표본 1개 | 동일 |
| G10 skill (C3) | **모든 틱 grasp**, wait 0·raw state[225]=0 | 동일 |
| role·입력 계약·action/done 복호화 | 원본 유지 | 원본 유지 |

G8은 **계산 유지·행동 경로 무효화**다. v2 C1의 “제거”와 달리 GO/ACK/permit 진단 계산은 남기며, 그 값이 행동·토큰·chunk·release 전환을 바꾸지 않는다는 행동상 등가를 CPU permit 대조 검사로 확인했다. 실제 GPU 동작의 등가를 검증했다는 뜻은 아니다(F-08(c)).

공통 G9는 외부 `TickExecutor.step`에서 강제한다. 원본 done recovery가 `done_requested`를 해제한 뒤 추가 discard하는 경로는 같은 리셋과 강제 discard 한 번으로 합친다. issue·segment 전환에서는 중복 discard하지 않으며 다음 step 전에 반드시 폐기한다. 따라서 매 로봇에서 `ticks = discard_calls = inference_calls = issued_ticks = sum(stage_counts)`여야 한다. 원본 r2의 `done_recovery=beamact4_done_recovery_v1`만 지원하고 다른 설정은 거부한다. cadence 없는 새 chunk 재사용 arm은 등록하지 않는다.

**grasp 고정의 정확한 범위:** 이번 사용자 지시를 문자 그대로 적용해 내부 release segment 이후에도 skill은 grasp다. 원래 목적지 전환 `none → B`는 유지한다(C는 로봇별, S는 공동 전환). 따라서 “release 전환”은 내부 작업 상태·목적지 전환이며 정책에 `skill=release`를 보내지 않는다. 실제 열기·내려놓기가 발생하는지는 모른다. r2에서는 release에 도달하지 않아 관측된 grasp 스트림은 같았지만, 가상의 원본 release 경로와는 다른 입력이다. 이를 성공이나 독립 release 동작의 증명으로 해석하지 않는다. `state[225]=0` 검사는 정규화 **전** contract context 기준이다.

C의 각 로봇 전환은 peer done을 읽지 않는다. lane 전체 종료는 “모든 로봇의 독립 완료 기록이 존재”할 때만 알린다. 이 마지막 AND는 시뮬레이션 수명 관리용이며 다른 로봇의 release 전환·행동을 보류하는 장벽이 아니다. 최초 독립 release 시각과 로봇별 release/finish 시각을 모두 남긴다.

READY의 비교 행(C5, P-06)은 양 arm·r2 모두 **같은 틱에 양 로봇의 정책 stage가 ready인 경우**를 사용하고, 접근→정렬의 앞선 누적 통과가 있을 때만 다음 관문을 통과시킨다. 프로토콜의 sticky ready 및 GO/ACK는 별도 진단이다. r2의 72,000개 `issued.stage`가 모두 approach여서 이 정의의 READY는 0으로 재산출 가능하다. C는 G5 READY 이벤트 0을 READY 도달 0으로 오독하지 않는다.

구현은 gcp6의 별도 `/home/ugrp/ugrp-sim/baseline-treatment/`에 둔다(v2 **C7**). 이번에 수정한 기존 런타임 파일은 `audit_cpu.py`·`future_driver.py` 두 개뿐이다. 기존 테스트 파일도 보존하고 `test_conditions_cpu.py`를 새로 추가했다. EVAL의 `python`을 새 실행 파일로 바꾸고, 원래 학생 Python에서 bootstrap이 `harness.pairact_r1_student.PairStudentController` 참조만 외부 subclass로 교체한다. 원래 worker main·serve·actor loader를 사용한다. `UGRP_BASELINE_TREATMENT` 미설정 또는 mode=none이 기본이며 원본 클래스를 그대로 선택한다. `pairact_r1.py`·adapter·freeze·학습 설정은 수정하거나 로더 검사를 무효화하지 않는다.

### 로더·외부 subclass·permit 삽입 지점 (C-10, v2 C7/C8, P-07/P-08)

`PairActActor.load`는 `meta['pairact_source_sha256'] == sha256(__file__)`가 아니면 로드를 거부한다(S/harness/pairact_r1.py:611-617). beamact3·grasp_act_contract의 결합 해시도 검사하므로 원본 파일을 수정하거나 로더 검사를 해제하지 않는다.

[MiniMax Q2](2026-10-26-baseline-c01b-minimax.md)에 따라 MiniMax 최종판 v2 P-07의 “호출부 제어”를 **“원본 파일 무수정을 유지한 채 호출부에서 외부 서브클래스로 대체”**로 명확히 한다. 기존 구현과 동치이며 동결 전에 구현 방식을 바꿀 필요는 없다. **PairActBarrier 무수정, TreatmentBarrier가 `ready`/`propose`/`issue`를 override하며 호출부(`controller.py:104`)에서 주입된다.** 외부 `TreatmentBarrier(pair.PairActBarrier)`의 상속·override와 `TreatmentController.__init__`의 `self.barriers` 인스턴스 선택, bootstrap의 worker controller 참조 선택은 그대로다. 원본 `PairActBarrier` 클래스·파일 자체도 그대로다. **원본 파일 무수정·외부 호출 위치의 객체 선택이라는 기능 요건은 코드 판독, 기본 none의 원본 동치 검사, 33파일 불변 대조로 확인했다.** CPU 확인을 넘어 실제 GPU 궤적의 동치를 주장하지 않는다. 구현 해시는 아래 C-08 현재 해시 표를 승계하며 P-07 대조표에도 실행·설정 9종을 붙인다.

permit 발생·삽입 경로는 `runtime-episode.py:117-119`에 해당하는 T의 `StudentEpisode.tick` → `RearmingSync.tick` → `GraspStartSync.tick` → 내부 `PairCarrySync` READY 유효성·GO 판단 → `GraspStartSync`의 ACK/permit 식 → 학생 `issue(permits)`다. permit 식은 `len(acks)==len(participants) and ready[r] and now>=go_at+delays[r]`다. 내부 **TTL 0.6 s는 PairCarrySync의 READY report 유효시간**이고, 참가자 시작지연은 **0≤delay≤1.5 s**다. 새 상수가 아니라 아래 현물 코드의 기존 값이다.

| permit 3-site 합동 확인 | 고정 현물·확인 내용 |
|---|---|
| 소비자 | S/harness/pairact_r1_student.py `3e12d2f5…`, S/harness/beamact_pair_student.py `9650e085…`: wait/pending·무permit 보류. C에서는 외부 subclass가 이 행동 링크를 무효화 |
| 중계·삽입 | T/harness/pairact_student_eval.py `03f6a231…`: RearmingSync·StudentEpisode의 READY→sync.tick→issue, factory 연결 |
| 생산자·시간창 | T/harness/grasp_act_start_sync.py `6333ab41…`: ACK·지연≤1.5; T/harness/pair_carry_sync.py `93a87245…`: report_ttl_s=0.6·freshness 판정 |

이번에 gcp6에서 위 현물의 코드 줄·전체 파일 SHA를 직접 읽어 [source-mechanisms.json](2026-10-26-baseline-treatment-evidence/conditions-fix-20261026/source-mechanisms.json)에 남겼고, 기존 고정 해시와 일치한다. 다른 `c30ebf68…` 사본과 혼합하지 않는다. **과거 r2 실행 바로 그 시점의 별도 바이트 기록이 없는 부분은 소급 증명하지 않는다.** 현물의 TTL·지연 값과 그 과거 이력의 검증 범위를 구분한다.

EVAL은 원본의 엄격한 6키 스키마를 유지한다. `python`만 바뀌고 `mode,source,model,config,device` 5키는 각각 동일하다. 처치 메타데이터는 `student-eval-arm-{c,s}.treatment.json` sidecar와 `treatment-metadata.json`에 둔다. JSON 안에 일곱 번째 metadata 키를 추가하지 않는다.

## 동결 근거·증거 트리 (P-08–P-10, C8)

약칭은 모두 gcp6 경로다. T의 디렉터리명 `26f84d…`를 HEAD로 해석하지 않는다.

| 약칭 | 절대경로 | 고정 HEAD |
|---|---|---|
| S | /home/ugrp/ugrp-sim/src/pairact-p5/student | 3c9337d5f5c9deefd49139b26ae7117022e3d5cc |
| T | /home/ugrp/ugrp-sim/src/26f84d0f0ada1c33473c83cca2d3415ce51bd247 | 75929e7719ad98a089e3dda5251f4249d8bae511 |
| R | /home/ugrp/ugrp-sim/src/pairact-p5/root | e5620e839907dc69d3b014becae2cbda4bbe27da |
| A | /home/ugrp/ugrp-sim/src/pairact-p5/adapter | afd7a6e17c6501d308b6a1d9015b15f5d5da9ed4 |
| L | /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py | Git 밖, 아래 파일 SHA로 식별 |
| RUN | /home/ugrp/ugrp-sim/runs/pairact-r2-reeval-20261026/r2-student-a1 | 원본 결과 |
| EVAL | /home/ugrp/ugrp-sim/runs/pairact-r2-reeval-20261026/student-eval-r2.json | 원본 6키 설정 |
| P5 | /home/ugrp/ugrp-sim/runs/pairact-p5-eval-20261025 | 원본 cases/refs·교사 |
| ACTOR | /home/ugrp/clockfix-build-20261024/train-r2-20261025/main/step-011000/actor | 선택 step 11000 고정 |

MiniMax §5-e의 증거 트리 6행 대조는 다음과 같다. 과거 사본의 동일성을 추정하지 않고 실제 실행 위치를 사용한다.

| 실행 요소 | 실행 트리/현물 SHA-256 |
|---|---|
| pairact_r1_student.py·worker | S: 3e12d2f5… / 7ac86ded… |
| pairact_student_eval.py | T: 03f6a231… |
| pairact_r1.py | S: 8a986924…; actor 결합과 일치, r2-train-tree 사본에만 의존하지 않음 |
| beamact_pair_student.py | S: 9650e085… |
| grasp_act_start_sync.py | T: 6333ab41…; 다른 c30ebf68… 사본 사용 안 함 |
| pair_carry_sync.py | T: 93a87245… |

실제 설정은 `stage_mode=beamact4_stage_v1`, witness 미사용, `place_sync=off`, `done_recovery=beamact4_done_recovery_v1`, deadband=2다. mode=off를 learned barrier 제거 대용으로 사용하지 않는다. actor adapter의 전체 키는 CPU readback JSON에 보존했고, 직접 로더 결합 소스는 pairact_r1.py·beamact3.py·grasp_act_contract.py의 3개임을 확인했다.

아래 20건은 gcp6 실측 보고서의 현물 표를 동결 근거로 재인용했다. 이번 구현 전후에 이 20건과 actor·출처를 포함한 총 33파일을 다시 해시 대조한다. **L의 과거 실행 당시 바이트 해시는 발견되지 않았으므로, 당시 L 전체 바이트 동일성을 추가로 증명했다는 뜻은 아니다.**

| 실측 파일 | SHA-256 |
|---|---|
| RUN/summary.json | `185b710347c0d025218998f472ac3f4aaa98939213016df7c76fb87d81e24437` |
| RUN/artifact-sha256.json | `9bb2321a52949034c65e7cca638cfc365cc6e0b44a7541e200fcdc7496f0215c` |
| RUN/rejection_table.json | `00b0595c4ee71d76a1519c1b9b7faaa8ea508aeee451549f171af62362960310` |
| EVAL | `dcc9cc826c1e882297f8b2b9ca6d70ed4ccad6f5ac2e6846af7af1d1c91bfc8d` |
| P5/p5-heldout-cases.json | `3e4bf69caa48f4638eb365aec649e8202948de56390dff37cbd540e542e504dc` |
| P5/refs-export/canonical-scene.xml | `e3dea4e3995c14d5375c84a7e8dd0a9654bf2c5eb6beaa1ca8801bd791897c60` |
| P5/refs-export/per-world-references.json | `467ea8bd02f30481cbb5b4533ed8da02a120ad3338b1f625bbc5c5f5e579d117` |
| /home/ugrp/ugrp-sim/run-r2-reeval.sh | `73ed1e590963d4f26bdff1fc7326eed713bd22e07b69f41f3ab8827931469aa7` |
| /home/ugrp/ugrp-sim/runs/pairact-r2-reeval-20261026-driver4.log | `00a6597587dfbd5d928ab77670b1bc83e68b4ee9d9358c1b34cc3ef7dee21bac` |
| L | `4390801e4c2057ddb80cdec08b6fcfcbd80fe4cfbe0bcc717b3118ca8c237d71` |
| R/scripts/run_warp_flow_teacher.py | `e7459aedd9af7674c2c6ebe1b3d793ab52d564e7ad9ebd5588138066e8f1555c` |
| R/scripts/warp_flow_episode.py | `73e283092fdb302b4f8d53ee3e5a9dd29031225607a7b8f427b643d1fefede6f` |
| A/scripts/run_beampair1.py | `b190ca61a670df19d1f297e4f68aabedbaf3f9e1fc679cde17bd30c804edce2a` |
| T/scripts/run_grasp_act_teacher.py | `ac812e25d0d3f43c647ddb6e19ce3bb7ba5d46aa363ec6e192f0e77f8ba4e744` |
| T/harness/pairact_student_eval.py | `03f6a2311c0d4f4a97495fdce5efe7d345a35fa2815c9c5ab3660223818efbec` |
| T/harness/grasp_act_start_sync.py | `6333ab411b433a19f8d2cefa22951d3afd0eec5052c475e6782728ad37e6091c` |
| T/harness/pair_carry_sync.py | `93a87245359a131551c128e4f6bf197dbf4141301c2564d3afaea924e78351e0` |
| S/harness/beamact_pair_student.py | `9650e08573adf61e622a2e832a7ca12f476d4e5988f9bbc299bb125a766ee1c6` |
| S/harness/pairact_r1_student.py | `3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54efdef77e81` |
| S/scripts/pairact_r1_student_worker.py | `7ac86ded4acd1d9055ce6950a69034882bee08906d4e1cd9f47e9839009c8031` |

| 추가 actor·로더·출처 파일 | SHA-256 |
|---|---|
| ACTOR/model.safetensors | `8263ad3f135048fea46d5cb85fee1d70910bdc399babbd1f2f20d92c2fbea271` |
| ACTOR/config.json | `b63bc05fb84e5c0f53329336a7a147f18ca73f297ed25279b42b968e279f571f` |
| ACTOR/adapter.json | `84811d26bb0a8bdcc9431bb3c8d5947c70dc8ccd0ba8cf6471566f15f0f1e018` |
| ACTOR/SHA256.json | `b5c3156fd03477e0663c59d09dfa71db4fe321e4782248cddbb256d2b7169a08` |
| S/harness/pairact_r1.py | `8a9869248740bf5ad2da7194cdd9a582347ac09e88783cd6ea127ef3f208a210` |
| S/harness/beamact3.py | `0bfa3986301e2997d8305106a78101c8ad7a6ed446b633dd1a1ca246b2b8b1d9` |
| S/harness/grasp_act_contract.py | `6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056` |
| dataset manifest | `7e544aff426b9ef10a8195c56831d0171224b1feb8ea5728e94956197d990d20` |
| stage sidecar | `65cbd8fbc919730352bb32594a27a6997fe82e65cd1c6c1e719d78e707ec5787` |
| normalization | `4f465a341fb5436b14f4429372e39da862535a5e8231a5cac0fbe67387305639` |
| train config | `37835e1ff9bd7b9686b4d7258b7597e6cd8e40b84a121c4f4156704c04b49326` |
| checkpoints | `f59aa8bc8ba0ff2aba53918db308b49fd82a4fd365978e7dec94b18592fe06ac` |
| selection | `df36fa86587fd943ac4add245f658bf0454dd99585cd911743fa837563b68208` |

해시 검증은 `verify_baseline.py`로 원본 경로에서 수행한다. 33/33 일치·S/T/R/A HEAD 일치·tracked clean을 요구한다. checkpoint 이름만 같거나 일부 해시가 맞는 것으로 대체하지 않는다. CPU actor readback은 원래 해시 검사·정책 config 비교·strict state_dict load까지 수행하되 모델 forward는 호출하지 않는다. CPU 로드가 불가능하면 사유와 hash-only 범위를 기록하고, 로드 성공으로 표기하지 않는다.

## 처치 패키지 현재 해시 바인딩 (C-08, P-07)

gcp6 `/home/ugrp/ugrp-sim/baseline-treatment/`에서 수정·CPU 검사 후 다시 계산한 지정 10파일이다. Oracle 검토 사본은 [package/](2026-10-26-baseline-treatment-evidence/package/)이며 바이트를 대조했다.

| 패키지 파일 | 현재 SHA-256 |
|---|---|
| eval-python | `19d33c89cbfb865cd67d71f9f1d205d2032579ebd37d35c3d28caf1762c09948` |
| eval-python-arm-c | `82f590f79f0f12c7a5279dbdcdabf0e1bceaa804fc5cd212f18d737222132891` |
| eval-python-arm-s | `a5cbb98d35d4acb160913851558edff27c109db525f7ec04d9c72776676dae1a` |
| bootstrap.py | `875c48da7d8909d1fec0bf54e5b07e12a0d971d780abd25cc2bfddae2fe15a2d` |
| controller.py | `407b385584fb29edfe32a8f5ca674566cfe787659ae2f7b4a5bf9e5b78d61bcf` |
| audit_cpu.py | `c87b5d3b736162ca5bc0cd771b4e72e05f17913b9d2ef9b073984a7a86137a5b` |
| future_driver.py | `91d9704966f96c07241ae0eb6a38febcbc030ca11114ed7e14bfa2ec3b8b9aa0` |
| student-eval-arm-c.json | `6d813017fac778487f5f6d85793135c60531f113bbf5a5c685a8cccd033e06bb` |
| student-eval-arm-s.json | `913660773e392df48471b66cd707a186098b365acef2baf367ea34f0418e28f3` |
| treatment-metadata.json | `f8ab83862165442a9f5080fbf01edc42c3fdd00faf816dc4d945eb3a2b8923f7` |

추가 테스트 `test_conditions_cpu.py` SHA-256은 `54a2ca3828a9926afbef31e45fee5e59a791dfb714cf5d47196e84a6be4766ad`다. 현재 외부 매니페스트 [conditions-package-sha256.json](2026-10-26-baseline-treatment-evidence/package/conditions-package-sha256.json)의 SHA-256은 `bcb147ddda498e274d5d4387cbf36e6ce02209c1e1c97cca597b47b0a50cff73`다.

**기존 `treatment-metadata.json`·`artifact-sha256.json`은 변경 제한에 따라 과거 구현판으로 보존했다.** 그 안의 이전 audit_cpu.py·future_driver.py 해시를 현재값으로 사용하지 않는다. 현재 두 해시는 위 표와 외부 매니페스트의 `current_package_files`가 우선하며, `supersedes`가 이전→현재 해시를 명시한다. 자기 자신을 재귀 해시하지 않고 본 문서가 외부 매니페스트를 바인딩한다. 모듈·설정·기준 파일 해시가 없거나 불일치하면 **동결 보류**다(C-13(a)).

## 공정성·평가·실패 기록 (A1–A12, P-12, P-14–P-19, P-26)

| 조건 | 고정·보고 규칙 |
|---|---|
| A1 seed/refs | 8342000–8342019, index 0–19, 동일 cases·canonical scene·per-world refs |
| A2 시간 상한 | 각 에피소드 180 SIM초(60+120). 60초에 release 강제 전환하지 않음. cap_end도 실패 분모에 포함 |
| A3 산출물 | 동일 step-011000, actor/adapter/normalization/stage head·원래 action/done decoder |
| A4 cadence | G9 HOLD, 매 로봇·틱 1회 fresh predict·discard·stage 표본 |
| A5 skill | 모든 틱 grasp, wait=0. release segment 이후 의미는 위 명시 |
| A6 실행기/기록기 | 원래 R/A/T/S와 기록기 6f31806d3 유지. 외부 처치·관리 콜백 SHA를 추가 기록. 원본 rows/decision 불변 |
| A7 성공 | 원래 평가 전용 접촉·높이·기울기·3초 유지와 carry evaluator 성공의 결합. 모델 done·finished·거부 0을 성공으로 사용하지 않음 |
| A8 퍼널 | approach → alignment → READY → grasp → hold_3s → carry_1m → door → place 순서 유지. **접근·정렬은 평가 전용 GT 기하**, 나머지 원래 기하/물리 조건 유지. READY 관측원은 정책 stage 로그로 통일 |
| A9 입력 감사 | gt_inputs_to_student=teacher_steps=truth_inputs=teacher_actions=0, allowlist 위반 0. 자기 RGB·자기 발행 이력 외 실시간 정답 입력 금지 |
| A10 hybrid | pairact_r1_hybrid_switch_v1 임계값 유지, hybrid arm 미개방 |
| A11 교사 | 기존 P5 19/20 재사용, 새 교사 GPU 0. 장벽 있는 다른 실행기의 결과라는 비대칭을 표시 |
| A12 HOST_ERROR | 아래 최대 1회 재시도·동일 seed·결측 규칙 적용 |

성공은 원래 raw `physical_success`와 그 내부 평가 근거로 집계한다. 파지 안정 유지의 원래 조건(각 접촉 ≥0.5, 최저 높이 ≥0.012 m, tilt ≤10°, 연속 3초)은 변경하지 않는다. done의 0.65 복호화 임계값, 시간 비교 1e-8, 3초/1.5초는 원본 코드 값으로 새로 맞추지 않았다. noslip=0·weld OFF·외관·카메라/FOV·장면·role 및 평가 지도를 유지하고 평가 정보를 제어기로 보내지 않는다.

교사 19/20은 같은 처치 안의 성능 기준이 아니다. 기존 교사 초기 네 퍼널은 미기록이며 0으로 쓰지 않는다. 교사 rows의 hold_3s=20과 엄밀한 원본 유지 19/20의 차이는 [독립 재집계](2026-10-26-round2-reeval-recount-codex.md)에 따른다. treated 교사 재실행은 **이번 계획에서 선택하지 않음**. 향후 선택하려면 Arm S를 폐기하고 별도 GPU 승인 범위로 정한다(P-18).

수정 전 거부 분포는 71,709/72,000 robot-ticks=99.5958%, 전부 close_before_learned_ready다. READY/permit/done은 모두 0, stage는 approach 72,000개였다. 가장 큰 원인을 먼저 제거하는 설계이며 새로운 결과에 맞춰 다른 게이트를 추가로 고치지 않는다.

P-19의 1차 판독치는 arm별 stage 분포, 실제 거부 사유 분포, 소프트웨어 wheels=0 보류 틱 수, 비영 wheel **명령** 틱 수, inference/discard/stage 표본 수, skill/state[225], state[0:224]·[250:252]·자기 RGB 변화 요약이다. 물리 이동과 wheel 명령을 구별한다. READY stage 수·프로토콜 READY 수·GO·ACK·permit은 각각 별도 열이다. 구현 필드명은 `skill_counts`이며, 각 로봇에서 `{'grasp': ticks}`와 raw `state225_nonzero==0`을 확인한다.

### P-19 물리 이동 열과 파일럿 ② (C-03)

원래 초안과 구현 보고서는 “물리 이동과 wheel 명령을 구별”한다고만 썼고 **물리 이동 열 이름은 없었다**. `nonzero_wheel_ticks`는 명령 열이다. 본 개정에서 아래 평가 전용 파생 열을 명시적으로 정의한다.

| 열 이름(로봇별) | 산식·원본 |
|---|---|
| `max_xy_excursion_m` | `max_t ||XY(t)-XY(first)||₂`, raw/eval-only.jsonl[.zst]의 `robots[rid].pose[:2]`. 파일럿의 물리 이동 판독 열 |
| `net_xy_displacement_m` | `||XY(last)-XY(first)||₂`, 출발점으로 돌아온 이동과 구분 |
| `xy_path_m` | 연속 표본의 XY 거리 합. 수치 드리프트 누적과 구분해 보고 |
| `yaw_path_rad` | 연속 yaw 변화의 wrap 후 절댓값 합. 제자리 회전 진단이며 물리 이동 통과 근거로 쓰지 않음 |

파일럿 ②는 기존 **전체 거부 0 + 비영 wheel 명령 존재**에 더해, 첫 4개 완료 월드의 r1/r2 로그가 모두 측정 가능하고 **최소 한 robot-world의 `max_xy_excursion_m > 0.03082987502070276 m`**일 것을 요구한다. 미측정·누락·NaN/Inf·시간 역전·10 Hz 표본 단절·에피소드 시간 범위 미충족은 실패다. 입력은 완료 후 닫힌 평가 로그만 읽어 별도 `physical-motion-world-NNN.json`에 기록한다. 학생 관측·행동·release 전환·성공 통보로 좌표를 보내지 않는다.

상수 근거: gcp6 원본 r2 20월드×2로봇=40궤적을 CPU로 재계산한 `max_xy_excursion_m`의 경험적 P100이다. P50=0.001817702522 m, P95=0.006276116765 m, P100=0.03082987502070276 m(world-002/r2). [motion-reference.json](2026-10-26-baseline-treatment-evidence/conditions-fix-20261026/motion-reference.json), SHA-256 `fc40c2e79df8a173801644ac4de4572980696b55c32535e558c65963b7392515`에 20원본 경로·압축/해제 SHA·계산 명령의 스크립트를 연결했다. 이는 사실상 정지했던 **기존 r2 관측 범위를 넘는 이동**을 요구하는 새 후보의 진단 상수이며 기본 none에서는 작동하지 않는다. 새 처치 결과로 재맞춤하지 않는다. 물리 성공·유용한 주행·목표 접근을 보장하지 않고, 이 거리 이하의 정상 미세 이동도 통과시키지 못할 수 있다. 이상적 제자리 회전(XY 고정)은 yaw·wheel 값에 관계없이 실패한다.

P-20 해석의 분기 입력은 stage 고정/진행과 함께 위 물리 이동 열을 포함한다. 비영 명령이 있으나 XY 이탈이 r2 범위 이하이고 yaw 변화만 크면 “퇴화 운동/이동 미확인”으로 따로 보고하며 stage-head 원인으로 자동 귀속하지 않는다.

| P-14 실패 양상 후보 | arm별 필수 관측 열 | 해석 범위 |
|---|---|---|
| stage 고정 | 로봇별 stage_counts, READY stage/틱 | 정체 관측, 학습 원인 확정 아님 |
| stage 진행·파지 실패 | close 제안·발행 수, 접촉·안정 유지 | 파지/정렬 실패 후보 |
| 비대칭 파지 | 로봇별 접촉·done 연속 구간·파지 시각 | 양측 동시 파지와 구별 |
| 로봇 간 접촉 | 평가 전용 robot_robot_contacts 및 원본 필드/시각 | 실제 기록 없으면 미관측으로 표시 |
| 비대칭 release→drop | 로봇별 done 시작·release_t·robot_finish_t, drop_events | 동시성 변화와 낙하의 시간 순서 기록, 자동 인과 확정 금지 |
| zone 배치 실패 | 원래 carry failure·door/place 퍼널 | 성공 미충족, 임계값 재조정 금지 |
| 제자리 회전·미세 드리프트 | max_xy_excursion_m·net_xy_displacement_m·xy_path_m·yaw_path_rad·비영 wheel 명령 수 | stage 정체와 별도 분기, 이동량·진행 방향·파지 성공을 혼동하지 않음 |

모든 거부·막힘·실패 행에 reason_category, blocked_object, min_gap_m 및 미관측/미측정 범위를 쓴다. 빈 사유는 금지한다. 소프트웨어 거부는 물체를 추측하지 않고 `UNKNOWN:not_observed`, gap은 null·측정 불가 사유를 기록한다. 존재하지 않는 접촉·drop 값을 0으로 채우지 않는다.

HOST_ERROR/ENOSPC/미완료·미회수는 물리 실패와 분리한다. 동일 seed·동일 설정으로 **추가 시도는 최대 1회(각 seed 총 시도 최대 2회, Arm C 재시도 배치도 최대 1회)**다. 오류를 본 뒤 성공한 시도만 고르는 규칙이 아니라 최초 정상 완료 시도를 사용한다. 정상 cap_end·물리 실패를 성공을 얻기 위해 재시도하지 않는다. 재시도하면 Arm S를 시작하지 않는다. 재시도 후에도 미완료이면 planned N=20·N_eff·결측 seed·오류를 함께 보고하며 전체 20 paired 분석이 완결됐다고 쓰지 않는다. 중단된 배치의 lane을 20개 실패로 바꾸지 않는다.

## 종료 집계·cap_end 대조

batch summary는 실패와 `sim_s>=60`을 결합해 cap_end로 셀 수 있지만 raw runner는 학생 180초를 기준으로 쓴다. 60–180초 사이의 learned-finished 실패가 batch cap_end로 잘못 분류될 수 있다. 원본은 고치지 않고 별도 `termination-crosscheck.json`에 다음 값을 모두 둔다.

1. raw status·cap_end·sim_s, batch cap_end, student_eval.finished_t, origin, finished_elapsed_s, physical_success, 원본 경로·SHA.
2. raw cap_end와 `sim_s>=180-1e-8`의 일치 여부. 정상 cap_end는 분모에 포함하며 성공 플래그와 독립적으로 보존한다.
3. **finished_t는 절대 SIM 시각**, sim_s는 경과 시간이다. 새 처치 summary의 `episode_origin_t`(초기 자기 발행 명령의 t)를 빼서 대조한다. 필요 시 원본 첫 student tick 및 batch native_initialization_only_sim_s와도 맞춘다. 예: origin=2.2, finished_t=92.2, sim_s=90 → 조기 learned_finished, cap_end 아님.
4. raw cap_end=false·elapsed<180·정상 finished면 learned_finished_early다. 성공 여부는 별도 평가 결과다. origin 누락·시각 충돌·필드 누락은 UNCLASSIFIED로 남기고 검증 완료로 표시하지 않는다. 원래 raw end_reason의 teacher_terminal 문자열도 그대로 보존한다.

이 대조의 순수 함수와 합성 사례는 `audit_cpu.py`에 구현했다. 새로운 실제 처치 결과는 아직 없으므로 실제 cap_end 수는 모른다.

## 파일럿·계속/중단 (P-13, P-23)

별도 4-case GPU 실행은 만들지 않는다. **한 Arm C 20-world 본 배치의 완료 순서상 첫 4개**를 파일럿으로 정의한다. 같은 control tick에서 여러 lane이 끝나면 원래 loop의 lane 순서를 따른다. 네 번째 완료 기록 직후, 다음 lane 처리/physics step 전에 다음 네 항목을 판정한다. 이 운영 정의는 초안에 공개하며 새 결과를 본 뒤 window를 고르지 않는다.

| 항목 | 계속 조건 | 중단 조건 |
|---|---|---|
| ① close 게이트 | close_before_learned_ready 실제 거부 0 | 1건 이상 |
| ② 처치 발효·평면 이동 | 전체 proposal_rejected 0, 비영 wheel 명령 존재 **AND** 4월드×r1/r2의 물리 로그 유효 **AND** 최소 한 robot-world의 max_xy_excursion_m > 0.03082987502070276 m | 거부·전부 wheel=0·XY 이동 미달·미측정·로그 오류·순수 제자리 회전 |
| ③ stage·HOLD 무결성 | stage 1개/틱, infer=discard=issue=ticks, skill_counts={'grasp':ticks}, raw state[225]=0 | 누락·불일치. **approach 100%만으로는 중단하지 않고 기본 계속** |
| ④ 호스트 | HOST_ERROR 0 | 오류·ENOSPC·정상 완료 자료 부족 |

불일치·필수 메타 누락은 fail-closed다. **Guard.finalize는 Arm C 완료 0~3건 종료에도 `pilot-gate.json`을 `pass_gate=false`, `reason=fewer_than_four_completed_episodes`로 남기고 관리 중단 상태를 반환한다.** 속도 측정이 이미 성공했더라도 같다(C-04). 원본 runner 예외 뒤에도 출력 디렉터리가 있으면 finally에서 finalize한다. 출력 생성 전 실패·파일 기록 불능 등으로 파일이 없으면 **부재 자체가 Arm S·C 재시도 차단 사유**다. driver의 exit 0만으로 통과 처리하지 않는다.

실패 시 남은 계산을 중단하고 원본/미완료 lane/실제 비용을 보존·보고하며 **Arm S·C 재시도의 후속 예약을 취소**한다. 처치 코드를 수정해 몰래 이어 돌리지 않는다. `pilot-gate.json`의 명시적 pass_gate=true와 C 완료/무결성·속도 확인 전에는 Arm S·C 재시도를 시작하지 않는다. 게이트가 실패한 실행의 관리 중단과 실제 호스트 고장은 따로 기록한다.

`future_driver.py`는 L의 **메모리 내 AST 복사본**에 관리 콜백 두 곳(완료·progress)만 넣는다. 파일 바이트·모델·평가식을 바꾸지 않는다. 계획 모드는 AST parse/compile만 하며 L을 import/exec하지 않는다. 이 코드의 실제 GPU 정지·cleanup 동작은 미검증이다. 중단 시 원래 lane close가 남은 raw를 interrupted/HOST_ERROR로 남길 수 있으므로 관리 중단과 실제 호스트 고장을 별도 표시한다.

**파일럿 비용 주의(C-05): 현재 arm의 1.70 GPU-h는 배치 기동 시점에 이미 확정되어 있고, 파일럿 게이트는 다음 지출(Arm C 재시도·Arm S) 실행 여부를 결정하는 게이트다.** 이는 예약 단위 설명이며 실제 wall 상한 보장이 아니다. 20-lane 병렬 배치에서 실패 lane이 모두 180 SIM초에 도달하면 4번째 완료는 배치 끝 무렵이므로 절약 GPU-h≈0이다(배치 구조에서 온 추론, 실제 처치 미실행). “미사용 예산 반환”이 아니라 **후속 예약 취소**로 기록한다. `audit_cpu.py`의 cost_note=`20 concurrent lanes already run; no 0.34 GPU-h stopping-cost guarantee`와 일치한다. v2의 약 0.34 GPU-h 또는 4/20 비례 비용을 근거로 쓰지 않는다. 별도 파일럿 비용 0은 별도 cohort를 추가하지 않는다는 뜻이다.

본 배치 첫 30 SIM초에 원래 first30 기록을 보존하고, lane별 task SIM과 batch wall/N으로 산출한 wall/SIM 중앙값도 별도 기록한다. setup 제외/원래 지표와 분모를 명시한다. >3.5 경고, **>6.0 또는 측정 불가/HOST_ERROR는 SPEED_GATE_FAIL**로 남기고 후속 진행을 중단한다. 이 숫자는 기존 프로젝트/P-23에서 가져오며 새 성능 상수로 맞추지 않는다. gcp6 GPU 재평가 구간에는 별도의 CPU 분석·readback·테스트를 동시에 돌리지 않는다. 관리 콜백의 작은 완료 요약 검사는 이 실행의 일부다.

## GPU 예산과 재시도 (P-22)

이번 소비는 **0 GPU-h**다. 아래는 향후 계획의 승인 상한이며 소요 보장이 아니다. 기존 실측은 20-world 배치 6,023.29397초=1.67314 GPU-h(점유 wall 환산), 계획 단위는 1.70이다. **1.70은 기대값을 세우는 기준값이며 상한이 아니다.** r2는 71,709/72,000 robot-ticks blocked·비영 wheel 60/72,000의 사실상 정지 실행이었다. Arm C에서 실제 이동·접촉·solver 부하가 늘 수 있고 기존 physics=2,079.596초는 전체 wall의 약 34.5%였다. gcp6 실측 §7의 “6,023초를 보장 상한으로 쓰면 안 된다”는 한계를 유지한다(C-06(a)). G9 유지 때문에 chunk 재사용에 의한 가속을 가정하지 않는다. 일부 lane의 조기 종료만으로 배치 GPU 비용을 비례 할인하지 않는다.

| 단계/예약 | 계획 GPU-h | 13.1 기준 누적 예약 |
|---|---:|---:|
| CPU 구현·사전등록·해시·CPU readback | 0 | 13.10 |
| Arm C 20개, 파일럿 내장 | 1.70 | 14.80 |
| Arm S 진단 20개 | 1.70 | 16.50 |
| Arm C 재시도 최대 1회 예약 | 1.70 | 18.20 |
| 집계/회수 예비 | 0.16 | 18.36 |
| 2-arm 전체 승인 상한(반올림) | **5.3** | **18.4 / 20 (per-arm 1.70 유지 가정)** |

위는 자원 예약표다. 실제 분기에서 S와 C 재시도를 모두 집행하지 않는다. **C 재시도를 쓰면 S를 폐기하고 그 몫을 재시도에 이전**한다. 1-arm 경로는 C 1.70 + C 재시도 1.70 + 예비 0.16=3.56, **상한 3.6 GPU-h**다. C 재시도 전에 이미 S를 돌리는 순서는 금지한다. S 자체의 추가 재시도는 이번 초안에서 허용하지 않는다.

별도 treated 교사 실행을 나중에 선택한다면 S를 폐기하고 1-arm 3.6 + 교사 1.7=5.3 범위로 다시 고정한다. 현재는 선택하지 않았다. 새 학습·offline gate 비용은 넣지 않는다.

**상방 초과 escalation 확정(C-06(b)): “Arm C 실측 wall이 1.70 GPU-h(=6,120s)의 1.5배(9,180s)를 넘으면 Arm S·C 재시도 예약을 취소하고 보고.”** 1.5배(9,180s)는 이 동결본의 확정 임계다. 실행 절의 E-04는 이 등록값에 따라 적용한다. 20 GPU-h 접근·다음 단계 상한 초과 전망이면 이 임계보다 먼저 중단·보고한다.

**18.4/20은 per-arm 1.70이 그대로 성립한다는 가정 하의 최악 예약**이지 비용 보장이 아니다. 13.1/20 및 잔량 6.9는 기존 보고의 시점 값으로 **현재 잔액을 재확인한 수치가 아니다**. 그 한계를 밝히고도 계획상의 2-arm 5.3/1-arm 3.6 GPU-h 예약 틀은 유지하되, 이번에 실제 자원 예약·제출은 하지 않았다. 동결 및 E-01 최신 원장 확인 전에는 집행하지 않는다. 실행 전에 최신 GPU 원장·크레딧/정지장치·중복 작업을 확인한다. 누적 20 GPU-h에 접근하거나 다음 단계가 상한을 넘길 전망이면 중단·보고한다. 1.70은 금융적 보장 상한이 아니므로 실제 wall 점유를 원장에 기록하고 5.3/3.6 및 전역 20 상한을 별도로 지킨다. 비용 정지 발동 시 다른 VM으로 우회하지 않는다.

## 사전 해석·통계 (P-20–P-21, P-25)

**C-01(b) 작성자 확인 반영:** [MiniMax Q1](2026-10-26-baseline-c01b-minimax.md)은 해당 허용 결론이 의도된 등록임을 확인했다. 아래 최종 문구를 분기표 해당 행의 관측·허용·결론 불가 세 칸에 그대로 적용하고, “모든 실패 원인이 stage-head로 확정됨” 금지는 유지한다. 허용 결론은 stage 진행의 병목 범위에 한정한다.

> "C 0/20 + 유효 stage 표본 전부 approach → 허용: 감독 해제만으로 stage 정체를 해소하지 못했고, **G1을 포함한 장벽이 stage 진행의 병목이었다는 근거는 없다**(병목 후보는 정책 stage head 쪽) → stage-head 진단이 다음 과제 / 결론 불가: **'모든 실패 원인이 stage-head로 확정됨'**."

**release 토큰 혼입(C-01(a)):** Arm C의 각 로봇 release 구간은 `skill='grasp'`·`destination='B'`다. r2는 release에 도달하지 않았고 P5도 동일 구간의 입력 기준선이 아니므로 이 구간은 r2·P5와 비교 불가다. **place 성공/실패는 감독 해제와 release 구간 토큰 오버라이드를 분리할 수 없다. release/place 동작의 능력·성능·원인에 대한 결론은 이 arm에서 금지한다.** 원래 physical_success 집계는 유지하되 이를 독립 release/place 동작 증명으로 바꾸지 않는다. 아래 3-branch는 이 한계와 물리 이동 분기를 함께 적용한다.

**인과 루프 가설(C-02(d), v2 §4(가)):** 정책 stage head→approach→G1 close→blocked→이전 명령+wheels=0→state[0:224]의 정지 발행 이력·state[251] 자기 PWM 시계·정적 RGB 몽타주→다시 approach. 이 루프는 기존 거부 71,709건·stage 72,000개 전부 approach라는 관측과 코드 경로를 결합한 가설이다. **카운터팩추얼(무장벽 상태의 stage 분포)은 미측정이다. Arm S가 이 가설의 직접 시험이다.**

**명시적 한계(C-02(a)~(c)):**

1. 학생 결과의 **개선/악화 주장·게이트 개선→폐루프 실패 인과·정렬 정체 기전·일반화 주장은 이 arm 범위 밖**이다. 아래 고정 과제의 기술적 성공 관측·등록 통계의 범위를 넘어 원인이나 일반 성능으로 확대하지 않는다.
2. **입력에 조율 필드가 0개라는 사실은 “정책이 조율 못 한다”의 근거가 아니다. 조율은 실행층에 있었다.**
3. 이 arm에서 “정책이 정상 입력에서 못 한다”와 “장벽이 입력을 오염시켰다”는 구분되지 않는다. **위 인과 루프는 Arm S의 stage 분포로 판정한다.** S가 취소·미완료이면 그 가설의 직접 시험도 미완료로 보고한다.

| 관측 | 허용할 결론 | 허용하지 않을 결론 |
|---|---|---|
| C 성공 ≥1/20 | 고정 과제에서 감독 해제와 입력 피드백 변화 아래 성공 사례가 생김. 감독의 원인적 기여 가설과 부합 | 조율 불필요, 일반화, 1건으로 유의한 개선 |
| C 0/20 + stage가 approach 밖으로 진행 | 감독 해제가 정체를 일부 해소해도 이 정책/과제에서는 성공으로 이어지지 않음 | 원래 장벽이 필요했음 |
| C 0/20 + 유효 stage 표본 전부 approach | 감독 해제만으로 stage 정체를 해소하지 못했고, **G1을 포함한 장벽이 stage 진행의 병목이었다는 근거는 없다**(병목 후보는 정책 stage head 쪽) → stage-head 진단이 다음 과제 | **'모든 실패 원인이 stage-head로 확정됨'**. |
| S에서 파지 시도·움직임이 생기나 READY=0, 성공 0 | close freeze는 행동을 가렸고 handshake는 여전히 열리지 않음. stage 병목 가설을 좁힘 | 장벽 제거가 손해였음 |
| S 성공, C 실패 | 남긴 조율과 다른 입력/전환 경로를 후속 진단할 근거 | 조율의 보편적 필요성 증명 |
| C 성공, S 실패 | G1 해제만으로 부족한 이 과제의 추가 실행 경로 효과 후보 | 어떤 개별 G5–G8이 원인인지 식별 |
| C 접촉/낙하·비대칭 release | 평가 전용 원본으로 물리 실패 양상 보고 | 장벽이 옳았다는 증거 |
| close 거부 0 | 처치 무결성 확인 | 파지·운반 성공 |

추가 물리 분기 입력은 `max_xy_excursion_m`·`net_xy_displacement_m`·`xy_path_m`·`yaw_path_rad`다. 제자리 회전/정지 드리프트·의미 있는 XY 이탈·측정 불능을 stage 고정/진행과 따로 표기한다. wheel 명령이나 yaw 증가만으로 “움직임 회복”을 결론 내리지 않는다.

**결과 보고서는 이 절의 허용/불허 결론표를 그대로 재현하고 불허 결론을 명시적으로 기재한다(C-12(b)).** 허용하지 않는 “조율 불필요”를 결과의 결론으로 쓰지 않는다. C-01(b)의 MiniMax Q1을 반영해 최종 동결한 버전의 표를 사용한다.

stage 고정/진행은 조기 종료 시에도 **실제 유효 틱 전체**를 분모로 삼고 반드시 72,000개가 있어야 한다고 가정하지 않는다. primary confirmatory 표는 C 대 r2의 동일 seed paired 성공이다. Arm S와 C↔S의 stage/실패 양상은 기전 진단이며 별도 확증 p-value 주장이나 arm 합산을 하지 않는다.

양측 exact McNemar α=0.05, arm별 성공률의 양측 Clopper–Pearson 95% 구간을 고정한다. baseline 0/20이고 paired 결측이 없을 때 discordance k는 C 성공 수이며 p=min(1,2×2^-k)다. 최소 유의 관측 변화는 **6/20=30 percentage points**(k=5 p=.0625, k=6 p=.03125)로 사전 명시한다. 이는 population 효과의 최소 검출력 보장이 아니다. 성공 1건은 탐색적 가능성 관측이다. CP 원수치: 0/20 [0,16.843347%], 1/20 [0.126509%,24.873276%]; MiniMax의 상향 표시 [0,16.9%]·[0.13%,24.9%]와 함께 정밀값을 보존한다. 2차 지표는 기술통계만 사용한다.

보류 20개는 P5·r2에 이어 세 번째 사용이다. 새 미관측 일반화 자료로 해석하지 않는다. arm 간 평균·합산, 다른 호스트/백엔드·noslip10 결과와 합산을 금지한다. 성공을 본 뒤 설정·게이트·선택을 바꾸거나 새 seed로 불리한 과제를 대체하지 않는다.

## 저장·디스크·재현 (P-16, P-24, P-27)

원본은 gcp6 영속 디스크의 새 run 아래 보존하고, 분석은 같은 VM CPU에서 GPU 실행 종료 후 수행한다. 모델/에이전트 키를 복사하지 않는다. 로컬에는 새 코드·해시·짧은 JSON·보고서만 회수한다. 새 run마다 `RUN_META(class=study, source heads, wrapper SHA, config SHA, batch)`를 확정하고, 현재 queue의 null commit/PR을 실행 전 실제 값으로 채운 새 봉인본을 만든다. 지금 queue는 NOT_SUBMITTED 템플릿이다.

각 arm의 파생 funnel에는 candidate·frame·event의 관문별 순차 누적 통과/거부 수, 사유 분포, 원본 경로/SHA 및 재현 명령을 둔다. GT/정책-stage/protocol의 관측원을 표시한다. 대기열 `rejection_table`에는 현재 존재하는 `/home/ugrp/ugrp-sim/baseline-treatment/prior-funnel.json` 절대경로를 연결했다. 이 파일은 직전 r2의 20→20→20→0 및 71,709 거부 분포를 보존한다. 새 처치 결과의 상세 frame funnel은 GPU 결과가 생긴 뒤 별도 파일로 산출하며 지금 완료됐다고 쓰지 않는다.

### 디스크 예상량·순서·공간 확보 (C-07, P-24)

**20-episode arm 예상 산출량은 약 0.5~1 GiB(기록 기반 추정)**다. round2-status 140행의 약 0.5G, 155행의 재평가 후 여유 11G→10G(97%)가 근거다. **Arm C 실제 바이트는 미측정**이다. 과거 floor.png 기록 실패로 HOST_ERROR 1건이 있었으므로 여유와 쓰기 완결성을 별도로 확인한다(F-08(a)).

이전 측정 9.913 GiB(10,643,202,048 B)에서 C→S→C 재시도를 모두 예약하면 1 GiB/arm 기준 약 6.9 GiB만 남아, **future_driver의 x86 8 GiB 기동 바닥 때문에 이 예약열은 기동 불가**다. S와 C 재시도를 모두 집행하는 순서는 기존 예산 분기에도 금지된다.

**기본 실행 순서: Arm C → (파일럿 게이트 통과 및 C 정상 완료·무결성/속도 확인 시) Arm S.** C에 재시도할 HOST_ERROR가 있으면 S 예약을 취소하고 C 재시도 분기를 검토한다. **C 재시도는 공간 확보 조치로 >64 KiB JSON/JSONL을 zstd 무손실 압축하고, 해제 바이트 SHA 일치·원본/압축 크기·양쪽 SHA·경로를 매니페스트에 기록한 뒤에만 가능하다.** 그 뒤에도 전체 쓰기 예산이 바닥을 만족해야 한다. 압축으로 부족하면 다른 허용 공간 조치를 먼저 별도 기록하며, 압축 절차를 생략한 재시도는 허용하지 않는다. 파일럿 실패·부재를 재시도로 우회하지 않는다.

**study 원본 삭제 금지.** 압축은 내용과 해시를 보존하는 저장 표현 변경이며 연구 원본을 폐기하는 정리가 아니다. 검증된 압축본·매니페스트 없이 원본을 제거하지 않는다. ARM 아카이브는 복사 후 25 GiB 유지·해시 확인을 전제로 하며, dev 정리는 기존 허용 범위에서만 한다. 이번 작업에서는 압축·삭제·이동·자원 예약을 실행하지 않았다.

`scripts/storage_budget.py`가 있어 아래 명령을 실제 CPU 실행했고 JSON에 stdout/stderr/종료코드를 보존했다.

| 이번 검사 | 결과·범위 |
|---|---|
| `python3 -B scripts/storage_budget.py --all-hosts --runs 1 --per-run-mb 1024` | **exit 1 / 전체 미검증**. oracle-x86 SSH exit 255. 이 도구의 기본 호스트는 x86=oracle-x86·arm=oracle·mac=실행 호스트 home이므로 Oracle Ubuntu에서의 결과를 실제 Mac·gcp6 전체 검사로 읽지 않음 |
| `--host x86 --ssh gcp6 --path /home/ugrp/ugrp-sim --runs 1 --per-run-mb 1024` | free 10,642,178,048 B, 1 GiB 예상 쓰기 후 9,568,436,224 B > 8 GiB, **이 가정에서만 PASS** |
| 같은 대상 `--runs 3 --per-run-mb 1024` | free 10,642,173,952 B, 3 GiB 쓰기 후 7,420,948,480 B < 8 GiB, **FAIL** |

근거: [전체 호스트 결과](2026-10-26-baseline-treatment-evidence/conditions-fix-20261026/storage-budget-all-hosts.json), [gcp6 1-arm](2026-10-26-baseline-treatment-evidence/conditions-fix-20261026/storage-budget-gcp6-one-arm.json), [gcp6 3개 예약](2026-10-26-baseline-treatment-evidence/conditions-fix-20261026/storage-budget-gcp6-three-reservations.json). 동시 작업의 남은 쓰기는 미확인이라 위 검사는 제출 승인 근거가 아니다. 실행 직전 --all-hosts의 실제 대상 연결·gcp6 전체 쓰기 예산을 재확인하고 원장/예약량을 포함한다(E-02). 기존 raw·실물 자료·열린 작업 자료를 삭제하지 않고 ENOSPC는 HOST_ERROR로 보존한다.

CPU 재현 명령은 아래 “이번 CPU 검증”과 [구현 보고서](2026-10-26-baseline-impl-codex.md)에 있다. 향후 기동안은 `future_driver.py --arm arm_c --out NEW`의 **기본 계획 모드**로 먼저 생성하며, 이 모드의 GPU 소비는 0이다. `--execute`는 이번에 호출하지 않았고, 이 초안 자체로 실행 승인을 부여하지 않는다. 실제 GPU 파일럿·S arm·성공률·시간·정지 cleanup·최신 GPU 잔액·독립 최종 검토는 미확인이다.

## 동결 전 위험 대응 (C-13, v2 R-05/R-06/R-12/R-13)

| 리스크 | 등록 규칙 |
|---|---|
| R-05 | 실행/actor/모듈/설정 해시가 미확보·누락·불일치이면 **동결 보류**. 현재 33파일 일치를 과거 모든 바이트나 전체 데이터 검증으로 넓히지 않음 |
| R-06 | permit 소비자·중계/삽입·생산자/시간창의 **3-site 합동 증명**을 요구. 위 C-10 표·source-mechanisms.json을 함께 사용. 서로 다른 grasp_start_sync 사본 혼합 금지 |
| R-12 | **Arm S는 선택 사항이며 Arm C 결과 확정 후 최소 지표(stage 분포·파지 시도·READY)로 축소 가능**. 축소는 보고 지표의 범위이며 동일 20case·시간 상한·필수 안전/무결성 감사를 줄이는 허가가 아님. S 전 축소 여부를 기록 |
| R-13 | 기존 r2 결정 트리의 **READY 도달률 <20%이면 stage-head 진단 선행** 임계를 명시. 본 arm은 현재 지시의 CPU 준비 범위만 진행. **teacher-forced READY 확률 추적은 0 GPU-h 설계만 병행**, 실제 forward/추론·새 진단 실행 없음. CPU 무거운 실행은 재평가 구간과 비동시 |

## 이번 CPU 검증·재현 (C-03/C-04, F-07)

gcp6에서 처치 **16/16**, 기존 집계/관리 **9/9**, 새 조건 보강 **19/19**, S 원본 회귀 **8/8**, 합계 **52/52 PASS / FAIL 0 / ERROR 0**. 모델·simulator import 금지와 CUDA 비활성 환경에서 합성 predictor·기존 평가 파일만 사용했고 GPU·에피소드·모델 forward·launcher 실행은 0이다. 전체 저장소 pytest·GPU 물리·cleanup 검증이 아니다.

기존 `test_cpu.py`·`test_audit_cpu.py`·`test_original_cpu.py`는 바이트를 유지했다. 새 `test_conditions_cpu.py`가 기존 9개 집계 테스트의 새 필수 인자인 물리 이동 fixture를 **메모리에서만** 보강해 원래 assertion을 그대로 실행한다. 물리 기록이 없으면 실패해야 한다는 별도 반례도 포함한다. 완료 0/1/2/3건·속도 측정 유무·runner 예외 후 finalize·정상 4번째 완료·제자리 회전·경계값·결측/NaN·plain/zstd 무손실 판독을 확인했다.

| F-07 수치 | 고정 숫자 대신 사용한 계산·검증 |
|---|---|
| Arm S close 로봇-사례 | `len(p.WITHDRAW_STAGES)*len(ROLES)` = 3×2 = 6. 새 검사에서 실제 발행 사례 수를 세어 대조 |
| Arm S 무permit 보류 로봇-사례 | `len(p.POST_GO_STAGES)*len(ROLES)` = 4×2 = 8. 새 검사에서 실제 보류 수를 세어 대조 |
| C READY 진단 | `len(frames)*len(ROLES)` = 3틱×2로봇 = 6 robot-ticks를 새 JSON의 `metrics.c_ready_diagnostic`에 기록. 정책 READY 진단과 행동 pending/started 부재를 함께 확인 |

위 동적 수치와 `skill_counts`는 [conditions-tests-v1.json](2026-10-26-baseline-treatment-evidence/package/conditions-tests-v1.json)에 있다. 기존 과거 검사 JSON의 하드코딩 수치는 덮어쓰지 않고 이 보강 증거를 사용한다.

```bash
ssh gcp6 'cd /home/ugrp/ugrp-sim/baseline-treatment && mkdir conditions-replay-NEW && CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /home/ugrp/e2emin-20261021/venv/bin/python -B test_conditions_cpu.py conditions-replay-NEW'
ssh gcp6 'cd /home/ugrp/ugrp-sim/baseline-treatment && CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /home/ugrp/e2emin-20261021/venv/bin/python -B test_original_cpu.py conditions-replay-NEW/original-tests.json'
ssh gcp6 'CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 python3 -B /home/ugrp/ugrp-sim/baseline-treatment/verify_baseline.py'
```

파일명 NEW는 미사용 경로로 바꾸며 기존 결과를 덮어쓰지 않는다. 위 명령은 CPU 검증용이다. actor CPU readback은 이번에 반복하지 않았다. 이전 readback의 239 state_dict·51,818,398 params·CUDA false·forward 0 범위를 유지하고 학생 성공으로 표현하지 않는다.

## 실행 중 준수 조건 (E-01~E-07, 정본 그대로 편입)

아래는 미래 실행의 운영 조건이며 이번 신규 실행을 뜻하지 않는다. 정본 E-07의 “C-04의 입력 혼입”은 문구를 그대로 보존했다. 본 개정의 입력 혼입 참조는 v2 C4·본 C-02이고, 하이픈 C-04는 파일럿 fail-closed 조건이다.

**E-01 — 원장·비용 재확인(기동 직전).** 13.1/20은 시점 값이다. 기동 직전에 최신 GPU 원장·크레딧·예산 정지장치 상태·VM 임대·동시 작업을 확인하고 **실제 값**을 기록한다. 13.1+계획을 원장 값으로 쓰지 않는다. 비용 정지 발동 시 다른 VM으로 우회하지 않는다(`AGENTS.md`).

**E-02 — 디스크·storage budget(기동 직전).** `storage_budget.py --all-hosts`와 gcp6 여유를 확인하고 8 GiB 바닥 + 동시 작업의 남은 쓰기를 반영한다. ENOSPC는 HOST_ERROR로 보존한다. 기존 원본·study 자료·열린 작업 자료를 삭제하지 않는다.

**E-03 — 파일럿 결정의 기록과 fail-closed 준수.** `pilot-gate.json`이 기록되기 전에는 Arm S·C 재시도를 시작하지 않는다. 게이트 실패 시 관리 중단(administrative stop)과 실제 호스트 고장을 **별도 표기**하고, 남은 lane raw는 interrupted/HOST_ERROR로 보존한다. 처치 코드를 고쳐 몰래 이어 돌리지 않는다. 완료 4건 미만으로 끝난 경우에도 파일럿 통과로 읽히지 않게 한다(C-04).

**E-04 — 실측 wall의 원장 기록과 escalation.** arm별 실측 wall 점유를 원장에 기록하고, C-06의 임계를 넘으면 등록된 escalation 규칙(예약 취소)을 적용한 뒤 보고한다. 1.70은 예산 근거로만 쓰고 실측으로 대체하지 않는다.

**E-05 — 속도 게이트·CPU 경합.** 첫 30 SIM초 median >6.0 또는 측정 불가/HOST_ERROR면 SPEED_GATE_FAIL로 후속 실행을 중단한다. gcp6 GPU 재평가 구간에 CPU 분석·readback·테스트를 동시에 돌리지 않는다(관리 콜백의 작은 완료 요약 검사는 이 실행의 일부로 허용).

**E-06 — 원본 불변·메타 봉인.** 원본 rows/decision은 불변, 파생 집계는 별도 파일, `RUN_META(class=study)`에 실제 null commit/PR·배치·source head를 채운 봉인본을 **기동 전에** 만든다. 원본/분석/디렉터리 격리를 유지하고 전체 파일 해시 목록을 남긴다.

**E-07 — 보고.** 결과 보고는 §"사전 해석·통계"의 허용/불허 표를 그대로 재현하고, C-01의 release 토큰 혼인·C-02의 미등록 한계·C-04의 입력 혼입·C-07에서 미해결로 남은 arm·교사 19/20 비대칭·n=20 통계 한계를 함께 명시한다. 보류 20개가 3회 사용(일반화 금지)임을 밝히고, arm 간 합산·평균·다른 호스트/백엔드/noslip10 결과와의 합산을 하지 않는다. **"조율 불필요" 문구를 쓰지 않는다.**

## 동결 완료·실행 직전 확인

C-11 본인 서면 확인과 C-06 1.5배(9,180s) escalation 확정으로 v3의 동결 차단 사유는 해소했다. **C-07은 동결 차단이 아니라 실행 직전 조건**이다. 오프피크 KST 01:30–09:30에 gcp6를 기동한 뒤 all-hosts 실제 대상·연결, 디스크·전체 쓰기 예산·동시 잔여 쓰기, GPU 원장·크레딧·예산 정지장치 및 예약량을 재확인하고 기록하기 전에는 GPU 실행을 시작할 수 없다. `SHAREDMEMORY.md` 2026-10-26 21:06 KST 기록상 gcp6는 TERMINATED이고 비용 규칙상 실행 때만 기동하며 종료 즉시 정지한다. 실제 GPU/CUDA 경로·첫4 완료 시각·파일럿 중단/cleanup·Arm C/S stage/성공·release/place 물리·실측 wall·산출 바이트는 미측정이다. L 등 과거 실행 시점 별도 해시가 없는 부분과 현물 코드 확인을 구분한다. 최종 교차 검토·실행 소스 Git 보존·기동 전 RUN_META 봉인은 별도 후속 작업이다. 이 문서는 **REGISTERED_FROZEN**이다.

## 사전등록 항목 대조

| ID | 이 개정안의 대응 내용 |
|---|---|
| P-01 | Supervision 해제형 명칭·C1 한 문장 정의·C/S 분리 |
| P-02 | G1–G10·공동 done 제거/유지 표, G2 계측 보존 |
| P-03 | G9 매 틱 discard/infer/stage=1의 구현·집계 규칙 |
| P-04 | grasp 전 틱·wait/state[225]=0, release 이후 범위까지 명시 |
| P-05 | 명령 이력·시계·RGB 입력 분포 혼입 선언 |
| P-06 | 양 로봇 policy stage ready 동시 관측·순차 누적 READY 정의 |
| P-07 | C7 로더 바인딩·기본 none. **원본 파일 무수정을 유지한 채 호출부에서 외부 서브클래스로 대체**([MiniMax Q2](2026-10-26-baseline-c01b-minimax.md)). PairActBarrier 무수정, TreatmentBarrier가 `ready`/`propose`/`issue`를 override하며 호출부(`controller.py:104`)에서 주입된다. **구현 해시(C-08 실행·설정 9종):** `eval-python: 19d33c89cbfb865cd67d71f9f1d205d2032579ebd37d35c3d28caf1762c09948`; `eval-python-arm-c: 82f590f79f0f12c7a5279dbdcdabf0e1bceaa804fc5cd212f18d737222132891`; `eval-python-arm-s: a5cbb98d35d4acb160913851558edff27c109db525f7ec04d9c72776676dae1a`; `bootstrap.py: 875c48da7d8909d1fec0bf54e5b07e12a0d971d780abd25cc2bfddae2fe15a2d`; `controller.py: 407b385584fb29edfe32a8f5ca674566cfe787659ae2f7b4a5bf9e5b78d61bcf`; `audit_cpu.py: c87b5d3b736162ca5bc0cd771b4e72e05f17913b9d2ef9b073984a7a86137a5b`; `future_driver.py: 91d9704966f96c07241ae0eb6a38febcbc030ca11114ed7e14bfa2ec3b8b9aa0`; `student-eval-arm-c.json: 6d813017fac778487f5f6d85793135c60531f113bbf5a5c685a8cccd033e06bb`; `student-eval-arm-s.json: 913660773e392df48471b66cd707a186098b365acef2baf367ea34f0418e28f3`. [C-08 현재 10파일 SHA 표·외부 매니페스트](#처치-패키지-현재-해시-바인딩-c-08-p-07)를 그대로 승계한다(10번째 `treatment-metadata.json`은 과거판 보존용). |
| P-08 | S/T/R/A·증거 트리 6행·실측 파일 20건 해시 표 |
| P-09 | beamact4_stage_v1·witness 미사용·place_sync off |
| P-10 | actor/checkpoints/manifest/normalization/sidecar/selection 해시·CPU readback |
| P-11 | 학습·게이트·선택 생략과 채널 제거→실행층 처치 변경을 분리. **07:18 지시는 서면 확인을 충족하지 않는다**([MiniMax Q3](2026-10-26-baseline-c01b-minimax.md)); v3 검토 시점까지 본인 서면 확인은 미수령이었고 07:18 이후 별도 승인 기록은 알 수 없었다. 2026-10-26 21:04 KST 실제 승인 근거: "본 arm의 기준선은 재학습·게이트·선택 없이 동결 step-011000을 재사용하고(0-GPU 산출물 해시 검증으로 대체), 실행 감독(G1 close 게이트 + G5~G8 READY/permit 체인 + 공동 완료 AND)을 해제한다 — 이는 03:33 승인 '입력에서 조율 채널만 제거'와 07:18 지시의 '학습 → 게이트 → 선택·동결' 순서 유지를 대체한다" (`~/.ductor/SHAREDMEMORY.md`) |
| P-12 | paired 20 seed·동일 refs·180 SIM초·cap_end 분모 유지 |
| P-13 | 동일 배치 첫4 완료, 물리 이동 포함 네 항목, 미완료 fail-closed·후속 예약 취소 |
| P-14 | 실패 양상 귀속 표·접촉/drop/로봇별 done·release 열 |
| P-15 | HOST_ERROR 제외·동일 seed 최대 2시도·C 재시도 배치 1회·결측 공개 |
| P-16 | 원래 기록기·파생 격리·빈 사유 금지·누적 funnel·queue 절대경로 |
| P-17 | 원래 성공 조건·3초 유지·FUNNEL 8항목 순서 |
| P-18 | 교사 P5 19/20 재사용·비대칭·treated 교사 미선택/선택 시 S 폐기 |
| P-19 | stage/거부/보류/inference/입력 분포 및 max_xy_excursion_m 등 4개 물리 열, skill_counts 명명 |
| P-20 | C-01(b) 분기 행에 [MiniMax Q1 최종 문구](2026-10-26-baseline-c01b-minimax.md) 반영·stage-head 원인 확정 금지 유지·release 토큰 혼입·인과 루프·물리 분기·보고 재현 의무 |
| P-21 | paired exact McNemar α=.05·CP 95%·6/20 최소 유의 관측 변화·2차 기술통계 |
| P-22 | 5.3/3.6 GPU-h 상한·단계 예약·재시도 시 S 폐기·전역 20 접근 시 중단 |
| P-23 | 첫30 SIM초 wall/SIM·>6.0 SPEED_GATE_FAIL·CPU 분석 비동시 |
| P-24 | 0.5~1 GiB/arm·C→S·재시도 전 압축·study 보존·전체 검사 접속 실패와 gcp6 실측·ENOSPC 선례 |
| P-25 | 보류 과제 세 번째 사용·일반화 금지·arm/호스트/백엔드 합산 금지 |
| P-26 | hybrid switch 임계 유지·hybrid arm 미개방 |
| P-27 | 새 원본/분석 분리·RUN_META study·경로/SHA/CPU 및 향후 명령안 |
