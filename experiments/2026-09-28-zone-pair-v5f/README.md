# PR #240 표식 무관 경계와 실행 승인 변경

로컬 코드·비물리 검증 완료. 기준 HEAD는
`8b0ddd27a931bfcecee1e3725ad4a6ed739c5c37`이며 변경은 미커밋 상태다.
물리 실행, 실제 모델 호출, 실행 승인 생성, 커밋·push·병합은 하지 않았다.

배송 부모 생성자, 로봇별 host provider 생성 순서, M1/memory 공유 leg,
M2 지연 PF 초기화, memory detector 프레임 참조, 고정 VIS3 부모의 태그 사전,
study 지도·Scene·projection 경로를 활성 adapter로 우회했다.
세부 감사 대응은 [경계 문서](../../docs/pose_provider_boundary_v5f.md)에 있다.
기존 동결 원본과 v5e 이전 등록은 바이트 그대로 보존했다.

`--execute`는 코디네이터의 명시적 `execution_authorization`을 요구한다.
등록 본문·승인 객체 해시, 실제 HEAD, 작업 트리와 index, 실행 직전 파일 바이트를
검사한다. 승인 객체만 등록 해시와 clean-source 검사의 예외이며,
본문 타입 변경과 저장된 등록 해시 변경은 거부한다.
[승인 설계](../../docs/zone_pair_execution_authorization.md)를 따른다.

| 검증 | 결과 | 근거 |
|---|---|---|
| 요청한 전체 범위 + M1/memory/vision/provider 회귀 | 1,583 passed, 2 skipped, 하위 검사 287 passed | `pytest-final.log` |
| 지도/study 입력·시나리오·소스 추적 의존성과 경계 보강 | 479 passed | `pytest-dependencies.log` |
| 태그 의존성 재현 표 | 14개 진입점 × 4조건 통과 | `tests/test_zone_pair_tag_boundary_matrix.py` |
| 최종 전체/의존성 검사의 가드 집계 | 물리 step·실제 vision worker·네트워크 시도 각 0 | 두 검사 로그 |
| dev11 / seed 907, dev12 / seed 908 | 모두 `prepared_not_executed`, 승인 null | `prepare/receipts.json` |
| 보존 | HEAD 원본 23개 바이트 일치, VIS3 등록 해시 7개 일치 | `verification.json` |
| 임계값·코호트·물리 조건 | v5e와 일치, weld OFF, cargo_noslip_v1 | `verification.json` |

479개 의존성 검사는 전체 검사와 일부 겹치므로 합산하지 않는다.
실제 물리 step이 필요한 아래 두 검사는 비물리 가드가 활성화된 경우에만
시작 전에 skip한다. 물리 통합 검증 완료로 보고하지 않는다.

- `tests/test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera`
- `tests/test_zone_own_executor_host.py::test_team_host_isolation_abort_and_horizon_on_the_real_world`

최초 전체 검사는 1,529 passed / 35 failed였다(`pytest-first.log`).
31개는 기존 배송 모의 제공자가 새 등록 제공자 검증을 통과하지 못한 문제여서
등록 제공자에 합성 보고서를 주입하도록 fixture를 고쳤다. 2개는 제거한 하드코딩
보류 오류를 계속 기대하던 assertion을 갱신했다. 나머지 2개 물리 테스트는
가드가 step 호출을 **실행 전에 차단**했으며, 이후 명시적 skip으로 분리했다.
최초 검사도 실제 물리 step은 실행하지 않았다.

승인 무결성 보강 전의 통과 로그·prepare·검증 영수증은 `before-*` 이름으로
보존한다. 최종 근거는 `pytest-final.log`, `prepare/`, `verification.json`,
`results.json`이다. 초기 prepare 보조 스크립트의 잘못된 import도 로그로 남겼고,
최종 prepare는 MuJoCo·물리 runtime·모델 transport의 import를 차단한 상태로 통과했다.

최종 등록 해시:
`0420d034003845d7037f6f56c6cab50a6797efda5b7adc6a3f997b461a085f5a`.
실행 소스 트리 해시:
`72067154318f4a43efe8ae7a535f5acfc2feb2fdfcb23f80ab376c6881f3c045`.
등록은 [prereg_v5f.json](../2026-09-27-zone-pair-dev/prereg_v5f.json)에 있다.
현재 소스는 미커밋이므로 실행 가능한 clean HEAD로 취급하지 않는다.

재현한 전체 검사:

```sh
OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 ../../ugrp/.venv-sim/bin/python -m pytest -q \
  -p no:cacheprovider -p tests.pose_provider_no_physics --basetemp=./.pytest_tmp \
  tests/test_zone_pair_*.py tests/test_zone_start_dock.py tests/test_zone_study_pair_delay.py \
  tests/test_zone_own_*.py tests/test_zone_study_integration*.py tests/test_pose_provider_boundary.py \
  tests/test_m1_owncam.py tests/test_owncam_memory*.py tests/test_real_scene_memory.py \
  tests/test_vision_pose_source.py tests/test_pose_provider_contract.py
```

검사 후 `.pytest_tmp` 삭제와 `git diff --check`, HEAD 불변을 확인한다.
이는 실험/학습 결과가 아닌 코드 경계 회귀와 prepare 기록이므로 TensorBoard
snapshot을 생성하지 않는다. UGRP의 로컬 보존 예외에 따라 Drive를 사용하지 않았다.
원격 확인은 fetch의 `FETCH_HEAD` 쓰기 권한과 GitHub 네트워크 실패로 완료하지 못했다.
