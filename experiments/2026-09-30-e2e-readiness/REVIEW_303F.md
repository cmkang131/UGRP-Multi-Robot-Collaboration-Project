# PR #303 여섯 번째 독립 수정 검증

2026-10-01 KST, 독립 검토자 Codex, `codex/review-303f`.
대상은 `567038c2563d3d6fb4c653ebc7f797b7e35fe79f` →
`3782887538db62c4673fe21908d252a3a7616da6`이며, 기준 지적은
`f80a8f98a84d9d308e48ebca42994d489f121a80`의 `REVIEW_303E.md` E303-1 한 건이다.
중간 main 병합 `746b040b`와 실제 수정 `37828875`를 구분해 확인했다.

**판정: MERGE AFTER FIXES.** E303-1의 원본 귀속 오류는 일반적인 키 검사로 수정됐다.
새 생산 코드에서 같은 성공 부풀림은 찾지 못했다. 다만 이번 요청의 생성형 검사 변이
검출 조건을 충족하지 못하고, 새 TensorBoard 검사의 import 때문에 실제 CI가 실패한다.
아래 두 P2를 한 묶음으로 전달한다. 이미 합의한 이벤트 재생 설계·고정 분모·고아 처리·
attempt 선택을 다시 문제 삼지 않는다. 이 문서는 병합 실행이나 물리 인수가 아니다.

## E303-1 수정 확인

- `harness/zone_evidence_key.py:8–29`는 여섯 열의 정확한 키·타입과 trial 범위를 검사한다.
  `harness/zone_referee_replay.py:49–60`은 생성 시 키를 복사하고 다른 키로 이어 쓰는 것을
  거절한다. `:69–82`는 admission·manifest 출처 키·각 이벤트 키의 일치를 확인한다.
- `scripts/tensorboard_tools/zone_study.py:145–155`가 정확한 파일 경로의 manifest 항목과
  시행 키를 대조하고, `scripts/zone_study_evidence_contract.py:206–213`이 원본 envelope와
  identity를 검사한 뒤 재생한다. 정상 성공은 이 모든 경계를 지나야 한다.
- `scripts/zone_study_evidence_cohort.py:43–107`은 정책·재생 검사 전에 파일·manifest·
  중첩 원본·이벤트에서 소유 선언을 각각 읽는다. `:117–137`은 실패 후에도 그 집합을
  보존한다. 읽을 수 있는 A 원본을 폴더명 B에만 귀속하지 않으며, 선언 A/B가 충돌하면
  둘 다 INVALID다. 출처 불명 전체 거절은 기존 보수적 선택으로 유지된다.
- 봉인은 기존 키를 덮어쓰지 않는다(`scripts/zone_study_evidence_contract.py:133–158`).
  특정 `run-0`/`run-1` 문자열에 맞춘 패치가 아니다.

원 검토 파일의 **assertion 16/16이 AST 기준 동일**하다. 바뀐 부분은 생성 시 키 인자,
설명과 기존 xfail 제거다. 원래 8개 반례는 정상 후보에서 통과한다.
독립적으로 추가한 8개 검사는 손상 전 세 원본이 각각 검증되는지부터 확인하고,
손상 후 정책/profile/events/summary에 해당하는 **정확한 거절 이유**와 `affected_keys=[A]`,
**A INVALID / B VALID, 성공 0/2**를 확인한다. 모두 실패시키는 가짜 수정도 배제한다.
원본·이벤트·manifest·identity 충돌 8개는 A/B만 INVALID, 제3 시행은 VALID로 남는다.

## F303-1 · P2 — 생성형 검사가 원래 귀속 오류를 되살리는 변이를 놓침

위치: `tests/test_zone_referee_ownership.py:144–205`, 특히 `:158–164`, `:184–195`.

제출된 `rejected_owner` 변이를 그대로 적용했다. `collect()`의 거절 처리에서 소유 선언
집합 대신 `source.name`으로 affected를 다시 고르는 **한 줄 변이**다. 생산 파일은
수정하지 않고 함수만 메모리에서 교체했다.

