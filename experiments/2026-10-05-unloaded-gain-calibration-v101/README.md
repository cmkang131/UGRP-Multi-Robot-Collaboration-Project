# 무하중 이득·시간상수 보정 v101 — 수집·적합·재생 결과 (2026-10-05)

Refs #363. 조정자 결정(2026-10-05): 잡음으로 계통 오차를 덮지 않고, 고전 방식(Borenstein & Feng 1996: 계통 오차를 측정해 모델에서 고친다)을
따른다. 이 폴더는 그 결정의 이행 기록이다. 설계와 판정 규칙은 [PREREGISTRATION.md](PREREGISTRATION.md)(수집 전 커밋 341ce3b9)와
[ADDENDUM_selection_rule.md](ADDENDUM_selection_rule.md)(재생 결과 보기 전 커밋 169f5578)에 고정돼 있다.

**성격: DEV_PILOT(개발 보정)이다.** `MEASURED_SIM`이 아니고 확증 표본이 아니다. 무하중 r1의 SIM 바퀴 평면만 쟀다(적재·지형·다른 로봇·실물은 아니다).
정답(SIM 변위)은 오프라인 보정 산출에만 썼고 제어의 실시간 입력에는 들어가지 않는다. 명령은 모두 미리 쓴 표다.

## 1. 한눈에 보는 결과

| 항목 | 값 |
|---|---|
| 수집 | 실행 6개 모두 `COLLECTED_UNQUALIFIED`(적합용 2, 보류 4), 인터록 중단 0, 재실행 0 |
| 채택 형태 | `linear_diag`(대각 이득 + 축별 지연 + 공통 정지 지연). 데드밴드·전체 이득 형태는 사전 등록 규칙(§4)에 못 미쳐 채택 안 됨 |
| 보류 평가 | **VALIDATED_DEV**(수락 규칙 4개 모두 통과, 아래 §3) |
| 이득(전진·좌우·회전) | 1.563 / 1.101 / 1.370 (DEV 기본 채움 1.15 / 0.94 / 1.40) |
| 시간상수(축별 지연) | 1.013 / 1.013 / 0.170 s (DEV 기본 0.12 s), 정지 지연 0.0705 s (DEV 0.12 s) |
| 보정 산출물 C | `aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4` (측정 이득·지연 + 등록 r4/r5 측정 잡음, 주 산출물) |
| 보정 산출물 C2 | `8afc61252934fd69e3a56a074d73d6f23dac0dad31a407987170a7c01b976aa8` (이 보정에서 잰 잔차 잡음). 잡음 포함 비율 0.788 < 0.90이라 선택 후보에서 제외, 참고만 |
| 재생 선택(사전 등록 규칙) | **C 선택**: 점수 S = C 2.88 < B 5.25 (HEAD 그대로 16.9) |
| 중앙 위치 오차(30–60 s, r1 / r2) | C 3 / 21 mm, B 51 / 20 mm, HEAD 그대로 215 / 196 mm |
| NEES 중앙값 포함(99.9 % 한계 13.8, 5시드) | C는 모든 창·두 로봇에서 5/5 시드 안, B는 r1 30–50 s 창에서 0/5, HEAD 그대로는 전부 0/5 |

**회복(R1·R2)과 통합 diff(조정자 결정: 둘 다 채택 방향).** 통합 diff = C 위에 R1(믿음 둘레 국소 증강 MCL) → R2(도착 거절 경로에서만 믿음 확장, 호출 위치는
`ViewConfirmedArrival._arrive`의 거절 분기)를 차례로 얹은 것이다. **기준 커밋은 #363 최신 HEAD `11f6d7c3`**(재고정 v6 통합 이후)이고 깨끗한 트리와 깨끗한 `git archive` 사본에 순서대로 적용됨을 확인했다
([diffs/](diffs/), §7). 이 보정(C) 아래 기록된 두 사례에서는 필터가 길을 잃지 않아 R1은 한 번도 발동하지 않았고(오탐 0), R2는 실제 도착 거절에서
오차를 일시적으로 키우되(약 +20 mm) σ와 NEES를 정직하게 만든다. 즉 회복은 "필요함이 입증"된 것이 아니라 **보험이고 비용이 측정됐다**(§7).

## 2. 수집 (표준 관리 경로, SIM 시간)

