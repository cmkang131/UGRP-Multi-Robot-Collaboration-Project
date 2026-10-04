# UGRP 연속 독립 검토 — 2026-10-04

**현재 개발 경로의 우선 수정 대상:** [12차 relook command 완료](round12/control.md), [worker 초기화 정리](round12/runtime.md), 기존 [image SIM·failure 분류](round8/runtime.md).

**[13차 추가 결과](round13/README.md)**는 optional V2 보정/학습 도구의 별도 두 P2다. 측정을 정정한 뒤 옛 점수로 재승격할 수 있고, 완전한 보정을 제공해도 CLI가 일부만 적용하면서 calibrated로 표시한다. 현재 pair v98/D5와 구분하며 실제 과거 피해나 물리 성능을 추정하지 않는다.

| 읽을 목적 | 문서 |
|---|---|
| 현재 uncertain look의 단계 구분 | [command 계층과 모델](round12/research.md), [10차 실제 gate 분기](round10/pose.md), [frame/scan/fix](round10/research.md) |
| optional 보정 도구 수정 | [평가 identity와 재승격](round13/stale-metric.md), [complete21→effective6](round13/consumer.md) |
| 보정 증거가 뜻하는 것 | [두 provenance 관문](round13/research.md), [공식 1차 근거](round13/primary-sources.md), [D5/v92 source 경계](round13/assembly.md) |
| 이전 비용·회수·보고 문제 | [비용/기록 영향](round11/impact.md), [Colab 회수](round10/collection.md), [시도 보고](round10/reporting.md), [latency](round11/latency.md) |
| 검토 범위와 계속할 일 | [coverage](round13/coverage.md), [13차 독립 검증](round13/validation.md), [backlog](round13/backlog.md), [원고13개](publication/README.md) |

지난 체크포인트: [12차](round12/README.md) · [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차 종합](publication/final-index-issue.md). 각 판정은 해당 SHA·시점에 한정한다. 이전 본문·원고13개·provenance는 보존하며 실제 수정된 status/prompt는 [8차 followup](round8/frontier-followup.md)에서 구분했다.

source·합성 검토이며 실제 물리/render/학습/model/cloud 실행, 구현 변경, 전체 CI 통과 보고가 아니다. public static map·승인 calibration 제품과 합성 측정값을 구별했다. raw/heldout outcome을 의도적으로 열어 분석하지 않았고 부수적 공개 fixture 출처 검색줄은 근거에서 제외했다. 실제 오류 빈도·현재 공개 실패 원인·통신 효과는 이 자료만으로 정하지 않는다.

GitHub는 Markdown만, script·작은 JSON은 별도 Mac 전달본에 보존한다. [증거 탐색](evidence/README.md).
