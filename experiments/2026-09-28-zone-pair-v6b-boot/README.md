# v6b 출발 위치 부트스트랩 설계와 오프라인 검증 (2026-09-28, Claude)

tags_temporary 조작 진단이며 연구 결과가 아니다. 물리 코호트는 실행하지 않았다. 짧은 부트스트랩 probe의 실행 여부와 결과는 아래 "smoke 결과" 절이 유일한 기록이다.
weld OFF, 모델 호출 0. 제어 입력은 자기 손목 RGB·자기 발행 명령·정적 지도/보정뿐이다. GT는 제어에 들어가지 않고 평가 기록(`eval_*`, `eval_only/`)에만 있다.

> **태그 전용 경고.** 오늘의 부트스트랩 PF(`BootstrapLocalizer._usable`, 부모 우도)는 임시 벽 태그만 읽는다. 최종 환경에는 AprilTag가 없다.
> 무태그 환경에서의 동작은 **검증되지 않았다.** `initialize_from_prior`·`PoseReport` 계약을 구현하는 markerless 제공자(VIS6, #253)가 있어야 한다.

## 검토 #261 반영 (Codex 적대적 검토, 2026-09-28)

| 지적 | 수정 | 회귀 테스트 |
|---|---|---|
| 1 High: 부트스트랩 소진 뒤 다음 작업이 gate를 건너뛰고 팔 명령 | 소진은 gate를 풀지 않는다. 다음 이동 작업마다 새 정지 재관측을 통과해야 한다(`attempts` 기록) | `test_exhausted_bootstrap_keeps_refusing_motion_for_later_jobs` (dock 사전분포 없는 지도, 두 번째 `look_around`도 팔 명령 0) |
| 2 High: guard의 σ 상한(0.15 m/0.20 rad) 때문에 생긴 통과로 완료 | 완료는 gate LOW이거나, σ가 상한 이하(clamp 비활성)이고 guard가 첫 팔 전이를 통과시킬 때만. 기존 정책의 guard는 그대로 | `test_completion_rejects_clearance_that_exists_only_by_sigma_clamping` (검토자 사례 σxy 0.361 m) |
| 3 High: dual 표본 가중치가 제안 밀도 q를 무시, 우도 중복 | dual 표본을 **제거**했다. 올바른 b·L/q 버전도 구현해 재생했지만 첫 시야 결과가 달라지지 않았고(팬 시작 가능 13/20 vs 제거 12/20, σ점 검사 기준), 사전분포+팬 시야만으로 합성 테스트가 완료된다 | `test_prior_and_pan_scan_alone_reach_completion_without_dual_samples` (5개 자세) |
| 4 High: 원래 팬 복귀만으로 완료 | 완료는 원래 팬에서 정착 0.6 s 뒤 **현재** 보고로만 판정한다. 실패하면 `verify_failed`를 남기고 예산 안에서 계속 관측한다 | `test_restore_rechecks_after_settle_and_reobserves_when_the_fix_is_lost` |
| 5 Medium: 거부된 관측이 입자·가중치를 변경 | 부모의 품질 판정 뒤, 승인된 시야에만 믿음 추가와 resample-move를 한다. 거부된 시야는 아무것도 바꾸지 않는다 | `test_rejected_observation_leaves_particles_and_weights_untouched` |
| 6 Medium: workflow 2.4.0이 #249와 충돌 | main·열린 PR 최댓값 2.4.0(#249) 다음인 **2.5.0** | `tests/test_zone_study_integration_pair.py` |
| 7 문서 모순, "GT는 루프 뒤에만" 표현 | 이 README와 probe docstring을 고쳤다 | – |

검토 뒤 추가 변경이 하나 있다. 팬 전이 검사를 가우시안 σ점에서 **입자 기회 제약**으로 바꿨다.
첫 시야 뒤 posterior 표본은 세 dock 행에 모두 걸쳐 있었다(재생: 20/20 중 18건이 세 행). 이런 다봉 분포를 σ점은 벽 쪽으로 벗어난 점으로 바꿔 거부한다(첫 팬 20/40). 입자 검사는 36/40 통과했다.
테스트는 `test_particle_pan_check_handles_a_multimodal_row_belief`다.

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
| workflow | `zone-study-integration-run` 2.3.0 → **2.5.0** (#249가 2.4.0 사용). 새 `zone-pair-bootstrap-probe` 0.1.0 |
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
  - 기존 gate LOW(0.05 m/0.06 rad)를 만족한다. 또는 σ가 guard 상한(0.15 m/0.20 rad) 이하여서 clamp가 작동하지 않는 상태에서, 그 작업의 첫 팔 전이(LOOK_P20, 원래 팬)를 **변경 없는** SweepGuard가 통과시킨다.
  - 판정은 원래 팬으로 돌아와 0.6 s 정착한 뒤의 현재 보고로 한다.
- 팔 움직임 중 프레임 제외 규칙(명령 후 0.3 s)은 그대로다. 대신 관측 창을 첫 움직임 **앞에** 둔다.
- 오프라인에서 접힌 팔 첫 시야 하나로는 y–yaw 능선이 남았다(아래 A). 그래서 그 사이에 허용하는 감지 행동은 **카메라 팬(servo 6)뿐**이다.
  - 바퀴는 hold, 팔은 발행 자세를 유지한다. 팬마다 0.6 s 정착 후 관측한다.
  - 순서는 `WIDE_LOOK_PANS`다. 끝나면 원래 팬으로 돌아간다.
- 예산은 이동 작업마다 기존 10 s 정지 관측 예산(`SWEEP_REOBSERVE_S`)이다. 넘으면 움직이지 않고 `STATIONARY_BOOTSTRAP_NO_FIX`로 작업을 끝낸다.
  실패는 gate를 풀지 않는다. 다음 이동 작업도 새 정지 재관측부터 시작한다.
- 팬 시야는 한 번씩만 방문한다. 다시 방문하면 같은 시야의 약간 다른 프레임이 새 증거로 두 번 들어갈 수 있기 때문이다.

### 3. 팬 전이만 belief 검사 (입자 기회 제약)

- 기존 guard는 σxy=√(var_x+var_y)로 등방 팽창하고, σ를 0.15 m/0.20 rad에서 자른다.
  이 값에서는 모든 dock에서 **현재의 접힌 자세조차** 거부된다(서쪽 벽까지 0.4 m).
- Blackmore 외(2010)의 입자 근사 기회 제약처럼 믿음의 입자 가설에서 충돌을 검사한다(RRBT도 평균이 아닌 믿음을 검사한다).
  posterior에서 체계적으로 뽑은 표본 64개와 평균, 모두에서 변경 없는 guard가 추가 팽창 없이(σ=0) 통과해야 한다.
- `belief_hypotheses`가 없는 제공자는 평균과 3×3 공분산 σ점 6개(k=2)로 대체한다.
- 적용 범위는 부트스트랩 중 **팬 전이뿐**이다. 팔 올림은 기존 guard와 gate를 그대로 쓴다.

### 4. 정지 믿음의 PF 표본 (결핍 대응)

- 사전분포는 넓고 한 시야의 우도는 날카롭다. 그래서 관측과 맞는 표본이 거의 없다(v6 재생: posterior support 1.5%).
- 대응은 **resample-move MCMC**(Gilks & Berzuini 2001) 하나다. 부모가 승인한 시야 뒤에만 돈다.
- 로봇이 정지해 있으므로 정확한 믿음은 사전분포 × Π p(z_j|x)이고, 이 믿음을 불변 목표로 둔다.
  정지 확산과 예측 단계마다 누적되는 지도 벌점은 목표에 포함하지 않는 근사다.
- 같은 프레임을 새 증거로 다시 쓰지 않는다. 같은 픽셀 프레임은 제공자가 여전히 버린다.
- 첫 초안의 Mixture-MCL dual 표본은 검토 #261 뒤 제거했다(위 표).
- 바퀴 명령이 오면 즉시 끝난다. 시야 6개가 상한이다.

모든 판단은 `PoseReport`(`last_fix_t`, `observation_quality`, 평균, `cov`)만 쓴다.
태그 ID·개수 조건은 없다. markerless 제공자는 `initialize_from_prior`를 구현해야 하며, 태그 대체 경로는 없다.

## 오프라인 재생 (물리 없음)

실행: `replay_bootstrap_v6b.py <raw> offline_replay.json 4` (기록 PF seed + 추가 seed 4개).
요약은 [replay_summary.json](replay_summary.json)이다. raw는 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v6-3c26acddec066adcd9164e6d2a6f51c1261c5f66/`이며, 6회 × r1/r2의 저장 JPEG·명령만 읽었다.

### A. 첫 정지 시야 (실패 4회, 로봇 8개 × PF seed 5개 = 40행)

검토 #261 수정 뒤 소스로 다시 재생한 값이다. 첫 판의 v6b 행(σ 0.26–0.56 m)은 잘못 가중된 dual 표본의 결과이며 폐기했다.

| 일정 | σxy (m) | 평가 오차 xy (m) | informative fix | 팔 올림 guard (기존, σ clamp) | 첫 팬(1230) 입자 검사 | 어느 팬이든 입자 검사 |
|---|---|---|---:|---|---:|---:|
| v5h 기록대로 | 0.97–1.30 | 0.12–0.81 | – | clear 40 | 26/40 | 30/40 |
| v6 기록대로 (실패 재현) | **2.68–2.91** | 2.71–3.27 | 0/40 | wait 40 | 0/40 | 0/40 |
| v6b 사전분포만, 명령 기록대로 (프레임 제외) | 1.20–1.23 | 0.21–1.44 | 0/40 | clear 40 | 16/40 | 28/40 |
| stop-and-look만 (사전분포 없음) | 0.41–0.59 | 0.01–0.11 | 4/40 | clear 26 / wait 14 | 36/40 | 36/40 |
| **v6b 첫 시야 (사전분포 + stop-and-look)** | **0.43–0.99** | 0.06–0.62 | 0/40 | clear 40 | **36/40** | **40/40** |

- 기록된 실패값(2.7031 m)을 v6 일정에서 그대로 재현했다(기록 seed 2.7086 m, 호출 시각 1.4 s).
- v6b는 첫 시야로 σ를 2.7–2.9 m에서 0.43–0.99 m로 줄인다. 하지만 행을 확정하지는 못한다(posterior 표본이 대부분 세 행에 걸침). **한 시야만으로는 guard가 원칙적으로 요구하는 σ에 닿지 못한다.**
  - dock에서 변경 없는 guard는 σ≈0.10 m/0.10 rad에서 통과하고, 상한값에서는 막힌다.
  - 태그가 약 2.9 m 앞에 모여 있어 y와 yaw가 서로 상쇄되는 능선이 남는다. 우도 단면에서 ±0.3–0.5 m 안이 1 nat 이내였다.
  - 팔 올림 "clear"는 모두 σ를 상한에서 자르기 때문에 생긴 통과다. v5h의 통과와 같은 종류의 운이다. 새 완료 규칙은 σ가 상한을 넘으면 이것을 받지 않는다.
- v6b에서는 입자 검사로 어느 팬이든 40/40이 허용됐다. 스캔을 시작할 수 있다는 뜻이다. 같은 경우를 σ점 대체 검사로 보면 20/40이다. v6 기록 일정은 0/40이었다.
- v5h 2회의 출발 프레임도 같은 결과다(v5h 일정 σ 0.97–1.30 m 불변).

### B. 여러 정지 시야의 PF 동작 (v5h 2회, v6b 일정 아님)

v5h 실행은 60.7 s까지 dock에 서 있으면서 팔을 올리고 팬했다. 그 자기 프레임을 v6b localizer에 넣었다.
정착 규칙은 실행기와 같다. resample-move와 거부 무변경 규칙이 여러 시야를 합쳐도 망가지지 않는지 확인하는 용도다.

| 실행·로봇 | v5h PF σxy / 오차 | v6b PF σxy / 오차 | v6b 첫 informative fix |
|---|---|---|---|
| s911 r1 | 0.032 / 0.051 m | 0.038 / 0.008 m | 2.30 s (σ 0.14 m) |
| s911 r2 | 0.043 / 0.008 m | 0.045 / 0.010 m | 2.30 s (σ 0.31 m) |
| s912 r1 | 0.032 / 0.053 m | 0.039 / 0.007 m | 2.30 s (σ 0.21 m) |
| s912 r2 | 0.042 / 0.019 m | 0.044 / 0.030 m | 2.30 s (σ 0.29 m) |

- 두 PF 모두 gate LOW에 들고 guard도 clear다. v6b의 평가 오차가 더 작고 σ는 조금 더 보수적이다.
- 첫 informative fix의 σ는 0.14–0.31 m다. 그래서 "informative fix만으로 끝내지 않는다" 규칙을 두었다.

### 합성 시야 (단위 테스트, 접힌 팔 팬 스캔)

`tests/test_owncam_bootstrap_v6b.py`의 합성 검출(보정 카메라 모델, 0.3 px 잡음)로 세 dock과 섭동 자세를 확인했다.
dual 표본 없이, 6개 자세 × PF seed 3개 = 18/18이 새 완료 규칙(σ 상한 이하 + guard, 또는 gate LOW)을 2–3번째 시야에서 만족했다.
예: y=0.55 행 0.96 → 0.16 → 0.095 m. 완료 시 평가 오차는 최대 0.18 m였다(σ 0.147 m).
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
# 1건 smoke
OMP_NUM_THREADS=2 python3 scripts/ugrp_session.py run v6b-boot-probe -- \
  .venv-sim/bin/python scripts/probe_zone_pair_bootstrap.py \
  --output /Users/changmin/projects/ugrp/outputs/zone-pair-v6b-boot-probe-<sha>/smoke \
  --seeds 911 --docks seeded --perturb 0,0,0 --policy b-boot
# grid (미실행; agent_lock status 확인 후)
... --seeds 911 912 913 914 --docks seeded rot1 rot2 \
    --perturb 0,0,0 0.05,0,0 0,0.05,0 0,-0.05,0 0,0,0.1 0,0,-0.1 --policy b-boot
```

### smoke 결과: 미실행 (물리 잠금)

- 소스 커밋(e4c5c7c2) 뒤 `agent_lock status`를 확인했다. 다른 작업(`claude/pair-stage-probes`, PID 39242, "pair stage probes v6 policies smoke+grid")이 잠금을 잡고 있었다.
  예상 종료는 2026-09-28 22:56 (로컬)이다.
- 규칙(잠금 중 물리 새로 시작 금지)에 따라 smoke를 시작하지 않았다. 앞선 잠금 해제 틈은 회귀 테스트가 끝나기 전이라 소스가 커밋되지 않은 상태였다.
- 따라서 접힌 팔 팬 스캔이 실제 렌더 영상에서 guard 통과까지 가는지는 **아직 모른다**. 잠금이 풀리면 위 1건 명령을 먼저 실행한다.

## 검증 범위와 남은 위험

- 오프라인 A는 첫 정지 시야만 검증한다. 접힌 팔 팬 시야는 어떤 저장 실행에도 없다. 그 부분의 근거는 합성 테스트와 아래 "smoke 결과" 절뿐이다.
- probe grid와 v6b 전체 코호트는 실행하지 않았다. A 플래그(빔 상대 정렬)는 여전히 물리에서 도달한 적이 없다.
- 팬 전이 입자 검사는 표본 64개 근사다(허용 위반 확률 약 1/64 수준). 표본 밖의 꼬리는 보장하지 않는다.
- resample-move 목표는 정지 확산과 예측마다 누적되는 지도 벌점을 포함하지 않는다. 전체 필터 posterior의 정확한 불변성은 입증하지 않았다.
- 부트스트랩이 성공하면 첫 팔 올림은 가능해진다. 그 뒤 v5h와 같은 정렬 재관측 실패(dev09–14, v6 v5h)는 이 변경과 무관하게 남는다.
- 매칭 seed 911/912는 부트스트랩 설계에 쓴 출발 프레임과 같다. v6b 코호트는 짝지은 개발 확인이지 held-out 결과가 아니다.
- **태그 전용.** 최종 환경에는 AprilTag가 없다. 부트스트랩 PF와 관측 경로는 임시 태그 제공자다. 무태그 동작은 검증되지 않았다.
  markerless 제공자(VIS6, #253)가 같은 계약(`initialize_from_prior`, `belief_hypotheses` 권장, 보고 영수증)을 구현해야 한다.
- v6b를 실행하려면 PR #259의 REGISTERED 경로가 필요하다. 이 PR은 main 기준이다. 둘 다 `scripts/zone_pair_v6_contract.py`를 바꾸므로 병합 순서에 따라 충돌 해소가 필요하다.

## 참고 자료

- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press, 2005. 8장 Monte Carlo Localization(초기 믿음, 전역 위치 추정, 입자 결핍·복구).
- ROS `amcl` 문서, `initial_pose_*`·`initial_cov_xx/yy/aa` 기본값(0.5·0.5, 0.5·0.5, (π/12)²): https://wiki.ros.org/amcl
- D. Fox, W. Burgard, S. Thrun, "Active Markov localization for mobile robots," *Robotics and Autonomous Systems* 25(3–4), 1998: https://doi.org/10.1016/S0921-8890(98)00049-9
- S. Thrun, D. Fox, W. Burgard, F. Dellaert, "Robust Monte Carlo localization for mobile robots," *Artificial Intelligence* 128(1–2), 2001 (Mixture-MCL; 첫 초안에서 쓰고 검토 뒤 제거).
- L. Blackmore, M. Ono, A. Bektassov, B. C. Williams, "A probabilistic particle-control approximation of chance-constrained stochastic predictive control," *IEEE Trans. Robotics* 26(3), 2010: https://doi.org/10.1109/TRO.2010.2044948
- W. R. Gilks, C. Berzuini, "Following a moving target — Monte Carlo inference for dynamic Bayesian models," *J. R. Stat. Soc. B* 63(1), 2001 (resample-move).
- A. Bry, N. Roy, "Rapidly-exploring Random Belief Trees for motion planning under uncertainty," ICRA 2011: https://doi.org/10.1109/ICRA.2011.5980508
- S. J. Julier, J. K. Uhlmann, "Unscented filtering and nonlinear estimation," *Proc. IEEE* 92(3), 2004 (σ점 대체 검사): https://doi.org/10.1109/JPROC.2003.823141
- 검토 #261 원문: 기본 체크아웃 `outputs/review-261-20260928.md` (Codex, 검토 SHA 8229cde4)
- v6 dev 결과와 실패 분석: PR #259 `experiments/2026-09-28-zone-pair-v6/dev-runs/README.md`
