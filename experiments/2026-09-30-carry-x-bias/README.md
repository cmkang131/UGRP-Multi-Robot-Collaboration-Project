# 운반 진행 방향(x) 오차 편향 분석 (carry-x-bias)

- 날짜: 2026-09-30. 성격: **오프라인 분석**. 새 물리 실행 없음, `agent_lock` 안 씀.
- 브랜치: `claude/carry-x-bias`, 기준: main `b10035db`. Refs #216. 분석 대상: PR #283(`claude/door-relax-envelope`)의 연쇄 검증과 그 이전 stage-probe 원자료.
- 등록된 실행 소스(봉인)는 **하나도 고치지 않았다**. 고칠 곳은 "제안 패치"에만 적었다.
- 이 실험은 새 실행 번들 ID를 예약하지 않았다. 제안 패치를 적용하는 사람이 그 시점에 `git grep`으로 다음 번호를 확인한다.

## 쉬운 요약

1. **원인은 하나다.** 짐을 든 채 앞으로 갈 때, 입자필터(PF, 로봇 위치 추정기)가 등록된 진행 방향 이득(gain) 1.4004를 믿고 실제보다 **약 5.3% 더 멀리 갔다고** 계산한다. 실제 로봇은 이득이 약 1.328(= 1.4004 x 0.948)인 것처럼 움직인다. 두 로봇 모두 같은 방향(추정이 앞서감)이고 크기도 거의 같다(실제/추정 = 0.948~0.950, 창마다 편차 +-0.001).
2. 그래서 추정 x 오차는 주행 구간에서만 쌓인다. L0 주행 약 +33 mm, L1 주행 약 +47 mm(로봇 둘 다). 조향·정지·코스팅 구간은 몇 mm 이내다. 전체가 "이동 거리에 비례"하는 오차라서 x의 시그마(불확실도)가 못 따라간다.
3. **r1과 r2의 z 점수 차이는 움직임 차이가 아니라 재파지 때 본 태그 한 번의 정보량 차이**다. r1은 태그 판독이 x를 약 -23 mm 끌어당기고 x 시그마를 24.7 mm에서 16.4 mm로 줄인다. r2의 판독은 x 정보가 거의 없다(시그마 27.9 mm에서 28.2 mm, x 이동 -0.3 mm). 그래서 L0에서 쌓인 오차가 r1에서는 재파지에서 일부 지워지고, r2에서는 그대로 L1로 넘어가 두 배로 쌓인다(L1 끝 평균 x 오차 r1 +50 mm, r2 +83 mm).
4. **고칠 것은 이득 하나(x 0.9483배)다.** 오프라인으로 같은 명령을 다시 통과시켜 보면 L1 끝 x 오차 평균이 +67 mm에서 -5 mm로, x +-2 시그마 포함률이 50%에서 100%(윌슨 신뢰구간 91~100%)로, z^2(정직하면 1)가 4.4에서 0.11로 내려간다. 시그마는 그대로라서 게이트(xy 0.07 m)에 걸리는 경우는 0/40이다.
5. **NEES(3자유도 일관성 통계)가 [2.29, 3.81] 대역에 들어가게는 못 만든다.** x만 고치면 NEES는 0.27로 대역 아래(즉 과신이 아니라 **보수적**)다. 연쇄에서 y와 yaw의 시그마가 원래 너무 넉넉하기 때문(z^2 0.03, 0.07)이다. x 시그마를 줄이면(V1_s0.5) NEES는 0.38로 조금 오르지만 대역에는 못 미치고, 이를 위해 시그마를 줄이는 것은 권하지 않는다.
6. **시그마만 키워서 정직하게 만드는 방법은 게이트 여유를 먹는다.** 편향은 그대로 두고 x 소음을 1.5배 키우면 포함률 100%(재파지 유지 기준 95%)가 되지만 오차는 +67 mm 그대로이고 피크 시그마가 59.6 mm로 게이트 70 mm에 10 mm 안쪽까지 온다. 2배부터는 게이트가 40개 중 20개에서 걸리고 3배면 40/40이다. 따라서 편향 보정이 먼저다.
7. 추천은 **A안(평균만 보정)**이다. 물리 재확인 없이 적용하면 안 된다(아래 "제안 패치"의 수용 기준).

## 자료와 방법

