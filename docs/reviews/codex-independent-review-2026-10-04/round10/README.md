# 10차 체크포인트 — 지금 막힌 uncertainty를 나누고 회수·보고 경계를 검증

2026-10-04. **현재 개발에서 가장 유용한 다음 판별은 거부 tick의 실제 predicate와, 영상 소비·PF 수치 갱신·새 informative fix를 구분하는 것이다.** 공개 저자 보고는 HIGH edge reference를 통과한 뒤 SELF_UNCERTAIN/POSE_UNCERTAIN에 도달했다. 이를 실제 raw replay나 특정 원인의 입증으로 바꾸지 않았다.

이번 신규 결함은 **선택 경로 두 건**이다. Colab 회수 완료 오판(P2)과 Gemini visual-team 시도 보고 누락(P3)을 실제 원본 함수와 작은 합성 대조로 재현하고 별도 검토자가 다시 실행했다. 현재 pair/live의 실제 실패 원인으로 합산하지 않는다.

| 우선순위·상태 | 판단과 다음 판별 | 근거 |
|---|---|---|
| 현재 blocker 진단 | reason 문자열만 보지 말고 admission failed_checks, gate 상태/회복 dwell, carry 분기, σxy/σyaw와 age를 같은 tick에서 구분 | [현재 uncertainty 분기](pose.md), [연구 판별표](research.md) |
| 현재 관측 해석 | PF scan은 가중치를 바꿔도 새 fix receipt는 못 받을 수 있다. 마지막 성공 quality를 현재 frame의 quality로 읽지 않는다 | [scan·edge 진단](vision.md) |
| 기존 활성 #371 P2 | 실패 호출의 이미지 SIM 비용, 단일 finalization 실패의 ledger 분류 불일치는 8차의 별도 수정 대상이다 | [8차 runtime](../round8/runtime.md), [a009 관련 경로 동일성](../round8/runtime-currentness.md) |
| 기존 조건부 #363 P2 | ROI 끝에 잘린 띠의 false edge 수용은 robustness fallback 성공과 다른 문제다. 실제 현재 실패의 원인·빈도는 미확정 | [8차 영상 기하](../round8/geometry.md), [수용 기준](../round8/geometry-acceptance.md) |
| 신규 P2 · 선택 Colab/Jev | 원격 완료 선언 5개 중 4개만 회수해도 complete/cleanup 허용. archive 무결성 검사는 통과하므로 기대 집합 누락을 따로 검증해야 한다 | [회수 완료](collection.md) |
| 신규 P3 · 선택 Gemini report | child 출력 전 실패한 시도가 runner 원장에는 있으나 report에서는 pending/attempted0. 성공률 왜곡 주장은 아님 | [시도 보고](reporting.md) |
| 새 버그 아님 | wire 정상·schema 유효·SIM release·delivery·request 포함은 다른 단계이며 마지막 통신 집계도 그 단계를 구분해야 한다 | [runtime 경계](runtime.md) |
| 음성 대조·정정 | parser/역할/시간/reset 가설의 좁은 반증, R9 fixture min_columns 4→6 보강(결과 동일) | [음성 경계](negative-controls.md), [검증·정정](validation.md) |

막힌 부분을 위해 [pose](pose.md) → [vision](vision.md) → [research](research.md) 순서로 읽으면 된다. 새로운 수정 후보는 [collection](collection.md)과 [reporting](reporting.md)에 최소 수용 기준을 적었다. [다음 backlog](backlog.md)는 완료·기각·미확인을 분리한다.

기준 source는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`, #363 `6727751b49ce11fb62234bb97274137f22850765` 및 README-only 후속 `de03fe87d08879abefaa7dac67c7ff313df5df89`다. 문서별 직접 실행과 소스 동일성 확인 범위를 구분한다. #372는 이번 결과의 대상이 아니다.

새 물리·렌더·LLM·학습·실기기·cloud 실행은 없다. 구현·설정도 바꾸지 않았다. raw/heldout outcome을 의도적으로 열어 분석하지 않았고, 앞선 코드검색에서 부수적으로 반환된 공개 fixture 출처줄은 근거에서 제외했다. 전체 코드 전줄 정독·전체 CI 통과를 주장하지 않는다. 과거 1–9차 본문은 동결된 기록으로 보존하고 이번 내용을 덧붙인다.
