# UGRP 연속 독립 검토 — 2026-10-04

**현재 수정·진단의 두 출발점은 [HIGH checkpoint attachment](round15/attachment.md)와 [inspect 중단 뒤 camera/provider 실패](round16/posture.md)입니다.** 전자는 최신66ff의 새 부착물 검사 결함이고, 후자는 명령 취소 계열의 현재 caller·영향 범위를 추가 확인한 증거입니다. 같은 원인을 새 버그로 중복 집계하지 않습니다.

| 읽을 목적 | 문서 |
|---|---|
| 중간 정지 뒤 beam 검사 가정 유지 | [15차 attachment](round15/attachment.md), [독립 근거](round15/validation.md) |
| 재관측 stop 뒤 왜 frame/fix가 회복되지 않을 수 있나 | [16차 current posture](round16/posture.md). Actual issued key/settle/failure latch; raw stage replay 아님 |
| 보정 보류가 무엇을 인증하는가 | [carry-align 통계 계약](round16/research.md). Skip≠small error,95%≠task safety |
| 새 기능에서 배제한 설명 | [PF/recovery/column 경계](round16/boundaries.md), [QA](round16/validation.md) |
| 고쳐진 기존 문제 | [같은-tick terminal final veto](round15/fixed.md), 확인한 control/arm caller에서 수정됨 |

#371 [worker 초기화 정리](round12/runtime.md)·[image SIM/failure 분류](round8/runtime.md), optional V2 [보정 두 결함](round13/README.md)은 다른 source 경로로 구분합니다. 최신 [공개 작성자 보고](round15/currentness.md)와 source 합성 증거, 실제 물리 결과를 합산하지 않습니다.16차 신규 버그 집계0개이며[다음 검토](round16/backlog.md)를 계속합니다.

이전 체크포인트: [16차](round16/README.md) · [15차](round15/README.md) · [14차](round14/README.md) · [13차](round13/README.md) · [12차](round12/README.md) · [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차](publication/final-index-issue.md). 이전 본문·원고13개·출처를 보존하고 각 판정의 SHA·시점을 유지합니다.

Source·합성 검토이며 실제 physics/render/model/학습/cloud 실행, 구현 변경 또는 전체 CI 통과 보고가 아닙니다. Public map·admitted calibration 제품·합성 입력을 구별하고 raw/heldout outcome을 의도적으로 열어 분석하지 않았습니다. 부수적인 fixture 출처 검색줄은 근거에서 제외했습니다.

GitHub는 Markdown만, Mac은 상세 원고·작은 script/result·선택된 exact source를 보존합니다. [증거 탐색](evidence/README.md).