- 번들·작업 흐름: `zone-final-environment-gaincal-v101` 1.0.0, 점검 `calibration-gain-v101`(번호 예약: 2026-10-05 main·열린 PR 헤드 최댓값 v100 다음).
  `scripts/sim_cli workflow run`을 `ugrp_session.py run`으로 실행했고, `collect.sh`가 `agent_sim_slots`로 비타이밍 SIM 슬롯을 잡았다(동시 최대 2).
- 소스 SHA `341ce3b9aeda6aca38fac57c6d5030b9c458760d`(깨끗한 커밋, 실행 중 고정, 모든 실행 `source_unchanged: true`).
  스모크 실행 하나(heldP2)는 같은 SHA·같은 코드로 먼저 돌렸고 별도 출력 이름이다. 정식 5개는 한 조정자 PID 66460 아래 같은 출력 루트에 있다.
- 원본(기본 체크아웃 `outputs/`, 커밋하지 않음 — pose 1.1 MB·명령 120 KB급 파일):
  `/Users/changmin/projects/ugrp/outputs/calib-gain-v101-341ce3b9-20261005T0350Z/`(정식 5개), `.../calib-gain-v101-341ce3b9-20261005T0340Z/`(스모크 heldP2),
  `.../calib-gain-v101-raw-all-20261005/`(둘을 한 폴더로 묶은 심볼릭 링크 트리, 적합기 입력). 파일별 sha256은 [runs/](runs/)의 `artifacts.sha256.json`.
- 디스크: 시작 전 여유 공간 ≥ 10 GiB를 실행기가 확인(수집 시점 여유 약 101 GiB).

| run | 역할 | 시드 | 시작 (x, y, yaw) | SIM 길이 | 시작 부하(1분) | 끝 부하(1분) |
|---|---|---|---|---|---|---|
| fitA1 | fit | 1101 | (3.775, −2.3, +90°) | 111.5 s | 18.3 | 20.8 |
| fitA2 | fit | 1102 | (3.8, 0.6, −90°) | 111.5 s | 18.3 | 20.8 |
| heldA3 | heldout | 1103 | (3.6, −2.3, +90°) | 84.0 s | 18.5 | 46.9 |
| heldM1 | heldout | 1104 | (3.95, 0.6, −90°) | 45.5 s | 18.5 | 32.9 |
| heldP1 | heldout | 1105 | (3.3, −2.3, +90°) | 16.1 s | 39.4 | 44.8 |
| heldP2 | heldout(스모크) | 1106 | (3.5, −2.3, +90°) | 16.1 s | 13.8 | 13.1 |

부하는 다른 작업과 겹쳐 높았다(최대 46.9). SIM 시간 결과이므로 속도·wall 시간 결론은 쓰지 않는다. 동시 보유자 전체는 [runs/](runs/)의 `run_result.json` `host_start/host_end`.
시드 1101–1106과 시작점은 v89·live probe(시드 911)와 겹치지 않는다(탐색/확증 분리).

## 3. 적합과 보류 평가

- 적합은 fitA1·fitA2만 읽는다(코드가 강제). 가중은 사용 에너지 분포(probe 명령의 축별 u² 비율) 기반이다.
  `fit.json` sha256 `8335c075ede24bbb31e6ae35227317e18e86d7f77729417e46241ccbf7a08567`([products/fit/](products/fit/)). 경계에 붙은 매개변수 0개.
- 모델 비의존 교차 확인(블록 끝 평균 속도의 사용 가중 기울기): 전진 1.473, 좌우 1.037, 회전 1.383. 궤적 적합의 유효 이득(1.563 / 1.101 / 1.370)보다
  전진·좌우가 낮다 — 저속에서 이득이 낮은 비선형(v89 실측과 같은 방향)을 단일 선형 이득으로 평균한 값이다. 그래서 이 값은 "접근 명령 분포로 가중한 유효 이득"이다.
- 반복 측정 퍼짐 5.8e-8(상대): 이 SIM 평면은 거의 결정적이다. `scale_std` = 0에 가깝고 `use_scale` = false, `rest_noise` = false(정지 1 s 변위 RMS 6.5 µm).
  따라서 **잡음은 이 수집에서 "물리 잡음"이 아니라 "선형 모델이 설명하지 못하는 잔차"만 잰다.** 그 값(C2)은 포함 비율 조건을 못 채웠다.
