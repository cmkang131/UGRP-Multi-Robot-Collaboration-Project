# R4 자기지도 관문 공식 재계수 (비물리, Mac)

라벨: **R4 = attempt**, `queue.round=3`, source `718777118be41991156b047faff78621969101bb`,
host gcp6, nworld 2, smoke 30 SIM s `cap_end`, physics `mjwarp_batch_v1`,
contact `warp_native_contact_v1`, keyframe policy **`elapsed_sim_v1`**.
원본: `gcp6:/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run` (Mac 사본 `/tmp/e2ewarp-r4-raw`).
이 재계수는 물리·모델을 import하지 않는 Mac 스크립트
`scripts/e2ewarp_selfmap_recount.py`로 원본 JSON만 읽어 수행했다.

## 1. funnel (원본 재계수)

| stage | cumulative_pass_n | rejected_n |
|---|---:|---:|
| own_rgb | 1806 | 0 |
| qualified_unloaded_FK | 1806 | 0 |
| settled_scan | 48 | 1758 |
| observed_wall_contacts | 48 | 0 |
| **inserted_keyframe** | **48** | 0 |

per-stream 6개(world0/1 × r1/r2/r3) 모두 `frames=301, qualified=301,
settled=8, **inserted=8**`, 삽입 ticks `[24,71,124,148,195,224,248,295]`.

## 2. `elapsed_sim_v1` 검증 (원본에서)

| 항목 | 값 |
|---|---:|
| keyframe insertions | 48 (R3: 0) |
| `keyframe_insertions_gt_zero` | true |
| **old `tick % 10 == 0` 게이트가 놓쳤을 삽입(off-grid)** | **48** |
| elapsed-cadence 위반 (`gap < 10 ticks`) | 0 |
| 삽입 간 tick gap (min/median/max) | 24 / 47 / 53 |

→ **elapsed_sim_v1 GPU 재검증 통과**: 삽입 48>0, 48개 전부 old modulo 게이트가
놓쳤을 프레임이고(즉 R3의 inserted 0 결함을 실제로 제거), 1 SIM초 cadence 위반 0.

Lead 1차 재계수와 대조: funnel·keyframes·per-stream 삽입 수 일치. 차이는
**off-old-modulo 0 → 48** 하나인데, 1차 때는 localization row에 `tick` 필드가 없어
(이 raw는 `sim_s`만 기록) gap 계산이 비어 있었고, 이 공식 재계수는 `sim_s*10`으로
10Hz 프레임 clock을 유도해 계산했다. 결론(재검증 통과)은 바뀌지 않는다.

## 3. 런 지표 (Lead 1차 요약 대조용, 원본 result/eval)

18 LLM calls·18 model_calls·오류/429 0·이미지 18·prompt 78,120·cache 23.68%·
wall 363.64s·wall/(SIM·world) 6.0607·`E2E_success=false`·`student_execution=false`.
의존성: ACT/loaded FK/mapbuild8 correction/release **waiting** (그대로).

## 4. visdet GPU 프레임 재생 검증 (새 실행 없음)

`scripts/e2ewarp_visdet_replay.py`로 R4의 기록된 own RGB 2Hz review frames
(`world-00/review-rgb`, r1/r2/r3, 183장)을 발행 명령 FK(`servo_fk_v1`) + 고정
fisheye 보정으로 만든 카메라 모델에 재생했다(Mac CPU, 2.66 s).

| 항목 | 값 |
|---|---:|
| frames | 183 |
| command-row-missing (t=30.0은 명령 로그가 29.9까지) | 3 |
| uncapped detector: observed | **180** (전부 floor colour) |
| uncapped component 예 | 185,765 px, bbox 582x334, extent 4.05 m, range 0.43-0.48 m |
| extent cap(2.0 m) 적용: observed | **36** (near-floor truncated patch), rejected extent 144 |
| arrival evidence | 0 |

**관측 결함**: GPU 렌더 프레임에서는 **바닥이 채도 높은 파란색**으로 렌더되어
CPU 원본에서 쓰던 visgoal 파란색 밴드(hue 104-120)가 floor를 zone paint로
오인한다(uncapped 180/183). zone 크기 기반 extent cap(zone 대각 1.52 m 근거로
2.0 m)을 넣으면 144건이 거부되지만, 화면 하단에 잘린 near-floor 조각 36건은
여전히 통과한다. R4 smoke 프레임에는 **zone B paint가 보이는 프레임이 없어**
GPU 렌더의 zone 외관을 이 원본으로 보정할 수 없다.

→ `navigation_factory`에 visdet를 연결해 **도착 판정**을 쓰려면 GPU 렌더에서
zone paint가 보이는 프레임(동쪽 방 도달 프레임 또는 별도 정적 캘리브레이션 캡처)이
먼저 필요하다. 그 전까지 모듈은 기본 off이며, replay 검증 범위는 "GPU 렌더
프레임에서 모듈이 동작하고 근거/reason을 남긴다"까지다(도착/임무 성공 주장 아님).

## 5. 재현

```
python3 scripts/e2ewarp_selfmap_recount.py \
  --raw /tmp/e2ewarp-r4-raw --output <out>/recount.json \
  --prior experiments/2026-10-17-e2ewarp/r3/rejection_table.json
python3 scripts/e2ewarp_visdet_replay.py \
  --raw /tmp/e2ewarp-r4-replay --output <out>/visdet-replay.json
```
`visdet-replay-uncapped.json`은 extent cap 진단용(비공식)이다.
파일 해시는 `SHA256SUMS.json`에 있다.

Produced with DeepSeek Harness. https://github.com/deepseek-ai/deepseek-harness
