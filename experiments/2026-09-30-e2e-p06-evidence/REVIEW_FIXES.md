# PR #303 독립 검토 후 수정

검토 대상 `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8`의 A303-1/2/3을 한 묶음으로 수정한다.
검토 출처는 `origin/codex/review-e2e-batch-a:experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_A.md`와
[#303 독립 검토 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/303#issuecomment-5911311182)이다.
먼저 `origin/main`의 `b10907c5`를 이 작업 브랜치에 병합했다. 텍스트 충돌은 없었다.

## 지적 → 수정

- **A303-1:** 파일 해시만 맞으면 trial ID/scenario/seed/주문을 바꿔도 성공 event가 나왔다.
  이제 `evidence_identity`로 논리 trial과 실제 run/episode/attempt를 별도로 연결한다.
  result/manifest/trial/evaluation 사이의 identity, bundle의 공개 scenario 참조와 주문서,
  요청 원문·provenance의 주문서, study config, 심판의 주문별 개체/시각/배송 수를 대조한다.
  파일 inventory와 해시를 모두 다시 계산한 반례도 거절한다. 성공한 두 retry는 같은
  trial ID와 서로 다른 run ID/attempt를 유지하며 각각 분모 1로 남긴다.
- **A303-2:** v6e가 고정한 runner를 바꿨다. 기대 해시나 등록 JSON을 수정하지 않고
  `scripts/run_zone_study_integration.py`를 main의 원래 바이트로 복원했다.
  SHA-256은 `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`다.
  P06의 기록 코드는 별도 `scripts/zone_study_evidence_writer.py`로 옮겼다.
  이 모듈은 실행기를 시작하거나 monkeypatch하지 않는다. 기존 등록을 역사화하거나
  #292를 임의로 합성하지 않았다. 새 writer의 물리 실행기 연결·새 봉인은 후속 작업이다.
- **A303-3:** terminal 표식을 빼면 통과했다. result의 JSON `true`, manifest의 완전한
  terminal 객체, boolean `record_complete`를 필수로 검사한다. 빠진/거짓/잘못된 타입/
  불일치 표식은 거절한다. 같은 run schema의 구형 자료도 묵시적으로 수입하지 않는다.
  원본에 표식을 덧붙이거나 기존 raw/snapshot을 다시 봉인하지 않는다.
- main에서 들어온 `experiments/2026-09-30-process-review/LITERATURE.md`의 CI 생략
  지시를 정상 CI 실행으로 정정했다. P06 프롬프트에도 로컬 실행 제한과 GitHub CI를
  구분했다. 이 작업은 CI를 취소하거나 생략 표식을 사용하지 않는다.

## 회귀와 검증 경계

새 회귀 이름은 `tests/test_zone_study_evidence.py::test_a303_*`다. A303-1은 원래 검토의
네 ID 변경과 envelope/bundle/evaluation/request/config 교환을 검사한다. A303-2는
등록 JSON이 고정한 runner 해시를 직접 대조하고 새 writer가 기존 함수에 설치되지
않았음을 확인한다. A303-3은 표식 누락·오류를 검사한다. 거절 사례는 event 미게시를
확인하며 정상 6종 terminal과 retry는 실제 TensorBoard event를 다시 읽는다.

최초 수정 전 테스트 시도는 다른 작업의 살아 있는 공용 잠금 때문에 실행되지 않았다
(exit 3, 최대 300초 유한 재시도). 기존 독립 검토의 실패를 이 작업에서 재실행한 결과로
표시하지 않는다. 다른 작업의 잠금·프로세스는 변경하지 않았다.

최종 검사 명령·결과·해시는 아래에 완료 후 기록한다.

물리·렌더·실제 모델 호출은 0회다. 검사 자료는 synthetic이며 OS 임시 폴더만 쓴다.
TensorBoard 공용 snapshot/서버/화면, 실제 provider 정산, 새 writer로 실행한 물리
종료·중단 인수는 수행하지 않았다. 로컬 원본·기존 snapshot·Drive에는 변경이 없다.

## 최종 로컬 검사

- **302 passed, 0 failed, 0 errors, 0 skipped** (pytest 77.99초). 로봇 성능 시간이 아니다.
- Python 3.12.13 / TensorBoard 2.21.0, 기존 Mac 환경 재사용. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, OMP/BLAS/MKL/VECLIB 스레드 1.
- 첫 선별 검사: 84 passed / 1 failed. 미상 비용 fixture의 다른 주문서 provenance가 새 검증에 거절됐다. 원래 자료의 provenance로 fixture를 고쳤고 검증 규칙은 유지했다.
- [선별 node 목록](review_test_selectors.json): 앞선 P06 검사 + 새 반례 + 두 소스 고정 파일 전체 + door-relax 등록 보존 검사. `test_zone_study_referee.py` 전체는 실행하지 않았다.
- 실행: `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python /tmp/p06-review-tests.py <선별 목록> --junitxml=/tmp/p06-review-final.xml`. 이 wrapper는 `scripts.run_ci_tests.run_locked`와 `scripts.agent_lock.DEFAULT_ROOT`를 사용했다.
- JUnit: `/tmp/p06-review-final.xml`, SHA-256 `6cba82cf4b9c29a87d16adb2d4e43de0f1833ec5bf97770f3e0c030af9c8e0b2` (로컬 임시 검사 기록).
- [검사 소스 해시](review_source_files.sha256). 302개 검사 전후 Python 해시 일치. 커밋 전 공백 검사에서 새 writer의 EOF 빈 줄 한 개만 제거했고 전후 AST 동일성을 확인했다. 위 해시 목록은 이 최종 공백 정리까지 반영한다. AST 문법과 `git diff --check` 통과. v6e runner와 기존 등록 파일은 main 대비 변경 없음.

| 검사 모듈 | 통과 |
|---|---:|
| `tests.test_tensorboard_export` | 64 |
| `tests.test_zone_pair_door_relax` | 1 |
| `tests.test_zone_pair_registered_source` | 22 |
| `tests.test_zone_study_eval.BoundaryTest` | 8 |
| `tests.test_zone_study_eval.ChannelTest` | 6 |
| `tests.test_zone_study_eval.ComparisonTest` | 9 |
| `tests.test_zone_study_eval.DialogueTest` | 20 |
| `tests.test_zone_study_eval.EfficiencyTest` | 8 |
| `tests.test_zone_study_eval.ParseTest` | 9 |
| `tests.test_zone_study_eval.ReportTest` | 8 |
| `tests.test_zone_study_eval.SummaryTest` | 3 |
| `tests.test_zone_study_evidence` | 84 |
| `tests.test_zone_study_referee` | 23 |
| `tests.test_zone_study_review_fixes` | 3 |
| `tests.test_zone_study_review_r5` | 1 |
| `tests.test_zone_study_source_pinning` | 33 |

이 숫자에 이전 203개·독립 검토 176개·첫 선별 84개를 합산하지 않는다. GitHub CI는 push된 최종 SHA에서 별도 확인하여 PR 댓글에 남긴다.
