# 변경 파일과 최종 검증

브랜치 `codex/zone-pair-beam-relative` / HEAD `f87921dc52f7a3f12d41b4bc6ab5c30227890e8e`. 커밋 없음.

최종 pytest: **853 passed, 0 failed, 198 subtests passed**. `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, 종료 후 임시 디렉터리 삭제. MuJoCo step·network sentinel 호출 0. 모델 호출 없음.

로봇 조건 비교 실행은 하지 않았다. dev05–14 20 endpoint + M2 49회/98 endpoint를 저장 입력에서 검사했으며 118개 후속 경로는 모두 unknown이다. 전체 episode/PF 재생이나 v6 완주 성공률이 아니다.

## 구현·테스트 파일

- `configs/simulation_workflows.json`
- `harness/owncam_observability_v6.py`
- `harness/owncam_pose_source.py`
- `harness/owncam_recovery_v6.py`
- `harness/zone_own_team_host.py`
- `harness/zone_pair_align.py`
- `harness/zone_pair_executor.py`
- `harness/zone_pair_global.py`
- `harness/zone_pair_grasp.py`
- `harness/zone_pair_guards.py`
- `harness/zone_pair_relative.py`
- `harness/zone_pair_v6_policy.py`
- `harness/zone_study_integration.py`
- `harness/zone_study_pose_delay.py`
- `scripts/replay_zone_pair_v6.py`
- `scripts/run_zone_pair_dev.py`
- `scripts/zone_pair_dev_runtime.py`
- `scripts/zone_pair_v6_contract.py`
- `tests/fixtures/zone_pair_v6/dev13_r2_1435.jpg`
- `tests/fixtures/zone_pair_v6/dev13_r2_1446.jpg`
- `tests/fixtures/zone_pair_v6/dev13_r2_1457.jpg`
- `tests/fixtures/zone_pair_v6/dev14_r2_1320.jpg`
- `tests/fixtures/zone_pair_v6/reports.json`
- `tests/test_m1_owncam.py`
- `tests/test_zone_pair_authorization.py`
- `tests/test_zone_pair_executor.py`
- `tests/test_zone_pair_grasp.py`
- `tests/test_zone_pair_v5c.py`
- `tests/test_zone_pair_v6.py`
- `tests/test_zone_study_integration_pair.py`
- `tests/test_zone_study_source_pinning.py`

## 기록

- `design.md`: 선행 설계와 확장 결정·관측/안전/복구 경계.
- `prereg_v6.json`: 동일 seed 911/912 × v5h/b-only/a+b의 6회 DRAFT. 회당 900 SIM초, 재시도 없음, ENOSPC=HOST_ERROR, 소스 SHA/승인 null.
- `bundle_reservation.json`, `remote_branches.json`: main/열린 PR 7개와 로컬 origin SHA 대조, 최대 v67 → v68 로컬 예약.
- `offline_replay.json`, `replay_summary.json`: 원본 228개 경로·해시와 조건부 재생.
- `rgb_residual_validation.json`: dev13/14 원본 자기 JPEG 4장의 실제 검출·잔차 재구성 일치.
- `pytest.log`, `pytest.xml`, `test_execution.json`, `validation.json`: 최종 검사 및 이전 실패 수정 이력.
- `tensorboard-view/`, `tensorboard-snapshot/`, `tensorboard_validation.json`: 오프라인 8 scalar 변환·EventAccumulator 재로딩 확인. 공용 경로 쓰기와 실제 대시보드 표시 미완료.

## 남은 위험

형상·단안 깊이·명령 기반 이동 오차 bound는 미보정 개발 가설이다. post-close band 의존, 실제 markerless provider 연결, 현장 안전·완주 검증이 남는다. PR 예약 코멘트는 승인 정책에 막혀 게시되지 않았다. 원본/raw 보존, Drive 미사용, 공용 viewer 변경 없음.

## 후속 source 보존 회귀

최종 후속 회귀: **2307 passed / 0 failed, 382 subtests passed**, 요청한 패턴 전체 62개 파일. MuJoCo step·네트워크 sentinel 0, 자식 step tripwire 0, 실제 모델 호출 없음. `.pytest_tmp` 삭제, 프로젝트 HEAD 유지.

[수정 파일·원인·보존 검증](source-regression/README.md)을 따른다. 과거 등록과 frozen_source JSON은 수정하지 않았다.