- 형태 선택(heldA3·heldM1 창 23개): 선택 RMS `linear_diag` 8.88 mm, `deadband_diag` 9.00 mm, `linear_full` 8.59 mm → 데드밴드는 10 % 개선 못 함, 전체 이득은 25 % 개선 못 함. `linear_diag` 유지.
- 수락 규칙(heldP1·heldP2 probe 명령 재생, heldA3·heldM1):

| 규칙 | 값 | 한계 | 결과 |
|---|---|---|---|
| (a) 끝 위치 오차/경로 길이(두 구간) | 0.035 / 0.024 | ≤ 0.06 | 통과 |
| (b) 구간 중 최대 위치 오차(두 구간) | 0.052 / 0.049 m | ≤ 0.12 m | 통과 |
| (c) 구간 RMS 대 DEV 채움 | 30.6 mm 대 207.4 mm (0.15배) | ≤ 0.5배 | 통과 |
| (d) 선택 창 끝 RMS 대 DEV 채움 / r4·r5 | 8.9 mm 대 19.8 / 41.0 mm (0.45 / 0.22배) | ≤ 0.6 / 0.8배 | 통과 |
| 잡음 포함 비율(C2 조건) | 0.788 (H1 0.842, H2 0.771, H4 0.668) | ≥ 0.90 | **미달 → C2 제외** |

  `heldout.json` sha256은 [products/heldout/](products/heldout/)의 `heldout.json.sha256`. 상태 `VALIDATED_DEV`.

## 4. 산출물 (기존 파일 덮어쓰기 없음)

