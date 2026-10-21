# pairact P2 -c3: 운반 첫 구간 우회 탐색 (carry_route detour_v1, opt-in)

원인: smoke-1c world-000(seed 8420001, r13 case 1) handover 직후 `to_west_staging`(빔 (1.549, 0.659) → west staging (1.25, −2.425))에서
formation이 경로 46.8% 지점에서 GT 물체 원과 겹쳐 `route_blocked`. 교사는 직선 2변형(translate-first / rotate-first)만 시도했습니다
(`outputs/pairact-world1-recovery-20261021/world1-fields.json`).

| tree | 브랜치 | SHA | 바뀐 것 |
|---|---|---|---|
| teacher | `dsh/pairact-p2-carrypath-c3` | `dbc08211c776117dddff7f3fec05f7327ba497a3` | `carry_route` (`straight_v1` 기본 / `detour_v1`). 두 직선 변형이 모두 막힐 때만 첫 구간을 formation 격자 A*(0.05 m, heading 8개, 제자리 회전만)로 우회. 최종 경로는 기존 `segment_clear`로 재검증. 실패 코드 `route_blocked_no_path`. runner `--carry-route` |
| adapter | `dsh/pairact-p2-carrypath-a-c3` | `30dbc689b8e681d87881d1338693cced04f9d7b4` | 후보 `pairact_p2_r13_detour`(= P2 + `carry_route=detour_v1`), `pairact_p3_collect_detour`(같은 프로필 + 기존 collect 녹화·승인 경로) |
| root | `dsh/pairact-p2-carrypath-r-c3` | 이 문서가 든 커밋 | pin 2줄 + `make_p2_cases.py --to` (기본값 그대로) |

- `straight_v1`(기존 후보 전부): 경로·`route_info`·diagnostic 바이트 동일(teacher `tests/test_pair_carry_detour.py`). `result.json`에 `carry_route` 키는 opt-in 때만 생깁니다.
- `detour_v1`이어도 직선(또는 rotate-first)이 통하면 기존 경로 그대로입니다. 우회가 쓰이면 `route_info.variant='detour'`, `route_info.detour.{waypoints,nodes_expanded,min_clearance_m,search}`, `route_info.straight_blocked`가 남습니다.
- [확인 필요] world 1 물체의 GT 좌표는 회수 파일에 없어, 기록된 첫 충돌(('object', 0.4677))을 정확히 재현하는 원(반지름 0.12 m)으로 재구성해 테스트했습니다. 실제 배치에서 경로가 찾아지는지는 pilot이 확인합니다.
- [확인 필요] world 11·17의 handover 자세는 레포에 없어 "바이트 동일"은 합성 자세 4개 + 기존 rollout 테스트로 고정했습니다. 실제 11·17은 pilot에서 smoke-1c 결과의 `carry.route`와 비교합니다.
- `pairact_p3_collect`(기존 수집 후보)는 바꾸지 않았습니다(FROZEN 사전등록이 P2 프로필 기준). 우회가 들어간 수집은 `pairact_p3_collect_detour`입니다.

## pilot (gcp6, 오프피크)

SMOKE.md §2–3과 같고 SHA·cases·out만 바꿉니다.

```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p2-c3; RUN=/home/ugrp/ugrp-sim/runs/pairact-p2
for t in teacher:dbc08211c776117dddff7f3fec05f7327ba497a3 adapter:30dbc689b8e681d87881d1338693cced04f9d7b4 root:origin/dsh/pairact-p2-carrypath-r-c3; do
  name=${t%%:*}; rev=${t#*:}; git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/$name $rev
done
git -C $SRC/root rev-parse HEAD        # ROOT_SHA
cd $SRC/teacher && python -m pytest -q tests/test_pair_carry_teacher_warp.py tests/test_pair_carry_detour.py   # 기대: 65 passed
cd $SRC/adapter && python -m pytest -q tests/test_pairact_p2_adapter.py                                       # 기대: 9 passed
cd $SRC/root    && python -m pytest -q tests/test_pairact_p2_root.py                                          # 기대: 12 passed
cd $SRC/root && python experiments/2026-10-21-pairact-p2/make_p2_cases.py --to pairact_p2_r13_detour \
  --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json \
  --out $RUN/p2-detour-cases.json
# 실행: SMOKE.md §3 명령에서 --adapter-source/--teacher-source=$SRC/..., --cases $RUN/p2-detour-cases.json, --out $RUN/detour-pilot-1
```

판정: world 1 `carry.outcome`이 `route_blocked`가 아니고(`command_sequence_complete` 또는 다른 단계 코드), `route_info.variant`가
`detour`, `carry_eval.wall_contact_ticks`·`robot_robot_contact_ticks` 기록. world 11·17은 `carry.route`가 smoke-1c와 같아야 합니다.
