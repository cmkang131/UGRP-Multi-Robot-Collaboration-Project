# 결과 보고 자동화: `scripts/report_tables.py`

실행 결과 원장(ledger)과 summary를 읽어 Markdown 표와 그림을 만듭니다. 10/24 이후 Claude 없이 DeepSeek이 실행 직후 같은 형식으로 보고할 수 있게 하려는 도구입니다.
물리를 돌리거나 run root에 쓰지 않습니다. 파일을 읽기만 합니다.

## 공통 규칙
| 항목 | 동작 |
|---|---|
| 입력 해시 | 읽은 모든 파일의 sha256을 `report.md` "입력" 절과 `report.json.inputs_sha256`에 남깁니다 |
| 사전 등록 SHA 대조 | 원장 header(또는 report.json)에 적힌 `prereg_sha256`이 `--prereg` 파일의 sha256과 다르면 *거부*(exit 2, `REFUSED: …`). `--expect-prereg-sha`로 커밋된 값을 고정하면 그것과도 대조합니다 |
| 사전 등록 상태 | `status`가 `FROZEN`/`REGISTERED`가 아니면 거부합니다. `--allow-draft`를 주면 표는 만들지만 맨 위에 "초안 기준, 판정 아님"을 붙이고 판정(승자 등)은 쓰지 않습니다. Markdown 사전 등록은 첫 `상태: **X**`(또는 `status: X`) 값을 읽습니다(`PREREG_L1LITE.md`, E2E `PREREG_DRAFT.md`) |
| 분모 | 사전 등록 N을 고정합니다. 실패·HOST_ERROR·미실행은 분모에서 빠지지 않고, 미실행은 따로 적고 판정을 보류합니다(L1-lite는 PREREG §7대로 미실행도 실패) |
| HOST_ERROR | tournament(단독 A·공동 P1)와 E2E는 *재실행하지 않고* 실패로 셉니다(각 사전 등록 `host_error`). P5만 사전 등록 `exclusions.host_error`대로 같은 seed 1회 재실행을 허용합니다 |
| 비율 표기 | `n/N (p%, CI lo–hi%)`. CI는 Wilson 95% |
| 합산 금지 | 트랙·레벨·표기(A/B/C)·smoke·DEV seed를 섞지 않습니다 |
| 출력 | `--out` 디렉터리에 `report.md`, `report.json`, `fig-*.png`. matplotlib가 없으면 그림만 건너뛰고 표는 만듭니다 |

종료 코드: 0 성공, 2 거부(이유는 stderr).

## 트랙별 사용법

