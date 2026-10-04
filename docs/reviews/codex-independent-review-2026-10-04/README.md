# UGRP 연속 독립 검토 — 2026-10-04

**[10차 현재 우선순위와 결과](round10/README.md)**부터 읽으면 됩니다. 현재 uncertainty 중단의 실제 판정 분기와 scan/fix 의미를 나눴고, 선택 Colab 회수 완료(P2)·Gemini 시도 보고(P3)를 새로 독립 재현했습니다. 구현 코드는 변경하지 않았습니다.

| 읽을 목적 | 문서 |
|---|---|
| 지금 막힌 원인 집합 좁히기 | [제어 판정](round10/pose.md), [scan·edge](round10/vision.md), [연구 판별표](round10/research.md) |
| 새 수정 후보와 수용 기준 | [회수 완료](round10/collection.md), [시도 보고](round10/reporting.md) |
| 런타임·지표 해석 및 반증 | [runtime](round10/runtime.md), [음성 경계](round10/negative-controls.md), [독립 검증](round10/validation.md) |
| 기존 활성 core 문제 | [8차 비용·종료 기록](round8/runtime.md), [ROI 기하](round8/geometry.md), [개발 경계](round8/frontier.md) |
| 지난 체크포인트 | [9차](round9/README.md), [8차](round8/README.md), [1–7차 종합 원문](publication/final-index-issue.md) |
| 계속 검토할 일 | [backlog](round10/backlog.md) |

각 문서의 현재/최신 판정은 명시한 SHA와 시점에 한정합니다. 공개 저자 보고와 자체 합성 재현을 구분하며 실제 물리 실패 원인·빈도·통신 인과 효과는 미확정입니다. 기존 status/prompt와 start-relief 수정 인정은 [8차 수정 검증](round8/frontier-followup.md)에 남아 있습니다.

1–7차 원고13개와 이전 회차 본문·과거 manifest는 바이트 그대로 보존했습니다. [원문 목록](publication/README.md), [증거 탐색](evidence/README.md). 소스 검토·작은 합성 대조이며 전체 코드 전줄 정독·전체 CI 통과 보고가 아닙니다. 새 physics·카메라 렌더·LLM·학습·실기기·cloud 실행은 없습니다. raw/heldout outcome을 의도적으로 열어 분석하지 않았고 부수적인 공개 fixture 출처 검색줄은 근거에서 제외했습니다.

GitHub에는 Markdown만 있습니다. 재현 스크립트·소규모 결과와 필요한 source 설명은 Mac 전달본에 보존합니다.
