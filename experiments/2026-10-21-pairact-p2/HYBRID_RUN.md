# pairact hybrid 실행 경로 (arm N, 기본 off, 실행 전 초안)

목적: arm N(근거리 전용 학습) 체크포인트를 *학습 근거리 + 코드 운반(hybrid)* 으로 평가합니다. 학생이 접근 → 정렬 → READY → 파지 → 3초 유지를 하고, 코드가 운반·문 통과를 하고, 하차 시작 지점에서 학생에게 제어를 돌려줍니다. 학생은 하강·열기·들기·후진까지 합니다.
실행한 것은 CPU 단위 테스트뿐입니다. MJWarp·GPU에서 이 경로를 돌린 적은 없습니다.

## 0. 규칙
- 표기: `hybrid_n` = "학습 근거리 + 코드 운반(hybrid)". arm F(`student`, "학습 전 구간")와 합산·대체하지 않습니다(사전 등록 v2.1 `arm_rules`, `dsh/pairact-r1-armN`).
- arm N은 순수 학생으로 돌리지 않습니다. 이 경로로만 평가합니다.
- 운반 코드는 pilot(8343000–039)·validation(8341000–019) seed에서만 맞춥니다. 보류 seed의 영상·로그는 튜닝에 쓰지 않습니다. config와 SHA는 보류 실행 전에 커밋합니다.
- 운반 모드 기본값은 `nav`입니다. `map`(정적 지도)은 창민 승인 전에는 root와 teacher 두 곳에서 모두 거부됩니다.
- 오프피크(UTC 16:30–00:30), gcp6 또는 gcp2, 새 run root, 끝나면 VM 정지.

## 1. 스택 (기본 경로는 -c5 그대로, `--hybrid-carry`일 때만 아래 SHA)
| tree | 브랜치 | SHA | 고정 위치 |
|---|---|---|---|
| root | `dsh/pairact-p2-carrypath-r-c5-hybrid` | 이 문서가 든 커밋 | — |
| adapter | `dsh/pairact-p2-carrypath-a-c5-hybrid` | `6e957a42665ce98e40aae8afcb79023f669b5e65` | `warp_flow_episode.HYBRID_ADAPTER_SHA` |
| teacher(runner) | `dsh/pairact-p2-carrypath-c5-hybrid` | `60ef0b1481082daad4cf5582d1542661c0b8664f` | `warp_flow_episode.HYBRID_TEACHER_SHA` |
| 학생 worker | `dsh/pairact-p5-student-hybrid` | `bdc41a3fa8ec151889a1c6559147f495a9619dad` | `run_warp_flow_teacher.HYBRID_STUDENT_SHA` |
| nav 검출기 | `dsh/nav-v5-recal` | `ceacd474b9e03110c1b35c0cd0fc2cca40594ec9` | `HYBRID_NAV_SHA`, teacher `hybrid_carry.NAV_SHA` |

- adapter -a-c5-hybrid는 -a-c5에서 teacher 고정 1줄만 바꿨습니다. teacher -c5-hybrid는 -c5에 `harness/hybrid_carry.py`를 더하고 runner에 `hybrid_carry=None` 인자와 학생 tick 가드 1줄을 넣었습니다(gate 경로 바이트 동일 테스트가 이 조각만 허용). worker -hybrid는 `shadow` op만 더했습니다.
- `--hybrid-carry` 없이 돌리면 -c5 고정(adapter `3779d961`, teacher `75929e77`, worker `3c9337d5`)을 그대로 씁니다. arm F 학생과 teacher arm은 -r-c5에서 돌려도 되고 여기서 플래그 없이 돌려도 같습니다.

