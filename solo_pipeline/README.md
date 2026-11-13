# Solo 파이프라인 묶음

로봇 한 대가 자기 카메라만 보고 상자를 찾아 집고 내려놓는 구조의 코드다. 구조 설명은 [Solo 구조와 모델](../docs/solo_architecture.md)에 있다. 모델 가중치는 저장소에 없고 릴리스에 붙어 있다.

이 폴더는 평가에 쓴 코드를 그대로 모은 것이다. 저장소의 `harness/`, `scripts/` 에 있는 같은 이름의 옛 파일과 섞이지 않게 따로 두었다.

## 무엇이 들어 있나

| 단계 | 파일 | 하는 일 |
|---|---|---|
| 전체 묶기 | `harness/approach_survey_v1.py` | 둘러보기 → 접근 → 복구·정면 맞추기를 0.1초 단위로 이어 주는 클래스 `SurveyApproach` |
| 0 둘러보기 | `harness/approach_survey_v1_parts/survey_observe.py` | 화면에서 상자를 찾아 관측 목록을 만드는 `Survey`, 지정 상자로 접근을 시작하는 `Approach` |
| 1 접근 | `harness/approach_survey_v1_parts/approach_core.py` | 색 덩어리를 따라 0.2 m 앞까지 가는 제어기 |
| 2 정면 맞추기 | `harness/approach_survey_v1_parts/face_align.py` | 면의 기울기 추정 `estimate`, 돌아 맞추기와 복구 `FaceAligner` |
| 바닥 투영 | `harness/approach_survey_v1_parts/ground_projection.py` | 카메라 명령 자세로 화소를 바닥 좌표로 바꿈 |
| 3 집기 (ACT) | `harness/grasp_act_contract.py`, `grasp_act_input.py`, `seg_frontend_v1.py`, `grasp_act_inference.py`, `grasp_act_policy.py`, `scripts/grasp_act_student_worker.py` | 모델 입력·출력 형식, 색 구분 전처리, 추론, 추론 프로세스 |
| 집기 끝 판정, 진행 | `harness/grasp_act_rollout.py` | 명령 기록 `OwnHistory`, 묶음 실행 `ChunkExecutor`, 집기 끝 규칙 `GraspTransitionRule`, 단계 순서 `SoloSequence` |
| 4 내려놓기 | `harness/release_code_v1.py`, `release_table_v1.json` | 87행 고정 순서 재생 |
| 시뮬레이션 실행 예 | `scripts/run_grasp_act_student.py` | 위 조각을 MuJoCo 에서 이어 돌리는 실행기. 옵션 `--approach-survey-v1` |

## 조각을 잇는 법

로봇 쪽에서 필요한 것은 두 가지다: 0.1초마다 카메라 화면(JPEG)을 주는 것, 돌아온 명령(바퀴 4, 서보 5)을 내보내는 것.

```python
approach = SurveyApproach(contract, select_index)   # select_index(관측 목록) -> 번호
while not approach.arrived:
    command = approach.step(jpeg_bytes, now)        # 둘러보기, 접근, 정면 맞추기
    send(command)
# 이후: ACT 가 집고(ChunkExecutor), 규칙이 집기 끝을 판정하고(GraspTransitionRule),
# 정해진 순서로 내려놓는다(ReleaseCodeV1). 순서는 실행 예 스크립트에 있다.
```

- `select_index` 는 관측 목록(상자마다 종류, 방위, 거리)을 받아 집을 상자의 번호를 돌려준다. 시뮬레이션 실행 예에서는 채점 쪽이 지정 상자와 목록을 맞춰 번호를 준다.
- ACT 로 넘길 때 모델에 들어가는 시계 두 개를 다시 맞춘다. 실행 예의 `act_clock` 부분을 그대로 따른다.
- `contract` 는 `harness/grasp_act_contract.py` 모듈이다. 명령 범위(바퀴 속도 0 또는 0.31–0.40, 펄스 0–0.15초, 서보 500–2500)를 검사한다.

## 필요한 것

- Python 3.12, NumPy, OpenCV, PyTorch, LeRobot 0.6.2 (ACT 구현).
- 시뮬레이션 실행 예는 이 저장소의 `sim/` 과 고정된 장면 묶음이 있어야 돈다. 그 준비는 이 폴더에 들어 있지 않다.
- 카메라 값(`ground_projection.py` 의 내부 값과 팔 끝 카메라 위치)은 시뮬레이션 기준이다. 실물에서는 다시 재야 한다.

## 확인한 범위

시뮬레이션에서 끝까지 돌린 결과(집어서 3초 이상 들고, 같은 자리에 떨어뜨리지 않고 내려놓음): 개발 장면 20개 중 19개, 고치는 데 쓰지 않은 평가 장면 12개 중 12개. 개발용 실행 환경에서 잰 값이다. 상자를 든 채 이동하는 것, 목적지 구역에 놓는 것, 실물 로봇은 포함하지 않는다.

이 폴더의 파일은 평가에 쓴 코드에서 주석과 상태 문구 몇 곳만 다듬은 것이다. 동작하는 코드는 같다.
