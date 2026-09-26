# memory_v3 개발 기록 — 코호트 미실행

2026-09-27, issue #217 / branch `codex/zone-owncam-memory-v3`, 작업 시작 HEAD `367b40da`.
사용자 지시에 따라 `.git` 변경·커밋·push·PR 작성·코호트 실행을 하지 않았다. coordinator가 커밋한다.
[설계](../../docs/design/2026-09-27-owncam-memory-v3.md), [DRAFT 사전등록](prereg_DRAFT.json).

## 구현 파일

- `harness/owncam_pose_guard_v3.py`: 누적 거리·시간 신선도, 과신 진단과 공분산 하한, 기존 PF 어댑터.
- `harness/owncam_memory_v3.py`: 존재 확률, far 회피 영역, 가시성 기반 miss·빈 바닥 증거, 동료 주장 별도 저장.
- `harness/owncam_drive_mem_v3.py`: 도착 재확인, 주행 중 새 회피 영역, 유한 재시도.
- `harness/m1_owncam_memory_v3.py`: 파지 진입·배치 게이트, 목표 재확인, 사각지대 두 번째 순회.
- `scripts/run_m1_owncam_memory_v3.py`: 버전 선택 및 DRAFT 거부. 기존 runner의 물리 실행 방식·기록 계약 재사용.
- `configs/simulation_workflows.json`: `zone-m1-owncam-memory-v3-run` 추가.
- `tests/test_owncam_memory_v3.py`, `scripts/run_ci_tests.py`, `tests/test_simulation_workflow_manager.py`: 회귀·CI 등록·카탈로그 fixture.

v2 핵심/runner 및 과거 실험 기록의 SHA-256은 `v2_preservation.json`에 있으며 단위 검사로 불변을 확인한다.
기존 off/v2는 새 runner에서도 선택할 수 있고, 예전 runner 파일도 그대로다.

## 검증

Python: `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`.
`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1`, `MKL_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`.
MuJoCo 없이 `unittest`로 검사했고, 새 제어기 import에 MuJoCo를 차단한 검사도 포함한다.
전체 `scripts/run_ci_tests.py`/원격 CI를 실행했다는 뜻은 아니다.

| 범위 | 결과 |
|---|---|
| 새 memory_v3 단위·통합 fixture | 최종 45/45 통과 (`unit_tests.txt`) |
| 기존 memory_v2, M1, localizer, workflow 4개 모듈 | 107개 실행 중 최초 104 통과, 새 카탈로그 fixture 2개 수정 후 재실행 통과, 환경 차단 1개 |
| 새 workflow 카탈로그 목록·모든 workflow read-only plan | 수정 후 2/2 통과 (`catalog_fix_tests.txt` 마지막 두 검사) |
| 보존·형식 | v2 파일/기록 해시 불변, DRAFT JSON 파싱, `git diff --check` |

기존 검사 미완료 1개: `test_parent_exit_cleans_background_child`가 자식 종료 뒤 `ps -o stat= -p <pid>`를 호출할 때 `PermissionError: [Errno 1] Operation not permitted: 'ps'`. 샌드박스 밖 재확인은 coordinator에게 남긴다. 테스트를 숨기거나 skip하도록 수정하지 않았다. 최초 오류 원문은 `related_tests_initial.txt`에 보존한다. 카탈로그 수 33→34와 새 workflow 인자 fixture의 최초 오류도 같은 로그에 있으며 수정 후 두 검사 통과를 별도 기록했다.

새 시나리오에는 다음이 있다.

- s161 기제: 0.43 m 뒤 고정/오래된 고정을 v2가 허용하고 v3가 거부. 왕복 누적 거리, 시간·거리 문턱, 미래 시각, 반올림 시각.
- s166 기제: far-only 상자를 v2가 keep-out에서 빼고 v3가 첫 관측부터 포함. 불확실성 하한, far→near 갱신, 새 장애물에 따른 경로 무효화.
- 과신: 작은 PF σ라도 나쁜 likelihood/innovation이면 조기 look 종료·트랙 확정을 거부. 기존 PF 어댑터에 합성 카메라 검출을 직접 공급해 보고 공분산 보강을 확인.
- 존재·부재: 3회 miss 즉시 삭제와 확률 모형 대조, 시야·벽·전경·먼 거리·짐·모호 대응·중복 관측 경계.
- 조작: 과거 상자/슬롯 기억만으로 파지·배치하지 않음, 새 자기 증거가 있으면 게이트 통과, 재확인 실패 우회 차단.
- 사각지대: 정적 카메라 기하에서 0.27 m 앞 물체는 안 보이고 0.72 m 앞에서는 보임, 추가 순회 1회로 제한.
- 동료 주장: 양 표현의 동일 참조 필드·TTL·중복 방지·자기 트랙과 격리.

과거 s161/s166 원본 궤적을 재생한 결과는 아니다. frozen v2를 같은 합성 입력에 적용해 실패 기제를 대조한 검사다.

## 남은 작업

1. coordinator가 소스 검토·커밋·원격 CI를 수행한다. GitHub CLI는 네트워크 접근 실패, 연결 도구는 저장소 조회 권한 오류여서 열린 PR/이슈의 최신 상태를 이 세션에서 확인하지 못했다. 문헌은 로컬 `origin/kiro/memory-literature`의 `3174c2f8`로 읽었다. 사용자가 제공한 #217 결정은 구현에 반영했다.
2. PR #227의 비전 관측원과 일관성 진단 어댑터를 연결한다. 지금 연결은 **interim tag provider**이며 태그 없는 실행 성공이 아니다.
3. DRAFT의 dev seed 27101–27104 / test seed 27201–27208은 제안이다. 원격 중복·미개봉 여부를 확인하고, 모든 조건의 관측원·물리·지도·예산을 일치시켜 최종 동결한다.
4. 보수적인 회피 영역 때문에 생길 수 있는 no-path, 하중 시야에서 슬롯의 실제 관측 가능성, 확인 거부에 따른 성공률을 dev에서 확인한다. 슬롯 unknown은 배치 금지로 남는다.
5. 실제 새 실험 후 원본·실패·해시와 TensorBoard snapshot/영상 검증을 수행한다. 이번에는 단위 검사만 했으므로 실험 결과·영상·TensorBoard snapshot을 만들지 않았다. UGRP 예외에 따라 Google Drive 작업도 없다.
