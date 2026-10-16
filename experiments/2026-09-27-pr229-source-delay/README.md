# PR #229 P1/P2 수정 검증 — 2026-09-27

P1의 소스 고정 누락과 P2의 실제 M2·지연 provider 결합 검증 공백을 수정했다. 커밋·물리 step·모델 호출은 하지 않았다. 기준 HEAD는 `3d52642d246e9180fda84c46105f2bf109edccb8`이며 작업 트리의 미커밋 변경이다.

## P1 — 소스 closure와 실행 SHA

`run_zone_study_integration.runtime_files()`는 AST로 전이 import를 추적한다. 함수 내부 import·상대 import·package initializer, 설정으로 선택하는 student/provider, 지원 모델 transport를 포함한다. 현재 pair DRAFT의 소스·등록 파일 166개를 고정하며 `harness/visual_arm.py`, `harness/llm_completion.py`, `sim/session_scenes.py` 변이도 번들 해시를 바꾼다. 번들 생성 시 실제 로드된 로컬 Python 모듈 77개 중 누락은 0개다.

비-dev 실행은 사전등록 `source_sha` 또는 `--expected-source-sha`를 Git으로 해석하고 HEAD와 비교한다. 두 pin이 있으면 둘 다 검사하며, 누락·미해결/다른 SHA·dirty 실행 소스·다른 bundle을 거절한다. SHA 불일치는 MuJoCo import·host·결과 디렉터리 생성 전에 실패한다. dev도 명시한 SHA는 대조한다.

새 ID: **`zone-study-integration-v64-source-closure`**. 로컬 `refs/heads`·`refs/remotes` 259개의 공통 `RUNNABLE_ID` 최대 v63, 통합 ID 최대 v2 다음으로 v64를 선택했다. 전체 조사 기록은 [local-ref-allocation.json](local-ref-allocation.json)이다. `git fetch origin`은 공유 `.git/.../FETCH_HEAD` 쓰기 제한, `gh pr list`는 `api.github.com` 접속 실패로 갱신하지 못했다. 최신 원격 열린 PR의 예약 여부는 미확인이다.

미커밋 후보 [bundle-candidate.json](bundle-candidate.json)의 SHA-256(digest): `bb3f4308754a84f6c9ea601fa8ab9ddff28d787c9879b1fe6a1a375401fa016c`. 실제 실행 사전등록이 아니며 `source_sha=null`, `draft_uncommitted_unqualified`다. 기존 `config/rgb_execution_bundles/`, integration 과거 prereg·번들·실행 기록과 pair DRAFT를 바꾸지 않았고, frozen M2 import manifest 회귀도 통과했다.

## P2 — 실제 M2와 0.16 SIM초 지연

실제 `PairTeam` → `M2DoorStudent` → 공유 `DelayedPoseSource` → `OwnCamPoseSource`/태그 검출기/PF를 사용했다. 가짜 물리 시계와 실제 host의 arm/decision 스케줄러에서 저장 자기 RGB 18장(약 328 KiB)·발행 서보 명령을 재생했다. 출처·JPEG 해시는 `tests/fixtures/zone_study_pair_delay/frames.json`에 있다. 평가 좌표·접촉·시뮬레이터 상태는 fixture/제어에 넣지 않았다. FakeM2, 즉시 pose 반환, readiness/guard 대체는 사용하지 않았다.

열린 checkpoint를 초기 조건으로 잡았다. 앞선 팔 안정화 대기 6초가 남은 r1에서는 실제 PF 교체·재관측·파지 영상 판정 뒤 두 로봇의 readiness가 성립하고 유효시한 안에 같은 시각 `lift_go_1`을 발행했다. 대기 차가 없는 영상 재생에서는 먼저 준비된 r1의 자세 불확실성이 상대 대기 중 커져 `POSE_UNCERTAIN`으로 중단하고, 상대도 abort하며 GO와 arm 큐가 남지 않았다. 두 회귀 모두 PF 교체 후 0.16초 전에 새 추정이 report/loc로 공개되지 않음을 검사했다. 이는 인터페이스와 시간 처리의 오프라인 검사다. 실제 접근·운반 성공, 전체 물리 코호트, 통신 조건 효과는 미검증이다.

GT 제어 금지·weld OFF·`cargo_noslip_v1`과 실제 인식 지연 구현을 유지했다. 별도 실험·학습·평가 코호트 결과가 없으므로 TensorBoard 변환/뷰어는 실행하지 않았다.

## 검증

[verification.json](verification.json)에 전체 명령·테스트 파일 해시를 저장했다. 기존 네 조건 통합·PairTeam/status/guard·M2 불변 검사와 새 회귀를 함께 실행해 **208 passed, 0 failed (75.59초)**를 확인했다. `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 적용했고 `.pytest_tmp`를 삭제했다. `git diff --check`도 통과했다. 잠금 획득이나 다른 작업 프로세스 조작은 없었다.

## 변경 파일

- `scripts/run_zone_study_integration.py`: closure 해시, 실행 SHA 사전검사, 기대 SHA CLI.
- `harness/python_source_closure.py`: 전이 로컬 import 추적(신규).
- `harness/zone_study_integration.py`: 새 실행 번들 ID.
- `tests/test_zone_study_source_pinning.py`: 해시 변이·SHA·물리 이전 거절 회귀(신규).
- `tests/test_zone_study_pair_delay.py`: 실제 M2·지연·readiness/GO 및 중단 회귀(신규).
- `tests/fixtures/zone_study_pair_delay/`: 자기 JPEG 18장, 명령/출처 manifest(신규).
- `scripts/run_ci_tests.py`: 새 두 회귀 모듈 등록.
- `docs/execution_versioning.md`, `docs/zone_study_integration.md`: 버전·검증 범위 안내.
- `experiments/2026-09-27-pr229-source-delay/`: 이 기록, refs 조사, 번들 후보, 검증 manifest(신규).

현재 후보는 미커밋이며 PR push/CI·최신 원격 번호 확인·물리/모델 실행은 하지 않았다.
