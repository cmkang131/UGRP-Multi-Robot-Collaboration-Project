# UGRP 연속 독립 검토 — 2026-10-04

**현재 수정·진단의 출발점은 [inspect 중단 뒤 camera/provider 실패](round16/posture.md), [HIGH checkpoint attachment 검사 누락](round15/attachment.md), #371의 [SIM 비용·실패 분류](round8/runtime.md)입니다.** 최신 체크포인트의 음성 결과가 이 문제들을 해결한 것은 아닙니다.

| 읽을 목적 | 문서 |
|---|---|
| 재관측 stop 뒤 frame/fix가 회복되지 않는 경로 | [16차 posture](round16/posture.md): issued key·settle·failure latch. 현재 source 합성 증거이며 raw stage 재생 아님 |
| 중간 정지 뒤 부착 beam 검사 가정 유지 | [15차 attachment](round15/attachment.md), [독립 검증](round15/validation.md) |
| #371 호출 비용과 실패 상태의 일관성 | [8차 runtime](round8/runtime.md), [a009 현재성](round8/runtime-currentness.md); worker 초기화는 [12차](round12/runtime.md) |
| 기존 로그로 어디까지 진단할 수 있나 | [17차 trace map](round17/trace.md): 같은 capture의 두 servo 필드와 기록되지 않는 값의 구분 |
| 최종 절차 종료와 성공 판정을 구분 | [17차 release](round17/release.md), [endpoint 경계](round17/boundaries.md#completion) |
| 기존 beam ROI 문제의 현재성 | [17차 source 확인](round17/beam-currentness.md): 현재 wrapper도 공유 detector의 수락을 보존; 현재 RGB 발생은 미확인 |
| 고쳐진 기존 문제 | [final veto](round15/fixed.md): 확인한 control/arm 두 caller에서 수정됨 |

[18차 요약](round18/README.md)은 optional Gemini replay의 [물리 source 검사 누락](round18/replay.md) 1건을 추가합니다. 실제 다른 물리 궤적의 통과를 입증한 것은 아닙니다. [Reference 자산 비교](round18/research.md)는 좁은 identity 검증이며 full admission·실행·학습 미노출로 확대하지 않습니다. Optional V2 [보정 두 결함](round13/README.md), [carry-align 통계 계약](round16/research.md), [공개 작성자 보고](round15/currentness.md)는 각각의 경로와 증거 수준을 유지합니다. [후속 독립 재도전](round18/backlog.md)을 계속합니다.

이전 체크포인트: [17차](round17/README.md) · [16차](round16/README.md) · [15차](round15/README.md) · [14차](round14/README.md) · [13차](round13/README.md) · [12차](round12/README.md) · [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차](publication/final-index-issue.md). 이전 본문·원고 13개·출처와 각 판정의 SHA·시점을 보존합니다.

소스 검토와 합성 대조이며 실제 physics/render/model/학습/cloud 실행, 구현 변경 또는 전체 CI 통과 보고가 아닙니다. Public map·admitted calibration·합성 입력을 구별하고 raw/heldout outcome을 의도적으로 열어 분석하지 않았습니다. 부수적인 fixture 출처 검색줄은 근거에서 제외했습니다.

GitHub는 Markdown만, Mac은 상세 원고·작은 script/result·선택된 exact source를 보존합니다. [증거 탐색](evidence/README.md).
