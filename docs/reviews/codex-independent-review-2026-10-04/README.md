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

[22차 검토](round22/README.md)는 #3 원격 보관·복구의 문서 계약과 아직 확인하지 않은 운영 증거를 구분합니다. 선별 보존 승인은 존중하며 프로젝트 원자료의 복구 완료를 주장하지 않습니다. 새 결함 0개입니다. [21차 그림자·teacher TOP](round21/README.md), [20차 CI·랜덤화](round20/README.md), [19차 우선순위](round19/README.md)도 유지합니다. **이 리뷰의 Git/Mac 전달 hash 검증은 프로젝트 원본의 별도 환경 복구 검증과 다릅니다.** [다음 source 조사](round22/backlog.md)를 이어갑니다.

이전 체크포인트: [21차](round21/README.md) · [20차](round20/README.md) · [19차](round19/README.md) · [18차](round18/README.md) · [17차](round17/README.md) · [16차](round16/README.md) · [15차](round15/README.md) · [14차](round14/README.md) · [13차](round13/README.md) · [12차](round12/README.md) · [11차](round11/README.md) · [10차](round10/README.md) · [9차](round9/README.md) · [8차](round8/README.md) · [1–7차](publication/final-index-issue.md). 이전 본문·원고 13개·출처와 각 판정의 SHA·시점을 보존합니다.

소스 검토와 합성 대조이며 실제 physics/render/model/학습/cloud 실행, 구현 변경 또는 전체 CI 통과 보고가 아닙니다. Public map·admitted calibration·합성 입력을 구별하고 raw/heldout outcome을 의도적으로 열어 분석하지 않았습니다. 부수적인 fixture 출처 검색줄은 근거에서 제외했습니다.

GitHub는 Markdown만, Mac은 상세 원고·작은 script/result·선택된 exact source를 보존합니다. [증거 탐색](evidence/README.md).
