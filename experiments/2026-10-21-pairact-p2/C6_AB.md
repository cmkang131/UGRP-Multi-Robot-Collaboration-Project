# pairact P2 -c6 후보 A/B (DeepSeek 실행 · teacher 수율 확인 · 학습 아님 · 수집 데이터 아님)

근거: `outputs/reports/claude-arch-parallel-20261019/t1-pilot-failure-analysis.md`. -c4 pilot(8343000–039)은 26/40이었고, 운반 실패 11 중 8이 경로 계획(`route_blocked`) 실패였습니다.

## 1. 스택

| tree | 브랜치 | SHA |
|---|---|---|
| teacher | `dsh/pairact-p2-carrypath-c6` | `a3cb7ffdf4a31b32685be98f1eda178b4900730e` (= -c5 + `detour_v2` opt-in) |
| adapter | `dsh/pairact-p2-carrypath-a-c6` | `952e06d3f90242cecf824448e9959433490eeb0b` |
| root | `dsh/pairact-p2-carrypath-r-c6` | 이 문서가 든 커밋 |
| 분석 | `dsh/pairact-pilot-analysis` | `scripts/analyze_pairact_pilot.py`, `PILOT_ANALYSIS.md` |

| 후보(adapter) | 바뀐 것 | 대상 실패 |
|---|---|---|
| `pairact_p2_r13_detour` (-c4 기준선) | detour_v1 | — |
| `pairact_p2_r13_detour2` (**c6-1, 1순위**) | `carry_route=detour_v2`: 시작 틈 탈출 + 물체 고려 west staging 목표 여러 개 + heading 16 | route 8 |
| `pairact_p2_r13_detour2_floor` (**c6-2, 2순위**) | 위 + 기존 `floor_contact_v1` 하강 | not_in_zone 1, drop 1(하강 구간일 때만) |

수집 후보(`pairact_p3_collect`, `pairact_p3_collect_detour`)와 수집 사전 등록(`dsh/pairact-carry-r1-v3-shard`)은 바꾸지 않았습니다.

## 2. 순서

0. *(CPU, 필수 관문)* `PILOT_ANALYSIS.md` §1로 -c4 pilot 파일을 회수하고 §2의 `--replay --teacher-src <c6 teacher> --replay-modes detour_v1,detour_v2`를 돌립니다.
   - route 실패 world 중 `matches_record=true`이고 `detour_v2`가 경로를 찾는 수를 `k/8`로 기록합니다.
   - *k < 3이면 GPU arm을 돌리지 않고* Claude에게 넘깁니다. 이때는 원인이 하류 막힘이나 물체 배치라서 후보 c6-3(아래 §4)이 필요합니다.
1. *(gcp6, 오프피크)* 설치·테스트:
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p2-c6; RUN=/home/ugrp/ugrp-sim/runs/pairact-p2-c6-$(date -u +%Y%m%dT%H%MZ)
for t in teacher:a3cb7ffdf4a31b32685be98f1eda178b4900730e adapter:952e06d3f90242cecf824448e9959433490eeb0b root:origin/dsh/pairact-p2-carrypath-r-c6; do
  name=${t%%:*}; rev=${t#*:}; git -C /home/ugrp/ugrp-sim/ugrp fetch -q origin; git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/$name $rev
done
cd $SRC/teacher && $PYW -m pytest -q tests/test_pair_carry_teacher_warp.py tests/test_pair_carry_detour.py tests/test_pair_carry_route_c4.py tests/test_pair_carry_detour_v2.py   # 기대 86 passed
cd $SRC/adapter && $PYW -m pytest -q tests/test_pairact_p2_adapter.py                                                                                       # 기대 10 passed
cd $SRC/root    && $PYW -m pytest -q tests/test_pairact_p2_root.py tests/test_pairact_p2_runtime_pins.py tests/test_pairact_p2_seed_refs.py                   # 기대 39 passed
```
2. cases: -c4 pilot과 *같은* seed refs manifest(8343000, 40)로 `make_p2_cases.py --seed-start 8343000 --n 40 --seed-cases … --seed-refs-manifest … --to pairact_p2_r13_detour2 --out $RUN/p2-seed8343000-detour2-cases.json`. refs는 새로 만들지 않습니다. `plan`과 `indices`는 -c4 pilot cases와 같아야 하고, `candidate`만 달라야 합니다(`jq` 비교 결과를 보고에 붙입니다).
3. 실행: C4_RUN.md §3-3과 같은 명령에서 `--adapter-source/--teacher-source`=`$SRC/...`, `--cases`=2의 결과, `--out $RUN/ab-detour2`만 바꿉니다. 녹화는 없습니다. `--initialize-only` + `check-init`을 먼저 돌립니다.
4. c6-2(`..._detour2_floor`)는 0단계 표에서 not_in_zone·drop world가 하강 이후(`lower`/`open`/`raise`/`retreat`)에 실패했을 때만 같은 방식으로 돌립니다. 운반 중 실패였다면 돌리지 않습니다.
5. 분석: `analyze_pairact_pilot.py --run $RUN/ab-detour2 …`으로 같은 표를 만들고 -c4 표와 world별로 나란히 둡니다.

예상 비용: -c4 pilot 실측은 3h18m에 약 $3.61이었습니다. arm 하나도 같은 규모로 봅니다. 두 arm이면 약 6.6 h, $7.2입니다 [확인 필요]. $20/런 기준 안입니다.

## 3. 사전 등록(실행 전 동결, 1회 판정)

- 비교 단위: 같은 seed 8343000–039, 같은 refs, 같은 r13 파지 프로필. 1차 지표는 `carry_success` n/40입니다. 기준선은 -c4 `pairact_p2_r13_detour` 26/40입니다.
- 채택 기준: (a) n ≥ 29/40(+3), (b) 기준선에서 성공한 world 중 새로 실패한 world ≤ 1, (c) HOST_ERROR 0, (d) 파지 성공 수가 기준선 ±1 안. 파지 단계는 바뀌지 않았으므로 (d)가 깨지면 결정성 문제로 보고 판정을 보류합니다. 샤딩 결정성 smoke 결과와 대조합니다.
- 보조 지표: route 실패 수, `plan_wall_s` 최대값(detour_v2 상한은 노드 60000이고, 로컬 Python 기준 최악 약 90 s로 추정 [확인 필요]), drop·not_in_zone 수.
- 확인 run: 채택 시 새 seed 40(8345000–039, refs 새로 생성)에서 1회 확인합니다. 패자 arm도 기록합니다.

## 4. 남은 후보 (구현 안 함, 0단계 결과에 따라)

- c6-3 *하류·물체 배치 우회*: route 실패가 `downstream_blocked`(문 진입 차로나 동쪽 구간이 물체·r3에 막힘)이면 east 구간에도 같은 A*를 쓰거나 r3를 경로 밖 대기 위치로 미리 보내야 합니다. 0단계에서 원인이 이쪽으로 확인되면 구현합니다.
- *실행 중 후진 후 재계획*: 시작 틈이 −3 cm보다 깊게 겹치는 `start_in_collision`이 많으면 실제로 물러난 뒤 다시 계획해야 합니다. 정적 탈출(c6-1)로 풀리지 않을 때만 엽니다.
