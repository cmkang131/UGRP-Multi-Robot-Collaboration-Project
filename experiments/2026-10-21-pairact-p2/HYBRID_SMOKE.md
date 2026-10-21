# hybrid 코드 운반 smoke: teacher 근거리 + 코드 운반 + teacher 하차 (학습 아님)

라벨: *teacher 근거리 + 코드 운반, 학습 아님*. 학생 정책은 돌지 않습니다. GT teacher가 공동 파지·3초 유지와 하차를 하고, 그 사이 운반·문 통과만 hybrid 코드(nav 방식: 자기 카메라 zone B 검출 + 자기 오도메트리, 정적 지도 없음)가 맡습니다.
목적: 코드 운반 경로가 *실제 GPU(MJWarp)에서* 문을 지나 zone B까지 가는지, 그리고 HYBRID_RUN.md §8의 위험 2·3(빔 가림, 문 검출기 없음)과 적재 자세 카메라 투영이 실제로 문제인지 smoke 결과로 판단합니다. 관문도 성공률 근거도 아닙니다.
실행한 것은 CPU 단위 테스트뿐입니다. 이 경로를 GPU에서 돌린 적은 없습니다.

## 0. 규칙
- 오프피크(UTC 16:30–00:30), gcp6 하나(새 VM 금지), 새 run root, 끝나면 VM 정지. 런당 $20 이하.
- *결과 미합산*: smoke의 n/N은 arm F·arm N·teacher P2/P3 어떤 결과와도 합산하지 않습니다. 보고는 world별 한 줄 + n/N.
- seed: smoke world 1·11·17(r13 cases, seed 8420001·8420011·8420017)과 pilot 8343000–8343009(10개). 학습·검증·보류 seed는 쓰지 않습니다.
- 운반 config의 보정값은 `fit_loaded_odom.py` 출력으로만 채웁니다(§2). 손으로 고친 값은 teacher가 거부합니다(`values_sha256`).
- 재실행 1회까지. 두 번째도 HOST_ERROR면 멈추고 Claude 리뷰를 요청합니다.

## 1. 스택 (`--hybrid-smoke`일 때만, 기본 경로는 -c5 그대로)
| tree | 브랜치 | SHA |
|---|---|---|
| root | `dsh/pairact-p2-carrypath-r-c5-hybrid2` | 이 문서가 든 커밋 |
| adapter | `dsh/pairact-p2-carrypath-a-c5-hybrid2` | `0479e7b47c87e0a5af7158015d011d98ca5df449` |
| teacher(runner) | `dsh/pairact-p2-carrypath-c5-hybrid2` | `c51f3e7c2cd419c3fe9ef4199481ffc1c5f74fea` |
| nav 검출기 | `dsh/nav-v5-recal` | `ceacd474b9e03110c1b35c0cd0fc2cca40594ec9` |

- 학생 worker는 쓰지 않습니다(`--student-eval`·`--hybrid-carry`와 같이 주면 root가 거부).
- teacher -c5-hybrid2 = -c5-hybrid + 적재 오도메트리 보정 v2(이득·지연·편향 + 출처 검사) + `run(hybrid_smoke=...)` + eval-only 로그 + 도구 3개(`scripts/fit_loaded_odom.py`, `scripts/make_hybrid_config.py`, `scripts/summarize_hybrid_smoke.py`). gate 경로 바이트 동일 테스트가 smoke 삽입 조각만 허용합니다.
- cases의 candidate는 `pairact_p2_r13`(GT 운반 on)이어야 합니다. smoke 모드에서는 GT 운반 teacher의 경로 계획을 쓰지 않으므로 `_detour`가 아니어도 됩니다.

