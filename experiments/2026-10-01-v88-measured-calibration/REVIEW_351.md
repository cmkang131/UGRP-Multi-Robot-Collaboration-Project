# PR #351 독립 재현 검토

**판정: MERGE AFTER FIXES.** 아래 R1–R4를 한 묶음으로 수정·검증한 뒤 다시 검토한다.

- 대상: `87aa99c337f700586f01039e40c6ad4dce410afa`, `codex/calib-measured-v88`.
- 기준 main / 리뷰 브랜치 시작점: `2523269857596ffdd1a8cda9814a6e92f399f1da`.
- 검토자: 독립 Codex. 작성자 검증 수치를 합산하지 않고 직접 재실행했다.
- 범위: Git 소스, `git archive` 임시 복사본, 합성 배열·파일, 오프라인 테스트만.
  실제 수집 raw 및 기본 체크아웃의 `outputs/`는 읽거나 쓰지 않았다.
  물리·렌더·모델 호출 0회. `.github/workflows` 변경 없음.

## 지적 사항 — 한 묶음

### R1 · P1 — 심볼릭 링크 수집 안에 출력 파일을 쓸 수 있음

`scripts/assemble_final_pair_calibration.py:120–125,254–258`,
`scripts/final_pair_calibration_io.py:75–76`.

출력 보호는 `raw_root` 한 경로와만 비교한다. 그러나 각
`calibration-*` 경로는 별도로 `resolve()`하여 외부 심볼릭 링크를 허용한다.
`view/calibration-unloaded -> actual/calibration-unloaded`를 만들고,
출력을 `actual/calibration-unloaded/new-output`으로 지정하면 검사를 통과한다.
실제 합성 수집으로 `PARTIAL`과 파일 3개가 **입력 수집 안에 생성**됐다.
마지막 파일 집합 검사는 이 쓰기보다 앞이라 입력 변경도 보고하지 않는다.

출력을 만들기 전에 실제로 해석된 모든 수집·case·입력 경로와 겹침을 검사하거나,
수집 경로의 외부 링크를 명시적으로 거부해야 한다. 새 이름이라는 조건만으로는 부족하다.
반례: `test_output_cannot_be_inside_a_symlinked_input_collection`.

### R2 · P1 — 하중 선별 뒤 사라진 deadband 식별 조건을 검사하지 않음

`scripts/final_pair_calibration_motion.py:62–67,93–104`,
`criterion_B_prime.json:120–123`.

B′는 실제 관측된 작은 정지 명령, ramp 안의 두 크기, 포화 크기를 요구한다.
코드는 양·음 부호와 horizon 존재, 최적화 rank·경계만 검사한다.
합성 loaded 자료에서 각 축의 `±0.006` step+coast를 하중 부적격으로 제거하면
남는 크기는 `[0.015, 0.025, 0.04]`다. 그래도 rank 13 적합과 PRBS 검증이 통과하고
`c0 ≈ 0.01`, `u1 ≈ 0.032`인 프로필을 승인한다.
명령표에 작은 크기가 있다는 사실은 유효 하중으로 그 응답을 관측했다는 증거가 아니다.

선별된 실제 fit 창에서 축별 필요한 크기·부호·정지/ramp/포화 응답을 확인해야 한다.
부족하면 해당 필드는 null과 구체적인 사유를 남겨야 한다.
반례: `test_loaded_deadband_requires_the_declared_four_amplitude_support`.

### R3 · P2 — NaN 접촉·beam 시각이 유효 하중 표본으로 통과

`scripts/final_pair_calibration_io.py:219–220`.

`abs(record_t - pose_t) > tolerance`만 검사하므로 `record_t=NaN`이면 거짓이다.
실제 JSON 파일의 `NaN`은 현재 Python JSON reader가 받아들이며,
`trajectory.jsonl` 또는 `contacts.jsonl`의 시각이 NaN인 표본도 `lifted`가 된다.
해시 일치는 유한 시각이나 동시 측정을 보증하지 않는다.

각 시각의 숫자형·유한성을 확인하고 잘못된 자료는 거부해야 한다.
반례: `test_loaded_evidence_requires_finite_sample_times`의 두 경우.

### R4 · P2 — 출력 재검사·잡음 분리의 중요한 회귀를 기존 테스트가 놓침

`tests/test_final_pair_calibration_assembly.py:201–216,367–402`,
`scripts/assemble_final_pair_calibration.py:237,254`,
`scripts/final_pair_calibration_motion.py:206`.

PR의 오염 검사는 `fit_shared()`의 평균과 별도 `evaluate()`를 검사한다.
오염된 PRBS로 `fit_profile()` 전체를 다시 돌려 잡음 선택의 불변성을 검사하지 않는다.
또 `Inputs.verify()` 자체 테스트는 있지만 출력 직전 호출이 빠져도 검출하지 못한다.
아래 되돌리기 M4·M5 모두 새 suite 전체 **134 passed**로 이를 확인했다.

