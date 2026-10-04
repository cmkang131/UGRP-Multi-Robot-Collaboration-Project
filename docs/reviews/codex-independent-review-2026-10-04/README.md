# UGRP 연속 독립 검토 — 2026-10-04

**[12차: 현재 제어·worker 경로의 두 수정 대상](round12/README.md)**. 실제 ranker가 고른 relook sequence에서 명령 완료 상태가 어긋나고, worker 생성 직후 초기화 오류에서는 정리 소유권이 빠집니다. 모두 조건과 음성 대조를 명시한 source·합성 재현이며 구현은 변경하지 않았습니다.

| 읽을 목적 | 문서 |
|---|---|
| 현재 개발 경로의 새 수정 대상 | [relook command 완료](round12/control.md), [worker 초기화 cleanup](round12/runtime.md) |
| 지금 uncertain look를 구분할 기록 | [command 계층과 모델](round12/research.md), [10차 실제 분기](round10/pose.md), [frame/scan/fix 판별](round10/research.md) |
| 이전 핵심 수정 항목과 연구 영향 | [8차 image SIM·failure 분류](round8/runtime.md), [a009 source 판정](round8/runtime-currentness.md), [11차 비용·기록 영향](round11/impact.md) |
| 선택적 회수·보고 경로 | [Colab 회수](round10/collection.md), [시도 보고](round10/reporting.md), [latency](round11/latency.md) |
| 근거와 계속할 일 | [12차 독립 검증](round12/validation.md), [backlog](round12/backlog.md), [원고13개](publication/README.md) |

지난 체크포인트: [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차 종합](publication/final-index-issue.md). 각 판정은 해당 SHA·시점에 한정한다. 과거 ROI·개발 trace는 당시 근거로 보존하며 새 head의 실제 실패 원인으로 승계하지 않는다. 과거 status/prompt 수정 인정은 [8차 followup](round8/frontier-followup.md)에 있다.

실제 물리/카메라 렌더/LLM/cloud 실행, 구현 변경, 전체 CI 통과 보고가 아니다. public static map과 admitted calibration 제품을 사용했고 raw/heldout outcome을 의도적으로 열어 분석하지 않았다. 부수적인 공개 fixture 출처 검색줄은 근거에서 제외했다. 실제 오류 빈도·현재 공개 실패 원인·통신 인과 효과는 별도 증거 없이 정하지 않는다.

GitHub는 Markdown만, 재현 script와 작은 결과는 별도 Mac 전달본에 보존한다. [증거 탐색](evidence/README.md).
