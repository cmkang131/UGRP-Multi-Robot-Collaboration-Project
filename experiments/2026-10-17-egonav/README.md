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

## 후보 A (gate-09) — 통과 16/16

queue: `queue-gate09.json` (source 2e27dc5, sha256 `80521816…c9449`), stack
check: `stack_check_gate09.json`(ok true, 30행). 변경: (1) 0.10 m² 관측 넓이
탄생 게이트(면적 없는 관측은 fail-closed로 무시), (2) 측정 회전 한계
62펄스, (3) 기억 이송 yaw 0.744774 보정. gate-08과 같은 setup·세계·시드.

원본 `/home/ugrp/ugrp-sim/runs/egonav/gate-n16-09` (gcp4),
`SHA256SUMS.json` sha256 `8f170246851bf7cf19e54e49c15204b7375ba6dc63c61bce1cd3e188d0fb1edf`,
`summary.json` sha256 `a8d5e4d3df9a167633cf6e022e05381cc8cbba5eb7e8234e84053e0370e309ca`.
재계수 `recount_gate09.json`(원본 JSON만 읽음, `all_checks_match true`),
표 `world-table-gate09.md`.

| 항목 | 값 |
|---|---|
| GT 구역 A 안 도착 | **16/16** |
| 도착 선언(`done`) | 16/16 (그중 world04는 `arrival_unverified` 후 정지, GT는 구역 안) |
| 한 번 이상 표시 관측 | 16/16 |
| 중간 상실 world | 15/16 (world09는 상실 없음) |
| 충돌 | 0/16, 0회 |
| 제외/분모 축소 | 없음 (world_n 16) |
| 최종 중심 거리 | 0.043–0.475 m |
| 기억 미관측 오차 기울기 | median -9.63e-6 m/s (n=15) |
| status | ALL_WORLDS_DONE, sim 25.5 s, wall 1317.5 s, speed 3.23 wall/(sim·world) |

funnel(`gate09-rejection_table.json`): requested_n16 16 → input_audit 16 →
target_observed 16 → arrived_inside 16, 거부 0. 원장 `reasons={}`,
`blocked_object=not_observed`, `minimum_gap_m=null`/`not_measured`.

world02 회복 확인: t=1.6·3.8·15.7에 `small_marking_rejected`
(최소 넓이 0.0221·0.0761·0.0945 m²), t=3.9에 진짜 표시로 `target_acquired`,
t=15.7 구역 안 도착. area 게이트가 gate-08 실패를 직접 막았다.
13개 `small_marking_rejected` 이벤트가 전 world에 걸쳐 기록됐다.

**기록 주의:** 평가 칸의 `final memory err`와 `target_lost`는 게이트가
"첫 원시 패치"를 기준으로 라벨링하므로(gate 스크립트의 `visible=bool(obs)`),
world02의 4.431 m는 받아들인 목표의 오차가 아니라 **첫 거짓 패치와 최종
목표 사이 거리**다. 다음 게이트에서는 평가 앵커도 area 게이트를 통과한
첫 관측으로 바꿔야 한다(이번 실행 코드는 그대로 두고 기록만 남긴다).
성공 판정(GT 구역 안)과 충돌 수는 이 라벨과 무관하다.

## 검증 범위와 남은 확인

* gate-08 재계수는 VM 원본 JSON·SHA256SUMS로 확인했다(앱 재실행 아님).
* world02 원인은 디버그·프레임 6장·preflight 분포로 확인했고, 후보 A의
  수정 효과는 gate-09 원본으로만 판정한다(아직 미확인).
* 로컬 `raw/`(프레임·replay 디버그, 5.2 MiB)는 실험 미디어 5 MiB 제한
  때문에 커밋하지 않고 VM 원본 경로와 해시로 연결한다.

## 시각화 실행: egonav_memory_trace_v1 (2026-10-17 사용자 요청)

사용자 요청: "자기 지도를 어떻게 만들고 있는지 실시간으로 보여줄 수 있나".
기억(지형지물)이 만들어지고 이동·소실되는 과정을 눈으로 보기 위한
**기록 전용** 실행이다. 성공 판정 근거가 아니며 gate-09/PR #583 결과와
합산하지 않는다. 다른 조건·16세계 gate는 바꾸지 않는다.

