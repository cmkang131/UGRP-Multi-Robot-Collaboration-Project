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

## 원거리 검출 한계와 기본 off far 후보 (2026-10-18)

사용자 질문: "좀 더 멀리서 찾아서 다가오게는 못할까?" 현재 0.10 m²
관문은 gate-08 world02의 동료 바퀴 오탐(0.0223 m²)을 막기 위한 값이다.
이 관문이 원거리 검출을 막는지, 더 먼 시작에서도 표시가 보이는지를
먼저 정적으로 쟀다(1단계). 정답 좌표는 시작 배치 저작과 평가 표에만
쓰고 제어 입력에는 넣지 않았다.

### 1단계 — 2·3·4·5 m 정적 검출 측정 (far-measure-02)

`scripts/egonav_gate.py --detect-probe`, world 4개, 각 100틱(9.9 SIM초),
바퀴 명령 0으로 정지한 채 자기 RGB만 사용. 바닥 투영은
`downward_min=0.05`, `max_range_m=4.0`(하드 클램프),
유효 바닥 픽셀 264686/307200. 저작 시작은 중심까지 2.000/3.000/
3.939/4.903 m(가장자리까지 1.700/2.267/3.191/4.510 m).

| 시작(중심/가장자리) | 목표 표시 검출 | observed_area_m2 | 픽셀 수 | hue 중앙값 | 패치 range | 판정 |
|---|---|---|---|---|---|---|
| 2.000 / 1.700 m | 100/100틱 | 0.842–0.903 | 11031–11116 | 12 | 1.969 m | 진짜 표시 |
| 3.000 / 2.267 m | 100/100틱 | 0.822–0.893 | 3347–3390 | 12 | 2.929 m | 진짜 표시 |
| 3.939 / 3.191 m | 100/100틱 | 0.378–0.442 | 805–959 | 12 | 3.716 m | 진짜 표시 |
| 4.903 / 4.510 m | 0/100틱 | 0.0092–0.0096 | 465–470 | 1 | 1.319 m | 목표 아님(빨간 화물, hue 1) |

* **핵심:** 0.10 m² 출생 관문은 원거리 한계가 아니다. 3.94 m에서도 진짜
  표시는 0.378–0.442 m²로 관문의 3.8–4.4배였다. 한계는 바닥 투영의
  `max_range_m=4.0`이다. 4.90 m에서는 구역 가장자리까지 4.510 m라
  진짜 표시의 유효 바닥점이 하나도 없고, 검출된 유일한 패치는 문 근처
  1.32 m의 빨간 화물(0.0092 m², hue 1)이다. 따라서 0.10 m² 미만 패치를
  추적하는 후보 토글로는 이 4.9 m 시작을 살릴 수 없다(추적할 진짜 패치가
  없다). 더 멀리 보려면 투영 `max_range_m`이나 카메라 기하를 바꿔야 하며,
  이번 작업 범위 밖이라 바꾸지 않았다.
  → 4단계에서 클램프를 진단용으로 풀어 재측정했고, 클램프 해제 뒤에도
  남는 상한은 `downward_min=0.05` 바닥 유효영역(중앙 열 4.785 m)이었다
  (아래 "4단계"에서 정정).
* 원본: VM `/home/ugrp/ugrp-sim/runs/egonav/far-measure-02`,
  Mac `outputs/egonav-far/far-measure-02/`. `detect_probe.json` sha256
  `ecb96271e825d3666758bbe5c552f8906d62193edafa70310235e5152c0e5874`,
  `SHA256SUMS.json` sha256
  `2888d9336b792fd04412d4659f40f681cc756b69ff5c762543d8f05501bea1c9`
  (Mac 회수분 9/9 검증, 프레임 12장은 VM 보존).
* 실패 보존: `far-measure-01`은 `.venv-sim`에 `mujoco_warp`가 없어
  ModuleNotFoundError로 끝났다(정확한 환경은 `.venv-warp`). 원본 보존.

### 2단계 — 기본 off 토글 `egonav_far_candidate_v1`

`harness/egocentric_goto.py`: 0.10 m² 미만 패치를 '후보'로 추적하되
다음 조건을 모두 만족할 때만 **탐색 회전의 부호**를 바꾼다(기본 off,
`far_candidate=False`).

1. 같은 kind/signature이며, 측정 hue가 이미 받아들인(≥0.10 m²) 표시의
   실측 hue와 3 이내. 아직 받아들인 표시가 없으면 `hue_reference_unavailable`로
   거부한다(fail-closed). hue는 게이트가 받아들인 구성요소 픽셀에서
   직접 측정하며 정답 hue를 넣지 않는다.
2. 5프레임(0.5 s) 연속 지속.
3. 자기 발행 명령 이력에 전진 명령이 있고, 관측 면적이 첫 면적의 1.25배 이상.

