# 문서 찾아보기

처음 참여한다면 [프로젝트 README](../README.md)의 세 갈래 시작과 검증 범위를 읽는다.
실물 이전의 새 입구는 **[Sim2Real 병렬 과제 안내](sim2real/README.md)**다.
아래 분류는 문서의 용도를 구분한 것이며, 링크가 있다는 사실은 현재 동작 검증을 뜻하지 않는다.

## 어느 문서를 먼저 믿나

1. [프로젝트 README](../README.md), [작업 계획](plan.md), [지금 하는 일](current_status.md), [연구 설계](research_design.md), [전체 구조](architecture.md), [Solo 구조와 모델](solo_architecture.md), [로드맵](../ROADMAP.md): 현재 기준이다.
2. [Sim2Real 안내](sim2real/README.md)와 과제 카드: 실물로 옮기는 일의 기준이다.
3. 그 밖의 문서, 특히 이름에 날짜가 붙은 문서와 `archive/`, `experiments/`: 그 날짜의 기록이다. 위 문서와 다르면 위 문서가 맞다.

## 현재 작업의 진입점

| 목적 | 문서 | 적용 범위 |
|---|---|---|
| **연구 설계** | **[연구 설계](research_design.md)** | 방향, 질문과 가설, 팀 구조, 협업 과제, 지표, 실험의 세 층 |
| **Solo 구조와 모델** | **[Solo 구조와 모델](solo_architecture.md)** | 단계별 구조, 입력과 출력, ACT 모델, 확인한 범위 |
| 설치·기존 시뮬 체험 | [Ubuntu 시작](ubuntu_quickstart.md), [로컬 시뮬레이션](local_simulation.md) | 기존 실행 경로; 최신 Solo hybrid는 main 미포함 |
| 실행 선택·확장 | [표준 관리](simulation_management.md), [확장 안내](simulation_extensions.md) | CLI·환경 구성과 실행 기록 |
| 작업 규칙·기여 | [AGENTS](../AGENTS.md), [CONTRIBUTING](../CONTRIBUTING.md) | 변경·검증·PR 절차; 날짜별 결정의 적용 범위 확인 |
| 버전·판정 | [실행 버전](execution_versioning.md), [제어기 검증](research_controller_validation.md) | 원본·설정·실행 결과를 구분하고 과거 성능 승계 금지 |
| 학습 모델 | [배포 안내](model_artifacts.md), [모델 목록](../configs/model_artifacts.json) | 가중치·해시·가용 상태; 최신 hybrid의 배포 보장 아님 |

기존 실행 안내의 환경·공급자·가중치 가용성은 실제 사용할 때 다시 확인한다.
이번 개편은 문서 진입점 정리이며 시뮬 실행이나 모델 로딩을 새로 검증한 작업이 아니다.

## Sim2Real: 병렬로 맡을 과제

| 문서 | 무엇을 확인하는가 |
|---|---|
| [전체 안내](sim2real/README.md) | 안전 체크리스트, 검증 등급, 현재 한계 |
| [환경과 색](sim2real/01_environment.md) | 초록 벽·빨강/파랑 상자와 실물 사진 보정 |
| [로봇 인터페이스](sim2real/02_robot_interface.md) | 카메라·바퀴·서보·명령 기록 계약 |
| [혼합 파이프라인](sim2real/03_pipeline.md) | 접근·ACT 집기·규칙 판정·고정 놓기와 이관 자산 |
| [과제 목록·결과 양식](sim2real/04_tasks.md) | 병렬 담당, 산출물, 필요한 통합 의존 조건 |

과제 번호는 실행 순서가 아니다. 준비·분석은 병렬로 진행하되 같은 로봇의 구동은 조율한다.
**실물 시험은 전부 확인 안 됨**이며, 시뮬 명령 범위를 실물 안전 한계로 사용하지 않는다.

### 기존 실물 자료: 원위치 참조

내용을 복사하지 않고 필요한 방법·형식만 참조한다. 옛 문서의 순서·입력 조건·수치는
새 과제의 안전 규칙이나 최신 연구 조건보다 우선하지 않는다.

