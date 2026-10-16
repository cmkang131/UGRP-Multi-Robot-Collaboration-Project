# 20차 체크포인트 — 열린 CI·랜덤화 이슈의 현재 계약

**#6은 현재 테스트 경로와 최근 main 정상 상태를 확인했지만 옛 간헐 실패의 원인은 미확인이고, #213은 부분 구현과 현재 consumer의 차이를 구분해야 한다.** 두 이슈를 해결됐거나 새 구현 결함이 생긴 것으로 세지 않는다.

| 이슈 | 확인된 근거 | 지금 남는 질문 |
|---|---|---|
| [#6 CI 종료](ci.md) | 실제 과거 실패 checkout의 `1 != 143`, 현재 명시 suite 선택, main 33 jobs·8개 offline shard success. Target test AST는 유지됨 | 실패 경로에서 wrapper stderr가 assertion에 남지 않는다. 현재 정상 run이나 macOS cleanup 수정만으로 옛 원인 해결을 확정할 수 없음 |
| [#213 비전 랜덤화](randomization.md) | 병합된 PR282의 정지 외형 렌더·학습 이미지 증강은 존재. 26개 source와 authored XML/분포 대조 독립 검증 | 최종 HIGH는 OpenCV를 소비하고 그 학습망 robustness를 자동 상속하지 않음. 기존 학습 후속 이슈와 현재 consumer의 적용 계약을 재연결해야 함 |

새 실행은 작은 source 상수/XML 대조뿐이다. CI 재실행·physics·renderer·모델·학습·실제 이미지나 실험 결과 분석은 하지 않았다. CI의 해당 assertion과 checkout 인프라 발췌만 읽었으며 연구 raw artifact를 읽지 않았다. [독립 QA](validation.md)는 각각 source/status와 source/합성 범위를 구분한다.

현재 [16차 inspect/camera](../round16/posture.md), [15차 attachment](../round15/attachment.md), [#371 비용·실패](../round8/runtime.md)의 우선순위를 유지한다. 기존 O11·V2 calibration·worker 증인은 서로 다른 caller이므로 이번 두 이슈의 원인으로 합치지 않는다. 이슈 탐색의 앞선 범위는 [19차](../round19/issues.md), 다음 판단은 [backlog](backlog.md)에 연결한다.
