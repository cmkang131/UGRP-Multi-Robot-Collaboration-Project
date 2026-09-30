# PR #302 — Batch B 지적 일괄 수정

2026-09-30. 검토 대상 `bd95530a2d5a8b8467620809749273068a7ed55d`에서 시작해 먼저 `origin/main`의 `c12796676802ab54cad2f0635e3e96e911691c76`을 충돌 없이 병합했다. 테스트 통과 전 커밋하지 않도록 병합 결과를 보류하고 같은 작업 트리에 수정했다.

검토 근거: [#302 독립 검토 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302#issuecomment-5911116785), [Batch B 리뷰 #317](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/317)의 `REVIEW_E2E_BATCH_B.md` B3/B4. 다른 PR의 B1/B2는 이 수정의 소유 범위가 아니다.

| 지적 | 수정 | 회귀 |
|---|---|---|
| B3: 로컬 실행 금지를 정상 CI에까지 적용해 취소/skip을 지시 | CI_INCIDENT/VERIFICATION/README/TASKS와 원래 P09 prompt에 정상 CI 허용·취소/건너뛰기 금지를 명시. 잘못된 당시 해석을 정정하고 취소 사실·시각·원본 증거는 보존 | `test_local_execution_limit_does_not_disable_normal_ci`: 문서 진입점 5개에서 허용 범위와 금지 지침 확인 |
| B4: 정식 6종 T02를 좁은 P02의 완료 조건처럼 표현 | T02를 P02 이후의 별도 확장 제안으로 표시. 담당 미정·착수 전 범위/담당 합의·#307에 소급 금지. T02 2×900=1,800과 #307 4조건×1800=7,200을 별도 시험으로 명시 | `test_t02_is_a_separate_extension_with_its_own_owner_and_budget` |

새 회귀는 `tests/test_scenario_capabilities_docs.py`에 두고 정상 CI의 `scripts/run_ci_tests.py` 목록에 등록했다. workflow의 실행/취소 설정은 수정하지 않는다.

## 검증 기록

- 수정 전 문서 복사본에서 새 회귀 **6 failed in 0.17s**: B3 5개 진입점과 B4 1개. 무관한 실패 없이 잘못된 기존 지침/범위를 재현했다.
- 최종 수정 후 관련 검사 **251 passed in 79.70s**, 실패/건너뜀 0. 세부 결과와 원본 해시는 [review_fixes_verification.json](review_fixes_verification.json)에 기록했다. 필수 `tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`, 기존 정적 feasibility/final-env/보조 검사와 CI 목록 분할 검사를 포함한다.
- 두 검사 실행 모두 기존 Mac 환경과 공용 잠금을 사용한다. MuJoCo·모델 라이브러리 import, 외부 socket 연결, schematic 렌더를 차단한다. 다른 작업의 잠금을 해제하지 않았다.
- 관련 검사 첫 수집은 임시 가드가 `map_goto`의 OpenCV import까지 차단해 두 번 종료됐다(각 1 collection error). 고정 소스/기대 해시는 건드리지 않고 임시 가드에서 OpenCV import만 허용했다. 화면 출력·capture·모델 생성은 계속 차단한다. 이 환경 오류와 대기 로그도 보존한다.
- 다음 검사에서는 229 passed / 22 failed였다. 실패 22건은 모두 `test_zone_study_source_pinning.py`가 실제 지도 정보의 출처인 `sim.session_scenes.ROOT`를 읽는 import를 임시 가드가 막았기 때문이다. 해시 불일치가 아니며, 정적 모듈 import만 허용하고 `Scene.__init__`를 차단한 최종 가드에서 251건 전부 통과했다. 제품 소스·등록 JSON·기존 테스트는 수정하지 않았다.
- CI fixture 사전검사는 처음에 sparse checkout에서 빠진 기존 v3/v4/v5 `example_trial_record.json.gz` 3개를 거절했다. 합계 158,676바이트만 sparse 목록에 추가해 원래 Git blob 그대로 복원한 뒤 통과했다. 새 데이터로 대체하거나 검사를 생략하지 않았다. CI shard 목록은 새 회귀 파일을 정확히 한 번 포함한다.
- 수정 전 등록 JSON·v6e 고정 소스·번들/workflow 등록·기존 P09 data **145파일**을 원래 HEAD와 바이트 대조했다. 수정 후에도 같은 145파일의 해시가 전부 동일함을 확인했다. source-pinning 검사나 기존 등록 해시를 완화하지 않는다.
- raw/음성 대조 문서/보호 해시/로그/JUnit은 `/Users/changmin/projects/ugrp/outputs/p09-review-fixes-20260930/`에 로컬 보존한다. 원격 백업 완료로 표시하지 않는다.

## 전달 범위

정상 GitHub CI는 허용되며 필수 검증이다. workflow를 취소하지 않는다. 커밋 지시어로 CI를 건너뛰지 않는다. 새 push가 기존 PR CI를 자동 취소하지 않도록 이전 실행 종료를 확인하고 push한다. 최종 커밋 SHA의 CI와 한국어 지적→수정 답변은 PR #302에서 확인한다. 과거 cancelled 실행이나 로컬 통과를 최신 CI 통과로 소급하지 않는다.

로컬 물리·렌더·모델 실행은 0회다. 이번 변경은 문서/회귀 보완이며 새 실험·학습·학생 평가 cohort가 없어 TensorBoard snapshot을 만들지 않는다. C6/C7 학생·물리 성공은 여전히 미측정이다. Drive 작업과 원본 삭제/덮어쓰기는 없다.
