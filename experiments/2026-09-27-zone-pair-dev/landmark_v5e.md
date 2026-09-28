# PR #240 생성자·prepare 후속 수정 — 2026-09-28

기준 HEAD `4059fce06199e22269cdb885a5120dfb004974d5` 위의 미커밋 변경이다.
사용자 지정 review6 P2와 dock 회귀를 처리했다. 물리 step·실제 모델 호출·커밋은 0이다.

## 변경과 재현

- `GuardedDriver`가 공유 localizer를 먼저 연결한다. 새 `SharedPoseDriver`가 상속 체인에서
  동결 `OwnCamDriver.__init__` 직전에 제어 상태만 초기화한다. pair의 기존 heading/pursuit
  생성자는 그대로 실행되며, 추가 PF·detector 생성과 `landmarks.tags/id/size_m` 접근은 없다.
- vision 제공자를 주입한 pair·goto·loaded goto에서 `landmarks` 제거, `id/size_m` 없는
  태그 항목, detector/PF/동결 생성자 차단을 검사한다. 수정 전 **15 failed**, 수정 후 모두 통과한다.
  별도 3건은 동결 생성자의 제공자 외 모든 상태 필드와 초기값이 일치함을 확인한다.
- 상속 감사는 최상위 `__init__`뿐 아니라 실제 협력 생성자 체인과 종료 지점까지 검사한다.
  새 초기화 모듈도 표식 참조·GT/평가/물리/모델 의존성 감사에 포함한다.
- dock 테스트가 과거 v5b의 소스 집합을 현재 집합으로 가정했다. 현재에는
  `sim/zone_own_scene_provider.py`가 추가되어 **5건 모두 소스 집합 assertion에서 실패**했다.
  최신 등록 전체 해시 일치, 알려진 추가 소스, 정적 장면 불변, 과거 등록 거절을 각각 검사한다.

보고된 `prepare imported MuJoCo`는 이 HEAD의 새 프로세스에서 **재현하지 못했다**.
수정 전 v5d prepare와 전체 비물리 테스트에서도 별도 import 실패는 없었다.
과거 등록 거절만 검사하던 dock subprocess 테스트에 최신 v5e의 성공 prepare 2건을 추가했다.
MuJoCo import를 금지한 상태에서 입력·manifest·workflow 계획까지 확인한다.
실제 준비 영수증은 MuJoCo 및 실제 모델 라이브러리 import 금지 상태에서 별도로 생성했다.

## 사전등록과 보존

[prereg_v5e.json](prereg_v5e.json)은 아직 실행하지 않은 dev11/907·dev12/908을 재등록한다.
v5d 원본 해시를 `supersedes`에 묶고 새 초기화 모듈을 grasp 소스 목록에 추가했다.
scene 소스 목록의 `sim/zone_own_scene_provider.py`도 계속 고정한다.
과거 prereg **9개**, allowlist 동결 소스 **4개**는 원본 바이트/해시가 같다.

criteria, stage_rules, planned_setdown, limits, timing, safety_coverage, environment,
inputs, runs, contact_profile_contract, scene_instances는 v5d와 동일하다.
grasp 행동 계약도 소스 해시 외에는 동일하다. 임계값·입력 경계·weld OFF·`cargo_noslip_v1`을 유지한다.
`execution_source_sha=null`, `execution_status=not_run`, `--execute`의 prepare-only 거절을 유지한다.
새 실행 번들/workflow 번호는 할당하지 않았다. 이번 재등록은 미실행 v67/0.5.0 후보의 수정이다.

## 검증

정확한 명령·해시·출력·제외 항목은 [검증 JSON](landmark_v5e_validation.json)에 있다.

- 사용자 지정 pytest 범위: **962 passed, 2 deselected**, 72.65초.
  `OMP_NUM_THREADS=2`, `-p no:cacheprovider`, `--basetemp=./.pytest_tmp`를 사용하고
  `-p tests.pose_provider_no_physics`를 추가했다.
- 추가 제공자·상속 경계 회귀: **118 passed**, 15.03초.
- 두 실행 모두 물리 step·실제 vision worker·네트워크 시도는 guard에서 **0**이다.
- 제외한 2건은 실제 world를 구성하고 물리 step을 실행하는
  `test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera`와
  `test_zone_own_executor_host.py::test_team_host_isolation_abort_and_horizon_on_the_real_world`이다.
  사용자 물리 step 금지에 따른 제외이며 sandbox 때문에 생략한 비물리 검사는 없다.
- dev11·dev12 prepare **2/2**: `prepared_not_executed`, `model_calls=0`,
  `applied=null`, `physical_success=null`. [영수증](landmark_v5e_prepare/receipt.json)과
  두 manifest·workflow 계획을 로컬 프로젝트에 보존했다.
- pytest 종료 후 `.pytest_tmp` 삭제, `git diff --check` 통과, HEAD 불변을 확인했다.

fetch는 공유 Git 메타데이터 쓰기 제한, `gh pr list/view`는 네트워크 제한으로 실패했다.
원격 최신 상태는 확인하지 못했고 기본 checkout·브랜치·Git 이력은 변경하지 않았다.
수정은 이 worktree에만 남아 있으며 commit/push/PR 수정은 하지 않았다.

검증 범위는 코드 회귀와 prepare다. vision 위치 정확도·공동 운반 완주·물리 실행 승인은 아니다.
새 물리/학습/평가 코호트가 없어 TensorBoard 실험 snapshot은 추가하지 않았다.
기존 raw·snapshot·실험 원본은 보존하며 UGRP 예외에 따라 Google Drive는 사용하지 않았다.
