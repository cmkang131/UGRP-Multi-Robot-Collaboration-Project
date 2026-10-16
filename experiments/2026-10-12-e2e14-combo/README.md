# E2E 14차 짝 비교 (DEV, PR #446)
- 8회: A(v202)와 B(12차 A + 공통 속도 옵션, v200), seed 61001–61004.
- 양쪽 모두 정확 속도 토글 5개 ON; A/B 원래 다섯 설정 차이 유지.
- 실행당 25,200 wall초, 1,800 SIM초; VM1 유휴 20분·8시간 가드.
- 종료조건: 같은 실행에서 정상 LLM 응답·자기 지도 경로 생성·평가된 시작→끝 운반.
- 첫 5분 운영 점검 후 30분 간격 평가 전용 관찰; 제어 개입 없음.
- 원본 VM1 영속 디스크→ARM 해시 검증; Mac은 이미지 없는 경량 회수.
- 진행·모든 실패·해시: summary.json; 실행 전 구성 설명: PREPARATION.md.
- DEV 비교이며 토글별 인과 분리·정식 연구 성공률 근거 아님.

## 다음 짝 실행 e2e15: v205(rgb_vo_v2 조합) 대 12차 A(v199) — 실행 명령만, 아직 실행 안 함
- A `e2e-combo14-vo2-v205`(7.98.0) = v204 조합에서 VO만 `rgb_vo_v2`(VO → 불가 시 펄스 게이트 정지 판정 → 그것도 불가면 명령). B `e2e-stall-budget-v199`(7.92.0) = 12차 A. 양쪽 모두 정확 속도 토글 off(v199와 같게). seed 61001–61003 × A/B = 6개 동시, 실행당 wall 25,200 s(7 h), 사례 1,800 SIM s.
- 주의: 저장 프레임 재생에서 v2는 v1과 같았다(게이트 결정 0/518, 벽 앞 단색 장면은 게이트도 판정 불가). 이 짝은 조합 전체 비교이며 v2 효과 분리 근거가 아니다.
- 별도 Mac 중계: 로컬 18394 → Azure 18391(e2e14 중계 18414→18393과 분리). 호출 ID `e2e15-[ab]-s6100[1-3]`만 허용(`scripts/s4_proxy_relay.py`).
- 사전 점검(필수): VM 할당·`azure_shutdown.py admit`, 여유 메모리 ≥ 6 GiB/실행, 디스크 ≥ 8 GiB + 6×2 GiB, 부하 평균 기록, Azure `ss -ltn | grep 18391` 비어 있음, 소스 `~/ugrp-sim/src/$SHA` clean, uptime+25,860 s < 28,800 s.

```bash
# Mac (기본 체크아웃 아님: 이 worktree), SHA = 실행할 claude/e2e14-combo 커밋
cd /Users/changmin/projects/ugrp-wt/e2e14-combo && SHA=$(git rev-parse origin/claude/e2e14-combo) && OUT=outputs/e2e15 && mkdir -p $OUT
python3 scripts/ugrp_session.py run e2e15-relay -- python3 -m scripts.s4_proxy_relay  # e2e14 중계와 같은 Mac python3 --output $OUT/relay --seconds 28800 --idempotent \
  --listen-port 18394 --remote-port 18391 --driver-profile study_gemma4_31b_v1 --upstream openrouter_v1 --gemma-state $OUT/upstream &
python3 scripts/ugrp_session.py run e2e15-tunnel -- ssh -T -n -o BatchMode=yes -o ServerAliveInterval=15 -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:18391:127.0.0.1:18394 azure 'sleep 28800' &
ssh azure 'mkdir -p ~/ugrp-sim/relays/e2e15' && scp $OUT/relay/identity.json azure:ugrp-sim/relays/e2e15/a.json

# Azure: 6개 동시 제출 (각 실행 remote_run_finish.py로 감싸 원본·해시 보존; e2e14 submit-remote.py와 같은 형식)
ssh azure "SHA=$SHA bash -s" <<'REMOTE'
set -euo pipefail; B=/home/ugrp/ugrp-sim; S=$B/src/$SHA; cd $S
python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit
curl -sf http://127.0.0.1:18391/identity | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["single_model"] and d["upstream"]=="openrouter_v1"'
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
COMMON="--expected-source-sha $SHA --driver-profile study_gemma4_31b_v1 --relay-receipt $B/relays/e2e15/a.json --e2e-live --event-driven-llm --compact-prompt --setdown-only-when-relook on_v1 --decider off --exploration-progress frontier_progress_v1 --pose-fix innovation --path-follow rpp_v1 --dev-light --stall-bundle --mapping-budget case_cap_v1 --wall-cap-s 25200"
A_ARGS="--stall-odometry rgb_vo_v2 --stall-recovery off --stall-noise off --boundary-views candidate_views_v1 --b-marker-detect contrast_v1"
B_ARGS="--stall-odometry rgb_pulse_gate_v1 --stall-recovery backup_replan_v1 --stall-noise amcl_alpha_v1"
for seed in 61001 61002 61003; do for g in a b; do
  R=$B/runs/e2e15-$g-s$seed; test ! -e $R; mkdir $R; touch $B/leases/e2e15-$g-s$seed; uptime > $R/LOADAVG; echo $SHA > $R/SOURCE_SHA
  if [ $g = a ]; then WF=e2e-combo14-vo2-v205; X=$A_ARGS; else WF=e2e-stall-budget-v199; X=$B_ARGS; fi
  printf '{"class":"dev","pr":446,"branch":"claude/e2e14-combo","sha":"%s","batch":"e2e15","group":"%s","seed":%s}\n' $SHA $g $seed > $R/RUN_META.json
  setsid nohup python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source $S --run $R -- \
    .venv-sim/bin/python -m scripts.sim_cli workflow run $WF --timeout 25260 -- $COMMON --output $R/raw --seed $seed $X --execute \
    </dev/null >/dev/null 2>&1 &
done; done
REMOTE
```
- 종료 뒤: VM `deallocated` 확인, ARM 해시 보관·Mac fetch-lite 회수(e2e14 `fetch-finish.py` 방식), Mac 중계는 `python3 scripts/ugrp_session.py stop e2e15-relay` / `stop e2e15-tunnel`.
