# 16차 체크포인트 — 재관측 중단, 실패 지속, 보정 보류의 뜻

2026-10-04. **현재 inspect 전환에서 알려진 camera 자세 사이를 움직이다 멈추면, 중간 명령 tuple이 camera 표에 없어 provider가 실패 상태에 남는 경계를 재현했다.** Source는 #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`,08:47 UTC 공식 재조회에서도 동일했다. 공개 저자의 raw trace를 재생한 결과는 아니며 source와 합성 입력의 독립 증거다.

| 이번에 확인한 질문 | 결과 | 활용 |
|---|---|---|
| 재관측 stop 이후 frame이 와도 왜 새 fix가 없을 수 있나? | Actual p45→inspect의 첫 upper command `765,1991,1865,1500`에서 queue 취소,0.2초 settle 뒤 미등록 camera key로 fail-closed. Receipt reset·known posture 복귀만으로 실패 latch는 안 지워짐 | [현재 command/camera 경계](posture.md). Wheel/emergency stop을 보존하면서 supported camera 전이와 provider 회복 수명을 구분 |
| carry-align의 `skip`이 정렬이 충분하다는 인증인가? | 아니다. Stored mean residual과 current report σ의 유의성 보류 정책. 같은 posterior의95% 구간 해석은 시점·분포 가정 필요 | [통계적 계약](research.md). 실제 carry 효과나 안전 확률로 해석하지 않음 |
| 새 PF·recovery·column 처리에서 무엇을 확인했나? | Roughening의 정확 RNG 경계, receipt 의미, recovery 실패 기록·단일 정리,96열 중심의 producer/consumer 정합 | [짧은 범위 요약](boundaries.md). Support 회복·task 성공·전체 pipeline 정확도로 확대하지 않음 |

이번 **새 버그 집계는0개**다. Posture 증거는 R12와 같은 명령 취소 계열의 최신 caller/실패 의미 후속 검증이다. R12 lower-port setpoint와 이번 upper issued camera key는 층이 다르며 동일 실제 run의 인과를 두 번 입증했다고 세지 않는다. 새 기능들의 negative/연구 대조도 별도 결함으로 바꾸지 않는다.

현재 수정 우선순위의 [15차 checkpoint attachment 문제](../round15/attachment.md)는 그대로 남는다. [same-tick final veto](../round15/fixed.md)는 확인한 두 caller에서 수정됐다. #371 [worker ownership](../round12/runtime.md)·[SIM/분류](../round8/runtime.md)와 optional V2 [보정 결함](../round13/README.md)은 다른 source 경로로 구분한다.

[독립 검증](validation.md) · [1차 문헌과 읽은 범위](primary-sources.md) · [다음 작업](backlog.md). 이전1–15차 본문과 원고13개는 보존했다. 실제 physics/render/model/학습/전체 CI 실행이나 구현 변경은 없다.
