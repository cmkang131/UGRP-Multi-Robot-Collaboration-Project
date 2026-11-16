# S3: 최종 v3 3대 호스트, LLM 없음

## 실행 전 고정 계획 (2026-10-06)

- 기준 main: `da92d91dbf4af193d3aa3559de9efe55653ec5c0` (#392 이후).
- 계획: `../2026-10-05-scenario-e2e-gap/README.md` 6.1–6.4, S3/K2.
- `dev_s1lite`: r3 cyan → A, r1/end_neg + r2/end_pos 동서 빔 → B. 역할 고정, 사건 없음, LLM/HTTP 호출 0.
- K11(임의 짝/r3 짝)은 후속 s1 전체 범위이며 이번에 졸업으로 표시하지 않는다.
- 로봇 입력은 자기 RGB·공개 정적 지도·자기 발행 명령. 기존 짝 실행기의 고정 enum 동기화는 재사용한다. 평가 정답은 별도 출력으로만 보존한다.
- S1 `scenario_scene`/`ScenarioFinalV3Scene`, #391 v106 단독 Runtime, 기존 highpose 짝 Runtime/벽 경계 OpenCV+PF, IntegratedTrial 및 심판을 재사용한다. 기존 경로 기본값은 수정하지 않는다.
- 예약: `zone-s3-host-v107`, workflow `3.14.0`. origin/main 및 열린 #393/#385/#339 전체 ref의 RUNNABLE_ID·별도 bundle/workflow 상수를 확인했다. 최고 v106/3.13.0.
- DEV seed는 scenario에 이미 선언된 **601, 602, 603**, 순서대로 1회씩. 재시도·튜닝 자료를 새 확증 자료로 세지 않는다.
- 후보 커밋/push 뒤 `launch_dev.zsh <전체 SHA> <기본 checkout outputs 아래 새 절대 경로> --release-s3-simulation`으로 직렬 실행하도록 준비한다. **이 작업에서는 실행 금지**: #393의 잠금이 비어도 시작하지 않는다.
- 졸업 기준: 세 seed 모두 두 주문이 심판의 배달 판정까지 완주. 명령 종료와 심판 배달을 구분한다. 같은 원인 두 번 실패하면 후속 seed 실행을 멈추고 고전/최근 공개 방법과 출처를 조사한다.
- 1800 SIM초/seed, 유한 wall 상한, 독점 잠금, nice 0, ENOSPC=HOST_ERROR, raw는 기본 checkout outputs에 보존한다. 완료 실험이 생기면 실패 포함 TensorBoard 후속 snapshot에 등록한다.
- PR은 DRAFT 유지, 병합 금지. 다른 worktree·PR·프로세스 변경 없음.

## 초기 상태

구현 및 비물리 시험 준비 중. DEV 시뮬레이션·MuJoCo compile/reset/render·모델 호출은 0회다. S2 졸업(#393)과 S3 물리 인수는 아직 확인하지 않았다.
worktree 생성은 기존 Codex 15개로 상한 8개에 걸려, 사용자의 새 전용 worktree 생성/다른 worktree 보존 요청을 이유로 관리 스크립트의 `--allow-over-cap --reason`에 기록했다.

## 연결 방식과 재사용 출처

| 부분 | 그대로 재사용 | S3에서 추가한 연결 |
|---|---|---|
| 3대 호스트 | `zone_study_integration.IntegratedTrial`, `zone_pair_role_integration.executor_plan` | 별도 subclass에서 모델/fixture 스케줄러를 시작하지 않고 고정 claim만 발행. r1=end_neg, r2=end_pos, r3=solo |
| 혼합 장면 | #392 `scenario_scene` → `ScenarioFinalV3Scene` | `dev_s1lite`를 선택, 세 로봇 포트와 두 화물을 같은 world에 연결 |
| cyan | #391 `zone_solo_cyan_v106.Runtime` | r3 자기 프레임·명령만 공급, 공개 주문 P1-1 → A / door_1 |
| 빔 | `zone_pair_highpose_runtime.Runtime`, 기존 highpose Team/Execution·GO/상태 채널 | 공개 order-5를 내부 별칭 cargoX에 연결. 기존 `bind`로 인스턴스에만 공개 task/계획기를 주입 |
| 위치 | `zone_pair_highpose_partial_fix` → OpenCV 벽 관측·PF, v106 solo motion adapter | 짝 provider의 기존 v3 기하에 명시적 소비자 선언 wrapper. 기본 제공자/보정 파일 수정 없음 |
| 물리·기록 | v106 Backend 생성/reset, `IntegerClock`, `CameraRobotPort`, floor_light/nearclip | capture 대상을 r1/r2/r3로 확장. 기준 timestep/contact/weld/카메라 유지 |
| 심판 | `StudyTeamHost.referee_truth`, B6 `Referee`·evidence key·raw event replay | 실행 중 truth JSONL만 쓰고 제어 종료 뒤 재생. 심판 완료는 제어·단계 전환·종료 조건으로도 쓰지 않음 |
| 관리 | `sim_cli workflow`, `agent_lock`, v98 exact speedups, 공통 source closure | v107/3.14.0 등록, 명시 S3 release + 자기 잠금 필요, seed 직렬 launch |

짝 검색 시작점은 공개 P2-3 슬롯 x중심을 공개 door_1 축에 투영하고 기존 0.1 m coarse 격자로 양자화한 `[1.3, 0.0, 0]` **사전 추정**이다. `eval.setup.placements`를 읽거나 실제 빔 좌표로 보정하지 않는다. 실제 배치를 바꾸어도 공개 주문과 이 추정은 같은 시험을 둔다. 기존 RGB 정렬이 실제 빔을 찾아야 하며, 이 사전 추정의 물리 도달성은 미검증이다. 초기 전체 슬롯 중심 `[1.3,0.4,0]`은 불필요한 가로 꺾임이 기존 경로의 최대 구간 수를 넘겨 거절됐다. 구간 상한·기존 계획기를 바꾸지 않고 공개 통로 축으로만 추정을 정했다.

## 준비한 명령 (이번 작업에서 실행하지 않음)

seed **601 → 602 → 603**, 각 1800 SIM초/최대 10800 wall초, reset 최대 5 SIM초, 끝난 뒤 3 SIM초 안정 관찰. 마지막 두 seed를 새 결과로 얻기 전에는 3/3 또는 S3 졸업을 쓰지 않는다. 같은 실패 코드가 2회 나오면 launch가 나머지 seed를 멈추고 `stop-reason.txt`에 조사 필요를 기록한다. 재실행 시 새 출력 경로를 쓴다.

```zsh
# 시뮬레이션 없음: 관리 경로/인자 확인만
cd /Users/changmin/projects/ugrp-wt/s3-host
S3_SHA=$(git rev-parse HEAD)
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.sim_cli workflow plan zone-s3-host-v107 -- \
  --expected-source-sha "$S3_SHA" --output /Users/changmin/projects/ugrp/outputs/s3-PLAN --seed 601

# 조정자가 #393 이후 S3 실행을 명시적으로 허용한 때만 실행
/bin/zsh experiments/2026-10-06-s3-host/launch_dev.zsh \
  "$S3_SHA" "/Users/changmin/projects/ugrp/outputs/s3-v107-${S3_SHA[1,8]}-NEW" --release-s3-simulation
```

launch는 현재/원격 branch SHA, 깨끗한 소스, nice 0, 잠금 부재를 확인한 뒤 자신의 PID로 배타 잠금을 잡는다. 관리 실행기의 자식 프로세스 그룹 정리를 재사용하며 자기 PID만 종료하고 잠금을 반환한다. 원격 결과 없음, raw 삭제·업로드 없음. `batch.jsonl`, 각 seed의 `bundle.json`, `environment.json`, `student_record.json`, `trial.json`, `result.json`, 명령/자기 JPEG·sha256, `eval_only/referee_truth.jsonl`·`referee.json`, 전체 파일 해시를 보존한다. 공용 top 영상은 로봇 입력에 넣지 않는다.

## 시험 중 발견과 수정

- 첫 오프라인 묶음: **48 passed / 4 failed**. 원인은 둘이다: 공개 슬롯 중심 경로의 `PAIR_PASSAGE_TOO_MANY_SEGMENTS` 1건, OpenCV 배포판 이름을 `opencv-python`으로 고정한 환경 기록 3건. 같은 원인 2회 규칙에 따라 이 묶음 이후 재실행을 멈추고 공식 자료·기존 경로를 조사했다.
- 경로는 공개 슬롯/통로의 기하만으로 prior를 정하고 같은 계획기 검사를 사용한다. 정확한 물체 pose 제공, 경로 구간 상한 확대, 실패 숨김은 하지 않았다.
- 환경 기록은 Python 공식 `packages_distributions()`로 import명→실제 배포판명을 구해 이 Mac의 `opencv-python-headless`를 기록한다. 이 오류가 결과 파일 쓰기 전에 빠져나가지 않도록 기록도 예외 처리 범위에 넣었다.
- v3 소비자 확인에서 기존 pair 모듈의 선언 속성이 없음을 발견했다. 실제 v3 팔/guard/provider를 쓰는 S3 wrapper에 선언했고 과거 파일에는 속성을 추가하지 않았다.

## 참고 자료 (2026-10-06 확인)

- 구축 계획 6.1–6.4 및 K2/K11: `../2026-10-05-scenario-e2e-gap/README.md`. S1 #392, S2 기술 #391, 진행 중인 졸업 #393은 역할·근거를 분리한다.
- 고전 위치 추정: Fox et al. (1999), [Monte Carlo Localization](https://www.cs.cmu.edu/~thrun/papers/fox.aaai99.pdf). 본문 motion/perception 분리 확인. 기존 OpenCV+PF를 그대로 사용하며 새로운 학습/GT seed를 넣지 않는다.
- 현재 공개 다중 에이전트 API: [PettingZoo Parallel API](https://pettingzoo.farama.org/api/parallel/). 로봇별 observation/action 사전을 하나의 world step에 연결하는 구조를 확인했다. 새 의존성·학습기를 도입하지 않고 기존 단일 시계에 적용한다.
- 공개 모션 계획 방법: [OMPL GoalRegion](https://ompl.kavrakilab.org/classompl_1_1base_1_1GoalRegion.html). 단일 정답 pose 대신 공개 영역 제약으로 계획한다는 표현을 확인했다. 이 PR의 슬롯→통로 투영은 제한된 고정 DEV 작업의 단순 기하 연결이며 OMPL 구현/성능을 재현한 주장이 아니다. Nav2 planner 문서는 조회 오류로 **미확인**, 채택 근거에 쓰지 않는다.
- 시계와 물리 소유자: [MuJoCo simulation 문서](https://mujoco.readthedocs.io/en/stable/programming/simulation.html). control/step 분리를 확인하고 기존 integer-substep clock과 포트를 재사용한다. 새 실제 MuJoCo 실행은 하지 않았다.
- 환경 오류의 표준 해결: [Python importlib.metadata](https://docs.python.org/3/library/importlib.metadata.html#mapping-import-to-distribution-packages), [OpenCV headless 배포 안내](https://pypi.org/project/opencv-python-headless/). import명/배포판명 차이와 같은 cv2 namespace 확인. 설치·환경 변경 없이 표준 메타데이터 조회를 사용한다.

## 남은 범위

S3 DEV **0/3 실행**, S3 졸업 미판정. #393의 S2 졸업 결과는 아직 의존성으로 남으며 이번 증거에 합산하지 않는다. 혼합 장면에서 파지·동시 운반·문 통과·상호 가림/충돌·배달, r3 짝 구성(K11), LLM(S4)은 검증하지 않았다. v106/짝 스택이 갖고 있던 실행 중 낙하·기울기·집게 이탈 감지 부재와 미검증 단독 하중 모델은 그대로 명시한다. B6 심판 배달은 물리 운반 기술/실물 성공과 다르다. 새 실험 데이터가 없어 TensorBoard 변환·서버 시작은 하지 않으며, 후속 DEV 결과 회수 시 실패 포함 새 snapshot과 실제 표시 확인이 필요하다.

## 최종 오프라인 검증

```sh
CI=true OMP_NUM_THREADS=2 PYTHONPATH=. \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_s3_host.py tests/test_s3_host_runner.py tests/test_solo_cyan_v106.py
```

**52 passed (74.81초, 속도 측정 아님).** 한 pytest 프로세스로 실행했으며 시뮬레이션 잠금은 잡지 않았다. 실제 v3 짝 provider/계획기 생성, 원래 짝 기본 계획 보존, 공개 배치 독립성, 세 로봇 링크/고정 claim, 자기 프레임·명령 분리, 같은 tick 실패 veto, 모델/fixture 호출 차단, 실제 호스트 루프의 가짜 backend, 두 주문의 B6 심판(잡힌 물체·영역 돌출·누락·배달 후 이탈 거절), 실패 후 정리와 파일 해시를 확인했다. 번들 변조/미등록 seed 거절, 표준 workflow 조회/plan, zsh 구문·diff 검사도 통과했다.

로그/JUnit: 기본 checkout의 `outputs/s3-host-offline-20261006/pytest-round2.{log,xml}`. 첫 묶음의 4실패는 위에 원인과 수정 방향을 남겼다. 이 시험은 **물리 성공/DEV 3 seed/S2·S3 졸업 근거가 아니다**. MuJoCo compile/reset/step/render는 모두 0회다. PR #394는 DRAFT 유지하며 병합하지 않는다.