## 2. 구간 흐름과 인터페이스 I1–I11 (teacher `harness/hybrid_carry.py`)
```
STUDENT_GRASP ──(두 로봇 자기 done 3초 → worker release_instruction)──▶ CARRY_SYNC ──(PairCarrySync 'carry' GO)──▶
CODE_CARRY ──(자기 판정 도착)──▶ PLACE_SYNC ──(PairCarrySync 'place' GO)──▶ STUDENT_PLACE ──(학생 finished)──▶ DONE
어느 구간에서든 실패 → ABORT(에피소드 종료, 실패로 셈)
```
| # | 구현 | 내용 |
|---|---|---|
| I1 | `HybridSegmentArbiter` | 로봇별 구간 상태기계. 정해진 순서 밖 전환은 예외. 전환 신호는 자기 신호뿐(GT `hold_ok` 안 씀) |
| I2 | `PairCarrySync` ×2 | task `carry`(운반 시작), `place`(반환). seq·epoch·TTL 검사 그대로 |
| I3 | `VirtualBeamPlanner` + `FormationTracker` | 리더(navigator)가 손잡이 시점 빔 좌표계 B0에서 가상 빔 자세 V를 움직이고, 두 로봇이 각자 `compose(V, 자기 오프셋)`을 자기 오도메트리로 추종(`pair_carry_teacher_warp.body_command`·`make_command` 재사용) |
| I4 | `MessageBus` | 리더 → 팔로워: V, 속도, 단계, 리더의 빔 추정, seq, observed_at_s. TTL을 넘으면 팔로워 정지. 지연·손실 모형은 없음 |
| I5 | `PoseTrustGate` | 자기 dead-reckoning 불확실성 한계를 넘으면 `SELF_POSE_UNCERTAIN`으로 실패(재기준점 없음, fail closed) |
| I6 | `NavZoneSensor` / `map_route_b0` | nav: 자기 카메라 zone B 검출(`GpuCalibZoneDetector`) + 성분 아래 가장자리 지면 투영(`ground_point_robot`). map: `carry_route`(정적 문·zone 좌표) + 에피소드 시작 자세 + 자기 오도메트리 |
| I7 | worker `shadow` op | 코드 구간에서 학생은 자기 카메라 관측만 받고(정책 추론은 로그용, 선택), 제안은 버립니다. 자기 발행 이력에는 *실제로 적용된 코드 명령*이 들어갑니다 |
| I8 | `PLACE_SYNC → STUDENT_PLACE` | 도착(자기 판정) + place GO에서 학생 명령 재개. 이 시점 학생 단계 head는 `place`를 내야 합니다(arm N 오프라인 gate의 carry→place 전이로 미리 봄) |
| I9 | runner 플래그 | root `--hybrid-carry <config>` → bridge → teacher `run(..., hybrid_carry=...)`. `--student-eval` 필수 |
| I10 | `HybridRun.summary()` | `carry_mode`, `outcome`, `code_segment_s`, `student_commands_executed_ratio`, `gt_inputs_to_code = 0`, `teacher_steps = 0`, 전환·sync·planner 이벤트, 오도메트리 누적 |
| I11 | `tests/test_hybrid_carry.py` | 모듈 import에 시뮬레이터·evaluator·학생 eval 없음, 함수 인자에 truth/gt/world/contacts 없음 |

nav 모드 운반 순서: `carry_hold`(들기 자세 유지) → `acquire`(빔 중심 기준 제자리 회전, zone B가 `confirm_ticks`번 연속 보이면 정지; 한 바퀴 또는 `acquire_budget_s` 넘으면 `zone_not_found`) → `approach`(navigator 정면을 zone 점으로 돌린 뒤 전진. 문은 nav r5처럼 zone 성분 중심을 겨눠 지나감. zone 아래 가장자리 거리 ≤ `arm_ground_m`이면 arming, 그 방향으로 `advance_m` 더 감; `reobserve_wait_s`의 2배 동안 안 보이면 `zone_lost`) → `zone_settle` → 도착.