## 2. 보정 config 만들기 (Oracle CPU, GPU 0)
입력: C4 pilot 회수본(`PILOT_ANALYSIS.md` §1, `outputs/pairact-p2-c4-pilot-fetch-<UTC>/x/pilot-8343000*`)과 P2 smoke-1c(`/home/ugrp/ugrp-sim/runs/pairact-p2/smoke-1c`, 같은 방식으로 `summary.json`, `world-*/raw/{result.json,carry-eval.json,eval-only.jsonl}{,.zst}` 회수 [확인 필요: smoke-1c 회수 경로]).
```bash
T=/home/ubuntu/UGRP-wt/p2c5-hybrid2         # teacher c51f3e7c (fit 도구가 이 tree의 운반 teacher를 offline 재실행)
PY=/home/ubuntu/ugrp-e1-venv/bin/python
RUNS=""; for d in $DST/x/pilot-8343000* $SMOKE1C; do RUNS="$RUNS --run $d"; done
$PY $T/scripts/fit_loaded_odom.py $RUNS --out $OUT/fit          # loaded-odom-fit.{json,md}; stdout: fit_sha256, values_sha256
$PY $T/scripts/make_hybrid_config.py --fit $OUT/fit/loaded-odom-fit.json \
  --template $T/experiments/2026-10-21-pairact-p2/HYBRID_CARRY_NAV_TEMPLATE_V2.json \
  --purpose teacher_smoke --expect-fit-sha256 <위 fit_sha256> --out $OUT/hybrid-smoke.json \
  --set nav.source=/home/ugrp/ugrp-sim/src/pairact-hybrid2/nav \
  --set nav.profile=<❗> --set nav.arm_ground_m=<❗> --set nav.advance_m=<❗> \
  --set limits.carry_budget_s=<❗> --set limits.sigma_xy_max_m=<❗> --set limits.sigma_yaw_max_deg=<❗>
```
- fit은 world마다 기록된 GT row 위에서 GT 운반 teacher를 다시 돌려 tick별 바퀴 명령을 복원합니다. 경로·단계 events·`drive_response`가 VM 기록과 *모두 같을 때만* 그 world를 씁니다. 다르면 `excluded: replay_differs_from_record`로 남깁니다. `eval-only.jsonl`이 없는 world는 `no_per_tick_source`로 제외합니다(집계값만으로는 전진·횡·회전을 나눌 수 없어 적합하지 않습니다).
- pilot·smoke 밖의 seed가 하나라도 있으면 `SEED_NOT_ALLOWED`로 멈춥니다. fit에 쓴 seed는 config `calibration_provenance.seeds`에 남고, teacher가 다시 검사합니다.
- 결과 해석: `loaded-odom-fit.md`의 지연 tick 표(정규화 잔차), 축별 R², world별 drift. 축별 R²가 0.5 미만이면 보정이 불안정한 것이므로 smoke 전에 Claude에게 넘깁니다.
- ❗ 결정 필요(Claude 본체, 실행 전): owner 값 6개. 측정값이 아니라 정책값이라 이 도구가 채우지 않습니다.

| 키 | smoke 후보값 | 근거 |
|---|---|---|
| `nav.profile` | [확인 필요] | nav v5 recal Step1 결과(gcp2 worker `95e34ef8`)로 고정. 결과 전이면 smoke를 미룹니다 |
| `nav.arm_ground_m` | 0.9 [확인 필요] | teacher 단위 테스트 고정값이고 유도 근거는 없습니다. navigator는 빔 끝에서 빔 쪽을 보므로 zone까지의 거리와 빔 중심의 zone 안 위치 관계가 단독 nav와 다릅니다. smoke의 `projection`·`gt_beam_pose`로 다시 정합니다 |
| `nav.advance_m` | 0.45 [확인 필요] | 같음(테스트 고정값). smoke 결과로 `zone_inside_final`이 false인 world의 최종 빔 위치를 보고 다시 정합니다 |
| `limits.carry_budget_s` | 110 | runner `carry_cap_s`(110)와 같게 |
| `limits.sigma_xy_max_m` | 0.5 | smoke는 drift를 관찰하는 것이 목적이라 느슨하게 둡니다. P5용 값은 smoke drift 결과로 따로 정합니다 |
| `limits.sigma_yaw_max_deg` | 15 | 같은 이유. CPU 자기 센서 운반 0/33은 3° 게이트에서 끝났습니다 |

