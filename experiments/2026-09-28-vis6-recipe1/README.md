# VIS6 — 레시피 1 "정직한 갱신" 사전 계획과 재생 결과 (dev 전용)

- 상태: **2026-09-29 재생·채점 완료. 사전 규칙상 채택 후보 없음, b0(VIS3 a1 = T0) 유지.** 결과는 아래 "재생 결과" 절에 있다. 그 아래의 사전 계획 본문은 재생 전 기록 그대로 둔다.
- 이슈: [#216](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216). 근거: `outputs/lit-review-tagfree-localization-20260928.md` 6.1절(1순위 레시피).
- 기준 SHA: `d5bd208e` (origin/main). 브랜치 `claude/vis6-recipe1`. 재생은 이 PR의 최종 커밋 SHA에 고정해서 실행한다.
- 기계 판독 계획: [`plan_v6.json`](plan_v6.json). 후보 29개 + 중립 재현 전용 `T1c_inert` 설정 1개: [`configs/`](configs/). 둘 다 [`make_plan_v6.py`](make_plan_v6.py)가 결정적으로 만든다. 테스트가 바이트 단위 재생성을 확인한다.

## 재생 결과 (2026-09-29, Claude `claude/vis6-replay`)

**결론: 사전 규칙상 채택 후보가 없다. b0(VIS3 a1 = T0)를 유지한다.** 정지 규칙 2(S2 검출기 관문 실패 → 1c·1a 제외)와 규칙 3(S1 적격 η 없음)이 걸렸다. 그래서 S4를 건너뛰었고, F에 올릴 후보가 없어 validation 관문(F)은 실행하지 않았다(규칙 4). 격자·임계값·규칙은 이 코호트에서 다시 조정하지 않았다.

### 실행 조건

| 항목 | 값 |
|---|---|
| 소스 | `7f649959`(origin/main, PR #253 병합 포함). 계획 revision 2의 모듈 해시 16개·설정 해시가 모두 일치(`run`이 단위마다 확인). clean committed sparse worktree `ugrp-wt/claude-vis6-replay` |
| 명령 | 위 "관리자용 후속 재생 명령"을 순서대로 옮긴 [`run_driver_20260929.sh`](run_driver_20260929.sh). 차이는 `VL_JOBS=3`(물리 stage-probe 작업과 Mac 공유), 단계 사이 정지 규칙·예산 자동 판정, CPU 시간 기록뿐이다. `ugrp_session.py run vis6-replay`로 실행 |
| 물리·잠금 | MuJoCo 적분·렌더·신경망 추론 0. 저장 관측 캐시·JPEG·자기 명령만 읽는 오프라인 재생이라 `agent_lock` 대상이 아니다(시간 측정 실험도 아님) |
| 전원·디스크 | AC 전원(`pmset`), 여유 104 GiB |
| 시간·CPU | 17:19–21:52Z(4.5 h 벽시계). 계획 부분 **10.54 CPU-h**(user+sys, `/usr/bin/time`), 보충 0.91 CPU-h. 예산 40 CPU-h 이내 |
| 부하 | 단위 시작·끝 1분 부하 433회 기록: 최소 8.2, 중앙 26.0, 최대 92.2(다른 작업 포함). [`results/load.txt`](results/load.txt) |
| raw | `/Users/changmin/projects/ugrp/outputs/vis6-recipe1-20260929/`(875 파일, 378 MB, 로컬만). 파일별 sha256: [`results/raw_manifest.json`](results/raw_manifest.json) |
| 실행 단위 | 계획 199 + 보충 15 = 214 단위, 실패 0 |

### P0 재현 — 통과

- 첫 단위 s909 k=0: T0 대 저장 VIS3 a1 3,596프레임 불일치 0, T1c_inert 대 T0 불일치 0.
- fit 6회 k=0: T0 대 a1 불일치 0([`results/P0_reproduce_fit.json`](results/P0_reproduce_fit.json)).

### fit 결과 (6회, 회차당 14,236프레임, PF seed 0–2 평균)

| 후보 | XY 95% 포함률 | >3σ | XY NLL | 소실(>30 cm) 프레임 | 문 위치 p90 | 문 횡 p99 | 문 yaw p90 | σ p90 적재 / 무적재 | 사건 / 사건 프레임 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **T0 (b0)** | **55.1%** | 33.8% | 748 | **3,962 (27.8%)** | **6.69 cm** | 4.46 cm | 1.98° | 6.1 / 6.4 cm | 3.3 / 3,977 |
| T1b η=.5 | 57.8% | 35.0% | 728 | 3,866 (27.2%) | 5.89 | 3.60 | 2.00 | 6.4 / 8.5 | 5.3 / 4,105 |
| T1b η=.25 | 51.5% | 38.3% | 654 | 4,328 (30.4%) | 5.10 | 3.81 | 1.91 | 7.0 / 11.2 | 8.7 / 4,700 |
| T1b η=.125 | 44.1% | 44.6% | 549 | 4,781 (33.6%) | 5.16 | 6.07 | 2.32 | 8.9 / 12.0 | 9.0 / 5,258 |
| T1c (1c만) | T0와 모든 값 동일 | | | | | | | | |
| T1ac d2 a3° | 44.6% | 46.1% | 692 | 5,431 (38.1%) | 5.89 | 4.21 | 1.81 | 6.6 / 15.0 | 11.0 / 5,527 |
| T1ac d2 a6° | 44.6% | 46.1% | 685 | 5,431 | 5.89 | 4.21 | 1.81 | 6.6 / 15.3 | 11.0 / 5,527 |
| T1ac d5 a3° | 45.9% | 45.7% | 576 | 5,456 | 5.33 | 4.40 | 1.99 | 6.7 / 20.5 | 12.7 / 5,400 |
| T1ac d5 a6° | 47.1% | 44.3% | 567 | 5,321 | 5.33 | 4.40 | 1.99 | 6.7 / 23.7 | 13.7 / 5,213 |
| T1ac d10 a3° | 50.1% | 40.6% | 633 | 5,154 | 5.56 | 3.15 | 1.70 | 6.4 / 27.7 | 12.3 / 4,966 |
| T1ac d10 a6° | 53.5% | 37.8% | 627 | 5,046 | 5.56 | 3.15 | 1.70 | 6.4 / 37.5 | 11.7 / 4,489 |

전체 수치(yaw 지표·seed SD·회차별 NLL 포함)는 [`results/metrics_fit_S1_S3.json`](results/metrics_fit_S1_S3.json)(sha256 `3a6d6ae1…`)에 있다. 문 근처 프레임은 seed당 634개다.

**단계별 판정**

- **S1(η):** 적격 없음. 포함률이 44–58%로 [90, 99]% 대역에서 멀다. η를 낮추면 오히려 포함률이 떨어지고 소실이 늘었다([`select_S1.json`](results/select_S1.json)). NLL이 내려간 것은 소실 회차의 큰 항이 줄어든 결과이고 정확도 개선이 아니다.
- **S2(1c 검출기): 관문 실패.** 프레임 쌍 10,696개 중 양성 960개. 판정은 **전부 `unknown`**(stall 0, moving 0)이라 recall 0, precision 정의 불가([`select_S2.json`](results/select_S2.json)). 이유 기록: `few_textured_floor_points`가 대부분이고(쌍마다 체커 경계 표본 중앙값 **0점**, 필요 150점), 나머지는 `not_a_static_arm_pair`다. README의 "칸이 커서 경계가 없는 프레임은 unknown" 위험이 전면적으로 현실이 됐다. 그래서 T1c는 T0와 비트 단위로 같은 추정을 냈다.
- **S3(게이팅):** 계산상 6개 모두 정확도 악화 한도 안이고 `T1ac_d05a6`가 NLL 최소였다([`select_S3.json`](results/select_S3.json)). 하지만 규칙 2로 제외했다. 1c가 항상 보류한 상태의 게이팅이라 사실상 명령 적분 이동만으로 연 게이트이고, 소실은 오히려 27.8% → 35–38%로 늘었다.
- **S4·F:** 실행하지 않았다(규칙 2·3·4).

### 보충: T0 validation (계획 밖 기술 통계, 선택에 쓰지 않음)

F가 열리지 않아 계획상 validation 채점은 없다. 태그 없는 위치 추정이 공동 운반에 충분한지 답하려고 T0만 validation 3회 × PF seed 0–4로 같은 소스에서 따로 돌렸다. 저장 a1과의 재현 불일치는 0이다([`results/SUPP_P0_reproduce_val.json`](results/SUPP_P0_reproduce_val.json)).

| T0 validation (회차당 6,197프레임, seed 0–4 평균) | 값 |
|---|---:|
| XY 95% 포함률 / >3σ | 65.3% / 26.2% |
| 소실(>30 cm) 프레임 | 919 (14.8%, 전부 s945) |
| 문 위치 p90 / 문 횡 p99 / 문 yaw p90 | **13.1 cm / 14.4 cm / 4.46°** |
| σ p90 적재 / 무적재 | 6.2 / 6.1 cm |

[`results/SUPP_metrics_val_T0.json`](results/SUPP_metrics_val_T0.json)(sha256 `5bfb6136…`).

### 사후 진단 (사전 등록 아님, 선택에 쓰지 않음)

[`posthoc_v6.py`](posthoc_v6.py) → [`results/posthoc_v6.json`](results/posthoc_v6.json). GT는 채점·표지에만 썼다.

1. **소실은 "끼임" 두 회차에 몰려 있다.** fit에서 교사가 접근점에 끼인 s909·s941(교사 결과: s909 "SIM 한도(접근점에서 끼임)", s941 "SIM 한도(끼임)", `../2026-09-26-vision-loc/README.md`·`README_v3.md`)의 프레임 55%가 소실이다. 나머지 4회(s910·s911·s942·s943)는 소실 0%, 오차 p50/p90 **3.8 / 10.4 cm**, 포함률 76.5%다. η=.5는 이 4회에서 포함률만 83.5%로 올린다.
2. **끼인 동안 필터는 명령을 따라 수 m를 흘러간다.** T0 seed0에서 s909 133–611 s 동안 실제 이동 0.6 cm, 추정 이동 **19.0 m**, 자기 전진 명령 4,780개, σ 중앙값 5.0 cm, 최대 오차 3.16 m. s941 72–382 s도 실제 3.4 cm, 추정 4.9 m, 최대 2.24 m다. 오차는 m 단위인데 σ는 수 cm라 과신이 된다. 1.2절(선행 조사)의 가설이 dev 전체에서 확인됐다.
3. **출발 dock에서는 충분하다.** 첫 주행 명령(2.7 s) 직전 T0는 6회 × 3 seed에서 오차 0.7–6.7 cm, yaw 오차 ≤ 1.8°, σ 5.8–11.2 cm, yaw σ ≤ 1.9°였다. #261의 guard 상한(0.15 m, 0.20 rad) 아래다. 단 이 재생은 **정답 dock 행을 사전분포 중심으로 받았다**(`spawn_y`, σ 0.15 m/10°). #261의 세 행 혼합 사전분포는 시험하지 않았다.
4. **이미 있는 경계 관측만으로 끼임이 보인다.** 같은 팔 명령·정착한 연속 프레임에서 캐시된 벽-바닥 경계 행의 중앙 변화는, GT 정지인데 추정이 움직인 쌍에서 p50 0–0.002 px(p90 ≤ 0.06 px), GT 이동 쌍에서 p50 0.035–1.0 px였다. s909·s941에서는 20배 넘게 갈린다. 렌더에는 센서 잡음이 없으므로 실제 카메라 임계값은 정지 프레임의 잡음 바닥으로 다시 정해야 한다. 다음 레시피의 근거로만 쓴다.

### 태그 없는 위치 추정이 공동 운반 단계에 충분한가

**아직 아니다.** 기준은 VIS2 사전 등록 문 게이트(위치 p90 ≤ 5 cm, 횡 p99 ≤ 6 cm, yaw p90 ≤ 3°)와 #261 guard(σ ≤ 0.15 m/0.20 rad)다.

- 문 통과: fit T0 문 위치 p90 6.7 cm(실패), validation 13.1 cm·횡 p99 14.4 cm·yaw 4.5°(모두 실패). 문 게이트를 통과한 설정은 없다.
- 과신: 끼임이 생기면 σ 5 cm로 2–3 m 틀린다. 실행기 σ guard가 이 상태를 막지 못한다. fit 소실 27.8%, validation 14.8%.
- 출발: 정답 행 사전분포에서는 guard를 넘는다(위 3). 세 행 혼합은 미검증이다.

### 다음 레시피 (조사 결과, 구현하지 않음)

같은 방법으로 두 번 막혔다(VIS4·VIS5 보고 σ 보정, VIS6 온도·게이팅·바닥 정지 검출). 전역 지침에 따라 선행 방법을 다시 조사했다. 기존 조사(`outputs/lit-review-tagfree-localization-20260928.md`)에 아래 원문 확인을 더했다.

| 방법 | 원문에서 확인한 것 | 우리에게 주는 것 |
|---|---|---|
| 평면도 가장자리 MCL, Boniardi 외 IROS 2019 [본문] | CNN 방 배치 가장자리 + 평면도 투영점의 거리 변환 우도(σz 10 px, 포화 δ 25 px), 이동 25 cm/15° 게이팅. 초기 자세 10 cm·15° 안에서 시작. 평균 선 RMSE **22.7 ± 13.7 cm**, 문 통과 때 일시 소실 | 평면도 단안 가장자리만으로 보고된 정확도는 dm급이다. 문 게이트(cm)는 전역 PF만으로 닿기 어렵다 |
| 문기둥 시각 서보, Pasteau 외 RAS 2016 [본문-부분] | 가장 가까운 **문기둥 하나**의 영상 직선으로 Lyapunov 제어. "서보 과정에 오도메트리와 지도를 쓰지 않는다" | 문 통과를 전역 자세 정확도 문제가 아니라 **문기둥 상대 측정** 문제로 바꾼다 |
| OpenVINS 영속도 갱신 [문서] | IMU χ² 검사 외에 추적 특징의 평균 영상 disparity가 임계값보다 작으면 정지로 보고 영속도 의사 측정을 넣는다 | 바닥 무늬가 아니라 **이미 추적 중인 관측의 disparity**로 정지를 판정한다 |
| ZUPT, Foxlin 2005; 고착 검출, Ward·Iagnemma 2008 (기존 조사) | 정지 구간 검출 → 의사 측정, 운동학 속도 대 관측 속도 불일치로 고착 판정 | 위와 같은 구조 |
| 초음파 MCL, Burguera 외 2009; 빔 모델, Thrun 외 *Probabilistic Robotics* 6장 (기존 조사) | 초음파 판독의 확률 모델과 격자 지도 정합 | #221에서 허용된 전면 초음파가 전진 방향 관측과 끼임 검출을 동시에 준다 |
| ORB-SLAM2 localization mode(Mur-Artal·Tardós T-RO 2017), ORB-SLAM3 Atlas(Campos 외 T-RO 2021), Visual Teach & Repeat(Furgale·Barfoot JFR 2010) [초록·검색요약] | 사전 시각 지도에 대한 재위치·경로 반복 | **보류.** 무늬 없는 벽과 0.57 m 체커에서 특징이 부족하다. 시각 외관 지도는 AGENTS.md의 허용 정적 지도 목록에 없으므로 사용자 결정이 필요하다 |
| 하향 카메라 상관 VO, Nourani-Vatani 외 JFR 2011 [초록] | 바닥을 수직으로 보는 카메라의 템플릿 상관 | **기각.** 우리 카메라는 하향이 아니고, VIS6 1c가 같은 바닥에서 100% 보류했다 |

**VIS7 레시피 초안 — "움직임 일관성 우선"** (새 사전 계획·새 번들 ID로 등록한 뒤 구현한다)

1. **R1 경계 disparity 정지 검출(오프라인 검증 가능, 신경망 추론 0).** 같은 팔 명령·정착한 연속 프레임에서, 캐시된 경계 행(`b_lo/t_lo`)의 측정 변화 중앙값 m과, 명령 적분 이동을 PF 평균 자세에서 같은 열 모델로 투영한 예측 변화 p를 비교한다. p ≥ 0.5 px이고 m ≤ 0.25p이면 `stall`, m ≥ 0.75p이면 `moving`, 나머지는 `unknown`. 임계값은 fit에서 정하고 실제 카메라용 잡음 바닥은 dock 정지 프레임(첫 1.8 s)으로 잰다. 판정의 적용은 VIS6 1c의 평균 이동 제거 경로를 그대로 재사용한다(OpenVINS, Foxlin). 관문은 S2와 같다(양성 ≥ 20, precision ≥ 0.8, recall ≥ 0.3).
2. **R2 끼임 인지 예측.** `unknown`인데 명령이 이어지면 예측 잡음을 명령 이동 거리에 비례해 키운다(Park·Moon 2026의 연속 확대, Ueda 외 2004 확장 리셋. 기존 조사 3.4절). 틀린 곳으로 흘러가도 σ가 오차를 덮게 한다.
3. **R3 η·게이팅 재시험은 R1 통과 뒤에만.** VIS6에서 둘 다 정지 검출 없이 소실을 늘렸다.
4. **R4 전면 초음파(#221, 새 렌더 필요).** Δ거리 대 명령 전진량으로 끼임을 검출하고, 빔 우도를 같은 η·게이트로 넣는다. 네 통신 조건에 똑같이 켜고 이전 baseline과 따로 비교한다. 오프라인 대용은 "합성 초음파"로 따로 표시한다.
5. **R5 문 통과는 문기둥 상대 측정으로.** 문 근처에서는 전역 PF 자세 대신 자기 RGB의 문기둥 직선(Pasteau 2016)으로 횡 오차와 거리를 재서 통과한다. PF는 문기둥이 보이는 곳(현재 비끼임 p90 10 cm면 충분)까지만 데려온다. 성공은 실제 통과로 따로 검증한다.
6. **평가:** 같은 fit/validation 분할과 VIS6 지표. 주 지표는 소실 프레임·포함률·끼임 구간의 최대 오차 대 σ다. 문 게이트는 R5의 폐루프 dev에서 따로 잰다.

### 공동 운반 출발 부트스트랩(#261, 태그 전용)에 필요한 것

1. **무태그 제공자.** 위 PF(T0 = VIS3 a1)를 하네스 제공자로 감싸 `initialize_from_prior`(세 dock 행 혼합, 가중치 포함)와 `PoseReport`(평균·공분산·informative fix 여부)를 구현해야 한다. 현재 #253 코드는 실험 재생기이고 이 계약이 없다.
2. **세 행 혼합의 오프라인 검증.** 같은 dev 렌더의 첫 정지 구간에서, 정답 행 대신 #261 사전분포(행 3개 × σ 0.5 m/0.5 m/15°)로 시작해 정답 행 질량과 σ가 guard 안으로 들어오는지 본다. 정답 행 사전분포에서는 이미 σ 5.8–11.2 cm였다. 기록된 dev 렌더에는 dock 팬 스캔이 없을 수 있으므로, 팬 스캔 효과는 #261 probe 경로에서 따로 잰다.
3. **끼임 검출(R1/R4)이 먼저다.** 부트스트랩이 풀린 뒤 접근점에서 끼이면 지금 PF는 σ 5 cm로 m 단위를 흘러가 guard가 막지 못한다.

### TensorBoard

- 스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-vis6-replay`(run 12개: 후보 11개 fit + T0 validation 보충, `collection.json` sha256 `f2e91db4…`). 파생 뷰 생성기 [`build_tb_views.py`](build_tb_views.py), 변환은 `scripts/export_offline_audit.py`.
- 검증: EventAccumulator로 다시 읽어 스칼라 468개를 원본 metrics JSON과 대조, 불일치 0([`results/tensorboard_verification.json`](results/tensorboard_verification.json)). 공용 서버(PID 9293, 재시작 안 함)의 `/data/runs`가 새 run 12개를 보여 주고, 스칼라 API 값이 원본과 같다.
- 대시보드: `outputs/tensorboard-view.json`의 `vis6_replay_20260929` URL(고정 카드 8개: 포함률, >3σ, 소실, 문 p90·횡 p99·yaw p90, 사건 프레임, 검출기 recall). 브라우저에서 "Pinned 8 cards"를 확인했다. 서버 run이 500개를 넘어 새 run은 기본 선택 해제 상태이므로 `0929-vis6-replay` run을 직접 선택한다. HParams 열은 `policy, case, split, seed, outcome`을 다시 적용한다. 성공률·명령 수·모델 호출·응답 시간 태그는 오프라인 재생이라 없다.

### 한계

- validation(s945–947)은 이미 본 dev다. 독립 test는 쓰지 않았다(`replay_v6.py`가 거부).
- 오프라인 재생이며 추정으로 로봇을 몰지 않았다. 문 게이트 판단도 오프라인 수치다.
- 사후 진단 1–4와 다음 레시피의 임계값은 이 결과를 보고 만든 것이다. 새 계획에서 사전 등록한 뒤 fit에서 다시 정해야 한다.

## 재생 전 재동결 (2026-09-28)

Claude가 시작한 PR #253을 **Codex가 이어서 수정**했다. 검토 기준은 `0687c620`, 원 검토는 기본 체크아웃의 `outputs/review-253-20260928.md`(P1 1건·P2 7건·P3 10건)다. 사용자 확인상 VIS6 실제 자료 재생은 아직 없으므로, 검토에서 발견한 결함을 고친 뒤 `make_plan_v6.py --out <새 임시 폴더>`로 설정과 계획을 재생성했다. 기존 FROZEN 계획·29개 설정은 [`pre_review_0687c620/`](pre_review_0687c620/)에 바이트 그대로 보존했다. 새 계획은 revision 2이며 이전 계획 SHA와 런타임 모듈 해시를 포함한다. 수정별 근거·검증·남은 제약은 [`review_fixes_20260928.md`](review_fixes_20260928.md)에 있다.

실행 번들 ID·workflow 버전은 새로 등록하지 않았다. 최종 환경은 표식 0개이며, 이 코드는 표식 검출을 입력으로 쓰지 않는다.

## 무엇을 바꾸나

VIS5 PF(`vision_pf_v5.py`) 위에 VIS6 하위 클래스를 얹는다. 세 구성요소는 설정 블록 `vis6`로만 켠다. 모두 끄면(`vis6` 없음, `{}`, `{"eta": 1}`) VIS5 객체 경로를 그대로 쓴다. 입자·가중치·난수 상태·보고값이 같다(테스트). 별도로 η=1·항상 unknown인 stall을 켠 VIS6 하위 클래스도 명령·재표본화·팔 변경·적재 전환에서 VIS5와 비교하며, 보고 x에 +1 m를 넣는 변이도 잡는다. VIS3/VIS4/VIS5의 기존 소스 파일은 한 바이트도 바꾸지 않았다.

| 구성요소 | 설정 | 동작 | 근거 |
|---|---|---|---|
| 1a 갱신 게이팅 | `vis6.gating` `{min_d_m, min_yaw_rad, min_servo_pulse, mode, max_interval_s}` | 마지막 적용 스캔 이후 **추정** 이동 ≥ d, 또는 yaw ≥ a, 또는 자기 팔·팬 명령 변화 ≥ Δpulse이면 비전 스캔 적용. 변화가 없어도 마지막 적용 뒤 2 s가 지나면 `timeout`으로 반복 횟수에 따른 할인 갱신. `skip`은 중간 반복을 버리고, `discount`는 k번째 반복을 1/(k+1)로 적용 | Nav2 AMCL `update_min_d/a`, CMU 16-831 강의 3 |
| 1b 우도 온도 | `vis6.eta` ∈ (0, 1] | 적용 스캔 로그우도 × η. 프레임 안 `effective_columns` 온도 위에 곱한다 | Thrun 외 AIJ 2001, Wu·Martin 2023 |
| 1c 영상 정지 검출 | `vis6.stall` (`vision_stall_v6.DEFAULT_STALL`) | 같은 팔 명령·정착·같은 짐 상태의 연속 두 프레임에서, 바닥 평면 워핑으로 예측 이동의 비율 s ∈ {0, .25, .5, .75, 1, 1.25}별 광도 잔차를 비교. s* ≤ .25이고 대비가 충분하면 `stall`: 몸체 좌표의 평균 이동만 제거하고 입자별 편차·과정 잡음은 보존. 속도는 50%만 감쇠. 연속 5회 뒤에는 보정 전 예측 사용 | Foxlin 2005, Ward·Iagnemma 2008 |

- 게이팅은 `stall`을 함께 켜야 하지만, **확정 stall의 첫 5프레임에서만 보정**된다. `unknown`(짐에 가린 바닥 포함), `moving`, 연속 상한 초과에서는 명령 적분 예측을 쓴다. 영상 이동 검증을 항상 보장한다는 이전 주장은 철회한다. `motion_by_verdict`로 판정별 이동 누적을 기록한다. unknown에 대한 정지 상태 유지(hysteresis)는 적용하지 않았다.
- 평균 이동을 되돌릴 때 그 구간의 예측 지도 벌점도 제거하고 보정한 입자 위치에서 다시 계산한다. 프레임 사이의 명령 분할도 누적한다.
- 1c는 자기 RGB JPEG·자기 명령·고정 카메라 보정만 쓴다. 분할 관측의 벽-바닥 경계 아래 행에 체커 색상 범위(조명 허용 오차 포함)와 주변 유효 화소 마스크를 추가한다. 컬러 상자·도색은 보수적으로 제외한다. 잔차는 양끝 10% 절사 평균이며, 개별 표본에서 정지·이동 지지가 각각 25% 이상이면 `unknown`이다. 질감 부족·예측 영상 이동 2 px 미만도 보류한다. 새 분할 추론·캐시 재생성은 없다.
- η는 새로운 센서 기제가 아니라 **스캔 유효 열 수의 격자**다. 원 우도는 `total × min(1, effective_columns/n_terms)`이고 VIS6은 여기에 η를 곱한다. `n_terms >= 8`에서는 η=.5/.25/.125가 유효 열 수 4/2/1과 같다. `n_terms < 8`에서는 포화 구간 때문에 일반적으로 같지 않다. η와 effective_columns를 독립 효과로 보고하지 않는다. 복구용 fit은 η·gate weight를 곱하기 전 우도로 계산한다.
- AMCL은 오도메트리 순변위의 축별 임계값과 `request_nomotion_update` 강제 갱신을 쓴다. 이 구현은 **프레임별 평균 이동의 길이 합**을 유지하며, 2 s 자동 timeout은 이 연구의 추가 정책이다. 왕복도 누적되며 d=2 cm는 0.12 m/s·5 Hz에서 거의 매 프레임 열린다. [Nav2 원문](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/amcl_node.cpp)의 `shouldUpdateFilter`·`nomotionUpdateCallback`을 2026-09-28 대조했다.
- 2순위(초음파) 연결점: `update_range(t, reading)`. 주입된 입자별 로그우도 제공자(PR #248 모델 어댑터 예정)에 같은 η와 별도 게이트 상태를 적용한다. PR #248에는 의존하지 않는다. 재표본화 ancestry로 이전 카메라 입자 순서를 맞추며, 주입 입자는 현재 자세를 이전 자세로 둔다. 프레임을 지우지 않는다. range 게이트 이동량은 카메라 갱신 시에만 누적하므로 최대 한 카메라 간격 지연이 있다. 이번 계획에서는 초음파 성능을 평가하지 않는다.
- 런타임 모듈은 `eval_only/`·교사·시뮬레이터를 읽지 않는다(소스 검사 테스트).

## 체커 한 칸 크기 (1c 설계 입력)

장면 **소스**에서 확인했다(렌더 출력만 본 것이 아님).

- `sim/masterpi_scene_v2.xml`: `texture name="ground" builtin="checker" width=256 height=256`, `material groundmat texrepeat="14 14"`, `texuniform` 없음(기본 false).
- `sim/zone_arena.py`: 구역 장면 생성 시 `floor.set('size', '8 8 .1')` → 16 m × 16 m 평면.
- MuJoCo `doc/XMLreference.rst`: texuniform false이면 2d 텍스처가 물체 위에 texrepeat번 반복된다. builtin checker는 2×2 무늬다.
- 따라서 텍스처 반복 1.1429 m, **체커 한 칸 0.5714 m**(= 8/14 m), 색 rgb .20/.22/.24 대 .27/.29/.31. `render/vl3-dev-s945/scene.xml`도 같은 값이다.
- 5 Hz·0.12 m/s면 프레임 간 이동은 2.4 cm다. 반주기(0.57 m)보다 훨씬 작아 체커 주기 별칭 위험은 무시할 수준이다. 반면 칸이 커서 시야에 경계가 없는 프레임이 많을 수 있다. 이런 프레임은 `unknown`이 된다.
- 값은 `vision_stall_v6.CHECKER`에 기록했다. `test_checker_size_matches_the_scene_source`가 소스와 대조한다.

## 자료와 분할 (VIS4·VIS5와 동일)

- fit: `vl-dev-s909 vl-dev-s910 vl-dev-s911 vl3-dev-s941 vl3-dev-s942 vl3-dev-s943`
- validation: `vl3-dev-s945 vl3-dev-s946 vl3-dev-s947`. 이미 본 dev이므로 독립 test가 아니다. 특히 s945는 1c 설계 동기에도 사용됐으므로 F 통과가 새로운 stall 사례의 일반화를 입증하지 않는다.
- 관측 캐시 `outputs/vision-loc-20260926/r3/obs-w6`(checkpoint sha256 `3485390…`, 해시만 확인), `calibration_train.json`, 입자 2,000개, a1_open 설정(`effective_columns 8`, `sigma_px 2.5`, `settle_s 0.2`, `refine_px 6`, `consistency_px 4`).
- 신경망 추론 0프레임. test 에피소드는 `replay_v6.py`가 거부한다. GT(`eval_only/frames_eval.jsonl`)는 `evaluate`의 채점에만 쓴다.
- PF seed 색인 k: k=0은 에피소드 seed(VIS3/VIS4와 같음), k≥1은 `episode_seed*1000 + k`. 선택 단계는 k=0–2, 최종 validation은 k=0–4.

## 후보와 단계

| 단계 | 후보 | 자료 | 규칙 |
|---|---|---|---|
| P0 | T0·T1c_inert | 첫 fit 회차 k=0 먼저 | xyyaw·std_xy_m·std_yaw_rad·measured를 저장 a1 및 중립 VIS6와 대조한 뒤 T0 나머지 실행 |
| S1 (1b) | T0, T1b_eta050, T1b_eta025, T1b_eta0125 | fit, k=0–2 | 보정 선택 규칙 |
| S2 (1c 검출기) | T1c | fit, 검출기 집계는 k=0만 | 검출기 관문: 양성 ≥ 20, precision ≥ 0.80, recall ≥ 0.30 |
| S3 (1a) | T1ac_{d02a3, d02a6, d05a3, d05a6, d10a3, d10a6} (η=1) | fit, k=0–2 | T0 대비 문 정확도 악화 한도(위치·횡 .003 m, yaw .2°)를 통과한 후보 중 fit XY NLL 최소 |
| S4 (1a+b+c) | T1ac_⟨S3⟩, T1abc_⟨S3⟩_eta050/025/0125 | fit, k=0–2 | 보정 선택 규칙 |
| F | T0(기준) 대 T1abc_⟨S4⟩, T1ac_⟨S3⟩, T1b_⟨S1⟩, T1c | validation, k=0–4 | validation 관문 |

게이팅 격자: d ∈ {2, 5, 10} cm × yaw ∈ {3°, 6°}, Δpulse 10, 모드 `skip`, timeout 2 s. 1c 매개변수는 `DEFAULT_STALL` 값을 설정 JSON에 명시해 고정한다(격자 없음).

**보정 선택 규칙(S1·S4)**: fit seed 평균 XY 95% 타원 포함률(full covariance, NEES ≤ 5.991)이 [0.90, 0.99] 안인 후보 중 fit 회차 균등 XY NLL이 가장 낮은 것. 동률이면 η가 큰 쪽(목록 앞). 정확도는 선택 기준이 아니다. 해당 후보가 없으면 그 단계는 후보를 내지 않는다.

**validation 관문(F)**: seed 평균으로 모두 만족해야 한다.
- XY 95% 포함률 90–99%, XY > 3σ(NEES > 11.83) ≤ 2%
- 문 위치 p90 악화 ≤ 0.3 cm, 문 횡 p99 악화 ≤ 0.3 cm, 문 yaw p90 악화 ≤ 0.2°(T0 대비)
- loaded·unloaded 각각 XY σ p90 ≤ 7 cm. 여기서 σ는 `sqrt(trace(P_xy))`이며 등방 축별 표준편차의 √2배다
- validation 세 회차 모두 XY NLL이 T0보다 나쁘지 않음
- 과신 프레임(오차 > max(3σ, 20 cm)) 수가 T0 대비 ≥30% 감소. T0가 0이면 후보도 0이어야 한다. 짧은 사건의 프레임도 모두 센다
- 사건 수는 기술 통계다. 연속 관측 안에서 ≤1 s 간격의 회복을 병합하고, 나쁜 프레임 ≥5개인 묶음만 사건으로 센다. 누락 프레임은 병합하지 않는다

통과 후보가 여럿이면 validation XY NLL이 가장 낮은 것을 채택한다(동률이면 위 목록 순서). 채택해도 기본 실행 설정은 이 PR에서 바꾸지 않는다. 폐루프·독립 test는 별도 계획이다.

보고 지표(선택에 쓰지 않는 것 포함): XY·yaw ANEES, 포함률, >3σ, NLL, 전체 위치 p90, 소실(>30 cm) 프레임, σ p90, 사건 수·프레임, 1c 검출기 precision/recall/보류율. 포함률은 프레임 풀링, NLL은 회차 균등 평균이며 가중이 다르다. yaw NLL은 wrapped normal 밀도다. yaw NEES·포함률은 접공간의 국소 지표로 큰 yaw 분산에서 해석에 한계가 있다. 프레임은 시간 상관이 있으므로 ANEES는 χ² 검정이 아니라 기술 통계다. 검출기 양성은 GT XY 속도 <.01 m/s 및 yaw 속도 <.02 rad/s, 예측 XY >.05 m/s 또는 yaw >.05 rad/s다. 정확한 stall은 XY·yaw 모두 `max(예측의 0.5배, 정지 임계속도×dt)` 안이어야 한다.

## 정지 규칙

1. P0 재현 실패 → 비교 전에 **중단**(코드·자료 변동). 기록만 남기고 선택하지 않는다.
2. S2 검출기 관문 실패 → 1c 제외, 1a도 함께 제외(게이팅은 1c 필요). F는 T1b만 비교한다.
3. S1·S3·S4에서 적격 후보 없음 → 그 단계는 후보 없음.
4. F 통과 후보 없음 → b0(VIS3 a1 = T0) 유지. 이 코호트에서 격자·임계값·규칙을 다시 조정하지 않는다. 새 아이디어는 새 계획으로 한다.
5. 호스트: 전원 연결에서만 실행(`run_units_v6.sh`가 배터리면 거부). 여유 공간 10 GiB 미만, ENOSPC, 중단된 실행은 HOST_ERROR다. 그 단위 전체를 새 출력 루트에서 다시 돌린다. `evaluate`는 불완전한 세트를 채점하지 않는다.
6. 예산: 누적 40 CPU시간을 넘으면 진행 중인 단계만 끝내고 멈춘 뒤 보고한다.

예산 추정: VIS3 a1의 단일 스레드 재생이 dev 9회 약 3,160 s였다. fit 한 세트(6회)는 약 37 CPU분, validation 한 세트(3회)는 약 16 CPU분이다. 계획 전체는 약 30 CPU시간이고, 4병렬이면 벽시계 8시간 안팎이다. 1c의 영상 처리 비용은 아직 재지 않았다. 산출물은 약 1 GB 이하로 예상한다.

## 관리자용 후속 재생 명령 (이번 수정에서는 미실행)

```sh
# 이 PR의 커밋에 고정된 worktree에서 실행한다(기본 체크아웃에서 돌리지 않는다).
WT=/Users/changmin/projects/ugrp-wt/claude-vis6
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
VIS=$WT/experiments/2026-09-26-vision-loc
P=$WT/experiments/2026-09-28-vis6-recipe1
OUT=/Users/changmin/projects/ugrp/outputs/vis6-recipe1-$(date +%Y%m%d)   # 새 경로. 기존 산출물에 덧쓰지 않는다
FIT="vl-dev-s909 vl-dev-s910 vl-dev-s911 vl3-dev-s941 vl3-dev-s942 vl3-dev-s943"
VAL="vl3-dev-s945 vl3-dev-s946 vl3-dev-s947"
RUN="python3 $WT/scripts/ugrp_session.py run vis6"
export VL_JOBS=4 OMP_NUM_THREADS=1
git -C "$WT" rev-parse HEAD > /dev/null && mkdir -p "$OUT" && git -C "$WT" rev-parse HEAD > "$OUT/source_sha.txt"

# P0: 가장 먼저 한 회차로 기존 a1과 중립 VIS6 경로 대조. 실패하면 중단한다.
$RUN -- "$P/run_units_v6.sh" "$OUT" "T0 T1c_inert" "0" "vl-dev-s909"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes vl-dev-s909 --output "$OUT/P0_first_a1.json"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T1c_inert --baseline "$OUT/runs/T0/seed0" --episodes vl-dev-s909 --output "$OUT/P0_first_inert.json"
$RUN -- "$P/run_units_v6.sh" "$OUT" "T0" "0" "vl-dev-s910 vl-dev-s911 vl3-dev-s941 vl3-dev-s942 vl3-dev-s943"
$RUN -- "$P/run_units_v6.sh" "$OUT" "T0" "1 2" "$FIT"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes $FIT --output "$OUT/P0_reproduce_fit.json"

# S1–S3: fit 선택 단계
$RUN -- "$P/run_units_v6.sh" "$OUT" "T1b_eta050 T1b_eta025 T1b_eta0125 T1c T1ac_d02a3 T1ac_d02a6 T1ac_d05a3 T1ac_d05a6 T1ac_d10a3 T1ac_d10a6" "0 1 2" "$FIT"
$PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 --episodes $FIT --output "$OUT/metrics_fit_S1_S3.json" \
  --candidates T0 T1b_eta050 T1b_eta025 T1b_eta0125 T1c T1ac_d02a3 T1ac_d02a6 T1ac_d05a3 T1ac_d05a6 T1ac_d10a3 T1ac_d10a6
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage calibration --output "$OUT/select_S1.json" \
  --candidates T0 T1b_eta050 T1b_eta025 T1b_eta0125
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage detector --output "$OUT/select_S2.json" --candidates T1c
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage lowest-nll --output "$OUT/select_S3.json" \
  --candidates T1ac_d02a3 T1ac_d02a6 T1ac_d05a3 T1ac_d05a6 T1ac_d10a3 T1ac_d10a6

# S4: S3 chosen이 null이면 이 단계와 T1ac도 제외한다.
# G = select_S3.json의 chosen에서 "T1ac_" 뒤 (예: d05a3). S2가 실패했으면 S3·S4·T1c·T1ac는 건너뛴다
G=$(python3 -c "import json;print(json.load(open('$OUT/select_S3.json'))['chosen'][5:])")
$RUN -- "$P/run_units_v6.sh" "$OUT" "T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125" "0 1 2" "$FIT"
$PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 --episodes $FIT --output "$OUT/metrics_fit_S4.json" \
  --candidates T1ac_$G T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S4.json" --stage calibration --output "$OUT/select_S4.json" \
  --candidates T1ac_$G T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125

# F: validation k=0–4. B = select_S1 chosen, A = select_S4 chosen. chosen이 null이거나 T0인 단계는 목록에서 뺀다
B=$(python3 -c "import json;print(json.load(open('$OUT/select_S1.json'))['chosen'])")
A=$(python3 -c "import json;print(json.load(open('$OUT/select_S4.json'))['chosen'])")
$RUN -- "$P/run_units_v6.sh" "$OUT" "T0 $A T1ac_$G $B T1c" "0 1 2 3 4" "$VAL"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes $VAL --output "$OUT/P0_reproduce_val.json"
$PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 3 4 --episodes $VAL --output "$OUT/metrics_val_F.json" \
  --candidates T0 $A T1ac_$G $B T1c
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_val_F.json" --stage final --baseline T0 --output "$OUT/select_F.json" \
  --candidates $A T1ac_$G $B T1c
```

- `run`은 clean committed worktree, 설정/모듈/계획 해시를 실행 전후 검사한다. `evaluate`는 단위별 meta의 설정/모듈/계획/추정 파일 SHA, 실패·dirty 상태, frame 수, 동일 git_head를 대조한다. `select`는 계획의 전체 split·seed 집합을 요구한다.
- 선택 단계(S1–S4)는 fit만 채점한다. validation 결과는 F에서 처음 연다.
- 산출물은 기본 체크아웃 `outputs/`의 새 경로에 둔다. 결과가 나오면 `experiments/2026-09-28-vis6-recipe1/`에 결과 README, 모든 selection JSON, 해시를 커밋한다. `docs/tensorboard.md`에 따라 새 TensorBoard 스냅샷도 만든다.
- 재생 뒤 확인할 진단(선택에 쓰지 않음): VISW s942 102–111 s는 관측 캐시가 없어 PF 재생이 불가능하다. 1c 검출기만 해당 JPEG로 따로 볼 수 있다. s945 170–205 s 추정 경로 대 정답 경로, GT 이동 < 1 cm 구간의 σ 추이.

## 구현·검증

- `experiments/2026-09-26-vision-loc/vision_pf_v6.py`: VIS6 PF(1a·1b·1c, 초음파 연결점)
- `experiments/2026-09-26-vision-loc/vision_stall_v6.py`: 1c 검출기, 체커 크기 기록
- `experiments/2026-09-26-vision-loc/vis6_metrics.py`: NEES·포함률·NLL·사건·선택 규칙(순수 함수)
- `experiments/2026-09-26-vision-loc/replay_v6.py`: `run / reproduce / evaluate / select`
- `experiments/2026-09-28-vis6-recipe1/`: 이 계획, `plan_v6.json`, `configs/`, `make_plan_v6.py`, `run_units_v6.sh`
- `tests/test_vision_loc_v6.py`: 합성 입력만 쓴다. 설정 거부, OFF = VIS5 비트 동일, η 정확 배율, 게이트 규칙, 합성 바닥에서 정지/이동/보류, PF 안 ZUPT, 팔 변경 시 1c 생략, 초음파 연결점, 지표 값·포함률, 사건 분할, 선택·관문 규칙, 계획 바이트 재생성, test 거부, 체커 크기 대조, 런타임 입력 경계.
- 최신 합성 테스트 및 기존 VIS 회귀 결과는 수정 기록에 적는다. 실제 자료 재생·시뮬레이션·신경망 추론은 이번 수정에서도 실행하지 않았다. 실험 결과가 없으므로 TensorBoard 스냅샷은 만들지 않았다. CI 결과는 PR에서 별도로 확인한다.

## 남은 검출 한계

1c는 예측 방향의 1차원 scale만 탐색하므로 실제 측방 이동이나 다른 yaw를 놓칠 수 있다. 같은 팔 명령이 같은 카메라 자세라는 가정은 팔 흔들림·차체 pitch에 취약하다. 바닥과 비슷한 회색 물체, 자기 그림자·광택 반사는 색상 마스크로 완전히 배제되지 않는다. 가속/감속 직후 제외, 측방·yaw 대안 가설, 수직 영상 이동 감사, 0.2–0.4 m 근거리 표본과의 비교는 후속 진단이다. 재생 전 기준을 추가 조정하거나 실제 precision·recall이 확인됐다고 주장하지 않는다.

## 참고 자료

- 선행 조사: `outputs/lit-review-tagfree-localization-20260928.md`(6.1절 레시피, 3.2·3.3·3.6·3.7절 근거)
- Nav2 AMCL 설정 문서(`update_min_d`, `update_min_a`): https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/
- S. Thrun, D. Fox, W. Burgard, F. Dellaert, "Robust Monte Carlo localization for mobile robots", AIJ 128, 2001. doi:10.1016/S0004-3702(01)00069-8
- D. Bagnell (scribe M. Dogar), CMU 16-831 Lecture 3 notes, 2009(측정 상관·평활화)
- P.-S. Wu, R. Martin, "A Comparison of Learning Rate Selection Methods in Generalized Bayesian Inference", Bayesian Analysis 18(1), 2023. doi:10.1214/21-BA1302
- E. Foxlin, "Pedestrian Tracking with Shoe-Mounted Inertial Sensors", IEEE CG&A 25(6), 2005(ZUPT)
- C. C. Ward, K. Iagnemma, "Classification-based wheel slip detection and detector fusion for mobile robots on outdoor terrain", Autonomous Robots, 2008
- Y. Bar-Shalom, X. R. Li, T. Kirubarajan, Estimation with Applications to Tracking and Navigation, Wiley 2001(NEES)
- R. Hartley, A. Zisserman, Multiple View Geometry, 2nd ed., 13.1절(평면 유도 호모그래피)
- MuJoCo XML reference, material `texrepeat`/`texuniform`, texture `builtin="checker"`: https://github.com/google-deepmind/mujoco/blob/main/doc/XMLreference.rst
