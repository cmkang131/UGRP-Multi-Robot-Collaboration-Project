# PR #234 3차 리뷰 수정

기준 `b1eebc0e922a72c6c46395f6360f754de5412e74`. 제공된 `codex-234-review3.md` 전체를 읽고 P1 3건·P2 1건 및 외부 SIM 한도 handoff 누락을 수정했다. 이 기록은 단위 검사이며 코호트·MuJoCo 물리 실행·새 성공률/속도 결과가 아니다. 커밋은 coordinator가 한다.

## 변경과 반례

| 항목 | 수정 | 수정 전 실패 테스트 |
|---|---|---|
| P1 둘러보기 충돌 | `owncam_sweep_collision.py` 공용 함수. `owncam_drive_mem_v3.py`의 full/short/refix와 `m1_owncam_memory_v3.py`의 슬롯/일반 sweep 및 팔 명령을 검사 | `test_p1_leg_relook_filters_jamb_collision_pan`, `test_p1_slot_sweep_checks_posture_and_pan_collision` |
| P1 점유/keep-out 불일치 | `owncam_memory_v3.py`의 `blocking_tracks`를 keep-out과 슬롯 게이트에서 공유. `slot_blocking`이면 확률이 시간 감쇠로 낮아지거나 상태가 absent/placed여도 회피 유지 | `test_p1_aged_slot_blocker_stays_in_driving_keepouts` |
| P1 왕복 중 화물 검사 우회 | `owncam_slot_inspection_v3.py`가 outbound/return의 모든 새 RGB에서 기존 `box.decide` → external_navigation carry 검사를 호출. look/팔 전환 프레임도 검사하고 실패·추가 개입 요구 시 다음 이동 전 종료/handoff | `test_p1_inspection_cargo_disappearance_stops_before_next_move[outbound/return]` |
| P2 지도 밖 후퇴점 | `owncam_search_projection_v3.py`가 차체 여유·정적 장애물·자기 관측 keep-out·연결성을 만족하는 가장 가까운 셀로 투영하고 기존 planner로 검증 | `test_p2_blind_search_retreat_is_projected_to_reachable_body_clear_point` |
| 외부 SIM_LIMIT | summary에 pending 슬롯 문맥을 남기고 v3 runner가 외부 종료 이유를 넣어 `result.json`에 저장. SIM_LIMIT 원래 판정 유지 | `test_external_sim_limit_persists_pending_slot_handoff` |

새 회귀 파일 `tests/test_owncam_memory_v3_review3.py`를 CI의 `TEST_PATTERNS`에 등록했다. v3 runner 소스 해시에 공용 충돌 함수와 후퇴점 투영 파일도 넣었다. frozen v2 및 기존 실행/리뷰 기록은 수정하지 않았다. 최신 설계·v3 README·DRAFT만 현재 계약으로 갱신했다.

## EXECFIX가 가져다 쓸 공용 함수

```python
from harness.owncam_sweep_collision import OwnPose, plan_safe_sweep, commands_clear

plan = plan_safe_sweep(static_map, issued_servo, look_pose, requested_pans,
                       OwnPose.from_report(own_pose_report),
                       loaded=loaded, restore=restore_pose)
# plan['pans']가 비면 명시적으로 정지한다. 임의 home pan을 넣지 않는다.
# 명령 직전 현재 자기 추정으로 팔/look batch를 다시 검사한다.
allowed = commands_clear(static_map, issued_servo, commands,
                         OwnPose.from_report(own_pose_report), loaded=loaded)
```

`body_spheres`, 정적 벽/문기둥 입력, `OwnPose`, 구와 벽의 여유 계산은 **499e4fd6의 `harness/zone_own_guards.py`**에서 분리했다. `body_spheres` 본문이 해당 소스와 같음을 확인한다. 당시 `body_model_calibration.json`을 이 폴더에 출처 SHA와 함께 복사 보존했으며 새 보정/물리 측정은 하지 않았다.

기존 모델의 xy/yaw 불확실성 상한 자르기는 제거했다. 60 PWM/tick 전환의 관절 조합 범위를 구의 이동 상한으로 감싸며, 안전 여부가 애매한 범위를 세분화하고 끝까지 불명확하면 거부한다. 따라서 직렬·동시 관절 전환, pan 사이 경로, 각 pan에서 복귀하는 경로를 검사한다. 둘러보기 조기 종료도 안전한 복귀가 있어야 허용한다. 현재 자기 pose가 없거나 모든 pan이 위험하면 `LOOK_COLLISION_UNVERIFIED`/`look_collision_unverified`로 끝난다. 기본 초기화가 불가능한 상황에서 임의로 팔을 휘두르지 않는다.

문 반례 `(2.08, .18, yaw=0)`의 2030 pan에서 0.40 m 벽 여유는 몸체 기하 기준 −27.4569 mm이며, 35 mm 기본/보정 여유를 포함하면 −62.4569 mm다. 문기둥 충돌도 검사했다. 안전 pan이 남는 경우와 열린 공간의 전체 pan 허용을 함께 테스트했다. 수치는 **정적 모델 계산**이며 실제 접촉 깊이가 아니다. EXECFIX 브랜치의 import 이관/abort 연결은 이번 worktree에서 수행하지 않았다.

## 보수적 종료와 데이터 경계

