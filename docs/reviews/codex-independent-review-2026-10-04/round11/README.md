# 11차 체크포인트 — 기록에서 보정할 수 있는 것과 남는 미확인

2026-10-04. **보고서의 표본·ledger의 실행 identity·최근 fix와 실제 정보 기여를 분리했다.** 새 확정 결함은 선택 Gemini visual-team 보고의 latency 이중 집계(P3) 한 건이다. 나머지는 원래 source가 보장하는 범위와 실행 전 확인할 운영 제약이며 새 버그로 합산하지 않는다.

| 실용적 결과 | 지금 할 수 있는 판단 | 상세 |
|---|---|---|
| 신규 P3 · 선택 report | 한 실패 call의 latency alias를 별개 표본으로 세어100/300ms 두 call이233.3ms 평균으로 보일 수 있다. call별 하나의 latency가 필요하다 | [latency 보고](latency.md) |
| 실행 전 identity 확인 | 같은 ledger의 condition/seed/attempt key는 cohort가 달라도 충돌한다. 기존 실행/비용은 보호되며 새 budget·seed로 우회할 근거는 없다 | [ledger 운영 제약](runtime.md) |
| 현재 영상 진단 | fresh fix144개가 독립 정보144개를 뜻하지 않는다. 같은 view의 가중치를 줄이면서 최근 receipt를 유지하는 것은 명시된 설계다 | [receipt와 반복](vision.md) |
| collision guard 반증 | 검사한 고정-servo·세 constant-twist 경로는 sample 사이 displacement pad가 있다. 실제 물리·모든 actuator 경로의 안전 증명은 아니다 | [시간 표본 bound](geometry.md) |
| 기존 결함의 연구 영향 | 이미지 입력 누락은 고정 call의 default raw0.596s, grid0.5/0.6s 차이. 나중에 더하는 비용 보정으로 정책 trajectory나 성공 효과를 복원할 수 없다 | [영향의 경계](impact.md) |

현재 공개 uncertainty 중단의 첫 판별은 계속 [10차 제어 분기](../round10/pose.md)와 [관측·기록 판별표](../round10/research.md)다. 이번 receipt 해석은 이를 보완한다. 과거 [8차 runtime 결함](../round8/runtime.md), [ROI 조건부 결함](../round8/geometry.md), [10차 회수·시도 보고](../round10/README.md)를 중복 발견으로 세지 않는다.

Hold가 arm interpolation을 취소하는 새로운 relook mechanism은 조사 중이다. 원본 endpoint 실행과 기하 guard 통과 증거가 있어도 실제 view selector 연결이 닫히기 전에는 확정 목록에 넣지 않는다. 다음 상태는 [backlog](backlog.md)에 적었다.

기준은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`, #363 source `6727751b49ce11fb62234bb97274137f22850765` 및 README-only 후속 `de03fe87d08879abefaa7dac67c7ff313df5df89`다. 원본13개와 이전 회차 본문은 동결해 보존한다. [검증·재현 경계](validation.md)를 함께 읽어야 한다.

구현 변경·실제 physics·카메라 렌더·모델·cloud·실기기 실행은 없다. 합성 SQLite/process·HTTP/clock·source 수학 대조만 수행했다. raw/heldout outcome을 의도적으로 열어 분석하지 않았으며 앞선 코드검색의 부수적 공개 fixture 출처줄은 근거에서 제외했다. 전체 CI·전줄 정독·실제 오류빈도 또는 성능 효과를 주장하지 않는다.