- 분석에 쓴 raw는 모두 `/Users/changmin/projects/ugrp/outputs/` 아래 기존 실행이다. 사본을 만들지 않았고 `results/raw_inputs.json`에 각 `cases.jsonl`의 sha256을 적었다.
  - 연쇄: `door-relax-envelope-77fde5f6-chK1gP2`(seed 911, 912 각 10건), `door-relax-envelope-fdd35cee-chK1gP1/chK1g/chK0g/chBase`.
  - 단일 구간: `pair-stage-probes-3f6ca985-ghR2`(+`ghR2L7`), `pair-stage-probes-495c1173-ghR`, `pair-stage-probes-f0716773-ghB/ghC/ghD`, `door-relax-envelope-fdd35cee-envK1gL0/L1`, `pair-stage-probes-ece01311-fcal`, `pair-stage-probes-7cecaf9b-fcal2`. 합쳐 25개 raw.
- 정답(GT, 시뮬레이터 좌표)은 **오프라인 채점에만** 썼다. 보정 후보는 제어기가 실제로 아는 양(자기 명령 이력, 단계, 정적 지도)만으로 만들어진다: 이득 계수 하나(kappa)다.
- 시간 정렬: PF 행은 `trace` 시각보다 최대 약 0.15 s 늦다. 채점은 PF 행 자신의 시각에서의 GT와 비교한다(이걸 어기면 약 10 mm 가짜 오차가 생긴다).
- 비교 기준 통계: NEES는 n=40일 때 3자유도 카이제곱 95% 대역 [2.29, 3.81], x +-2 시그마 포함률은 윌슨 구간을 함께 적는다. 게이트는 `GATE_LOADED`(xy 0.07 m, yaw 3도; k1g 변형은 5도/4도).

## 1. 오차가 쌓이는 위치 (단계별)

`analysis/phase_budget.py`, 결과 `results/phase_budget.txt`. 연쇄 20건 x 로봇 1대씩의 평균(mm). "e_x"는 PF 평균 - GT의 세계 x 성분.

| 단계 | 로봇 | GT 이동 | PF 이동 | e_x 변화 |
|---|---|---|---|---|
| L0 조향(steer) | r1 / r2 | -0.7 / +1.0 | -0.3 / -0.3 | +0.3 / -1.3 |
| L0 주행(drive) | r1 / r2 | +588.9 / +588.3 | +621.5 / +621.4 | **+32.7 / +33.1** |
| L0 코스팅 | r1 / r2 | -1.6 / +9.1 | +4.0 / +4.0 | +5.6 / -5.1 |
| 재파지(내림~올림, 태그 1회) | r1 / r2 | +11.0 / -10.8 | -22.6 / -0.3 | **-33.6 / +10.5** |
| L1 조향 | r1 / r2 | -2.2 / +2.2 | -0.2 / -0.7 | +2.0 / -2.9 |
| L1 주행 | r1 / r2 | +893.1 / +893.4 | +940.5 / +939.9 | **+47.4 / +46.5** |
| L1 코스팅 | r1 / r2 | +3.7 / +3.7 | +2.4 / +2.4 | -1.3 / -1.3 |

- 부호: 모든 20건에서 e_x > 0(추정이 앞섬). L0/L1 주행 오차 비율 32.7/589 = 5.6%, 47.4/893 = 5.3%로 거리 비례다.
- 재파지 구간에서 GT가 로봇마다 반대로 약 11 mm 되밀린다(r1 +11.0, r2 -10.8). 역할 의존이며 이 분석에서는 모델링하지 않았다.
- **r1/r2 차이** (`analysis/fix_information.py`, `results/fix_information.json`): 태그 판독 한 번이 PF에 주는 정보가 다르다. 주의: 판독은 PF 행 두 개(재파지 시각과 약 0.2 s 뒤)에 나뉘어 반영되므로 "판독 직전 행"과 "판독 뒤 행"을 재파지 시각 -0.2 s / +0.15 s로 잡았다.

| | x 시그마 전 -> 후 | x 평균 이동 | 판독의 x 전달 계수 A_xx |
|---|---|---|---|
| r1 | 24.7 -> 16.4 mm | -22.6 mm | 0.44 |
| r2 | 27.9 -> 28.2 mm | -0.3 mm | 1.02 |

  (A_xx = 판독 뒤 공분산 x 사전 공분산의 역. 1이면 판독이 x를 전혀 못 바꾼다.) r1은 판독으로 x가 눌리고, r2는 x가 그대로라 오차가 계속 쌓인다. L1 끝 z(x) 평균은 r1 1.71~1.99, r2 2.21~2.50으로 검토에서 본 값과 일치한다.