상수 근거(측정 분포): 진짜 표시 hue는 100/100틱에서 12, 빨간 화물은 1이라
허용 3은 둘을 구분한다. 정지 상태 면적 max/min은 ≤1.169라 1.25는 잡음
위이고, 진짜 패치는 100/100틱 존재해 5프레임은 최소 지속 창이다.
후보는 기억을 만들지 않고, `seen_target`/`done`을 세우지 않으며, 전진
주행에 쓰지 않는다. 확정·도착 판정은 계속 0.10 m² 관문이 소유한다.
수용/거부 원장은 `reason_category`, `blocked_object=
orange_object_below_zone_marking_area`, `minimum_gap_m=None`,
`gap_status=not_measured`, `observed_area_m2`, `first_area_m2`, `frames`,
`hue`, `confirmed_hue`, `forward_approach`를 남긴다. 1.0 s 넘게 후보가
안 보이면 `far_candidate_expired`를 남긴다. 거부 사유:
`hue_not_measured`, `hue_reference_unavailable`, `hue_mismatch`,
`persistence`, `no_forward_approach`, `no_area_growth`.

### 3단계 — 같은 시작 4세계 off/on 프로브 (source aa5d503e)

같은 4개 저작 시작, `step_budget` 1200(모든 세계가 끝나면 자동 종료),
gcp4 L4·`.venv-warp`·`41584d3a1-warp10-pool`. off/on은 같은 SHA의 별도
프로세스이며 서로 합산하지 않는다.

| world | 시작 | off-03 | on-03 | far 후보 이벤트(on) |
|---|---|---|---|---|
| 0 | 2.0 m | 구역 도착 | 구역 도착 | 0 |
| 1 | 3.0 m | 구역 도착 | 구역 도착 | 0 |
| 2 | 3.94 m | 구역 도착 | 구역 도착 | 0 |
| 3 | 4.9 m | 실패(구역 밖 4.506 m) | 실패(구역 밖 4.506 m) | 7행, 수용·회전 0 |

* 합계: off 3/4, on 3/4 도착. 충돌 0/0. SIM 25.6/25.5 s, wall
  449.9/448.1 s. `arrival_claimed_outside_zone` 1(world3)은
  `search_exhausted`로 끝난 실패다.
* on world3 원장: t=0.0 빨간 화물(hue 1, 0.00917 m²) 추적 → t=1.1 만료;
  t=1.3 hue 14·0.0620 m² 패치 추적 → t=1.4 `hue_reference_unavailable`
  거부 → t=3.2 만료; t=3.7 hue 13·0.0167 m² 추적 → t=3.8 같은 사유 거부.
  이 세계는 진짜 표시가 투영 범위 밖이라 한 번도 확정되지 않아 기준
  hue가 없고, 후보는 fail-closed로 회전에 쓰이지 않았다
  (`far_candidate_turn` 0회).
* off/on은 별도 프로세스라 물리 궤적이 비트 단위로 같지 않다(world1
  t=8.3, world2 t=15.4에서 turn/forward 선택이 갈렸고 둘 다 도착). 두
  세계 모두 far 이벤트가 0이므로 이 차이는 토글에 귀속할 수 없다.
  실행 간 시뮬레이터 비결정성 여부는 별도로 재지 않았다.
* 입력 감사(전 실행): `held_world_reads=0`, `top_camera_control=false`,
  `static_map_control=0`, `truth_control=0`.
* 실패 보존: `far-probe-off-01`은 source 908bd2c1c에 `--gate-probe`가
  없어 `GATE_N16_REQUIRED`로 끝났다(4628ac6c에서 우회 추가). 원본 보존.
  `far-probe-off-02`는 토글 코드 이전 source 4628ac6c의 off 기록으로,
  off-03/on-03과 합산하지 않는다(결과는 같은 3/4).

### 영상 (시각화, 성공 판정 근거 아님)

`outputs/egonav-far/far-visual-01/far-candidate-confirm-and-reject.mp4`
(960×560, 10 fps=1× SIM, 33.6 s, 798610 bytes, sha256
`1531c8e07621ca723360c66d9a843e3606a64a4e629cde64441768d8ded30ca3`).
앞 25.3 s는 world0(3.94 m)의 표시 확정·도착, 뒤 8 s는 world1(4.9 m)의
후보 검출·거부·탐색 구간이다. 기록 전용 `egonav_memory_trace_v1` 실행
`far-visual-01`(source aa5d503e, 세계 2개, 세계당 254프레임, SIM 25.3 s,
world0 도착·world1 실패, 후보 이벤트 7행, 수용 0)에서 만들었다. 재생
빌더는 world별 스폰 메타데이터 버그를 고친 7cc7fdd(sha256
`b76359afd115f445f496e1594e63e5b0821abfe9ea8be6c4de8da2d73dff09f5`)를
쓴다. 구성 mp4 sha256: world0 `83142a8c…`, world1 `e2598055…`.

