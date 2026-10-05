# 27차 — main 등록 entrypoint와 기존 검토 근거 연결

**main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 실제 workflow catalog는 48개다.** base JSON 41개와 `simulation_workflows.d`의 7개 fragment를 원래 `workflow_manager.catalog` 규칙에 따라 합쳤다. 등록은 실행 접근 경로의 선언이며 현재 HIGH 지원, 실제 실행 승인, 연구 인수·물리 성공을 뜻하지 않는다. 모든 저장소 파일·문서 전용 CLI·두 열린 PR의 새 entrypoint를 이 48개 안에 포함한다고 주장하지 않는다.

로컬 checkout은 이전 `f2577bb`이므로 Git 객체의 b23 source로 대조했다. 48개 고유 entry/runner source는 모두 이전 검토 main과 byte 동일했다. 이 확인은 그 파일의 변경 부재만 뜻하며 모든 dependency·실행환경이 동일하다는 뜻은 아니다. 최신 AGENTS의 선별 이미지 보존 정책 차이는 R22/25의 범위를 유지하고 다시 감사하지 않았다.

파일명/AST/import는 위치 인덱스다. 보고서 이름 hit가 없다고 미검토로 단정하지 않았으며, dependency가 이전 보고서에 있다고 해당 CLI 전체를 닫힌 경로로 세지도 않았다. 아래 표는 기존 원고·source manifest·재현 범위를 연결한 분류이고 통과율 표가 아니다. 48개 ID/entry/실제 runner/hash/첫 import와 검색 보조 목록은 `entrypoint-structural-index.json` (Mac 전달본 증거)에 있다.

| 등록 묶음 | 수 | 직접 연결한 기존 근거 | 남는 경계 |
|---|---:|---|---|
| local 관리 | 1 | R2 workflow argv/input/source/launch/finalization, R4 session config/CLI | 임의 사용자 plugin·모든 native 실행 아님 |
| dispatch / dispatch-skills | 2 | R3 generic RGB skill/navigation, R7 native observer/replay | own+TOP 계약이며 현재 HIGH와 별도; 모든 모델 분기 아님 |
| communication / communication-study / cloud-submit | 3 | R2 legacy study/clock/accounting의 명시 범위, R18 reference prepare→child preflight→backend tuple | `communication`의 모든 metric, 원격 제출 성공까지 승격하지 않음 |
| zone-study-pilot | 1 | **R27 원래 preflight writer→shared PilotBudget→cohort admission→명시 정산** | 저작 대역·임시 DB; 실제 provider/물리 없음 |
| multi-object / stage-sync | 2 | R26 예약→단계→해제와 paired 분기 source triage, 실제 `task_stage_sync` | 막 닫힌 검토를 반복하지 않음 |
| zone dispatch·teacher-fix·cargo probe·team smoke·catalogue | 5 | R21 teacher 요구/source, R2 teacher 부분, R4 scene/cargo geometry | 공유 부품 검토가 5개 CLI 전체 검증은 아님; 교사 성공은 학생 성공 아님 |
| color / cargo perception offline eval | 2 | R21 S1/A3는 별도 evaluator임을 확인 | **render→score 경계는 R28에 분리 위임** |
| RGB outcome offline eval | 1 | registry의 observer replay·평가 분리 선언, 공유 port/scene 일부 기존 근거 | 이 evaluator 전체 판정/원자료를 새로 검증하지 않음 |
| navigation / pair-navigation / camera-pair / rgb-traffic | 4 | R3 map projection·pair navigation 및 R3 analysis 실제 시간 caller | navigation 부품 범위를 보존; traffic·camera-pair 전체 CLI 완료 주장 없음 |
| ACT 실행·teacher 수집·map-suite·두 training·finalization | 6 | R2 checkpoint/resume, R4 실제 data→training→export 경계 | 모든 역사 collector·실제 weights·성능 아님; static map preview·특정 역사 finalization은 새 핵심 실행 후보로 승격하지 않음 |
| Jev | 1 | R3 관련 motion 일부, R10 optional 수집 완료 판정 | cohort 전체 실행/효과 미검증 |
| physical / worker / tensorboard | 3 | R25 REAL deploy→recorder→analyzer clock, R3 shared-world/WS, R3/R7 exporter·observer | 실물·GUI·서비스 운전 아님 |
| owncam loc-record / loop / M1 / memory 2종 | 5 | R27 별도 recorder→evaluator source triage, R14 M1 reanchor, R23 memory caller | 임시 wall-tag·교사 수집과 현재 tag0 HIGH를 구분; 모든 loop 분기 검증 아님 |
| M2 / pair-dev / study integration / bootstrap | 4 | R1/2/4 main integration 및 pair/own executor caller, R8 이후 현재 pair 분리 검토 | bootstrap 모든 CLI·물리 인수까지 확장하지 않음 |
| static audit / final environment 3종 | 4 | R4 geometry/source/calibration, R9 identity, R13 측정 producer→loader | 정적 구조·부분 측정 검사와 실제 render/물리 적격성을 구분 |
| final-pair v3 / heldout v90·v91 / loaded v92 | 4 | R4 fixed geometry/calibration, R7 lock admission, R9 identity, R13 D5/v92 조립 | 과거 결과·heldout 개봉·실제 재생 없음; 현행 HIGH의 새로운 인수를 대체하지 않음 |
| **합계** | **48** | **서로 다른 검토 깊이를 합산하지 않음** | **전 경로·전 코드 완전 검증 아님** |

