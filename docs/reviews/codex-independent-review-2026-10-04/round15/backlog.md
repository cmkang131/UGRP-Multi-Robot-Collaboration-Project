# 15차 이후 진행 큐

| 상태 | 범위 | 다음 확인 |
|---|---|---|
| 검증 완료 · 새P2 | 최신66ff checkpoint receipt→attached beam geometry 누락 | 같은 close epoch와 route segment의 수명 분리, open/cancel 대조 보존. 구현은 별도 작업 |
| 수정 확인 | 66ff control/arm same-tick final veto | 현재 두 caller에서 수정됨. 과거 본문은 보존 |
| 후속16차 | 최신 inspect/relook·PF roughening·carry-align significance | 각각 실제 caller/command/model 계약으로 한정; 저자 raw 진단과 독립 증거를 구별 |
| 후속 | HIGH 최종 lower→open→retreat→done | 절차 완료와 allowed observation, 별도 task success를 연결하되 GT를 정책에 넣지 않음 |
| 범위 완료 · 새bug0 | de03 다섯 pan 모델 민감도, optional M1 handoff | 새66ff 전체 pan·실제 영상 품질·실물 joint와 성공으로 확대하지 않음 |
| 이전 source 범위 유지 | #371 worker 정리·SIM billing·failure 분류, optionalV2 calibration | [12차](../round12/README.md), [8차](../round8/runtime.md), [13차](../round13/README.md)의 pin별 근거를 사용 |

현재 공개 stage는 carry 전에 멈췄다는 작성자 보고다. 이번 checkpoint attachment 불일치를 그 첫 실패의 원인으로 쓰지 않는다. R14의 checkpoint time/pose 증인은 attachment=True collaborator의 범위로 유지한다. 새 finding 수를 채우기 위해 동일 원인·음성 대조·연구 설계 한계를 중복 집계하지 않는다.

이번 게시를 끝으로 작업을 종료하지 않는다. 후속 source 검토와 독립 QA를 별도 체크포인트로 이어가며, 이전1–15차 snapshot/원고13개/재현 원본을 소급 수정하지 않는다.
