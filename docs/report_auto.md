# 결과 보고 자동화: `scripts/report_tables.py`

실행 결과 원장(ledger)과 summary를 읽어 Markdown 표와 그림을 만듭니다. 10/24 이후 Claude 없이 DeepSeek이 실행 직후 같은 형식으로 보고할 수 있게 하려는 도구입니다.
물리를 돌리거나 run root에 쓰지 않습니다. 파일을 읽기만 합니다.

## 공통 규칙
| 항목 | 동작 |
|---|---|
| 입력 해시 | 읽은 모든 파일의 sha256을 `report.md` "입력" 절과 `report.json.inputs_sha256`에 남깁니다 |
| 사전 등록 SHA 대조 | 원장 header(또는 report.json)에 적힌 `prereg_sha256`이 `--prereg` 파일의 sha256과 다르면 *거부*(exit 2, `REFUSED: …`). `--expect-prereg-sha`로 커밋된 값을 고정하면 그것과도 대조합니다 |
| 사전 등록 상태 | `status`가 `FROZEN`/`REGISTERED`가 아니면 거부합니다. `--allow-draft`를 주면 표는 만들지만 맨 위에 "초안 기준, 판정 아님"을 붙이고 판정(승자 등)은 쓰지 않습니다. Markdown 사전 등록(E2E `PREREG_DRAFT.md`)은 상태를 읽을 수 없어 항상 초안 취급입니다 |
| 분모 | 사전 등록 N을 고정합니다. 실패·HOST_ERROR·미실행은 분모에서 빠지지 않고, 미실행은 따로 적고 판정을 보류합니다 |
| 비율 표기 | `n/N (p%, CI lo–hi%)`. CI는 Wilson 95% |
| 합산 금지 | 트랙·레벨·표기(A/B/C)·smoke·DEV seed를 섞지 않습니다 |
| 출력 | `--out` 디렉터리에 `report.md`, `report.json`, `fig-*.png`. matplotlib가 없으면 그림만 건너뛰고 표는 만듭니다 |

종료 코드: 0 성공, 2 거부(이유는 stderr).

## 트랙별 사용법

### (a) 단독 ACT release tournament A
```
python scripts/report_tables.py tournament \
  --prereg experiments/2026-10-17-act18/CARRY_TOURNAMENT_A_PREREG.json \
  --ledger <run_root>/tournament-ledger.jsonl --out <run_root>/report
```
원장 형식(JSONL). *tournament runner가 아직 없어 이 형식은 제안입니다* [확인 필요]. 실행 측(DeepSeek)이 world-run마다 한 줄씩 씁니다.
```
{"type":"header","prereg_sha256":"<sha256>"}
{"type":"world_run","arm":"A-c1","rep":1,"cohort":"HO4","seed":88668,"status":"complete",
 "release_success":true,"physical_success":true,"drop_detected":false,
 "G":true,"early_open_grasp":false,"open_issued":true,"release_done":true,"cap_end":false}
```
- `release_success`·`physical_success`·`drop_detected`는 `harness/grasp_act_rollout.py` 기록 키입니다(확인함). `G`·`early_open_grasp`·`open_issued`·`release_done`·`cap_end`는 C2c 집계 용어를 world-run 단위 bool로 옮긴 것이며 키 이름은 [확인 필요]입니다.
- 주 지표: `status=="complete"` 그리고 release·physical 성공. 분모 24(8 seed × 3).
- 판정: 기준 대비 +3/24 이상, G가 −2/24보다 나쁘면 탈락, 동률은 조기 open 0 → 낙하 수. 규칙으로 못 가르면 "동률".
- HOST_ERROR는 분모에 남기고 실패로 셉니다. 토너먼트 사전 등록에 재실행 규칙이 없어서입니다 [확인 필요].
- 확인 run(미사용 seed 4 × 2)은 seed 목록이 미정이라 지원하지 않습니다.

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
python scripts/report_tables.py pairact-eval \
  --prereg experiments/2026-10-21-pairact-r1/PAIRACT_R1_EVAL_PREREG.json \
  --rows <p5_root>/p5-rows.jsonl --out <p5_root>/report
