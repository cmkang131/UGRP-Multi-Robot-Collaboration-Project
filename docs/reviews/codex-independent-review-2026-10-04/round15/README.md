# 15차 체크포인트 — 현재 부착물 검사와 수정된 취소 경계

2026-10-04. **새 현재 경로 문제 1건, 기존 문제 수정 확인, 연구·진단을 구분했다.** #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`의 HIGH checkpoint는 집게를 열지 않고 segment만 바꾸지만, guard의 attachment receipt는 과거 segment에 남아 beam 전체 형상이 검사에서 빠진다. 실제 최신 메서드와 별도 static geometry를 독립 재현했다.

| 분류 | 확인한 결과 | 다음 판단 |
|---|---|---|
| 새 현재 경로 문제 · P2 | command-held=True인데 geometry의 attached beam flag=False. 같은 합법 명령이 body-only에서는 허용되고 beam 포함 시 reserve −7mm로 거부됨 | [attachment identity](attachment.md). Route segment와 close epoch를 구분하면서 실제 open/cancel의 해제를 보존할 것 |
| 기존 문제 수정 확인 | 66ff의 final veto가 같은 tick peer abort 뒤 앞 actor의 motion/arm dispatch를 hold로 바꿈. Abort 없는 대조는 보존 | [수정 회귀 검증](fixed.md). 과거 반례는 역사적 증거로 보존하며 현재 미해결로 세지 않음 |
| 공개 현재 상태 · 저자 보고 | 새 stage는 carry에 못 도달했고 inspect/relook 중 명령·camera model 경계를 저자가 진단 | [현재성](currentness.md). Raw 재실행과 구분하고 checkpoint 결함을 현재 첫 실패 원인으로 사용하지 않음 |
| 연구·진단 · 새 버그0 | 절차 완료·관측 확인·별도 task predicate, 모델 행 수·축 지원, M1 작은 probe와 큰 pan 취소의 차이 | [성공 증거 계약](research.md), [진단 경계](diagnostics.md) |

부착물 문제는 receipt 생성부터 정상 lower READY/GO·callback·guard flag 전달까지 실제 source를 실행한 증거와, 실제 geometry 소비자의 독립 대조를 연결한 **한 finding**이다. 실제 물리 grasp prefix·충돌·낙하 또는 현행 route의 해당 pose/command 발생은 검증하지 않았다. Loaded uncertainty profile도 계속 적용되므로 모든 guard가 꺼진다는 뜻이 아니다.

R14 checkpoint fixture의 `beam_grasp_confirmed=True` collaborator는 시간/pose 분기만 검증했다. 이번 별도 경계가 그 범위를 명확히 한다. de03의 opening 다섯 pan 모델은 historical 진단으로 유지하고, 66ff의 새 여덟 방향 전체 분석으로 승격하지 않는다. PF/carry-align/relook delta의 넓은 기능 검토는 [다음 배치](backlog.md)다.

현재 #371의 [worker 초기화 정리](../round12/runtime.md), [image SIM·failure 분류](../round8/runtime.md), optional V2의 [보정 두 결함](../round13/README.md)은 별도 source 범위다. de03 [relook command-only 증거](../round12/control.md)와 최신 저자 진단도 동일 실행의 인과로 합치지 않는다.

[독립 검증과 재현](validation.md) · [문헌 원문 범위](primary-sources.md) · [이전14차](../round14/README.md). 기존1–14차 본문과 원고13개는 보존했다. 실제 physics/render/model/학습 실행, 구현 변경, 전체 CI 통과 판정은 이번 작업에 포함하지 않는다.
