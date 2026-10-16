# PR #307 — main 충돌 해소와 비물리 재검증

- 작업 브랜치: `codex/mixed-jobs`
- 승인 검토 대상/병합 전 HEAD: `1bf7a1cd6352effce0b5619a7e01a3c960068263`
- 병합한 main: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`
- 범위: main 병합 충돌 해소, 관련 검사, 병합 커밋·push. 실제 임무 실행 없음.

## 충돌 해소

`scripts/run_ci_tests.py`에 P02 mixed jobs와 main의 P07 manifest 검사를 모두 유지했다.
전체 테스트 등록 목록은 양쪽 부모의 Counter 합집합과 같다. 기존 중복 패턴 4개는
양쪽에 이미 있던 항목이며 기존 수집기가 중복을 제거한다. 335개 파일의 8개 shard
포함·중복 검증을 통과했다. main의 비물리 검사 기본 무잠금 규칙도 그대로 유지한다.

`experiments/2026-09-30-process-review/LITERATURE.md`는 양쪽 정정을 합쳐
정상 GitHub CI 필수 실행, 취소·생략 금지, 과거 로컬 미실행 기록 보존과
실제 확인한 CI 결과만 보고한다는 뜻을 유지했다.

## 검증

- PR 관련 11개 파일과 테스트 등록/잠금 관련 3개 파일: **448 passed / 1 skipped**.
- `test_zone_pair_registered_source.py`: 22건 통과.
- `test_zone_study_source_pinning.py`: 34건 통과.
- 생략한 1건은 기존 native 물리 테스트이며 비물리 가드에 따라 생략했다.
- 물리 step·렌더러·실제 비전 worker·네트워크 호출 시도 모두 0회.
- v6e 소스 85개 및 사전 등록 JSON 53개가 main과 바이트 단위로 동일하다.
- main 설정/workflow 32개, 브랜치 설정 32개, 기존 보존 대상 14개가 동일하다.
- 승인받은 mixed 소스와 테스트 해시는 그대로이며 `.github/workflows` 변경은 없다.
- `git diff --check` 통과. sparse checkout이 제외한 CI gzip fixture 3개를
  저장소 main 바이트 그대로 복원하고 `check_ci_fixtures.py`를 통과했다.

검사 명령·JUnit·로그·가드와 해시는 `MERGE_MAIN_VERIFICATION.json`에 연결한다.
최초 정적 검증기의 중복 패턴 금지 가정은 양쪽 부모에 이미 있던 중복 4개를 발견해
정확한 Counter 합집합 검사로 바로잡았다. 소스/테스트 수정은 필요하지 않았다.

raw 경로: `/Users/changmin/projects/ugrp/outputs/e2e-p02-main-merge-20260930T141223Z`. 로컬 보관이며 원격 백업을 뜻하지 않는다.
새 실험/학습/평가 코호트가 없어 TensorBoard 변환은 수행하지 않았다. Drive 작업 없음.
GitHub CI와 실제 PR 병합 여부는 push 뒤 별도 확인하며, 이 기록은 전체 CI 통과나
최종 v3/provider/v6h1 혼합 운반 성공을 주장하지 않는다.