## 3. 운반 모드
| 모드 | 입력 | 상태 |
|---|---|---|
| `nav`(기본) | 자기 카메라 zone 검출, 자기 오도메트리, 리더 메시지. 정적 지도 없음 | 구현, CPU 테스트만 |
| `map` | 정적 지도의 문·zone 좌표(`static_map_for` → `carry_route`), 케이스 시작 자세, 자기 오도메트리 | 구현, *사용 금지*. root `HYBRID_MAP_MODE_APPROVED=False`, teacher `MAP_MODE_APPROVAL_SHA256=None`이라 시작 전에 거부됩니다 |

`map`을 쓰려면 (1) 창민이 공동 운반의 정적 지도 사용을 승인하고, (2) 승인 기록 파일을 커밋하고, (3) teacher에 그 sha256을 `MAP_MODE_APPROVAL_SHA256`으로, root에 `HYBRID_MAP_MODE_APPROVED=True`를 새 커밋으로 넣고, (4) 결과를 `hybrid_n_map`("(정적 지도)" 표기)으로 따로 보고해야 합니다. 이 문서 작성 시점에는 (1)이 없습니다.

## 4. config (`HYBRID_CARRY_NAV_TEMPLATE.json`)
- 키 집합이 정확히 맞아야 하고, 수치는 모두 양수여야 합니다. 기본값을 몰래 넣지 않습니다. 템플릿의 `[확인 필요]` 칸이 남아 있으면 검증에서 거부됩니다.
- 채워야 할 값: 적재 상태 오도메트리 보정 3개, 불확실성 한계·증가율 4개, `carry_budget_s`(사전 등록 `episode_cap_sim_s`의 운반 예산과 같게), nav `profile`, `arm_ground_m`, `advance_m`.
- `v_max`·`w_max`·stretch 값은 GT 운반 teacher `Params`의 값을 그대로 옮겼습니다.
- 보정값 측정 도구는 아직 없습니다 [확인 필요: pilot seed에서 자기 명령 적분 대비 eval-only 이동량을 재는 스크립트. 측정값만 config에 들어가고 GT는 실행 중 입력이 아닙니다].

## 5. 실행
```bash
# 0) tree 준비(각 SHA로 checkout, clean). nav tree는 config nav.source 경로
for t in root:dsh/pairact-p2-carrypath-r-c5-hybrid adapter:6e957a42665ce98e40aae8afcb79023f669b5e65 \
         teacher:60ef0b1481082daad4cf5582d1542661c0b8664f student:bdc41a3fa8ec151889a1c6559147f495a9619dad \
         nav:ceacd474b9e03110c1b35c0cd0fc2cca40594ec9; do echo "$t"; done   # git worktree add $SRC/<name> <ref>

# 1) student-eval.json: P5_STUDENT_EVAL.md §2와 같은 6키. source=$SRC/student(-hybrid worker),
#    model=arm N 동결 체크포인트(CHECKPOINT_FREEZE_ARM_N.json), config=...PAIRACT_R1_TRAIN_CONFIG_ARM_N.json
# 2) hybrid.json: 템플릿을 채운 파일(커밋 후 사용)

# 3) pilot smoke (pilot seed 3개, 보류 seed 아님)
cd $SRC/root
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/pilot-cases.json --indices 0,1,2 --cap-s 60 --out $RUN/hybrid-smoke --vm-hourly-usd 1.096 \
  <SMOKE.md §3의 physics/contact/scene 플래그 그대로> \
  --student-eval $RUN/student-eval.json --hybrid-carry $RUN/hybrid.json

# 4) P5 보류 20 seed (arm N 동결·prereg FROZEN 커밋 뒤에만): 위와 같고
#    --cases $RUN/p5-heldout-cases.json --indices 0,...,19 --out $RUN/p5-hybrid-n
```
- [확인 필요] gcp6 wrapper(`run_warp_flow_teacher_gcp6.py`)가 `--hybrid-carry`를 그대로 넘기는지. wrapper는 이 레포 밖 경로입니다.
- [확인 필요] 적재 자세에서 카메라 높이·피치가 `GATE_GROUND_PROJECTION`(높이 0.300 m, 아래로 19°)과 같은지. 다르면 zone 거리 투영이 틀립니다.

