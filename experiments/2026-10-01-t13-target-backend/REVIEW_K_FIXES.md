# PR #339 검토 K 한 묶음의 답변

검토 원문: `origin/codex/review-e2e-batch-k` / `84f672ae`,
`experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_K.md`.
후보 출발: `eb46383f3bc435d1801f4917034606a885d1f8b6`.
main `0d45ef8c2afb55e3e4ac9f8a61ac519f41e92e4f`를 먼저 병합했고,
#338 `6df8f1ae6ff36b8a779fb36c1cb1c0ab6548e069`를 의존 브랜치로 통합했다.

| 지적 | 변경 | 확인 범위·남은 일 |
|---|---|---|
| K2 P1: 같은 시각 두 촬영으로 영구 정지 | 새 host adapter의 `_capture`에서 로봇별 같은 시각 요청을 한 번으로 합침 | 원 반례와 later-time 양성 대조, active target·arm macro·정기 촬영 겹침, peer 격리, 다음 시각 refresh 통과. identity의 같은/역순 시각 거부 유지 |
| K3 P1: 기존 v6e catalog hash 수정 | catalog·등록 파일을 origin/main의 원 바이트로 복구, 별도 workflow fragment 사용 | 고정 소스 85개 모두 일치. 기존 번들 65개와 이전 v85 번들, CI workflow 및 보호된 두 테스트 원본 보존 |
| K4 P1: 최종 v3 환경 미연결 | v84 final environment의 지도·로봇·provider·보정 계약·소스 hash를 새 v86 후보에 연결 | **부분 해결/실행 BLOCK 유지.** v3 측정 보정과 target RGB projection/held 판단·manipulation/host 이관은 없음. runner·직접 API·v2 consumer는 미지원 조합을 물리 생성 전에 거부 |

K4를 단순히 `robot_model` 문자열만 바꿔 해결했다고 보고하지 않는다. #338에도 측정 보정과
표적 조작 스킬이 없고 기존 v9·RGB 모델은 v2 기하를 사용한다. `--execute`는
`T13_FINAL_ENVIRONMENT_NOT_READY`로 거부한다. v3 모델에 v2 보정을 적용하거나 현재
물리 실행 가능/성공으로 선언하지 않았다. **#339는 #338에 의존하며 draft/BLOCK을 유지한다.**
사용자의 물리 실행 금지에 따라 보정 수집·실제 known-case 인수·렌더·모델 실행은 하지 않았다.

기존 v85 bundle은 그대로 보관한다. main + 열린 PR 17개에서 선언과 catalog를 조회한 뒤
다음 번호 **zone-target-v86 / 2.19.0**을 예약했다. 원본 s5 배치·주문·30/62.5초 사건은
그대로이며 신규 환경과 과거 v2 결과를 혼합하지 않는다.

검토의 #339 테스트 네 개는 xfail을 모두 제거했다. #338의 K1은 부분 문자열 대신
정확한 테스트 파일 이름을 확인하도록 고쳤으며 두 환경 테스트 모두 CI 수집을 유지한다.
두 신규 workflow를 함께 병합한 catalog 검사도 43개와 두 ID 존재를 확인하도록 맞췄다.
`.github/workflows`는 origin/main과 동일하다. normal CI를 사용하며 병합하지 않는다.

## 검증 이력

- 수정 전 원 반례: 3 failed, 1 passed. duplicate frame·기존 등록 bytes·v2 환경 선택을 재현.
- K2/K3 수정 후 보존·관련 검사: 126 passed, 1 deselected(K4).
- 추가 테스트 첫 실행: 23 passed, 3 failed. 테스트 기대 status 오기,
  v3 template XML 선언 누락, 검사 도중 소스 변경으로 생긴 bundle drift를 수정했다.
  이 실행을 안정된 후보 검증으로 사용하지 않는다.
- 안정된 좁은 묶음: 26 passed.
- 전체 관련 첫 묶음: 577 passed, 1 skipped, 1 failed. 실패는 두 브랜치 통합 뒤
  catalog 개수 기대값(42→43) 하나이며 원 로그를 보존했다.
- 최종 묶음·mutation·계획·보존 검사는 [review_k_verification.json](review_k_verification.json)에 기록한다.
  mutation은 기존 8개와 신규 4개를 자식 프로세스 메모리에서만 변경하며 파일을 수정하지 않는다.

전체 pickup region clear-empty/OWN_PICKUP_ABSENT는 아직 미구현이다. 실제 파지·낙하·복구·배송,
4조건 메시지/효과 및 물리 성공률은 미측정이다. 새 실험 결과가 없어 TensorBoard 변환·viewer는
시작하지 않았다. raw 로그는 로컬 outputs 보관이며 원격 raw 백업으로 보고하지 않는다.
임시 extraction 디렉터리를 만들지 않았고 사용한 임시 경로 포인터는 삭제했다.
