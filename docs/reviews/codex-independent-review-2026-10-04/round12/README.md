# 12차 체크포인트 — view 명령 완료와 worker 생성 실패

2026-10-04. **현재 개발 경로의 서로 다른 두 수정 대상을 좁혔다.** 실제 선택된 relook pan에서 상위 완료 상태와 port 발행 명령이 달라지는 제어 문제, 그리고 worker를 만든 직후 초기화 실패가 정리 책임 밖에 놓이는 문제다. 구현은 변경하지 않았다.

| 우선순위·범위 | 확인한 문제 | 바로 확인할 기준 |
|---|---|---|
| P2 · #363 relook | 실제 ranker의 세 방향을 실행하면 마지막 view의 upstream 목표와 port 발행 setpoint가 어긋난 채 예정 완료로 진행 | wheel stop·명시적 arm 취소 의미를 유지하면서 view 완료의 command 일치를 보장. [제어 근거](control.md) |
| P2 · #371 worker 초기화 | Popen 성공 뒤 selector 생성/등록 ENOMEM이 cleanup 앞에서 발생하면 반환되지 않은 worker를 상위 caller도 회수하지 못함 | 부분 초기화 상태에서 생성 즉시 ownership을 갖고 다음 attempt 전에 회수/실패를 명시. [runtime 근거](runtime.md) |

두 항목 모두 원본 source와 합성 collaborator를 사용하고 독립 재실행했다. 실제 robot joint, RGB/PF error, OS 자원 고갈의 빈도, 현재 공개 failure의 원인을 측정한 결과가 아니다. relook의 정확한 수치는 각 fixture의 port/host 시각 규칙에 한정한다. command 불일치와 실제 물리 tracking 오차를 구별해야 한다.

[연구 해석](research.md)은 미래 queue endpoint·상위 target·하위 issued setpoint를 분리하고, 무엇을 기록하면 명령 실패와 관측 부족을 가를 수 있는지 제안한다. 모델/observer 연결은 source로 확인했으며 실제 image likelihood를 실행한 결과가 아니다. [covariance 보조 검토](geometry.md)는 world normal·cap·fallback의 좁은 부정 대조이며 새 버그가 아니다.

기존 핵심 수정 항목도 계속 남아 있다. #371 a009 source에서 [8차 image SIM/최종 failure 분류](../round8/runtime.md), 그 연구 해석의 [11차 비용·기록 영향 경계](../round11/impact.md)를 함께 보라. 선택적 회수·보고 경로는 [10차](../round10/README.md), [11차 latency](../round11/latency.md)에 보존했다. 과거 ROI와 개발 trace 판정은 당시 SHA의 기록이며 최신 원인으로 승계하지 않는다.

Source cutoff: #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`(07:44:44Z 공식 확인), #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 이번 분석은 main의 새 head를 전면 감사한 것이 아니다. [독립 검증](validation.md) · [계속할 일](backlog.md). 이전1–11차 본문과 원고13개는 그대로 보존한다.
