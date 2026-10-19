# nav v230-r4 — 단독 claim 진단 · 슬롯 gate · 드리프트 진단 (2026-10-19)

prereg: `experiments/2026-10-17-act18/PREREG_V230_R4.md` (이 디렉터리의 파일은 결과 뒤에도
prereg를 대체하지 않는다). base `3d90cc3eb`, branch `dsh/nav-v230-r4`, gcp6 단일 lease.

## 무엇을 재는가
- ① 단독 r1 / 단독 r2: 같은 mode·seed·예산에서 **한 로봇만** XML에 남긴 진단 2회. claim이
  접촉 없이 GT zone 안에서 성립하는지. 게이트 아님.
- ② 2-robot 슬롯 gate 1회: 주문서 `slots={r1:left, r2:right}`. r3 수용표 그대로
  (`GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0`) + 로봇 간 최소 거리·접촉 원장.
- ③ ①② 원본에서 명령 yaw / odometry yaw / GT yaw / 코스팅 / 슬립을 분해해 남쪽 쏠림의
  조향·차동·슬립·접촉 성분을 판정한다(수정 없음).

## 실행 (VM clone root, Linux gcp6 only)
```bash
export E2EWARP_NAV_GATE_MODE=v230_r4
export E2EWARP_NAV_ARRIVAL=odom_projection
export E2EWARP_NAV_CALIBRATION=/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json

python -m scripts.e2ewarp_nav_manifest --out runs/e2ewarp-nav-v230-r4-components.json \
  --calibration "$E2EWARP_NAV_CALIBRATION" --source-sha <SHA>

# ① 단독 r1 / r2  (각각 새 out dir)
python -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 --seed 601 \
  --condition peer_en --nav-sim-budget-s 60 --components <components> \
  --arrival-odom-projection --nav-solo-robot r1 --output runs/e2ewarp-nav-v230-r4-solo-r1-admission
python -m scripts.run_e2e_warp --mode nav --execute --nav-solo-robot r1 \
  --queue runs/e2ewarp-nav-v230-r4-solo-r1-admission/queue.json --expected-source-sha <SHA> \
  --host-receipt <receipt> --components <components> --output runs/e2ewarp-nav-v230-r4-solo-r1
# (r2 동일)

# ② 2-robot gate (1회)
python -m scripts.run_e2e_warp --mode nav --prepare ... --output runs/e2ewarp-nav-v230-r4-admission
python -m scripts.run_e2e_warp --mode nav --execute --arrival-odom-projection \
  --queue runs/e2ewarp-nav-v230-r4-admission/queue.json --output runs/e2ewarp-nav-v230-r4-run ...
```

## 분석
```bash
python -m scripts.e2ewarp_nav_recount --run <run>
python experiments/2026-10-19-nav-v230-r4/nav_v230_r4_analysis.py \
  --run <run> --admission <admission> --expected-source-sha <SHA> --out <analysis.json>
```
`nav_v230_r4_analysis.py`는 수용표·접촉·드리프트를 원본에서 재계수한다. r3 원본에 대해
`GT 1/2 · claim 2/2 · mismatch 1 · min center 0.1681 m`를 재현해 도구를 검증했다(보고서 §1).
