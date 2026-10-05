# R26: solo r2·상자 1개의 mission 예약, 단계 완료, 슬롯 인계

**새 결함 0건.** 등록된 실험용 `multi-object` 경로에서 solo r2·상자 1개의 staging→final에 원래 합의·예약·단계·포트를 연결한 작은 작성 fixture는 문서의 보고 기반 완료 계약과 일치했다. 공동 2대 운반의 실행 검증이나 운반 성공·물리 안전성 재현이 아니다.

기준 소스는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`다. 별도 담당자가 확인한 공개 currentness는 `current-frontier-refresh.json`에 있다. 검토 소스 19개의 정확한 hash는 `mission-stage-source-manifest.json`, 실행한 원본 8개의 hash는 결과 JSON에도 기록했다. 읽은 작업 트리 파일들은 해당 Git 소스와 byte가 같았다. 구현은 변경하지 않았다.

## 선정 근거와 실제 호출자

초기 AST 파일 목록만으로 공백을 판단하지 않았다. 기존 coverage와 독립 담당자의 대조에서 generic crew, learned carry/history, checkpoint/resume는 이미 깊게 읽은 범위라 제외했다. R2의 task-stage cancellation 검토와 R3/R4/R7/R13의 관련 범위에는 **상위 multi-object mission의 dependency/resource lease가 TaskStageExecution 완료와 이어지는 의미**가 직접 닫혀 있지 않았다. 이번 범위는 하위 취소 기능의 반복 검증이 아닌 이 상위 연결 하나다.

`configs/simulation_workflows.json`의 `multi-object` 항목은 `scripts/run_multi_object_execution.py`를 등록하며 model endpoint가 필요한 실험용 실행임을 명시한다. `docs/multi_object_execution.md:40–54`는 실제 CLI와 paused-SIM 시계를 설명한다. 파일이 오래됐다는 이유로 고른 경로가 아니다.

| 경계 | 원래 소스에서 확인한 연결 | 이번 실행 범위 |
| --- | --- | --- |
| CLI → 합의 → gate | runner:167–185에서 TeamAgreement와 mission validator를 만들고, 합의 후 MultiObjectExecution을 생성한다. | CLI/모델 협상은 source-only. 실제 TeamAgreement에 작성한 2라운드 ACK를 넣어 같은 validator와 gate를 생성했다. |
| gate → 예약 → 단계 | execution:93–107에서 완료된 선행 작업을 확인하고 grant된 Ticket으로 TaskStageExecution을 만든다. plan:227–252에서도 dependency와 자원 점유를 확인한다. | 한 상자의 `stage_box → finish_box`를 실제 메서드로 실행했다. |
| 단계 FINISH → mission DONE | execution:189–194에서 advance가 성공하고 FINISH일 때만 참여자 전원의 report_done을 전달한다. | APPROACH 이후 GRASP/LIFT/TRANSIT/LOWER/RELEASE를 거쳐 실제 완료 연결을 실행했다. |
| DONE → lease/slot 인계 | plan:255–278에서 현재 ticket과 보고를 확인한 뒤 완료를 기록하고 locks를 해제하며 해당 물건의 resident를 목적 슬롯으로 옮긴다. | staging 점유 보존과 final로의 장부상 인계를 관찰했다. |
| 기록 → 최종 평가 | execution:230–233은 물리 성공을 `separate_evaluation_only`로 표시한다. runner:219–227은 gate를 닫은 뒤 별도 evaluate를 호출한다. | summary는 실제 실행. evaluate/physics는 source-only이며 호출하지 않았다. |

줄 번호는 위 고정 SHA 기준이다. 주요 소스 `multi_object_execution.py`, `multi_object_plan.py`, `task_stage_sync.py`, `task_stage_execution.py`와 runner를 읽었다. `three_robot_plan.py`는 합의/검증 prefix, `pair_carry_sync.py`는 사용되는 sync class, `dispatch_execution.py`는 검증 함수와 주변 prefix, `camera_robot_port.py`는 사용되는 bounded-command/hold 경계를 확인했다. 이들 모듈을 fixture가 로드했다는 사실을 모든 함수가 실행됐다는 주장으로 쓰지 않는다. tracker는 입력 경계를 source-only로 확인했다.

기존 `test_multi_object_execution.py`와 `test_task_stage_execution.py`의 관련 코드를 읽고, mission/stage-sync 테스트는 AST 이름 목록을 비교했다. 이미 존재하는 five-task/expiry/missing-partner/wrong-action/old-stage 단위 시나리오를 새 공백으로 세지 않았으며 기존 전체 테스트는 실행하지 않았다.

## 최소 작성 fixture와 결과

`mission-stage-boundary-repro.py`는 표준 라이브러리만 쓰며, 고정 SHA의 정확한 원본을 `git show`로 로드한다. `validate_action`/`validate_reply` 두 함수는 원래 AST body를 그대로 사용한다. 나머지 사용되는 합의·mission·stage·port는 실제 클래스다. 실험 파일·저장된 mission·RGB·결과 자료를 가져오지 않고 한 물건, staging/final 슬롯, 공유 논리 경로를 직접 작성했다.

CargoTracker 결과, 시각적 READY/DONE 주장, 단조 시각, actuator sink는 대역이다. 카메라 바이트는 디코딩하지 않는 작성 placeholder이며, 세계 좌표/측정 상태 접근은 fixture에서 거부한다. 실제 모델·렌더러·물리·학습·하드웨어를 호출하지 않았다.

| 작성 입력 | 실제 consumer의 관찰 결과 | 주장 범위 |
| --- | --- | --- |
| 정상 staging → final | 각 작업에 APPROACH와 5개 단계 명령이 기록됐다. 첫 RELEASE/DONE 후 completed 1, locks 없음, resident=`staging_a: box_a`. 후속 작업 중 staging resident가 유지됐고, 최종 RELEASE/DONE 후 completed 2, locks/active 없음, resident=`final_a: box_a`. | 보고에 근거한 순서·예약 장부다. staging/final의 실제 물리적 배치가 아니다. |
| 다른 task_id로 바꾼 Ticket | `old or unknown task ticket`, 관찰한 장부 snapshot 불변. | 실제 report_done consumer에 직접 넣은 음성 대조다. 정상 writer가 이 ticket을 생성했다고 주장하지 않는다. |
| 첫 작업의 마지막 outer reply를 다음 작업에 전달 | `stale request, plan or stage`, 새 명령 없음, 다음 작업은 APPROACH 유지. | 실제 batch의 이전 요청 거부 대조다. 실서비스에서 stale 응답이 발생했다는 보고가 아니다. |
| 접근 명령 후 agreement invalidate | 두 번의 tick이 `plan revoked; leases retained until external recovery`로 중단됐다. locks와 미완료 상태 유지, motor sink는 모두 0. | 계획 취소 시 논리 예약 보존과 명령 sink 정지다. 물리 정지·복구·재계획 후 재개 보장은 아니다. |

정상 summary는 `completed_task_claims=2`, `final_object_claims=1`, `issued_task_commands=12`, `physical_success='separate_evaluation_only'`다. 마지막 motor sink도 0이었다. 이는 한 물건·한 참가자 경로의 bounded witness이며, 다중 객체 경쟁/협동 참가자 전체 조합을 망라하지 않는다.

```sh
python review-notes/round26/mission-stage-boundary-repro.py \
  --repo ugrp-colab \
  --output /tmp/new-mission-stage-result.json
