다섯 번째 프로젝트 `ugrp-sim-e-1016`의 L4를 beamact3 C2용으로 준비했습니다. `gcp5` 별칭은 `g2-standard-8` / L4×1 /140GB 공개 CUDA 이미지로 연결되며 기본 호스트는 gcp2 그대로입니다. 실행 시간 상한 없이 유휴20분·서비스 계정/scope 없음·전용 SSH 키·임대/정지 거부 규칙을 적용합니다.

의존 PR: **#554 → #558 → #559**. 이 PR의 base는 `codex/gcp4setup`입니다. gcp1에는 요청하지 않았고 gcp2/gcp3/gcp4 기존 비용 장치는 변경하지 않았습니다.

검증:
- gcp5 프로젝트 필터 월 순비용1,000 KRW·기본 결제 IAM 이메일 → Pub/Sub → stop_on_budget. e2-micro 시험에서 발행 후6.983초 STOPPING·36.474초 TERMINATED, 시험 VM/디스크 삭제 후에만 L4 생성.
- gcp4와 CPU/MJWarp freeze·핵심 소스3파일 SHA 일치. CUDA 2세계·1스텝 통과.
- gcp2 L4의 ACT 환경115패키지 버전 일치. 인덱스가 선택한 torchcodec CUDA 로컬 버전1건은 원본 PyPI0.10.0으로 보정하고 거부 원장에 보존.
- 데이터1,482파일·21,052,237,810바이트 전체 출발/도착 SHA 일치. 키·자격 증명·Git 전체 이력 복사 없이 허용 데이터/코드만 전송.
- 실제 beamact3 B 모듈/데이터로50step·actor/optimizer 저장/재로딩·같은 입력 예측 완전 일치(97.27초). C2 본학습·학생/임무 관문은 미실행.
- 관련 비물리 테스트18개, shell/AST·diff 검사 통과. 임대 중 정지 거부75 확인. 다른 작업 없음 확인 후 자기 임대만 해제하고 gcp5 TERMINATED 확인. gcp2는 다른 작업 임대를 보존하고 정지하지 않음.

ACT 환경은 `/home/ugrp/ugrp-rl1b-act-env`, 데이터는 원래와 같은 `/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view`입니다. 현재 참조 train_shared.py의 gcp2 전용 host guard와 C2 설정 연결은 beamact3 브랜치 작업으로 남습니다. 실제 청구 집계 지연·이메일 수신은 미검증이며 정지 후 디스크/빌드 저장소는 남습니다. 결과는 다른 프로젝트와 합산하지 않습니다.

기록: `experiments/2026-10-16-gcp5setup/README.md`, `summary.json`, `evidence/funnel.json`, `evidence/SHA256.json`. 반복 검토/실행 시 기존 원본을 덮어쓰지 않도록 새 출력 이름을 사용합니다.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
