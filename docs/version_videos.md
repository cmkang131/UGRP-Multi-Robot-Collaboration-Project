# 버전별 대표 영상 색인 (제출·보고용 후보)

2026-09-29 사용자 요청: 제어기/정책 버전마다 대표 영상 1개와 그 자료를 남긴다. 나중에 제출 영상과 보고서 그림으로 쓰기 위해서다. 이 문서는 색인이고, 영상 파일·해시·원자료 경로의 근거는 [실험 기록](../experiments/2026-09-29-version-videos/README.md)에 있다.

**영상은 stage probe를 다시 그린 것이다.** 위에서 본 그림은 정답 위치(평가용, 로봇 입력 아님)를 그린 도식이며 top 카메라 영상이 아니다(probe는 공용 top 카메라 프레임을 저장하지 않는다). 아래 곡선은 로봇이 추정한 yaw 불확실도 σ다. E2E 성공, 학생 성공, 성공률이 아니다.

## 대표 케이스 선택 규칙

1. **그 버전의 가장 전형적인 결과 1건.** 그 버전이 가장 자주 낸 판정(성공만 고르지 않는다. 그 버전의 기준선이 실패 위주면 전형적인 실패)을 낸 단계·셀에서 고른다. 사전 지정 seed(911)와 `nominal` 또는 그 코호트의 기준 셀을 우선한다.
2. **새 버전은 이전 버전이 실패한 같은 case를 쓴다(paired).** 같은 단계·leg·셀·seed로 두 실행을 나란히 그린다. 같은 셀의 다른 seed·셀 결과를 행에 함께 적어, 고른 case가 예외가 아님을 보인다.
3. **고른 이유와 예외를 행에 적는다.** raw가 없거나 `pf`/σ 기록이 없으면 그 행은 `raw 없음`으로 두고 억지로 만들지 않는다. 진행 중인 실행의 case는 실행 상태를 함께 적는다.
4. **일반화하지 않는다.** 행의 "일반화하지 못하는 것" 칸에 이 한 케이스가 보이지 못하는 것을 적는다.

## 저장 규칙

- 커밋하는 영상은 파일당 1 MiB 미만, 실험당 5 MiB 미만이다. 넘으면 `--width/--height/--fps/--dt/--crf`를 낮춰 다시 만들고, 고해상도 원본은 기본 체크아웃 `outputs/`에 두고 sha256만 남긴다(디스크 규칙: [디스크 관리](disk_management.md)).
- 행마다 원자료(case 폴더의 `result.json`, `eval_only/trace.jsonl`, `robots.json`) 경로와 sha256을 남긴다. `outputs/`는 로컬 보관이며 원격 백업이 아니다.
- 새 정책·번들 버전을 등록하고 측정 기록을 남길 때 이 표에 대표 영상 행을 채운다(CONTRIBUTING의 증거 절 참고).

## 색인

도구: `scripts/render_pair_probe_video.py`(matplotlib·ffmpeg 필요, 물리 실행 없음). 모든 영상을 다시 만드는 명령:

```
OUT=/Users/changmin/projects/ugrp/outputs bash experiments/2026-09-29-version-videos/build_videos.sh [출력 폴더]
```

영상 파일은 모두 `experiments/2026-09-29-version-videos/videos/`에 있다.