* 토글 `egonav_memory_trace_v1`(기본 off, `--memory-trace`): 매 10 Hz 틱마다
  기억 항목(id·종류·자기 기준 상대 x/y·불확실성·마지막 관측 시각), 그 틱의
  이벤트, 로봇 자세(`pose_eval_only`, 평가 전용)를 `memory_trace/world00.jsonl`에
  남기고, 전 구간 자기 RGB 프레임을 `frames/world00/`에 저장한다. 이 값은
  제어기에 전달되지 않는다(제어 변경 없음). 게이트의 기존 `trace`·`summary`
  동작은 토글 off에서 이전과 같다.
* 실행: 세계 1개(world00), 같은 장면·시드·설정. 캡만 120 SIM초
  (`gate-setup-visual120.json`, `step_budget` 500→1200; 다른 키는
  `gate-setup.json`과 동일). `--worlds 1 --memory-trace`.
* 재생: `scripts/egonav_memory_replay.py`가 왼쪽 자기 중심 top-down(로봇은
  원점·정면 고정, 기억·불확실성 원이 상대 위치로 반대로 이동), 오른쪽 자기
  RGB, 아래 t·기억 개수·이벤트를 그려 10 fps(=10 Hz 트레이스, 1× SIM 속도)
  mp4로 만든다.
* 산출물: Mac `/Users/changmin/projects/ugrp/outputs/egonav-mapbuild/`
  (mp4·트레이스·메타). VM 원본은 `/home/ugrp/ugrp-sim/runs/egonav/mapbuild-01`.

### 실행 결과 (2026-10-17)

* `mapbuild-01`(파이프라인 확인): gate world00 스폰 (3.55, 0.4), sim 6.3 s,
  트레이스/프레임 64행, GT 구역 도착 1/1, 충돌 0. 영상 960×560·10 fps·6.4 s.
  목표가 0.99 m 앞에서 시작해 6.3 s 만에 도착, 기억이 1개뿐이라 시연용으로는
  너무 짧았다(원본 보존).
* `mapbuild-02`(시연): gate world02 스폰 (2.75, 0.4, yaw 1.570796) —
  `gate-setup.json`의 `worlds[2]`와 같은 값. sim 15.7 s, wall 186.9 s,
  트레이스/프레임 158행, GT 구역 도착 1/1, 충돌 0, target_loss 2회.
  이벤트: t=1.6·3.8 `small_marking_rejected` → t=3.9 `target_acquired`
  (+reacquired) → t=12.8 `target_lost` → t=13.5 `target_reacquired` →
  t=15.7 `arrival_from_recent_close_observation`. 기억 개수 0→1,
  불확실성 반경 0.19→0.06 m, 자기 기준 상대 위치 1.83→0.17 m(접근에 따라
  왼쪽 패널에서 반대로 이동).
* 영상: 960×560, 158프레임, 10 fps(=10 Hz 트레이스, **1× SIM 속도**), 15.8 s,
  mp4 sha256 `332be3d8901f45be33c9acb6319986b16cdf7ee51991479b3d94446f6f25c4f2`,
  트레이스 sha256 `e346e915227b1951bcf7bd8c7bc370dbd047ed9ce1ea4d2d274e0f125f2bd5c3`,
  빌더 sha256 `d30e4fc7a54a0e5a05cf410eb52665c773fbd6fdd48de79defe8a1b97301d4d5`.
* Mac 산출물: `/Users/changmin/projects/ugrp/outputs/egonav-mapbuild/`
  (`egonav-memory-replay-world02-15.8s.mp4`, `memory_trace-world02-spawn.jsonl`,
  `replay-meta.json`, `run-summary.json`, `preview/*.png`).
* VM 원본: `/home/ugrp/ugrp-sim/runs/egonav/mapbuild-01`,
  `/home/ugrp/ugrp-sim/runs/egonav/mapbuild-02`(VM 정지, 디스크 보존).
  gcp4는 리스 해제 후 TERMINATED 확인.
* 주의: 이 영상은 시각화이며 성공 판정 근거가 아니다. gate-09/PR #583 결과와
  합산하지 않는다. 왼쪽 패널의 기억은 컨트롤러가 받아들인 목표 표시 1개이고,
  거부된 작은 패치는 기억으로 만들지 않으므로 이벤트 텍스트로만 보인다.
