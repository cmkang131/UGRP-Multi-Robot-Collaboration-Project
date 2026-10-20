# pairact-r1 P3 교사 시연 수집 사양 (초안, 수집 전)

상태: *초안이고 수집하지 않았습니다.* P1(MJWarp teacher 공동 파지 관문 ≥38/40)과 P2(MJWarp 운반·하차 경로 smoke)가 통과해야 시작합니다. 실행은 DeepSeek이 gcp6 또는 gcp2에서 오프피크에 합니다.

## 1. seed 분할 (`seeds.json`)
| split | seed | 개수 | 용도 |
|---|---|---|---|
| train | 8340000–8340199 | 200 | teacher 시연. *teacher 성공 에피소드만* TRAIN 텐서에 들어갑니다 |
| validation | 8341000–8341019 | 20 | teacher 시연. 오프라인 gate와 체크포인트 선택에만 씁니다 |
| heldout | 8342000–8342019 | 20 | *시연을 수집하지 않습니다.* P5 closed-loop(학생·teacher 같은 seed)에만 씁니다 |

- ~~시도 수는 seed 200/20으로 고정합니다(보충 범위 없음).~~ *2026-10-21 대체*: 성공 필터 결정(`pairact-success-filter-decision.md`)에 따라 `COLLECT_PREREG_DRAFT.json`이 기준입니다. train 시도는 8340000부터 순서대로 소비하고, 부족하면 `seeds.json`의 `train_extension` 8340200–8340599로 넘어갑니다(시도 상한 600, 목표 성공 200·최소 150, 구간 6개 × 성공 ≥20). validation 20은 1회씩, heldout은 수집하지 않습니다.
- 겹침 검사(수집 전 필수, 결과 JSON을 run root에 저장):
  ```
  python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 \
    origin/claude/beampair7 origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 \
    origin/dsh/pairact-p0-diag origin/dsh/act18-carry-retrain-r1
  ```
  P1·P2 브랜치가 push되면 그 ref도 추가합니다(없는 ref는 스크립트가 오류로 멈춥니다).
  2026-10-20 실행 결과: problems 0, scan_hits 0(위 8개 ref). `dsh/pairact-p2-carrypath`는 아직 origin에 없어서 검사하지 못했습니다. 양성 대조로 보류 범위를 8329000–8329019로 바꾸면 main에서 1,318건이 잡혔습니다.
- 등록된 기존 범위: 71001–71007, 8316902, 8318600–8318639, 8318700–8318739, 8328000–8328199(beamact1–4 TRAIN/validation), 8329000–8329019(beamact2/3 보류), 8420000–8420039(beamact5 wide gate40). 출처는 `seeds.json`의 `known_ranges`에 적었습니다.

## 2. 시작 분포
- 각 로봇의 시작 위치는 *자기가 맡은 빔 끝의 파지점에서 평면 거리 0.3–1.2 m 균등*으로 뽑습니다. 방위각과 yaw는 beampair8 생성기 규칙을 그대로 따릅니다[확인 필요: MJWarp beamact5 생성기의 해당 인자 이름].
- 근거: beamact4 README:9. 평가는 40로봇 중 30개가 0.8 m 밖에서 시작했는데 TRAIN은 54/60,023행(0.090%)뿐이었고 최대값이 0.84855 m였습니다. beamact2 README:60에 따르면 TRAIN은 0.8 m 이내만 선정됐습니다.
- *수집 관문(사전 등록)*: TRAIN 성공 에피소드의 시작 거리(로봇별)를 0.1 m 구간 9개로 나눴을 때 모든 구간에 1개 이상 있고, 0.8 m 초과 비율이 25% 이상이어야 합니다. 균등분포라면 기대값은 44%입니다. 못 미치면 학습으로 넘어가지 않고 보고합니다.
- 시작 거리는 eval-only(plan.json)에만 기록합니다. 필드 이름은 [확인 필요]입니다. 히스토그램(`start-distance-hist.json`)은 DeepSeek이 plan.json에서 집계합니다. 학생 입력에는 들어가지 않습니다.
- P5 보류 평가도 같은 생성기와 같은 0.3–1.2 m 범위를 씁니다. 1.2 m 밖은 r1 범위가 아닙니다(DESIGN §4-4).

## 3. 에피소드 범위
한 에피소드: cold start → 접근 → 정렬 → READY/GO → 파지 → 공동 3초 유지 → 운반(빔을 든 채 문 통과) → zone B 정렬 → 하강·열기·들어올림·후진 → 완료.
- 로봇별 student stream은 연속된 두 구간입니다. ①skill `grasp`(파지·3초 유지까지) ②skill `release`, destination_zone `B`(운반·하차). P2 recorder 설계(`harness/pair_carry_recorder.py`, `dsh/pairact-p2-carrypath`)와 같습니다.
- 계약 입력은 바꾸지 않습니다. 자기 RGB 4 lag, 자기 발행 명령 16개, 작업 토큰(skill·object_kind·role·destination_zone), 자기 시계 2개만 들어갑니다. GT·상대 자세·단계는 입력이 아닙니다.