### 4단계 — 바닥 투영 클램프 해제 거리 진단 `far-diag-range-01`

1단계에서 한계로 지목한 `max_range_m=4.0` 하드 클램프를 **진단에서만**
10.0 m로 풀고, 4.0/4.5/5.0/5.5 m 정지 측정을 했다(각 100틱). source
`c4256a3fb`, `--detect-probe`, 바퀴 명령 0, 평가 전용. **제어 기본값은
4.0 m 그대로**이며 이 실행은 제어에 쓰지 않았다(`control_use=false`).

원본: VM `/home/ugrp/ugrp-sim/runs/egonav/far-diag-range-01`(gcp4, 디스크
보존), Mac 로컬 `experiments/2026-10-17-egonav/raw/far-diag-range-01/`(비커밋
실험 raw, `SHA256SUMS.json` 대조 **21/21 일치**, 프레임 12장 포함).
`detect_probe.json` sha256 `ed9e5fa7db92f66c4b2f97b655eba5fe37698cf30d2c6998cf3b77cc18841b81`,
`SHA256SUMS.json` sha256 `8a7ef7f347b5bef019b83386485a6ee47cfcba31d85474aba535ca06a7bbbc1d`.
재계수: `scripts/egonav_far_diag_recount.py --frames` → `recount_far_diag_range_01.json`
(400행 원본만 읽고, 프레임은 원인 확인용). 정지 측정이라 tick0은 첫 물리
step 이전 렌더로 물리 정착 뒤와 원거리 기하가 조금 다르므로(4.5 m에서
프레임 hue 유효 픽셀 86.8% vs 63.3%), 판정은 안정 상태(tick 1–99)
기준으로 한다.

| 시작(중심/가장자리) | 존 마킹 검출(안정) | area_m2 min/median/max | 픽셀 min/median/max | hue | 단축/장축 m (median) | tick0 | 판정 |
|---|---|---|---|---|---|---|---|
| 4.000/3.618 m | **0/99** (전체 1/100) | 0.5306(1틱) | 893 | 12 | 0.681/1.101 | accepted | 안정 상태 `metric_size` 99/99 거부. tick0만 관문 근접 통과 |
| 4.500/4.111 m | **100/100** | 0.1722/0.1987/0.4224 | 237/269/533 | 12 | 0.447/0.644 | accepted | 진짜 표시. 면적은 0.10 m² 관문의 1.7–4.2배 |
| 5.000/4.606 m | **0/100** | 수용분 없음(화물만) | — | 1 | — | — | 존 마킹 성분 없음. 화물 hue 1(1.43 m, 0.0100 m²)만 |
| 5.500/5.102 m | **0/100** | 수용분 없음(화물만) | — | 1/25 | — | — | 존 마킹 성분 없음. 화물 hue 1(1.97 m, 0.0117 m²)·화물 hue 25(1.29 m, 0.0095 m²)만 |

* 4.0 m는 100틱 모두 `before_metric=1`(후보 성분 존재)이다. tick0만
  accepted(0.5306 m²·893 px·hue 12·단축 0.681 m로 관문 0.72에 근접)이고,
  ticks 1–99는 전부 `metric_size` 거부다(99/99). 안정 상태 기준 4.0 m는
  검출 실패로 본다.
* 4.5 m는 100/100 수용. hue p10=p90=12, 평가용 world 투영상 존 A 중심에서
  0.217–0.235 m(원거리 투영 편향 포함)로 진짜 표시다. 이번 측정에서
  **검출된 가장 먼 시작**이다.
* 5.0/5.5 m에서 수용된 성분은 존 마킹(hue 10–16)이 아니라 화물
  (빨강 hue 1, range 1.43/1.97 m; 노랑 hue 25, range 1.29 m)뿐이다.
  회수 프레임 색 표본에서도 hue 25는 노란 화물이었다(peer 아님).
* **원인(면적·픽셀 임계값 아님):** 바닥 투영 `floor_intersections`의 유효
  조건 `direction_z < -downward_min`(0.05)과 카메라 높이 0.2309 m 때문에
  유효 바닥 영역이 제한된다. 카메라 모델(`camera_v3`) 계산으로 유효 바닥
  픽셀 269137/307200(87.6%), 중앙 열 최상단 유효 바닥 range 4.785 m,
  프레임 전체 최대 5.69 m. 존 마킹 코너의 카메라 거리는 4.0 m
  3.494–4.356(전부 유효), 4.5 m 3.987–4.852(일부), 5.0 m 4.482–5.348,
  5.5 m 4.978–5.845다. 회수 프레임에서 hue 11–15 픽셀 중 유효 바닥 영역
  안 비율(tick50): 4.0 m 956/956=100%, 4.5 m 346/547=63.3%(tick0 86.8%),
  5.0 m 0/402=0%(tick0 16.4%), 5.5 m 0/334=0%(전 틱). 즉 5.0 m 이상은
  존 마킹 픽셀이 카메라 영상에는 보이지만(5.0 m 402 px, 5.5 m 334 px)
  유효 바닥점이 하나도 없어 마스크 단계에서 전부 제외된다. 현행 투영
  규칙에서는 검출이 불가능하고, 0.10 m² 관문을 낮추거나 0.10 m² 미만
  후보를 추적해도 복구할 수 없다.
