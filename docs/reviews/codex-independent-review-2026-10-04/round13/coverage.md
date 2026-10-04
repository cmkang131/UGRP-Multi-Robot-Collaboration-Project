# R13 · 추가 심층 검토 선정과 coverage 장부

이 장부는 검토 범위를 정직하게 나누기 위한 것이다. **전체 코드 전줄 정독·전체 테스트 실행·전 경로 안전성을 뜻하지 않는다.** 이전 보고서의 주장 범위를 대조했고, 같은 결함·같은 반례를 새 발견으로 세지 않았다.

## 분모와 증거 수준

초기 `architecture-python-inventory.json`은 `f2577bb`의 **AST 구조 목록**이다. harness 395개/104,577줄, scripts 459개/109,339줄, sim 86개/25,273줄, tests 641개/144,005줄, examples 4개/82줄을 인덱싱했다. 이 숫자는 정독한 파일 수·실행한 테스트 수가 아니다. 서로 다른 리뷰어의 부분 함수 읽기를 파일 전체 읽기로 합산하지 않았으므로 검토율 백분율도 계산하지 않는다.

| 영역 | 증거 수준과 기존 기록 | 아직 구분해야 할 것 |
| --- | --- | --- |
| pair LLM/protocol/scheduler/ledger | 여러 라운드의 caller 연결·선택 합성 재현; R11 seed/input/archive 추가 범위는 source-only | 실제 hosted LLM 정책 효과·물리 성공·전체 concurrency를 검증한 것은 아님 |
| owncam/HIGH/guard/issued command | 수학·합성 frame/endpoint 재현과 현재 head source delta; 실제 relook sequence는 별도 담당 | commanded state와 measured state, nominal guard와 실제 충돌을 구분 |
| 연구 설계·평가·보고 | 고정 분모·선택 조건·기록 합류의 source+synthetic 및 원문 연구 | 실제 raw/held-out outcome은 열지 않았으며 효과량 재분석 없음 |
| 모델 ZIP/CLI/plugin/source packaging | R4에 전체 작은 모듈·caller 계약 읽기와 선택 반례 | release 가중치 로딩·임의 plugin의 모든 import closure 검증 아님 |
| 실행 소유권·observer/replay·SIM slots | R4/R7의 읽기 및 temp mmap/fake transport/slot 검사 | 실제 GUI·native process 모든 실패·PID 재사용 보장 아님 |
| 정적 geometry/camera/route | R4의 XML/FK 수학·세 등록 route 연속 sweep·선택 tests | 임의 비볼록 polygon·미등록 rotated terrain·실물 mount 전 범위 아님 |
| ACT/data/optional cloud/legacy interface | 특정 writer/consumer와 synthetic 반례; 소스 목록만 확인한 부분도 남음 | 현재 pair 경로의 결함으로 합치지 않음 |
| D5/v92 측정 producer→assembler→loader | **이번 추가 전체 7모듈 source-only**, [경계 기록](assembly.md) | 실제 측정 품질·source 관문의 full pytest 실행 없음 |
| V2 실물 calibration | **이번 실제 계획/fitter/기록기/validator/promotion을 합성 temp 자료로 연결**, [신규 반례](stale-metric.md) | 실제 실물 자료·물리/학습 결과는 읽거나 실행하지 않음 |

기존 범위 확인에 사용한 기록은 `round4-source-contracts.md`, `round4-calibration-geometry.md`, `round7-coverage-audit.md`, `round11/runtime-additional-source-coverage.md`, `round11/evaluation-coverage-boundary.md`, R10/R11 backlog다. 문서의 '전체 파일'과 '부분 함수', '실행함'과 '읽음'을 그대로 유지했다. 현재 head는 official GitHub read에서 main `b23fc087`, #371 `a009112f`, #363 `de03fe87`로 확인했다. 이 담당은 #363 변경 소스를 다시 정독한 것이 아니며, 최신 relook/command 분석을 맡은 담당과 범위를 분리했다.

## 시작 시 선정한 세 가지 추가 우선순위

1. **D5/v92 측정 산출물→조립→입장.** 기존 검토는 scene/hash/rigid transform 중심이어서 실제 측정 producer가 fit과 loader로 이어지는 부분을 우선 읽었다. 의도된 PARTIAL·HIGH-only·step/PRBS·입력 재해시를 확인했으며 이 범위의 신규 결함은 없다.
2. **실물 hand-eye/servo/dynamics의 fit→manifest→acceptance.** 이전 coverage에서 미심층으로 남은 경로다. 현재 pair의 필수 경로와 별개지만, calibrated/validated/training-ready 문구의 근거를 결정한다. 공식 측정 정정 후 stale metric으로 재승격하는 실제 caller 반례를 확인했다. 별도 평가 담당은 이후 training consumer의 실제 매개변수 적용을 독립 검토한다.
3. **공유 지도 planner의 실제 비볼록/waypoint 소비자.** 단순 grid endpoint 한계는 이미 R4에서 알려진 범위다. 이어서 볼 것은 실제 caller가 return segment/footprint를 어떻게 재검사하는지와, 현재 지원되는 정적 지도의 차이다. 존재하지 않는 rotated map을 만들어 현재 blocker로 주장하지 않는다.

지속 작업은 새로운 실제 caller 또는 아직 검증하지 않은 계약을 기준으로 정한다. 같은 source/hash나 이미 입증된 경계를 반복해서 발견 수를 늘리지 않는다. 저장소 구현 변경·실험 실행·외부 게시·자료 정리는 이 담당의 작업에 포함하지 않았다.
