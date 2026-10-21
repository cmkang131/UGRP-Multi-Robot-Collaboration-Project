# pairact-r1 P3 교사 시연 수집 사양 (초안, 수집 전)

상태: *초안이고 수집하지 않았습니다(v2, 2026-10-21 정정).* 시작 조건은 *P2 smoke 전 구간 성공 ≥1* 하나입니다(근거: smoke-1c seed 8420001·8420011·8420017 중 운반 성공 2/3, 증거 SHA는 `COLLECT_PREREG_DRAFT.json` `start_trigger.evidence`·`RUN_MANIFEST.json` `smoke`). P1 teacher 공동 파지 관문(≥38/40)은 수집을 막지 않는 비차단 병행 작업입니다. 실행은 DeepSeek이 오프피크에 합니다. 판정·필터·멈춤 규칙의 정본은 `COLLECT_PREREG_DRAFT.json`(v2)이고, 이 문서와 다르면 사전 등록이 우선입니다.

## 1. seed 분할 (`seeds.json`)
| split | seed | 개수 | 용도 |
|---|---|---|---|
| train | 8340000–8340199 | 200 | teacher 시연. *teacher 성공 에피소드만* TRAIN 텐서에 들어갑니다 |
| validation | 8341000–8341019 | 20 | teacher 시연. 오프라인 gate와 체크포인트 선택에만 씁니다 |
| heldout | 8342000–8342019 | 20 | *시연을 수집하지 않습니다.* P5 closed-loop(학생·teacher 같은 seed)에만 씁니다. 규칙 A 정적 검사 제외는 분모에서 빼고 대체하지 않습니다(`PAIRACT_R1_EVAL_PREREG_DRAFT.json` exclusions) |
| pilot | 8343000–8343039 | 40 | *측정(녹화 off) 수율 run 전용.* 구간 = (seed−8343000) % 6. 텐서에 들어가지 않고 학습 run의 A와 합산하지 않습니다. 녹화 probe 시작 3개도 여기서 뽑습니다 |

- *v2 기준(2026-10-21)*: 단위는 *pair episode*입니다. train 시도는 8340000부터 순서대로 소비하고, 부족하면 `train_extension` 8340200–8340599로 넘어갑니다. 숫자는 셋으로 나눠 씁니다: 물리 성공 S/N, 최종 채택 A/N(N = 행동 시도, 환경 실패 제외), validation S/20·A/20. *200은 채택 목표이지 분모가 아닙니다.* 학습 판정은 4단계입니다(오너 2026-10-21, 결과를 보기 전 고정, 사전 등록 `training_decision.tiers`): ①A ≥ 150 ∧ 6구간 각 ≥ 20 → 학습(정상) ②A ≥ 150 ∧ 일부 구간 < 20 → 학습, '데이터 범위 제한(구간 부족: 구간 목록)' 표기 ③80 ≤ A < 150 → 학습, '소량 데이터(A<150)' 표기, 결과 해석은 단계 퍼널 중심 ④A < 80 → 학습 안 함, P2 교사 운반 경로 개선으로 돌아가고 보고. 결정 문서의 '진행 가능한 최소치 150'은 이 4단계로 대체됩니다.
- validation 20은 *train 수집이 멈춘 뒤에만* 1회씩 돌립니다. 측정(pilot) run은 validation을 쓰지 않습니다. validation 채택 ≥ 8 ∧ 필수 단계 7개가 없으면 학습하지 않고 보고합니다(대체 seed 없음).
- 겹침 검사(수집 전 필수, 결과 JSON을 run root에 저장):
  ```
  python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 \
    origin/claude/beampair7 origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 \
    origin/dsh/pairact-p0-diag origin/dsh/act18-carry-retrain-r1
  ```
  P1·P2 브랜치가 push되면 그 ref도 추가합니다(없는 ref는 스크립트가 오류로 멈춥니다).
  2026-10-20 실행 결과: problems 0, scan_hits 0(위 8개 ref). 양성 대조로 보류 범위를 8329000–8329019로 바꾸면 main에서 1,318건이 잡혔습니다.
  2026-10-21(v2, pilot 포함) 실행 결과: RUNBOOK §1-1의 15개 ref에서 passed=true, problems 0, scan_hits 0. pilot 범위를 기존 범위와 겹치게 바꾸면 검사가 잡습니다(`tests/test_pairact_collect.py::test_seeds_json_and_check_script_cover_pilot`).
- 등록된 기존 범위: 71001–71007, 8316902, 8318600–8318639, 8318700–8318739, 8328000–8328199(beamact1–4 TRAIN/validation), 8329000–8329019(beamact2/3 보류), 8420000–8420039(beamact5 wide gate40). 출처는 `seeds.json`의 `known_ranges`에 적었습니다.

