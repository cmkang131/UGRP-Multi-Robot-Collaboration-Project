# R26 · 다중 물체 임무→단계→완료의 독립 범위 QA

**원래 source를 실행한 좁은 재현과 완료/자원 handoff의 source 해석은 PASS다.** 저장된 실험이나 모델·물리·렌더·카메라를 실행하지 않았으며, 이 판정을 실제 물체 배치·운반 성공으로 읽지 않는다.

`mission-stage-boundary-repro.py`를 새 임시 디렉터리와 별도 Python subprocess에서 실행했다. exit 0, stderr 없음, 담당자 결과와 전체 JSON bytes가 같았다. 결과 SHA256은 `cc4911c4a3f9bc17511f6feccff7e51bb0c6f965f59ffa2b2d0e482161956bc3`, 재현 script SHA256은 `424c44eea9fd3c84efc2a7460d84a034b1de828f83fc51f3fadf53a779bbb654`다. 결과에 기록된 source 8개를 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` Git blob과 별도로 대조했다. `mission-stage-boundary-independent-check.json` (Mac 전달본 증거).

## 실제 실행한 범위

| 확인 | 정확한 범위 |
|---|---|
| 합의→임무 lease→단계→포트 | 실제 `TeamAgreement`, `MissionProtocol`, `MultiObjectExecution`, `TaskStageExecution`, `TaskStageSync`, `CameraRobotPort`를 실행했다. dispatch의 reply/action validator는 원래 AST body다. |
| 정상 작업 연결 | 작성한 상자 하나가 r2 `solo` 역할로 staging→final 두 작업을 거친다. 각 작업의 APPROACH/GRASP/LIFT/TRANSIT/LOWER/RELEASE 발행 기록과 완료 claim을 확인한다. 3로봇 plan ACK는 있지만 2대 공동 운반 명령을 실행한 대조는 아니다. |
| 작업 identity | 다른 task ID로 바꾼 Ticket은 직접 `report_done` consumer에서 거부되고 상태가 유지된다. 이전 작업의 outer reply는 다음 작업의 request에 재사용됐을 때 거부되며 명령 수가 늘지 않는다. 후자는 outer request identity 검증을 포함한 대조이고, task ID 하나만의 독립 효과라고 표현하지 않는다. |
| 임시 슬롯과 후속 작업 | staging 작업 완료 뒤 resident를 유지하고, 같은 object의 후속 작업이 끝나면 final resident로 옮기는 논리 bookkeeping이다. 물체가 그 슬롯에 실제로 있다는 증거가 아니다. |
| revoke | APPROACH 명령 뒤 plan을 무효화하면 실제 tick이 중단되고 fake motor sink의 마지막 값이 0이며 lease는 유지된다. 물리 정지·servo 피드백·충돌 없음의 증명이 아니다. |

tracker는 작성자가 만든 항상-valid 협력자이고 READY/DONE은 작성한 visual claim이다. 이미지 bytes는 디코딩되지 않는 placeholder이며 실제 RGB identity, perception 정확도, lane 기하, 모델 계획/응답, 실제 physics는 검증하지 않는다. `physical_success='separate_evaluation_only'` 출력이 이 범위를 잘 구분한다.

## source challenge

`MultiObjectExecution.batch:189–194`는 단계 advance가 성공하고 phase가 FINISH일 때에만 participant 전원의 `report_done`을 전달한다. `MissionProtocol.report_done:255–278`은 ticket/계획/object/증가 sequence/신선도/pre-grant 조건과 전원의 최신 완료 보고를 확인한 뒤 lock을 해제하고 resident를 갱신한다. 첫 participant 호출의 False 반환을 버린다는 한 줄만으로 결함이라 판단하지 않았다. 정상 actual batch는 모든 사람을 같은 now에 전달하고 identity 신선도 0.8초를 앞서 확인하며 protocol에도 같은 한도를 사용한다.

후속 작업의 `after`는 `observe:94`와 `grant_ready:232` 양쪽에서 completed를 요구한다. 완료 때 같은 object의 이전 resident만 제거하고 새 목적 슬롯을 점유한다. `MultiObjectExecution.summary:230–233`은 protocol-only의 실행 미지원 라벨을 실제 bounded-port 설명으로 덮고 물리 성공을 별도 평가로 남기므로, 내부 protocol summary만 떼어 현재 caller의 결과 라벨이라고 쓰지 않는다.

`TaskStageExecution.receive`는 producer reply를 실제 pending capture 문맥과 연결하고, `TaskStageSync.receive`는 DONE에 마지막 command 및 command 종료 이후 관측을 요구한다. 이는 문자열/시각/identity 계약이며 영상 내용이 보고를 지지한다는 인증은 아니다. 현행 `TaskPlan:76–77`은 명시적 `solo` 역할을 지원한다. 이전 sync 문서의 최소 2인 문장만으로 이번 새 caller의 solo 경로를 무지원으로 판단하지 않았다.

## 앞선 검토와 구별

R2의 task-stage port cancellation은 테스트 대조 범위였다. 대조한 R2/R3/R4/R7/R13 보고서에서는 이번 multi-object mission dependency/resource→stage→completion caller의 심층 감사가 확인되지 않았다. 이는 선정한 보고서 안에서의 coverage 확인이며 전 저장소나 모든 리뷰 기록의 부재 증명이 아니다. R3에서 이미 읽은 crew engine, R4의 carry history/data, 이전 final-pair abort를 새 영역으로 다시 세지 않는다.

이 QA는 위 fixture와 선정 source 계약의 검증이다. 전체 live runner, 모든 mission topology, 다중 task 동시 실행, 공동 운반, 원격 네트워크나 실제 시계의 검증으로 확대하지 않는다. 이 경로의 문서는 공용 TOP RGB를 허용하므로, 현재 HIGH의 own-camera 전용 계약을 소급 적용해 새 입력 누출로 분류하지 않는다.

## 최종 원고 대조

[담당자 원고](README.md) SHA256 `994338d312048037d420454f0bbf2b28b223177466c973747f86c31aebc311af`의 solo 범위, 직접 consumer/outer reply 대조, reported slot bookkeeping과 별도 물리 평가 한정을 최종 확인해 **PASS**로 판정했다. source manifest 19개 항목도 Git blob hash와 일치했다. 이 추가 hash 대조는 19개 전체 동작의 전수 감사가 아니며, evaluator는 `run_multi_object_execution.py:105–126,219–227`의 종료 후 호출과 terminal-placement 범위를 source로만 읽었다. 현재성 API를 이 QA에서 다시 조회한 것은 아니다.

최종 추가한 공동 2대 분기 triage도 source-only 범위로 수용한다. `command_participants:367–377`의 GRASP 미완료 peer 선택과 결합 단계 전원 미완료 조건, 상위 `batch:181–201`의 전달·이력, 기존 `test_multi_object_execution:35–46,82–102,212–224`의 r1/r3 beam 전 단계·missing-partner 및 `test_task_stage_execution:258–312`의 부분 GRASP·완료 peer 불변·결합 단계 거부를 대조했다. 해당 기존 테스트는 실행하지 않았다. 이 근거는 참가자 수만 늘린 다음 라운드를 만들 필요가 없다는 선정 판단이며, 이번 solo fixture의 실행 범위를 공동 운반으로 확대하지 않는다. 재현 예제도 보존 결과가 아닌 새 `/tmp` 파일을 출력 대상으로 쓰도록 바뀌었음을 확인했다. script와 golden hash는 그대로이며 추가 재실행은 하지 않았다.