* **6.0 m 미측정 사유:** 이 문 통과 시선에서 지도상 합법 시작 최대는
  ~5.58 m(서벽 안쪽 면 x=-1.025 m − 로봇 외곽 반경 0.1582 m)라 5.5 m가
  가장 먼 합법 시작이다. 게다가 위 유효영역 컷(중앙 열 4.785 m) 때문에
  6.0 m는 애초에 검출 불가라, 실측해도 판정을 바꿀 수 없어 하지 않았다.

### 판정 — far 검출 프로필 미승격, 4.0 m 한계 유지

사용자 결정 규칙("4.5–6 m에서 픽셀·면적·hue가 버티면 새 기본 off 검출
프로필로 승격, 무너지면 4 m가 물리 한계")에 대한 답:

* 4.5 m는 버틴다(100/100, 면적 관문의 1.7배 이상, hue 12 일정). 단일
  여유점으로 기록한다.
* 5.0/5.5 m는 무너진다(존 마킹 0/100). 원인은 검출 임계값이 아니라 바닥
  투영 유효영역(카메라 높이·피치·`downward_min` 조합)이다.
* 따라서 **새 far 검출 프로필은 승격하지 않는다.** 제어 기본
  `max_range_m=4.0`·0.10 m² 관문·기본 off `egonav_far_candidate_v1`를
  그대로 두고, 새 상수·새 프로필을 만들지 않았다. 4.0 m가 현행 검출의
  한계이고 4.5 m 1점은 "클램프만 풀면 닿는 여유"로 기록만 한다(승격 아님).
* 5 m 이상을 보려면 카메라 피치/높이 또는 바닥 투영 규칙(`downward_min`)을
  바꾸는 별도 장면·검출 설계가 필요하다. 이번 범위 밖이라 바꾸지 않았다.

### 검증 범위

* 1–4단계를 수행했다. 16세계 전체 관문은 돌리지 않았고, 4세계
  프로브(3단계)·거리 진단(4단계)은 gate-09(16세계)와 별개 조건이라
  합산하지 않는다.
* 오프라인 단위 시험 9개(`tests/test_egocentric_goto.py`)만 로컬에서
  통과했고, 물리 검증은 gcp4 원본으로 위 표를 다시 센 것이다.
* Mac 회수분은 SHA256SUMS.json 대조로 검증했다(off-03 9/9, on-03 9/9,
  visual 8/8, far-diag-range-01 21/21; 영상·재생 산출물은 게이트 SUMS
  이후 생성이라 별도 해시).
* 4단계 재계수는 회수 원본 `detect_probe.json`만 읽어(400행) 표를 다시
  만들었다. 프레임 기반 유효영역 비율은 회수 JPEG를 얼린 `camera_v3`
  바닥 투영으로 계산했으므로 JPEG 양자화로 경계값이 수 픽셀 흔들린다.
  표의 검출·거부 수와 거부 사유는 원본 JSON의 `diagnostics` 기록이다.
* 3단계 off/on 프로브는 source aa5d503e 결과다. far 후보 hue 기준을
  교체한 c4256a3fb 기준의 off/on 재측정은 하지 않았다(4단계는
  c4256a3fb). far 후보는 승격하지 않으므로 3단계 수치는 비교 근거로만
  남긴다.
* 원본: VM `/home/ugrp/ugrp-sim/runs/egonav/far-probe-off-03`,
  `far-probe-on-03`, `far-visual-01`, `far-diag-range-01`. Mac
  `outputs/egonav-far/`의 같은 이름(4단계는 `raw/far-diag-range-01/`).
* gcp4: 3단계 뒤 egonav 리스를 제거하고 2026-10-18 01:11 KST에 정지했다.
  4단계 진단을 위해 01:18–01:21 KST 재가동했고, 완료 뒤 리스가 없고
  실행 프로세스 0임을 확인한 상태에서 01:28 KST `TERMINATED`로 정지했다
  (원본 디스크 보존). 다른 GCP 프로젝트 결과와 합산하지 않는다.
* PR: #587 (draft). 사용한 새 실행 번들·runnable ID는 없다.
