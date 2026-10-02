# PR #352 독립 검토

판정: **MERGE AFTER FIXES**. 사용자가 요구한 v88 전체 바이트 보존 조건을 충족하지 않고,
검증용 표기를 학습용으로 바꿔도 기존 검사에서 놓치는 반례가 있다.
검사한 진입점에서 지도·seed 제한이나 안전 차단의 우회는 발견하지 않았다.

- 후보: `d92efd8d7381a270ff266c01d7534dc8ab1c89f8` (`codex/calib-heldout-maps`).
- 원 검토 기준: `2523269857596ffdd1a8cda9814a6e92f399f1da`.
- 재개 시 최신 main 및 검토 브랜치 base: `11e9aa26954d3f1ce58c5116ddd14ec2b2738037`.
  추가된 37개 파일은 다른 검토 기록뿐이고 관련 소스·설정·테스트 차이는 없다. 후보와 최신 main의 merge-tree는 충돌 없이 구성된다.
- 검토 브랜치: `codex/review-352`. 구현 코드는 고치지 않았으며 검토 문서·증거·반례만 추가했다.
- `git fetch origin`, PR diff, `git archive origin/codex/calib-heldout-maps | tar -x -C <scratch>`로 검사했다.
  기본 체크아웃은 지침·Git 상태만 읽었고, 공용 outputs는 열거나 변경하지 않았다. 물리·렌더·모델 호출은 하지 않았다.

## 지적 사항 — 한 묶음

### R1 · P1: v88 plan/bundle 전체 바이트가 바뀐다

위치: `harness/zone_final_pair_contract.py:189-201,226`,
`scripts/run_final_pair_v3.py:167-171`, `tests/test_zone_final_pair_heldout.py:85-91`.

같은 두 문 지도, 세 calibration profile, seed 911, 같은 source 인자를 main과 후보에서
각각 계획하면 **bundle의 `source_sha256`와 plan의 `bundles_sha256`가 달라진다**.
기존 v88 bundle/3.1.0 workflow는 수정된 공유 파일 네 개와 새 heldout 모듈을 참조한다.
후보의 보존 테스트는 이 두 필드를 지우고 비교하므로 요청한 전체 바이트 보존을 증명하지 못한다.

무하중 bundle의 실제 JSON writer 바이트 SHA-256:

- main: `1f4685fe5240ab91bb1982b6db8e3ec63b5689959e9afc787b2c38f55aaf3d94`
- 후보: `0fdbfc1f7b7665960a51cdc3926757f24ca521928fd921de28b5fda95775a4e7`

**명령·시간표·비해시 동작 값이 바뀌었다는 지적은 아니다.** 이 값들은 동일하다.
소스 해시를 실제 변경에 맞춰 갱신한 것은 올바르지만, 사용자가 이번 검토에 명시한
"plan, bundle byte-for-byte unchanged"에는 예외가 허용되어 있지 않다.
v90 경로를 기존 v88의 실행 소스 의존성과 분리하여 이 조건을 충족하거나,
해시를 제외하는 비교 기준을 명시적으로 합의해야 한다. 과거 해시를 새 코드에 덮어씌우면 안 된다.

반례: `tests/test_review_352.py::test_v88_full_bytes_are_preserved` —
세 profile × plan/bundle **6 strict xfail**. 독립 main 생성값과 비교하며 해시 필드를 삭제하지 않는다.
상세: `review_352/preservation-review.json`.

### R2 · P2: HELD_OUT_VALIDATION 의미를 생산 코드 상수와 함께 바꾸면 검사가 통과한다

위치: `tests/test_zone_final_pair_heldout.py:42,116,129,187,215`.

테스트가 기대값을 독립적으로 고정하지 않고 `heldout.ROLE`과 비교한다.
임시 복사본에서 `harness/zone_final_pair_heldout.py`와 `configs/zone_final_pair_v90.json`의
`HELD_OUT_VALIDATION`만 `TRAINING`으로 바꾼 반례를 검사했다.
이 변이에서도 기존 heldout 테스트 **38개가 전부 통과**했다.
독립 리터럴 검사로 같은 변이를 실행하면 두 지도 모두 실패한다(**2 failed**).
등록 파일과 코드가 함께 바뀌면 이 의미 변경을 탐지해야 한다.

수정: 기대 역할을 독립 리터럴 `HELD_OUT_VALIDATION`으로 고정하고, plan/bundle/result와
두 boolean을 함께 검사해야 한다.

반례: `tests/test_review_352.py::test_existing_plan_regression_detects_training_label_drift`
— 기존 plan 테스트가 잘못된 표기를 허용하는 **1 strict xfail**.
독립 보완 검사 `test_literal_heldout_role_in_plan_bundle_and_fake_result`는
문자열·두 boolean을 고정하여 plan/bundle/fake result를 검사한다.

## 확인한 범위

