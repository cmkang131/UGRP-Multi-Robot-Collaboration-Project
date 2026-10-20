# pairact P5: 학생 ACT 공동 운반 평가 runner (기본 off, 실행 전 초안)

목적: 보류 20 seed에서 *학생 ACT가 모든 명령을 내는* MJWarp 에피소드를 teacher와 같은 seed·같은 evaluator로 돌립니다. 이 문서는 실행 방법만 정합니다. 실행 조건(체크포인트 선택, prereg 커밋)은 `dsh/pairact-p5-student`의 `experiments/2026-10-21-pairact-r1/PAIRACT_R1_EVAL_PREREG_DRAFT.json`과 `RUNBOOK.md` §5를 따릅니다.

## 0. 규칙
- P4 체크포인트가 오프라인 gate를 통과하고, prereg(에피소드 cap 값 포함)가 커밋된 뒤에만 돌립니다. 오프피크(UTC 16:30–00:30), gcp6 또는 gcp2, 새 run root, 끝나면 VM 정지.
- 학생 arm과 teacher arm은 같은 cases(같은 seed 순서)를 씁니다. teacher arm은 `--student-eval` 없이 같은 명령입니다.
- 결과는 n/20(학생)과 n/20(teacher)를 나란히 보고하고 합산하지 않습니다. CPU 결과·P1/P2 결과와도 합산하지 않습니다.

## 1. 스택 (세 tree + 학생 worker tree)
| tree | 브랜치 | 고정 방식 |
|---|---|---|
| root | `dsh/pairact-p2-carrypath-r` | 이 문서가 든 커밋 |
| adapter | `dsh/pairact-p2-carrypath-a` | `warp_flow_episode.ADAPTER_SHA` |
| teacher(runner) | `dsh/pairact-p2-carrypath` | `warp_flow_episode.TEACHER_SHA` |
| 학생 worker | `dsh/pairact-p5-student` | `run_warp_flow_teacher.STUDENT_SHA`(다르면 시작 거부) |

## 2. 학생 config (`student-eval.json`, 키 6개 고정, 절대 경로)
```json
{"mode": "pairact_r1_student_eval_v1",
 "python": "/home/ugrp/<act-venv>/bin/python",
 "source": "/home/ugrp/ugrp-sim/src/pairact-p5/student",
 "model": "/home/ugrp/ugrp-sim/runs/pairact-carry-r1-<TS>/main/step-<선택>",
 "config": "/home/ugrp/ugrp-sim/src/pairact-p5/student/experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json",
 "device": "cuda"}
```
- `python`은 torch·lerobot이 있는 ACT 환경입니다 [확인 필요: gcp6/gcp2의 ACT venv 경로]. worker는 `source`를 cwd로 띄웁니다.
- GT·teacher·상대 자세 키는 config에 존재할 수 없습니다(키 집합이 다르면 거부).

## 3. 실행 (SMOKE.md §3과 같은 플래그 + 두 가지)
```bash
cd $SRC/root
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/p5-heldout-cases.json --indices 0,...,19 \
  --cap-s 60 --out $RUN/p5-student --vm-hourly-usd 1.096 \
  <SMOKE.md §3의 physics/contact/scene 플래그 그대로> \
  --student-eval $RUN/student-eval.json
```
- `--cap-s 60` + 후보 프로필의 `carry_cap_s`가 학생 에피소드 전체 상한입니다(runner가 처음부터 `cap_s + carry_cap_s`로 돕니다). prereg의 cap 규칙으로 정한 값과 다르면 adapter 후보의 `carry_cap_s`를 새 후보로 만들어 맞춥니다(기존 후보는 바꾸지 않음).
- 보류 seed cases(`p5-heldout-cases.json`)는 P3 생성기로 만든 보류 20 seed입니다. 생성 명령은 [확인 필요: P3 수집 명령 확정 후].

## 4. 볼 것
| 파일 | 내용 |
|---|---|
| `summary.json` | `student_eval`(config, sha256), `worlds[].success`(= 학생: 3초 유지 도달 ∧ evaluator 성공), `student_funnel`, `teacher_steps`(0이어야 함), `student_worker_requests` |
| `world-00k/raw/result.json` → `student_eval` | 지시 전환 시각(`release_instruction_t`), 종료 시각, barrier·protocol 이벤트, 시계 리셋 수, `teacher_steps = 0`, `gt_inputs_to_student = 0`, 퍼널 |
| `world-00k/raw/carry-eval.json` | evaluator 판정(`setdown_boundary = zone_entry_v1`) |
| `world-00k/raw/student-eval.jsonl` | 매 tick 학생 입력(관측 행, 픽셀 제외)·READY·발행 명령·eval-only 퍼널 통과 여부 |

## 5. 막히면
- worker 시작 실패(`student worker startup mismatch`)·SHA 불일치: 실행하지 않고 보고합니다.
- HOST_ERROR: 같은 seed 1회 재실행, 두 번째도 HOST_ERROR면 실패로 세고 따로 보고합니다(prereg exclusions).
