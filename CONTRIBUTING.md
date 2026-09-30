# 개발·검증·실험 관리

처음 참여하는 팀원은 **[Ubuntu 24.04 시작 안내](docs/ubuntu_quickstart.md)**를 먼저 따른다. 설치, 무료 시뮬레이션 데모, 모델 프록시 준비 조건과 PR 명령을 포함한다. 아래 `.venv-sim-worker-mac`은 기존 Mac 환경 이름이며 Ubuntu에서는 `.venv-dev`를 사용한다.

## 변경 절차

1. 기존 이슈를 확인하거나, 문제·완료 기준을 담은 이슈를 만든다.
2. `main`에서 작업 브랜치를 만들고 범위가 분명한 변경을 한다. 이미 다른 변경이 있으면 보존하고 범위를 구분한다.
3. 관련 자동 테스트를 실행하고 PR에 결과를 적는다. 실제 동작을 바꾼 경우 영향받는 구간을 검증한다.
4. 실험을 실행할 코드를 먼저 커밋한다. 실행 중 소스를 바꾸지 않는다. 원인을 좁히는 진단 후 최종 후보로 전체 비교 조건을 실행한다.
5. 실험 ID·코드 SHA·환경·설정·전체 결과·제약을 `experiments/`에 기록한다. 실패도 남기고 새로운 결과는 기존 결과를 덮어쓰지 않는다.
6. CI와 검토가 끝난 PR을 병합한다. `main`에는 PR과 `offline-regressions` 통과, 최신 base 반영 및 미해결 대화 해소를 요구하는 GitHub 보호 규칙이 설정돼 있다. 강제 push와 브랜치 삭제는 금지한다. 승인 리뷰 1개와 코드 소유자 `@kcm0127-dotcom`의 승인을 필수로 한다. [.github/CODEOWNERS](.github/CODEOWNERS)는 모든 파일에 적용된다. 새 코드 변경이 push되면 기존 승인을 해제해 다시 검토받는다. 팀원의 Write 권한은 유지되지만 다른 팀원의 승인만으로는 병합할 수 없다. 관리자 우회 권한은 기존대로 소유자에게 남으며, 자동 작업은 이를 사용자 승인 없이 사용하지 않는다.

7. 병합한 에이전트는 아래 절차로 기본 로컬 프로젝트도 최신화하고 검증한다.

GitHub PR의 **Files changed → Review changes → Approve → Submit review**로 소유자가 승인한다. 확인했다는 일반 댓글은 승인 리뷰를 대신하지 않는다. 소유자 본인이 작성한 PR에는 자기 승인을 제출할 수 없으므로, 소유자가 직접 확인 후 관리자 권한으로 병합한다. 에이전트는 해당 PR의 명시적인 병합 승인을 받은 뒤에만 진행한다.

작은 문서 수정에는 전체 시뮬레이션이 필요 없다. CI는 외부 모델 호출이나 하드웨어 검증을 대신하지 않는다.

## 실행 환경 선택

2026-09-22 요청에 따라 환경 구성·시뮬레이션·렌더링의 기본은 [로컬 CLI·native viewer·Python API](docs/local_simulation.md)다. Mac의 기존 환경과 Ubuntu 개발 환경을 사용한다. 대규모 학습·평가는 실행 예산과 자원을 먼저 정하고, Colab/Kaggle은 명시적으로 선택하는 배치 경로로 보존한다.

## 자동 테스트

Python 3.12를 사용한다. 로컬의 검증된 MuJoCo 환경은 `.venv-sim-worker-mac`이다. `.venv-sim`은 이 환경의 호환 링크다. 예전 클라우드 배포 환경은 [퇴역 기록](docs/cloud_simulation.md)으로 남기고 제거했으며, 새 Colab CLI 경로와 구분한다. 새 자동 테스트 환경은 다음과 같이 만든다.

```sh
python3.12 -m venv .venv-test
.venv-test/bin/python -m pip install -r requirements-test.txt
```

테스트 실행:

```sh
.venv-test/bin/python scripts/run_ci_tests.py
```

