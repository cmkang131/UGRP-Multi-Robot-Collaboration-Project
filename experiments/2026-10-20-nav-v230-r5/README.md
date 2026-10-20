# nav v230-r5 — 2단계 조준(문 통과 → 1.5 m 슬롯) · ① 단독 r1 · ② 2-robot Step B (2026-10-20)

prereg: `experiments/2026-10-17-act18/PREREG_V230_R5.md` (결과 뒤에도 이 디렉터리의 파일이
prereg를 대체하지 않는다). base `523b011c1`, branch `dsh/nav-v230-r5`, gcp6 단일 lease.

## 무엇을 재는가
- ① 단독 r1 1회(진단, 게이트 아님): 문 통과·stage 2 활성·arming·claim. 문에 걸리면 ② 중단.
- ② 2-robot Step B 1회: 수용표 `GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0`.
  로봇 간 최소 거리·접촉 + **로봇-벽/문틀 접촉(eval-only)** + **명령 적산 대 GT 비율(판정 미사용)**.

## 실행 (VM clone root, Linux gcp6 only, `.venv-warp`)
```bash
export E2EWARP_NAV_GATE_MODE=v230_r5
export E2EWARP_NAV_ARRIVAL=odom_projection
export E2EWARP_NAV_CALIBRATION=/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json
P=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
$P -m scripts.e2ewarp_nav_manifest --out runs/nav-v230-r5-components.json \
  --calibration "$E2EWARP_NAV_CALIBRATION" --source-sha 219d08779bf068fb35156e16d19e7744e36d4595
$P experiments/2026-10-19-nav-v230-r3/render_check.py --out runs/nav-v230-r5-render-<TS> \
  --expected-source-sha 219d0877…
# ① 단독 r1
$P -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 --seed 601 --nworld 1 \
  --condition peer_en --nav-sim-budget-s 60 --components runs/nav-v230-r5-components.json \
  --arrival-odom-projection --nav-solo-robot r1 --output runs/e2ewarp-nav-v230-r5-solo-r1-admission
$P -m scripts.run_e2e_warp --mode nav --execute --e2e-warp-batch on_v1 --nav-solo-robot r1 \
  --queue runs/e2ewarp-nav-v230-r5-solo-r1-admission/queue.json --expected-source-sha 219d0877… \
  --host-receipt runs/… --components runs/nav-v230-r5-components.json \
  --relay-url http://127.0.0.1:18627/v1/chat/completions --output runs/e2ewarp-nav-v230-r5-solo-r1
# ② 2-robot Step B (같은 방식, --nav-solo-robot 없이, 새 root)
```

## 결과 요약
- ① r1: 문 22.2 s 통과, stage 2 26.6 s(1.4833 m), claim 39.7 s(`d_proj 0.5239`), GT zone 안(+0.1104 m),
  접촉 0, 명령/GT 1.002.
- ② `GT 2/2 · claim 2/2 · mismatch 0 · FP 0 · 경계 0` **PASS**. 두 로봇 39.7/39.9 s claim,
  최종 GT 안(+0.114/+0.1276 m). 로봇-로봇·로봇-씬 접촉 **0 tick**, 최소 중심 0.1770 m/박스 0.0457 m
  @27.1–27.2 s, 명령/GT 1.002/1.003.
- 원본: VM `/home/ugrp/ugrp-sim/runs/e2ewarp-nav-v230-r5-*`, Oracle
  `outputs/e2e18-admin/nav-gate/v230-r5/stepB-20261020T0205Z/`, 보고서
  `outputs/reports/2026-10-20-nav-stepB-v230-r5-dsh-20261020T0210Z.md`.

## 분석
```bash
$P -m scripts.e2ewarp_nav_recount --run <run>
$P experiments/2026-10-20-nav-v230-r5/nav_v230_r5_analysis.py --run <run> --admission <admission> \
  --expected-source-sha 219d0877… --out <analysis.json> --preflight-render <render>/measure.json
```
`nav_v230_r5_analysis.py`는 r4 재계수 도구를 import해 수용표를 다시 세고(stage 2·scene 접촉·명령/GT
비율 추가) eval-only로만 기록한다. post-run 수정 `ef5ebcd9`(FP 필드·arming 지면거리)는 run 종료 뒤
분석에만 적용했고 수용표 수치는 불변이다.
