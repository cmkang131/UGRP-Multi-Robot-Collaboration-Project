# PR #346 독립 검토

**판정: MERGE AFTER FIXES.** 수치 재현과 학생 입력 경계는 확인했지만, criterion B 검증기가 부적격·불완전한 자료를 `HELD_OUT`, 축별 `pass=true`로 표시한다. 아래 지적은 한 묶음이다. r4의 실제 held-out 검증이나 로봇 실행 승인은 아니다.

- 검토 대상: `65ce28cf7da3c8c33de97a03b19cd1665b45f831`, `origin/codex/calib-fit-v87`.
- 검토 브랜치: `codex/review-346`, 시작 main `2c45b137c480eecff3dac871277cf48914dd5cf4`.
- 원본: `/Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001`, `/Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001/calibration-unloaded`.
- `git archive` 사본에서 실행했다. 물리·렌더·모델 실행 0회. 제어기·`.github/workflows` 변경 없음. 원본은 읽기만 했다.

**수정할 사항**

1. **P1 / R1 — 수집 시점이 확인되지 않아도 held-out 통과를 낸다.**
   `scripts/validate_consumer_criterion_b.py:230–249`.
   B는 새 수집이 고정 이후에 이루어졌다는 조건을 요구한다. 현재 적격성 검사는 v89 여부, 이미 본 pose 바이트, 지도 이름뿐이다. 수집 시점·B 고정과 연결된 확인 기록이 전혀 없고 `source_sha`도 존재 여부를 확인하지 않은 40자리 문자열인 합성 raw가 `HELD_OUT`, `forward=true`가 된다. README:95와 결과의 주의 문구는 이 조건을 수동 확인해야 한다고 설명하지만 판정을 막지는 않는다.
   수정 조건: 수집 확인 기록을 B·후보·raw 해시와 연결해 검증하거나, 확인 전에는 수치 진단만 내고 축별 검증 판정은 null로 남긴다. 소스 커밋 날짜만으로 수집 시점을 대신하지 않는다.
   반례: `tests/test_review_346.py::test_unverified_acquisition_chronology_cannot_validate` (strict xfail 1개).

2. **P1 / R2 — 수집 조건의 모순과 실패한 상위 수집을 놓친다.**
   `scripts/validate_consumer_criterion_b.py:90–107`, `:114–128`, `:157–164`.
   bundle은 unloaded/corridor인데 (a) `result.check=calibration-loaded`, (b) `result.case.map_id=zone_wide_two_doors_final_v3`, (c) pose의 `requested_check=calibration-loaded`인 세 경우 모두 거부하지 않는다. 이 필드는 실제 v88 수집기 `b7bc885a`가 쓰는 기록이다. 또 상위 `result.json`이 `HOST_ERROR`, `source_unchanged=false`여도 `--raw`에 하위 case 폴더를 주면 상위 검사를 건너뛴다. 네 경우 모두 수치가 맞는 합성 자료에서 `HELD_OUT`, `forward=true`를 확인했다.
   수정 조건: bundle·measurement·case result·pose의 수집 조건과 지도 신원을 대조하고, case 경로를 받더라도 해당 수집의 완료·소스 고정 실패를 우회하지 못하게 한다. 모순된 raw는 B의 규정대로 오류여야 한다.
   반례: `test_contradictory_raw_identity_is_rejected` 3개, `test_case_path_cannot_bypass_failed_collection_root` 1개 (모두 strict xfail).

3. **P2 / R3 — 누락된 정지 명령을 발행된 0 명령으로 채운다.**
   `scripts/validate_consumer_criterion_b.py:129–143`.
   `issued`를 0으로 초기화하고 값만 비교하므로, 일정에 명시된 coast의 0 명령 90개를 로그에서 없애도 통과한다. 초기 hold는 그대로 남긴 반례다. 결과는 다시 `forward=true`다. lease 만료로 같은 평균 궤적을 계산할 수 있다는 사실은 명령 기록이 완전하다는 증거가 아니다.
   수정 조건: 실제 일정이 발행을 요구하는 tick 집합과 `seen`을 비교한다. 일정 밖의 초기 hold까지 명령을 요구할 필요는 없다.
   반례: `test_missing_scheduled_zero_commands_are_not_invented` (strict xfail 1개).