| 자료 | 재사용할 부분 |
|---|---|
| [실측 프로토콜](sim2real_measurement_protocol.md), [보정 자산](../calibration/masterpi/README.md) | 측정 형식·출처·fit/holdout 분리 |
| [물리 보정 기록](masterpi_physics_calibration.md) | 구형 모델 한계와 측정 배경; 최신 실물 성공 근거 아님 |
| [네트워크 런북](masterpi_network_runbook.md) | 연결 절차; 과거 연결 상태를 현재 상태로 해석하지 않음 |
| [실행 기록기](real_execution_recorder.md), [trace 구조](real_trace_system.md) | 관측·명령·실패 기록 형식; 완전성은 별도 확인 |

## 역사 문서: 아직 원위치에 있음

옛 README를 제외한 다른 문서의 archive 이동은 **0건**이다.
보관 이동 작업은 두 차례 시간 초과로 완료되지 않았으므로 아래 문서가 옮겨졌다고 표시하지 않는다.
날짜별 기록의 “현재”, 실행 중 상태, 모델·클라우드 설정은 당시 맥락에서 읽는다.

| 종류 | 현재 위치의 링크 | 읽는 목적 |
|---|---|---|
| 과거 현황·로드맵 | [2026-10-18 까지의 현황](archive/current_status_20261018.md), [2026-09 로드맵](archive/roadmap_20260904.md) | 그 날짜의 기록; 현재 기준 아님 |
| 과거 계획 | [연구 TODO](research_todo.md), [옛 아키텍처](current_architecture_todo.md) | 당시 우선순위와 설계 배경; 현재 일정으로 승계하지 않음 |
| 결정 이력 | [결정 로그](decision_log.md), [ACT 실행 결정](act_execution_decisions.md) | 필요한 날짜·키워드로 변경 이유 확인 |
| 과거 E2E·설계 | [E2E 현황](archive/e2e_status_20260925.md), [공동 운반 설계](design/2026-09-25-zone-team-carry-codex.md) | 당시 검증 범위와 미완료 항목 |
| 연구 기록 탐색 | [대표 영상 색인](version_videos.md) | 관련 실험 ID·실행 SHA·원본 근거 찾기 |
| 퇴역 경로 | [브라우저 UI](archive/browser_ui_retirement_20260923.md), [환경 정리](archive/simulation_cleanup_20260909.md) | 퇴역 이유; 현재 실행 안내로 사용하지 않음 |
| 저장소 정리 이력 | [2026-09-20](archive/repository_cleanup_20260920.md), [2026-10-06](repository_cleanup_20261006.md) | 과거 이동·정리 범위 확인 |

실험은 저장소 루트의 `experiments/<ID>/`에서 찾는다. sparse checkout에서는 실험 파일이
빠져 있을 수 있다. 로컬에 없는 기록이나 raw 자료를 읽었다고 간주하지 않는다.
실험 요약·단위 시험·교사 재생·학생 폐루프 성공은 서로 다른 증거다.

## 보관 폴더에 있는 문서

- [이전 README 원문](archive/README_20261113.md): 개편 전 루트 README의 바이트 동일 역사 스냅샷.
- [이전 검증 요약](archive/validation_summary_20260917.md): 당시 조건과 범위의 과거 결과.
- [과거 검증 요약](archive/validation_summary_20260917.md): 그 밖의 보관 기록 예시. 전체 역사 문서의 이동 완료 목록은 아니다.

이전 README 안의 상대 링크는 **원래 루트 README 위치 기준**으로 쓰인 것이다.
원문 보존을 위해 링크를 고치지 않았으므로 archive 위치에서 바로 클릭하면 깨질 수 있다.
그 링크는 개편 전 루트 위치와 해당 Git 이력을 기준으로 해석한다.
archive 내부의 기존 상대 링크는 이번에 새로 작성한 두 진입점의 링크 검증 대상과 분리한다.
이는 과거 링크의 정상 동작을 보장한다는 뜻이 아니다.

## 읽기·변경 원칙

- 필요한 주제의 코드·테스트·실험 ID부터 좁혀 읽고, 과거 기록은 근거가 필요할 때 찾는다.
- 최신 프로젝트 결정과 과거 실험의 조건을 구분하고 서로 다른 조건의 성적을 합산하지 않는다.
- 새 기록에는 실패·미실행·제외와 전체 분모, 원본 해시·접근 상태를 남긴다.
- 공개 문서에 개인 절대경로·IP·이메일·클라우드 프로젝트 식별자·비밀값을 넣지 않는다.
- 증거를 옮기거나 삭제하기 전에 코드·fixture·manifest 참조와 원본 보존 상태를 확인한다.
