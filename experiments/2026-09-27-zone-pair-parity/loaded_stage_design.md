# 공동 운반 loaded 단계의 관측·불확실성 예산

2026-09-27 · **설계 초안, 구현·물리 실행 승인 아님** · `wait_lift / lift / wait_carry / carry / lower`와 그 사이 `wait_lower`를 함께 다룬다.

**권고:** #240 v5를 전제로, **단계별 오차 예산으로 진입을 결정하는 정지·내려놓기·재관측 checkpoint**를 설계한다. 먼저 낮은 팔 자세/공동 하중의 예측 오차와 시간 이산화를 보정하고, 모든 loaded 구간을 정지·lower까지 포함한 여유로 승인한다. 빔 영상은 상대 파지·미끄러짐 감시에는 쓰지만 전역 위치의 새 관측으로 세지 않는다. 현재 저장 자료만으로 새 noise 계수나 허용 구간 길이는 확정할 수 없다. **현 상태는 dev 실행 NOT_READY**다.

## 1. 기준·범위·출처

- 작업 checkout: `a1a304d1594bbe9b060b48c95b99e65b793a2094`, `codex/zone-pair-parity`.
- 설계 기준 #240 v5: `3839555dc0de0880f74a40c831044e2b5be2d2d7`. 2026-09-27 14:38:26 UTC GitHub 조회에서 OPEN 및 동일 head 확인. PR 제목/본문에는 v4 설명이 남아 있으므로 v5 **소스와 prereg_v5**를 기준으로 한다. 이 SHA의 PF/pose-source는 작업 checkout과 동일하다.
- [#221 최신 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5856789331): 설계와 #240 dev09/10을 병행하되 **구현은 #240 병합 뒤**. 일괄 threshold 완화 금지. [직전 v5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5856308924)은 align 전/중 능동 재관측과 END_CLIPPED 보완이다.
- [기존 차분 진단](README.md), [dev 직접 재생](dev-main.json), [M2 조건부 PF 재생](m2-shadow-main.json), 원본 `outputs/zone-pair-dev-v2-* / v3-* / v4-*`, `outputs/zone-m2-pair-20260926/` 및 기존 목록의 Kiro M2 원본을 읽었다. 발견된 공통 dev는 dev03–08이다. dev09/10 결과는 이 분석에 없다.
- 원격 조회 기록: [loaded_stage_sources.json](loaded_stage_sources.json). 현재 열린 관련 PR은 #240, #244(이 차분 진단), #242/#243(비전 위치 추정)이다. 댓글·메시지는 게시하지 않았다.
- 정량 산출: [loaded_stage_metrics.json](loaded_stage_metrics.json), 재현 분석: [loaded_stage_analysis.py](loaded_stage_analysis.py). 223개 원본/파생 파일의 현재 SHA-256을 기록했다. M2 49회 × 결과/명령/입력목록/이벤트의 해시는 기존 재생 manifest와 일치한다. 기존 43,699 JPEG 검증을 승계해서 설명하되 **이번에 JPEG 전체를 재검증한 것은 아니다**.
- 자기 상태로 표본을 고른 뒤 GT trace를 사후 대조했다. 각 보고시각 이하의 가장 가까운 GT 표본만 사용했고 차이는 0.051 s 이하임을 검사했다. GT는 측정 오차의 평가 열에만 있다. dev frame별 σ는 소수 5자리여서 정확한 gate 경계의 내부 full precision과 구분한다.
- 물리 step 0, 모델 호출 0, 생산 코드 변경 0, git commit 0. MuJoCo/Torch/TensorFlow/네트워크 클라이언트 import 차단 아래 분석·관련 검사를 수행했다. 외부 GitHub 조회는 자료 읽기다. Google Drive는 사용하지 않는다.

## 2. PF 과신: 관찰과 원인을 분리

### 2.1 중단 직전 자기 보고와 사후 오차

중단시각 이하 마지막 RGB 보고를 사용했다. dev05의 실제 중단은 190.429 s이고 직전 보고는 190.4 s, dev07 r2는 r1의 중단 202.8 s보다 앞선 202.7 s다. 미래 프레임을 사용하지 않았다. `오차/σxy`는 진단 비율이며 정규분포 z-score가 아니다(`σxy = sqrt(var x + var y)`).

| 실행·로봇 | 보고시각 s | XY 오차 m (평가) | σxy m | 오차/σxy | σyaw ° | 마지막 태그 후 s | PF 모드 |
|---|---:|---:|---:|---:|---:|---:|---|
| dev05 r1 | 190.4 | .75921 | .05985 | 12.69 | 1.362 | 28.2 | unloaded |
| dev05 r2 | 190.4 | .88664 | .05441 | 16.30 | 1.142 | 26.7 | unloaded |
| dev06 r1 | 193.7 | .70285 | .05653 | 12.43 | 1.383 | 26.9 | unloaded |
| dev06 r2 | 193.7 | .94896 | .05753 | 16.50 | 3.001 | 30.5 | loaded |
| dev07 r1 | 202.8 | .00925 | .02383 | .39 | .692 | 2.9 | unloaded |
| dev07 r2 | 202.7 | .00911 | .02676 | .34 | .538 | 2.8 | unloaded |
| dev08 r1 | 175.6 | .68302 | .04265 | 16.01 | 1.184 | 10.8 | unloaded |
| dev08 r2 | 175.6 | .76046 | .07004 | 10.86 | 1.512 | 15.3 | unloaded |

dev07도 relook **이전** align 말기에는 r1/r2 오차 .91276/.86878 m, σ .05744/.05691 m였다. 재관측 뒤 위처럼 줄었고, 별도 partial-view 계약에서 중단됐다. 이 사례는 관측 회복의 직접 근거지만 v5 전체 완주의 근거는 아니다.

align 동안의 순변위도 예측 모델 불일치를 보인다. dev05 r1/r2의 PF 순변위는 1.0229/1.1704 m, 실제 사후 순변위는 .2713/.2839 m였다(3.77/4.12배). dev06은 1.0078/1.2088 m 대 .3104/.2610 m(3.25/4.63배). 이것은 경로 길이나 새 gain 추정이 아니라 **같은 align 시작·끝의 순변위 비교**다. σ를 키우기만 하거나 종료 오차로 좌표를 보정하는 방법으로 해결할 문제가 아니다.

dev03/04는 공동 접근·loaded 단계에 진입하지 않았으므로 위 표의 분모에 넣지 않았다. raw 목록과 해시는 유지했다. frame별 2σ 초과 건수는 JSON에 있으나 시간 상관이 강해 독립 시행 수로 취급하지 않는다.

### 2.2 원인 경로

1. **동작 평균 모델이 파지 자세와 다르다.** `harness/owncam_localizer.py:182-222`는 gain·lag에 자기 발행 명령을 넣어 입자를 전파한다. pair align에서 shared PF에 팔을 낮춘 별도 motion profile을 선택하는 경로가 없다. `scripts/run_m2_pair.py:353-365,480-550`에도 낮춘 팔에서 기존 예측이 약 4배라는 배경과 별도 VO가 명시되어 있다. 공통 PF에는 beam 관측 residual이 들어가지 않는다. 위 순변위와 일치하는 **모드 불일치**이며, 팔 자세·마찰·명령 lag의 기여율까지 현재 자료로 분해하지는 못했다.
2. **입자 분산은 모델 bias가 아니다.** 마지막 태그가 좁힌 입자와 slip scale이 같은 잘못된 평균 모델을 따라 이동하면, 평균이 크게 틀려도 입자끼리는 가깝다. `estimate():379-393`의 weighted covariance에는 실제 예측 bias, 공동 물체의 힘, 하중 모드 오판에 대한 독립 항이 없다. 정지에는 scale random walk도 멈춘다. `motion_loaded.scale_std`는 모드 전환 때 새로 적용되지 않고 초기 scale 생성은 `motion.scale_std`를 사용한다. 따라서 load switch가 하중 불확실성의 재초기화인 것도 아니다.
3. **태그 없음은 관측 갱신 없음이다.** `update():313-357`은 dets가 있어야 likelihood/reset을 수행한다. 빈 프레임은 예측·정규화만 수행한다. 오래 못 봤다는 이유로 bias bound를 추가하거나 global covariance를 재평가하지 않는다. `since_tag_s`는 보고되지만 pair loaded gate는 기본적으로 σ/보고 freshness를 본다. `report(now)`가 새 시각을 찍었다고 새 절대 관측이 생기지는 않는다. 별도로 `OwnCamPoseSource.on_frame`의 `last_valid_obs`는 detector의 dets, `last_tag_t`는 map/solution/range 필터를 통과한 dets 기준이므로 새 설계는 **accepted absolute fix**를 명시적으로 기록해야 한다.
4. **loaded는 파지 관측이 아니라 PWM 추정이다.** `LoadState:83-107`은 servo1 ≤1600이며 명령 FK 높이가 .06 m 미만이면 loaded, ≥1800이면 unloaded로 바꾼다. dev05 양쪽/dev06 r1은 중단까지 unloaded다. dev06 r2만 grasp 중 189.072 s, pulse1552에서 loaded로 바뀌고 4.628 s 뒤 gate에 걸렸다. 실패한 닫힘도 loaded가 될 수 있고, 중간 높이 재파지는 실제 하중을 놓칠 수 있다. 이 flag, `beam_grasp_confirmed`(영상 receipt), guard의 단계별 부착 가정은 서로 다른 개념이다.
5. **process noise의 시간 이산화가 호출격자에 의존한다.** `predict_to:194-222`는 매 호출의 작은 dt마다 velocity noise를 뽑은 뒤 dt를 곱한다. 독립 noise의 위치/각도 분산 증분은 `a² Σdt_k²`다. 물리시간당 diffusion `Q Σdt_k`가 아니다. 50 ms 이하로 `report/command/frame`가 끼어들면 같은 시간에도 더 작아진다. 실제 두 러너의 숨은 predict 호출격자를 완전히 복원하지 않았으므로 98개 shadow σ를 원래 M2 σ라고 부를 수 없다.
6. **추가로 확인할 원인:** map prior가 벽 밖 입자에 매 substep -8을 누적하므로 관측 없이도 잘못된 cloud를 잘라 σ를 줄일 수 있다. resampling도 bias를 검출하지 않는다. 이 기작은 소스에서 확인했지만 이번 overconfidence 중 얼마를 설명하는지 ablation하지 않았다. 이미 실패한 좁은 posterior에 작은 roughening을 넣는 것만으로 0.9 m bias가 회복된다는 근거는 없다.

### 2.3 loaded yaw 예산의 정량 불일치

고정 calibration `calibration_loop_v2.json`의 yaw velocity `noise_abs`는 unloaded **.01406 rad/s**, loaded **.09762 rad/s**다. loaded의 순수 yaw noise 분산은 48.21배다. 이 calibration은 단독 상자 운반/정지 dev에서 유래했으며 공동 빔의 단계별 fit이 아니다.

50 ms 간격, 정지, 지도 가중치 없음, yaw wrapping 영향이 작은 구간에서는:

`q_yaw = .09762² × .05 = .00047648322 rad²/s`

`σyaw²(T) ≈ σyaw²(0) + q_yaw T`

| 초기 σyaw | 현재 식으로 3°까지 남은 정지시간 |
|---:|---:|
| 0° | 5.754 s |
| 1° | 5.114 s |
| 2° | 3.197 s |
| 2.5° | 1.758 s |

순수 PF 수치 확인: zero-spread/zero-motion에서 10 s 예측한 loaded σyaw는 외부 호출간격 50/25/10 ms에 **4.058/2.821/1.783°**, 해석값은 **3.955/2.797/1.769°**였다(seed20260927, 2000 particles). 같은 50 ms unloaded 해석값은 .570°다. 이 차이는 물리 변화가 아닌 예측 호출 분할의 영향이다. **dt에 맞춰 noise를 다시 정의해야 한다는 근거이지 기존 noise를 줄여도 된다는 근거가 아니다.**

M2 성공 선택군 49회/98 trace의 기존 조건부 PF 재생에서 최초 거부는 carry63, wait_carry19, wait_lift10, lift6이며 모두 PF loaded였다. loaded 명령 이후 거부까지 p50 **5.176 s**, 범위 **4.358–6.551 s**. 마지막 태그 이후는 p50 **24.561 s**, 범위 **8.621–31.779 s**. 표준 50 ms 정지 예산과 같은 규모지만 격자·초기σ·운동이 달라 인과 기여율을 정밀 추정한 것은 아니다.

원본 state 이벤트의 완료 phase 206개/종류(동일 episode의 반복 segment 포함):

| phase | p50 s | p90 s | max s |
|---|---:|---:|---:|
| wait_lift | .201 | 4.161 | 8.621 |
| lift | 1.504 | 1.504 | 1.504 |
| wait_carry | .200 | .201 | .201 |
| carry | 23.859 | 24.862 | 54.035 |
| wait_lower | .201 | .401 | .401 |
| lower | 1.604 | 1.604 | 1.604 |

open_floor(42 robot-segments)의 carry p50은 20.651 s, door(164)의 carry p50은 23.8595 s다. 서로 다른 cohort/seed/버전을 통합 성공률로 계산하지 않았다. M2 .06 m/s 설정과 axial scale .772이면 .55/.65/.85/.80 m의 **주행 부분만** 11.87/14.03/18.35/17.27 s다. barrier·lift·door 정렬·lower는 별도다. 따라서 **3°를 유지하면서 checkpoint를 조금 더 넣는 것만으로 현재 noise 모순은 풀리지 않는다.** 2.5°에서 시작하면 최소 lift+wait_carry+lower만으로도 예산을 넘는다. 현행 8 segment 제한도 짧은 구간을 무한히 추가하는 해법을 허용하지 않는다.

M2 VO는 98 trace 중 46개에 `vo_pose` 사건이 있다. 모든 M2 성공을 VO 덕분으로 단정하지 않는다. VO는 **바닥에 정지한 빔**의 첫/마지막 자기 관측을 arrival estimate에 연결한 grasp pose이고, 운반 중 움직이는 빔을 세계의 고정 landmark로 쓰는 방법이 아니다. M2에는 같은 loaded pose gate가 없었다.

## 3. 설계 후보 3개

공통 입력 allowlist: 자기 wrist RGB·그 RGB 시각/ID·자기 발행 명령과 고정 보정·정적 지도/물체 치수/역할/사전 계획·유한한 STATUS enum. peer 좌표·covariance·영상·beam fit·GT·접촉력·측정 관절·host의 실시간 장면은 금지한다. STATUS의 기존 seq/시각/TTL은 freshness 및 장벽에만 쓴다. 시각·enum·segment ID에 좌표/오차를 부호화하지 않는다. protocol은 무통신 포함 모든 연구 조건에서 동일하다.

| 후보 | 유지할 상태/기대 효과 | 위험·한계 | 오프라인 → dev 검증 |
|---|---|---|---|
| A. 자기 빔 상대 자세 + grasp anchor | 건강한 자기 태그 fix와 파지 전 full beam fit으로 `T_world_base(t0)`, `T_base_beam(t0)`, 공분산/나이/출처를 묶는다. 이후 자기 RGB의 빔 상대 자세·파지점 잔차로 상대 slip/tilt를 감시. 동일 cargo/고정 role의 양쪽 fresh GRASPED enum은 공동 파지 가설의 필요조건 | 둘과 빔이 같은 SE(2) 변환을 하면 상대영상이 같으므로 공통 전역 translation/yaw는 비관측. 두 번째 로봇 좌표 없이 metric loop closure 불가. 다른 물체/한 손 오탐/beam 끝 잘림/마찰 slip·휨. PWM FK는 실제 손목이 아니다 | 정지빔 align에서 relative fit 잔차·anchor 공분산 전파·partial 관측 rank 검사. 공통 이동/한 손 slip/오탐 반례에서 global σ 감소 금지. holdout offline 이후, 별도 dev에서 슬립 조기 중지 여부. 전역 위치 유지의 단독 해법으로 채택하지 않음 |
| B. 사전 계획 checkpoint에서 양쪽 정지·하역·순차 look | 두 로봇이 같은 고정 구간 끝에서 장벽으로 정지. 안전한 lower/release 후 end_neg → end_pos 순으로 기존 wrist look, 각자 자기 PF만 태그로 갱신. 새 양쪽 READY 후 재파지/들기. 절대 관측 공백을 유한하게 만듦 | loaded 상태에서 손목 pan은 빔 전체 sweep/상대 손 토크를 유발하므로 그대로 적용 불가. 내려놓기 여유가 없는 문 안/문설주 옆에서는 checkpoint 금지. 재파지 실패와 시간/명령 증가, 안 보이는 태그, 낮은 벽 위 파지 자세의 FK 오차 | 저장 정적 map·own pose/servo에서 전체 stop/lower/look sweep 및 tag visibility 후보만 검증. 새 viewpoint RGB는 저장 자료로 생성 불가. dev에서 양쪽 정지·지원면/그립·재관측·재파지·문 통과를 각각 검사 |
| C. 모드·시간·이동거리별 오차 예산과 단계별 gate | `align_low/open`, `grasp_closing/unknown`, `loaded_stationary`, `loaded_translation`, `loaded_turn`, `lowering` 별 bias·분산/상관을 보정. 기준시간에 독립적인 Q, 최근 absolute fix 이후 T·누적 명령거리 L·회전 A, stop lag reserve로 다음 관측까지의 오차 tube 계산. σ 한 시점보다 남은 작업을 미리 거부 | noise를 줄이는 것만으로는 안전해지지 않음. 타임아웃을 짧게 해 early abort가 늘 수 있음. 단독 box calibration을 pair에 재사용 불가. 느리게 달리면 거리 오차는 줄어도 시간 noise는 더 증가할 수 있음 | 저장 명령/자기영상 replay를 독립 eval로 채점. 10/25/50/100 ms report cadence에서 같은 예산. holdout episode 단위 coverage, bias/상대·전역 gauge 검사 후 dev. 불충분하면 계수 null·진입 거부 |

### A의 경계와 공분산

`T_world_beam = T_world_base × T_base_beam`의 anchor는 **anchor 당시**에만 정적 빔 가설 아래 유효하다. 운반 중은 `T_world_beam(t)`도 상태로 움직인다. 빔을 고정 world landmark처럼 반복 update하면 자기 예측을 재관측으로 오인해 과신이 더 커진다. 전역 gauge의 오차 하한은 절대 fix 이후 단조 증가하며 상대 update로 줄이지 않는다. 공유 이미지/공분산 없이 상대 로봇의 독립 정보인 척 곱하지 않는다. partial beam은 관측 가능한 축만 쓰고 끝점·scale이 안 보이면 해당 축은 unknown/상한으로 유지한다. `same_beam` STATUS는 physical constraint의 증명이 아니라 로봇별 자기 증거에 기반한 receipt다.

### B의 상태·장벽 계약

`carry → cp_stop_ready → cp_stop_go → lower_ready/go → cp_support_ready/go → open_ready/go → look_neg → look_pos → refix_ready/go → align/close/lift → carry`

- checkpoint 위치·look 순서·후보 pan은 정적 계획에 들어간다. 매 로봇이 자기 plan과 자기 예산으로만 READY 여부를 결정한다. host는 기존 두 endpoint의 유효 enum과 공통 GO 시각을 전달한다. 새 작업/계획/좌표를 만들어 상대에게 주지 않는다.
- **멈춤:** own hold 발행은 실제 정지 증명이 아니다. 보수적인 stop lag 시간과 자기 RGB 잔차를 확인하고, 그동안 base/beam swept tube를 유지한다. partner의 STOPPED는 위 계약을 충족했다는 assertion일 뿐 좌표 관측이 아니다.
- **내리기/놓기:** fresh 자기 RGB 파지 유지 및 사전 계산한 lower sweep을 만족할 때 양쪽 동시에 실행. support/open은 바닥 기준 자기 영상에서 지원면·빔 안정이 확인되어야 한다. 현재 뷰로 support를 판별 못하면 unknown으로 막는다. GT 지원면 판정은 평가용뿐이다.
- **look:** 양쪽 release/손의 분리가 자기 RGB로 확인된 뒤 한 로봇씩. 손에 든 채 한쪽 손목을 pan하는 경로는 첫 구현에서 제외한다. 그런 별도 경로를 허용하려면 양측 폐쇄 운동학·빔/팔 전체 sweep·slip 관측을 추가로 증명해야 한다.
- **다시 들기:** 각 로봇은 새 태그 fix·새 beam anchor·현재 PWM과 일치하는 새 RGB·예산을 가진 뒤 #240 close 장벽부터 재사용한다. heartbeat가 오래된 준비 증거의 수명을 연장하지 못한다. 모든 전이는 phase/segment/task epoch와 seq를 검사하고 비대칭 지연/재전송/취소 때 양쪽 예약 명령을 폐기한다.
- 무한 wait 금지. 기존 phase timeout을 상한으로 사용하되 **현재 오차 예산에서 안전하게 멈추고 lower할 수 있는 더 짧은 deadline**을 우선한다. 반복 look·regrasp는 고정 총횟수/총시간 예산을 소모한다. peer 미준비로 deadline이 줄어도 남은 구간을 강행하지 않는다.

### C의 예산·벽 여유 계약

통계 σ와 모델 불일치 bound를 별도로 기록한다. 예시 구조(계수는 아직 미정):

`P_next = F P Fᵀ + Q_mode Δt + Q_distance ΔL + Q_turn |Δψ_cmd|`

`B_xy = b0_xy + b_t T + b_L L + b_A A + B_stop + B_arm + B_anchor`

`B_yaw = b0_yaw + c_t T + c_L L + c_A A`

지속 bias는 white noise가 아니므로 필요하면 bias 상태와 상관을 보존한다(분산 관점에서 T²/L² 항). Q/units는 calibration manifest에 고정하고 임의 dt 변경으로 noise가 줄어들지 않게 한다. mode는 자기 단계·명령·RGB receipt로 선택하며, 물리 loaded 여부가 모호하면 가능한 모드의 오차 상한 합집합을 사용한다. 파지 성공 enum만으로 좌표/σ를 reset하지 않는다.

벽 법선 n과 본체/팔/빔의 각 대표점 j에 대해 `J_j=[I, R'(yaw) r_j]`로 world point covariance를 투영한다. 모든 미래 명령·양방향 회전·정지 coast·lower 동안:

`clearance_j = distance(point_j, static_wall) - radius_j - M_j`

`M_j = .035 m + sampling_pad + B_xy + 2 L_j sin(min(B_yaw, π)/2) + k sqrt(nᵀ J_j P J_jᵀ n) + B_relative_j`

기존 `PairSweepGuard`의 전체 빔 sphere/팔/차체 검사를 재사용한다. `.035 = BASE_MARGIN .020 + body residual .015`이며 유지한다. 현재 `2σxy + 2 L σyaw`보다 작은 margin으로 바꾸는 것은 **방향별 coverage가 독립 검증되기 전에는 금지**하고, 초기 후보는 두 계산의 큰 값을 쓴다. Gaussian coverage를 검증하지 않았다면 k=2를 95% 안전 확률이라고 부르지 않는다. 큰 불확실도를 `.15 m/.20 rad` cap으로 잘라 통과시키지 않는다. 지원영역 밖이면 거부한다. sphere sampling 간 간격·servo sweep·stop 변위까지 포함해야 한다.

계산 예(실제 맵의 안전 인증 아님): lever .90 m, σxy .030 m, σyaw 2°일 때 기존 margin은 `.035 + .060 + 2×.9×.03491 = .15783 m`. nominal 형상 여유 .20 m라면 나머지는 .04217 m뿐이고 bias·coast·sampling pad를 여기서 더 빼야 한다. 같은 geometry에서 yaw가 3°면 나머지는 .01075 m다. 문폭만 보고 충분하다고 할 수 없다. 반대로 open 공간의 hold에 전진과 같은 gate를 적용할 이유도 없다.

| 단계 | 필요한 관측·예산 | gate 동작 |
|---|---|---|
| wait_lift | #240 close 이후 자기 파지 receipt, 최근 absolute anchor, 남은 양쪽 대기+lift+최소 안전 lower 예산 | hold는 항상 허용. READY는 미래 예산이 있을 때만. peer를 기다리며 σ/bias clock은 계속 진행 |
| lift | 새 자기 gripper/beam 영상, 양쪽 lift GO, lift sweep+그립 및 예정 stop/lower tube | base 이동 금지. grip loss/receipt expiry/unsafe tube이면 양쪽 abort. lift 성공만으로 global σ 축소 금지 |
| wait_carry | lift 후 새 hold-view, 새로운 carry READY, 다음 checkpoint까지 travel+모든 wait+lower 예산 | 예산 없는 GO 거부. arm 복귀/관측 시간도 포함; 태그가 안 보여도 이전 σ를 복원하지 않음 |
| carry | 매 자기 RGB의 상대 slip/그립 잔차, 자기 명령 적분과 mode별 증가 bound | 명령 한 tick뿐 아니라 endpoint+stop까지 검사. soft budget 도달 전 계획된 checkpoint로 종료. 통과할 여유 없으면 새 구간 진입 금지 |
| wait_lower / lower | 양쪽 lower readiness와 자기 support 후보·lower sweep; 남은 lower+settle budget | 증명된 lower만 실행. threshold 초과 뒤에는 '내리면 안전'이라 가정하지 않음. hold/abort는 허용하지만 안전한 착지 완료로 보고하지 않음 |

첫 구현은 기존 loaded **σxy HIGH .07 m / yaw HIGH 3°**, LOW .06 m / 2.5°, .035 m geometry margin을 유지한다. phase gate 재정의는 **hold / readiness / 실제 움직임 / 완료 확인을 분리하고 미래 예산을 추가**하는 범위다. 방향별 clearance가 충분할 때 scalar gate를 대체하는 확장안은 별도 cohort/검토가 필요하며 이번 권고에 포함하지 않는다. 이벤트 dwell .6 s를 motion 유예로 쓰지 않는다.

## 4. 권고안과 구현 범위(이번에는 미구현)

**B+C를 하나의 후보로 선택한다.** #240 v5를 그대로 기반으로 하되, loaded global 관측은 안전한 set-down checkpoint에서 회복하고, 그 사이에는 보정된 명령 모델과 보수적인 오차 증가를 사용한다. A는 local slip/receipt 검증만 우선 포함하고 global pose update는 실험 대상으로 남긴다. 순서는 **모드/시간 noise 진단 → holdout calibration → checkpoint 가능성 검사 → 공통 endpoint 통합 → dev**다. 현재 noise 그대로는 carry 계획이 불가능할 수 있으며 이것은 올바른 사전 거부다. 결과를 내기 위해 σ 감소·reset·gate 완화를 넣지 않는다.

| 예정 파일 | 한정된 변경 내용 | 대응 검사 |
|---|---|---|
| `harness/owncam_localizer.py`, `owncam_pose_source.py` | 별도 버전의 mode별 Q/bias, dt에 독립적인 전파, accepted fix/anchor age와 load hypothesis provenance. 기존 calibration 동작은 버전으로 보존 | predict 호출 분할 일치, no-tag clock 증가, load 실패/재파지/해제의 모드, invalid tag가 fix age를 갱신하지 않음 |
| **신규 후보** `harness/zone_pair_budget.py` | own-only loaded stage budget 및 다음 stop/lower까지 reachability certificate; null 계수/지원 밖 fail closed | 정지·회전·속도·구간·barrier 지연, 초과/NaN/무관측/큰 bias, 안전 여유 단조성 |
| `harness/zone_pair_geometry.py`, `zone_pair_guards.py` | 현재/미래 full-beam sweep, bias/stop pad, stationary hold 분리, geometry cap bypass 방지 | 기존 review4 빔 중앙/lever/pan 충돌 유지 + 문설주·coast·lower sample gap 반례 |
| `harness/zone_pair_executor.py`, **신규 후보** `zone_pair_checkpoint.py` | 고정 checkpoint, 양쪽 stop/lower/release, 순차 look, 새 준비 증거로 재시작. frozen M2 원본 직접 수정 금지 | 독립 endpoint, stale/duplicate/abort/silent/late GO, 양쪽 큐 폐기, 한 손 loaded-pan 금지 |
| `harness/zone_pair_status.py`, `zone_pair_executor.py:make_plan`, `zone_pair_grasp.py` / `zone_pair_align.py` | 유한 checkpoint enum/epoch와 정적 계획 hash; #240 close/anchor 계약 재사용. 기존 8 segment 상한 내 우선 판정 | 임의 좌표·image·cov·자유문장 거부, enum/시각에 연속값 인코딩 불가, 이전 segment 메시지 재사용 금지 |
| `tests/test_owncam_localizer.py`, `test_m1_owncam.py`, `test_zone_pair_review4.py`, `review5.py`, `test_zone_pair_status.py`, **신규** `test_zone_pair_budget.py`, `test_zone_pair_checkpoint.py` | 위 계약과 입력 경계·관측 불가능성 회귀 | 공통 SE(2) 이동이 beam-only global confidence를 개선하지 않음. 동일 JPEG/anchor 재사용 시 독립 관측으로 누적 금지 |
| `scripts/run_zone_pair_dev.py`, `configs/simulation_workflows.json`, 실행 bundle·calibration manifest, 해당 `experiments/` | 기존 `sim_cli zone-pair-dev` 어댑터에 옵션/로그·새 bundle 연결. actual applied values와 소스 고정 | CLI 사전등록 불일치/미등록 draft 실행 거부, baseline/candidate input·물리 동일, 로그 coverage |

파일명은 구현 계획이며 신규 production 파일을 만들지 않았다. bundle/prereg 번호·seed는 main과 열린 PR의 사용값을 다시 확인한 뒤 예약한다. #240 dev09/10 번호를 가져오지 않는다. 새 control profile은 기본 OFF이며, 기존 source/record를 덮어쓰지 않는다.

## 5. 사전등록 초안 기준

기계 판독 초안은 [loaded_stage_design.json](loaded_stage_design.json)의 `preregistration_draft`다. **status=DRAFT_NOT_RUN, runnable=false**, 실행 SHA/bundle/계수/새 seed가 null인 동안 CLI 실행 불가가 요구사항이다.

### O0: 자료와 오프라인 검증

1. 기존 49개 성공 trace는 failure-mode 발견에만 사용한다. 98/98을 통과하도록 noise/gate를 맞추지 않는다. 원본 전체 dev의 성공·실패·취소를 manifest에 등록하고 version/seed/status 조건을 분리한다. `development_seed=false` 및 과거 test 자료는 평가 전용으로 격리한다. 이미 본 성공군을 새 blind holdout이라 부르지 않는다.
2. fit용 과거 dev와 holdout은 **episode/seed 단위**로 고정한다. 동일 seed의 on/off·서브프레임·crop은 한 split에만 둔다. dev03–08과 M2 dev는 이미 진단에 쓰였음을 표시한다. 새 test-like holdout이 필요하면 추가 수집 승인이 선행되어야 하며 이번에는 실행하지 않는다.
3. replay control 경로는 자기 RGB/명령/static/enum만 읽고 GT 파일 open을 금지한다. 별도 scorer가 산출물을 닫은 뒤 GT와 join한다. full covariance, accepted tag IDs/시각, 모드, cmd time/dt, residual/bias bound, next checkpoint certificate를 보존한다. 없는 covariance/clock는 `insufficient_evidence`; 반올림 σ로 NEES를 만들지 않는다.
4. 모델 선택 기준은 held-out 각 phase의 XY/yaw/벽 법선 방향 오차 coverage다. nominal 95% bound의 **episode-block bootstrap 95% 하한 ≥.95**를 목표로 하며 유효 episode 수/phase 노출 부족은 통과가 아니라 미확인이다. 이는 운영 안전 보증이 아니다. 관측 없는 전역 gauge 오차를 숨기는 covariance shrink와 실제 충돌 trajectory에 false-safe certificate는 0건이어야 한다. GT 여유가 양수인 장면만 선택해 성공률을 주장하지 않는다.
5. cadence metamorphic 검사(동일 own commands/frames; 10/25/50/100 ms의 report 호출, command expiry에서 분할)는 analytic budget 차이 ≤1%, 증거가 바뀌지 않는 경계 밖 gate 결정 동일을 요구한다. 1%는 제안된 수치 회귀 허용치이고 물리 정확도 기준이 아니다. 후보 구현의 baseline noise 보존/새 모델 버전을 각각 기록한다.
6. 저장 프레임은 새 checkpoint/팔 자세의 관측 결과를 제공하지 않는다. 새 viewpoint가 필요한 첫 분기에서 exact replay를 종료하고 그 뒤는 conditional diagnostic으로만 표시한다. checkpoint 개수·최대길이는 fit 후 고정한 미래 예산과 정적 map 계산으로 정하고 test를 본 뒤 조절하지 않는다. feasible plan이 없으면 O0 불통과다.

### O1: #240 병합 후 별도 승인될 dev(이번 미실행)

- 비교: frozen #240 v5 baseline vs B+C 후보. same scene/map/sheet/contact/timestep/카메라/FOV/캡처·명령 주기/STATUS 정책, weld OFF, 실제 모델 호출 0. 파지 전 v5 능동 relook는 양쪽에 동일하게 둔다.
- 총 **8 run** 초안: 새 normal seed 2개 × baseline/candidate 2조건 =4, 새 fault case 2개(고정 loaded no-tag blackout, carry/checkpoint에서 고정 STATUS abort 또는 silence) ×2조건 =4. fault 조건은 같은 과거 성공률에 합산하지 않는다. 한 fault에 abort와 silence를 섞어 결과를 선택하지 않고 등록 때 하나를 고정한다.
- 각 run 최대 **900 SIM s**, 추가 재시도 0, 전체 7200 SIM s. .00025 s 물리 timestep이면 run당 3,600,000 step 상한. wall deadline/CPU/디스크 예상량은 실행 담당자가 가용 자원에 맞춰 별도로 확정해야 하며 null 상태로는 실행 금지. 물리 사전 exclusive lock·세션 cleanup·부하/디스크 기록은 기존 규칙을 따른다.
- **필수 안전 조건:** 금지 접촉 0, stale/unsafe GO 0, 입력 누출 0, 한쪽 loaded-pan 0, 양쪽 abort 후 추가 arm/base 명령 0, 원본과 연결된 완전한 phase/GT/접촉 coverage. 지원면이 없는 lower/release를 완료로 세지 않는다.
- 물리 단계/성공 기준은 #240 `prereg_v5.json`의 `criteria/stage_rules/planned_setdown`을 해시로 보존해 승계한다: 양손 각 finger≥1 N·.2 s, 전 빔 bottom≥.04 m 및 문 slab 전체 통과, tilt≤15°, B 전체 배치·방출·정지 등을 별도 evaluator에서 검사한다. 새 checkpoint의 planned setdown을 사전에 열거한다. 타임아웃·검증 누락·ENOSPC는 성공 아님(ENOSPC=HOST_ERROR).
- normal 후보 2/2의 파지→들기→문→B 배치/방출 모두와 안전 조건을 요구한다. 둘 다 loaded 진입 이전 실패면 loaded 설계는 `not_reached`다. **2/2는 dev 확인 범위일 뿐 일반 성공률/실물 승인 아님**. baseline 대비 관측 회수·중단 단계·추정 coverage·최소 여유·σ/bias 증가·checkpoint별 overhead·SIM 시간·발행 명령·모델 호출/비용(0)을 모두 보고한다. 더 짧은 실패 시간을 성능 향상으로 표시하지 않는다.
- fault 2개는 명시한 중단/양쪽 큐 제거를 모두 통과해야 한다. 정상 성공과 fault stop을 서로 대체하지 않는다. 판단 범위는 simulator dev이고 실제 MasterPi는 별도다. 실패가 나오면 같은 frozen cohort 안에서 수정·재시도하지 않고 새 후보/새 등록으로 이동한다.

## 6. 이번 검증·남은 일

- 분석 완료: dev03–08 6개 원본 및 M2 성공 49개 목록/명령/이벤트, 223 파일 SHA, phase별 시간, 직접 자기 σ 대비 사후 오차, synthetic PF noise 시간격자 확인. 새 detector 전체 재생/새 모델 fit/실제 checkpoint 영상/운반 검증은 하지 않았다.
- 기존 입력·stop lag·full-beam geometry·loaded 중단 계약 회귀: **73 passed, 92 subtests passed**. 물리/model import 차단, `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, bytecode/cache OFF로 실행했고 `.pytest_tmp` 삭제 확인. 이 수치는 **현재 코드의 관련 회귀**이며 설계 후보 구현/전체 CI 통과가 아니다.
- TensorBoard 새 임시 snapshot **3 run 변환, scalar 수치와 HParams의 EventAccumulator 실제 재로딩 확인**. [전달 기록](loaded_stage_tensorboard.json)에 위치·event SHA를 적었다. shared viewing root `/Users/changmin/projects/ugrp/outputs/tensorboard`는 쓰기 허용 범위 밖이고, 이번 native Chrome 조회는 `cgWindowNotFound`로 실패했다. 따라서 공유 게시·핀·HParams GUI 확인은 미완료다. [기존 대시보드](http://127.0.0.1:6006)에 이번 진단이 보인다는 주장은 하지 않는다. 새 물리 영상도 없고 viewer/서버를 시작하지 않았다.
- `git fetch origin`은 공유 FETCH_HEAD 쓰기 제한, `gh`는 네트워크 제한으로 실패했고 연결 GitHub GET 도구로 이슈·PR 최신 상태를 확인했다. primary main은 시작 시 `ba0eb4f547996af880de65003442882c5326c71d`; 이번에는 병합/primary 갱신을 수행하지 않았다.
- 다음 구현의 선행조건: #240 병합과 dev09/10 검토, calibration coverage 및 static checkpoint feasibility, peer 기하 공유 없는 protocol 검토, source/bundle/seed/자원·raw 위치 동결. **설계 문서 작성은 완료, 구현·물리 dev는 미실행/준비 미완료**다.

### 재현 명령(오프라인 전용)

```sh
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_DIR=experiments/2026-09-27-zone-pair-parity
"$PAIR_PY" "$PAIR_DIR/loaded_stage_analysis.py"
"$PAIR_PY" "$PAIR_DIR/loaded_stage_tensorboard.py"
```

분석은 새 `loaded_stage_metrics.json`만 다시 쓰며 raw/기존 parity 결과는 읽기 전용이다. 변경된 분석 결과를 보존하려면 먼저 새 버전 파일명을 정한다. TensorBoard 변환기는 동일 source hash의 기존 snapshot을 재사용하고, 기존 receipt와 다른 source면 덮어쓰지 않고 실패한다. 위 명령에는 물리 실행 경로가 없다.
