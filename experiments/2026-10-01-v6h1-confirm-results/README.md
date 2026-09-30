# b-v6h1 확증 코호트 개봉 결과 (2026-10-01)

**한 줄 결과:** 주 시드 941의 고정 60곳(C01–C60)이 모두 `PASS_CLEAN`(60/60)이고 하드 한계(관통 5 mm, 기울기 15°) 위반은 0건이다. 사전 기준 A(48/60 이상), 기준 B(σ 포함률·평균 z²), 안전이 모두 통과해 `full_verdict = PASS_A_B_SAFETY`다. 보조 시드 943의 첫 12곳도 12/12이며 주 분모에 합치지 않았다.

**이 결과가 말하는 것:** 시뮬레이션(SIM)에서 teacher가 한 번 만든 시작 자세로부터, 로봇 두 대가 자기 RGB + 공용 top RGB + 자기 발행 명령 + 정적 지도로 L0 → 내려놓기 → 재파지 → L1을 이어서 해낸 것이 **고정된 60곳**에서 관측되었다.
**말하지 않는 것:** E2E 성공이 아니다(주문·목적지 내려놓기·대화 없음). 실물 로봇 결과가 아니다. 모집단 성공률 ≥80%의 증명이 아니다(관측된 고정 코호트 기준이며 Wilson 95% 구간은 배치 단위 [0.940, 1.000]). teacher 시작 자세가 있으므로 학생의 독립 시작 성공이 아니다. 실제 모델 호출은 0이다.

## 무엇을 시험했나

