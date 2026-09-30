# PR #299 네 번째 독립 검토 — 2026-10-01

**판정: MERGE AFTER FIXES.** 이전 13개 반례와 공개 acceptance 호환성은 고쳐졌다.
그러나 원 좌표가 실패를 뜻해도 저장된 거리 요약만 믿고 PASS를 주며, 실제 recorder가
남기는 시작 기록의 누락·시간 역전도 PASS로 받아들인다. 아래 P1 두 묶음을 고친 뒤
변경 범위를 다시 검증해야 한다. 이번 검토에서 구현·workflow·봉인·원본은 바꾸지 않았다.

| 대상 | 고정 값 |
|---|---|
| #299 검토 head | `58dc07e7607e86dd526bc0defe9374489f0ce931` |
| 수정 전 분류기 | `f32d5fd9afc54ca57ed49860843f54d6b5ca174d` |
| 실제 등록 recorder #292 | `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` |
| 등록 초안 #285 | `76e0f9ce793f8cbbff2349b2be2bbaa359250a42` |
| 공개 acceptance 소스 | `3c4fe30e2197518443b195392212b0341507ac59` |
| 이전 검토 | `origin/codex/review-299c:experiments/2026-09-30-pair-v6h-carry/REVIEW_299c_astra.md` |
| 조정 결정·작성자 답변 | [D1–D5 반영 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/299#issuecomment-5914186130) |
| 리뷰 브랜치 기준 main | `6f766ecaa590b21d3d4b8763ee88a8c2eea4b67d` |

이하 `C`는 `experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py`,
`A`는 같은 디렉터리의 `recorder_v4c6b.py`이며 줄 번호는 위 head 기준이다.
물리·렌더·모델 실행 없이 `git archive`로 푼 사본에서 검사했다. 새 worktree와
호스트 잠금은 만들지 않았다(#328). blinded confirmatory raw는 열거·조회하지 않았다.

**P1 / 299d-R1 — 원 좌표와 거리 요약이 모순돼도 PASS (`C:808–826`, `A:57–62`).**

현재 source→derived 대조는 끝 시각, lift, tilt, jaws만 확인한다. 그런데 등록 producer의
`harness/pair_chain_probe.py:191–226`은 원 `leg_start/leg_end`의 `gt.beam_xyz`와
case의 정적 route로 `end_error_m`과 `leg_error_m`도 계산한다. 이 두 값은 각각
100 mm 통과 관문인데, 소비자는 이 대응을 확인하지 않는다.

공개 CI projection `case_01.json`의 복사본(S01/911)에만 아래 변형을 가했다.
row·result.row·시각·집게·기울기·PF·등록 식별자는 그대로다. 두 로봇의 해당 원 좌표
x에 1 m를 더했다. `math.dist`로 독립 재계산했고 producer 함수의 계산식도 대조했다.

| 변형 | 원 좌표가 뜻하는 끝점 오차 | 원 좌표가 뜻하는 leg 길이 오차 | 실제 판정 |
|---|---:|---:|---|
| 원본 양성 대조 | 0.050784 m | 0.002679 m | PASS_CLEAN |
| L1 끝 원 좌표만 이동 | **0.950487 m** | **1.002557 m** | **PASS_CLEAN**, issues `[]` |
| L1 시작 원 좌표만 이동 | 0.050784 m | **0.701158 m** | **PASS_CLEAN**, issues `[]` |

이는 서로 다른 시각의 비동기 관측을 같은 표본으로 비교한 것이 아니다. 기존 source
시각과 그 source에서 계산되어야 할 요약값 사이의 모순이다. 기록 후 해시를 우회하거나
원본을 수정한 실험도 아니다. 별도 메모리/합성 파일에서 처음부터 모순된 레코드를 입력했다.

등록 schema를 통과하는 합성 단일 실행에서도 재현했다. 기존 `registered_fixture`의
정상 1개 PASS/71개 누락을 확인한 다음 같은 원 좌표 변형만 적용하면,
`analyse(..., sealed_manifest=...)`가 여전히 **`pass_placements=1`**로 센다.
나머지 71개가 누락이므로 이 재현의 전체 verdict는 NOT_EVALUABLE이다.
전체 60개 코호트 PASS를 재현했다고 주장하지 않는다.

수정 조건: producer가 실제 저장한 시작·끝 GT, 정적 route와 거리 요약의 관계를
검사한다. 서로 모순되거나 필수 원 수치가 없는 경우 null/INVALID로 남기고,
확인된 하드 위반은 계속 우선한다. 원 raw를 고치거나 새로운 관측을 만들지 않는다.

재현: `test_source_distance_failure_cannot_be_hidden_by_pass_summary` 2개,
`test_registered_reader_does_not_count_source_distance_contradiction` 1개 strict xfail.

**P1 / 299d-R2 — 시작 증거와 원 시각 순서를 검사하지 않는다 (`A:57–62`, `C:804–826,840–845`).**

producer는 두 로봇 모두의 start/end가 있어야 `recorded=True`로 만든다
(`harness/pair_chain_probe.py:201–208`). 어댑터는 end만 필수화하고, classifier는
요약 leg의 시각만 검증한다. 따라서 다음 7개가 모두 **PASS_CLEAN / issues `[]`**다.

- r1 또는 r2의 L0/L1 `chain_raw.<robot>.leg_start.<leg>` 하나 삭제: **4개**.
  같은 원 기록을 producer의 `chain_legs`에 넣으면 해당 leg는 `recorded=False`다.
- L1 두 로봇의 원 start를 **61.3 s**, 원 end를 기존 **60.3 s**로 둠: **1개**.
  원 GT의 t도 source 시각과 일치시키며, 저장된 정상 start 요약 **35.9 s**만 남겨 둔다.
- 더 이른 로봇의 L1 원 end/GT 시각을 **−1 s**로 바꿈: **1개**.
  다른 로봇의 정상 end가 max이므로 현재 검사를 통과한다.
- `gt_at_stop.t`를 마지막 trace보다 **100 s 뒤**로 바꿈: **1개**.
  contact 요약 코드는 유한한 수인지만 확인하고 실행 종료와의 순서를 확인하지 않는다.

수정 조건: 실제 producer의 recorded 조건에 맞춰 양쪽 시작·끝 증거와 derived
시각의 연결을 검사하고, 저장된 경계들이 음수가 아니며 해당 실행 창·순서와 맞는지
확인한다. 정상 비동기 로봇 관측은 허용해야 한다. dict/leg 배열의 단순 순서 변경은
시각 역전과 다르다. 추가 양성 대조에서 이 두 컨테이너 순서 변경은 정상 PASS다.

재현: `test_recorded_leg_requires_the_producers_start_witnesses` 4개,
`test_reordered_source_boundaries_cannot_pass` 3개 strict xfail.

**이전 R1–R5와 요청한 재현 검사**

| 항목 | 독립 확인 |
|---|---|
| 299c-R1 / 실제 recorder | 공개 11건 전체 원본과 CI projection의 판정 객체 일치. lag-on **10 PASS_CLEAN**, lag-off sanity **1 FAIL**. producer 파일은 acceptance와 #292에서 바이트 동일 |
| 없는 계측값 | 접촉 총 표본 수·주기·수집 시작/끝·기록 시점 receipt는 `not_recorded`. 관측 trace의 t/길이와 구분. raw 쓰기 없음 |
| 299c-R2 / HOST | `result.host_error`, termination 부재 및 cleanup 전 정상 termination, ENOSPC·미해결 HOST·주 시드 누락은 **class=null**. 실패로 대치하거나 분모에서 빼지 않고 완료 주장을 막음 |
| 두 PREREG_DRAFT | #285 `167–168,191–193`, #292 `148–150`의 HOST 미분류·같은 배치/시드 1회 재실행·원 기록 보존 규칙과 대조. 실제 blinded 봉인은 읽지 않음 |
| 299c-R3 / 완료 실패 | rest_release·regrasp·restaging 3개 및 L1 중 HOST로 끝나도 이미 도달한 handover 실패 3개가 보존됨. 원/재시도·보조 시드·거부 시도의 하드 위반 회귀 유지 |
| 299c-R4 / 모순 | 기존 result HOST 사본과 같은 시각 lift/jaws/tilt 반례는 차단. **거리 요약까지의 일반성은 새 R1에서 미완** |
| 299c-R5 / coverage | teacher 범위와 coverage의 음수/역전/count/period/gap 모순은 차단. **별도 source 경계의 일반성은 새 R2에서 미완** |
| 이전 strict-xfail 13건 | 현 코드 **13/13 통과**, 수정 전 **13/13 AssertionError**. R1의 4개는 D1에 따라 “없는 필드를 요구”에서 “실제 producer 형식 수용”으로 바뀐 소비자 검사임 |
| mutation | 작성자 guard 삭제 검사 **7/7 검출**도 별도로 재실행. 이전 코드 비교와 구분 |
| 공개 308건 | 완료 16코호트 **308/308 기존 분류 일치**, cA/cB 각각 **24/24**. 부분 tX1은 별도 14건: PASS 12, HOST 미분류 2 |
| 봉인·고정 자료 | 공개 등록/배치/설정 **17파일**이 f32d5fd9와 58dc07e7에서 바이트 동일. 관련 source/pinning 테스트 **56 passed** |
| 정상 대조·순서 | 원본, robot dict 순서, leg 목록 순서는 PASS. trace 시각 순서 변경은 INVALID. 원 GT 16°는 기존처럼 FAIL_HARD_LIMIT |

이전 코드 비교는 classifier 본문을 `git show f32d5fd9:...`로 불러 동일한 증거를
넣었다. 새 `recorder_context` 인수만 무시하는 API 호환 wrapper를 사용했다.
오류/TypeError를 결함 검출로 세지 않았고 **13개 모두 판정 기대값의 AssertionError**다.
의존 분석기와 `pair_chain_probe.py`는 두 SHA 사이에 변화가 없다.

**실행 결과와 재현**

기존 관련 검사 **442개**를 최종 확인했다(기존 묶음 386 + source/pinning 56).
10,000개 생성 사례도 포함한다. 첫 archive 실행은 Git 메타데이터가 없어
**426 passed / 16 failed**였다. 실패는 모두 역사적 Git blob 조회였고, 파일을 고치지
않고 Git 읽기 환경을 연결한 재실행에서 해당 두 파일 **56 passed**를 확인했다.
그 환경의 main과 검토 SHA에서 source/pinning 검사가 쓰는 공개 등록·설정 16파일의
마지막 변경 commit도 동일하다(미병합 배치 초안은 이 Git-history 비교에서 제외).
첫 실패 로그를 숨기거나 전체 묶음이 한 번에 통과했다고 쓰지 않는다.

새 리뷰 파일은 **4 passed / 10 xfailed**이며 `--runxfail -m xfail` 실행은
**10 failed / 4 deselected**, 전부 위 반례의 AssertionError다.
[검증 기록](analysis/review_299d_validation/)에 요약·해시·mutation 재현기를,
`/Users/changmin/projects/ugrp/outputs/review-299d-58dc07e7/`에 전체 원 로그와
308건의 상세 재분류를 보존했다. 생성된 큰 결과를 중복 커밋하지 않았다.

```sh
# 리뷰 파일을 PR archive의 tests/에 복사한 뒤, archive에서 실행한다.
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_classify_review_299.py \
  tests/test_classify_review_299b.py tests/test_classify_review_299c.py \
  tests/test_v6h_recorder_contract.py tests/test_v6h_classifier_properties.py \
  tests/test_ci_sharding.py tests/test_chain_analysis_hard_limit.py \
  tests/test_pair_chain_probe.py tests/test_b_v6h_gain.py tests/test_classify_review_299d.py
"$PY" -m pytest -q -p no:cacheprovider --runxfail -m xfail tests/test_classify_review_299d.py
GIT_DIR=/Users/changmin/projects/ugrp/.git GIT_WORK_TREE="$PWD" \
  "$PY" -m pytest -q -p no:cacheprovider \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
# 새 출력 경로를 지정한다. 원 raw 안에 출력하지 않는다.
GIT_DIR=/Users/changmin/projects/ugrp/.git "$PY" \
  experiments/2026-09-30-pair-v6h-carry/analysis/verify_recorder_contract.py --output /tmp/299d-acceptance-NEW.json
"$PY" experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py --output /tmp/299d-published-NEW
"$PY" experiments/2026-09-30-pair-v6h-carry/analysis/check_299c_mutations.py --output /tmp/299d-guards-NEW.json
# 리뷰 브랜치의 재현기; --tree는 PR archive, --repo는 Git history를 가진 경로다.
"$PY" /Users/changmin/projects/ugrp-wt/review-299d/experiments/2026-09-30-pair-v6h-carry/analysis/review_299d_validation/check_pre_fix.py \
  --tree "$PWD" --repo /Users/changmin/projects/ugrp-wt/review-299d --output /tmp/299d-prefix-NEW.json
```

공개 acceptance의 실제 읽은 **36파일 전후 SHA-256**과 마지막 재확인 값이 같다.
후보 소스·기존 검사·fixture 파일도 실행 뒤 Git의 `58dc07e7` 바이트와 일치한다.
확인 당시 #299의 head는 그대로이며 GitHub check 33개가 모두 SUCCESS다.
CI 성공은 위 새 반례를 해결했다는 뜻이 아니다.

새 실험·확증 코호트·물리 성공을 만들거나 회수한 작업이 아니므로 TensorBoard 재변환과
viewer 실행은 하지 않았다. 기존 snapshot을 보존했다. Google Drive 작업도 없다.
리뷰 문서·테스트·작은 검증 기록만 commit/push하며 raw의 원격 백업을 주장하지 않는다.
리뷰 push는 `[skip ci]`를 사용하며, 요청대로 `codex/review-299d`만 push하고
#299에 한국어 코멘트 한 번으로 이 묶음을 전달한다. PR 병합·main 갱신은 이번 범위가 아니다.
