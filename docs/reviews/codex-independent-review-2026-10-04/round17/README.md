# 17차 체크포인트 — 절차 종료와 기록의 연결

2026-10-04, #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`. **최종 lower/open/retract/retreat 의 실제 제어 경계와, 그 뒤 양쪽 done 을 기다리는 endpoint 계약을 분리해 검증했다.** 실제 물리 release·도착·task 성공을 새로 입증한 결과는 아니다. 새 버그 집계 0개이며 기존 beam ROI finding 의 현재성도 별도로 닫았다.

| 이번 결과 | 확인한 범위 | 다음 활용 |
|---|---|---|
| [최종 제어 순서](release.md) | 정상 lower/open READY/GO→상위 command/retract→retreat→done; partner abort/silence·sample 부족·open 미준비 대조 | Released 후 6 초 창과 실제 reverse 발행 시작을 구분. Commanded floor/절차 done 을 접촉·성공으로 읽지 않음 |
| [Endpoint 완료](boundaries.md#completion) | 선언된 done/open prefix 뒤 actual endpoint/status/job 의 양쪽 done·지연·abort·silence·invalid image 5조건 및 중복 종료 대조 | PAIR_SEQUENCE_DONE 의 결과는 unconfirmed/holding unknown; 별도 evaluator 와 혼합하지 않음 |
| [어떤 기존 로그를 연결할 수 있나](trace.md) | Frame identity,두 servo 필드,job/phase,stored mean/current sigma,delay timing,guard 상세의 실제 writer 계약 | 같은 capture 의 명령 불일치부터 확인. 저장되지 않은 mean/revision/consumed time 은 추측으로 채우지 않음 |
| [기존 beam ROI 문제의 현재성](beam-currentness.md) | R8 공유 detector 동일+새 wrapper가 수락 결과를 그대로 반환+현재 HIGH caller 유지 | 소스상 해소되지 않음. R14 wall-band negative와 다른 경로이며 현재 RGB 발생은 미확인 |
| [작은 covariance 정밀도](boundaries.md#precision) |40µm 의 authored belief 에서 출력 반올림이 gate 와 command 값에 전달될 수 있음 | 실제 도달성·운반영향 미입증, 추가 P2/P3 로 세지 않는 한정 경계 |

현재 우선 수정 대상인 [15차 attachment identity](../round15/attachment.md), [16차 중간 camera posture 실패](../round16/posture.md)를 유지한다. [같은-tick final veto](../round15/fixed.md)는 검증한 두 caller 에서 수정됐다. 상세 source 원고와 작은 재현/manifest 는 Mac evidence 로 보존하고 [독립 검증](validation.md)에서 범위를 모았다.

원래 1–16차 본문과 원고 13개를 소급 수정하지 않았다. Actual physics/render/model/학습/전체 CI 나 raw 실험 재생은 없으며, 다음 [18차 검토](backlog.md)를 계속한다.