정확한 CI 테스트 명령과 포함 범위는 [workflow](.github/workflows/tests.yml)를 따른다. 테스트 전용 의존성과 실제 실험 의존성은 구분한다.

오프라인 회귀 목록은 `scripts/run_ci_tests.py`의 `TEST_PATTERNS`를 glob 확장한 뒤
중복 제거·정렬한다. CI에서는 이 목록을 파일 단위로 8개 shard에 나누며,
각 실행 전에 전체 shard의 합집합과 원래 목록이 같고 각 파일이 정확히 한 번
포함되는지 검사한다. 목록만 확인하는 다음 명령은 pytest나 공용 잠금을 시작하지 않는다.

```sh
python scripts/run_ci_tests.py --shard-count 8 --list-shards
```

한 shard 실행은 `--shard-count 8 --shard-index 0`처럼 지정한다(번호 0–7).
옵션을 생략하면 기존처럼 전체 목록을 실행한다. 현재는 파일 수 기준으로 균등 분할한다.
파일별 측정 시간이 생기면 `--durations-json <파일>`로
`{"tests/test_example.py": 12.5}` 형태의 초 단위 JSON을 모든 shard에 동일하게
전달할 수 있다. 긴 파일부터 누적 시간이 가장 작은 shard에 배치하고 새 파일에는
현재 목록에서 측정된 시간의 중앙값을 쓴다. 같은 입력은 항상 같은 분할을 만든다.
CI의 `offline-shard-*` JUnit artifact에는 파일 경로와 테스트별 setup/call/teardown
합산 시간이 남는다. 시간 자료를 갱신할 때 파일별로 합산하고 실행 SHA·환경도 기록한다.
파일 수 균등은 시간 균등을 보장하지 않으므로 실제 shard 실행 시간을 확인한다.

CI는 feature branch의 push 대신 PR에서 실행하고, main push에서도 전체 검사를
유지한다. 같은 PR의 새 커밋은 이전 실행을 취소한다. `ci-preflight`는 의존성
설치 전에 필수 frozen fixture 3개와 CI 분기·집계 로직을 검사한다.
root Markdown, `docs/`의 문서·이미지 등 허용된 문서 형식,
`experiments/`의 Markdown만 바뀐 PR은 문서 전용 경로를 쓴다.
코드·설정·테스트·알 수 없는 경로, 비교 실패, main push는 전체 검사를 쓴다.
사전 등록·판정 문서의 독립 검토는 문서 전용 CI에서도 유지한다.

`offline-regression-checks`는 bundle/registry 검증과 기존 protocol fixture를
한 번씩 실행하고, 분할 전용 단위 테스트와 전체 shard 목록도 검증한다.
기존 required check 이름인 **`offline-regressions`**는 이 공통 job과
`offline-regression-shards` matrix 전체를 기다리는 집계 job이다.
전체 검사에서는 둘 다 `success`일 때만 통과하며 실패·취소·건너뜀은
통과시키지 않는다. 문서 전용 경로는 `ci-preflight` 성공과 명시적인 문서
판정이 있을 때만 두 suite의 의도된 건너뜀을 허용한다. 집계 job은 항상
실행하며 branch protection의 required check 이름을 유지한다.

로컬 `run_ci_tests.py`도 pytest와 공용 잠금 시작 전에 frozen fixture 누락을
거부한다. `python3 scripts/check_ci_fixtures.py`로 먼저 확인할 수 있으며,
오류 메시지의 sparse 추가 명령은 기존 기록을 다시 체크아웃한다.
새 worktree의 sparse 규칙에는 이 작은 fixture 3개가 포함된다.
`--list-shards`는 fixture·pytest·잠금을 시작하지 않는 목록 확인으로 유지한다.

공용 Mac의 기본 저장소와 연결된 worktree에서는 `run_ci_tests.py`가 실험과 같은
`outputs/agent-locks` 잠금을 **획득한 뒤** pytest를 시작한다. 점유 중이면 테스트를
생성하지 않고 종료 코드 3을 반환한다. 중단 시 자신이 만든 프로세스 그룹을 정리한
뒤에만 잠금을 반환하며, 정리가 확인되지 않으면 잠금을 유지한다. GitHub CI와 별도
clone에서는 Mac 경로를 만들지 않는다. 직접 `pytest`를 실행하거나 이전 브랜치의
실행기를 쓰는 경우에는 이 보호가 없으므로 공용 잠금을 별도로 획득해야 한다.