| 항목 | 값 |
|---|---|
| 단계 연쇄 | L0(문 접근 운반) → 내려놓기 → 재파지 → L1(문 통과 운반), L1 끝에서 정지(`chain_stop_leg=1`). 목적지 내려놓기는 평가하지 않음 |
| 시작 | teacher가 빔을 한 번 들어 올린 자세(teacher 예외, 이후 제어기는 자기 입력만 사용) |
| 제어 입력 | 자기 RGB · 공용 top RGB · 자기 발행 명령 이력 · 허용된 정적 지도. 정답 좌표는 평가 전용 |
| 환경 | SIM(clock SIM), weld OFF, 모델 호출 0, 초음파 off, 렌더 `floor_light_v1`, PF/contact ON, 접촉 프로필 `cargo_noslip_v1` |
| 제어기 | `b-v6h1`, 실행 소스 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`(274파일 고정), 번들 `zone-pair-v83-carry-door-gain`, workflow 2.16.0 |
| 코호트 | seed 941 × C01–C60(주 분모 60), seed 943 × 첫 12곳(민감도). 각 1회 시도, 재시도 0 |
| 예산 | SIM 800 s / 실제 1500 s, workers 4, OMP 1 |
| 판정 | 봉인 v2(`5be4330e`)의 분류기 `classify_placements.py` — 기준 A·B·안전 |

## 기록 시점 공개 (중요)

- **블라인드 기록은 분석 봉인보다 먼저 이뤄졌다.** 72건은 `prereg_v6h.json`이 봉인되기 전에 "봉인되지 않은 단계 시험(unsealed stage-probe admission, `--prereg` 없음)"으로 기록됐다. 사전 등록 전 실행으로 소급 표시하지 않는다. 사전 등록 문서도 `analysis_sealed_after_blinded_recording`으로 적었다.
- 기록은 별도의 얇은 driver가 같은 worker 진입점을 호출해 만들었다(메타데이터 커밋 `e78ef70f`, `0b77ae4b`, 브랜치 `origin/claude/v6h1-confirm-run`).
- 시각 증거(파일 수정 시각·manifest, 암호학적 증명이 아님, 로컬 시각 +09:00):

| 시각 | 사건 |
|---|---|
| 2026-09-30 23:06 | 첫 case 시작 (`case_status.jsonl`) |
| 2026-10-01 00:55 | driver 종료(`DRIVER_FINISHED completed`), 72건 모두 attempt 1·worker 종료 코드 0 |
| 2026-10-01 04:50 | 취득 목록(acquisition inventory) 생성 — 기록 **뒤**, 개봉 **앞** |
| 2026-10-01 06:22 | 봉인 v2 커밋 `5be4330e` |
| 2026-10-01 08:07 | 개봉 실행 산출물 생성 (`sealed_analysis.json`, `classifier.json`) |

- driver의 첫 시도(`manifest_wait_attempt1_aborted.json`)는 물리 잠금을 기다리다 SIGTERM으로 멈췄고(1237 s 대기) case를 하나도 실행하지 않았다. 버려진 case는 없다.
- 기록 중 다른 작업 때문에 load average가 최대 약 220까지 올랐다. SIM 시간 실행이라 행동은 부하와 무관하지만 **wall 시간은 성능 지표가 아니다**.
- 개봉 전 검사: `--verify` rc 0, `--verify-seal v2` rc 0, 나열된 486개 테스트 통과. 테스트 fixture 오류 6건은 `GIT_WORK_TREE`를 export했을 때만 생겼고(export하지 않으면 통과) 결과 분석과 무관하다. 전체 테스트 실행 로그: `480 passed, 6 errors`(export한 환경).

## 명령과 해시

개봉(읽기 전용; 분석 재실행 아님, 여기서는 그 산출물만 읽었다). 조정자가 실제로 실행한 명령 원문(2026-10-01 08:07 KST, 종료 코드 0)은 다음과 같다. 사전 검사 `--verify`·`--verify-seal --seal-revision v2`는 모두 종료 코드 0, REGISTRATION_PLAN의 12개 테스트 파일은 480개 통과·6개 오류였고, 6개 오류는 `GIT_WORK_TREE`를 export한 상태에서 테스트 fixture의 `git clone --shared`가 실패한 것이며 변수를 해제하고 다시 돌리면 6개 모두 통과했다.

```
cd /Users/changmin/projects/ugrp-wt/unblind-v6h1-s2        # 분리 HEAD 5be4330e, 깨끗한 작업 트리
export GIT_WORK_TREE=/Users/changmin/projects/ugrp-wt/unblind-v6h1-s2
V6H_PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
V6H_SEAL_V2_COMMIT=5be4330eca9b23d2cbde3657dcbb215ee1923b25
$V6H_PYTHON -m experiments.2026-09-30-pair-v6h-carry.analysis.apply_sealed_analysis \
  --seal-commit "$V6H_SEAL_V2_COMMIT" \
  --prereg experiments/2026-09-30-pair-v6h-carry/analysis/seal_v2/prereg_v6h.json \
  --raw /Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930 \
  --inventory /Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930-inventory/acquisition_inventory.json \
  --output /Users/changmin/projects/ugrp/outputs/v6h1-sealed-analysis-v2-20261001