- [products/C/](products/C/): `calibration_dev_pilot_unloaded_v101.json`(C) + 옆 `input_manifest_dev.json`. 기존 `calibration_dev_pilot.json`(`398372ae…`, 부모, 덮어쓰지 않음)을
  복사해 `params.motion` 10개 항목을 채우고 `missing: []`, `field_provenance`·`source_sha`·`dev_manifest_sha256`·`unloaded_gain_calibration`·`parent_calibration`만 갱신했다
  (`params.motion_loaded`와 카메라 모델 등 나머지는 바이트 그대로; #363 diff C의 시험이 이를 검사한다).
- [products/C2/](products/C2/): 같은 구조, 잡음만 이 보정에서 잰 값.
- [products/fit/](products/fit/), [products/heldout/](products/heldout/): 적합·평가 기록과 sha.

## 5. 사전 등록과 다른 점 (숨기지 않음)

1. **heldP2는 스모크 실행이 먼저였다.** 수집 코드 점검용으로 heldP2를 먼저 돌렸고 거기서 전진 이득 ≈ 1.49를 읽었다. 즉 "보류 자료를 보기 전" 원칙에서 heldP2는 예외다.
   적합기는 보류 run을 코드로 읽지 못하고(fit 단계는 fit 역할만 연다) 문턱은 수집 전 커밋 341ce3b9에 있었으므로 판정에 영향은 없지만 사실은 이렇다.
2. **C2 재생은 판정 전에 대기열에 넣었다.** 포함 비율 결과(0.788)가 나온 뒤에야 C2가 제외 대상임을 확인했고, 이미 대기열에 있어 같이 돌렸다. 선택에는 쓰지 않았다(보충 규칙 1항).
   참고로 C2의 S는 2.409(C 2.880)이고 C2 재생은 r1에서 NEES 중앙값이 3–4(한계 안)다.
3. **선택 규칙 (ii)/(iii) 해석 보충**을 재생 결과를 보기 전에 커밋했다([ADDENDUM](ADDENDUM_selection_rule.md)). 결정 경로는 "S 최소 = C" 한 줄로 끝났고 (i)–(iii)은 발동하지 않았다.
4. 적합기 입력은 두 출력 루트(스모크 + 정식)를 심볼릭 링크 트리로 묶었다(코드 변경 없음, 소스 SHA 고정 유지).
5. 재생은 사전 등록(§7)대로 5시드 × r1·r2 × 60 s이고 같은 도구에 `--cal-path/--cal-sha`만 추가했다(`analysis/replay_pf.py`).
   기준선 `base`는 이전 분석(1f7fb800 기준)이 아니라 #363 HEAD 94d083ba에서 새로 재생했다.

## 6. 재생 비교 (사전 등록 §7, #363 HEAD 94d083ba에서 실행 — 재생이 읽는 모듈은 최신 `11f6d7c3`과 바이트 동일, §7.1 — 같은 5시드)

원자료 요약은 [analysis/sel_summary.txt](analysis/sel_summary.txt). 셀 = 시드 사이 중앙값(시드별 창 중앙 NEES) [최소..최대] (한계 13.8 이내 시드 수).
점수 S = Σ_{r1,r2} Σ_{30–40, 40–50, 50–60 s} |log10(중앙 NEES / 1.386)|, 작을수록 좋다.

| 후보 | r1 30–40 | r1 40–50 | r1 50–60 | r2 30–40 | r2 40–50 | r2 50–60 | S | 중앙 오차 r1 / r2 (mm) | σx 평균 r1 / r2 (mm) |
|---|---|---|---|---|---|---|---|---|---|
| HEAD 그대로(참고) | 2865 | 2345 | 1834 | 391 | 354 | 341 | 16.91 | 215 / 196 | 4.2 / 10.4 |
| B(등록 잡음 overlay) | 99.8 | 26.9 | 12.3 | 5.6 | 2.8 | 2.4 | 5.25 | 51 / 20 | 9.4 / 7.1 |
| **C(측정 이득 + 등록 잡음)** | 0.20 | 0.31 | 0.52 | 2.88 | 2.80 | 3.09 | **2.88** | 3 / 21 | 4.9 / 3.4 |
| C2(참고, 선택 제외) | 3.69 | 3.20 | 2.72 | 3.54 | 3.75 | 4.28 | 2.41 | 6 / 19 | 3.2 / 2.8 |

- 해석: C는 이득 편향(과신의 원인, 이전 분석 §이득 편향)을 모델에서 직접 고쳐 오차를 두 자릿수로 줄였고, NEES를 중앙값 1.4 근처로 가져왔다.
  r1의 C는 NEES 0.2–0.5로 약간 **과소신뢰**(σ가 조금 큼)이고 r2는 약 3으로 약간 과신 쪽이나 둘 다 99.9 % 한계 안이다. B는 잡음으로만 덮은 경우여서 r1에서 아직 한계 밖이다.
- 한계: 같은 probe의 기록 입력을 PF에 다시 넣은 **열린 고리 재생**이다(명령은 옛 과신 PF가 만든 궤적). 보정 자료는 이 probe와 시드·시작점이 달라 튜닝 대상은 아니다.
  하지만 이 probe의 명령 분포로 사용 가중치를 만들었다는 점에서 완전히 독립은 아니다(§사후 선택은 PREREGISTRATION §11).

## 7. 회복(R1, R2) 적층

### 7.1 diff 구성 (모두 #363 `11f6d7c3` 기준, sha256은 [diffs/SHA256SUMS](diffs/SHA256SUMS))

| diff | 내용 | 줄 수 |
|---|---|---|
| [diff_C_measured_unloaded_calibration.patch](diffs/diff_C_measured_unloaded_calibration.patch) | 레지스트리 `dev_pilot.admitted_calibration_sha256`에 C 추가 + `admitted_source` 등록, 보정 C·fit·heldout 파일 추가, 시험 3개 갱신 | 3787 |
| [diff_R1_augmented_mcl_local.patch](diffs/diff_R1_augmented_mcl_local.patch) | `PF_RECOVERY`(Nav2 예시 α_slow 0.001 / α_fast 0.1, 국소 주입 (0.1, 0.1, 0.2)) 를 `make_robust_pf`에 전달 | 38 |
| [diff_R2_expansion_on_arrival_rejection.patch](diffs/diff_R2_expansion_on_arrival_rejection.patch) | 제공자의 일회용 `arm_expansion`/`begin_relocalization` 확장 + 도착 거절 분기에서 `request_belief_expansion` 호출 + 시험 + CI 목록 한 줄 | 345 |
| [diff_integrated_C_R1_R2.patch](diffs/diff_integrated_C_R1_R2.patch) | 위 셋을 합친 한 파일(순서대로 적용한 결과와 바이트 동일) | 4150 |

- 적용 순서: C → R1 → R2. 적용 검사: `11f6d7c3` 깨끗한 `git archive` 사본에서 세 diff를 순서대로 `git apply`한 결과가 통합 트리와 바이트 동일, #363 worktree(`11f6d7c3`, 깨끗함)에서 `git apply --check`로 diff C와 통합 diff 모두 통과(읽기 전용 검사, worktree는 건드리지 않음).
- **R2 호출 위치**: `harness/zone_pair_highpose_arrival_confirm.py` `ViewConfirmedArrival._arrive`의 "거절 + 재시도 남음" 분기, `self._relocalize(now)` 바로 앞.
  `request_belief_expansion(self._shared_pose)`이 (지연 래퍼의 `.provider`인) HIGH 제공자의 일회용 요청을 켜고, 같은 호출 흐름 안에서
  `DelayedPoseSource.begin_relocalization → HighPoseSource.begin_relocalization`이 요청을 소비해 확장한다. 소비되지 않아도 `finally`에서 끈다.
  DR 체크포인트·look-around 등 다른 재위치추정은 요청이 없으므로 믿음을 그대로 둔다. 공용·동결 모듈(`zone_study_pose_delay_p03`)은 바꾸지 않았다.
- 조용한 무동작을 막는 시험: 실제 v98 런타임의 두 로봇 드라이버 모두 `request_belief_expansion(_shared_pose)`가 True이고 제공자 `_expand_next`를 켠다(`test_real_v98_runtime_drivers_...`).
  실제 지연 래퍼 + 제공자 + 실제 거절 화면으로 거절 1회에서만 한 번 확장하고 확정 도착에서는 확장하지 않는 시험도 있다(`test_highpose_belief_expansion.py`).
- **`run_ci_tests.py` 목록 줄 겹침(재확인 완료)**: `11f6d7c3`가 추가한 refix 두 줄(`test_highpose_dr_checkpoint.py` 줄 뒤) 와 겹치지 않도록 새 시험 한 줄을 `test_highpose_receipt_nees.py` 줄 뒤에 넣었다. 위 적용 검사에서 충돌 없음.
- 기준 커밋이 `94d083ba → 496da4ea → 11f6d7c3`으로 바뀌었다. 재생 결과는 **94d083ba 기준 트리**에서 만들었지만, 재생이 불러오는 저장소 모듈 90개(제공자·계약·PF 일관성·도착 확인 등)의
  바이트가 `11f6d7c3` 기준 통합 트리와 모두 같음을 확인했다(차이 0개). 달라진 파일(`zone_pair_highpose_runtime.py`·`dr_checkpoint.py`·`refix.py`·시험)은 재생이 읽지 않는다. 그래서 재생을 다시 하지 않았다.

### 7.2 시험 (실제 #363 `11f6d7c3` 사본에서)

- 사본: `11f6d7c3`의 `git archive`(configs·harness·tests·scripts·sim) + 이 diff 적용(실험 폴더 일부 포함). 관련 시험 = `tests/test_highpose_*.py`, `test_zone_final_pair_highpose.py`, `test_own_image_gates.py`.
- diff C만 적용(`11f6d7c3` 사본): **503 passed, 1 skipped** (21분 38초, [analysis/tests_11f6d7c3_diffC.txt](analysis/tests_11f6d7c3_diffC.txt)).
- 통합 diff(C + R1 + R2) 적용: **510 passed, 1 skipped** (21분 44초, [analysis/tests_11f6d7c3_integrated_C_R1_R2.txt](analysis/tests_11f6d7c3_integrated_C_R1_R2.txt)). 늘어난 7개는 R2 시험이다.
- 건너뜀 1개는 `tests/test_highpose_edge_fit.py:141`("raw probe output not on this host", 작업 폴더 기준 원본 경로). 이 사본에는 원본이 없어서이고, #363 worktree에서는 돌 것이다.
- diff C가 고친 기존 시험: `test_zone_final_pair_highpose.py::test_v96_registry_retired_...`(v96·v98 `dev_pilot` 차이에 `admitted_calibration_sha256`·`admitted_source`를 허용하고 v96 목록이 앞부분임을 확인),
  `test_highpose_dev_pilot.py`(승인 목록 `[옛 sha, C]` + C 시험 3개), `test_highpose_arrival_confirm.py`(기록 문구를 확장 설명으로, 거절 경로·실제 런타임 시험 추가).
- 이전 기준 커밋(496da4ea)에서 diff C만 적용한 같은 시험은 444 passed, 1 skipped였다([analysis/tests_496da4ea_diffC_superseded_base.txt](analysis/tests_496da4ea_diffC_superseded_base.txt)).
- 이 PR(보정 수집 코드): `tests/test_final_environment_gain_calibration_v101.py`·`tests/test_simulation_workflow_manager.py` 28 passed ([analysis/tests_this_pr_gaincal_workflow.txt](analysis/tests_this_pr_gaincal_workflow.txt)). CI 전체는 PR의 CI가 돈다.

### 7.3 회복 재생 결과 (C 보정, 평가 전용: 정답은 채점에만 씀)

(a) **실제 도착 거절 사례** — `v98-dev-probe-dock_approach-1236c63d` r1: 첫 도착이 자기 영상 검사에서 실제로 거절됐고(기록된 `begin_relocalization` 프레임 시각 46.40 s),
거절은 한 번 더 일어나 약 64 s에 접근이 끝났다. 기록된 재위치추정 시점에 도착 거절 경로와 같은 요청을 켜서(`--arm-reloc`, 제품 코드의 같은 helper) 재생했다. 3시드(0·101·102). r2는 거절 없는 정상 주행.
([analysis/real_summary.txt](analysis/real_summary.txt))

| r1, 시드 0/101/102 | 36–46 s 오차 mm (NEES) | 46.5–52 s | 52–58 s | 58–66 s | σx 36–46 → 58–66 s (mm) | 주입(R1) | 확장(R2) |
|---|---|---|---|---|---|---|---|
| HEAD 그대로(옛 DEV 채움) | 214 / 236 / 153 (2897–5869) | 212 / 234 / 151 | 210 / 232 / 150 | 208 / 231 / 146 (NEES 1585–3394) | 2.1–4.3 → 3.6–4.9 (과신) | 0 | 0 |
| C만 | 23 / 23 / 26 (7.0–7.2) | 20 / 19 / 21 (7.5–7.7) | 17 / 16 / 18 | 16 / 16 / 17 (NEES 8.3–8.7) | 4.5 → 3.8–3.9 | 0 | 0 |
| C + R1 | C만과 동일(비트 단위) | 동일 | 동일 | 동일 | 동일 | **0** | 0 |
| C + R1 + R2 | 23 / 23 / 26 | **40 / 44 / 44** (NEES 1.8–2.3) | 16 / 15 / 22 (0.9–1.9) | 14 / 13 / 19 (1.9–3.4) | 4.5 → **10.5 / 7.4 / 9.4** | 0 | 1 |

- 해석: C 아래서는 실제 거절 시점에도 추정이 정답 약 2–3 cm 안이고 NEES 7로 한계 13.8 안이라 길을 잃은 필터가 아니다(HEAD 그대로는 15–24 cm, NEES 수천). R1은 한 번도 발동하지 않았다.
  R2는 거절 직후 입자를 ±(0.1, 0.1, 0.2)만큼 퍼뜨려 오차를 일시적으로 약 +20 mm 키우고(40–44 mm), σx를 약 2배로 키운 뒤 다음 둘러보기에서 다시 수렴한다(58–66 s 13–19 mm로 C만과 같은 수준).
  그 대가로 NEES는 7–9(약간 과신)에서 1–3(적절)으로 내려온다. 이 사례에서 R2의 순이득은 "정직한 σ"이고 오차 이득은 없다. r2(거절 없음)는 C만과 통합 모두 한 칸도 다르지 않다(확장 0).

(b) **1f7fb800 probe의 반사실 거절**(그 코드에는 도착 검사가 없었다; r2의 기록된 재위치추정 49.10 s는 도착 거절이 아닌 다른 원인이고 r1은 49.1 s에 가상 거절을 놓음. 둘 다 "거절이었다면"의 반사실 배치) — C 보정, 시드 0·101, 66 s까지
([analysis/rec_summary.txt](analysis/rec_summary.txt)):

| | 거절 후 50–56 s 오차 mm / NEES | 60–66 s | σx 40–49 → 60–66 s | 주입 | 확장 |
|---|---|---|---|---|---|
| r1 C만 | 3 / 0.5 | 4 / 0.7 | 4.8–5.0 → 4.1–4.3 | 0 | 0 |
| r1 C+R1+R2 | 9 / 0.2 · 7 / 0.1 | 7 / 0.4 · 11 / 0.7 | 5.1–5.3 → 10.4–10.9 | 0 | 1 |
| r2 C만 | 20–21 / 3.0–4.0 | 19–20 / 3.2–3.8 | 3.2 → 4.1–4.2 | 0 | 0 |
| r2 C+R1+R2 | 36 · 25 / 0.8 · 0.5 | 30 · 16 / 3.2 · 1.2 | 3.5 → 4.3 | 0 | 1 |

  두 번째 거절(52.1 s, 시드 0)을 더하면 r1 σx는 13.2 mm까지, 오차는 5–10 mm다. 같은 경향이다(비용은 작고 σ는 넓어진다).

(c) **오탐 검사(보류 도크·정상 주행)**: 보류 도크 probe 2개(3358372e·7623c4dc, r1·r2 = 4실행)에서 C만 대 통합 트리의 오차 시계열이 비트 단위로 같고(최대 차이 0), R1 주입 0, 재위치추정 0, R2 확장 0.
정상 주행 구간(위 모든 재생의 거절 전: 1f7fb800 r1·r2 < 49 s, dock_approach r1·r2 < 46.4 s)에서도 R1 주입 0. ([analysis/held_summary.txt](analysis/held_summary.txt))

(d) 한계와 정직한 판정: **C 보정 아래에서는 R1·R2가 필요한 사례가 이번 기록에 없다**(필터가 길을 잃지 않음). 이전 분석(2026-10-04, 옛 과신 필터)에서 R1·R2가 회복하는 것을 봤지만,
그 필터는 C가 이득 편향을 고치면서 사라진 상태다. 그래서 R1·R2는 "이득·잡음 모델이 다시 틀렸을 때를 위한 보험"이고, 이번에 잰 비용은 위 표(R2 한 번에 약 +20 mm 일시, σ 약 2배)다.
조정자 결정에 따라 diff로 제공하되, 효과(회복 능력)는 새 기록에서 길을 잃은 필터를 만났을 때 다시 확인해야 한다(미검증).

## 8. 무효화 목록 (diff C 이상을 적용할 때)

1. **새 실행 번들이 필요하다.** `dev_pilot` 레지스트리가 바뀌어 v98 번들 해시가 달라진다. 새 번호는 적용 시점에 main·열린 PR 헤드의 최댓값을 다시 확인해 예약한다
   (이 시점 사용 중: v100 `claude/llm-pair-e2e`, v101 이 PR의 보정 수집 번들).
2. **이전 v98 DEV probe 기록(398372ae 보정)과 새 번들의 결과는 합산하지 않는다**(보정이 다름). 옛 sha는 레지스트리에 남겨 옛 기록의 DEV 표식을 계속 인식·거부(`require_promotable`)한다.
3. **README(#363)의 NEES 표를 새 보정 기준으로 다시 만든다**(PF σ·오차가 달라짐).
4. **σ 문턱 재검증**: PF σ를 읽는 문턱은 DR 영수증(std_xy ≤ 50 mm, std_yaw ≤ 3°), blind close의 `FIX_STD_*`, relook(σ ≤ 0.08/0.10 m), look-around 장애물 법선 σ, carry align의 Z·σ,
   가드 `SIGMA_CAP_*`다. C에서 σx 평균은 probe 30–60 s에 r1 4.9 mm, r2 3.4 mm로 HEAD(4.2, 10.4)와 같은 자릿수지만, 하중 구간(`motion_loaded`는 바꾸지 않음)과 긴 DR 구간은 이번에 안 쟀다.
5. 영상 문턱 `own_image_gates`의 기록 항목 `dev_calibration_sha256`은 옛 sha(398372ae)를 가리킨 채 남는다. 이 문턱은 영상 통계로 정했고 C는 `params.motion`만 바꾸며
   카메라 모델이 같아 영향은 없다(읽는 코드도 이 항목을 검사하지 않는다). 필요하면 별도 PR에서 갱신.
6. 하중(적재) 운동 모델과 loaded PF는 이번에 바꾸지 않았다. 적재 구간의 PF 일관성은 이 결과로 주장할 수 없다.
7. 이 보정은 SIM 바퀴 평면(임시 wrench 모델, 마찰 0.001)에 대한 것이다. 실물 보정이 아니며 sim2real 결론은 아니다.

## 9. 파일

- 실행 기록: [runs/](runs/)(run별 `case_result.json`, `run_result.json`, `plan.json`, `artifacts.sha256.json`; `coordinator_main.txt`, `coordinator_smoke_heldP2.txt`).
- 산출물: [products/](products/). 적용용 diff: [diffs/](diffs/)(sha256은 [diffs/SHA256SUMS](diffs/SHA256SUMS)).
- 재생 분석 도구·요약: [analysis/](analysis/). 재생 원본(.jsonl)은 기본 체크아웃 `/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/replay/`(커밋하지 않음, sha256 목록 [analysis/replay_files.sha256](analysis/replay_files.sha256)).
- 시험: [analysis/tests_*.txt](analysis/).

## 10. 참고 자료 (U = 원문 미확인)

- [V] J. Borenstein, L. Feng, "Measurement and Correction of Systematic Odometry Errors in Mobile Robots", IEEE Trans. Robotics and Automation 12(6):869–880, 1996(저자 사본 읽음).
  계통 오차는 잡음으로 흡수하지 않고 측정해 모델에서 고친다. 이 보정은 UMBmark의 식이 아니라 "작동점에서 계통 이득을 재서 고친다"는 원칙을 쓴다.
- [V] 이 저장소 PF 예측기 `harness/owncam_localizer.py predict_to`(적합 모델과 같은 형태), `harness/zone_pair_highpose_contract.py dev_pilot_calibration`(수용 규칙).
- [V] Nav2 AMCL 소스·문서(`recovery_alpha_slow` 0.001 / `recovery_alpha_fast` 0.1 예시값), MRPT 운동 모델 문서, emcl2 README(expansion radius 0.1 m / 0.2 rad) — 이전 조사(2026-10-04 `references.txt`)에서 값을 읽음.
- [U] Thrun, Burgard, Fox, *Probabilistic Robotics*, MIT Press 2005 (5장 운동 모델, 8장 augmented MCL).
- [U] Ueda, Arai, Sakamoto, "Expansion resetting for recovery from fatal error in Monte Carlo localization", IROS 2004 — 원문 미확인(emcl2 README로 값만 확인).
- [U] Lenser & Veloso, "Sensor resetting localization for poorly modelled mobile robots", ICRA 2000.
- [U] Ljung, *System Identification: Theory for the User*, 2nd ed., 1999 — 출력 오차 식별과 검증 자료 분리 원칙.
- 이 PR의 측정 근거 파일: `calibration_candidate_r5_yaw.json` sha256 `978727fc…`(등록 r4/r5 잡음), `experiments/2026-10-01-calib-motion-v89-physics/fit_check_output.txt`.

## 11. 열린 문제

1. R1·R2의 회복 능력은 C 아래에서 **미검증**이다(길을 잃은 필터가 이번 기록에 없음). 비용만 측정했다(§7.3). 새 기록에서 필터가 길을 잃는 경우를 만나면 다시 확인해야 한다.
2. 하중(적재) 구간 보정(`motion_loaded`)과 긴 DR 구간의 σ는 이번에 쟀거나 고치지 않았다. σ 문턱 재검증(§8-4)은 #363 작성자의 새 번들 실행에서 한다.
3. 잡음 B는 등록된 r4/r5 값을 그대로 썼다. 이 SIM 평면은 거의 결정적이어서(반복 퍼짐 5.8e-8) 이 보정만으로는 물리 잡음을 잴 수 없다. 이 보정에서 잰 잔차 잡음(C2)은 포함 비율 조건을 못 채웠다.
4. 이 보정 값(이득 1.56 / 1.10 / 1.37)은 임시 wrench 구동 모델(마찰 0.001)의 값이다. 실물 로봇에는 따로 측정해야 한다.
5. TensorBoard: 조정자 요청(2026-10-05)으로 `docs/tensorboard.md`의 오프라인 감사 진입점(`scripts/export_offline_audit.py`)에 맞춰 파생 뷰 31개를 만들어 새 스냅샷 `outputs/tensorboard/1005b-gaincal-v101`로 등록했다(수집 6건, 적합·보류 요약 1건, 재생 선택 HEAD/B/C/C2 × 5시드 20건 + 설정별 앙상블 4건). 생성기는 `analysis/gen_tb_views.py`이며 값은 해시된 원본·`sel_summary.json`·`heldout.json`에서 그대로 옮겼다(재계산 없음). 공용 서버 6006에서 실행 31개가 읽혔고 scalar 576개를 API로 되읽어 모두 일치했다. 공용 HParams 표는 오래된 실험이 정한 14개 지표 열만 등록하므로 이 세션의 `offline/*` 값은 Time Series 고정 카드로 본다. 링크·고정 카드는 `outputs/tensorboard-view.json`의 `gaincal_v101_20261005` 키에 있다.
6. diff C·통합 diff의 적용·커밋은 #363 작성자가 한다. 적용 뒤 새 번들 번호 예약과 README NEES 표 재생성이 남아 있다(§8).