4. **P2 / R4 — 최상위 완료 기록은 입력 해시 재검사에서 빠진다.**
   `scripts/validate_consumer_criterion_b.py:158–164`, `:260–264`.
   정상 상위 `result.json`을 읽은 뒤 `HOST_ERROR/source_unchanged=false`로 바꿔도 `verify_inputs()`가 성공한다. 이 파일은 적격성에 사용되지만 `inputs`에 저장되지 않는다. 따라서 README:92–95의 실행 후 입력 재확인이 수집 완료 기록에는 적용되지 않는다.
   수정 조건: 상위 결과와 적격성에 사용한 모든 기록을 보고서의 입력 manifest 및 전후 해시 대조에 포함한다.
   반례: `test_collection_completion_change_is_detected` (strict xfail 1개).

**재현된 값과 검증 범위**

해시 manifest의 5,869항목을 모두 대조했다. 원본 고유 파일은 v87 5,465개 + v89 162개 = **5,627개**이며 검토 후에도 크기·SHA-256 불일치 0개다. 과거 소스 항목은 각각 r1 `a5cc1402`, r2 `8feab578`, r3 `bedcc99d`, r4 `6ed94e4c` 또는 명시된 git blob과 비교했다. main 통합 뒤 달라진 CI 목록을 과거 실행 소스로 취급하지 않았다.

- **r1:** raw 재적합의 `fit_report.json`, `calibration_partial.json`, `input_manifest.tsv`가 원본과 바이트 단위로 같다. 별도 계산으로 지도 3개 × 자세 21개의 `Rbᵀ(pc−pb)`, `RbᵀRc·diag(1,−1,−1)` 및 잔차를 대조했다. 모든 회전은 SO(3), origin/회전 행렬 값 차이는 0이다. 독립 회전 잔차 계산의 최대 차이는 부동소수점 연산 순서에 따른 `5.01e-7°`다.
- **r3:** 단순 모델을 계단 raw에서 다시 적합했다. 전진 `(gain, run tau, stop tau)=(1.2417454479, 0.8358115892, 0.0643915571)`, 측면 `(0.8547672927, 0.8309730366, 0.0619408269)`가 일치한다. 저장된 단순/회색상자 모델·잡음 파라미터로 2축 × 2모델 × 2분할 × 6 horizon의 오차·coverage·NEES 표를 다시 계산했다. 비교한 수치 7,440개 차이 0이다. 회색상자 파라미터 자체의 전체 재탐색은 하지 않았다.
- **r4:** v89 raw만으로 평균과 최소 잡음을 다시 적합했다. 후보·훈련 표의 수치 710개가 정확히 같다. 전진 `(1.2371430924, 0.7977909567, 0.0889785569)`, 측면 `(0.8509603197, 0.7877102182, 0.0884619201)`. `noise_abs=[0.01538, 0.012767691858458299, 0.01406]`, 최저 2σ 훈련 포함률 `1465/1542=95.006485%`. 새로운 검증 자료는 사용하지 않았다.

| r3, PRBS 3.2초, 각각 297창 | 위치 오차 p95 (mm) | 구동 성분 2σ 포함률 | 구동 성분 평균 NEES |
|---|---:|---:|---:|
| 전진 단순 | 6.794519 | 100% | 0.382646 |
| 전진 회색상자 | 0.370411 | 31.9865% | 17.298767 |
| 측면 단순 | 5.501298 | 100% | 0.277167 |
| 측면 회색상자 | 0.433037 | 61.2795% | 4.617861 |

3.2초 성분별 수치, 전체 분할의 대조 요약과 합성 반례 관측은 [REVIEW_346_VERIFICATION.json](REVIEW_346_VERIFICATION.json)에 기록했다. 위 표는 이미 본 자료의 재계산이며 새로운 확증 결과가 아니다.

**기준·입력 경계·소비자**

