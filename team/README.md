# 팀 실행: 계획기와 실행기의 연결

로봇 2~3대가 상자를 나눠 옮기는 실험의 코드다. LLM 계획기(`team/`)가 로봇마다 행동을 고르고, 실행기(`scripts/run_team_carry.py`)가 그 선택을 접근, 집기(ACT), 운반, 내려놓기로 바꾼다. 구조 그림은 [전체 구조](../docs/architecture.md), 계획기 입력과 메시지 규칙은 [계획기와 메시지 규칙](../docs/planning_messages.md), 실행층은 [실행층](../docs/execution_layer.md)에 있다.

## 어디에 무엇이 있나

| 부분 | 위치 |
|---|---|
| 계획기: 판단 전용 `TeamBrain`, 호출 수·지출 가드, 시험 | `team/brain/`, 시험은 `team/brain/tests/` |
| 계획기 HTTP 서버(실행 하나에 서버 하나) | `team/brain_server.py` |
| 실행기 연결: 팀 실행, 로봇 2대 고정 순서 기준선 | `scripts/run_team_carry.py`, `scripts/run_duo_carry.py` |
| 로봇 하나의 실행(조사·접근·ACT 집기·운반·놓기를 한 틱씩 진행) | `scripts/run_grasp_act_student.py` |
| 둘러보기·접근·정면 맞추기 | `harness/approach_survey_v1.py`, `harness/approach_survey_v1_parts/` |
| 장소 기억(문, 구역, 표식), 번호 표식, 천장 카메라, 든 채 이동, 놓기 | `harness/place_memory_v1.py`, `robot_tags_v1.py`, `overhead_v1.py`, `carry_nav_v1.py`, `drive_record_v1.py`, `release_code_v1.py` (+ 표 `drive_table_v1.json`, `release_table_v1.json`) |
| 실행 분석: 판정, 원인 분해, 검정, 그림 | `analysis/` ([RUNBOOK](../analysis/RUNBOOK.md)) |
| 묶음 실행 스케줄러(작업 VM 여러 대) | `batch/` ([README](../batch/README.md)) |
| 장면 파일과 생성기·검사기 | `scenes/` |
| 사전 등록과 동결 도구 | `prereg/` |

`solo_pipeline/` 은 Solo 평가에 쓴 코드를 그대로 모은 기록이다. 위 `harness/`, `scripts/` 의 같은 이름 파일은 팀 실행을 위해 그 뒤에 고친 판이며 둘을 섞지 않는다.

## 연결 방식

실행기는 로봇마다 결정 시점(집을 상자, 목적지 표식, 문 앞 대기, 내려놓기)에서 계획기에 묻는다. 계획기 서버는 `/tell`(사실 전달), `/decide`(행동 선택), `/chance`(이동 중 답장 기회), `/poll`(새 메시지 확인), `/record`(기록)를 HTTP 로 받는다. 서버는 `127.0.0.1` 에만 묶이고 인증이 없다. 시뮬레이터가 다른 호스트에 있으면 운영자가 관리하는 포트 전달(`ssh -R`)로만 이어 준다. 모델 키는 계획기 호스트에만 둔다.

## 돌리는 법 (자리표시는 본인 값으로)

```bash
# 계획기 호스트
export OPENROUTER_API_KEY_FILE=<키 파일 경로>        # 키는 이 파일에만 있다. 값은 환경에 넣지 않는다
export UGRP_SPEND_GUARD_FILE=<지출 가드 JSON 경로>   # {"baseline_usage_usd": ..., "limit_usd": ...}. 없으면 유료 호출이 막힌다
export UGRP_BRAIN_EVIDENCE_DIR=<기록 폴더>           # 기본 outputs/team-brain
python3 team/brain_server.py --team T1 --robots r1,r2,r3 --port <포트> --log-dir <새 폴더>   # --robots 는 장면의 로봇 수와 같게(scenes3_main.json 은 3대)

# 시뮬레이터 호스트 (저장소 루트에서)
python3 -m scripts.run_team_carry --brain-url http://localhost:<전달한 포트> \
  --plan <plan.json> --protocol <protocol.json> --model <ACT 모델 폴더> --actor-python <actor 인터프리터> \
  --scene-source <고정 장면 묶음> --output <새 폴더> \
  --scenes scenes/scenes3_main.json --scene-id <장면 id> --robot-tags --overhead --regrasp-max 1
```

- `--brain-url` 을 빼면 고정 참조 계획이 돈다. `--fixed oracle` 은 장면 파일의 정답 계획이다(`--scenes` 필요). 기준선은 계획기 없이 이것으로 돈다.
- 계획기 서버 조건: `--option-order reverse`(선택지 순서 뒤집기), `--pre-exchange`(T1/T2 사전 교환), `--leader`, `--model`, `--temperature`, `--max-calls`(로봇당). 실행기 조건: `--listen-s`, `--full-info`, `--no-redecide-destination`.
- 팀 구조는 T0(통신 없음), T1(동등), T2(팀장)다. T3 은 뼈대뿐이라 실행하지 않는다.
- 비용 안전장치는 코드에 있다: 한 실행 300호출, 캠페인 1.5 USD, 가드 상한 2.0 USD. 서버를 켜는 것은 유료 호출 승인이 아니다.

## 이 저장소에 없는 것, 알려진 한계

- ACT 모델과 adapter, plan·protocol JSON, 고정 장면·물리 묶음(`--scene-source`), actor 환경(LeRobot 등), OpenCV(aruco)·NumPy·MuJoCo, 모델 공급자 키. ACT 모델 가중치는 저장소가 아니라 릴리스에 있다([solo_pipeline](../solo_pipeline/README.md)).
- `scripts/run_grasp_act_student.py` 는 시작할 때 `scripts/grasp_act_training_guard.py` 의 `require_gcp(training=False)` 로 실행 호스트를 확인한다. 이 저장소의 그 검사는 원래 연구의 호스트만 통과시키므로, 다른 호스트에서 돌리려면 소유자가 호스트 확인 방식을 정해야 한다. 이번 올림은 그 검사를 바꾸지 않았다.
- `--approach-code-v1`, `--gaze-code-v1` 옵션은 `harness/approach_servo_v1.py`, `harness/gaze_correction.py` 가 필요한데 팀 실행 경로가 쓰지 않아 올리지 않았다. 두 옵션은 쓸 수 없다.
- 시험(`team/brain/tests`, `analysis/`, `batch/`, `scenes/` 의 검사기)은 오프라인이며 시뮬레이션·모델 호출을 하지 않는다. 시뮬레이션 실행, 모델 로드, 서버와 실행기의 실제 통신은 이 올림에서 확인하지 않았다.
- 천장 카메라 위치와 경기장 모양은 동작 코드만 쓰고 계획기는 받지 않는다([전체 구조](../docs/architecture.md)의 원칙). 이 경계를 끝에서 끝까지 감사한 결과는 이 저장소에 없다.
