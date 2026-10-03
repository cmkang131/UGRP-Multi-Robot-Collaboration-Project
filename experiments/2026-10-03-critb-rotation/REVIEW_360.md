# PR #360 독립 검토

**판정: MERGE.** 훈련 전용 yaw 후보와 별도 채점 전 부록을 보존하는 범위에서 병합 가능하다. P0/P1 및 병합 전 필수 수정은 발견하지 못했다. 아래 P2 두 건은 후속 검증에서 지킬 비차단 경계다. v91 통과, PF/학생 제어기 채택 또는 물리 성공에 대한 승인이 아니다.

- 검토자: Codex, `codex/review-360`; 2026-10-03 06:03 UTC 기준.
- 검토 대상: `c3af0783e8d05b40c9e859657e7f6ecae0928aed`.
- 비교 main: fetch로 확인한 `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`.
- 지침·README·current_status·CONTRIBUTING을 읽고 시작 시 `git fetch origin`, 열린 PR을 확인했다. 리뷰 브랜치만 대상 SHA로 fast-forward했다.
- 허용된 v88/v89 학습 raw만 읽었다. v91 held-out 경로는 identity 예외도 사용하지 않았으며 열람·해시·채점 0회다. 별도 Python 접근 가드로 재현 중 held-out 접근과 학습 raw 쓰기를 차단했다.
- 물리·렌더·모델 호출 0회. 실행 중 프로세스·공용 잠금·서버 및 `.github/workflows`를 변경하지 않았다. 이번 변경은 이 리뷰 파일뿐이다.

## 비차단 관찰과 후속 조건

### P2-1 — 선언된 3개 파라미터는 식별되지만 독립 표본·넓은 동작 범위의 증거는 아니다

위치: `scripts/fit_consumer_criterion_b_rotation.py:83-105`, `experiments/2026-10-03-critb-rotation/README.md:25-27,49-50,76-79`.

v88 한 지도·r1·무하중의 242–326 SIM초를 쓴다. ±0.01/±0.02/±0.03 각각 10초 step과 1초 coast, ±0.02 PRBS 31칩(칩당 0.5초)과 마지막 2.5초 coast가 있다. 양수 760/음수 750 tick이며 모든 0.2–3.2초 창을 지원한다. 재현한 로그 파라미터 Jacobian 특이값은 `[3.5933097839, 0.1540127757, 0.0186919285]`, 조건수 약 192.24, rank 3이고 경계 도달 없이 8회 함수 평가로 수렴했다. **고정된 sign-common gain/run tau/stop tau 모델의 수치 식별은 충분하다.**

다만 8,736개 잔차는 같은 단일 궤적에서 중첩해 만든 창이다. 예를 들어 3.2초 창을 0.05초 이동하면 인접 두 창은 63/64 tick을 공유한다. 따라서 895/942는 독립 시험 942회의 성공률이나 파라미터 신뢰구간이 아니다. stop tau 0.03737초는 0.05초 표본 간격보다 짧으므로 이 값은 해당 이산 소비자 법칙의 유효 계수로 해석한다. 더 빠른 연속 동역학, sign별 비선형성, 혼합축·하중·실물 일반화를 입증하지 않는다. 현재 후보의 null 검증 상태와 제한 문구가 이 경계를 보존하므로 비차단이다.

### P2-2 — v88 PRBS 재사용과 동일 자극 일정의 일반화 범위를 구분해야 한다

위치: `scripts/fit_consumer_criterion_b_rotation.py:83-86,239-256`, `scripts/final_pair_calibration_motion.py:241-250`, `experiments/2026-10-03-critb-rotation/SCORING_HOOK.md:13-21,27-36`.

r5는 v88 steps와 PRBS를 모두 평균·잡음 학습에 사용한다. 기존 B-prime 경로가 같은 수집의 PRBS를 `validation_split`으로 부르는 것과 구분해야 한다. **구체적 재사용 반례:** r5를 같은 v88 PRBS에 대입해 나온 100%를 “새 검증 성공”으로 보고하면 이미 학습한 창을 검증에 다시 쓴 것이다. r5에서는 그 자료 전체가 훈련이며 후속 검증으로 재사용할 수 없다.

정적 소스상 v91은 v88의 같은 자극 일정을 사용한다(`configs/zone_final_pair_v91.json:14`; 수집 SHA 두 개의 `harness/zone_final_pair_excitation.py` 바이트 동일). 새 두 지도·새 수집 검증은 가능하지만 새로운 PRBS/진폭/시간 패턴의 일반화 검증은 아니다. 이번 감사에서 학습 manifest는 훈련 지도만 포함했고 두 학습 pose 해시가 r5의 `previously_seen_pose_sha256`에 들어 있다. v91 raw를 읽지 않았으므로 실제 raw 간 비중복을 여기서 확정하지 않는다. 후속 hook에서 공개 고정·두 지도 identity/source/schedule·기존 pose 중복 거부를 구현·검사해야 한다. 동일 파일 해시 차단은 재작성·재표본화한 파생 자료까지 독립성을 증명하지 않는다.