## 6. 집계
```bash
python scripts/pairact_p5_rows.py --prereg <v2.1 FROZEN> --cases p5-heldout-cases.json \
  --student RUN/p5-student --hybrid-n RUN/p5-hybrid-n --teacher RUN/p5-teacher [--static-check rule-A.json] \
  --out RUN-report/p5-rows.jsonl
python scripts/pairact_r1_p5_decide.py --prereg <v2.1 FROZEN> --rows RUN-report/p5-rows.jsonl \
  --freeze experiments/2026-10-21-pairact-r1/CHECKPOINT_FREEZE.json --out RUN-report/p5-decision.json   # dsh/pairact-r1-armN
```
- `hybrid_n` 행에는 `carry_mode`, `gt_inputs_to_code`, `code_segment_s`, `hybrid_outcome`, `student_commands_executed_ratio`가 붙습니다. hybrid 블록이 없는 run을 `--hybrid-n`으로 넣으면 거부합니다.
- `p5_counts`는 `carry_mode`가 `nav`가 아닌 행을 오류로 처리하고, `gt_inputs_to_code`가 null이면 성공으로 세지 않습니다.

## 7. 볼 것
| 파일 | 내용 |
|---|---|
| `world-00k/raw/result.json` → `hybrid` | 위 I10 필드. `outcome`이 `handed_back`이 아니면 실패 사유(`abort:zone_not_found`, `abort:zone_lost`, `abort:SELF_POSE_UNCERTAIN`, `abort:formation_stretch`, `abort:code_carry_timeout`) |
| `world-00k/raw/student-eval.jsonl` | 코드 구간 행: `hybrid_segment`, 적용한 코드 명령, 학생 shadow 단계. 학생 구간 행은 P5와 같음 |
| `summary.json` → `worlds[].hybrid` | 행 집계용 요약 |

## 8. 위험과 미검증 (실행 전 확인)
1. GPU/MJWarp에서 한 번도 돌지 않았습니다. 테스트의 가짜 세계는 명령이 보정값대로 정확히 움직이는 운동학 모형이라 미끄러짐·접촉·빔 하중이 없습니다.
2. navigator는 빔과 상대 로봇 쪽을 봅니다. 빔·상대 차체가 zone B를 가리면 `acquire`가 실패합니다 [확인 필요: pilot smoke 영상].
3. 문 검출기가 없습니다. 문은 zone 성분 중심을 겨눠 지나가는데, 이것은 단독 로봇(nav r5)에서만 확인된 방식입니다. 1 m 넘는 대형으로 문을 지나는지는 모릅니다.
4. 대형 유지는 두 로봇의 dead-reckoning 추정 비교뿐입니다. 실제 늘어남을 직접 재지 않습니다. CPU 자기 센서 운반은 0/33(`SELF_POSE_UNCERTAIN`)이었습니다.
5. 반환 시점 학생 이력은 코드 명령입니다. teacher 시연(운반 중 teacher 명령)과 분포가 다를 수 있습니다.
6. 메시지 지연·손실 모형이 없습니다(같은 프로세스, 지연 0). L1-lite 지연 조건과는 별개입니다.

## 9. 테스트 (CPU, mujoco·warp 없음)
- teacher -c5-hybrid: `tests/test_hybrid_carry.py` 17개 + 기존 C5 묶음(`test_pairact_p3_collect_admission.py`, `test_grasp_act_admission.py`, `test_pair_carry_route_c4.py`, `test_pair_carry_detour.py`, `test_pair_carry_teacher_warp.py`) 88개 → 105개 통과.
- worker -hybrid: `tests/test_pairact_r1_student.py` 10개 통과(shadow 2개 추가).
- adapter -a-c5-hybrid: `tests/test_pairact_p2_adapter.py` 9개 통과.
- root: `tests/test_pairact_p2_root.py`·`tests/test_pairact_p5_rows.py` 21개 통과(hybrid 5개 추가).