- A SHA-256 `49b7ffbbc07425dda3d2f2410c480ea6ee1315a1c831f97e75efc6989164391c`, B SHA-256 `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`, 후보 SHA-256 `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071`을 확인했다. A와 r1–r3 산출물은 이후 커밋에서도 바이트가 보존된다. A 실패에 B를 적용해 재판정하지 않았다.
- **선고정 시점의 증거 한계:** A는 r3 결과와 함께 `bedcc99d`(2026-10-01 07:02:41 KST)에 처음 커밋됐다. 실행 기반 `8feab578`에는 A 파일이 없다. 코드가 A를 먼저 읽고 해시를 출력한 뒤 적합하는 순서는 확인했지만, 독립적으로 시간 고정된 선행 커밋/영수증으로 “적합 전 고정”을 입증하지는 못했다. 이를 확인된 사전 등록으로 확대하지 않는다.
- B는 r3 뒤 `6ed94e4c`(07:29:54 KST)에 처음 커밋됐고 해당 PR의 r4 입력은 기존 v89뿐이다. 기록상 새 held-out 판정은 전부 null이다. 향후 실제 수집의 선후관계까지 증명하는 기록은 아직 없으며 R1을 고쳐야 한다. 지정 v88 `b7bc885a`는 turn 자극을 포함하지만 두 문 지도만 허용하므로 그대로는 B의 다른 지도 조건을 충족하지 못한다.
- 수치 게이트는 `p95(abs(error)/sigma) <= 2`의 NumPy linear percentile, 2σ 포함률 `>=0.90`, 0.2/0.5/1/2/3/3.2초의 각 성분·분할 검사와 맞는다. 경계값·각 성분의 실패·90%/88.89% 포함률·정보용 NEES·미검증 축 null을 합성 검사했다. 실제 v89 CLI는 `TRAINING_SMOKE`, 세 축 null, 종료 코드 2다.
- `eval_only`는 오프라인 적합·잔차 표적에만 사용된다. 숨은 예측 상태는 발행 명령으로만 누적된다. 후보를 읽는 학생 factory 연결이 없으며 `git diff origin/main...65ce28cf -- harness sim .github/workflows`는 비어 있다.
- `harness/owncam_localizer.py:270–330`의 필드와 식을 대조했다. r4는 끝 속도 Euler 적분, 스칼라 stop tau, `sigma=noise_rel*abs(v)+noise_abs`, tick당 분산 `sigma²·dt²`와 맞는다. 축별 특이 gain·혼합축 미지원·scale 제외·선형화 과정 잡음이라는 README의 제한도 맞다. r3의 연속시간 정확 적분과 r4 소비자 식을 혼동하지 않는다.
- P03/최종 환경 로더의 PARTIAL/CANDIDATE 거부 검사가 통과했다. 정확히는 **r1의 `params.motion` 전체가 null인 것은 아니다**. 전진·측면 gain과 모든 stop tau는 null이고 회전 탐색치가 남은 부분 객체다. 상태는 PARTIAL이며 사용이 차단된다. r2/r3/r4의 `params.motion`은 null이다.
- README는 A 실패, B의 사후 결정, r4 미검증, 훈련과 새 held-out의 구분, loaded/fine/PF/실물 성공 미검증을 명확히 쓴다. 다만 검증기의 완료·신원·입력 재확인 주장은 R1–R4 수정이 필요하다.

**실행 기록**

관련 기존 오프라인 검사 **286 passed**, 새 검토 검사 **10 passed / 7 strict xfailed**, unexpected failure·skip 0개다. 합계 **296 passed / 7 strict xfailed**이며 xfail은 해결되지 않은 결함이다. 같은 대상 SHA의 GitHub CI 33개 작업 성공도 조회했지만 이 반례의 해결 근거는 아니다.

기존 검사 파일: `test_consumer_criterion_b.py`, `test_unloaded_consumer.py`, `test_unloaded_hammerstein.py`, `test_final_environment_unloaded_fit.py`, `test_zone_final_environment_floor_light.py`, `test_zone_final_environment_runnable.py`, `test_vision_pose_source.py`, `test_owncam_localizer.py`, `test_ci_sharding.py`.

검토 반례 재현(아카이브에는 `.git`이 없으므로 기존 저장소의 git 객체만 읽도록 지정):

```sh
review_root=$(mktemp -d /private/tmp/review346.XXXXXX)
git archive 65ce28cf7da3c8c33de97a03b19cd1665b45f831 | tar -x -C "$review_root"
UGRP_REVIEW_346_ROOT="$review_root" GIT_DIR=/Users/changmin/projects/ugrp/.git \
  PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python3 -m pytest \
  -q -p no:cacheprovider tests/test_review_346.py -rx
```

원본 재계산 코드·요약·JUnit·반례 관측은 로컬 `/Users/changmin/projects/ugrp/outputs/review-346-65ce28cf/`에 보존한다. 코드 `recompute.py`는 `REVIEW_346_TARGET`으로 위 아카이브를 받아 읽는다. 원본 raw의 원격 백업을 뜻하지 않는다. 기존 [TensorBoard r3/r4](http://127.0.0.1:6006/?runFilter=%5E1001-v89-consumer-%28r3%7Cr4-final%29%2F#timeseries)는 참고 링크이며 이번 검토에서 화면 확인·새 snapshot 생성은 하지 않았다. 재계산을 새 실험으로 중복 등록하지 않았다.

이번 검토가 만든 `/private/tmp/review346.uTxPwi` 아카이브와 그 안의 합성 raw는 종료 전에 삭제·부재 확인했다. 원본 수집 자료는 보존했다. 검토 기록만 커밋·push하고 PR #346에 한 번 보고하며, 이 판정으로 PR을 병합하지 않는다.