```

재실행 시 `--output`에는 아직 존재하지 않는 새 임시 파일 경로를 지정해 보존된 결과 JSON을 덮어쓰지 않는다.

## 해석 제한과 다음 경계 판단

`docs/multi_object_pilot.md:52–66`은 같은 실행기 시계, 보고 기반 완료, 논리 lane, 교착/복구 한계를 명시한다. 최신 adapter 문서:26–35는 solo와 단계 연결을 설명한다. 따라서 허용된 TOP 입력이나 실험용 raw action, 보수적인 staging 점유, 미구현 복구를 새 결함으로 분류하지 않는다. 이 검토는 타 경로의 host/Pi clock 문제나 종료·취소 전체 안전성을 재검증하지 않는다.

바로 다음의 구현된 consumer는 runner의 protocol summary 저장과 종료 후 `evaluate(scene)`다. runner:105–126, 219–227에서 평가가 제어를 닫은 뒤 수행되고 결과 스스로 terminal placement만 다룬다고 명시함을 source-only로 확인했다. 이 연결에서 새로 실행할 유용한 미검토 caller는 특정하지 못했다. 문서:64–68의 다음 병목인 목표 ID를 유지하는 학습 접근/파지·ACT 연결과 교착 복구는 여기서 이미 구현된 후속 caller라고 볼 근거가 없다. 이번 결과로 이 경계를 닫으며, 전체 코드베이스의 모든 경로가 검증됐다는 뜻은 아니다.

solo 결과를 공동 2대 운반으로 확대하지 않기 위해 그 분기는 source로 별도 triage했다. `TaskStageSync.command_participants:367–377`은 GRASP에서 DONE인 peer를 제외하지만 결합 단계에서는 전원이 미완료여야 명령을 허가한다. 상위 `MultiObjectExecution.batch:181–201`은 이 선택을 그대로 dispatch에 넘기고 명령 이력은 peer별로 유지한다. 기존 `test_multi_object_execution:35–46,82–102`는 r1/r3 beam을 포함한 실제 상위 gate의 전 단계, :212–224는 그 caller의 missing-partner를 다룬다. 하위 실제 포트의 GRASP 부분완료/완료 peer 불변/결합 단계 거부는 `test_task_stage_execution:258–312`에 명시돼 있다. 이 테스트들의 source를 읽었으며 실행하지 않았다. 따라서 참가자 수만 늘린 재현을 다음 라운드로 만들 근거는 찾지 못했다. 이 판단도 공동 운반의 물리 성공이나 모든 비동기 조합이 검증됐다는 주장은 아니다.