``` 이 기록을 만든 명령(모두 읽기 전용):

```
python3 experiments/2026-10-01-v6h1-confirm-results/tabulate.py            # per_case.csv, distributions.json
python3 experiments/2026-10-01-v6h1-confirm-results/build_tb_views.py --output /Users/changmin/projects/ugrp/outputs/v6h1-unblind-results-tb-derived-20261001
.venv-sim-worker-mac/bin/python scripts/export_offline_audit.py --source <파생 뷰 74개> --output /Users/changmin/projects/ugrp/outputs/tensorboard/1001-v6h1-confirm
python3 scripts/render_pair_probe_video.py --case <C49 s941 case 폴더> --label "b-v6h1 C49 s941 (PASS_CLEAN)" [--wrist] --dt 0.5 --fps 8 --output videos/…
```

| 대상 | 위치 | SHA-256 |
|---|---|---|
| 사전 등록 payload(`registration_sha256`) | `5be4330e:experiments/2026-09-30-pair-v6h-carry/prereg_v6h.json` | `487950b61e0207e6634e8e2895b8f2b8b79dc91c50aded2bd26c23064f807d57` |
| 봉인 파일 바이트 | 같은 파일 | `337f12055230a7401b4285d99a977bfc7f5fe9a1f4c3f5514879e81af3ec83b3` |
| `sealed_analysis.json` (이 폴더에 사본) | `outputs/v6h1-sealed-analysis-v2-20261001/` | `e22ee5bbf9acadf69813ba6c5e716622980fd08a0d1a6fdd3be986d9192eb297` |
| `classifier.json` (1,104,045 B > 1 MiB라 **사본 없음**, 경로+해시) | `outputs/v6h1-sealed-analysis-v2-20261001/classifier.json` | `2383683ba4eb52afe0350767b4c6edd0751f706ddf02e96bf27fa3934c2bf7ca` |
| 취득 목록 | `outputs/v6h1-confirm-4c6b439f-20260930-inventory/acquisition_inventory.json` | `d7ceca9824d4098956c7bfc5cbd7298ee5b0cfa5dacdb12586d07c2ee07ec03f` |
| raw `manifest.json` | `outputs/v6h1-confirm-4c6b439f-20260930/manifest.json` | `07f623b7b30374da25cd0a8d2df62a70bbfdcae47b80279be6e310d7def27950` |
| raw `cases.jsonl` | 같은 raw | `8e7837cbc948abcd7a29a6b81272870ec7ab716c1aba87f018cd3aca655d1836` |
| raw `plan.json` | 같은 raw | `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026` |
| raw driver | 같은 raw `driver.py` | `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56` |
| 커밋된 `RUN_MANIFEST.json` | `e78ef70f` | `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210` |

raw(72 case 폴더)와 봉인 산출물은 수정하지 않았다. raw는 로컬 보관이며 원격 백업이 아니다.

## 결과

### 판정 수 (봉인 v2)

| | seed 941 (주, C01–C60) | seed 943 (민감도, 첫 12곳) |
|---|---|---|
| `PASS_CLEAN` | 60 | 12 |
| `PASS_CONTACT_RECOVERED` / `BLOCKED_BY_CONTACT` / `FAIL` | 0 / 0 / 0 | 0 / 0 / 0 |
| `FAIL_HARD_LIMIT` | 0 | 0 |
| 미분류(HOST_ERROR·누락 등) | 0 | 0 |
| 기준 A (≥48/60) | 통과 (60) | 해당 없음(민감도) |
| 배치 단위 Wilson 95% | [0.940, 1.000] | (12/12: [0.757, 1.000] 계산값) |

주 시드와 보조 시드에서 모두 성공한 배치가 60곳, 모든 기록 시드에서 성공한 배치가 60곳이다(보조 시드가 있는 12곳 포함). 하드 위반 0건은 두 시드의 모든 시도를 합친 값이다. 72건 전부 재시도 없이 첫 시도다.

### 기준 B (자기 위치 σ 보정 확인)

주 시드, 로봇 2대 × 배치. 기준: x/y/yaw 각각 ±2σ 포함 ≥90% **그리고** 평균 z² ≤1.3.

| leg | 축 | ±2σ 포함 배치 (표본 포함률) | 평균 z² |
|---|---|---|---|
| L0 | x / y / yaw | 60 / **59** / **59** of 60 (1.000 / 0.992 / 0.992) | 0.029 / 0.455 / 0.353 |
| L1 | x / y / yaw | 60 / 60 / 60 (1.000) | 0.054 / 0.239 / 0.040 |

seed 943(민감도): L0·L1 모두 12/12/12, 평균 z²는 L0 0.026/0.506/0.356, L1 0.061/0.158/0.038. 기준 B는 통과다. σ가 정확히 보정되었다는 주장은 하지 않는다. 평균 z²가 모두 1보다 훨씬 작아 σ는 오히려 **보수적(크게 잡힘)**으로 보인다(과보수 진단 C는 보고만 하는 항목).

### 독립 집계 (classifier.json + raw `cases.jsonl`에서 표로 옮김, 분석 재실행 아님)

집계 재현: `tabulate.py` → `per_case.csv`(72행), `distributions.json`. 아래 수치는 seed 941(n=60) 기준이며 seed 943(n=12)도 거의 같다(`distributions.json`).

| 지표 | 최소 | 중앙값 | p90 | 최대 |
|---|---|---|---|---|
| 기록된 SIM 정지 시각 (s, 6.1 s에서 시작) | 58.4 | 60.3 | 62.3 | 62.3 |
| 연쇄 SIM 길이 L0 시작→L1 끝 (s) | 52.3 | 54.2 | 56.2 | 56.2 |
| 발행 명령 수, 두 로봇 합 | 2143 | 2181 | 2221 | 2221 |
| 발행 명령 수, r1 / r2 | 1072 / 1071 | 1091 / 1090 | 1111 / 1110 | 1111 / 1110 |
| L0 끝점 오차 (m, 한계 0.10) | 0.0091 | 0.0428 | 0.0609 | **0.0716** (C12) |
| L1 끝점 오차 (m, 한계 0.10) | 0.0079 | 0.0464 | 0.0685 | **0.0789** (C14) |
| 연쇄 전체 최대 기울기 (°, 한계 15) | 0.017 | 0.018 | 0.019 | 0.020 |
| 연쇄 전체 최대 관통 (m, 한계 0.005) | 0 | 0 | 0 | 0 |
| 접촉 episode (연쇄 전체) | 0 | 0 | 0 | 0 |
| wall 시간 (s, 부하 영향, 성능 지표 아님) | 208 | 285 | 514 | 1029 (C27) |

SIM 정지 시각은 세 값(58.4 s 12건, 60.3 s 47건, 62.3 s 13건)뿐이며 기록 창이 0.5 s 간격이라 그렇다. 명령 수도 세 값(2143 / 2181 / 2221, 각각 정지 58.4 / 60.3 / 62.3 s와 일대일)뿐이다. 명령 발행이 SIM 시간에 비례하고 모든 case가 같은 계획 경로를 따른 것과 일치한다(r1·r2는 1건 차이).

재파지·재시도 카운트(자기 기록한 타임라인 기준): 72건 × 로봇 2대 전부 `grasp`·`pregrasp_look`·`lift`·`cp_open`·`lower`가 **정확히 1회**다(재파지 재시도 0). 위치 추정기 reset·교체 0, 재관측 호출 1회(`begin_observation`)씩이다. 기준의 모든 leg 검사(들림, 기울기, 양 집게 접촉, 끝점, leg 오차)와 handover(내려놓기 → 재파지 들림)가 72건 모두 참이다. 들림 높이 L0 0.0614 m, L1 0.0616 m로 전 case 거의 같다(최소 기준 0.03 m).

### 아슬아슬한 것 (near-miss)

1. **σ yaw가 게이트 바로 아래까지 올라간다 (가장 중요한 관찰).** 자기 위치 yaw 불확실도 σ의 최댓값이 72건 전부 49.6–52.2 mrad이고, 든 상태의 게이트(3°, 52.4 mrad)까지 남은 여유가 중앙값 1.1 mrad, **최소 0.2 mrad**(C59, r1 52.19 mrad)다. 게이트를 넘기고 0.6 s 지속하면 `SELF_POSE_UNCERTAIN`으로 실패하는 규칙이라, 이 코호트는 모두 L1 끝(정지)에서 **게이트 여유가 거의 없이** 끝났다. 더 긴 leg, 추가 지연, 다른 시작 조건이면 실패할 수 있는 여유 폭이다. 이것을 "여유 있는 성공"으로 읽지 않는다.
2. **σ 포함률 59/60은 L0 C29 한 곳이다.** C29(seed 941)의 L0에서 r2의 y 오차가 2.03σ, yaw 오차가 2.14σ로 ±2σ를 벗어났다(r1 yaw는 1.94σ로 안쪽). y와 yaw의 59/60이 같은 배치이며 x는 안쪽이다. 기준 B 문턱(≥90%)에 비하면 여유가 크다. L0 z² 최댓값은 y 4.11, yaw 4.58이다.
3. **끝점 오차**: 한계 0.10 m 대비 최대 0.079 m(79%)이고, 0.05 m를 넘는 case가 L0 23건·L1 27건(72건 중), 0.07 m를 넘는 case가 L0 3건·L1 4건이다. 모든 leg에서 한계 안이지만 중앙값이 한계의 약 45%다.
4. 기울기 최대 0.020°, 관통 0, 접촉 episode 0으로 **안전 한계는 여유가 매우 크다**. 들림은 전 case에서 문턱(0.03 m)의 두 배쯤이다.

### 기록기 자체 라벨과의 관계

raw `cases.jsonl`의 각 case에는 표준 단계 시험의 자체 판정 `passed=false`, `category=STAGE_BUDGET_EXHAUSTED`, `outcome_class=FAIL`이 72건 모두 적혀 있다. 이 라벨은 **목적지 내려놓기(setdown)**를 기준으로 한 것으로, 이 연쇄는 L1 끝에서 일부러 멈추므로 제어기 종료(`controller_exit_both`)가 없고 내려놓기도 평가하지 않는다. 분류기 코드의 주석도 같은 뜻이다("Wrapper passed/outcome_class refer to destination setdown, outside this task"). 이 과제의 판정은 **사전에 봉인한 분류기**이며 이 라벨을 성공·실패에 쓰지 않았다. TensorBoard에서도 이 라벨은 `success`가 아니라 텍스트로만 싣는다.

## 같은 계열의 이전 기록 (참고, 합산하지 않음)

같은 `floor_light_v1` 렌더의 b-v6h 탐색 코호트가 있다(`0930-b-v6h-axial-lag`, `0930-b-v6h-gain` 스냅샷): 사전 등록 전 탐색이며 **배치가 다르다**(12곳·hR2 기록 10곳·추가 7곳, PF seed 두 개가 독립이 아님). 같은 계열(`k1g+p2f+gain+alag`)의 tS 24/24, tR 20/20, tX1 12/12(+X06 재실행 2/2)이고, 지연 보정이 없는 대조 tX0는 7/14, 더 이전 gain 대조는 sB 22/24·rB 14/20이다. 이 확증 코호트와 합산하지 않았고 그림에서도 조건을 구분해 표시했다. 그림자(shadows) 렌더의 더 오래된 결과는 포함하지 않았다.

## 한계 (말하지 않는 것)

- SIM만이다. 실물 로봇·실제 지면·하중 성능은 검증하지 않았다.
- teacher가 만든 시작 자세에서 시작한다. 학생이 처음부터 스스로 만든 시작이 아니다.
- L0 → L1까지이며 목적지 내려놓기·주문·대화·E2E를 평가하지 않았다. 정지 대응 성공으로 확대하지 않는다.
- 고정된 60곳의 **관측된** 성공이며 모집단 성공률이 아니다. 시드 943은 민감도이고 주 분모에 합치지 않았다. 두 PF 시드는 독립 표본이 아니다.
- 블라인드 기록은 분석 봉인보다 먼저였다(미봉인 admission). 취득 목록은 기록 뒤·개봉 앞에 만들었다는 것이 파일 시각 증거로만 뒷받침된다.
- 벽 접촉 추적기는 벽만 본다. 빔·로봇 사이의 접촉은 이 기록의 안전 판정 범위 밖이다.
- σ 보정의 "통과"는 σ가 정확하다는 증명이 아니다. 위의 게이트 여유도 함께 본다.
- 이 기록을 만든 세션은 분석을 다시 돌리지 않았다. 분류기 산출물의 수치를 raw와 대조해 표로 옮겼고 불일치는 없었다.

## 대표 영상 (버전별 대표 1건 규칙)

[`docs/version_videos.md`](../../docs/version_videos.md)의 규칙에 따라 b-v6h1의 대표 case 1건을 골랐다. 규칙: seed 941의 60건 중 끝점 오차 L0·L1, 요 드리프트 L0·L1, 정지 시각을 각각 중앙값·표준편차로 정규화한 거리의 합이 가장 작은 case = **C49 (seed 941, `PASS_CLEAN`)**. 개봉 뒤에 이 규칙으로 골랐으나 결과를 고르는 기준이 아니라 중앙값 근접이다. 이전 버전과 같은 case가 없어(배치 집합이 새로움) paired가 아니다.

| 파일 | 크기 | SHA-256 |
|---|---|---|
| `videos/chain_C49_s941_v6h1_topdown.mp4` | 68,050 B | `27afadb2db89ff1a4684d0ddb0d4bc17aaa23ecbc119106ffd8c8f539f280bbb` |
| `videos/chain_C49_s941_v6h1_topdown_wrist.mp4` | 82,643 B | `55379fbfcf43d2f3324a5a9f68f7395aab44eae7464a5f43de9fab29d0620802` |

영상은 **정답 위치(평가용, 로봇 입력 아님)를 위에서 본 도식**과 로봇 자기 σ 곡선을 다시 그린 것이다. 실제 top 카메라 영상이 아니다(시험은 공용 top 카메라를 저장하지 않는다). wrist 판은 각 로봇의 저장된 자기 카메라 프레임을 같이 보여준다(프레임 시각 정합 정확). 재생 속도 4배, SIM 0.5 s 간격. E2E 성공·성공률이 아니다. 이 한 case가 보이지 못하는 것: 다른 59곳의 분포, σ가 게이트에 가까웠던 점(영상의 σ 곡선에는 보이나 이 case가 가장 가까운 것은 아님), 시작 자세가 teacher가 만든 것이라는 점. case 원자료: `outputs/v6h1-confirm-4c6b439f-20260930/cases/chain_b-v6h1_teacher_C49_s941_pPOST_VENVS/`.

## TensorBoard

- 새 스냅샷: `/Users/changmin/projects/ugrp/outputs/tensorboard/1001-v6h1-confirm` (run 74개: case 72 + 시드별 집계 `ALL-s941`, `ALL-s943`). 파생 뷰 입력: `outputs/v6h1-unblind-results-tb-derived-20261001/`(각 뷰가 case의 원본 `result.json` 또는 `sealed_analysis.json`을 경로+SHA-256으로 가리킨다).
- run 이름은 `1001-v6h1-confirm/C01-s941`처럼 짧게 썼다. 조건 열은 `confirm primary s941 chain L0->L1` / `confirm sensitivity s943 chain L0->L1`, 정책 `b-v6h1`, family `b_v6h1_confirm`.
- 싣은 값: case별 `evaluation/reported_success`(=PASS_CLEAN), `result/sim_s`·`wall_s`·`commands`·`model_calls`(0), leg별 끝점 오차·σ·z²·NEES, 최대 기울기·관통·접촉, 집계의 성공 수·Wilson 구간·σ 포함 배치 수. 모델 응답 시간은 모델 호출이 0이라 없다(0으로 채우지 않음).
- 비교 기준(`0930-b-v6h-axial-lag/ALL-*`, `0930-b-v6h-gain/ALL-sB·rB`)은 위 "이전 기록"의 탐색 코호트이며 같은 카드에 나란히 놓되 합산하지 않는다.
- 스냅샷 `collection.json` SHA-256 `df5af26df50248ad32e86e25681857f9da6ed0e1373c58fa8fdc560b20f5d8b2`. 이벤트를 EventAccumulator로 다시 읽어 72개 case와 집계 2개의 성공·sim_s·wall_s·model_calls·최대 기울기·L1 끝점 오차가 classifier/raw와 일치함을 확인했다(불일치 0). 공용 서버(pid 26582, `--logdir` 기본 체크아웃 `outputs/tensorboard`)는 수정하지 않았고 새 run 74개를 읽고 있다. 내장 브라우저에서 저장된 pin 링크를 열어 집계 표의 값(941·943 모두 성공 1, 비교 tS 1·tR 1·tX0 0.5·sB 0.917·rB 0.7)을 원본과 대조했다. HParams 탭의 열 표시는 새 행에서 화면으로 확인하지 못했다(미확인).
- 정리된 보기 링크·확인 범위는 `outputs/tensorboard-view.json`의 `v6h1_confirm_20261001` 키에 있다. 영상은 오프라인 감사 변환기가 영상 등록을 지원하지 않아 TensorBoard 미디어로는 등록하지 않았고, 위 영상은 이 폴더와 `docs/version_videos.md`에 있다.
