# pairact P2 -c4 pilot(8343000–039) 실패 회수·원인표 (DeepSeek 실행, Claude 분석)

라벨: *teacher 수율 확인*. 학습 결과도 수집 데이터도 아닙니다. 원본 run은 읽기만 하고, 복사본만 분석합니다.
보고 수치(STATUS 10/21 19:55 KST): 26/40, 파지 37/40(A 11·B 15는 두 절반의 성공 수로 보입니다 [확인 필요]), HOST_ERROR 0, cap_end 2, route_blocked 8, drop 1, not_in_zone 1.
산수 확인: 실패 14 = 파지 실패 3 + 운반 실패 11입니다. 보고된 코드는 2+8+1+1 = 12라서 *2건이 비어 있습니다*(파지 실패 1, 운반 실패 1로 추정 [확인 필요]). 이 스크립트가 world별로 채웁니다.

## 1. 회수 (gcp6 → Oracle, CPU만, GPU 0)

원본 경로는 Slack 보고에 없습니다. C4_RUN.md §3 규칙대로라면 `/home/ugrp/ugrp-sim/runs/pairact-p2-c4-<UTC>/pilot-8343000*`입니다. 20+20으로 나눴다면 out 디렉터리가 2개입니다. 둘 다 회수합니다.

```bash
VM=ugrp-act-l4-gcp6; P=ugrp-sim-f-1016; Z=asia-northeast3-a
gcloud compute instances start $VM --project $P --zone $Z            # lease 1개, 끝나면 stop
gcloud compute ssh $VM --project $P --zone $Z --command 'sudo bash -s' <<'EOF'
set -euo pipefail
ls -d /home/ugrp/ugrp-sim/runs/pairact-p2-c4-*/pilot-8343000* | tee /tmp/pilot-dirs.txt     # 경로를 보고에 그대로 적습니다
rm -f /tmp/pilot-8343000-analysis.tar
while read -r d; do
  base=$(dirname "$d"); name=$(basename "$d")
  files=$(cd "$base" && ls -d "$name"/{summary.json,progress.json,rejection_table.json,artifact-sha256.json} \
          "$name"/world-*/raw/{result.json,carry-route.json,carry-eval.json,eval-only.jsonl,start-protocol.json,manifest.json}{,.zst} 2>/dev/null || true)
  tar -C "$base" -rf /tmp/pilot-8343000-analysis.tar $files
done < /tmp/pilot-dirs.txt
chmod 644 /tmp/pilot-8343000-analysis.tar; sha256sum /tmp/pilot-8343000-analysis.tar; du -h /tmp/pilot-8343000-analysis.tar
EOF
DST=/home/ubuntu/UGRP/outputs/pairact-p2-c4-pilot-fetch-$(date -u +%Y%m%dT%H%MZ); mkdir -p $DST
gcloud compute scp --project $P --zone $Z $VM:/tmp/pilot-8343000-analysis.tar $DST/
gcloud compute ssh $VM --project $P --zone $Z --command 'rm -f /tmp/pilot-8343000-analysis.tar /tmp/pilot-dirs.txt'
gcloud compute instances stop $VM --project $P --zone $Z
sha256sum $DST/pilot-8343000-analysis.tar      # VM 쪽 sha와 같아야 합니다
mkdir $DST/x && tar -C $DST/x -xf $DST/pilot-8343000-analysis.tar
```

