# nav v230-r3 — projection claim (①) 실험 기록 — 2026-10-19

**조건 표기: sim 전용(`domain=sim`).** branch `dsh/nav-v230-r3`, Step B source
`a84082b195967b39a2e486b3c90a5b1e8eb24d0f`(= prereg commit, base `d2e10e7e9`). 결과는 이 조건의
1회 run이며 r2/45 s dev/fwd24/v1과 pooling하지 않는다.

## 무엇을 바꿨나

- claim 정의: `d_proj = (p_odom(t) − p_odom(t_armed)) · u(t_armed) ≥ 0.52 m`.
  `p_odom`은 자기 발행 명령 + 주입 캘리브레이션 적분, `u`는 armed 시점 자기 기억 bearing 방향
  (자기 오도메트리 프레임). 세계 x축·지도·GT 미사용.
- heading hold: armed 이후 `turn = clamp(wrap(u − yaw_odom)/45°, −1, 1)`, `forward=1.0`(r2와 동일
  pulse vocabulary).
- fail-safe: armed 이후 경로 1.0 m에서 `d_proj<0.52`면 claim 없이 정지 + `NO_CLAIM` 기록.
- gate: `E2EWARP_NAV_GATE_MODE=v230_r3`, `--arrival-odom-projection` (기본 off). 0.52·1.0은
  환경/CLI로 바꿀 수 없는 동결 상수. v1/fwd24/r2 queue·기본값 불변.
- 상세 계약·근거는 `experiments/2026-10-17-act18/PREREG_V230_R3.md`(§3·§4·§5).

## 실행 1 — ② FP 재렌더 (새 SHA, preflight)

| 항목 | 값 |
|---|---|
| raw (VM) | `/home/ugrp/ugrp-sim/runs/nav-v230-r3-render-20261019T2011Z/` + `.log` |
| Oracle | `outputs/e2e18-admin/nav-gate/v230-r3/render-20261019T2011Z/` |
| evidence tar sha256 | `3a82070a6e36546f197659bf60f0ac39f4281c7f4fff79e251a7df39060a5f56` (VM=Oracle) |
| `measure.json` sha256 | `2acd4f1904431e053b430a0634f59b30ae1134e673148e3615e7376632ffdbab` |
| 결과 | r1 zone-free **검출 0/10, 최대성분 1 px**(<600) **PASS**; r2 레인 10프레임 0/10·최대 212 px; ③ 경로 감사 PASS(최소 여유 0.0343 m) |
| 판정 | **② PASS → Step B 진행** |
| class | preflight (gate 아님, controller/LLM 0) |

## 실행 2 — Step B (v230_r3, 2 robots, seed 601, peer_en, 60 s) — **FAIL**

| 항목 | 값 |
|---|---|
| raw (VM) | `/home/ugrp/ugrp-sim/runs/e2ewarp-nav-v230-r3-run/`, `…-admission/`, `…-components.json`, `…-analysis.json`, `…-stepB.log`, `…-STEPB-META.txt`, `…-lease.json`, `…-host-receipt.json` |
| Oracle | `outputs/e2e18-admin/nav-gate/v230-r3/stepB-20261019T2025Z/` |
| evidence tar sha256 | `edf9425585366dac928d9a5a5cf31a55f77f1c502e954e14bb4394bf40a829f8` (VM=Oracle) |
| status | `NAV_ARRIVAL_UNVERIFIED` (두 로봇 claim 후 조기 종료) |
| SIM / wall | 41.2 s / 302.55 s (wall/SIM 7.34, first30 6.68 — 기록 전용 경고) |
| **판정** | **FAIL** — GT 1/2, claim 2/2, mismatch 1, FP 1(최종)/2(claim 시점), 경계 0, `NO_CLAIM` 0/2 |
| claim | r1 39.4 s `d_proj 0.533936`(GT 최종 +0.0028 m, claim 시점 −0.0584 m), r2 41.2 s `d_proj 0.525325`(최종 −0.1358 m) |
| 검출 | r1 342/413틱(fresh 311), r2 372/413(fresh 347); 첫 fresh 7.1/4.1 s |
| wheel | commands 826행(413/로봇), 비영 806행; 60 s 기대 1200 미달(조기 종료) |
| 원인 | 두 로봇이 26.4 s부터 base 충돌 박스 거리(<0.181 m) 안으로 수렴(claim 시 0.174 m) + wheel odometry/GT 괴리(r1 1.19×·u 투영 0.185 m, r2 1.63×·0.315 m). 상세는 보고서 §6 |
| class | **study** (prereg), gate=true, pooling=false |

전체 판정·수치·영상 확인·증거 목록: `outputs/reports/2026-10-19-nav-stepB-v230-r3-dsh-20261019T2025Z.md`.

## 재현

```bash
# VM(clone root), gcp6
export E2EWARP_NAV_CALIBRATION=/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json
export E2EWARP_NAV_GATE_MODE=v230_r3 E2EWARP_NAV_ARRIVAL=odom_projection
python -m scripts.e2ewarp_nav_manifest --out .../e2ewarp-nav-v230-r3-components.json \
  --calibration "$E2EWARP_NAV_CALIBRATION" --source-sha <SHA>
python -m scripts.run_e2e_warp --e2e-warp-batch on_v1 --mode nav --output .../e2ewarp-nav-v230-r3-admission \
  --seed 601 --nworld 1 --condition peer_en --nav-sim-budget-s 60 \
  --components .../e2ewarp-nav-v230-r3-components.json --arrival-odom-projection --prepare
python -m scripts.run_e2e_warp ... --execute --queue .../admission/queue.json --expected-source-sha <SHA> \
  --host-receipt .../nav-v230-r3-host-receipt.json --components .../components.json \
  --relay-url http://127.0.0.1:18627/v1/chat/completions
python -m scripts.e2ewarp_nav_recount --run .../e2ewarp-nav-v230-r3-run
python experiments/2026-10-19-nav-v230-r3/nav_v230_r3_analysis.py --run ... --admission ... \
  --expected-source-sha <SHA> --out .../nav-v230-r3-analysis.json
```

## CPU 시험

`tests/test_e2ewarp_nav_v230_r3.py` 17개(투영 claim·정의 구분·heading hold·NO_CLAIM·1.0 m cap·
default off·queue binding) + 관련 nav 시험 총 **165 passed** (Step B 전, `a84082b19`).

## 한계

- 1회·1 seed·단일 장면, sim 전용. 접촉력 원장이 없어 로봇 간 접촉은 기하·기구학 근거로만 보고한다.
- post-run 분석 도구 수정은 수용표 수치를 바꾸지 않았고 두 버전 sha를 함께 기록했다(보고서 §6.4).
