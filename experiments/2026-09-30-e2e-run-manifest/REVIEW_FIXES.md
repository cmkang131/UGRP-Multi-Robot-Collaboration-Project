# PR #311 독립 검토 수정

검토 대상은 `bd011c997f9f7946de28f912dbdd3833ebb33988`, 지적은
[Batch C / C311-1](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/318)이다.
작업 시작 시 최신 main `c12796676802ab54cad2f0635e3e96e911691c76`을 먼저 합성했다.
텍스트 충돌은 없었다. 로컬 물리·렌더·추론·모델 호출은 하지 않는다.
작업 도중 main에 추가된 #306도 합성했다. 최종 포함 main은
`b10907c5f2c84f2712030f48fb38061fd4f51281`이며 추가 병합도 충돌 없이 끝났다.

## C311-1: 실제 P03 조합과 참조 자산의 해시 누락

기존 코드는 provider allow-list와 runner의 전역 리터럴/AST import만 읽었다.
#312의 지역 `assets`에 추가된 `configs/vision_loc_provider_p03.json`은 발견하지
못했고, 카메라 선언이 달라져도 P07 초안 해시는 같았다.

- P03 조합 JSON을 명시적으로 읽고 파일 자체와 `active.files_sha256`의 모든 자산을
  계획 해시에 연결한다. worker·카메라·동작 보정 참조 누락, 비로컬/누락 파일과
  자산 해시 불일치를 거절한다. 해당 JSON이 없는 소스는 `unavailable`로 기록한다.
- 저장한 초안에 대해 카메라 선언 변경, 새 참조 자산 변경 및 P03 파일 삭제를 거절한다.
  JSON 존재·해시 일치만으로 최종 v3 조합을 지원한다고 표시하지 않는다.
- `candidate_opt_in`은 선언만 보존한다. 미배포 로컬 가중치를 읽거나 provider를
  시작하지 않는다. `runnable=false`, `physical_ready=false`, 승인·봉인 null을 유지한다.

회귀 자료는 #312 검토 SHA `919f78ef6ebaf2495633338bcb1b9510f46399bd`의
조합 JSON과 worker JSON 원본이다. `tests/fixtures/zone_e2e/README.md`에 출처를
남겼다. 두 파일은 테스트의 임시 소스에만 합성하며 현재 등록된 worker를 수정하지 않는다.

## 기존 CI 실패도 함께 수정

기존 HEAD의 CI run `36711857850` shard 3과 `36711853313` shard 2는
`tests/test_zone_eval_top.py::RobotInputBoundaryTests::test_no_robot_side_module_references_the_profiles`
검사에서 실패했다. 평가 프로필 이름을 P07의 `harness/` 파일에 직접 선언했기 때문이다.

평가 선언을 `evaluation_proposal_v1.json`으로 분리하고 해당 파일의 해시를 계획에
포함했다. 기존 입력 경계 검사의 예외를 늘리거나 검사 자체를 바꾸지 않았다.
평가 선언의 해시 변경 거절 검사와 선언 연결 검사를 추가했다.

최초 P07 기록의 CI 금지 해석도 정정했다. 정상 GitHub CI는 허용되며 필수다.
취소나 skip 커밋 표기를 사용하지 않는다. 로컬 물리 금지와 GitHub CI를 구분한다.

## 보존 범위

기존 등록 JSON 60개는 검토 HEAD와 바이트가 같고, 현재 v6e가 고정한 소스
85개는 등록 해시와 같다. 기존 등록 해시를 새 코드에 맞춰 바꾸지 않았으며
runner·provider·물리·보정 소스는 수정하지 않았다.

최초 `manifest_DRAFT.json`/`dry_run_DRAFT.json`과 검사 수치·해시는 역사적 원본이다.
수정된 planner에서 이 옛 초안이 거절되는 것은 정상이다. 새 초안과 실행 없는 CLI
검사, 테스트 원본·해시는 기본 체크아웃의
`outputs/e2e-p07-manifest/review-fixes-20260930/`에 별도로 보관한다.
로컬 raw 전체가 원격 백업되었다고 주장하지 않는다.

새 실험 코호트·모델·물리 결과가 없으므로 TensorBoard 변환이나 서버를 만들지 않는다.
Drive 작업·봉인·실행 승인은 없다.

## 검증

수정 전 planner에 새 반례를 적용해 **2 failed**를 확인했다. 카메라 설정 및
새 참조 파일이 바뀌어도 초안 해시는 같았다. 첫 수정 검사 **294 passed / 5 failed**는
테스트 합성본에 #312의 worker 설정을 함께 복사하지 않아 새 해시 검사가 거절한
결과다. 실제 고정 worker를 수정하지 않고 테스트 자료를 완성한 뒤 다시 검사했다.

최종 관련 검사: **303 passed, 0 failed, 0 skipped**, 97.30초.

```text
tests/test_zone_e2e_manifest.py
tests/test_zone_pair_registered_source.py
tests/test_zone_study_source_pinning.py
tests/test_zone_pair_authorization.py
tests/test_ci_sharding.py
tests/test_zone_eval_top.py::RobotInputBoundaryTests
```

기존 Python 3.12 환경과 공용 `run_locked(..., local_lock_root())`, OMP/BLAS 스레드
1을 사용했다. 별도 guard로 MuJoCo·torch·실제 worker·네트워크를 막았다.
소스 고정 검사 파일은 제외 없이 실행했다. 임시 SQLite를 쓰는 기존 테스트도 이번
검사에 포함했으며 실제 연구 예산 DB나 외부 모델 연결을 만들지 않았다.

새 CLI 초안 생성과 저장 후 재검사는 둘 다 종료 코드 **3**, stdout 바이트 일치다.
main 추가 병합 뒤 재검사도 같은 결과다. 과거 초안은 종료 코드 **2**로 거절된다.
새 초안은 runtime 268파일을 고정하고 미충족 관문 37개를 남긴다. 4/4/24/72회,
212,250 SIM초 및 raw 목적지 228개는 여전히 제안일 뿐이며 raw 실행 폴더를 만들지 않았다.

Sparse checkout이 제외한 기존 추적 fixture 3개는 원본 그대로 다시 표시한 뒤
`scripts/check_ci_fixtures.py`를 통과했다. `git diff --check`도 통과했다.
main의 #306 추가 합성 후 `test_ci_sharding.py`와 `test_ci_fast_path.py`를 다시
검사해 **76 passed, 280 subtests passed**를 확인했다(303개 결과와 중복 합산하지 않는다).
소스·시험·원본 해시와 판정은 [verification_review_fixes.json](verification_review_fixes.json)에 기록했다.
정상 GitHub CI는 push 뒤 확인해 PR 코멘트에 별도로 보고한다.