표의 정확한 ID 배정과 근거 파일명은 `entrypoint-coverage-groups.json` (Mac 전달본 증거)에 보존했다. `dispatch-skills`의 선언 entry는 `run_dispatch_skills.py`지만 실제 runner는 `scripts.run_dispatch_e2e`다. 이런 차이는 registry의 실제 runner를 따라 대응했으며 이름만 비교하지 않았다.

## 이번에 선택한 실제 빈 경계 두 곳

1. **등록 adapter pilot의 완료·진입·정산:** R12의 proxy identity 읽기는 `zone_pilot_*` 전체가 아니고, R11의 main-study ledger와도 다른 writer/consumer였다. [pilot-admission-boundary.md](budget.md)의 좁은 실제 함수 연결에서 새 결함 0건으로 기록한다.
2. **offline 색/화물 인식의 render manifest→score:** R21은 `eval_zone_own_perception_v3_1.py`의 S1/A3 및 teacher 색상 계약이고, 등록 `eval_zone_color_detection.py` / `eval_zone_cargo_perception.py`의 전체 평가 caller는 아니다. R28 담당에 정확한 registry/문서/source를 넘겼으며 결과는 그 담당의 독립 검증을 따른다. 이 문서는 결함 여부를 선판정하지 않는다.

Coverage 담당의 추가 `localization-data-source-triage.md` (Mac: `round27/evidence/authored/localization-data-source-triage.md.txt`)는 recorder fresh directory, inputs/eval_only 분리, frame hash, issued-servo replay, dev-only calibration, truth join을 **source-only**로 확인했다. 신규 실행·결함은 없고 이미 읽은 경로를 다시 분리 과제로 만들지 않았다.

현재 PR #363 `66ff0978…`와 #371 `a009112f…`는 이 main catalog 밖의 별도 검토 근거를 따른다. R15 attachment receipt, R16 inspect queue/camera posture, R8 #371 SIM image cost와 finalization 분류 등 기존 활성 결론의 중요도가 이번 정리 때문에 낮아지는 것은 아니다. 최신 exact source와 상태는 root의 공식 currentness 기록을 따른다.

이후 추가 검토는 변경된 실제 source 또는 구체 writer/consumer 질문이 있을 때 선정할 수 있다. 이 표의 ‘부분/확인불가’를 버그 수로 바꾸거나, 이름이 낯선 역사 파일을 실행 지원 경로로 올리지 않았다.
