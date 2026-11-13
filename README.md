# UGRP: 로봇 협력 이송과 Sim2Real

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Solo 제어 구조: 자기 카메라와 지정 상자의 기억이 색 구분과 상자 위치 추정을 거쳐 접근 제어기, ACT, 집기 끝 판정, 내려놓기 단계로 들어가고, 내보낸 명령의 기록이 되돌아간다" width="900">
</p>

MasterPi 로봇이 자기 카메라만 보고 상자를 집어 옮기는 연구다. MuJoCo 시뮬레이션에서 만들고, 같은 입출력 규격으로 실물 로봇에 옮긴다.
지도, 벽 표식, 천장 카메라는 쓰지 않는다. 벽은 짙은 초록, 상자는 빨강과 파랑이다.

## 연구 질문

각 로봇이 자기가 본 것만 아는 상황에서, LLM 이 짠 작업 계획은 팀 구조에 따라 얼마나 달라지는가.
통신 없음, 모두 동등, 팀장 있음, 혼합의 네 구조를, 협업이 필요한 이유가 서로 다른 과제(정보 의존, 좁은 통로, 어려운 길, 순서 제약, 능력 차이, 로봇별 지정 구역)에서 비교한다.
팀 구조와 보고 체계를 미리 정해 주는 방식(계층, 역할 분담, 공유 게시판, 입찰, 구역 담당, 스스로 짜기)도 함께 비교한다.
로봇은 실물 3대이고, 시뮬레이션에서는 64대까지 늘린다.
위 그림의 구조는 이 실험에서 로봇 한 대가 상자를 집어 옮기는 동작을 맡는다.

**[연구 설계 전문](docs/research_design.md)**: 방향, 질문과 가설, 팀 구조, 협업 과제 14종, 로봇 수, 지표, 실험의 세 층.

진행 상황과 최신 결과는 저장소에 적지 않고 팀 Linear(UGRP 팀)에 적는다.

## 시작하기

| 하고 싶은 일 | 문서 |
|---|---|
| 시뮬레이션 돌려 보기 | [설치와 첫 실행](docs/ubuntu_quickstart.md), [로컬 실행](docs/local_simulation.md) |
| 실물로 옮기기 | [Sim2Real 안내](docs/sim2real/README.md), [과제 목록](docs/sim2real/04_tasks.md) |
| 구조와 규격 알기 | [단계별 구성](docs/sim2real/03_pipeline.md), [로봇 입출력 규격](docs/sim2real/02_robot_interface.md), [경기장과 색](docs/sim2real/01_environment.md) |
| 옛 기록 찾기 | [문서 찾아보기](docs/README.md), [실험 목록](experiments/README.md) |

Sim2Real 은 순서가 정해진 단계가 아니라 여러 사람이 동시에 맡는 과제 묶음이다. 과제마다 준비물, 절차, 통과 기준, 결과를 올릴 위치가 적혀 있다.

## 폴더

| 경로 | 내용 |
|---|---|
| `harness/` | 인식, 제어, 모델 입력과 실행 |
| `sim/` | MuJoCo 환경과 평가 |
| `scripts/` | 실행, 검증, 기록 도구 |
| `tests/` | 자동 검사 |
| `configs/` | 실행 설정 |
| `calibration/` | 실물 측정과 보정 |
| `docs/sim2real/` | 실물로 옮기는 안내와 과제 |
| `experiments/` | 실험별 요약. 영상과 큰 자료는 [드라이브](experiments/RAW_DATA_INDEX.md)에 있다 |

## 규칙

작업 전에 [AGENTS.md](AGENTS.md)(로봇 입력과 학습 경계)와 [CONTRIBUTING.md](CONTRIBUTING.md)를 읽는다.
결과를 적을 때는 몇 개 중 몇 개인지와 제외한 것을 함께 적고, 시뮬 결과와 실물 결과를 구분한다.