- **보편성**: 25개 raw 전체에서 (로봇, 구간)별 kappa는 0.935~0.954(잘린 구간 일부 0.92), 횡이동(lateral) 구간 kappa는 약 0.98이다. 연쇄만의 문제가 아니고 등록된 이득이 진행 방향에서 약 5% 높다.

## 2. 보정 모델과 적합 (오프라인)

`analysis/build_windows.py`, `analysis/fit_forward_model.py`, 결과 `results/fit_forward_model.json`.

- 모델 M0: 등록된 것(이득 1.4004, 지연 시간상수 tau 0.8 s).
- M1: 진행 방향 이득만 x kappa(**kappa = 0.9483, 이득 1.3281**, tau 0.8 유지). M2: kappa 0.9607 + tau 1.0 s(이득 1.3454; 궤적 모양까지 맞추는 선택지). M3: 로봇별 kappa(r1 0.9441, r2 0.9526). M4: 로봇 x 구간(L0/이후)별 kappa.
- **적합 집합**: 연쇄 seed 911(L0, L1 각 10건)과 hR2 구간 0(10건), 축 방향 창 60개. **보류 집합**: 나머지 전부(seed 912, envelope, hB/hC/hD/hR, cal 등) 축 방향 창 694개. 주의: 같은 물리를 반복한 실행이 많아(시뮬레이터가 결정적) 창들은 독립이 아니다. 독립 표본 수는 훨씬 작다.
- 보류 집합 구간 끝 x 오차(창 694개, mm):

| 모델 | 편향 | RMS | 최대 | 궤적 RMS |
|---|---|---|---|---|
| M0 등록 | -39.3 | 39.9 | | 22.9 |
| M1 | -0.6 | 4.3 | 18.6 | 4.8 |
| M2 | +0.4 | 3.8 | 15.3 | 2.1 |
| M3 / M4 | | 3.7 | | 4.6~5.0 |

- M3/M4(로봇별·구간별)는 보류 집합에서 이득이 없다. 그래서 **로봇별·단계별 이득은 필요 없고 하나의 kappa면 된다.** 로봇 하나를 빼고 적합하는 검증(LOCO)의 M1 끝 RMS는 4.5 mm(최대 7.3 mm)다.
- M2는 궤적 RMS를 절반 이하로 줄이지만 끝점은 같다. tau는 `motion_loaded` 전체가 공유하고 `leg_duration()`도 읽으므로 횡·회전 응답을 확인하지 못했다. M1을 권한다.

## 3. PF 다시 돌리기: 재생 검증과 반사실

- **재생 검증** (`analysis/validate_replay.py`, `results/replay_validation.json`): 기록된 명령을 등록 모델로 PF(입자 2000개)에 다시 넣으면 기록된 PF와 x 평균 차가 L0 0.26 mm, L1 0.40 mm(최대 2.2 mm), 시그마 비율 0.97~1.02로 재현된다. y/yaw는 빔 가장자리 yaw 갱신·쌍 평균 결합을 재생하지 않아 그대로 재현하지 못한다. 그래서 반사실은 **"기록된 상태 + (변형 재생 - 등록 재생)"**(같은 난수 사용)으로 계산한다.
- **재파지 판독의 전달**: 판독은 선형 가우시안 규칙(`mq' = mq + A(mp' - mp)`, `A = Sq Sp^-1`)으로 옮긴다(`fuse`). 판독이 다시 위치를 맞춘다고 보는 상한이 `replace`(기록된 판독 뒤 상태를 그대로 사용; r1에는 상한이지만 r2에는 비현실적)이다. 두 값을 괄호로 함께 적는다.
- 명령은 기록된 그대로 고정이다. 실제로 이득이 바뀌면 조향 피드백이 명령을 바꿀 수 있으므로 물리 재확인이 필요하다(한계 참조).

### 3.1 연쇄 L1 끝, n=40(seed 911+912; 물리가 같아 독립 표본 아님)