| 같은 변이에 실행한 검사 | 결과 |
|---|---|
| 원 E303 반례 8개 | **8 failed / 0 errors**, 모두 성공 **0/2 → 1/2** assertion 실패 |
| 새 원본 변환 property만 단독 실행 | **3 passed / 0 failures / 0 errors**, 생성 사례 **192개 모두 생존** |

즉 실제 옛 결함을 복원하는 유효한 변이인데, 새 property 자체는 이를 잡지 못한다.
현재 move는 파일/이벤트 행만 옮기며 거절된 사본 디렉터리의 basename을 다른 admission
run ID로 바꾸지 않는다. duplicate도 기존 거절 원본을 유지하므로 그 원본의 거절이
사라지는 경우를 충분히 만들지 않는다. 선언된 기존 INVALID 유지 assertion이 있어도
생성 입력이 해당 반례에 도달하지 않는다.

수정 조건: A 성공·B 비성공·A 거절 사본을 포함한 baseline에서, 사본의 키/내용은 그대로
두고 그 디렉터리를 B 이름으로 이동하는 변환을 생성기에 포함한다. 정상 후보에서는
성공 비증가와 A INVALID를 유지하고, 위 한 줄 변이에서는 **property 자체가 assertion으로
실패**해야 한다. 직접 예시 8개의 변이 검출을 생성형 검사의 검출로 대신 세지 않는다.

`event_key` 비교만 지운 추가 변이에서도 property는 192개 모두 통과했다. 상위 소유 선언
검사가 중복 방어하므로 이 결과만으로 별도 생산 결함을 주장하지 않는다. 결정적인 음성
대조는 E303-1을 실제로 복원하는 위 `rejected_owner` 변이다.

## F303-2 · P2 — 새 TensorBoard CI 검사가 불필요하게 OpenCV를 요구함

위치: `tests/test_tensorboard_export.py:35–39` → `tests/test_review_303e.py:19` →
`tests/test_zone_referee_replay.py:17`.

기존 optional job은 `requirements-observability.txt`와 pytest만 설치한다. 새 검사가
review 모듈의 `claims`를 가져오고, 그 모듈이 다시 통합 실행기용 테스트를 가져오면서
`harness/map_goto.py:21`의 `import cv2`에 도달한다. 원본 JSON을 검사하는 새 테스트가
카메라 패키지 설치에 의존하게 된 회귀다.

