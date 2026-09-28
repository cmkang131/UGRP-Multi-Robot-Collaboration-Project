# v6b 출발 위치 부트스트랩 설계와 오프라인 검증 (2026-09-28, Claude)

tags_temporary 조작 진단이며 연구 결과가 아니다. 물리 코호트는 실행하지 않았다(짧은 부트스트랩 probe 1건만, 아래).
weld OFF, 모델 호출 0. 제어 입력은 자기 손목 RGB·자기 발행 명령·정적 지도/보정뿐이다. GT는 평가 열(`eval_*`)에만 있다.

## 왜 (v6 dev 실패, PR #259)

- v6 b-only·a+b 4회는 출발 직후 첫 `look_around`에서 `SWEEP_TRANSITION_BLOCKED`로 멈췄다.
- 태그가 보이는 자기 프레임은 1.30025 s 하나뿐이었다. 첫 팔 명령(1.3 s)보다 0.25 ms 늦었다.
  v6 PF는 이 프레임을 "팔 움직임"으로 버렸고, σxy는 2.7–2.9 m에 머물렀다. 그래서 팔 올림 guard가 막혔다.
- dev03–04에 이은 **같은 실패의 두 번째**다. 전역 지침(두 번 막히면 검증된 방법)에 따라 국소 임계값을 고치지 않았다.
  아래 문헌 방법을 그대로 가져왔다.

## 무엇을 바꿨나 (새 번들 v75, 기존 정책 불변)