`analysis/run_counterfactual.py`, `aggregate_counterfactual.py`, `tradeoff_table.py`; 결과 `results/tradeoff_table.txt`. NEES 대역 [2.29, 3.81].

| 변형 | NEES | z^2 x/y/yaw (정직=1) | x 포함률 (윌슨) | e_x 평균 / 절대평균 mm | 시그마 x / xy mm | 피크 시그마 xy mm | 게이트 걸림 |
|---|---|---|---|---|---|---|---|
| V0 등록 | 4.64 | 4.42/0.04/0.12 | 50% (35-65) | +67.3 / 67.3 | 31.8 / 53.2 | 52.1 | 0/40 |
| **V1 이득 x0.9483** | **0.27** | 0.11/0.03/0.07 | **100% (91-100)** | -4.6 / 8.5 | 31.6 / 51.9 | 50.8 | 0/40 |
| V2 이득 x0.9607 + tau 1.0 | 0.26 | 0.10/0.03/0.07 | 100% (91-100) | -5.2 / 8.0 | 31.6 / 52.0 | 50.9 | 0/40 |
| V1_s0.5 (보정 + x 소음 0.5배) | 0.38 | 0.22/0.03/0.07 | 100% | -4.4 / 8.6 | 23.2 / 46.8 | 45.6 | 0/40 |
| V0_s1.5 (보정 없이 x 소음 1.5배) | 2.66 | 2.47/0.04/0.12 | 100% (91-100) | +67.2 / 67.2 | 42.5 / 60.6 | 59.6 | 0/40 |
| V0_s2.0 | 1.71 | 1.52/0.04/0.12 | 100% | +67.0 / 67.0 | 54.0 / 69.5 | 68.7 | **20/40** |
| V0_s3.0 | 0.90 | 0.73/0.04/0.11 | 100% | +66.8 / 66.8 | 77.9 / 90.0 | 89.4 | **40/40** |
| V0_w0.03 (x 백색소음 +0.03 m/s) | 1.94 | 1.75/0.04/0.12 | 100% | +67.2 / 67.2 | 50.5 / 66.7 | 65.9 | **20/40** |
| V0_w0.05 | 1.03 | 0.85/0.04/0.11 | 100% | +67.1 / 67.1 | 72.6 / 85.4 | 84.7 | **40/40** |

(`replace` 기준: V0 NEES 4.64, V1 NEES 0.64 / e_x +18.8 mm / z^2x 0.48 / 포함률 100% / 게이트 0/40; V0_s1.5는 NEES 3.02, 포함률 95%(83-99), 게이트 0/40, 피크 57.4 mm; V0_w0.03은 NEES 2.35, 100%, 0/40.)

로봇별(`fuse`, L1 끝): V0는 r1 e_x +51.1 mm(z^2x 3.46, 포함률 100%), r2 +83.6 mm(z^2x 5.39, 포함률 0%). V1은 r1 -11.7 mm, r2 +2.5 mm(z^2x 0.19 / 0.03). `replace`의 V1은 r1 +2.6 mm, r2 +35.0 mm다. r1의 -11.7 mm(fuse)는 판독 전달 근사에서 온 값이므로 r1 잔차의 부호는 신뢰하지 않는다.

L0 끝(`fuse`/`replace` 공통, 시작 오차가 재파지 이전이라 판독 무관): V0 e_x r1 +31.0, r2 +35.8 mm, V1은 -0.8, +4.1 mm.

### 3.2 단일 구간 보류 집합 (n=328 로봇-구간, `leg:ALL_HOLDOUT`)

| 변형 | NEES [2.74, 3.27] | z^2 x/y/yaw | x 포함률 | e_x 평균 mm | 게이트 걸림 |
|---|---|---|---|---|---|
| V0 | 4.11 | 2.04/1.12/1.05 | 98% | +37.8 | 0/328 |
| V1 | 2.21 | 0.15/1.18/1.05 | 100% | -3.1 | 0/328 |
| V0_s3.0 | 2.42 | 0.40/1.11/1.05 | 100% | +38.1 | 212/328 |

단일 구간에서 y와 yaw는 정직(z^2 약 1.1)하고 x만 편향이라 보정 뒤 NEES가 대역보다 낮아지는 것은 x 시그마가 남는 오차보다 넉넉해서다. hB/hC/cal 집합의 평균 e_x -18 mm는 편향이 아니라 시작 자세의 E2E 사전 오프셋(-11~-18 mm)에서 온다.

