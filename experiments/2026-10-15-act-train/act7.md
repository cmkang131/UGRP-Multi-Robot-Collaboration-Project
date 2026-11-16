# ACT7 — 고정 교사 import 충돌 수정

기준 `d4abe49f`, PR #504. 교사 실행 동안 `scripts/sim/harness`의 캐시와 패키지 경로를
`6f057f7e` 의존 checkout으로 격리하고 정상·예외 종료 모두 원래 모듈과 경로를 복원한다.
[동명 파일 목록](act7-module-collisions.json)은 1,671개(모듈 1,614개, 내용 차이 8개)다.
모든 모듈의 실제 패키지 검색 경로와 실제 교사 import 175개의 의존 경로를 확인했다.

`git archive`로 만든 임시 폴더의 전체 선택 파일을 고정 Git blob과 대조했다.
실제 어댑터·계획기·교사·장면 설정을 생성하고 **world 생성 직전** 강제 정지했다.
Mac 물리 step·렌더·학습·원격 호스트 접속은 0이다. 호스트·플랫폼·Git 메타데이터 검사는
이 시험에서만 대체했고 교사 import와 설정 코드는 실제다. 관련 시험 **26 passed / 0 skipped**.
[검증 요약](act7-summary.json) · [실제 import 경로](act7-import-proof.json).

[기존 근거](act7-prior-evidence.json): census 50/50, 원본 100 SHA PASS를 경로·해시로 연결하며
재실행하지 않는다. 8316600은 world/result/RGB 생성 전 EXIT1 HOST_ERROR·명령 0행이므로
재사용하고, 미제출 39개도 재사용한다. 기존 실패는 새 관문 분모에 넣지 않는다.

커밋 뒤 `python3 -m scripts.queue_grasp_act_act7 --output-dir
/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue`로
`20261015-act7-<SHA8>.json`을 만든다. 새 SHA의 **관문 40회만** 준비한다.
모든 approved/enabled/ready/stage_ready/submitted는 false이며 이전 큐 3개는 보존한다.
운영 승인·최신 재고/비용/종료 장치 점검·새 잡음 관문과 회복 성능 검증은 남아 있다.
