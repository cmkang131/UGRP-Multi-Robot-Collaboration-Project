# egonav — 자기 중심 기억으로 바닥 표시 찾아 이동 (2026-10-17)

제어 입력은 자기 RGB, 자기 서보 명령, 자기 발행 바퀴 명령 이력뿐이다.
정적 지도·top 카메라·정답 좌표는 제어에 쓰지 않는다(`held_world_reads=0`,
`static_map_control=0`). base 후보 `egocentric_goto_v1`, MJWarp batch N=16,
`warp_native_contact_v1`(noslip 0), scene `walls_floor_contrast_v5_indigo110_s80`,
scenario `s1_normal_mixed_v7`, cargo v6, step_budget 500.

## gate-08 원본 재계수 (source 0f8755a)

원본 VM 경로 `/home/ugrp/ugrp-sim/runs/egonav/gate-n16-08` (gcp4).
`SHA256SUMS.json` sha256 `16fde8f2d85c67e1dabd97c18e04eeaeefdc4e9e5572b25cc75a716ab3040264`,
`summary.json` sha256 `c96b7fd53bffa33c3fdf2a6ef0b3bedb1eb26cf22f753471f780d93bae5b3ed1`,
`world02.json` sha256 `d899a2b000167338171e6e56933f42f6841172c27943e66433c0d294f350c425`.
로컬 검증 사본 `/tmp/egonav-gate08-json`(21개 파일, VM `SHA256SUMS`와 불일치 0).

| 항목 | 값 |
|---|---|
| GT 구역 A 안 도착 | 15/16 |
| 도착 선언(`done`) | 16/16 |
| 한 번 이상 표시 관측 | 16/16 |
| 중간에 표적 상실한 world | 16/16 |
| 충돌(상승 에지) | 0/16, 0회 |
| 제외/분모 축소 | 없음 (world_n 16 전부 집계) |
| 최종 구역 거리 | mean 0.2316 m, median 0, max 3.7043 m |
| 기억 미관측 오차 기울기 | median -6.99e-7 m/s (n=16), 즉 증가 없음 |
| `cap_end`로 끝난 world | 0 (ALL_WORLDS_DONE, sim 33.8 s) |

per-world 표: `world-table-gate08.md`. 재계수 원본: `recount_gate08.json`
(`recount.py`로 VM 원본 JSON만 읽어 재계산, summary와 일치 확인).

## gate-08 유일 실패 world02 원인 (프레임 6장 확인)

`arrival_claimed_outside_zone`, 최종 구역 거리 3.704 m, spawn
[2.75, 0.4, yaw 1.5708], 기억 앵커 world (0.1508, -0.9910) at t=1.6.

* t=1.6 첫 수용 패치가 몸체 좌표 (2.717, 1.150) m, 넓이 0.0223 m²,
  변 [0.056, 0.491] m, 102 px, solidity 0.986 — **바닥 표시가 아니라
  동료 로봇의 주황 바퀴/팔**이다. 동료는 world02 base spawn (-0.8, -2.8)에
  있고, 로봇은 그 방향으로 약 2.5 m 주행한 뒤 표적을 잃었다.
* 확인 프레임(자기 카메라): ring world02 `0239, 0260, 0280, 0300, 0320, 0338`
  (각 1장, 총 6장; 로컬 `raw/frames-gate08-w02/`). 0260–0338에서 주황
  바퀴·주황 팔의 동료 로봇과 초록 상자가 보이고, 바닥 주황 표시는 없다.
* 재현 replay `replay02`(world02 spawn, step_budget 180): 180틱 중 수용 패치
  267개, 넓이 0.00515–0.02679 m²(median 0.01353). 디버그 원본
  `raw/replay02-debug.json`.
* 같은 장면 preflight t=0의 진짜 zone A 표시 넓이는 0.4427–0.8619 m²
  (10/16 world에서 관측, 거리 0.99–3.71 m): `raw/preflight-gate08.json`.
  참/거짓 분포의 기하 중점 sqrt(0.4427×0.02679)=0.109 → **0.10 m²** 탄생
  게이트를 채택했다(진짜 최소의 4.4배 아래, 거짓 최대의 3.7배 위).
  판정 대상 축소는 없다(world02 1개 실패만 원인 분석).

원장: `blocked_object=peer_robot_orange_wheels`(프레임 근거),
`minimum_gap_m=null`·`gap_status=not_measured`(제어기가 동료까지의 거리를
재지 않음). 게이트 거부표의 실패 행은
`reason_category=arrival_claimed_outside_zone`,
`blocked_object=target_zone_boundary`, `minimum_gap_m=3.7043`,
`gap_status=measured_eval_only`다.

## 회전 모델 보정 (상수 근거)

`harness/egocentric_goto.py`의 `command_delta()`는 고정 휠 접촉 모델이고,
`update_memory()`의 기억 이송과 `motion_variance`가 같은 모델을 쓴다.
gate-07 world06의 "6.41 rad 모델 대 1.49 rad 실제(4.29x)"는 펄스당 델타가
아니라 **spawn yaw(1.33977)와 최종 qpos yaw(-0.15319)를 비교한 값**이었다.

순수 회전 펄스 probe (`--probe-rotation`, 평가 전용, 제어 미사용):

| 원본 | 펄스 | 중앙값 rad | p10 rad | p90 rad |
|---|---:|---:|---:|---:|
| `probe-rotation.json` (world00, 239델타) | 240 | 0.1060358 | 0.1027191 | 0.1103730 |
| `probe-rotation-w0-6.json` (world0–6, 각 59델타) | 60 | 0.10599–0.10615 | — | — |

고정 모델 예측 0.1423730 rad/펄스 → 실제의 1.34배. world06 spawn을 포함한
7개 world가 모두 0.106 rad/펄스로 같아 world별 장애물 때문이 아니다.
적용: search/verify 완료는 `ceil(2π/p10)=62`펄스(=측정 한 바퀴),
기억 이송 yaw는 `median/model=0.744774`로 보정. `SEARCH_SWEEP_MARGIN=5`
배율 상수는 삭제했다. 근거 수치는 코드 주석에 같은 값으로 적었다.

## 후보 A (gate-09)

queue: `queue-gate09.json` (source 2e27dc5), stack check:
`stack_check_gate09.json`(ok true, 30행). 변경: (1) 0.10 m² 관측 넓이
탄생 게이트(면적 없는 관측은 fail-closed로 무시), (2) 측정 회전 한계
62펄스, (3) 기억 이송 yaw 0.744774 보정. gate-08과 같은 setup·세계·시드.
raw: `/home/ugrp/ugrp-sim/runs/egonav/gate-n16-09` (진행/결과는 아래에 추가).

## 검증 범위와 남은 확인

* gate-08 재계수는 VM 원본 JSON·SHA256SUMS로 확인했다(앱 재실행 아님).
* world02 원인은 디버그·프레임 6장·preflight 분포로 확인했고, 후보 A의
  수정 효과는 gate-09 원본으로만 판정한다(아직 미확인).
* 로컬 `raw/`(프레임·replay 디버그, 5.2 MiB)는 실험 미디어 5 MiB 제한
  때문에 커밋하지 않고 VM 원본 경로와 해시로 연결한다.
