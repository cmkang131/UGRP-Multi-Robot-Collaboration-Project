# UGRP: 로봇 협력 이송과 Sim2Real

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Solo 제어 구조: 자기 카메라와 지정 상자의 기억이 색 구분과 상자 위치 추정을 거쳐 접근 제어기, ACT, 집기 끝 판정, 내려놓기 단계로 들어가고, 내보낸 명령의 기록이 되돌아간다" width="900">
</p>

MasterPi 로봇이 자기 카메라만 보고 상자를 집어 옮기는 연구다. MuJoCo 시뮬레이션에서 만들고, 같은 입출력 규격으로 실물 로봇에 옮긴다.
지도, 벽 표식, 천장 카메라는 쓰지 않는다. 벽은 짙은 초록, 상자는 빨강과 파랑이다.

## 지금 상태 (2026-11-13, 시뮬레이션)

| 과제 | 결과 | 남은 문제 |
|---|---|---|
| Solo: 로봇 1대가 상자를 집어 내려놓기 (위 그림의 구조) | 처음 보는 12장면 중 6개, 개발 20장면 중 13개 성공 | 실패는 대부분 접근 단계. 상자까지의 거리와 방향 추정을 고치는 중 |
| Solo, ACT 혼자서 전부 | 같은 12장면 중 0개 | 접근에서 멈춤 |
| 물건 없이 이동 (문 통과, 구역 도착) | 문 통과 12개 중 11개, 구역 도착 6개 중 5개 | 집기와 이어 붙이지 않음 |
| Pair: 로봇 2대가 막대를 함께 운반 | 함께 들기 아직 0 | Solo 와 같은 구조로 다시 만드는 중 |
| 실물 로봇 | 아직 시험 전 | [Sim2Real 과제](docs/sim2real/04_tasks.md)로 진행 |

Solo 구조의 코드는 아직 `main` 에 없다. 접근 단계가 안정되면 별도 PR 로 올린다.

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