### 3.3 3자유도 NEES를 대역에 넣을 수 있는가

**넣을 수 없다.** 이유: (i) 정직해야 하는 것은 x 하나인데 연쇄의 y, yaw z^2는 0.03, 0.07(매우 보수적)이라서 x를 정확히 z^2 = 1로 맞춰도 3자유도 평균은 약 0.4다. (ii) x를 더 정직하게 만들려고 x 시그마를 줄이면(V1_s0.25 NEES 0.45) 대역에는 여전히 못 미치고 시뮬레이터 플랜트의 재현 정밀도(약 4 mm) 바깥의 보증을 하게 된다. 따라서 수용 기준은 3자유도 NEES 대역이 아니라 **축별**로 잡는 것을 제안한다: x 포함률 >= 90%, x의 z^2가 1 안팎(과신 방향 상한 1.3), y/yaw z^2는 별도 보고, "NEES가 대역 상한 3.81 이하"인 한쪽 기준.

### 3.4 선택지 정리

| 안 | 내용 | 결과(n=40 연쇄, fuse) | 판단 |
|---|---|---|---|
| A | 평균만 보정(이득 x0.9483) | e_x -4.6 mm, 포함률 100%, 게이트 0/40, 피크 50.8 mm | **추천** |
| B | A + 보정 후 x 소음 축소(0.5배) | z^2x 0.22, 피크 45.6 mm | 권하지 않음: 독립 보정 표본이 필요 |
| C | 보정 없이 시그마만 확대 | 1.5배: 포함률 100%(95%), 오차 +67 mm 그대로, 피크 59.6 mm; 2배부터 게이트 20/40 | 권하지 않음 |

## 4. 제안 패치 (미적용; 봉인된 소스는 그대로)

`proposed_carry_fwd_gain_fit.json`에 kappa, 이득, 출처를 적어 두었다(`PROPOSED, NOT APPLIED`, 어떤 하네스 파일도 읽지 않는다).

1. `harness/owncam_carry_v6e.py`: 적합 파일을 가리키는 상수 `FWD_GAIN_FIT`를 두고 `enable_provider(general=True)`에서 `profile['drift_ratio_std']`를 정한 다음(현재 124행 근처), 지금 `pf.params['motion_loaded']['gain']`(3x3)을 복사해 `[0][0] *= kappa`한 `profile['gain']`을 만들어 함께 병합한다(params를 다시 묶는 방식이라 다른 제공자에 영향 없음). 적합 파일의 sha256과 kappa를 `info`에 남긴다.
2. `harness/zone_pair_v6_policy.py`: `PairPolicy`에 새 플래그 `carry_fwd_gain`(기본 `False`)과 이를 켠 정책 변형을 추가한다.
3. `harness/zone_pair_executor.py`(467~477행 근처): 새 플래그를 `enable_provider`로 전달하고, `carry_dr_general` 없이 쓰면 오류를 내게 한다.
4. 새 실행 번들 ID(현재 `zone-pair-v81-carry-dr-general`, v6e README가 v82/워크플로 2.15.0/v6f를 예약해 뒀다): 적용 시점에 main과 열린 PR 브랜치에서 `git grep`으로 최댓값을 확인하고 다음 번호를 쓴다. `REVISION_POLICIES`, `configs/simulation_workflows.json`, `configs/zone_study_integration/llm_driver.json`, 재봉인(`scripts/zone_pair_v6_contract.py`), 은퇴 목록 갱신이 함께 필요하다.
5. **건드리지 않는 것**: `calibration_loop_v2.json`(공유·봉인, sha 04f56834), `leg_duration`. 다만 `leg_duration`도 같은 이득 1.4004에서 구간 시간을 계산하므로 계획 시간이 실제 이동에 비해 짧을 수 있다(이 분석에서는 계획 거리 대비 실제 도달 거리를 따로 비교하지 않았다). 바꿀지는 별도 확인·결정이 필요하다.
6. **사전 등록에 넣을 수용 기준(제안)**: `--pf-track` 켠 교정 코호트로 L0 -> 재파지 -> L1 연쇄를 실제로 돌려, kappa(구간별)가 [0.94, 0.96], |평균 e_x| <= 15 mm(L1 끝), x 포함률 >= 90%(독립 n >= 40), 게이트 0회, 축별 z^2 보고. 실제 파지 성공률과 통과 성공은 별도로 본다.

