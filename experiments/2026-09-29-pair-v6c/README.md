# 공동 운반 v6c: PF fix 시계 + 파지 입장 허용오차 (2026-09-29, Claude)

**stage probe, not E2E success.** 모든 물리 결과는 PR #260 단계 probe 하네스의 단계 하나 통과다. E2E 성공도, 학생 성공도 아니다.
조건: weld OFF, `cargo_noslip_v1`, 모델 호출 0. 제어에는 정답(GT)을 넣지 않는다. GT는 staging(teacher 예외)과 `eval_only/` 판정에만 쓴다.

Refs #221. #260(단계 probe 첫 격자·v6 정책 probe)의 후속이다.

## 한 줄 요약

(물리 결과 뒤에 기입)

## 버전

| 항목 | 값 | 이유 |
|---|---|---|
| 실행 번들 | `zone-pair-v76-fixclock-grasp-entry` | main v70, 열린 PR 최댓값 v75(#261) 다음 |
| 정책 | `b-v6c` = `posterior_relook` + `exact_fix_clock` + `grasp_range_entry` | 새 플래그 2개는 opt-in. v5h·b-only·a+b 동작은 바뀌지 않음 |
| 등록 revision | `v6c` (`experiments/2026-09-29-pair-v6c/prereg_v6c.json`, DRAFT) | v6(#259, REGISTERED)는 등록 커밋 3c26acdd 기준 historical 감사만 한다(#262 방식) |
| workflow `zone-study-integration-run` | `2.6.0` **예약, 카탈로그 반영 보류** | #249 2.4.0, #261 2.5.0 다음. REGISTERED v6 prereg가 `configs/simulation_workflows.json` 전체를 해시하므로 v6-historical PR 병합 전에는 카탈로그를 고치지 않는다 |
| probe | `PROBE_VERSION 0.3.0` (`b-v6c` 추가) | workflow 행 등록은 #260과 같이 보류 (`workflow_registration_pending.json`) |

v70은 v6 dev 코호트(#259)가 기록한 소스라서 `RETIRED_BUNDLE_IDS`에 보존한다.

## 문제 1: v6 b-only 정렬 relook의 음수 fix 나이

### 증상 (#260 Run A)

v6 b-only 정렬 25건이 모두 `ALIGN_RELOOK_NO_FIX`로 끝났다. 거부된 relook fix 125건 중 116건은 `fix_age_valid` 하나만 실패했다. 기록된 나이는 −6.7e-14 … −2.5e-13 s였다.

### 근본 원인

SIM 시각을 표현하는 float 누적값 두 개가 만났다.

- fix 시각은 자기 프레임의 원래 캡처 시각이다(`update(t)`의 `t`). 이 값 자체가 0.00025 s 물리 스텝을 호스트에서 누적한 값이다. 예: `1.5002500000000847`.
- PF 시계 `self.t`는 별도 누적값이다. `OwnCamLocalizer.predict_to(t)`는 `min(STEP_S, t − self.t)`씩 더하다가 `self.t ≥ t − 1e-9`이면 멈춘다. 그래서 스텝 합이 `t`보다 최대 1e-9 s **앞에서** 끝날 수 있다.
- `RecoveryLocalizer.estimate`는 `fix_age_s = self.t − last_fix_t`를 반올림 없이 보고한다. 그래서 이 프레임에서 만든 fix의 나이가 음수가 되고 `accepted_fix_checks`가 거부했다.
- v5h는 `round(age, 3)`로 같은 불일치를 가렸다. #260의 진단 패치 `fix_age_round`는 이 가림을 다시 넣어 원인을 확인한 것이다. 제어기 수정은 아니었다.

기록값으로 재현했다. 앞 fix 1.300250000000018과 프레임 1.5002500000000847로 predict하면 나이가 정확히 −6.661338147750939e-14 s다(`tests/test_zone_pair_v6c.py`).

### 수정 (`harness/owncam_recovery_v6c.py`, 플래그 `exact_fix_clock`)

나이가 아니라 시계를 고쳤다. `predict_to(t)`가 루프 자체의 허용오차(1e-9 s) 안에서 `t` 직전에 멈추면, PF 상태에 요청 시각 `t`를 그대로 붙인다.

- 이는 Bayes 필터 구현의 표준 방식이다. robot_localization `FilterBase::processMeasurement`는 `predict(measurement.time_, delta)`를 부른 뒤 `lastMeasurementTime_ = measurement.time_`로 **측정 시각**을 상태 시각으로 쓴다.
- 건너뛰는 구간은 루프 자체의 허용오차보다 짧으므로 버려지는 운동이 없다.
- 시계는 뒤로 가지 않는다. PF 시계보다 오래된 프레임은 앞으로 당기지 않으므로 나이가 양수로 남는다.
- 사후분포와 객체 정체성(`enable_provider`의 같은 객체)은 v6 그대로다. 나이 반올림이나 clamp는 쓰지 않는다.

## 문제 2: 정렬 허용오차(ex ±12 mm)와 파지 입장(ex −8…−4 mm)의 불일치

### 증상 (#260 경계 격자, v5h)

정렬 정지는 |ex| ≤ 12 mm를 받아들이지만, 바뀌지 않은 파지 입장은 ex −8…−4 mm에서만 통과했다. 실패한 로봇은 항상 r1이었다.

- ex ≥ 0: pre-close에서 빔 추정이 없어 `PREGRASP_NOT_READY`로 끝났다.
- ex −12 / ey −8 / corner++−: standoff fit이 실패했다(`PREGRASP_BEAM_UNCERTAIN`).

### 근본 원인 (기록된 자기 프레임 재생, [replay_boundary_entry.py](replay_boundary_entry.py))

standoff 축 fit과 pre-close 부분 관측 검사는 **v1 lime 픽셀**(hue 36–54)만 빔 윗면에 투영했다. 그런데 파지 거리에서 빔 윗면은 노랗게(hue ≈ 30) 렌더된다. `owncam_pair_beam_v2`가 이미 이 현상을 기록했고(dev 613), `grip_view`/co-motion에서는 `beam_colour_mask`(hue 25–54, S ≥ 100, V ≥ 120)로 처리한다. 이 두 검사만 그 모델을 쓰지 않았다.

- 내린 open-jaw 자세: 카메라가 띠와 양쪽 빔 윗면을 본다. 빔 색 점은 14k–28k개다. 하지만 lime 점은 60개(MIN_POINTS) 미만이다. 더 어두운 가까운 끝 **면**이 화면에 들어올 때(ex ≤ −4 mm)만 예외다. 그래서 ex ≥ 0이면 부분 관측 증거가 없어 `BEAM_UNCERTAIN` → `PREGRASP_NOT_READY`가 된다.
- ex −12 mm standoff 관측: 띠 너머 lime 점은 strip마다 몇 개뿐이다. 반면 끝 면 strip에는 약 1.4k개가 있다. 두 half-fit이 0.068 rad(> 3°) 어긋났다.
- 마지막 하강 자세의 첫 프레임은 팔이 아직 명령 PWM을 따라가는 중이었다. `grip_view_m2` 어두운 비율 0.393(corner−+− r1, 기준 0.40)이었고, 이후 프레임은 0.50–0.60이었다.

### 수정 (`harness/zone_pair_grasp_entry_v6c.py`, 플래그 `grasp_range_entry`)

게이트와 임계값은 모두 그대로 둔다(3°, 50 mm, ≥ 4 strip / ≥ 60 mm, 95 % footprint 지지, MIN_POINTS, 추적 σ·나이·segment). 증거만 바꿨다.

1. standoff edge pair와 pre-close 부분 관측에 파지 거리 빔 색 모델을 쓴다. 수직이고 더 어두운 끝 면(윗면에 잘못 투영되는 면)은 V < 120으로 빠진다.
2. 띠/끝 경계에 잘린 10 mm strip은 일부만 덮인다. 그 중점은 두 edge의 중점이 아니다. 그래서 median strip 지지의 1/4 미만인 strip을 line fit 전에 뺀다(`MIN_STRIP_SUPPORT = .25`).
3. 마지막 하강 자세는 첫 READY 프레임 전에 `FINAL_DESCENT_SETTLE_S = .3` s 정착한다. 다른 모든 자기 관측의 'settled' 규칙과 같은 값이다.

정렬을 좁히지 않고 파지 입장을 넓힌 이유는 funnel 순차 합성 원리다(Burridge, Rizzi & Koditschek 1999). 앞 funnel의 목표 집합은 다음 funnel의 영역 안에 있어야 한다. MoveIt Task Constructor pick 파이프라인도 같은 구조다. approach 단계는 거리 범위(`setMinMaxDistance(0.1, 0.15)`)를 받고, 다음 단계는 앞 단계가 남길 수 있는 범위 전체에서 시작해야 한다.

### 오프라인 재생 결과 (#260 경계 raw, v5h 23건 × 2 로봇)

| 증거 | standoff 프레임 실패 | 앵커 없음(로봇) | 파지 자세 부분 관측 실패 |
|---|---:|---:|---:|
| v1 lime (v5h/b-only) | 9 / 138 | 3 / 46 | 22 / 155 |
| v6c 빔 색 + strip 지지 필터 | 0 / 138 | 0 / 46 | 0 / 155 |

- 파지 자세 프레임은 실제로 하강한 로봇의 마지막 하강 자세 첫 4장이다.
- 오프라인 재생은 물리 통과가 아니다. 물리 결과는 아래 격자에서 따로 본다.
- 전체 출력: [replay_boundary_entry.txt](replay_boundary_entry.txt).

## 문제 3 (선택): a+b r2 단안 빔 상대 인식 실패 — 진단만

#260 Run A에서 a+b 정렬 23/25가 `BEAM_RELATIVE_UNCERTAIN`으로 끝났다.

**원인:** r2의 첫 프레임에서 상대 로봇 r1의 노란 부품이 빔 먼 끝 바로 너머에 보인다. 이 부품이 `beam_colour_mask`에 들어간다.

- `zone_pair_relative.component_points`는 '큰' 성분(≥ 60점)이 1개 이하이면 모든 점을 유지한다. 그래서 작은 상대 로봇 덩어리가 남는다.
- 그 결과 PCA 길이가 1.54 m(lo 0.389, hi 1.926)가 되어 `SHAPE_AMBIGUOUS`/`MONOCULAR_DEPTH_AMBIGUOUS`로 끝났다.
- r1 시점에서는 길이 0.667 m로 정상이었다.

**고치지 않은 이유:** 후보 수정은 작은 성분에도 `associate_component`의 결합 길이(> .66 m) 규칙을 적용하는 것이다. 하지만 이것은 싸지 않다.

- 새 플래그와 정책 `a+b-v6c`가 필요하다.
- 같은 규칙은 빔 자체의 작은 조각에도 `ADJACENT_OCCLUDER_CANDIDATE`를 낼 수 있어 회귀 위험이 있다.
- 별도 물리 격자가 필요하다.

그래서 이번 범위에서는 진단만 기록한다.

## 물리 격자 (단계 probe)

(실행 후 기입: 명령, 소스 SHA, 잠금, 부하 평균, 단계별 통과표, 실패 원인, raw 경로·해시)

## 참고 자료

- robot_localization, `FilterBase::processMeasurement` (측정 시각으로 predict한 뒤 상태 시각 = 측정 시각). https://github.com/cra-ros-pkg/robot_localization/blob/ros2/src/filter_base.cpp
- R. R. Burridge, A. A. Rizzi, D. E. Koditschek, "Sequential Composition of Dynamically Dexterous Robot Behaviors," IJRR 18(6):534–555, 1999. doi:10.1177/02783649922066385 (앞 funnel 목표 ⊆ 다음 funnel 영역)
- MoveIt Task Constructor, Pick and Place tutorial (approach `setMinMaxDistance`, `GenerateGraspPose::setAngleDelta`). https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html
- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005 (#260에서 인용한 Bayes 필터 predict/update 구조).
- 저장소 내부: `harness/owncam_pair_beam_v2.py` (dev 613 파지 거리 빔 색 모델), `experiments/2026-09-28-pair-stage-probes/README.md` (#260 기준선).
