# S3 door_1 예약·양보 (DRAFT, 오프라인 구현)

기준: PR #394 `e4b72aaffb0d756560397b7f0a30995da12da89f`.
작업: `codex/s3-door-yield`, 전용 `/Users/changmin/projects/ugrp-wt/s3-door`.
**시뮬레이션·MuJoCo compile/reset/step/render·실제 모델 호출 금지, 병합 금지.**
다른 작업의 잠금·프로세스·worktree·PR·raw는 수정하지 않는다. worktree 관리 도구의 상한 예외는 새 전용 worktree 생성/기존 작업 보존 요청을 사유로 기록했다.

## 문제와 선택

r1·r2 빔과 r3 cyan의 공개 계획이 모두 door_1을 지나지만 #394에는 짝 밖의 예약이 없다.
새 옵션 `--door-yield s3-door-yield-v1`은 문을 한 팀씩 쓰는 예약 표를 추가한다.
고전 예약 표와 Open-RMF의 단일 자원 mutex/명시적 반환 방식을 따른다. S3의 두 고정 작업은 같은 시점에 요청하므로 공개 우선순위는 **(r1,r2) → (r3)**다.

v1은 **전체 작업을 하나의 예약 구간으로 잡는 보수적 구현**이다. r3는 초기 dock에서 작업 시작 전에 기다린다. 먼저 접근시킨 뒤 문 앞에서 멈추는 최적화나 대기 장소 재계획을 넣지 않았다. 기존 제어기의 시간에 따른 팔/공동 운반 단계를 중간에 진행시킨 채 명령만 버리는 위험을 피한다. 따라서 문 앞 동시 진입 문제를 막는 대신 cyan 접근/파지도 늦춘다. 통로 밖 충돌 해결·최적 스케줄·일반 MAPF·s1–s8 완성을 주장하지 않는다.

로봇별 `Client`가 같은 정적 우선순위와 받은 enum으로 자기 실행 여부를 결정한다. `Relay`는 정확한 세 신호를 검사하고 모두에게 같은 묶음을 전달할 뿐 위치·경로·역할·양보를 선택하지 않는다. 짝은 두 USING 상태가 함께 있어야 움직인다. 대기 중에는 producer의 step/arm_step을 호출하지 않고 hold만 발행한다. 자기 RGB/명령 이력 갱신은 유지한다. 기존 짝 GO 상호 확인과 실패 시 같은 tick 전체 hold는 유지한다.

## 입력·조건 경계

| 항목 | 고정 규칙 |
|---|---|
| 채널 필드 | `robot_id`, `resource=door_1`, 단조 증가 정수 `round`, `state=REQUEST/USING/CLEAR`만 허용 |
| 전달 | 같은 호스트 tick 안의 완전한 동기 broadcast. 누락/중복/과거 round/외부 ID/추가 필드/소유권 없는 USING/상태 건너뛰기 거절 |
| 요청 | 자기에게 이미 지정된 공개 단방향 작업 계획에서 시작 전 REQUEST. 첫 묶음으로 전원 요청을 확인한 뒤 로봇별 USING 발행 |
| 종료 | 자기 작업 명령의 종료 + 자기 추정의 화물/로봇 envelope가 문 동쪽을 완전히 벗어남. r1·r2 모두 CLEAR여야 반환 |
| 위치 계산 | 자기 PF 보고서 + 공개 grasp station offset/기존 envelope. 3σ 위치·회전 여유와 5 cm 간격. 최근 1초 이내 보고서, 초기화·유한값·과거 fix 필요 |
| 짝 기하 | 자기 위치/방향으로 계획상 빔 중심과 envelope를 추정. 상대 위치나 실제 빔/접촉/관절 좌표를 읽지 않음. 실제 형성/파지 확인은 아님 |
| 실패/불확실 | 실패·누락·시간 경과만으로 예약 반환 없음. 자기 위치 확인이 안 되면 후속 팀은 계속 대기하고 전역 horizon에서 끝남 |
| 세 조건 | `rule/no_comm/peer_nl` 모두 필드·전달·우선순위·판정이 동일. 조건에 따른 코드 분기 없음. 자연어나 모델 호출 계기로 전달하지 않음 |
| 시간 | 실제 host SIM 시각과 기존 전역/로컬 시간 상한 유지. 대기 robot-seconds 기록. 기다린 시간을 지우거나 타이머를 되감지 않음 |