- slot gate와 주행은 같은 `slot_blocking` 관측 기준을 쓴다. 자기 held 및 명시적 제외 대상은 제외한다. 충분한 가시 miss로 차단이 풀려야 keep-out에서도 빠진다. 불확실한 큰 영역 때문에 길이 없어지면 진행하지 않는다.
- 왕복 중 기존 carry의 낙하·가림·anchor drift·낮은 표면의 모호함 등 종료 규칙을 유지한다. 새 프레임마다 한 번만 호출하며 enclosing `pre_release` 스킬은 호출하지 않는다. reference 부재도 명시적 실패다. 현재 RGB가 0.25초보다 오래되면 hold하고 전체 120 SIM s deadline은 계속 적용한다.
- look 중 carry 검사까지 적용하므로 정상 자세 전환을 보수적으로 거부할 수 있다. 실제 새 dev에서 거부율·화물 유지·왕복 가능성을 확인해야 한다. 정적 모델 역시 실제 관절 궤적이나 접촉 측정이 아니다.
- blind-strip 목표 서쪽 0.45 m에서 최대 0.45 m 안의 연결된 셀을 검색하되 기존 점보다 최소 0.10 m 뒤여야 한다. 차체 envelope·여유·대각선 모서리 통과 제한은 기존 planner와 같다. 후보가 없으면 `SEARCH_BLIND_SPOT_UNREACHABLE`; unsafe 목표를 driver에 넘기지 않는다.
- 슬롯 단계/시도/목표/기한/해제 미시작을 pending handoff로 남긴다. v3 runner가 `SIM_LIMIT` 또는 예외로 먼저 끝나도 `external_stop:<outcome>`를 결과에 보존하고 저장 후 result 해시를 기록한다. 이미 더 구체적인 실패 handoff가 있으면 덮어쓰지 않는다. 이는 기존 실행기의 종료 결과 보존이며 실제 LLM 메시지 전송은 아니다.
- 이전 fixture의 **v2 test split s162/s164/s165** 노출 사실과 새 미개봉 seed만 미래 test로 쓰는 정책은 [상위 README](../README.md), [DRAFT](../prereg_DRAFT.json)에 유지한다. 새 테스트도 개발·회귀용이며 v3 재실행 성공 표본으로 세지 않는다.

## 검사 결과

Python `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`.
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1`,
OpenCV GCD는 기존 wrapper의 `setNumThreads(0)` 및 `getNumThreads()==1`, pytest main process 1개.
모든 pytest는 `--basetemp=./.pytest_tmp`를 사용했다.

| 검사 | 결과 |
|---|---|
| runtime 수정 전 핵심 반례 | **7 failed** (`before-corrected-fixture.txt`) |
| 최종 핵심 테스트를 b1eebc0e runtime에 메모리 내 적용 | **7 failed, 14 deselected** (`before-confirmed.txt`) |
| 3차 새 회귀·경계 21개와 기존 v3 회귀 | **137 passed** (`after-boundaries.txt`) |
| 기존 memory/M1/localizer/attachment/v9/map planner/box skill 포함 최종 | **286 passed, 382 subtests passed** (`final-single-thread.txt`) |

`reproduce_baseline.py`는 `git show b1eebc0e:<파일>`로 기준 모듈을 메모리에만 읽으며 checkout/index/소스는 바꾸지 않는다. 위 네 thread 환경변수를 설정해 실행하면 exit 1/7 failed가 기대 결과다.

최종 명령은 기존 `review-fixes/run_review_tests.py -q --basetemp=./.pytest_tmp`에 다음 파일을 넘겼다: `test_owncam_memory_v3_review3`, `test_owncam_memory_v3_review2`, `test_owncam_memory_v3_review`, `test_owncam_memory_v3`, `test_owncam_memory`, `test_m1_owncam`, `test_owncam_localizer`, `test_visual_attachment`, `test_wrist_zone_skill_v9`, `test_map_goto`, `test_visual_box_skill` (모두 `tests/*.py`). 전 프로젝트/원격 CI는 실행하지 않았다.

초기 `before.txt`의 마지막 항목은 fixture의 `skill.events` 누락으로 실패해 반례 근거에서 제외하고, 이를 고친 before 로그를 사용한다. 중간 호환 검사에서 발견한 comprehension 오류와 이전 fixture의 carry reference/관측 시각/분리된 pan stage 가정도 고쳤고 최종 전체를 다시 검사했다. 로그를 덮어쓰지 않고 이 폴더에 모두 보존했다.

## 남은 작업

coordinator의 검토·커밋·원격 CI, EXECFIX의 공용 API import 이관, PR #227 연결, 새 dev에서 충돌 거부·실제 통과·화물 유지·슬롯 관측/복귀 검증이 남는다. DRAFT는 실행 허가가 아니며 새 코호트는 소스·조건·새 seed를 동결한 뒤 등록한다. 이번 변경의 TensorBoard 실험 결과는 없다. `gh pr list`는 네트워크 오류로 확인하지 못했고, `.git` 쓰기 금지에 따라 fetch/commit은 하지 않았다.

## 참고 자료

- 제공된 `codex-234-review3.md` 전체: 원문 경로/SHA-256은 `verification.json`.
- `499e4fd6445614a8b647eaea11f7bb9c77e5e2bd:harness/zone_own_guards.py`, 당시 `experiments/2026-09-26-zone-own-executor/body_model_calibration.json`.
- [현재 설계](../../../docs/design/2026-09-27-owncam-memory-v3.md), [2차 수정 기록](../review2-fixes/README.md). 이전 로그는 당시 구현의 기록이다.
- `harness/map_goto.py`, `harness/visual_box_skill.py` 및 `harness/wrist_zone_skill.py`의 기존 planner/carry 검사. 원본 코드는 변경하지 않았다.