## 실제 실험 재현

실행은 [표준 시뮬레이션 관리](docs/simulation_management.md)의 `sim_cli`를 사용한다. 새 연구 경로를 추가할 때는 공통 카탈로그·실행 기록·입력 및 결과 해시 검증을 함께 연결한다. 기존 스크립트를 직접 호출한 과거 기록은 유지하지만, 이를 공통 관리 기록이 있는 실행으로 소급 표시하지 않는다.

코드 SHA와 함께 [실행 번들 버전](docs/execution_versioning.md)을 고정한다. 실행기·물리 설정·영상 전처리·명령 타이밍이 달라지면 같은 스킬 이름을 사용하더라도 별도 후보이다. 성공 기준과의 설정 차이, 실행 전 검사, 실제 적용값 및 결과 해시를 보존한다. 새 후보의 완주 검증 전에는 과거 성공률을 현재 버전의 성능으로 보고하지 않는다.

실행 당시 설치 버전은 각 실험의 `environment.json`에 남긴다. 기존 시뮬레이션 의존성은 `requirements-sim.txt`에 있다. Ubuntu 24.04의 설치와 기본 물리·렌더링 데모는 CI에서 확인한다. 이 의존성 목록은 과거 N7 환경의 정확한 lockfile은 아니다(예: N7의 websockets는 17.1, 개발 설치 목록은 15.0.1). 플랫폼 간 실제 모델 실험 성능은 별도 검증한다. 자동 테스트용 환경만으로 기존 실험 환경을 재현했다고 주장하지 않는다.

Gemini 실험에는 접근 가능한 모델 프록시가 필요하다. `GEMINI_PROXY_URL`을 본인의 프록시 주소로 설정한다. 인증정보는 저장소에 넣지 않는다. 현재 기본 설정이 특정 개발자의 로컬 서비스를 가리킬 수 있으므로 새 환경에서는 명시적으로 설정한다.

다음 명령은 **실제 모델 호출과 비용**이 발생하는 수동 실험이며 CI에서 실행하지 않는다. 출력 폴더는 새 이름을 사용해야 한다.

```sh
PYTHONPATH=. .venv-sim-worker-mac/bin/python scripts/ugrp_session.py run markerless-validation -- \
  .venv-sim-worker-mac/bin/python -m scripts.run_gemini_seed_validation \
  --execute --output outputs/markerless-validation-NEW-ID \
  --seeds 45 46 42 43 44 --reasoning-effort medium --request-timeout 60
```

현재 실행기는 로봇1대, Gemini 3.8 Flash, 조건당 30호출·120,000입력토큰·300SIM초를 사용한다. 모델 가용성은 프록시에서 확인해야 한다. 결과의 정확한 재생을 보장하지 않으며 모델 응답·지연이 달라질 수 있다.

완료된 실행 하나에 대해:

```sh
PYTHONPATH=. .venv-sim-worker-mac/bin/python scripts/verify_gemini_budget_run.py \
  outputs/markerless-validation-NEW-ID/solo-45 --seed 45 --max-input-tokens 120000
.venv-sim-worker-mac/bin/python scripts/review_navigation_trial.py \
  outputs/markerless-validation-NEW-ID/solo-45
```

생성된 카메라 입력과 영상도 직접 검토하고, 검토 범위와 한계를 기록한다. 자동 검사 통과만으로 실제 운반 성공을 선언하지 않는다. 원시 로그의 평가 좌표를 제어 입력으로 사용하지 않는다.

## 서비스 수명

지속 프로세스는 `scripts/ugrp_session.py run <이름> -- <명령>`으로 시작한다. 완료 시 세션 전체가 종료되는지 확인한다. 필요하면 `python3 scripts/ugrp_session.py stop <이름>`으로 해당 세션만 중지한다. 다른 작업의 프로세스를 이름 패턴만으로 종료하지 않는다.

## 증거와 저장 범위