이는 #397 `782830b5d030310805b1a9816b1f8fb95a0a2e39` 초안 §2의 “고수준 자연어 대화 없음, 최소 고정 상태 채널 유지” 경계를 구현 후보로 구체화한 것이다. #397의 문서는 수정하지 않는다. S3 실행 자체는 여전히 모델 없는 고정 역할이며 S4/LLM 또는 본 연구 세 조건의 실제 연결 완료를 뜻하지 않는다. 이 규칙·대기 범위는 본 연구 등록 전에 공통 조건으로 채택 여부를 검토해야 한다.

CLEAR는 자기 작업이 끝난 뒤에만 가능하므로 이 단방향 일회 작업에서 다시 문으로 들어갈 후속 명령은 없다. 추정이 늦거나 불확실하면 전체 기다림이 길어질 수 있고, cyan의 기존 900초 로컬 상한에도 대기 시간이 포함된다. 이 한계는 새 실행에서 측정해야 하며 이번에 시간 예산이나 과거 성공 기준을 바꾸지 않는다. 물리적 낙하/집게 이탈 검출 부재는 #394 그대로다.

## 명시 옵션·버전

- 생략 또는 `--door-yield off`: 원래 `Runtime`, 원래 v107 bundle/CLI 기본값. 기존 host·pair·solo·계약 소스는 #394와 바이트 동일하게 유지한다. 변경 runner의 off 출력/명령/기록은 동결한 #394 runner와 가짜 backend로 바이트 대조한다. 새 코드 SHA/소스 manifest의 출처 해시가 과거 SHA와 같다고 주장하지 않는다.
- ON: 새 `zone-s3-door-yield-v108`, workflow `3.15.0`, `s3-door-yield-v1` 명세/파일 해시/채널을 bundle과 trial/student 기록에 남긴다. 기존 v107 bundle를 덮어쓰지 않는다.
- 번호 확인: origin/main 및 열린 #393/#394/#395/#397/#385/#339의 `RUNNABLE_ID`와 전체 `BUNDLE_ID/WORKFLOW_VERSION` 상수를 확인했다. 최고 v107/3.14.0 다음을 사용했다.
- 새 표준 workflow는 `scripts/run_s3_door_yield.py`로 동일 host에 명시 옵션을 넣는다. 이 경로에서는 off로 바꿀 수 없고, off는 기존 S3 host 경로를 쓴다.

```sh
# 계획 확인만. 실제 실행은 이번 작업에서 금지.
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.sim_cli workflow plan zone-s3-door-yield-v108 -- \
  --expected-source-sha <검증한-40자리-SHA> --output /Users/changmin/projects/ugrp/outputs/s3-door-PLAN --seed 601
# 같은 옵션을 기존 runner에 직접 넘길 수도 있다(기본은 off).
# python -m scripts.run_s3_host ... --door-yield s3-door-yield-v1
```

실행은 기존 명시 release·자기 브랜치의 배타 잠금·깨끗한 커밋·출력/디스크 검사를 모두 요구한다. 이번 작업은 그 권한을 사용하지 않는다. 새 실험 결과가 없어 TensorBoard 변환/서버 시작 대상은 없다. Drive 사용 없음, 오프라인 시험 원본은 기본 checkout outputs의 새 전용 폴더에 둔다.

## 참고 자료와 적용 범위 (2026-10-06 직접 확인)