공개 고정은 수집 후·채점 전이다. 서버 댓글 시각과 해시 일치는 확인했지만 모든 참여자의 과거 미열람을 증명하지는 않는다. 부록과 hook이 이 한계를 이미 명시하고 결과를 별도로 저장하도록 하므로 비차단이다.

## 요청된 검사 결과

### 1. 공개 고정 및 기존 바이트 — PASS

[#219 댓글 5966135675](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966135675)를 GitHub API로 직접 확인했다. `created_at == updated_at == 2026-10-03T05:56:19Z`; 본문 SHA-256은 `a878f54a20b27db812bac783b82545bcb0047c0dc0c26b9b4390728ba784dbc7`이다. 아래 두 공개 값이 대상 PR의 실제 파일 바이트와 일치한다.

| 파일 | 실제 SHA-256 |
|---|---|
| `consumer_criterion_B_rotation.json` | `6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08` |
| `calibration_candidate_r5_yaw.json` | `978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97` |

`preservation.json`의 36개 파일을 PR/main Git blob과 직접 대조했다. 기존 B `74c312b5…`, r4 `fa7d3aa2…`, frozen validator `8d2a693a…`를 포함하여 모두 byte-identical이다. r5의 forward/left 전체 객체는 r4와 같고, 들여쓰기를 포함한 직렬화 블록 바이트도 같다. `params` 전체도 같으며 `params.motion=null`, 모든 `axis_validation=null`, 상태 `CANDIDATE_UNVALIDATED`를 유지한다.

### 2. r4 방법과 수치 재현 — PASS

새 적합기를 허용 raw로 다시 계산한 yaw 객체와 훈련 보고서 전체 수치가 커밋된 값과 정확히 일치했다. 동일 v88 입력에 기존 `r4.fit_mean(data, 2, B)`를 직접 호출해 세 평균 파라미터가 정확히 같은 것도 확인했다. 별도로 작성한 0.05초 끝 속도 Euler recurrence 역시 기존 계산과 오차 1e-15 미만으로 일치했다.

sign-common gain, run/stop tau, 로그 파라미터의 범위·초깃값·least-squares 종료 조건, 모든 끝점 오차의 동일 가중, 명령만으로 초기화·누적하는 상태를 그대로 쓴다. 잡음식 `noise_rel*abs(v_next)+noise_abs`, M1 하한, 상대 세 값 → 절대 yaw → forward → left의 사전식 순서를 유지한다. 회전 좌표계의 x/y 분산 혼합을 포함한 해석식은 frozen full-matrix evaluator 및 합성 테스트로 대조했다. r4의 병진 전용 최소화 함수를 회전에 직접 사용한 것은 아니다.

| 항목 | 독립 재현값 |
|---|---:|
| gain | 1.0725221565695355 |
| run tau (s) | 0.16770868665607128 |
| stop tau (s) | 0.03736721159765567 |
| yaw noise_rel | 0.1116 |
| yaw noise_abs | 0.015461140772925479 |
| 최소 2σ 훈련 포함률 | 0.9501061571125266 = 895/942 |
| 제한 그룹 | steps / 3.2초 / yaw |
| 해당 정규화 절대오차 p95 | 1.9999999996663158 |
| 평균 적합 잔차 수 / RMSE rad | 8736 / 0.004666751616148002 |

잡음 벡터는 rel `[0.3176,0.4438,0.1116]`, abs `[0.01538,0.00504,0.015461140772925479]`다. yaw 최소해 `0.015461140771925478`에 1e-12만 더했다. 최소해에서 1e-8을 낮추는 독립 반례에서는 해당 포함률이 79.6178344%로 떨어져 95% 조건을 위반했다. 이는 최소해 근처에 잔차 임계값이 밀집한 결과이며 독립 성공확률의 여유를 뜻하지 않는다.

| 시간 (s) | steps 창 | PRBS 창 | steps yaw 포함률 | PRBS yaw 포함률 |
|---:|---:|---:|---:|---:|
| 0.2 | 1302 | 357 | 100% | 100% |
| 0.5 | 1266 | 351 | 100% | 100% |
| 1.0 | 1206 | 341 | 100% | 100% |
| 2.0 | 1086 | 321 | 100% | 100% |
| 3.0 | 966 | 301 | 100% | 100% |
| 3.2 | 942 | 297 | 95.0106157113% | 100% |

forward/left 오차 성분은 모든 그룹에서 100%다.

### 3. 학습 입력과 실제 시계 schema — PASS

명세의 9개 파일 SHA-256·바이트 수를 실제 파일과 대조했고 계산 후 다시 확인했다. v89 네 파일은 frozen r4 입력과 같고 turn은 4,600 tick 모두 0이어서 yaw 학습 창 0개다. v88은 지정된 source `747d2b9f1eb43e21804ccef58fff4db241d1a844`, 훈련 지도 `zone_wide_two_doors_final_v3`, 무하중 r1의 다섯 파일만 사용한다. 기록된 measurement도 해당 수집 SHA의 `design('calibration-unloaded')`와 정확히 같다. 지도·하중·완료 상태·실제 발행 명령·lease·pose 0.05초 시계/순번/회전행렬 감사가 통과했다.

fitter는 pose/commands의 `t`를 사용하며 frame을 읽지 않는다. 검토자는 허용된 v88 훈련 `robots/r1/frames.jsonl`의 첫 metadata 행만 별도로 확인했다. 실제 키는 `sim_time`이고 `t`는 없다. 이미지·라벨이나 frame의 actuator 값은 적합에 넣지 않았다. held-out 지도/파일을 학습 입력에서 발견하지 못했다.

### 4. 부록의 B 유지 및 v91 채점 정의 — PASS (연결 구현은 후속 범위)

`consumer_criterion_B_rotation.json:7-10,131-174`와 `SCORING_HOOK.md:6-36`은 원래 B/r4 판정을 보존하고 yaw 부록 결과를 별도로 저장한다. horizons·components·windows·axis_support·acceptance는 B와 문자열/JSON 값이 같다. `fit.mean`은 B 문구를 그대로 보존해 “v89”라는 원문도 남아 있으나 실제 yaw 자료 선택은 `training.v88_selection`과 README에 분명히 정의돼 있다.

v91 bundle/source, corridor+door-geometry 두 지도, 무하중, 훈련 부적격을 지정한다. 각 지도/사례/steps·PRBS/시간/성분에서 NumPy linear `p95(abs(error)/sigma) <= 2`와 `coverage_2sigma >= 0.90`을 모두 요구한다. 모든 0.05초 시작점·coast를 포함하며 구간 연결·솎기·중심화·재적합은 금지한다. 지원 부족은 null, 한 실패는 false, 전부 통과해야 true다. 기존 `evaluate_axis` 재사용과 공개 해시·입력 감사를 요구한다. 수집 후 고정을 수집 전 등록으로 소급하지 않는다.

이 PR은 hook 설계까지다. #356 이후 연결 구현과 합성 회귀검사, 실제 두 지도 raw의 적격성 확인·채점은 완료되지 않았으며 이번 MERGE 권고에 포함하지 않는다.

## 검증 기록과 전달

독립 실행한 명령:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -m pytest -q \
  tests/test_consumer_criterion_b_rotation.py tests/test_consumer_criterion_b.py \
  tests/test_unloaded_consumer.py tests/test_unloaded_hammerstein.py tests/test_review_346.py
# 141 passed in 7.65s (yaw tests 18개 포함)

PYTHONPATH=. OPENBLAS_NUM_THREADS=1 python3 \
  /Users/changmin/projects/ugrp/outputs/review-360-c3af0783/audit.py
# 파일/공개 hash, r4 비교, raw 재현, 수치·schema·접근 경계 모두 PASS
```

환경은 기존 Python 3.13.5 / NumPy 2.4.4 / SciPy 1.17.1이다. 첫 감사 실행의 tuple/list 직렬화 비교 오류는 검토 helper에서 JSON 정규화로 수정한 뒤 재실행했다. PR 결함이 아니며 최초 실패 로그도 보존했다. 테스트 실패·skip·xfail은 없다.

같은 PR HEAD의 [CI run 37099450205](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37099450205)는 33/33 checks `SUCCESS`; `MERGEABLE`, `REVIEW_REQUIRED` 상태였다. 이는 검토자가 수행한 141개 로컬 검사와 구분한다. 이 작업은 리뷰 기록·push·댓글 인계이며 PR 병합은 수행하지 않는다.

로컬 근거는 `/Users/changmin/projects/ugrp/outputs/review-360-c3af0783/`에 보존했다. raw 원격 백업으로 표현하지 않는다.

| 근거 | SHA-256 |
|---|---|
| `audit.py` | `c0a74b04e82893512e36373fca375670f8a0492754df34efa33079f35d49f2d6` |
| `audit.json` / `audit.log` | `660a6974795adea828de001dcef7645940921903a083ff332da59c63efe2ac6d` |
| `tests.log` | `faaeac22b4e6ec9e6308408607be825189fbe19d450455cba3514607f12b34e1` |
| `tests.xml` | `a5098728f41d75701921b85b3b65f16d3a670fa78069c105cedb8c04c011b3aa` |
| `commitment-5966135675.json` | `317ed3462870222bfb868b54df527a5624433ecf15c8609d6594accb365dbcef` |
| `pr-state.json` | `1758c7ff335128f59d427617e8cb107693308f4ce924c481e50cf74edceb6ed4` |

새 실험 코호트를 만든 것이 아니라 기존 훈련 산출물의 독립 재현이므로 TensorBoard 중복 snapshot을 만들지 않았다. 기존 [r5 훈련·r4 기준선 링크](http://127.0.0.1:6006/?runFilter=%5E%281003-r5-yaw-training%7C1001-v89-consumer-r4-final%29%2F&smoothing=0#timeseries)를 유지한다. 사용자 지정 무렌더·프로세스 보존 범위에서 이번 검토는 dashboard/UI를 다시 확인하지 않았으며, 기존 기록의 UI 미완료 상태를 완료로 바꾸지 않는다.
