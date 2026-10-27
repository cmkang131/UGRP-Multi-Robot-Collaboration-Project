
## 2026-10-16 coordinator
- Mac 여유 15 GiB(경보선) → 가중치 Mac 경유(stage) 금지. 공개·비게이트 저장소(토큰 불필요)면 L4 VM에서 고정 revision으로 직접 받고 전체 해시를 manifest와 대조. 게이트면 멈추고 보고.
- 실행 호스트: 세 번째 프로젝트 L4 `ugrp-act-l4-gcp3`(gcp3setup READY 후). 공유 gcp2 L4는 쓰지 않음.
- 판단 모델 기본은 사용자 결정으로 CoreWeave fp4(plannerswap). llmhost는 비교 측정 전용, 기본 전환은 사용자 결정.

## 2026-10-16 사용자: "LLM을 GCP에 띄우는 건 일단 보류해줘"
보류. 가중치 다운로드·L4 기동·측정 모두 하지 않는다. PR #551은 draft로 유지.