### (a) 단독 ACT release tournament A
```
python scripts/act18_tournament_ledger.py --prereg experiments/2026-10-17-act18/CARRY_TOURNAMENT_A_PREREG.json \
  --run-root <run_root> --out <run_root>-report/tournament-ledger.jsonl          # dsh/act18-carry-cand-1
python scripts/report_tables.py tournament \
  --prereg experiments/2026-10-17-act18/CARRY_TOURNAMENT_A_PREREG.json \
  --ledger <run_root>-report/tournament-ledger.jsonl --out <run_root>-report/report
```
원장 기록기 `scripts/act18_tournament_ledger.py`(브랜치 `dsh/act18-carry-cand-1`)는 C2c 배치(`<arm>-<ho4|train4>-rep<k>/R8-<diag|train>/group-NNN/{plans.json,evaluation/}`)의 run root를 읽어 world-run마다 한 줄씩 씁니다.
```
{"type":"header","prereg_sha256":"<sha256>","schema":"ugrp.act18.tournament_ledger.v1",...}
{"type":"world_run","arm":"A-c1","rep":1,"cohort":"HO4","seed":88668,"status":"complete",
 "release_success":true,"physical_success":true,"drop_detected":false,
 "G":true,"early_open_grasp":false,"open_issued":true,"release_done":true,"cap_end":false}
```
- `release_success`·`physical_success`·`drop_detected`·`cap_end`는 `summary.json` `student_scores`(`harness/grasp_act_rollout.SoloScore.record`) 값입니다. `G`는 `scripts/act18_c2c_analyze.py` 정의(grasp done 시각까지 3초 안정 들기 완료)입니다. `early_open_grasp`는 grasp skill에서 닫힘 명령(pwm1 < 1900) 뒤 다시 pwm1 ≥ 1900을 낸 경우, `open_issued`는 release skill에서 pwm1 ≥ 1900을 낸 경우, `release_done`은 release done 발행입니다(`actor-actions.jsonl`).
- 주 지표: `status=="complete"` 그리고 release·physical 성공. 분모 24(8 seed × 3).
- 판정: 기준 대비 +3/24 이상, G가 −2/24보다 나쁘면 탈락, 동률은 조기 open 0 → 낙하 수. 규칙으로 못 가르면 "동률".
- HOST_ERROR: summary가 없거나 HOST_ERROR이거나 student_scores가 plans를 다 덮지 않는 group은 그 group의 모든 seed를 HOST_ERROR로 씁니다. 재실행하지 않고 분모에 남겨 실패로 셉니다(사전 등록 `host_error`). 시작하지 않은 run 디렉터리는 행이 없고 판정 보류입니다.
- 확인 run(미사용 seed 4 × 2)은 seed 목록이 미정이라 지원하지 않습니다 [확인 필요: 사전 등록 confirmation.seeds].

### (a') 공동 운반 P1 teacher 관문 tournament / confirmation
```
bash experiments/2026-10-21-pairact-p1/run_p1.sh run      # verdict 뒤 p1_ledger.py가 OUT_ROOT/p1-ledger.jsonl을 씀 (dsh/pairact-p0-diag)
python scripts/report_tables.py pairact-p1 --prereg experiments/2026-10-21-pairact-p1/PAIRACT_P1_PREREG.json \
  --ledger <OUT_ROOT>/p1-ledger.jsonl --out <OUT_ROOT>-report
```
- 행 모양은 (a)와 같고(`world_run`), arm × case index 40행입니다. `status`는 `complete`·`HOST_ERROR`·`not_executed`(world 15, N_eff 안의 실패)·`excluded`(규칙 A, N_eff 밖)입니다.
- 채택 = 통과 ≥ ceil(0.95 × N_eff). n/40과 n/N_eff를 함께 씁니다. 승자는 채택 기준을 넘은 후보 중 최대, 동률은 world 27 통과 → c3 → c1 → c2b 순입니다. confirmation은 D5대로 winner ≥ 필요 수 그리고 같은 world에서 r13 이상일 때만 채택합니다.
- HOST_ERROR는 재실행하지 않습니다. `run_p1.sh`는 이미 시작한 arm 디렉터리가 있으면 그 arm을 다시 돌리지 않습니다(사전 등록 `host_error`).
- 원장 header의 `excluded_worlds`가 사전 등록과 다르거나, 같은 arm·world 행이 둘이면 거부합니다.

### (b1) 공동 운반 교사 시연 수집 (표기 A, pilot, validation)
```
python scripts/run_pairact_collect.py report --prereg P --run-root R      # 기존 도구, R/report.json 갱신
python scripts/report_tables.py pairact-collect --prereg P --report R/report.json --out R/report-md
```
- 입력은 `harness/pairact_collect.report()` 출력(`ugrp.pairact_r1.collect_report.v2`)이며, `dsh/pairact-carry-r1-v2`에서 확인했습니다. 그 안의 `prereg_sha256`을 대조합니다.
- training 모드: A 전체·primary·extension 행(S/N, A/N, 환경 실패는 N 밖), validation(분모 20), 학습 결정(`TRAIN*`/`NO_TRAIN*`)과 라벨, 구간 B0–B5 표, 구간별 막대 그림을 만듭니다. measurement 모드는 pilot 수율 표만 만듭니다.
- 200은 채택 목표이고 분모가 아니라는 문구를 표에 붙입니다.

