# T08b main 통합·CI 중단 원인 확인 — 2026-10-01

PR #333의 `86aec953a11fa3ea5df4c3a847a28a536c89a500`에서
`git pull --ff-only`는 already up to date였다. `git fetch origin` 뒤 main
`fb8ee9fbde4f5a458d1c9c7efa625110dd196edc`를 작업 브랜치에 병합했다.
로컬 검사가 끝나기 전 커밋하지 않도록 `--no-commit`을 사용했다.
이 main은 T08a #315의 병합 `7e081d7047aa2df737cc1890c963b1d3a14302c0`와
tile #334의 병합 `fb8ee9fbde4f5a458d1c9c7efa625110dd196edc`를 포함한다.

## 충돌 해결과 보존

- add/add 충돌은 `tests/test_review_e2e_batch_h.py` 한 파일이었다.
  main의 #334 반례 두 개와 #333의 native PWM 반례를 함께 보존했다.
  두 원본의 fixture·검사 함수 AST는 모두 동일하며 xfail이나 과거 blob 대체는 없다.
- `harness/beam_initial_pose_plan.py`, `tests/test_beam_initial_pose_plan.py`,
  `scripts/run_ci_tests.py`는 main의 병합본과 바이트가 같다.
  T08a가 이제 CI에 직접 등록되므로 중복 수집용
  `tests/test_pair_navigation_beam_initial_pose_plan.py`는 제거했다.
- `harness/beam_approach.py`와 `tests/test_pair_navigation_beam_approach.py`는
  검토 수정본 `d054ac955cd5add7ec88ea6c00fcabb764f27984`와 바이트가 같다.
  `.github/workflows` 전체도 main과 바이트가 같다.
- 봉인 v6e의 85개 소스 해시가 모두 일치한다. 정상 CI의 353개 파일 목록에서
  T08a·T08b·tile 및 tile 반례 연결 파일은 각각 한 shard에만 포함된다.

과거 README·REVIEW_FIXES의 T08a 미병합 상태와 연결 파일 설명은 당시 기록이다.
현재 통합 상태는 이 문서와 `MAIN_INTEGRATION_VERIFICATION.json`을 따른다.

## 기존 CI 실패의 원인

대상 실행: [36748682228](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36748682228),
job `110001619053` (`ubuntu-simulation-scenarios`). `gh pr checks 333`는 fail로
표시했으며 실제 job 결론은 `cancelled`였다. `gh run view --log-failed`가
빈 결과를 반환하여 해당 job 전체 로그와 annotation·단계별 시각을 조회했다.

Ubuntu 패키지 171 MB 다운로드가 **11분 50초, 241 kB/s**를 소비했다.
설치 단계 전체는 17:05:26–17:17:32 UTC의 **12분 6초**다.
설치·첫 quickstart 검사는 통과했고, RGB traffic은 sequence 0/20/40/60으로
진행하다 17:20:15 UTC에 job 전체 15분 제한으로 취소됐다.
annotation은 `The job has exceeded the maximum execution time of 15m0s`다.
관측한 로그에는 assertion 실패가 없고, 이후 stage/arena 단계는 미실행이다.
같은 시점 #334의 정상 CI는 같은 설치 단계를 32초에 마쳤다.

이는 패키지 다운로드 지연으로 실행 예산이 소진된 근거다. 제어기나 CI 제한을
변경하지 않고 정상 PR push로 새 CI를 실행한다. 새 실행의 완료 여부는 별도 확인하며,
이전의 취소된 실행을 성공으로 바꾸어 보고하지 않는다.

## 로컬 검증과 기록

기존 Mac Python 환경과 `offline_guard`를 사용했다. MuJoCo/모델 SDK import와
네트워크 연결을 차단했으며 호스트 잠금을 획득하지 않았다. 다음 검사에
batch H 전체, 필수 source 두 파일, T08a/T08b, 기존 approach/passage/STATUS,
통합한 tile 및 CI shard 검사를 포함했다.

```sh
PYTHONPATH=.:experiments/2026-09-30-beam-approach \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -p offline_guard \
  tests/test_review_e2e_batch_h.py tests/test_zone_pair_registered_source.py \
  tests/test_zone_study_source_pinning.py tests/test_pair_navigation_beam_approach.py \
  tests/test_beam_initial_pose_plan.py tests/test_pair_owncam_approach.py \
  tests/test_pair_passage_plan.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor_tile.py tests/test_zone_own_executor_tile_review_h.py \
  tests/test_ci_sharding.py -q
```

**492 passed**, 실패·skip·xfail·수집 오류 0이다. Batch H의 세 반례는 직접 실행과
정상 CI 연결 파일 양쪽에서 실행했으므로 3회 중복을 빼면 고유 검사는 **489개**다.
필수 세 파일은 batch H 3개, registered source 22개, source pinning 34개가 통과했다.
파일별 검사 수와 원본 해시는 `MAIN_INTEGRATION_VERIFICATION.json`에 기록한다.
raw 로그는 primary checkout의 `outputs/t08b-main-integration-20261001/`에
로컬 보존하며 원격 raw 백업이 아니다. `/private/tmp` 추출 디렉터리는 만들지 않았다.

로컬 물리·SIM step·렌더·모델 호출은 0회다. 새 연구 실험/학습/평가 결과가 없어
TensorBoard snapshot이나 서버를 변경하지 않았다. 최종 v3 provider/observer/guard,
표준 adapter와 실제 출발→정렬 인수는 남았다. `physical_ready=false`를 유지하며
PR #333은 병합하지 않는다.