## 3. 실행 (gcp6, 오프피크)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-hybrid2; RUN=/home/ugrp/ugrp-sim/runs/pairact-hybrid-smoke-$(date -u +%Y%m%dT%H%MZ)
for t in root:origin/dsh/pairact-p2-carrypath-r-c5-hybrid2 adapter:0479e7b47c87e0a5af7158015d011d98ca5df449 \
         teacher:c51f3e7c2cd419c3fe9ef4199481ffc1c5f74fea nav:ceacd474b9e03110c1b35c0cd0fc2cca40594ec9; do
  git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/${t%%:*} ${t#*:}      # 레포 경로는 SMOKE.md §2와 같음 [확인 필요]
done
cd $SRC/teacher && python -m pytest -q tests/test_hybrid_carry.py tests/test_hybrid_smoke.py tests/test_fit_loaded_odom.py   # 기대 39 passed
cd $SRC/root && python -m pytest -q tests/test_pairact_p2_root.py                                                         # 기대 이 브랜치 커밋 메시지의 수
scp/복사: $OUT/hybrid-smoke.json → $RUN/hybrid-smoke.json (커밋된 config, sha256 기록)

# A) smoke world 1·11·17 (r13 cases에서 pairact_p2_r13로 뽑은 기존 p2-smoke-cases.json)
cd $SRC/root
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases /home/ugrp/ugrp-sim/runs/pairact-p2/p2-smoke-cases.json --indices 0,1,2 \
  --cap-s 60 --out $RUN/smoke-A --vm-hourly-usd 1.096 \
  <SMOKE.md §3의 physics/contact/scene/refs/rejection 플래그 그대로> \
  --hybrid-smoke $RUN/hybrid-smoke.json

# B) pilot 8343000–009: SEED_REFS.md의 e 단계를 --to pairact_p2_r13로 다시 만든 cases(--n 10)
python experiments/2026-10-21-pairact-p2/make_p2_cases.py --seed-start 8343000 --n 10 \
  --seed-cases <wide-start-8343000/wide-cases.json> --seed-refs-manifest <seed-refs-8343000-manifest.json> \
  --to pairact_p2_r13 --out $RUN/pilot10-cases.json
python .../run_warp_flow_teacher_gcp6.py ... --cases $RUN/pilot10-cases.json --indices 0,...,9 --out $RUN/pilot-B \
  <manifest의 canonical-xml·refs·rejection 3경로> --hybrid-smoke $RUN/hybrid-smoke.json
```
- [확인 필요] gcp6 wrapper가 `--hybrid-smoke`를 그대로 넘기는지. 판정: `summary.json`의 `hybrid_smoke.label`이 `teacher 근거리 + 코드 운반, 학습 아님`이고 `source_sha`가 root SHA와 같아야 합니다. 아니면 그 실행은 무효입니다.
- A가 HOST_ERROR 없이 끝나고 world 하나 이상에서 `hybrid-drive.jsonl`이 생기면 B로 갑니다. A에서 3 world 모두 `abort:zone_not_found`이면 B를 돌리지 않고 §6으로 갑니다.

## 4. 예상 시간·비용
| 묶음 | world | 최대 SIM | 근거 | 예상 wall | 비용(L4 $1.096/h) |
|---|---|---|---|---|---|
| A | 3 | 170 s/world(파지 cap 60 + 운반 110) | -c4 실측: 3 world 1.30 s/tick(STATUS 10/21) | 약 37 min + 코드 구간 카메라 캡처 2장/tick 추가분 [확인 필요] → 0.6–0.9 h | 약 $0.7–1.0 |
| B | 10 | 같음 | 0.34 s/tick/world 직렬(20 world 6.8 s/tick) → 10 world 약 3.5 s/tick | 1700 tick × 3.5 s ≈ 1.65 h, 캡처 추가분 포함 1.7–2.5 h | 약 $1.9–2.8 |
| 준비(boot, worktree, 회수) | — | — | PILOT_ANALYSIS 회수 실측 약 10 min | 0.3 h | 약 $0.3 |
| 합계 | 13 | | | *약 2.6–3.7 GPU-h* | *약 $3–4 (런당 $20 이하)* |
- 실측 wall·비용을 summary와 함께 보고합니다. 3.7 h를 넘기면 B를 중간에서 멈추지 말고 끝까지 돌린 뒤 실측을 남깁니다(부분 결과로 판정하지 않기 위해).

## 5. 볼 것
```bash
python $SRC/teacher/scripts/summarize_hybrid_smoke.py --run $RUN/smoke-A --run $RUN/pilot-B --out $RUN/report   # Oracle 회수 뒤에도 같음
python $SRC/teacher/scripts/fit_loaded_odom.py --run $RUN/smoke-A --run $RUN/pilot-B --out $RUN/fit2           # smoke의 코드 명령으로 다시 적합(P5 hybrid_n용)
```
| 파일 | 내용 |
|---|---|
| `world-00k/raw/hybrid-drive.jsonl` | 코드 구간 tick별 `segment`, `planner_phase`, 적용한 바퀴 명령(fit 입력), `zone_seen`, `zone_point`, `eval_only{gt_beam_pose, gt_robot_pose, camera_mount, projection, occlusion}` |
| `world-00k/raw/result.json` → `hybrid_smoke` | HybridRun 감사(I10): `outcome`, `code_segment_s`, `gt_inputs_to_code = 0`, `near_field = teacher`, `handback_sim_s`, `calibration_values_sha256`, planner·sync 이벤트, 오도메트리 누적 |
| `→ carry` | `mode = hybrid_smoke`, `code_outcome`(`handed_back` 또는 `abort:*`), `place_teacher`(하차 teacher 진단) |
| `world-00k/raw/carry-eval.json` | handover부터 끝까지 GT evaluator 1회(`setdown_boundary = hybrid_smoke_handback_v1`), funnel(`door_passed`, `zone_inside_final`, …), `code_drive_response`·`place_drive_response`(eval-only) |
| `report/hybrid-smoke-summary.md` | world별 표: 코드 결과, 문 통과, zone, 성공/실패, 카메라 높이·피치, 투영 오차, acquire 단계 zone 검출률·GT 가시율·빔 가림 |

## 6. 판단 규칙 (실행 전 고정)
- *코드 운반 경로 동작*: 파지가 된 world 중 `code_outcome = handed_back`이고 evaluator `door_passed = true`인 world 수 n/N. N = 파지 성공 world 수(파지 실패는 운반 미시작으로 따로 셉니다).
- *문 검출기 없음 위험(§8-3)*: `door_passed = false`인 world를 `code_outcome`으로 나눕니다. `handed_back`인데 문을 못 지났으면(zone을 문 너머로 보고 벽 앞에서 도착 판정) 문 검출기가 필요하다는 근거입니다. `abort:zone_lost`·`abort:code_carry_timeout`이 문 앞에서 났는지는 `hybrid-drive.jsonl`의 `gt_beam_pose`로 봅니다. 파지 world의 절반 이상이 이 유형이면 문 검출기(또는 문 성분 겨냥)를 다음 후보로 올립니다.
- *빔 가림 위험(§8-2)*: acquire 단계에서 GT 가시율 중앙값 < 0.5이거나 빔 가림 중앙값 > 0.5이고 그 world가 `abort:zone_not_found`이면 빔 가림이 원인입니다. GT 가시율은 높은데 `zone_seen` 비율이 낮으면 검출기 profile 문제로 봅니다.
- *적재 자세 투영*: `projection_error_m` 중앙값 > 0.10 m이거나 카메라 높이 차 > 0.03 m·피치 차 > 3°이면 arming 거리(`arm_ground_m`)가 틀린 것입니다. 이 경우 적재 자세 투영을 nav 투영에 별도 프로필로 넣는 후보를 올립니다(측정값 = eval-only 로그, 실행 중 입력 아님).
- smoke 결과로 config 값을 바꾸면 새 후보이고, 다른 world 집합에서 다시 확인합니다. smoke world를 P5 보류 seed 판정에 쓰지 않습니다.

## 7. 막히면
- `SEED_NOT_ALLOWED`·`NO_FIT_DATA`·`FIT_FAILED`(§2): 회수 파일 목록과 fit 출력의 `excluded`를 첨부해 Claude에게 넘깁니다.
- `ValueError ... values_sha256`: config를 손으로 고친 경우입니다. §2를 다시 실행합니다.
- `camera_unavailable_ticks > 0`: MJWarp world에서 `world.data.cam_xpos/cam_xmat`을 못 읽은 것입니다. 운반 판정은 유효하고 투영·가림 측정만 빠집니다. 로그를 첨부합니다.
- HOST_ERROR: 로그·`progress.json` 보존, 1 world(`--indices 0`)로 1회만 다시 봅니다.