### (b2) 공동 운반 P5 평가 (표기 C: 학생 n/20 대 teacher n/20, 단계 퍼널)
```
python scripts/pairact_p5_rows.py --prereg <PAIRACT_R1_EVAL_PREREG.json> --cases <p5-heldout-cases.json> \
  --student <RUN>/p5-student --teacher <RUN>/p5-teacher [--static-check <rule-A json>] \
  [--student-rerun <dir>] [--teacher-rerun <dir>] --out <RUN>-report/p5-rows.jsonl        # dsh/pairact-p2-carrypath-r-c2
python scripts/report_tables.py pairact-eval \
  --prereg <PAIRACT_R1_EVAL_PREREG.json> --rows <RUN>-report/p5-rows.jsonl --out <RUN>-report/report
```
행 기록기 `scripts/pairact_p5_rows.py`는 root 쪽 별도 파일이며 runner·경로 계획 파일을 바꾸지 않습니다. -c3 스택(`dsh/pairact-p2-carrypath-r-c3`)에는 같은 파일을 cherry-pick해 씁니다.
```
{"type":"header","prereg_sha256":"…","excluded_seeds":[8342019],"static_check_sha256":"…","schema":"ugrp.pairact.p5_rows.v1",...}
{"type":"episode","arm":"student","seed":8342000,"attempt":1,"status":"complete","success":false,
 "funnel":{"approach":true,"alignment":true,"READY":false,"grasp":false,"hold_3s":false,
           "carry_1m":false,"door":false,"place":false},
 "termination":"carry_total_timeout","student_gt_corrections":0,"teacher_commands_issued_to_student":0}
```
- `success` = `worlds[].success`(3초 유지) ∧ `carry_success`(GT `pair_carry_eval`), 두 arm 같은 식입니다.
- 학생 퍼널은 `summary.json` `student_funnel.reached`입니다. teacher runner는 approach·alignment·READY·grasp를 기록하지 않아 `null`이고, 표에는 "미기록"으로 나옵니다(0이 아님). hold_3s·carry_1m·door·place는 관문·`carry_eval`에서 옵니다.
- `student_gt_corrections`(raw `student_eval.gt_inputs_to_student`)나 `teacher_commands_issued_to_student`(`teacher_steps`)가 `null`이면 확인 불가로 보고 성공으로 세지 않습니다.
- 분모 N_eff = 20 − 규칙 A 정적 제외(header). 제외가 있으면 `static_check_sha256`이 반드시 있어야 하고, 제외 seed에 episode 행이 있으면 거부합니다.
- HOST_ERROR는 같은 seed로 한 번만 다시 돌립니다(`attempt: 2`, 기록기는 1차 HOST_ERROR seed만 받음). 두 번째도 HOST_ERROR면 실패로 세고 따로 적습니다.
- 출력: 성공 n/N_eff, 퍼널 표, 종료 사유, seed별 첫 실패 단계, 퍼널 막대(두 arm, Wilson CI).

### (c) L1-lite (조건별 n/6)
```
python scripts/analyze_l1lite.py <root>/ledger.json --prereg experiments/2026-10-20-l1lite-alloc/PREREG_L1LITE.md \
  --out-json <report>/analysis.json --out-md <report>/analysis.md                         # dsh/l1lite-alloc
python scripts/report_tables.py l1lite --prereg experiments/2026-10-20-l1lite-alloc/PREREG_L1LITE.md \
  --analysis <report>/analysis.json --ledger <root>/ledger.json --out <report>/tables
```
- 입력은 별도 행 형식이 아니라 `scripts/analyze_l1lite.py`의 analysis(`ugrp.e2ewarp.l1lite_analysis.v1`)입니다. PREREG §7 규칙(24칸 고정, 칸마다 첫 시도만, NOT_RUN·HOST_ERROR·SHA_MISMATCH·EVAL_MISSING은 실패, smoke·dev 제외)을 analysis가 한 번만 적용합니다.
- 사전 등록 sha256은 원장 `ledger.json`의 `prereg_sha256` 키이고 analysis에 그대로 복사됩니다. `--ledger`를 주면 그 파일 sha256이 `analysis.ledger.sha256`과 같아야 합니다.
- analysis 칸이 정확히 4조건 × TEST 601–606이 아니면(DEV 701·702 포함 등) 거부합니다.
- 출력: 조건별 n/6(Wilson), 1차 실패 사유, 성분별 실패 run 수, 보조 지표(완료 SIM s, 최소 차체 간격, 발화, 교착, 환각, LLM 비용), seed × 조건 표, 제외 행·편차, 막대. NOT_RUN + HOST_ERROR ≥ 5/24면 "실행 불완전"을 붙입니다(§7-6).