| 항목 | 값 |
|---|---|
| 번들 | `zone-pair-v75-dock-prior-bootstrap` (v70은 `RETIRED_BUNDLE_IDS`로 이동) |
| 번호 근거 | main v70, 열린 PR v72(#256)·v73(#257)·v74(#249)를 `git grep`으로 확인했다. v75는 어느 브랜치에도 없다. |
| 새 정책 | `b-boot`, `a+b-boot` (`stationary_bootstrap=True`) |
| 불변 | `v5h`, `b-only`, `a+b`의 플래그와 동작. 부트스트랩 상태가 없는 제공자는 실행기 훅을 그대로 지나간다(단위 테스트로 확인). |
| workflow | `zone-study-integration-run` 2.3.0 → 2.4.0. 새 `zone-pair-bootstrap-probe` 0.1.0 |
| 사전등록 | `prereg_v6b.json` **DRAFT** (prepare-only, 승인·실행 소스 없음). v6 DRAFT는 이력으로 남긴다. 자기 커밋의 blob으로만 감사한다(`verify_v6_historical`). |

코드: `harness/owncam_bootstrap_v6b.py`(새 파일), `harness/zone_own_executor.py`(opt-in 훅), `harness/zone_pair_executor.py`(PairTeam opt-in),
`harness/zone_pair_v6_policy.py`, `scripts/zone_pair_v6_contract.py`, `scripts/probe_zone_pair_bootstrap.py`(새 파일).

### 1. AMCL식 사전분포 (정적 지도 dock 행)

- MCL은 사전 믿음 bel(x0)에서 시작한다. 사전 정보가 없을 때만 전역 균일 초기화를 쓴다(Probabilistic Robotics 8장).
- ROS `amcl`의 `initial_pose`·`initial_cov` 기본값(σ 0.5 m, 0.5 m, π/12 rad)을 그대로 썼다.
- 바꾼 점은 하나다. 지도에 dock 행이 셋(`zone_start_dock_v3`, y=−2.25/−0.85/0.55, x=−0.65, yaw 0)이고 로봇-행 배정은 없다.
  그래서 행마다 AMCL 가우시안 하나씩, 같은 가중치로 섞었다.
- dock 행은 호스트가 이미 idle keep-out에 쓰는 정적 지도 정보다. 실시간 자세가 아니다. profile seal(sha256)이 맞아야 쓴다.
- 사전분포는 fix가 아니다. fix 시각·informative 영수증을 만들지 않는다.
- 세션 시작(미초기화, 바퀴 명령 없음)에만 적용한다. 아니면 적용하지 않고 이유를 기록한다.

### 2. 정지 관측과 능동 팬 (stop-and-look)

- Active Markov Localization처럼, 믿음이 모호하면 움직이기 전에 먼저 본다.
- 실행기는 두 조건이 모두 될 때까지 자기 팔·바퀴 명령을 내지 않는다.
  - 제공자가 정착된 프레임에서 informative fix를 보고한다.
  - 그 작업의 첫 팔 전이(LOOK_P20, 원래 팬)를 **변경 없는** SweepGuard가 통과시킨다. 또는 기존 gate LOW(0.05 m/0.06 rad)를 만족한다.
- 팔 움직임 중 프레임 제외 규칙(명령 후 0.3 s)은 그대로다. 대신 관측 창을 첫 움직임 **앞에** 둔다.
- 오프라인에서 접힌 팔 첫 시야 하나로는 y–yaw 능선이 남았다(아래 A). 그래서 그 사이에 허용하는 감지 행동은 **카메라 팬(servo 6)뿐**이다.
  - 바퀴는 hold, 팔은 발행 자세를 유지한다. 팬마다 0.6 s 정착 후 관측한다.
  - 순서는 `WIDE_LOOK_PANS`다. 끝나면 원래 팬으로 돌아간다.
- 예산은 기존 10 s 정지 관측 예산(`SWEEP_REOBSERVE_S`)이다. 넘으면 움직이지 않고 `STATIONARY_BOOTSTRAP_NO_FIX`로 작업을 끝낸다.

### 3. 팬 전이만 belief 검사 (RRBT식)

- 기존 guard는 σxy=√(var_x+var_y)로 등방 팽창하고, σ를 0.15 m/0.20 rad에서 자른다.
  이 값에서는 모든 dock에서 **현재의 접힌 자세조차** 거부된다(서쪽 벽까지 0.4 m).
- RRBT(Bry & Roy)처럼 믿음의 k-σ 불확실도 타원을 장애물과 대조했다.
  보고된 3×3 공분산의 평균과 ±k·σ 주축 점 6개에서, 변경 없는 guard를 추가 팽창 없이(σ=0) 검사한다. k=`K_SIGMA`=2이다.
- 적용 범위는 부트스트랩 중 **팬 전이뿐**이다. 팔 올림은 기존 guard와 gate를 그대로 쓴다.

### 4. 정지 믿음의 PF 표본 (결핍 대응)

- 사전분포는 넓고 한 시야의 우도는 날카롭다. 그래서 관측과 맞는 표본이 거의 없다(v6 재생: posterior support 1.5%).
- 대응은 두 가지다.
  - **Mixture-MCL dual 표본**(Thrun·Fox·Burgard·Dellaert 2001): 기존 sensor-resetting 제안(`_reset_from`)에서 20%를 뽑고, 예측 믿음으로 가중한다.
  - **resample-move MCMC**(Gilks & Berzuini 2001): 같은 믿음을 불변 목표로 둔다.
- 로봇이 정지해 있으므로 정확한 믿음은 사전분포 × Π p(z_j|x)다(정지 확산 제외).
  두 방법 모두 같은 프레임을 새 증거로 다시 쓰지 않는다. 같은 픽셀 프레임은 제공자가 여전히 버린다.
- 바퀴 명령이 오면 즉시 끝난다. 시야 6개가 상한이다.

모든 판단은 `PoseReport`(`last_fix_t`, `observation_quality`, 평균, `cov`)만 쓴다.
태그 ID·개수 조건은 없다. markerless 제공자는 `initialize_from_prior`를 구현해야 하며, 태그 대체 경로는 없다.

## 오프라인 재생 (물리 없음)

실행: `replay_bootstrap_v6b.py <raw> offline_replay.json 4` (기록 PF seed + 추가 seed 4개).
요약은 [replay_summary.json](replay_summary.json)이다. raw는 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v6-3c26acddec066adcd9164e6d2a6f51c1261c5f66/`이며, 6회 × r1/r2의 저장 JPEG·명령만 읽었다.

### A. 첫 정지 시야 (실패 4회, 로봇 8개 × PF seed 5개 = 40행)

| 일정 | σxy (m) | 평가 오차 xy (m) | informative fix | 팔 올림 guard (기존) | 첫 팬 belief 검사 |
|---|---|---|---:|---|---:|
| v5h 기록대로 | 0.97–1.30 | 0.12–0.81 | – | clear 40 (σ 상한 덕분) | 0/40 |
| v6 기록대로 (실패 재현) | **2.68–2.91** | 2.71–3.27 | 0/40 | wait 40 | 0/40 |
| v6b 사전분포만, 명령 기록대로 (프레임 제외) | 1.20–1.23 | 0.21–1.44 | 0/40 | clear 40 (σ 상한) | 0/40 |
| stop-and-look만 (사전분포 없음) | 0.41–0.59 | 0.01–0.11 | 4/40 | clear 26 / wait 14 | 24/40 |
| **v6b 첫 시야 (사전분포 + stop-and-look)** | **0.26–0.56** | 0.05–0.22 | 0/40 | clear 26 / wait 14 | **36/40** |

- 기록된 실패값(2.7031 m)을 v6 일정에서 그대로 재현했다(기록 seed 2.7086 m, 호출 시각 1.4 s).
- v6b는 첫 시야로 σ를 2.7–2.9 m에서 0.26–0.56 m로 줄이고 맞는 dock 행을 고른다. 하지만 **한 시야만으로는 guard가 원칙적으로 요구하는 σ에 닿지 못한다.**
  - dock에서 변경 없는 guard는 σ≈0.10 m/0.10 rad에서 통과하고, 상한값에서는 막힌다.
  - 태그가 약 2.9 m 앞에 모여 있어 y와 yaw가 서로 상쇄되는 능선이 남는다. 우도 단면에서 ±0.3–0.5 m 안이 1 nat 이내였다.
  - "clear 26"은 σ를 0.15 m에서 자르기 때문에 생긴 통과다. v5h의 통과와 같은 종류의 운이다. 그래서 v6b는 이것으로 끝내지 않는다.
- 첫 팬(1230)의 belief 검사는 v6b에서 36/40 통과했다. v6 기록 일정은 0/40이었다. 스캔을 시작할 수 있다는 뜻이다.
- v5h 2회의 출발 프레임도 같은 결과다(v5h 일정 σ 0.97–1.30 m 불변, v6b 첫 시야 0.26–0.56 m).

### B. 여러 정지 시야의 PF 동작 (v5h 2회, v6b 일정 아님)

v5h 실행은 60.7 s까지 dock에 서 있으면서 팔을 올리고 팬했다. 그 자기 프레임을 v6b localizer에 넣었다.
정착 규칙은 실행기와 같다. dual 표본·resample-move가 여러 시야를 합쳐 망가지지 않는지 확인하는 용도다.

| 실행·로봇 | v5h PF σxy / 오차 | v6b PF σxy / 오차 | v6b 첫 informative fix |
|---|---|---|---|
| s911 r1 | 0.032 / 0.051 m | 0.040 / 0.009 m | 2.30 s (σ 0.23 m) |
| s911 r2 | 0.043 / 0.008 m | 0.046 / 0.009 m | 2.10 s (σ 0.39 m) |
| s912 r1 | 0.032 / 0.053 m | 0.040 / 0.008 m | 2.30 s (σ 0.18 m) |
| s912 r2 | 0.042 / 0.019 m | 0.044 / 0.002 m | 2.10 s (σ 0.29 m) |

- 두 PF 모두 gate LOW에 들고 guard도 clear다. v6b의 평가 오차가 더 작고 σ는 조금 더 보수적이다.
- 첫 informative fix의 σ는 0.18–0.39 m다. 그래서 "informative fix만으로 끝내지 않는다" 규칙을 두었다.

### 합성 시야 (단위 테스트, 접힌 팔 팬 스캔)

`tests/test_owncam_bootstrap_v6b.py`의 합성 검출(보정 카메라 모델, 0.3 px 잡음)로 세 dock과 섭동 자세를 확인했다.
σxy는 팬마다 줄었다(예: y=0.55 행 0.33 → 0.15 → 0.09 → 0.06 → 0.046 m). 세 행 모두 맞는 행을 골랐다(오차 ≤ 0.1 m).
합성 검출이며 실제 렌더 영상의 검출률·오검출은 반영하지 않는다.

## 짧은 부트스트랩 probe (전체 E2E 대신)

`scripts/probe_zone_pair_bootstrap.py`의 동작은 다음과 같다.

1. pair 장면을 세운다.
2. r1·r2가 dev 배우와 같은 첫 `look_around`를 요청한다.
3. 둘 다 결과가 나오면 즉시 끝낸다. 통과는 팔 올림 전이 후 팬 단계 진입이고, 실패는 작업 종료다(기본 25 SIM s 상한).

- grid는 seed × dock 배정(`seeded`/`rot1`/`rot2`) × 섭동(`dx,dy,dyaw`, ≤0.15 m/0.35 rad, 설치 전용)이다.
- 사례별로 결과·시간·σ·부트스트랩 영수증·명령을 남긴다. `eval_only` 열에만 GT를 둔다.
- 대조로 `--policy v5h|b-only`도 받는다.

```bash
# 1건 smoke (이 PR에서 실행한 것)
OMP_NUM_THREADS=2 python3 scripts/ugrp_session.py run v6b-boot-probe -- \
  .venv-sim/bin/python scripts/probe_zone_pair_bootstrap.py \
  --output /Users/changmin/projects/ugrp/outputs/zone-pair-v6b-boot-probe-<sha>/smoke \
  --seeds 911 --docks seeded --perturb 0,0,0 --policy b-boot
# grid (미실행; agent_lock status 확인 후)
... --seeds 911 912 913 914 --docks seeded rot1 rot2 \
    --perturb 0,0,0 0.05,0,0 0,0.05,0 0,-0.05,0 0,0,0.1 0,0,-0.1 --policy b-boot
```

smoke 결과는 이 소스 커밋 뒤 실행해 "smoke 결과" 절에 추가한다.

## 검증 범위와 남은 위험

- 오프라인 A는 첫 정지 시야만 검증한다. 접힌 팔 팬 시야는 어떤 저장 실행에도 없다. 합성 테스트와 probe smoke 1건만 있다.
- probe grid와 v6b 전체 코호트는 실행하지 않았다. A 플래그(빔 상대 정렬)는 여전히 물리에서 도달한 적이 없다.
- 팬 전이 belief 검사는 가우시안 σ점 근사다. 휘어진 능선의 꼬리는 놓칠 수 있다. 필요하면 입자 기회 제약으로 바꾼다.
- 부트스트랩이 성공하면 첫 팔 올림은 가능해진다. 그 뒤 v5h와 같은 정렬 재관측 실패(dev09–14, v6 v5h)는 이 변경과 무관하게 남는다.
- 매칭 seed 911/912는 부트스트랩 설계에 쓴 출발 프레임과 같다. v6b 코호트는 짝지은 개발 확인이지 held-out 결과가 아니다.
- 최종 환경에는 AprilTag가 없다. 이 PF 경로는 임시 태그 제공자다. markerless 제공자는 같은 계약(`initialize_from_prior`, 보고 영수증)을 구현해야 하며 아직 없다.
- v6b를 실행하려면 PR #259의 REGISTERED 경로가 필요하다. 이 PR은 main 기준이다. 둘 다 `scripts/zone_pair_v6_contract.py`를 바꾸므로 병합 순서에 따라 충돌 해소가 필요하다.

## 참고 자료

- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press, 2005. 8장 Monte Carlo Localization(초기 믿음, 전역 위치 추정, 입자 결핍·복구).
- ROS `amcl` 문서, `initial_pose_*`·`initial_cov_xx/yy/aa` 기본값(0.5·0.5, 0.5·0.5, (π/12)²): https://wiki.ros.org/amcl
- D. Fox, W. Burgard, S. Thrun, "Active Markov localization for mobile robots," *Robotics and Autonomous Systems* 25(3–4), 1998: https://doi.org/10.1016/S0921-8890(98)00049-9
- S. Thrun, D. Fox, W. Burgard, F. Dellaert, "Robust Monte Carlo localization for mobile robots," *Artificial Intelligence* 128(1–2), 2001 (Mixture-MCL, dual sampling).
- S. Lenser, M. Veloso, "Sensor resetting localization for poorly modelled mobile robots," ICRA 2000 (`_reset_from`의 근거).
- W. R. Gilks, C. Berzuini, "Following a moving target — Monte Carlo inference for dynamic Bayesian models," *J. R. Stat. Soc. B* 63(1), 2001 (resample-move).
- A. Bry, N. Roy, "Rapidly-exploring Random Belief Trees for motion planning under uncertainty," ICRA 2011: https://doi.org/10.1109/ICRA.2011.5980508
- S. J. Julier, J. K. Uhlmann, "Unscented filtering and nonlinear estimation," *Proc. IEEE* 92(3), 2004 (σ점): https://doi.org/10.1109/JPROC.2003.823141
- v6 dev 결과와 실패 분석: PR #259 `experiments/2026-09-28-zone-pair-v6/dev-runs/README.md`
