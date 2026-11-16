# 구현·비물리 검증 기록 — 2026-09-27

기준 HEAD는 `2b4cab6700056e8602140a7f89571c27eff8a33a`, branch는
`codex/zone-pair-executor`다. 이번 변경은 **미커밋 로컬 수정**이다.
물리 world 생성/stepping, 모델 호출, 학습, 공용 잠금 획득, Google Drive,
GitHub 쓰기는 하지 않았다.

## 변경

- 기본 prepare-only 드라이버, 인자/해시 검증, clean source·고정 SHA·잠금·managed 실행 admission.
- 실제 OwnCamTeamHost/PairTeam, 표준 Scene 재사용, r3 비참여. 모델의 실제 적용값 기록.
- 자기 JPEG/관측·명령·STATUS·종료 queue 로그와 GT/접촉/observer 영상을 분리 보존.
- 단계별 평가 및 영상 검토. `PAIR_SEQUENCE_DONE/unconfirmed` 단독 성공 처리 금지.
- dev01(seed901) 정상 1회 / dev02(seed902) abort 1회 DRAFT, 900 SIM / 7200 wall 상한.
- workflow `zone-pair-dev` 0.1.0 등록, common input receipt와 CI 수집 연결.
- README에 코디네이터의 잠금·실행·영상·TensorBoard 후속 절차 기록.

## 검증

| 검사 | 결과 |
|---|---|
| 최종 관련 회귀 | 494 passed / 3 deselected, 17.57 s |
| 새 드라이버 테스트 | 52 passed |
| MuJoCo import 차단 상태 | 49 passed / 3 skipped, 0.63 s |
| 동결 import SHA256 | 32/32 일치 |
| M2 원본 3개 | HEAD 대비 byte-identical |
| Python AST, workflow entry/docs | 6개 구문, 34개 workflow 정상 |
| git diff --check | 통과 |

새 정상/abort 통합 테스트는 실제 host 스케줄러와 PairTeam에 **가짜 world**를 연결한다.
동결 M2 import 때문에 MuJoCo가 없으면 3건이 명시적 사유와 함께 skip된다.
실제 world/observer는 생성하지 않는다. 이 임시 fixture 결과는 실험 결과가 아니며 제거했다.

최종 관련 회귀 명령:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_dev.py \
  tests/test_zone_pair_review7.py tests/test_zone_pair_review6.py tests/test_zone_pair_review5.py \
  tests/test_zone_pair_review4.py tests/test_zone_pair_review3.py tests/test_zone_pair_review2.py \
  tests/test_zone_pair_review.py tests/test_zone_pair_executor.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_pair_owncam_approach.py tests/test_m2_pair_door_v3.py \
  tests/test_simulation_workflow_manager.py tests/test_zone_study_protocol.py \
  tests/test_simulation_scenes.py --basetemp=./.pytest_tmp \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world and not test_source_fingerprint_includes_calibration_requirements_and_sparse_absence and not test_parent_exit_cleans_background_child'
```

이번 사용자 허용에 따라 잠금 없이 비물리 검사만 실행했다. 제외 3건은 실제 MuJoCo world
검사, sandbox 임시 `.git` 쓰기 검사, `ps` 제한에 걸리는 자식 종료 검사다.
첫 전체 회귀에서 README 작성 전 새 문서 경로 검사 2개가 실패했으나 작성 후 최종 회귀는
통과했다. 가짜 실행 fixture의 준비 디렉터리 누락도 수정 후 정상/abort가 통과했다.
검사 종료 뒤 `.pytest_tmp`를 제거했다.

원본 SHA256:

- `scripts/run_m2_pair.py`: `3432df1fbefd4779921dc89a20f60fb67299fcdd02aa4568c6ecd14e27978783`
- `scripts/study_owncam_pair_beam.py`: `3e4c77e279cde780e19b1a1eb2643c626c46dac15e4671001607c5fa6b9c3cff`
- `scripts/zone_teacher.py`: `e84742fe788d80c726d79c0a46f7617a0f237edcaa0a325f2592a25c40acd5e4`

## 제한과 이관

`git fetch origin`은 공용 `.git` 쓰기 제한, `gh` 조회는 네트워크 제한으로 실패했다.
GitHub connector 대체 조회도 저장소 접근 권한 오류였다. 원격 최신 PR/CI·브랜치 전체는
확인하지 못했고 사용자 지정 HEAD로 작업했다. 기존 RGB RUNNABLE_ID는 변경하지 않았다.
기본 checkout은 읽기만 했다. 관측 HEAD `a67b6e33`과 cached origin/main `2823c57c`는
달랐으며 원격 fetch 불가 상태라 갱신하지 않았다. 다른 작업 프로세스도 변경하지 않았다.

코디네이터에게 남는 항목:

- 변경 검토·커밋·전체 CI·원격 중복 확인 및 실행 SHA 고정.
- 잠금/세션을 통한 dev01/dev02 실행, 실제 적용값·r3 비간섭 확인.
- dev02가 실제 carry GO에 도달하고 pending queue를 abort로 제거했는지 확인.
- B 전체 발자국(명시적 dev 허용 오차 2 cm), 낙하·접촉·전체 영상 확인.
- 실패 포함 raw/hash 검증, native TensorBoard 새 snapshot·영상 등록·실제 로딩/표시.

현재 물리 결과·영상·실험 TensorBoard snapshot은 없다. 이미지 이상·상대 소실의 물리 주입,
연구 통신 효과와 실물 성공도 이번 결과에 포함하지 않는다.