- `tests/fixtures/`: 작은 재현용 입력, 출처와 SHA를 함께 저장한다.
- `experiments/<ID>/`: 코드 SHA, 환경, 설정, 모든 결과, 원본 해시, 실제 저장 위치.
- 새 제어기·정책 버전의 측정 기록을 남길 때 [버전별 대표 영상 색인](docs/version_videos.md)에 대표 영상 행을 채운다(영상은 파일당 1 MiB 미만, 원본은 `outputs/`와 해시).
- `outputs/`: raw 영상과 로그. 현재 로컬 보관이며 Git에서 제외된다. 다른 사람이 필요로 하면 허가된 저장소에 공유하고 접근 가능한 위치를 결과 기록에 추가한다.
- 보관만 한 해시는 백업이 아니다. raw 자료가 공유·백업되지 않았으면 그대로 명시한다.
- 실험 중복 ZIP, 개인 계정 설정, 키·토큰, 가상환경과 의존성 폴더를 커밋하지 않는다.
- 결과에 사용한 학습 모델은 [모델 배포](docs/model_artifacts.md)에 따라 버전별 GitHub Release에 보존한다. 저장소에는 모델 목록·출처·해시를 넣고, 가중치는 Release asset으로 올린 뒤 재다운로드·파일 검증·로딩 결과를 남긴다. 학습 도중 임시 체크포인트 전부를 업로드할 필요는 없지만 선택 모델과 보고한 비교/실패 모델은 재현 가능하게 보존한다. 누락된 원본은 배포 완료로 표시하지 않는다.

## 과거 실패 재생 도구

`scripts/probe_markerless_loaded_grip.py`는 로컬 M4/solo-46 원본 로그에 의존하고, `scripts/probe_markerless_release_recovery.py`는 과거 실행 폴더를 입력으로 받는다(기본값 N3/solo-45). 원시 폴더는 Git에 포함되지 않아 새 clone만으로 이 진단을 실행할 수 없다. 진단 성공과 실제 모델 운반 성공은 구분한다. 최신 방출 재생기의 비매크로 전이 보완은 전체 재생으로 재검증하지 않았으므로 검증된 N7 실행 경로로 취급하지 않는다.

## 병합 후 로컬 최신화

PR이 GitHub에서 병합되어도 이미 열려 있는 로컬 폴더의 파일은 자동 변경되지 않는다. 병합한 작업에서 이 단계까지 완료한다. 별도 작업 worktree는 그대로 두고 기본 체크아웃만 대상으로 한다.

1. GitHub에서 해당 PR의 MERGED 상태와 병합 SHA를 확인한다.
2. 기본 경로와 origin이 맞는지 확인한다. 이 Mac은 `/Users/changmin/projects/ugrp`이며, 다른 호스트의 경로는 프로젝트 설정과 `git worktree list`에서 확인한다.
3. 기본 경로의 AGENTS.md를 다시 읽고 main 브랜치·깨끗한 작업 트리(미추적 파일 포함)·실험 및 소스 고정 작업 부재를 확인한다. 실행 여부가 불명확하면 갱신을 미룬다.
4. 다음을 **기본 체크아웃에서** 실행한다. 각 단계가 실패하면 중단한다.

```sh
git fetch origin
git status --short --branch
git merge --ff-only origin/main
git rev-parse HEAD origin/main
git status --short --branch
```

두 SHA가 동일하고 `git merge-base --is-ancestor <확인한-PR-병합-SHA> HEAD`가 성공해야 해당 PR의 로컬 반영을 확인한 것이다. 병합 이후 다른 PR이 추가될 수 있으므로 병합 SHA와 HEAD가 직접 같아야 하는 것은 아니다.

미커밋 변경, 로컬 분기 또는 실험이 있으면 자동 stash/reset/clean이나 프로세스 종료로 해결하지 않는다. 갱신을 미룬 경로와 이유를 보고하고 다음 안전한 종료 시점에 다시 확인한다. 다른 작업 브랜치에 main을 자동 병합하지 않는다. 새 작업을 시작하는 에이전트도 기본 체크아웃의 최신 지침과 원격 대비 상태를 먼저 확인한다.