## 4. recorder 필수 필드 (P2 워커 ④와 조율)
| 파일 | 필드 | 요구 |
|---|---|---|
| student-{rid}.jsonl | `skill_elapsed_s`, `pwm_elapsed_s` | *v7 시계*(deadband 2). *반영됨(2026-10-21)*: `dsh/pairact-p2-carrypath`의 runner가 pair_carry on일 때 로봇별 `pair_carry_recorder.DeadbandIssuedClock(2)`(이 브랜치 `DeadbandIssuedClock`과 같은 규칙) 하나를 파지·운반 구간에 같이 씁니다. `result.json → carry_recording`에 `issued_clock_deadband: 2`와 로봇별 리셋 횟수가 남습니다 |
| teacher-{rid}.jsonl | `teacher_phase` | 모든 행에 필수입니다. 운반 구간은 `carry:<phase>`(P2 PHASES 14개), 파지 구간은 visible_only 교사 어휘 9개(approach·search·relook·align·ready·pick·verify·complete·done)입니다. *대응표 고정(2026-10-21)*: P2 teacher DESIGN §7-1과 `pair_carry_recorder.TEACHER_PHASE_TO_STAGE`, 이 브랜치 `TEACHER_PHASE_TO_STAGE`가 같은 키에서 같아야 합니다(양쪽 테스트). 없는 값이 있으면 sidecar 생성이 그 에피소드를 거부합니다 |
| teacher-{rid}.jsonl | `sample_id` | student 행과 1:1. sidecar가 이 키로 phase를 붙입니다 |
| raw/result.json | `physical_success`, `status`, `student_execution=false`, `recording_mode=training`, `training_rgb=true` | `grasp_act_data.convert` 요구 그대로입니다. `physical_success`는 §5의 teacher 성공과 같아야 합니다. *반영됨*: 기록 on + pair_carry on에서 runner가 `physical_success = grasp_physical_success ∧ carry_success`로 씁니다(기록 off smoke에서는 파지 관문 정의 그대로) |
| eval-only.jsonl | GT 자세, 빔 자세, 접촉 | P2 evaluator 입력입니다. 학습 텐서로는 들어가지 않습니다 |

## 5. teacher 성공 판정 (학습 포함 조건)
아래를 모두 만족한 에피소드만 TRAIN·validation 텐서에 들어갑니다.
1. EXIT 0, `status=complete`, HOST_ERROR 없음
2. 공동 파지 관문 통과(P1과 같은 3초 공동 유지 기준)
3. P2 evaluator(`harness/pair_carry_eval.py`, DESIGN §5) 성공: `placed_in_zone_B AND drop_events == 0 AND robot_robot_contacts == 0`. 벽 접촉은 기록만 합니다.
4. 두 로봇 stream이 모두 sidecar 생성을 통과(phase 누락·미등록 phase 0)

실패 에피소드는 수집 원장(`ledger.jsonl`, `scripts/run_pairact_collect.py`)과 `rejection_table.json`에 seed·실패 단계·사유를 남기고 학습에는 쓰지 않습니다. 원본은 지우지 않습니다. 판정·필터의 정본은 `COLLECT_PREREG_DRAFT.json`의 `success`·`filter`입니다. teacher 성공률(n/200, n/20)은 결과로 보고합니다.

## 6. 산출물 배치 (원본 덮어쓰기 금지, 새 run root)
```
runs/pairact-p3-<TS>/seed-<seed>/{SOURCE_SHA,EXIT,raw/...}     # 수집 원본
datasets/pairact-r1-<TS>/                                         # grasp_act_data.convert 출력
datasets/pairact-r1-<TS>-stage/stage-targets.json                 # build_pairact_r1_stage_targets.py
runs/pairact-p3-<TS>/{seed-check.json,rejection_table.json,start-distance-hist.json,SHA256SUMS}
```
- convert protocol: `train_seeds` = 성공한 train seed, `validation_seeds` = 성공한 validation seed. heldout seed는 넣지 않습니다(`pairact_r1_offline.py`가 heldout 포함 데이터셋을 거부합니다).
- 데이터 SHA(`manifest.json`, `stage-targets.json`)를 고정한 뒤 P4 approval 파일에 넣습니다.

## 7. 비용 추정
- aggressive-replan §1: P3 1부 100개 약 2 h, 2부 140개 약 2.5 h, 합계 약 4.5 GPU-h[확인 필요: P2 smoke의 wall/SIM 실측으로 다시 계산]. 오프피크(UTC 16:30–00:30)에 실행합니다.