- 40 world 전부 회수합니다(성공 world도 시작 틈 분포 비교에 씁니다). `eval-only.jsonl`은 `compress_logs`가 `.zst`로 줄였을 수 있습니다. 둘 다 glob에 넣었습니다.
- `carry-route.json`이 *하나도 없으면* 그 pilot은 `straight_v1`(cases `--to pairact_p2_r13`)로 돈 것입니다. -c4는 opt-in route 모드에서만 이 파일을 씁니다. 이 경우 `route_blocked 8`은 우회 탐색을 아예 하지 않은 결과입니다. 반대로 `detour_v1`로 돌았다면 교사 outcome은 `route_blocked`가 될 수 없고 `route_blocked_no_path`여야 합니다(`PairCarryTeacherWarp.__init__`). 보고의 `route_blocked`가 어느 쪽인지 [확인 필요]이고, 아래 표가 world별로 가립니다.
- 다른 run 파일과 VM 설정은 건드리지 않습니다. 비용은 boot+scp 약 10분, $0.2 이하로 봅니다 [확인 필요].

## 2. 원인표 (Oracle CPU)

```bash
cd /home/ubuntu/UGRP-wt/pilot-analysis      # dsh/pairact-pilot-analysis
for d in $DST/x/pilot-8343000*; do RUNS="$RUNS --run $d"; done
/home/ubuntu/ugrp-e1-venv/bin/python scripts/analyze_pairact_pilot.py $RUNS --verify --out $DST/analysis
# 경로 재생: -c6 teacher(detour_v2)까지 같이 돌릴 때
/home/ubuntu/ugrp-e1-venv/bin/python scripts/analyze_pairact_pilot.py $RUNS --verify --replay \
    --teacher-src /home/ubuntu/UGRP-wt/p2c6 --replay-modes detour_v1,detour_v2 --out $DST/analysis-replay
```

출력: `pilot-analysis.json`(world별 레코드, `verify` 결과, 요약), `pilot-analysis.md`(원인표, 재생표).

| 분류(`category`) | 원인(`cause`) 형식 | 근거 코드 |
|---|---|---|
| `grasp` | `grasp_cap_end` 또는 `grasp_teacher:<outcome>` | root `run_warp_flow_teacher.py`: `cap_end = not success and sim_s >= cap_s(60)`. smoke(녹화 off)에서 `success`는 *파지 관문*이므로 root `cap_end`는 파지 실패만 셉니다 |
| `route` | `<code>[:<search reason>]@<segment>/<hit kind>` | teacher `__init__`: `route_blocked`(straight_v1, 두 직선 변형 모두 막힘), `route_blocked_no_path`(detour_v1, A* 실패: `start_in_collision`/`exhausted`/`node_budget`/`final_check`) |
| `carry_teacher` | `<code>@<phase>` | `step()`: `carry_hold_lost`, `formation_stretch`, `formation_tracking_lost`, `carry_total_timeout`, 단계별 `*_timeout` |
| `eval` | `drop:<kind>@<phase>` 또는 `<failure>(teacher=<outcome>)` | `pair_carry_eval.evaluate`: `drop`(carry_low/tilt/fall) > `robot_robot_contact` > `not_through_door` > `not_in_zone` > `not_resting` > `not_released` > `not_still` |
| `host_error` | error_type | root summary |

- route 실패 world의 운반 evaluator failure는 거의 항상 `not_through_door`입니다(운반 0 m). 그래서 Slack 보고의 `route_blocked`는 교사 outcome이고, `drop`·`not_in_zone`은 evaluator failure입니다. 두 어휘가 섞여 있으니 표에서는 `category`로 나눕니다.
- `--replay`: `eval-only.jsonl`에서 handover 행(`carry.events[0].t` 이후 첫 행)을 찾아, VM과 같은 `carry_obstacles`로 물체 원을 다시 만들고 경로 계획기만 다시 돌립니다. 시작 틈(`formation_clearance`), 벽만 고려한 틈, 가장 가까운 물체, west staging 회전 위치 틈, 직선 막힘이 기록과 같은지(`matches_record`), 모드별 결과를 냅니다. `matches_record=false`이면 재생이 VM과 다르다는 뜻이므로 그 world의 재생 결과는 쓰지 않습니다.
- 재생이 보여 주는 것은 *계획기가 경로를 찾는지*뿐입니다. 실제 주행 성공은 GPU A/B로만 판정합니다.
