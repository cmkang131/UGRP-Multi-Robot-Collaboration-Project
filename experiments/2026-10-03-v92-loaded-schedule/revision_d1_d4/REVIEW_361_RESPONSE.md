# review-361 답변

검토 대상 `a9481446d9c7c503bdbc53941d3538cd5ec5ee12`, 검토 기록 `4ee5ff52ea53153c0fe6ab8d6decf18d6daa2740`의 댓글과 전체 검토서를 읽었다. 현재 HIGH/B″ 개정은 다른 후보이므로 이전 판정·독립 물리 수치·학생 자세 보존 PASS를 승계하지 않는다. 작성자의 짧은 검사와 검토자의 재현 횟수도 합산하지 않는다.

## P1: 카탈로그 회귀 수정

아직 적용되는 병합 전 지적 1개를 수정했다. 카탈로그 기대 개수를 **48**로 갱신하고 `zone-final-pair-loaded-v92`의 plan 예시에 `--check calibration-loaded`, `--map-id zone_wide_two_doors_final_v3`, 40자리 `--expected-source-sha`를 추가했다. 오래된 thirty 함수명은 등록 카탈로그를 뜻하는 이름으로 고쳤다. `.github/workflows`나 CI 제외 목록은 수정하지 않았다.

카탈로그/계획 회귀는 **`4 passed, 14 deselected in 0.22s`**다. 기존 실패 두 개를 포함하며 다른 두 계획 테스트도 통과했다. 프로세스 수명 등 변경 범위 밖 14개는 이번 명령에서 선택하지 않았고 원격 전체 CI는 새 SHA에서 별도로 돈다. [명령·로그·JUnit 해시](review_361_fix_validation.json). 앞선 새 v92 27개와 관련 의존성 89개 통과는 그대로이며, 이번 수정은 테스트와 기록뿐이다. B″·일정·실행 코드 해시는 변하지 않았다.

## 나머지 권고의 처리와 남은 조건

| 검토 권고 | 반영 또는 남은 조건 |
|---|---|
| 전진/옆 c0·정지/램프 | D3로 이미 본 v88 탐색 근거와 비음수 하한 0을 B″에 고정했다. .006을 정지로 단정하지 않고 .001/.002/.004도 관측 전 분류하지 않는다. PRBS는 검증, v91 held-out은 열람 금지 유지. 내부해·잔차·실제 지지는 새 D5 분석기에서 확인해야 한다. |
| 바닥 파지 상태 | D2에 따라 24 mm는 파지·들기 준비뿐이다. loaded 운동·카메라는 HIGH만 정의한다. 상승/접촉 게이트를 삭제하거나 unloaded 값을 복사하지 않았다. 새 로더 계약은 D2 담당자와 조립기의 후속 작업이다. |
| 학생 HIGH 채택 | 이 PR은 수집 경로다. 별도 v93 학생 제어기/계약 제안과 연동하며, 기존 학생이나 그 보정값을 수정하지 않았다. 실제 RGB/BeamEdgeTracker·전이/운반 인수는 조정자에게 남긴다. |
| 8초 준비/측정 | D4를 새 B″의 loaded 선택으로 고정했다. 모든 7개 카메라 구간은 반열린 8초 측정 창이며 마지막 팔/팬/이동 뒤 8초 이상 준비한다. 1 mm/0.1°·최소 표본·전체 원본과 기존 B′는 유지한다. |
| v92 reader·혼합 명령 | D5 별도 분석기/조립기가 v92 ID·720초·해시·표본·역할을 감사하고 공동/상대 회전을 분리해야 한다. v88 조립기는 수정하지 않았으며 rank3을 13계수 인수로 표시하지 않는다. |
| 팬/자세별 모형 | HIGH에서 운동과 쌍 측정을 모두 하므로 hover 운동 모형의 자동 전용이 없다. 팬 1480–1520 범위를 유지하고 그 밖에 적용하지 않는다. 실제 모형 승인은 아직 없다. |
| 전체 수집 순서 | B″·일정·조립기 해시를 #219에 함께 고정한 뒤 조정자가 렌더 수집을 진행해야 한다. 전체 720초 접촉·상대회전·종료 하강, 실제 RGB, 선별 후 288개 명령 지지·적합/잔차·학생 인수는 짧은 첫 70초 검사로 대체하지 않는다. |

새 HIGH/B″ 변경 범위의 독립 재검토와 새 SHA 필수 CI는 남아 있다. 이 답변을 독립 승인이나 병합·수집·학생 운반 승인으로 표시하지 않는다.

## 참고 자료

- [독립 검토 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361#issuecomment-5966324406)
- [전체 검토서의 고정 소스](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/4ee5ff52ea53153c0fe6ab8d6decf18d6daa2740/experiments/2026-10-03-v92-loaded-schedule/REVIEW_361.md)
- [D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)
- [현재 설계·검증](../README.md), [B″](../criterion_B_double_prime.json), [이전·새 일정 해시](schedule_receipt.json)