## 2. 시작 분포
- 각 로봇의 시작 위치는 *자기가 맡은 빔 끝의 파지점에서 평면 거리 0.3–1.2 m 균등*으로 뽑습니다. 방위각과 yaw는 beampair8 생성기 규칙을 그대로 따릅니다[확인 필요: MJWarp beamact5 생성기의 해당 인자 이름].
- 근거: beamact4 README:9. 평가는 40로봇 중 30개가 0.8 m 밖에서 시작했는데 TRAIN은 54/60,023행(0.090%)뿐이었고 최대값이 0.84855 m였습니다. beamact2 README:60에 따르면 TRAIN은 0.8 m 이내만 선정됐습니다.
- *시작거리 관문(사전 등록 `distance_gate`)*: *채택된(admitted) train pair episode*의 로봇별 시작 거리를 0.1 m 구간 9개로 나눴을 때 모든 구간에 1개 이상 있고, 0.8 m 초과 비율이 25% 이상이어야 합니다. 균등분포라면 기대값은 44%입니다. A ≥ 150이 된 뒤 매 batch 경계와 최종 집합에서 검사하고, 실패하면 *사후 seed 선별 없이* 멈추고 보고합니다(STOP_DISTANCE → NO_TRAIN_DISTANCE_GATE).
- *적응형 배정*: 구간은 앞선 결과에 따라 배정합니다(결손 가중). 두 로봇은 항상 같은 구간입니다. 따라서 수율은 원래의 로봇별 균등분포 수율이 아니라 적응형 수집 수율이고, 보고는 구간별·확장 전후(primary/extension)를 나눠 냅니다. 구간 시도 20회 뒤 운반 성공률이 20% 미만이면 그 구간은 '구간 범위 제한'으로 닫고 시도를 더 배정하지 않습니다(world 1 원인 불명 대응, `bins.bin_limit`).
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

## 5. teacher 성공 판정과 채택 (v2, 정본은 사전 등록 `status_table`·`success`·`filter`)
- *상태표*: world `complete`(cap_end·planning_wall_safety_cap·임무 실패 포함)는 행동 결과로 분모 N에 들어갑니다. `HOST_ERROR`·`interrupted`·결과 없음·admission 오류는 환경 실패로 N에서 빼고 따로 세며 seed는 소비합니다(HOST_ERROR만 같은 seed·구간으로 1회 재배정).
- *batch 조건(audit ①)*: batch summary가 `complete`, `HOST_ERROR == 0`, episode 명령 EXIT 0, `rejection_table` 절대경로가 모두 맞아야 정상 batch입니다. 아니면 그 batch의 개별 성공은 S에는 들어가도 *채택하지 않습니다*.
- *물리 성공 S*: `grasp_physical_success` ∧ P2 evaluator `carry_eval.success` ∧ `drop_events == []` ∧ `robot_robot_contact_ticks == 0`. 벽 접촉은 기록만 합니다.
- *필수 필드*: `grasp_physical_success`·`search_handoff`·`approach_handoff`·`data_admitted`·`end_reason`, 파지 뒤에는 `carry.outcome/events`와 `carry_eval.success/failure/drop_events/robot_robot_contact_ticks`. 하나라도 없거나 형이 다르면 기본값(0 등)으로 채우지 않고 record_error로 거부하며 수집을 멈춥니다(STOP_RECORD).
- *채택 A*: S ∧ handoff 없음 ∧ 정상 batch ∧ (학습 모드) `data_admitted` ∧ 두 로봇 stream이 모두 sidecar 검사 통과. sidecar 검사는 수집 중 원장 기록 전에 하고, 통과한 뒤에만 eligible로 셉니다.
- *운반 실패 하위 사유*: 원장에 `eval_failure`(not_through_door 등), teacher `carry.outcome`(route_blocked, *_timeout 등), 마지막 `fail` 이벤트(code·phase·detail), funnel, carried_max_m를 그대로 남기고 구간별로 집계합니다.

실패 에피소드는 원장(`ledger.jsonl`)에 남기고 학습에는 쓰지 않습니다. 원본은 지우지 않습니다. 생성기 예산 소진도 `setup_rejected` 행(관문별 누적 통과·거부, 막은 물체, 최소 틈, 생성기 SHA, 재현 명령)으로 남깁니다. 결과 보고는 S/N, A/N, validation S/20·A/20이며 n/200 표기는 쓰지 않습니다.

## 6. 산출물 배치 (원본 덮어쓰기 금지, 새 run root)
```
runs/pairact-p3-<TS>/seed-<seed>/{SOURCE_SHA,EXIT,raw/...}     # 수집 원본
datasets/pairact-r1-<TS>/                                         # grasp_act_data.convert 출력
datasets/pairact-r1-<TS>-stage/stage-targets.json                 # build_pairact_r1_stage_targets.py
runs/pairact-p3-<TS>/{seed-check.json,ledger.jsonl,report.json,SHA256SUMS}   # report.json: 구간 표·KS·distance_gate·decision
experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json                 # 스택·명령·자산·호스트·smoke·녹화 check 해시 (사전 등록과 함께 동결)
```
- convert protocol: `train_seeds` = 성공한 train seed, `validation_seeds` = 성공한 validation seed. heldout seed는 넣지 않습니다(`pairact_r1_offline.py`가 heldout 포함 데이터셋을 거부합니다).
- convert-input은 원장 header의 사전 등록 SHA가 현재 파일과 같고 판정이 TRAIN/TRAIN_DATA_RANGE_LIMITED일 때만 만들어집니다(audit ②). `protocol.json`에 판정과 '데이터 범위 제한' 여부가 남습니다.
- 데이터 SHA(`manifest.json`, `stage-targets.json`)를 고정한 뒤 P4 approval 파일에 넣습니다.

## 7. 비용 추정
- aggressive-replan §1: P3 1부 100개 약 2 h, 2부 140개 약 2.5 h, 합계 약 4.5 GPU-h[확인 필요: P2 smoke의 wall/SIM 실측으로 다시 계산]. 오프피크(UTC 16:30–00:30)에 실행합니다.