정확한 후보 SHA의 [CI #36752618220](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36752618220)은
**32 SUCCESS / 1 FAILURE**이며, `tensorboard-export`가
`test_p06_rejected_owners_with_real_tensorboard`에서 `ModuleNotFoundError: No module named 'cv2'`로
실패했다(job 내부 **95 passed / 1 failed**). 별도 로컬 프로세스에서 `cv2` import를 차단해
같은 경로의 **1 failed / 0 errors**를 재현했다. 설치된 Mac 환경에서의 통과로 이 실패를
덮지 않는다.

수정 조건: 필요한 순수 fixture/claims를 순수 보조 모듈로 분리하거나 import 경로를
정리하고, 기존 optional 의존성만으로 해당 검사와 CI를 다시 통과시킨다.
`.github/workflows` 변경이나 검사를 건너뛰는 조치는 필요하지 않다.

두 반례는 [tests/test_review_303f.py](../../tests/test_review_303f.py)에
`xfail(strict=True, raises=AssertionError)`로 남겼다. import/수집 오류나 skip은 검출로
세지 않으며, property 반례는 192개가 모두 통과한 뒤 검출 없음 assertion에서 실패한다.

## 실행·회귀·workflow 확인

최종 검사 수와 로그 해시는 [review_303f/verification.json](review_303f/verification.json)에 있다.

- 관련 전체 묶음: **671 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed**.
  관계 생성 12,000개·이벤트 재생 12,000개·원본 변환 192개를 실제 실행했다.
  합계 24,192개는 pytest 항목 11개 안의 사례 수이며 671에 더하지 않는다.
  원 E303 파일 68개, 소유 연결 검사 40개, 등록 소스 22개·source pinning 34개도 포함한다.
  실제 TensorBoard event 읽기와 TensorBoard import를 차단한 별도 프로세스 검사도 통과했다.
- 검토 파일: **8 passed / 2 strict xfailed / 0 errors**.
- strict xfail을 해제한 두 반례: **2 failed / 0 errors**. 두 실패 모두 기대한 assertion이다.
- 변경 범위의 제출 변이 6종: event key, source key, rejected owner, owner union,
  manifest key, seal rekey. 모두 지정 검사에서 실패하며 수집 오류는 없다.

최신 `origin/main`과 workflow가 바이트 단위로 같다는 조건은 현재 충족하지 않는다.
후보 workflow tree는 `d16776ce7b241a0ab49132f65bfa6a5ac17895e7`로, 후보가 병합한 main
`7e081d70`과 같다. 최종 fetch의 main `78ce79162d907d88d38ef3afcfc0c62e4a72aaba`의 workflow tree는
`bc804b64df75a6975dbea1e151b0ecefd2717d59`다. 차이는 이후 main의 apt 캐시 변경
`be318606`/`6f4e6060`이며 `.github/workflows/tests.yml` 한 파일이다.
**두 점 diff는 차이가 있고, 세 점 PR diff 및 567038c2→37828875 diff는 0개**다.
P06이 workflow를 수정했다는 뜻은 아니다. 최신 main 반영 후 동일성·필수 CI를 확인해야 한다.
검토자는 workflow를 편집하지 않았다.

## 재현·보존·범위

`git fetch`, 열린 PR/댓글/diff 확인 후 `git archive origin/codex/evidence-referee | tar -x`
방식으로 `/private/tmp/ugrp-review-303f-O5JR8Q`에 후보를 추출했다. 추가 worktree나 환경을
만들지 않았다. 기존 Python 3.12 환경을 사용했고, driver에서 MuJoCo·torch·물리 worker
import를 차단하고 수치 라이브러리 스레드를 1개로 제한했다. host lock은 사용하지 않았다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
# 정확한 후보 archive에서 실행. 등록 이력 검사만 기존 Git object DB를 읽는다.
GIT_DIR=/Users/changmin/projects/ugrp/.git "$PY" \
  experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py --tb=short
# 이 검토 테스트를 archive/tests에 복사한 다음 검토 브랜치에서 실행:
"$PY" experiments/2026-09-30-e2e-readiness/review_303f/offline.py /path/to/archive \
  tests/test_review_303f.py -rx
"$PY" experiments/2026-09-30-e2e-readiness/review_303f/offline.py /path/to/archive \
  --mutation rejected_owner \
  tests/test_zone_referee_ownership.py::test_192_generated_raw_record_transformations_never_increase_success
```

초기 독립 검사에서 검토자가 summary 거절 메시지 정규식을 잘못 적어 2개가 실패했다.
실제 메시지로 고친 뒤 재실행했으며, 초기 로그도 보존했다. 후보 코드 결함으로 세지 않는다.
원본 로그/JUnit은 `/Users/changmin/projects/ugrp/outputs/review-303f/`에 로컬 보존한다.
보고서·재현 코드·로그 해시만 Git에 넣으며 전체 로그의 원격 백업을 주장하지 않는다.
새 연구 코호트 없이 합성 TensorBoard event를 실제로 읽는 코드 검증만 수행했다.
공용 TensorBoard snapshot·서버·UI와 Drive는 변경하지 않았다.

물리·렌더·학습·실제 모델 호출은 0회다. 실제 실행기 연결, PHYSICAL/E2E 성공,
provider 정산과 대시보드 UI 인수는 이 검토의 범위가 아니다.
검사 종료 뒤 추출 디렉터리를 삭제하고 부재를 확인했다. 실제 연구 raw와 기존 snapshot은
삭제하지 않았다. 검토 대상 23개 수정 파일은 추출본에서 Git 원본과 모두 일치했다.