| 요청 | 확인 결과 |
|---|---|
| v88 보존 | 세 명령 schedule 파일은 바이트 동일. plan/bundle은 위 두 해시 필드 외 동일. v88 registry·기존 workflow JSON 5개·지도/보정/clearance 계약과 학생 runtime/skill/provider 보존 확인. 전체 바이트 조건은 R1. |
| 추가 등록·번호 | v90 / `zone-final-pair-heldout-v90` 3.2.0 추가. 재개 시 main과 열린 PR 6개 모두 실제 원격 SHA와 `git grep RUNNABLE_ID` 및 harness/configs의 bundle 번호 조회. 다른 브랜치 최댓값 v89, v90 충돌 없음. |
| 지도·profile·seed | 두 held-out 지도 unloaded/911 허용. fine/loaded, 미등록 지도, 새 workflow의 두 문·학생 선택, seed 912 거부. weld/interlock/render/teacher 우회 flag 없음. |
| 표기·일정 | 현재 plan/bundle/사례 및 전체 result는 HELD_OUT_VALIDATION, training_eligible=false, teacher_only=true. v89에서 유래해 v88이 확장한 step+PRBS 및 자세 명령을 그대로 재사용. 370 SIM초, pose 0.05초 7,401개, RGB 0.2초 1,851개를 fake backend로 확인. v89 원본의 RGB 5초 주기를 승계한 것은 아님. |
| 안전·경계 | 0.30 m + 0.05 m buffer, 명령 전·substep 전후·표본 시점 interlock 유지. 두 지도에서 위험 시작점·NaN·위조된 saved PASS 거부. wall/NaN/누락 시 hold·HOST_ERROR·부분 자료 보존 확인. weld OFF, floor_light_v1, teacher 전용, 학생 경계 유지. |
| 인계 명령 | 두 명령의 bash 문법, acquire의 owner/branch/pid/예상 10분, workflow·seed·source SHA·output 인자와 실제 parser/plan 연결 통과. FINAL_SHA는 실행 worktree의 HEAD에서 얻고 실행기는 clean HEAD 일치를 검사한다. 실제 잠금/수집은 실행하지 않았다. |

무하중 schedule SHA-256:
`8e9a126cfdcbc5961cacac4165b76ac65da3310aa40b758f0590d999917813db`.
fine/loaded와 전체 원격 조회·기존 파일 해시는 `review_352/`에 저장했다.

## 테스트와 제한 복원 검사

중단 전 관련 회귀 123개와 workflow 17개 통과 로그를 보존했다.
archive의 추적 파일 9,063개를 후보 Git blob과 대조해 모두 동일함을 확인한 뒤,
중단된 표기 변이와 최종 후보 검사를 이어서 실행했다.

네 변이는 각각 seed 제한·새 workflow 범위·runtime interlock·위험 시작점 차단을 제거했고,
기존 검사가 모두 잡았다(각 2·3·6·3개 실패). 다섯 번째는 코드/등록 JSON의 검증용 표기를
함께 TRAINING으로 바꿨고 기존 검사 38개는 모두 통과했다. 독립 검사는 두 지도 모두 실패했다.
따라서 **다섯 변이 중 기존 검사 탐지 4개 / 미탐지 1개**다.

**중복 제거 합계: 193 passed, 7 strict xfail, 환경 제한 미확인 1개.**
재개한 후보/반례 검사는 53 passed + 7 strict xfail이다.
중단 전 123개 관련 회귀와 workflow 17개 통과를 합쳤고, 예전 반례/flag 재실행을 중복 합산하지 않았다.

최종 검사 수치·다섯 변이의 탐지 결과는 `review_352/verification.json`과
`review_352/mutations.json`을 따른다. 반례의 xfail은 성공 판정에 합산하지 않는다.
review 브랜치는 main 기반이므로 후보 모듈이 없는 곳에서는 이 반례 파일이 skip된다.
후보 SHA의 archive에 `tests/test_review_352.py`를 복사하여 실행해야 한다.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  -m pytest -q -rx -p no:cacheprovider tests/test_review_352.py
```

중단 전 Git 이력이 필요한 관련 테스트는 GIT_DIR을 지정해 재검사했다.
재개 검사는 GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR 상속을 제거하고,
공용 outputs의 파일 접근을 차단하는 audit hook을 사용했다.
첫 시도는 basetemp 부모 누락과 archive의 Git 이력 부재로 실패했으며, 실행 환경을 바로잡고
관련 테스트를 재실행했다. 기존 workflow의 `test_parent_exit_cleans_background_child`는
sandbox가 `ps`를 거부하여 미확인이다. 이 실패를 후보 코드 결함으로 취급하지 않는다.

## 범위와 마무리

판정은 코드 등록·재현성 검토에 한정한다. 현재 후보의 수집 완료·물리 안전·학생 성공·
MEASURED_SIM·criterion B 통과를 승인하지 않는다.
동결 criterion B가 v88만 받는 한계는 PR이 이미 공개한 후속 작업이며 이번 새 지적에 포함하지 않는다.
새 실험 결과가 없고 공용 outputs 접근이 금지되어 TensorBoard 작업을 하지 않았다.
UGRP 예외에 따라 Drive 작업도 하지 않았다. `.github/workflows`는 변경하지 않았다.
실제 PR 병합은 하지 않으며 이 검토는 위 후보 SHA에만 적용된다.

재개 종료: 후보 파일 9,063개가 원래 Git blob과 같은지 다시 확인한 뒤 이 작업의
`/private/tmp/ugrp-review-352.tCrih6` 추출 폴더와 내부 임시 자료를 삭제했다.
검토 문서·반례·로그는 검토 브랜치에 보존한다. 기본 체크아웃은 진행 중인 물리 수집과
기존 미커밋 변경 때문에 갱신하지 않았다.
