# PR 自動 CI 예외 기록

사용자의 새 물리 실행 금지 범위를 PR 자동 CI까지 사전에 차단하지 못했다.

- [run 40531267967](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/40531267967): 이 PR이 자동 생성한 실행만 cancel 및 force-cancel 요청. 최종 `completed/cancelled` 확인.
- `ci-preflight`는 통과했다. `ubuntu-simulation-scenarios`의 **Render and move without a model or GPU** 단계는 취소 적용 전 `success`로 완료됐고, **Two unloaded robots yield using RGB and clear reservations**는 `cancelled`다. 따라서 전체 실행을 physics 0으로 보고할 수 없다. 단계 내 물리 step 수는 재계수하지 않았다.
- `ubuntu-simulation-runtime`은 input/output boundary 검사 중 취소됐으며 이후 geometry/physics 검증 단계는 skipped다. `multi-object-scenes`의 정적 렌더 단계는 skipped다. 전체 CI 통과는 아니다.
- 로컬 작업은 pure-Python tests, JSON/trace 분석과 sha256sum뿐이며 GPU·GCP VM 조작은 없었다. 기존 sealed result/prereg는 수정하지 않았다.
- 취소 메타데이터는 `/home/ubuntu/agent-logs/20261027/han32-pr636-ci-cancellation.json`에 회수했다. 해당 파일은 새 예외 기록이며 실험 원본을 대체하지 않는다.
- 후속 정정 커밋은 `[skip ci]`를 사용한다. GitHub의 push/pull_request skip 지침을 확인했다: [GitHub Docs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs). 다른 workflow나 프로젝트 설정은 바꾸지 않았다. 이 예외를 성공 실험이나 Level-B 결과로 세지 않는다.