- Silver (2005), [Cooperative Pathfinding](https://www.davidsilver.uk/wp-content/uploads/2020/03/coop-path-AIIDE.pdf), 예약 표·우선순위 계획 본문 확인. 공간/시간 자원을 겹치지 않게 예약하는 원칙을 사용한다. 전체 경로 공유를 전제로 한 CA*/WHCA*는 입력 경계와 불필요한 새 계획기 때문에 도입하지 않는다.
- Chakravarty et al. (IROS 2024), [Time-Ordered Ad-hoc Resource Sharing for Independent Robotic Agents](https://arxiv.org/html/2408.07942v1), §II–III 자원 요청·겹치지 않는 사용 시간, §IV SAT/greedy 비교 확인. 단일 자원/고정 두 요청에는 최적화 solver를 추가하지 않는다. [저자 공개 코드](https://github.com/open-rmf/rmf_reservation)는 실험적 scheduling library임을 README에서 확인했다.
- Gupta et al. (2025), [Virtual Traffic Lights for Multi-Robot Navigation](https://arxiv.org/html/2511.07811v1), §3/§5의 충돌 구역 밖 대기·한 번에 한 로봇 통행 확인. 논문의 중앙 pose/path 수집은 우리 입력 경계와 달라 사용하지 않는다. 로봇별 enum 판정으로 바꾸고 통로 밖 초기 dock 대기를 택했다. 논문의 실험 성능을 우리 근거로 합산하지 않는다.
- [Open-RMF rmf_reservation_node 공개 코드](https://github.com/open-rmf/rmf_ros2/blob/d3c1c34e06969f06f913202b82cb43f76c8c7a6a/rmf_reservation_node/src/main.cpp): `CurrentState`의 단일 자원 mutex, `ItemQueue`의 중복 제거, `ServiceQueueManager`의 반환 뒤 후속 요청 처리, `ReservationNode::release` 확인. 이 표준 요청→배타 사용→명시 반환 순서를 그대로 따랐다. 모든 요청이 초기 barrier에 모이는 S3라 고정 ID 순서를 쓰고, 중앙 할당은 각 로봇의 동일 규칙으로 옮겼다. C++ 코드 복사나 ROS 의존성 추가는 없다.

## 검증 기록

시험 실행 뒤 결과를 이 절에 추가한다. 물리 인수·실제 통로 통과·전체 세 조건 비교는 미실행이며 DRAFT를 유지한다.

### 최종 결과

- 첫 대상 시험: `tests/test_s3_host.py tests/test_s3_host_door_yield.py tests/test_s3_host_runner.py` → **64 passed, 173.87초**. 시간은 실행 기록이며 속도 비교가 아니다.
- 자체 확인에서 전역 horizon의 마지막 hold 직전 한 tick이 대기 시간 집계에서 빠질 수 있음을 발견했다. 최종 발행 명령 시각까지 한 번만 집계하도록 수정했다. 제어·허용 명령·조건/메시지 정책은 바꾸지 않았다.
- 마지막 수정 범위: `tests/test_s3_host_door_yield.py tests/test_s3_host_runner.py::test_real_host_loop_uses_door_runtime_and_saves_status` → **32 passed, 12.50초**. 앞 64개 중 영향 범위를 다시 검사했으므로 총 96개라고 합산하지 않는다. 두 번 모두 실패 0, pytest 동시 실행 1개.
- OFF: #394 실행기 원문을 `tests/fixtures/s3_runner_e4b72aaf.py`에 SHA-256으로 고정. 정상 종료·horizon·같은 tick 실패의 실제 호스트 루프를 가짜 backend에서 실행해 발행 명령/모든 저장 파일을 바이트 비교했다. 생략/명시 off 계획 출력도 동결 실행기와 같다. 물리 입력이나 성공 궤적 재생 검증은 아니다.
- ON: 동시 요청 6순열, 짝 한 대만 종료 시 예약 유지, stale/NaN/큰 불확실성/문 안 위치, 중복·누락·과거/잘못된 신호, 실패 시 전체 hold, 세 조건 동등성, producer 대기, 최종 대기 시간, 새 bundle 변조 거절/관리 경로/기록 저장 확인.
- 구문·`git diff --check`·workflow ID 중복 없음·기존 CI glob의 새 시험 포함 확인. 기존 host/계약/pair/solo/physics host 5파일은 #394와 바이트 동일하다.
- [검증 목록·소스 해시](offline_validation.json). 원본 로그/JUnit/보존 파일 해시는 `/Users/changmin/projects/ugrp/outputs/s3-door-offline-20261006/`에 보존한다.
- 시뮬레이션·MuJoCo·모델 호출 0. 실제 양보/통과·위치 오차·대기 비용·운반 성공과 #397 최종 채택은 미검증. DRAFT/병합 금지 유지.