### (d) 단독 최소 E2E
```
python scripts/report_tables.py e2e --prereg experiments/2026-10-21-e2e-min/PREREG.md \
  --rows <report>/e2e-rows.jsonl --out <report> [--expect-prereg-sha …]
```
```
{"type":"header","prereg_sha256":"…"}
{"type":"run","level":"E2E-1p","seed":601,"smoke":false,"status":"complete","report_path":"runs/e2e-1p-1/eval.json"}
{"type":"run","level":"E2E-2","seed":601,"smoke":false,"status":"HOST_ERROR"}
```
- 행 형식은 `claude/e2e-min-runner` `PREREG_DRAFT.md` §10과 같습니다. report는 `harness.e2e_min_eval.recount_run(run_dir)`의 출력(`ugrp.e2e_min.evaluation.v1`)입니다. HOST_ERROR 행은 report 없이 실패로 세고 단계 도달 0입니다.
- 레벨별로 따로 셉니다(E2E-1' 혼합 / E2E-2 순수). "대체 단계" 열에 `release←rule_script:release_open_v1`처럼 대체 단계를 적습니다. `substitutions_match_level`이 거짓이면 거부합니다.
- smoke 행(`"smoke": true`)은 n/N에 넣지 않고 따로 한 줄로 적습니다.
- *등록 N은 고정입니다: E2E-1' 3, E2E-2 6*(PREREG_DRAFT §2). 바꾸는 옵션은 없고, 등록 N보다 많은 본 run은 거부합니다. HOST_ERROR는 재실행하지 않습니다(§3).
- 단계 도달은 로봇 단위로 셉니다(분모 = 2 × N).

## DeepSeek 실행 절차 (각 실험 직후)
1. 사전 등록이 FROZEN으로 커밋됐는지, 원장 header에 그 sha256이 있는지 확인합니다.
2. 위 명령을 run root 안의 *새* `report*/` 디렉터리로 실행합니다. 원본 결과는 바꾸지 않습니다.
3. exit 2면 stderr의 `REFUSED:` 사유를 그대로 보고하고 표를 쓰지 않습니다.
4. `report.md`의 요약 줄과 그림을 보고서에 붙입니다. 판정 문장은 `report.md`에 적힌 것만 씁니다.

## 테스트
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_report_tables.py   # matplotlib 없으면 그림 테스트 1개 skip
```
가짜 입력으로 각 트랙의 표, 분모, 거부 경로(SHA 불일치, 초안, 미등록 seed, 중복, 대체 단계 불일치, 원장 제외 목록 불일치, 미기록 퍼널, GT 보정 기록 없음)를 확인합니다.
테스트용 사전 등록 사본은 `tests/fixtures/report_auto/`에 있으며(출처 SHA는 `SOURCE.txt`), 원본이 아닙니다. 실행 측 기록기 테스트는 각 브랜치의 `tests/test_act18_tournament_ledger.py`, `tests/test_pairact_p1_ledger.py`, `tests/test_pairact_p5_rows.py`, `tests/test_analyze_l1lite.py`, `tests/test_e2e_min_prereg.py`입니다.
