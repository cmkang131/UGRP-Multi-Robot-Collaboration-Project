# VIS6 — 레시피 1 "정직한 갱신" 사전 계획 (dev 전용, 재생 전)

- 상태: **사전 등록. 재생·채점은 아직 하지 않았다.** 코드와 합성 단위 테스트만 있다. 실제 재생은 전원 연결 뒤 실행한다.
- 이슈: [#216](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216). 근거: `outputs/lit-review-tagfree-localization-20260928.md` 6.1절(1순위 레시피).
- 기준 SHA: `d5bd208e` (origin/main). 브랜치 `claude/vis6-recipe1`. 재생은 이 PR의 최종 커밋 SHA에 고정해서 실행한다.
- 기계 판독 계획: [`plan_v6.json`](plan_v6.json). 후보 설정 29개: [`configs/`](configs/). 둘 다 [`make_plan_v6.py`](make_plan_v6.py)가 결정적으로 만든다. 테스트가 바이트 단위 재생성을 확인한다.

## 무엇을 바꾸나

VIS5 PF(`vision_pf_v5.py`) 위에 VIS6 하위 클래스를 얹는다. 세 구성요소는 설정 블록 `vis6`로만 켠다. 모두 끄면(`vis6` 없음, `{}`, `{"eta": 1}`) VIS5 객체 경로를 그대로 쓴다. 입자·가중치·난수 상태·보고값이 같다(테스트). VIS3/VIS4/VIS5의 기존 소스 파일은 한 바이트도 바꾸지 않았다.

| 구성요소 | 설정 | 동작 | 근거 |
|---|---|---|---|
| 1a 갱신 게이팅 | `vis6.gating` `{min_d_m, min_yaw_rad, min_servo_pulse, mode}` | 마지막 적용 스캔 이후 **추정** 이동 ≥ d, 또는 yaw ≥ a, 또는 자기 팔·팬 명령 변화 ≥ Δpulse일 때만 비전 스캔 적용. `skip`은 반복 스캔을 버리고, `discount`는 k번째 반복을 1/(k+1)로 적용 | Nav2 AMCL `update_min_d/a`, CMU 16-831 강의 3 |
| 1b 우도 온도 | `vis6.eta` ∈ (0, 1] | 적용 스캔 로그우도 × η. 프레임 안 `effective_columns` 온도 위에 곱한다 | Thrun 외 AIJ 2001, Wu·Martin 2023 |
| 1c 영상 정지 검출 | `vis6.stall` (`vision_stall_v6.DEFAULT_STALL`) | 같은 팔 명령·정착·같은 짐 상태의 연속 두 프레임에서, 바닥 평면 워핑으로 예측 이동의 비율 s ∈ {0, .25, .5, .75, 1, 1.25}별 광도 잔차를 비교. s* ≤ .25이고 대비가 충분하면 `stall`: 그 프레임 구간의 예측 이동과 PF 속도 상태를 0으로 되돌림(ZUPT) | Foxlin 2005, Ward·Iagnemma 2008 |

- **"명령 적분만으로 이동을 판정하지 않는다."** 게이팅의 이동량은 1c 보정 **뒤**의 가중 평균 입자 이동이다. 그래서 `gating`은 `stall` 없이 켤 수 없다(생성 시 거부).
- 1c는 자기 RGB JPEG(고전 영상처리)와 자기 명령, 고정 카메라 보정만 쓴다. 바닥 표본은 같은 프레임의 자기 분할 관측(`r3/obs-w6`)에서 벽-바닥 경계 아래 행으로 제한한다. 질감이 없거나(구역 도색) 예측 영상 이동이 2 px 미만이면 `unknown`으로 판단을 보류한다.
- 2순위(초음파) 연결점: `update_range(t, reading)`. 주입된 입자별 로그우도 제공자(PR #248 모델 어댑터 예정)에 같은 η와 별도 게이트 상태를 적용한다. PR #248에는 의존하지 않는다. 이번 계획에서는 평가하지 않는다.
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
- validation: `vl3-dev-s945 vl3-dev-s946 vl3-dev-s947`. 이미 본 dev이므로 독립 test가 아니다.
- 관측 캐시 `outputs/vision-loc-20260926/r3/obs-w6`(checkpoint sha256 `3485390…`, 해시만 확인), `calibration_train.json`, 입자 2,000개, a1_open 설정(`effective_columns 8`, `sigma_px 2.5`, `settle_s 0.2`, `refine_px 6`, `consistency_px 4`).
- 신경망 추론 0프레임. test 에피소드는 `replay_v6.py`가 거부한다. GT(`eval_only/frames_eval.jsonl`)는 `evaluate`의 채점에만 쓴다.
- PF seed 색인 k: k=0은 에피소드 seed(VIS3/VIS4와 같음), k≥1은 `episode_seed*1000 + k`. 선택 단계는 k=0–2, 최종 validation은 k=0–4.

## 후보와 단계

| 단계 | 후보 | 자료 | 규칙 |
|---|---|---|---|
| P0 | T0 | fit, k=0–2 | `reproduce`: T0 k=0의 매 프레임 xyyaw가 저장된 VIS3 a1 추정과 같아야 함 |
| S1 (1b) | T0, T1b_eta050, T1b_eta025, T1b_eta0125 | fit, k=0–2 | 보정 선택 규칙 |
| S2 (1c 검출기) | T1c | fit, k=0–2 | 검출기 관문: 양성 ≥ 20, precision ≥ 0.80, recall ≥ 0.30 |
| S3 (1a) | T1ac_{d02a3, d02a6, d05a3, d05a6, d10a3, d10a6} (η=1) | fit, k=0–2 | fit XY NLL 최소, 동률은 앞 순서 |
| S4 (1a+b+c) | T1ac_⟨S3⟩, T1abc_⟨S3⟩_eta050/025/0125 | fit, k=0–2 | 보정 선택 규칙 |
| F | T0(기준) 대 T1abc_⟨S4⟩, T1ac_⟨S3⟩, T1b_⟨S1⟩, T1c | validation, k=0–4 | validation 관문 |

게이팅 격자: d ∈ {2, 5, 10} cm × yaw ∈ {3°, 6°}, Δpulse 10, 모드 `skip`. 1c 매개변수는 `DEFAULT_STALL` 그대로 고정한다(격자 없음).

**보정 선택 규칙(S1·S4)**: fit seed 평균 XY 95% 타원 포함률(full covariance, NEES ≤ 5.991)이 [0.90, 0.99] 안인 후보 중 fit 회차 균등 XY NLL이 가장 낮은 것. 동률이면 η가 큰 쪽(목록 앞). 정확도는 선택 기준이 아니다. 해당 후보가 없으면 그 단계는 후보를 내지 않는다.

**validation 관문(F)**: seed 평균으로 모두 만족해야 한다.
- XY 95% 포함률 90–99%, XY > 3σ(NEES > 11.83) ≤ 2%
- 문 위치 p90 악화 ≤ 0.3 cm, 문 횡 p99 악화 ≤ 0.3 cm, 문 yaw p90 악화 ≤ 0.2°(T0 대비)
- loaded XY σ p90 ≤ 7 cm("σ만 키우기" 방지)
- validation 세 회차 모두 XY NLL이 T0보다 나쁘지 않음
- 과신 소실 사건(오차 > max(3σ, 20 cm) 연속 묶음) 수가 T0보다 적음

통과 후보가 여럿이면 validation XY NLL이 가장 낮은 것을 채택한다(동률이면 위 목록 순서). 채택해도 기본 실행 설정은 이 PR에서 바꾸지 않는다. 폐루프·독립 test는 별도 계획이다.

보고 지표(선택에 쓰지 않는 것 포함): XY·yaw ANEES, 포함률, >3σ, NLL, 전체 위치 p90, 소실(>30 cm) 프레임, σ p90, 사건 수·프레임, 1c 검출기 precision/recall/보류율. 프레임은 시간 상관이 있으므로 ANEES는 χ² 검정이 아니라 기술 통계다.

## 정지 규칙

1. P0 재현 실패 → 비교 전에 **중단**(코드·자료 변동). 기록만 남기고 선택하지 않는다.
2. S2 검출기 관문 실패 → 1c 제외, 1a도 함께 제외(게이팅은 1c 필요). F는 T1b만 비교한다.
3. S1·S4에서 적격 후보 없음 → 그 단계는 후보 없음.
4. F 통과 후보 없음 → b0(VIS3 a1 = T0) 유지. 이 코호트에서 격자·임계값·규칙을 다시 조정하지 않는다. 새 아이디어는 새 계획으로 한다.
5. 호스트: 전원 연결에서만 실행(`run_units_v6.sh`가 배터리면 거부). 여유 공간 10 GiB 미만, ENOSPC, 중단된 실행은 HOST_ERROR다. 그 단위 전체를 새 출력 루트에서 다시 돌린다. `evaluate`는 불완전한 세트를 채점하지 않는다.
6. 예산: 누적 40 CPU시간을 넘으면 진행 중인 단계만 끝내고 멈춘 뒤 보고한다.

예산 추정: VIS3 a1의 단일 스레드 재생이 dev 9회 약 3,160 s였다. fit 한 세트(6회)는 약 37 CPU분, validation 한 세트(3회)는 약 16 CPU분이다. 계획 전체는 약 30 CPU시간이고, 4병렬이면 벽시계 8시간 안팎이다. 1c의 영상 처리 비용은 아직 재지 않았다. 산출물은 약 1 GB 이하로 예상한다.

## 재생 명령 (전원 연결 후)

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

# P0: T0 재현
$RUN -- "$P/run_units_v6.sh" "$OUT" "T0" "0 1 2" "$FIT"
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

# S4: G = select_S3.json의 chosen에서 "T1ac_" 뒤 (예: d05a3). S2가 실패했으면 S3·S4·T1c·T1ac는 건너뛴다
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
- 배터리 제약으로 새 테스트만 실행했다. 실제 자료 재생·시뮬레이션·신경망 추론은 하지 않았다. 기존 VIS 테스트 묶음과 CI 결과는 PR에서 따로 확인한다.

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
