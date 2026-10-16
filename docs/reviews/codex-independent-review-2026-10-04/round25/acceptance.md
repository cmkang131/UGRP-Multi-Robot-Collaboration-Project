# R25 · 열린 이슈의 남은 인수 증거와 다음 source 검토

R19에서 공식 조회한 16개 open 이슈에 R20–23의 좁은 검토를 더한 **작업 선정표**다. 이번 표를 위해 이슈 상태를 다시 조회하지 않았으며, 이슈를 해결 처리하지 않는다. 이전 [16개 이슈 표](../round19/issues.md)의 시점·source pin과 각 보고서의 범위를 유지한다. 실행·원자료·실물 인수 증거가 필요한 항목을 더 많은 source 리뷰로 대체하지 않는다.

| 이슈 | 현재 남은 구체 범위 | 다음 source 검토로 할 수 있는 일 / 제외할 반복 |
|---|---|---|
| #3 원본 보관·복구 | 남기기로 한 대표 입력의 허가 위치·읽기/hash·별도 환경 복구 기록 | R22에서 배포/회수/로컬 이동과 독립 복구를 구분했다. 새 source 불일치 없음. 실제 보존·복구를 열거나 실행하지 않는다. |
| #6 CI 간헐 종료 | 과거 실패의 실제 원인과 현재 지속 여부 | R20에서 현재 지원 test·최신 main 성공과 과거 원인 미확인을 나눴다. 같은 source를 다시 읽거나 green run을 과거 원인 해결로 승격하지 않는다. |
| #213 도메인 랜덤화 | 학습용 appearance randomization과 현행 OpenCV provider 사이의 수용 계약 및 독립 비교 | R20은 PR282 구현과 current provider 미소비를 구분했다. 추가 학습·렌더·결과 열람 없이 효과를 입증할 새 source caller는 현재 선정하지 않았다. |
| #214 실물 단계 검증 | H0 실물 사진부터 H1–H4 수행·현장 지도/환경 identity·실제 시간 비용 | 실물 인수는 source로 증명할 수 없다. **R25 후보:** 기존 REAL CLI의 trace 생성→Pi skill 기록→분석 consumer에서 frame/명령/완료/시간의 의미. R3 motor stop·servo settle·pose/camera transport를 다시 결함으로 세지 않는다. |
| #216 위치추정 | 최종 표식 없는 관측의 실제 정확도·오류/불확실성 calibration·환경 적용 | R14/16 관측·카메라 자세 경계와 R23 active frontier의 담당 범위를 우선한다. 정적 좌표 일치가 정확도를 보장하지 않으므로 새 source만으로 인수 종료하지 않는다. |
| #217 기억·다시 보기 | 선택한 provider와 등록된 비교 입력의 연결, 실제 짝 맞은 look-policy 효과/오판 집계 | R23은 selector/common safety/default tag를 source로 연결했다. OFF의 추적 기억 유지와 downstream exposure 변화를 명시했다. 같은 경계를 반복하지 않는다. |
| #218 최종 환경 | 고정 환경에서 실제 M1/M2·loaded 접촉/문 통과 인수와 선언된 조건 일치 | R4 기하·R13 route caller는 정적/source 증거다. 실제 환경 수용을 대신할 새 미검토 caller는 이번 선정에서 찾지 않았다. |
| #219 최종 M1/M2 | 작성자 진단 보고와 분리된 최종 학생 수행·loaded 조건·현재 blocker의 실제 최초 원인 | R15/16 반례를 공개 실패의 원인으로 확정하지 않는다. 기존 후보 채점·raw 재분석 없이 source finding 개수로 진도를 환산하지 않는다. |
| #220 그림자·가림 | S1 gate와 보고 전용 A3의 후속 인수 기준, 최종 환경의 독립 영상 평가 | R21은 evaluator의 단위·문턱과 현재 caller 범위를 연결했다. known `unknown or 1`이나 같은 wrapper를 재발견하지 않는다. |
| #221 own-camera 실행기 | 3대 전체 smoke 및 실제 release/task success | R15 두 caller abort 수정 확인과 R17 release/done 경계를 유지한다. 새 active caller는 frontier 담당과 조율하며 기존 terminal 검사를 반복하지 않는다. |
| #222 대화 adapter | a009 경로의 실제 허용 입력/대화 실행과 남은 구현 수정 확인 | R8–11의 비용·응답 admission과 현재 별도 frontier 후보를 우선한다. accepted reply만으로 행동 변화나 이득을 증명하지 않는다. |
| #223 4조건·리더·비용 | 3대/4조건의 실제 통합, 입력·비용·시간에 맞는 비교 | 보존 #371 2대/3조건 feasibility를 이 이슈 완료로 바꾸지 않는다. source 비용식과 실제 조건별 빈도/효과는 별도다. |
| #224 smoke→pilot→본 실험 | 단계별 허용/관측/referee 성공과 실제 등록 연구의 완료 증거 | R18 reference 자산 prefix, HIGH controller done 및 DEV 절차는 각각 제한된 증거다. 새로운 실험 admission이나 연구 완료를 이번 표로 승인하지 않는다. |
| #225 교사 지원 | 공개 N1의 실제 TOP 인식 수정·교사 시연 및 남은 선언 순서 인수 | R21이 현재 teacher TOP consumer/threshold를 확인했다. 교사 feasibility와 학생 입력/성공을 합치거나 재렌더 없이 과거 원인을 확정하지 않는다. |
| #226 저장·속도·기록 | 실제 보존 정책 적용·복구, 운영 성능/UI, 기록으로 가능한 진단 범위 | R3/R17/R18/R22의 서로 다른 기록·재생·보존 경계를 유지한다. #214와 같은 R25 REAL trace caller를 한 번 검토하며 별도 신규 발견으로 중복 집계하지 않는다. |
| #366 E2E 이후 방향 | 첫 LLM E2E 뒤의 실물/위 카메라/로봇별 지도 방향 결정 | 공개 사용자 보류 결정이 있다. self-map/VO 구현·실물 착수를 새로 고르지 않는다. |

이번에 새로 고른 하나는 **REAL 플랫폼 진단 trace의 실제 CLI 연결**이다. `docs/real_trace_system.md`와 `docs/real_execution_recorder.md`가 설명하는 소비 frame·detection·command·completion이 `harness.execution_trace`/`trace_analysis`와 연결되는 지원 caller부터 확인한다. source/작성한 가짜 입력으로 검증 가능한 기록 identity·시간·분석 의미만 다루며, issued/completed/measured를 구분한다. 카메라·하드웨어·외부 통신·과거 frame 원본은 실행하거나 열지 않는다. 이 경로가 현재 지원되지 않거나 이미 깊게 검토됐으면 그 근거로 후보를 닫는다.

선정 뒤 확인한 결과와 독립 검증은 [R25 REAL trace clock 원고](clock.md)에 분리했다. 이 표는 후보를 고른 당시의 범위 기록으로 남긴다.

R20 #213 및 R21 #220/#225의 후속 범위는 각 독립 보고서를 읽어 반영했다. 이 표는 모든 코드의 미검토 영역이 없다는 증명이 아니며, 현재 승인 범위에서 새로운 가치가 확인된 다음 caller 하나를 고르기 위한 기록이다.
