# PR #307 — 독립 검토 B1 수정

검토 대상은 `6bb522b14aa28fcaa3ff30f988aebca4ab3aee15`이며, 시작 시 최신 main
`c12796676802ab54cad2f0635e3e96e911691c76`을 먼저 충돌 없이 병합했다.
검토 원문은 [#317](https://github.com/kcm0127-dotcom/ugrp/pull/317)의 Batch B와
[#307 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/307#issuecomment-5911113048)이다.

## B1 → 수정

혼합 기능이 바꾼 `harness/zone_own_team_host.py`, `harness/zone_study_integration.py`,
`scripts/run_zone_study_integration.py`를 v6e 등록 해시와 같은 원본 바이트로 복원했다.
해시를 새 소스에 맞춰 바꾸거나 검사를 없애지 않았다. v6e의 소스 **85/85개**와
기존 보존 대상 14개가 일치하며, 기존 등록 JSON·Scene·bundle/workflow를 변경하지 않았다.

혼합 기능은 새 `scripts.zone_mixed_study_adapter`에서 명시적으로 연결한다.
`MixedOwnCamTeamHost`는 정적 계약/inventory 검사 뒤 기존 solo 초기화와 pair 연결을
순서대로 수행한다. `MixedIntegratedTrial`은 새 계획 거절 처리를 자기 dispatch에 적용하고
기존 스케줄러·원장·자기 명령 기록을 재사용한다. 공용 모듈의 전역 함수 교체는 없다.
기존 CLI는 혼합 주문을 계속 거절하며 새 실행 봉인은 코디네이터 후속 범위다.

새 회귀 10건은 위 3개 파일의 바이트 보존, 의존성/기존 admission 분리, 실제 정적 Scene과
fake World 소유자의 생성자 연결, 잘못된 계약·inventory·frames 설정 거절, 종료/죽은 로봇
거절 우선순위를 확인한다. 기존 네 조건의 독립 API·실패 격리·ledger/eval join 검사도 유지했다.

## 검증

- 새 바이트 회귀를 보존한 수정 전 파일에 적용: **3 failed**, 예상한 음성 대조다.
- 혼합·등록·소스 고정·기존 door 회귀: **111 passed**.
- 초기 추가 검사: **244 passed / 1 failed**. 제가 native World 테스트를 잘못 선택했다.
  렌더러 생성에서 `invalid CoreGraphics connection`으로 차단되어 `host.run`에 도달하지 않았다.
  이 시도를 없었던 것으로 적지 않으며 원본 JUnit을 보존했다.
- 최종 11개 파일 전체: **355 passed / 1 skipped**. 기존 `tests.pose_provider_no_physics`와
  로컬 렌더러 생성 차단 플러그인을 켰다. 제외 1건은 위 native 테스트다.
  최종 실행의 물리 step·렌더러·실제 비전 worker·네트워크 호출 시도는 모두 **0**이다.
- `tests/test_zone_pair_registered_source.py` 22건과 `tests/test_zone_study_source_pinning.py`
  33건을 포함한다. `git diff --check`와 새/관련 Python 파일 구문 검사도 통과했다.

모든 pytest는 공용 잠금 아래 실행했고, 다른 작업의 잠금·프로세스는 바꾸지 않았다.
정확한 파일 해시·검사 목록·원본 위치·실패 이력은 [VERIFICATION_B1.json](VERIFICATION_B1.json)에 있다.
원본은 기본 checkout의 `outputs/e2e-p02-b1-fix-20260930/`에 로컬 보존한다.

main에서 들어온 `LITERATURE.md`의 CI 생략 지침을 잘못된 해석으로 정정하고 P02 프롬프트에도
정상 CI 허용을 명시했다. GitHub CI를 취소하거나 커밋에 CI 생략 표시를 넣지 않는다.
최종 push SHA와 CI 결과는 #307 댓글에서 따로 확인한다.

제출 전 추가된 main `b10907c5f2c84f2712030f48fb38061fd4f51281`(#306)도 충돌 없이 병합했다.
검사한 mixed 소스·테스트와 v6e의 85개 소스 바이트는 그대로다. 검사 목록에는 main의
L1 분석 테스트 한 행만 추가되어, 8개 shard의 전체 포함/중복 검사와 P02/L1 파일의
각 1회 등록을 정적으로 확인했다. 관련 소스가 같아 위 355건을 중복 실행해 합산하지 않았다.

임무 물리 성공·실제 모델·최종 v3/provider/v6h1 합성은 여전히 미검증이다. 등록 번호는 새로
예약하지 않았다. 실험 cohort가 없으므로 TensorBoard snapshot은 만들지 않았고 Drive 작업도 없다.