```
행 형식. *P5 rollout 기록기가 아직 없어 제안 형식입니다* [확인 필요]. `dsh/pairact-p5-student`에는 컨트롤러만 있습니다.
```
{"type":"header","prereg_sha256":"…","excluded_seeds":[8342019],"static_check_sha256":"…"}
{"type":"episode","arm":"student","seed":8342000,"attempt":1,"status":"complete","success":false,
 "funnel":{"approach":true,"alignment":true,"READY":false,"grasp":false,"hold_3s":false,
           "carry_1m":false,"door":false,"place":false},
 "termination":"cap_end","student_gt_corrections":0,"teacher_commands_issued_to_student":0}
```
- 분모 N_eff = 20 − 규칙 A 정적 제외(header). 제외가 있으면 `static_check_sha256`이 반드시 있어야 하고, 제외 seed에 episode 행이 있으면 거부합니다.
- HOST_ERROR는 같은 seed로 한 번만 다시 돌립니다(`attempt: 2`). 두 번째도 HOST_ERROR면 실패로 세고 따로 적습니다. 그 밖의 중복 행은 거부합니다.
- 학생 성공은 보정 0일 때만 인정합니다. `success: true`인데 `funnel.place`가 아니면 거부합니다.
- 출력: 성공 n/N_eff, 퍼널 표, 종료 사유, seed별 첫 실패 단계, 퍼널 막대(두 arm, Wilson CI).

### (c) L1-lite (조건별 n/6)
```
python scripts/report_tables.py l1lite --prereg <L1LITE_PREREG.json> --rows <root>/l1lite-rows.jsonl --out <root>/report
```
```
{"type":"header","prereg_sha256":"…"}
{"type":"run","condition":"peer_en","seed":601,"report_path":"runs/peer_en-601/eval.json"}
```
- `report`(내장) 또는 `report_path`(rows 파일 기준 상대 경로)는 `harness.e2ewarp_l1lite_eval.evaluate_run(run_dir)`의 출력(`ugrp.e2ewarp.l1lite_evaluation.v1`)이며, `dsh/l1lite-alloc`에서 확인했습니다.
- 조건과 seed는 사전 등록의 `conditions`/`seeds` 키를 씁니다. 없으면 브랜치 기본값(4조건, TEST 601–606)을 쓰고 [확인 필요]를 표시합니다. L1-lite 사전 등록은 아직 없습니다.
- DEV seed(701, 702), 미등록 조건, 같은 조건·seed 중복은 거부합니다.
- 출력: 조건별 성공 n/6과 성공 성분 수, 보조 지표(완료 SIM s 중앙값, 발화, 60 s 교착, 환각, 비용), seed × 조건 표, 조건별 막대.

### (d) 단독 최소 E2E
```
python scripts/report_tables.py e2e --prereg experiments/2026-10-21-e2e-min/PREREG.md \
  --rows <root>/e2e-rows.jsonl --out <root>/report [--planned E2E-1p=3 --planned E2E-2=6] [--expect-prereg-sha …]
```
```
{"type":"header","prereg_sha256":"…"}
{"type":"run","level":"E2E-1p","seed":601,"smoke":false,"report_path":"runs/e2e-1p-1/eval.json"}
```
- report는 `harness.e2e_min_eval.recount_run(run_dir)`의 출력(`ugrp.e2e_min.evaluation.v1`)이고, 그 안에 `e2e-handoff.json` 단계 도달이 들어 있습니다. `dsh/e2e-min`에서 확인했습니다.
- 레벨별로 따로 셉니다(E2E-1' 혼합 / E2E-2 순수). "대체 단계" 열에 `release←rule_script:release_open_v1`처럼 대체 단계를 적습니다. `substitutions_match_level`이 거짓이면 거부합니다.
- smoke 행(`"smoke": true`)은 n/N에 넣지 않고 따로 한 줄로 적습니다.
- 등록 N은 기본 E2E-1p=3, E2E-2=6입니다(PREREG_DRAFT §2). 등록 N보다 많은 run은 거부합니다.
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
가짜 입력으로 각 트랙의 표, 분모, 거부 경로(SHA 불일치, 초안, 미등록 seed, 중복, 대체 단계 불일치)를 확인합니다.
테스트용 사전 등록 사본은 `tests/fixtures/report_auto/`에 있으며, 원본이 아닙니다.