리뷰 테스트에 PRBS 내부만 오염시키는 검사와 조립 도중 입력 바이트를 바꾸는 검사를
추가했다. 공유 경계 pose는 그대로 유지하며, 외부 오류를 xfail로 숨기지 않는다.
새 검사는 M4·M5를 각각 **1 failed, 오류 0**으로 검출했다. M5에서는 잡음이
`[0.01538, 0.00504, 0.01406]`에서 `[0.2643142, 0.0120341, 0.01406]`으로
커지면서 오염된 검증도 승인됐다. 원본에서는 잡음이 그대로이고 검증은 거부됐다.

## 요청한 여섯 항목의 확인 결과

| 항목 | 확인 결과와 한계 |
|---|---|
| 1. 동결 B/B′ | 실제 B 파일 SHA-256과 `parent_sha256`가 모두 `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`. `parent_text`는 JSON 전체 값이 같다. B′ 해시는 `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`. p95 ≤ 2, 2σ 포함률 ≥ 90%, horizon `[0.2,0.5,1,2,3,3.2]`, M1 relative/absolute noise 하한과 95% fit 포함률을 보존한다. 다만 추가 사항이 문자 그대로 두 개뿐은 아니다. JSON에 loaded deadband·선별, 최소 100창, camera/pair/spread 기준도 명시돼 있다. 수치 pass 기준을 완화한 것은 발견하지 않았으며 deadband 지지 조건 미집행은 R2다. |
| 2. 적합/검증 분리 | `fit_shared`·axis 후보·`minimum_noise`의 표적은 steps+coast만, 채점은 PRBS+coast다. 속도는 기록 시작 0에서 검증된 발행 명령으로 누적한다. 측정 속도·미래 pose·접촉·sim state를 predictor 입력으로 넣지 않는다. pose는 오프라인 표적/창의 시작 좌표계이며 접촉은 loaded 적격 선별에만 쓴다. 검증 창을 적합에 넣는 되돌리기는 기존 검사가 잡는다. 잡음 분리의 회귀 보호는 R4다. |
| 3. loaded 적격성 | beam box의 오프셋·회전을 반영한 바닥 높이 ≥ 1 cm, 네 finger 접촉, 외부 지지 없음, weld OFF를 검사한다. `selected_segments`가 실패 표본을 가로지르는 창을 제거한다. 요청한 loaded 명칭만으로 승인하지 않으며 weld는 수집 전체를 거부한다. NaN 시각은 R3, 선별 뒤 deadband 지원 부족은 R2다. |
| 4. 입력·출력 | 완료 기록이 없으면 내부 raw를 읽지 않는다. plan/bundle/result·명령·clock·manifest 파일 집합·각 hash와 출력 전 재검사를 확인했다. 승인되지 않은 필수 값은 null과 필드 경로/사유를 남기고 정상 PARTIAL CLI는 2를 반환한다. 해시 변경 등 무결성 오류는 출력 전 예외로 중단한다. 기존 경로/직접적인 부모·자식 출력은 거부하지만 링크를 통한 겹침은 R1이다. |
| 5. 현재 MEASURED_SIM 불가 | 정확하다. 세 acquisition 설계의 `MAP_ID`는 `zone_wide_two_doors_final_v3` 하나이며 B의 training map이다. 허용 held-out 두 지도와 다르고 rotate 후보·수집 선후관계 검증도 없다. frozen scorer와 assembler가 unloaded 승인을 null/거부로 유지한다. 이는 등록 코드 확인이며 실행 중인 실제 raw를 열어 확인한 결과가 아니다. |
| 6. 테스트 품질 | 기존 관련 5개 suite **283 passed**. 합성 반례 3종(시각 2조건)은 strict xfail로 남겼다. ImportError·프로브 종료 오류·timeout은 xfail 대상이 아니며, 아래 5개 되돌리기 결과를 별도 기록했다. |

## 직접 실행한 검증

기존 `.venv-sim-worker-mac`과 `.venv-dev`에는 SciPy가 없어 수집 오류가 났다.
환경을 설치·변경하지 않고 기존 `/opt/anaconda3/bin/python3`를 사용했다:
Python 3.13.5, NumPy 2.4.4, SciPy 1.17.1, pytest 8.3.4, Pillow 12.2.0.
BLAS/OMP thread는 1로 제한했다. Python 3.12 CI 결과를 대신하지 않는다.

archive에는 `.git`이 없으므로 `GIT_DIR`를 기존 리뷰 worktree의 Git metadata,
`GIT_WORK_TREE`를 archive로 지정했다. Git 조회는 기존 객체와 provenance만 읽으며
`GIT_OPTIONAL_LOCKS=0`을 사용했다. 테스트 실행 파일은 archive의 PR head다.

