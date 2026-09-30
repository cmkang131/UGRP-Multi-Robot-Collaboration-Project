# PR #338 — Batch K 수정과 오프라인 검증

2026-10-01, Codex. 독립 검토 `84f672ae97e2d7a6c7b4b299a2f90e5ba3f552a6`의
#338 지적 K1을 수정했다. 검토 대상은 `6df8f1ae6ff36b8a779fb36c1cb1c0ab6548e069`였으며,
수정 전 main `f3fbbf9a08c0ba96b22858b573ab5d4da52e9011`을 병합했다.
이 main에는 P03 #312와 T10a #310이 포함된다. 관련 검사를 모두 통과한 뒤 커밋한다.
PR은 draft로 유지하며 병합하지 않는다.

## 원인과 수정

기존 `test_ci_collects_this_file`은 `test_zone_final_env`라는 부분 문자열로
패턴을 골랐다. 새 `test_zone_final_environment_runnable.py`도 이 문자열을 포함해
실제 CI가 두 파일을 올바르게 수집하는데도 검사가 실패했다.

실제 실행기가 쓰는 `collect_test_files`의 glob 확장 결과에 정확한 파일 경로가
있는지 검사하도록 바꿨다. 이름이 비슷한 다른 파일과 넓은 glob을 허용하면서,
원래 파일이 빠졌거나 존재하지 않는 경로만 등록된 경우에는 계속 실패한다.

검토 브랜치 `tests/test_review_e2e_batch_k.py`에서 #338 반례와 필요한 helper를
가져와 K1의 strict-xfail을 제거했다. #339 반례는 이 PR에 가져오지 않았다.
기존 환경 검사·새 실행 환경 검사·리뷰 반례 파일이 각각 정확히 한 번 수집되는지,
넓은 glob·겹치는 glob·유사 이름만 등록·없는 파일·빈 목록을 검사한다.
리뷰 반례도 `scripts/run_ci_tests.py`의 정상 CI 목록에 넣었다.

## 검증

- 수정 전 K1 반례: **1 failed**. 수정 후 CI 수집·분할 및 기존 환경: **165 passed**.
- 변이 **16/16 검출**: K1 관련 5개와 기존 환경 계약 11개 모두 목표 pytest가
  exit 1로 실패했다. 매번 원본 bytes 복원을 확인했고, 복원 후 K1 묶음 9개가 통과했다.
- 환경/소스 고정/provider/관리자/의존성 계약 관련: **369 passed, 4 subtests passed**.
  실제 물리 테스트 4개는 guard로 skip했다. `ps` 조회가 필요한 기존
  `test_parent_exit_cleans_background_child` 1개는 로컬에서 제외하며 CI에는 남긴다.
- 기존 RGB 번들 JSON **65/65 바이트 동일**, v6e 소스 pin **85/85 일치**.
  v6e 등록·기본 workflow catalog와 보호된 두 테스트도 origin/main과 바이트 동일하다.
- `.github/workflows`의 origin/main 대비 diff는 0이다. tests.yml은 main 병합으로만
  갱신했으며 이 수정에서 workflow를 편집하지 않았다.
- RGB v63 `verify-current`, 기존 registry `verify-registry`, 필수 fixture 3개 검사를 통과했다.
- main+열린 PR **17개**의 SHA·번들 선언·workflow를 재조회했다.
  v84 및 2.17.0은 #338에만 있고, 각 catalog의 workflow ID 중복도 없다.
  번호를 새로 예약하거나 바꾸지 않았다.

변이 검사와 검증 파일 해시는 [검증 기록](review_k_verification.json),
번호 근거는 [예약 재확인](review_k_reservation.json),
바이트 근거는 [보존 검사](review_k_preservation.json)에 남긴다.
기존 결과 파일은 덮어쓰지 않는다.

## 범위와 남은 일

새 제어기 변경은 없다. 제어 입력은 자기 RGB·정적 지도·자기 명령 이력·전달된
메시지이며, GT는 평가 경계에 남는다. P01 수집 경로와 P03 거절 조건을 fake로
검사했다. 로컬 물리·렌더·실제 모델 추론·LLM 실행 및 호스트 잠금 사용은 0회다.
새 실험/훈련/평가 cohort가 없어 TensorBoard 변환이나 viewer 시작은 하지 않았다.

P03는 실측 v3 보정과 별도 v3 pair chain adapter가 없어 계속 `runnable:false`다.
위 검사는 물리 정확도·파지·완주·독립 재검토 승인을 뜻하지 않는다.
정상 push 뒤 CI 결과는 해당 커밋의 GitHub 검사에서 별도로 확인한다.
`/private/tmp` archive 추출 폴더는 생성하지 않았다. raw 검증 로그는 로컬 공용
`outputs/final-env-v84-k1-20261001/`에 보존하며 원격 raw 백업으로 표현하지 않는다.
