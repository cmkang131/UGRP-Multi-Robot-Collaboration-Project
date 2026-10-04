# UGRP 연속 독립 검토 — 2026-10-04

**먼저 읽을 문서: [현재 pair의 다음 판단](round14/decision.md).** 실패 tick의 direct predicate를 나누고, relook command 완료→frame→scan→fix→gate를 구분하는 최소 순서다. 공개 보고에 없는 phase/sigma는 unknown으로 남긴다.

현재 수정 대상은 [12차 relook command 완료](round12/control.md), [worker 초기화 정리](round12/runtime.md), 기존 [image SIM·failure 분류](round8/runtime.md)다. optional V2의 [13차 두 보정 결함](round13/README.md)은 현재 pair와 분리한다.

| 읽을 목적 | 문서 |
|---|---|
| 지금 어떤 설명부터 기각할지 | [14차 판단 메모](round14/decision.md), [짧은 경계 요약](round14/boundaries.md) |
| source에서 실행한 검사와 실제 보장 | [14차 검증](round14/validation.md), [10차 direct predicate](round10/pose.md), [frame/scan/fix](round10/research.md) |
| parameter를 실제로 구별하는가 | [optional servo plan의 동등성](round14/servo.md), [보정 provenance/consumer](round13/research.md) |
| 이전 비용·회수·보고 문제 | [비용/기록 영향](round11/impact.md), [Colab 회수](round10/collection.md), [시도 보고](round10/reporting.md), [latency](round11/latency.md) |
| 범위와 다음 일 | [14차 요약](round14/README.md), [backlog](round14/backlog.md), [coverage](round13/coverage.md), [원고13개](publication/README.md) |

14차는 새로운 구현 버그0개인 진단·식별가능성 검토다. checkpoint/observer/approach의 상세 negative coverage는 짧은 경계 문서로 모으고 Mac에 상세 증거를 보존했다. 전체 checkpoint 안전, 실제 carry GO, 실제 정보량, 실물 calibration precision을 검증했다고 확대하지 않는다.

지난 체크포인트: [13차](round13/README.md) · [12차](round12/README.md) · [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차](publication/final-index-issue.md). 각 판정은 해당 source SHA·시점에 한정하며 이전 본문·원고13개·출처는 보존한다.

source·합성 검토이며 실제 physics/render/학습/model/cloud 실행, 구현 변경, 전체 CI 통과 보고가 아니다. public map·admitted calibration 제품·합성 입력을 구별하고 raw/heldout outcome을 의도적으로 열어 분석하지 않았다. 부수적인 fixture 출처 검색줄은 근거에서 제외했다.

GitHub는 Markdown만, script·작은 결과는 Mac 전달본에 보존한다. [증거 탐색](evidence/README.md).