```sh
git fetch origin
git diff origin/main...87aa99c3
scratch_dir=$(mktemp -d /private/tmp/ugrp-review-351.XXXXXX)
git archive origin/codex/calib-measured-v88 | tar -x -C "$scratch_dir"
# 반드시 origin/codex/calib-measured-v88 == 위 고정 SHA인지 먼저 확인한다.
review_git_dir=$(git rev-parse --absolute-git-dir)
(
  cd "$scratch_dir"
  GIT_DIR="$review_git_dir" GIT_WORK_TREE="$scratch_dir" GIT_OPTIONAL_LOCKS=0 \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/anaconda3/bin/python3 -m pytest -q \
    tests/test_final_pair_calibration_assembly.py \
    tests/test_consumer_criterion_b.py tests/test_final_environment_unloaded_fit.py \
    tests/test_zone_final_pair_v3.py tests/test_zone_final_pair_review_fixes.py \
    --basetemp="$scratch_dir/test-tmp"
)
REVIEW_351_ROOT="$scratch_dir" /opt/anaconda3/bin/python3 -m pytest -q -rx \
  tests/test_review_351.py --basetemp="$scratch_dir/review-test-tmp"
rm -rf -- "$scratch_dir"
```

## 작은 되돌리기 검사

각 변경은 archive에서 하나씩 적용하고 실행 후 원본 바이트를 복원했다.
고정 기준 JSON·해시를 바꾸거나 테스트의 assertion을 약화하지 않았다.
`S`는 `tests/test_final_pair_calibration_assembly.py`다.

| ID | 변경 | 실행 범위 | 결과 |
|---|---|---|---|
| M1 | `fit_shared`의 `window_groups(split_data(data,'steps'),gate)`를 `window_groups(data,gate)`로 변경 | S의 `test_b_prime_motion_fit_and_heldout_independence` | 1 failed, 오류 0 — 검출 |
| M2 | `valid_contacts = True` | S의 `test_loaded_contact_height_and_weld_selection` | 1 failed, 오류 0 — 검출 |
| M3 | artifact SHA 비교 조건을 false로 변경 | S의 `test_raw_audit_rejects_tampering[bad_image_hash]` | 1 failed, 오류 0 — 검출 |
| M4 | assembler의 `inputs.verify()` 두 호출 제거 | S 전체 | 134 passed — 미검출 |
| M5 | `fit_profile`의 잡음 입력을 steps에서 전체 steps+PRBS로 변경 | S 전체 | 134 passed — 미검출 |

## 중단 후 완료 확인

이전 실행이 남긴 커밋·미추적 파일과 archive를 먼저 확인하고, 완료된 검사를 보존했다.
기존 JUnit 원본으로 관련 **283 passed**, 리뷰 **2 passed / 4 strict xfailed**를 확인했다.
네 xfail은 R1, R2, R3의 시각 두 조건이며 모두 실제 assertion 실패다.
M4·M5의 리뷰 검사 로그도 각각 assertion 실패를 확인했다. 작성자 수치는 합산하지 않았다.

재개 시 archive의 관련 소스·테스트·설정·지도와 B/B′ 기록 **2,365파일**의 Git blob을
`87aa99c3`과 대조해 불일치 0개를 확인했다. 모든 되돌리기 변경은 복원됐다.
완료된 테스트를 처음부터 다시 실행하지 않았다.

- [기계 판독 검증 기록](REVIEW_351_VALIDATION.json): 정확한 반례 출력, 변경 전후 검사 결과,
  소스/테스트 해시와 증거 파일 해시.
- [관련 suite JUnit](review-351-evidence/baseline.xml),
  [리뷰 JUnit](review-351-evidence/review-final.xml),
  [M4 리뷰 검사 실패](review-351-evidence/M4_omit_output_rechecks-review-control.txt),
  [M5 리뷰 검사 실패](review-351-evidence/M5_noise_includes_validation-review-control.txt).

임시 extraction `/private/tmp/ugrp-review-351.aOlx8W`는 필요한 작은 로그·반례 값을
위 기록으로 보존한 뒤 삭제하고 경로 부재를 확인했다. 합성 임시 자료만 정리했으며
실제 수집 자료는 접근하지 않았다.

알려진 CI durations coverage 89.9% 실패는 요청대로 검토 대상에서 제외했다.
새 실험 코호트가 없으며 `outputs/` 접근 금지 범위에 따라 TensorBoard를 시작하지 않았다.
이번 판정은 오프라인 조립 코드에 한정하며 물리 성능·MEASURED_SIM·학생 실행 승인이 아니다.