| 버전 | 실행 소스(SHA) · 번들 | 대표 case (paired) | 결과 (sim 시간) | 영상 · sha256 | 무엇을 보여주나 | 일반화하지 못하는 것 |
|---|---|---|---|---|---|---|
| **b-v6c** 운반 | `b604499d`(clean, probe 0.4.1) · v76 | 운반 leg 1, nominal, seed 911 | 실패 `SELF_POSE_UNCERTAIN`(yaw), 8.8 s에 σ가 게이트 52.4 mrad에 닿음 | `carry_L1_nominal_s911_v6c_topdown.mp4` `56063b7e…ffcc0` | 운반 명령 2.7 s 만에 σ가 게이트에 닿는 기준선 실패 | 한 케이스. 33건이 같은 원인이라는 것은 v6c-carry 기록의 결과이며 이 영상이 보이는 것이 아님 |
| **b-v6d** 정렬 | `052e3eba`(source_dirty, probe 0.4.0) · v76 (병합 트리 `4714263a`는 v80) | 정렬 yaw+/opp, seed 911. b-v6c(`b5234b7a`)와 paired | b-v6c `ALIGN_RELOOK_NO_FIX`(stage 20.5 s) → b-v6d 통과(36.1 s) | `align_yawp-opp_s911_v6c_vs_v6d_topdown.mp4` `efc276c5…d0ab2` | 같은 셀에서 실패가 통과로 바뀜. σ는 게이트보다 아래(원인 아님) | 운반 raw 없음(v6d는 운반 미측정). 정렬 영상은 위치 그림에서 차이가 거의 안 보여 **제출용으로는 약함**. 이 셀 하나이며 v6d 정렬 25/25는 v6d 기록을 따름 |
| **b-v6e-base**(예전 `b-v6e`) 운반 | `d08818ef`(source_dirty, probe 0.6.0) · v80 | 운반 leg 1, lat−/opp, seed 911 (같은 leg 5건이 모두 같은 결과) | 실패 `SELF_POSE_UNCERTAIN`(yaw), 28.6 s에 σ가 게이트에 닿음(σ 최댓값 52.6 mrad) | 아래 b-v6e yaw 수정과 같은 영상의 왼쪽 열 | 운반 leg 1 전 구간에서 σ가 서서히 올라 게이트에 닿음 | 한 케이스. cal L1·L2 5건씩 모두 같은 원인이나 PF seed는 독립 반복이 아님 |
| **b-v6e** yaw 수정 운반 | `f2186414`(source_dirty, probe 0.7.0) · v80. **실행 진행 중**(cal 40건 전체 판정 미완) | 같은 case: 운반 leg 1, lat−/opp, seed 911 (b-v6e-base와 paired) | 통과, 31.3 s 완주. σ는 완주 시 약 40 mrad(게이트 여유 약 12 mrad) | `carry_L1_latm-opp_s911_v6e-base_vs_v6e-yaw_topdown.mp4` `d7dc208f…20e7ad` (+ 손목 카메라 `…_wrist.mp4` `f94a8563…e905d`) | 수정이 σ 증가를 **늦춘다**(없애지 않는다). 곡선은 통과 때도 계속 오름 | 이 leg 하나 한 seed. 성공의 일반화가 아님. cal 40건 판정은 진행 중이며 격자·held-out 없음. 종료 시점 추정-정답 yaw 차는 r1 −62, r2 −100 mrad로 크다(result.json) |
| v5h·b-only·a+b·b-boot·b-v6b | – | – | – | – | – | **이번에 백필하지 않았다**(v6c 이후만 다룸, raw 존재 여부도 확인하지 않음). 필요하면 이 표에 행을 추가한다 |
| b-v6f(내려놓기) 등 다른 단계 | – | – | – | – | – | 내려놓기·파지 단계의 대표 영상은 아직 없다 |

각 행의 원자료 경로·`result.json`/`trace.jsonl`/`robots.json` sha256·소스 manifest 상태는 [실험 기록의 원자료 표](../experiments/2026-09-29-version-videos/README.md#원자료와-해시)에 있다. 영상 sha256은 앞·뒤 8자리만 줄여 적었고 전체 값은 같은 실험 기록에 있다.

## 새 영상을 추가하는 방법

1. 대표 case를 위 규칙으로 고른다(paired 상대가 있으면 같은 셀·seed).
2. `python3 scripts/render_pair_probe_video.py --case <이전 case> --label ... --case <새 case> --label ... --output <mp4>`. `--pf-track`으로 돌린 실행은 σ가 `trace.jsonl`의 PF에서 나오고, 없으면 `robots.json` 보고로 대신한다(영상 안에 출처가 적힌다). 정렬처럼 σ 게이트가 종료 원인이 아닌 단계는 `--gate none`.
3. 파일 크기와 sha256을 확인하고 `experiments/<ID>/videos/`에 넣는다. 이 표에 행을 추가한다.
