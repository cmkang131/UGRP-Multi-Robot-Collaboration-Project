# v6 후속: start-dock 등록 소스 회귀 수정

과거 등록의 소스 해시를 현재 작업 트리에 대조하던 테스트를 수정했다. 등록 JSON이나 기존 해시 기대값을 새 값으로 덮어쓰지 않았다.

## 원인과 경계

`tests/test_zone_start_dock.py::registered_tree`가 현재 `scene_contract()`를 마지막 v5h 등록과 무조건 같다고 요구했다. v6에서 다음 closure 파일이 바뀌며 이 가정이 깨졌다.

- `harness/zone_own_team_host.py`
- `scripts/run_zone_pair_dev.py`
- `scripts/zone_pair_dev_runtime.py`

현재 소스에서 과거 등록을 실행/prepare하려 할 때 `load_config`가 scene/grasp mismatch로 거부하는 것은 유지한다. 과거 기록의 무결성 검사와 현재 실행 허가는 별도다.

`scripts/zone_pair_registered_source.py`는 해당 등록을 마지막으로 바꾼 커밋을 찾고 `git show <SHA>:<path>`로 등록 원문, scene/grasp/contact 계약의 seal·소스 closure, map/calibration 및 predecessor 입력을 검증한다. 과거 Python은 import/실행하지 않는다. Git 이력이 없으면 현재 소스로 대체하지 않고 실패한다. CI offline-regressions는 이미 fetch-depth: 0이다.

## 검증한 등록 커밋

| 등록 | 소스 커밋 |
|---|---|
| `prereg_v3.json` | `4a17e7d47616056db85f35933327c6b63581853d` |
| `prereg_v4.json` | `8effc2cee5c3534d553adb75a0d82b49097e5286` |
| `prereg_v5.json` | `2aedf030c5236a7aa98329acd8367ad6d76743cb` |
| `prereg_v5b.json` | `3ea2edc08e5addafaf3cedc934c463ad8e1635c8` |
| `prereg_v5c.json` | `f510901719afc419863344385514304f3d3a905a` |
| `prereg_v5d.json` | `4059fce06199e22269cdb885a5120dfb004974d5` |
| `prereg_v5e.json` | `8b0ddd27a931bfcecee1e3725ad4a6ed739c5c37` |
| `prereg_v5f.json` | `1d756c5f2706bc662d50f334d0db9e7b8a75d479` |
| `prereg_v5g.json` | `c38f94e6c551d8c0fa9993945ff4df087754672e` |
| `prereg_v5h.json` | `f87921dc52f7a3f12d41b4bc6ab5c30227890e8e` |

새 회귀는 현재 소스 파일 읽기 금지, 다른 커밋 대입, 재봉인한 잘못된 source SHA, 등록 원문 변조, v6에 과거 scene/grasp 계약 삽입을 검사한다. dev09/10도 기존 start-dock prepare 매개변수에 추가했다.

## v6 등록

`prereg_v6.json`의 scene 계약은 현재 파일에서 계산하고 v6 closure는 그 scene 소스 전체를 포함한다(65개). 과거 `grasp_contract`는 새 등록에서 제거하고 해시 고정 `baseline_registration`으로 v5h를 참조한다. v6 자체 계약과 loader에서 이를 엄격히 대조한다. 실행 SHA·승인은 계속 null이며 prepare-only다.

## 재검증

수정 전: start-dock 13 passed / 11 failed (`start-dock-before.log`). 사용자가 적은 목록 중 이 트리에서 재현된 실패 수다.

수정 후 좁은 회귀: 72 passed / 0 failed (`start-dock-after.log`).

첫 확대 회귀는 2307 passed / 1 failed / 381 subtests passed였다. 추가 실패는 `test_owncam_memory.py`의 기존 successor 목록에 v6 `owncam_pose_source.py` SHA가 없어서였다. 원래 M1 동결 JSON은 그대로 두고 정확한 successor SHA를 사유와 함께 추가했으며, 32개 원래 동결 파일도 각각 `source_sha`의 git blob과 대조하도록 강화했다. 해당 회귀는 1 passed / 32 subtests passed로 확인했다.

최종 확대 회귀의 전체 파일 목록·결과는 `final/test_execution.json`, `final/pytest.log`, `final/pytest.xml`을 따른다. 이전 실패 로그도 같은 상위 폴더에 보존했다. MuJoCo step 및 외부 네트워크를 차단하고 Python 자식 프로세스에도 step 차단을 상속한다. 이번 검증은 실행·학습·평가 실험이 아닌 소스 보존 회귀이며 새 물리 결과나 TensorBoard 실험 snapshot을 만들지 않는다.

재실행 명령(기존 환경, 잠금 없는 비물리 테스트):

```sh
mkdir -p /private/tmp/v6-no-physics
cp experiments/2026-09-28-zone-pair-v6/source-regression/step_tripwire.py /private/tmp/v6-no-physics/sitecustomize.py
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
V6_STEP_AUDIT=/private/tmp/v6-physics-audit.log PYTHONPATH=/private/tmp/v6-no-physics:. \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
experiments/2026-09-28-zone-pair-v6/source-regression/run_final_tests.py
```

러너는 `--basetemp=./.pytest_tmp`를 적용하고 finally에서 해당 임시 디렉터리를 지운다. 기존 검증 로그를 보존하려면 재실행 전 runner의 `record`를 새 결과 폴더로 지정한다. Git commit은 기존 registry 테스트가 임시 테스트 저장소 안에서만 만들며 실제 프로젝트 HEAD는 바꾸지 않는다.

이번 후속 수정 파일:

- `scripts/zone_pair_registered_source.py`: 과거 등록/소스의 git blob 감사.
- `tests/test_zone_start_dock.py`: 감사와 현재 실행 적합성 분리; dev09/10 추가.
- `tests/test_zone_pair_registered_source.py`: 과거/현재 경계와 변조 거부 회귀.
- `tests/test_owncam_memory.py`: 명시적 v6 successor와 원래 M1 git blob 검증.
- `scripts/zone_pair_v6_contract.py`: 현재 scene closure 포함 및 v5h baseline 구분.
- `experiments/2026-09-28-zone-pair-v6/prereg_v6.json`: 현재 scene/v6 해시와 baseline 참조.

누락된 tracked test fixture는 없었고 전체 실행에서도 fixture 누락 오류가 없었다. 따라서 sparse checkout 복원이나 추가 index 변경은 하지 않았다.

최종 후속 회귀: **2307 passed / 0 failed, 382 subtests passed**, 요청한 패턴 전체 62개 파일. MuJoCo step·네트워크 sentinel 0, 자식 step tripwire 0, 실제 모델 호출 없음. `.pytest_tmp` 삭제, 프로젝트 HEAD 유지.