## 5. 한계

- 반사실은 **기록된 명령을 고정**한다. 이득이 바뀌면 조향 피드백이 명령을 바꿀 수 있어 실제 재실행이 필요하다.
- hR2 표본은 2개 배치 유형의 10건뿐이고 seed/변형은 모두 같은 결정적 물리의 반복이다. 표본 수는 모두 부풀려 있다.
- 재파지 판독 전달은 근사다(`fuse`와 `replace`로 상하한을 잡았다). r1 잔차의 부호는 근사에 민감하다.
- 재파지 구간의 GT 되밀림(약 +-11 mm, 역할 의존)은 모델에 없다.
- r1의 L0 kappa(0.935~0.945)가 r2(0.947~0.954)보다 약간 낮다. 하나의 kappa로 이 차이를 덮는다(잔차는 수 mm).
- 횡·회전 구간, 다른 짐 무게·지면은 검증하지 않았다. 지형/하중 성능은 실제 검증 전에는 확정이 아니다.
- b-v6e 교정 코호트는 다른 프로파일이라 결과를 합산하지 않았다.
- 재생 검증의 y/yaw는 재현되지 않으므로 y/yaw 결론(보수적)은 기록된 값 기준이다.

## 6. 재현 방법

경로는 이 폴더 기준이다. Python은 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`, 파생 자료는 `/Users/changmin/projects/ugrp/outputs/carry-x-bias-20260930/`에 둔다(1 MiB 초과).

```
cd experiments/2026-09-30-carry-x-bias/analysis
python hash_inputs.py                      # ../results/raw_inputs.json
python build_windows.py                    # outputs/.../windows.pkl
python fit_forward_model.py                # ../results/fit_forward_model.json
python phase_budget.py                     # ../results/phase_budget.{json,txt}
python fix_information.py                  # ../results/fix_information.json
python validate_replay.py                  # ../results/replay_validation.json
python run_counterfactual.py <출력폴더>     # records.jsonl (3 프로세스, 수 분)
python aggregate_counterfactual.py <records.jsonl> ../results/counterfactual_summary.json /dev/null
python tradeoff_table.py <records.jsonl> ../results/tradeoff_table.json ../results/tradeoff_table.txt
```

- 파생 자료 sha256: `records_all.jsonl` a39e4d9078599315b6fa1d773cf009be9b1548058bcdc19a9b6ef8b830069003(2280 연쇄 + 6612 구간 레코드), `windows.pkl` 8ddbcf661fe2ad2336e205872543fc97f09058da75237cf5ccc748dabf7e6a5d.
- 이 폴더에는 raw나 1 MiB 넘는 파일이 없다(합계 약 0.7 MiB).

## 7. 참고 자료

- J. Borenstein, L. Feng, "Measurement and correction of systematic odometry errors in mobile robots," IEEE Trans. Robotics and Automation 12(6):869-880, 1996 (UMBmark). 체계적 오차는 보정 계수로 교정한다는 방법을 그대로 적용해 진행 방향 이득 하나를 교정했다. 원문 사본: https://johnloomis.org/ece445/topics/odometry/borenstein/paper58.pdf
- 스키드 스티어 운동학의 곱셈형 종방향 미끄러짐 계수: https://arxiv.org/pdf/2402.18065, https://pmc.ncbi.nlm.nih.gov/articles/PMC4481911/ (진행 방향 이득을 하나의 미끄러짐 계수로 보는 근거).
- 이전 v6e README에서 인용한 S. Thrun, W. Burgard, D. Fox, "Probabilistic Robotics," 2005(입자필터·운동 모델); O. Woodman, "An introduction to inertial navigation," 2007(추측항법 오차 누적). 이 PR에서 원문을 다시 열지는 않았다.
- Y. Bar-Shalom, X. R. Li, T. Kirubarajan, "Estimation with Applications to Tracking and Navigation," 2001(NEES 일관성 검정, 카이제곱 대역).
- 저장소 안: PR #283 README(`experiments/2026-09-30-door-relax-envelope/README.md`)와 `analysis/chain_analysis.py`(NEES/포함률 계산 방식), `harness/owncam_localizer.py::predict_to`(운동 모델), `harness/owncam_carry_v6e.py`(프로파일 병합).
