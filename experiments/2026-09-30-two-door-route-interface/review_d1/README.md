# PR #314 — D1 검토 보완

독립 batch D의 **MAJOR D1 전체 수정**. 정상 구현의 운반자 형상은 이미
완전했으며, 운반자 누락을 놓치던 테스트를 고쳤다. 실행 제어 소스는 바꾸지 않았다.

- 검토 HEAD: `e9ee23ea89bc8e1c971f0b719cd8971942a14779`
- 수정 전에 병합한 최신 main: `b10907c5f2c84f2712030f48fb38061fd4f51281`
- main 병합 충돌 없음. 첫 main 병합과 D1 보완은 검증 뒤 `9738a3d2` merge commit으로 기록했다.
- 근거: [독립 리뷰 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/314#issuecomment-5911363097),
  [리뷰 #322](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/322).

## 지적 → 수정

1. **뒤쪽 운반자가 빠져도 우회 경로 테스트 통과** → 빔·양 역할의 차체·팔,
   총 5개 기준 사각형을 v3 규약의 수치로 테스트에 별도 고정했다. 계획기의
   `_formation`, `team_footprint`, 반환 형상을 기대값으로 사용하지 않는다.
   동/서 고정 heading의 XY 병진은 양 끝 사각형의 AABB가 정확한 연속 sweep이다.
   모든 구간을 정적 벽 및 지도 경계와 검사한다. 물리 sweep이 아니다.
2. **두 문 선택 검사는 ID만 확인** → 선택되지 않은 후보까지 전체 편대로
   재검사한다. 별도로 두 문 × 양방향 × 0/π heading의 8개 경우마다
   실제 문 횡단과 통과 후 비어 있지 않은 옆 이동을 강제해 검사한다.
3. **벽 사례가 end_pos에만 민감** → end_neg/end_pos 각각의 차체만 닿는
   고정 벽을 두 heading에서 검사한다. 시작·굽이·목표는 모두 깨끗하고,
   옆 이동 도중 해당 역할만 충돌하며, 점/.17/.21 m 원은 통과함을 별도 확인한다.

추가로 main에서 들어온 CI 자동 취소 설정을 이번 사용자 지시와 맞췄다.
`github.run_id`별 그룹과 `cancel-in-progress: false`를 사용하고
CONTRIBUTING.md도 수정했다. PR별 공용 그룹에서 취소만 끄면 대기 중인
실행이 대체될 수 있어 그룹까지 분리했다. 일반 GitHub CI와 전체 suite는 유지한다.
CI 수동 취소나 skip trailer는 사용하지 않는다.

## 실제 검사

기존 Mac Python 3.12 환경, 한 스레드 설정, 공용 잠금 아래 실행했다.
MuJoCo/GLFW/torch/모델 SDK import와 네트워크 연결을 차단했다.
**물리·렌더·모델 호출 0회.** 새 실험 결과가 없어 TensorBoard 변환은 하지 않는다.
Google Drive 작업도 없다.

| 소스/변이 | 실제 결과 | 판정 |
|---|---:|---|
| 정상 코드, 관련 suite | **230 passed, 280 subtests passed**, 실패/skip 0 | 통과 |
| 수정 전 62개 검사 + end_neg 형상 제거 | **62 passed** | 기존 검사의 누락 재현 |
| 보완한 76개 검사 + end_neg 형상 제거 | **8 failed, 68 passed** | 누락 검출 |
| 보완한 76개 검사 + end_pos 형상 제거 | **9 failed, 67 passed** | 누락 검출 |
| 새 CI 보존 검사 + 수정 전 main workflow | **1 failed** | 취소 설정 회귀 검출 |

정상 suite에는 `tests/test_zone_pair_registered_source.py` **22개**와
`tests/test_zone_study_source_pinning.py` **33개**가 포함된다.
전체 경로·파일별 건수·명령·SHA-256은 [verification.json](verification.json)에 있다.
pytest 67.52초는 검사 실행 시간이며 물리/모델 성능 비교가 아니다.

수정·추가한 기하 검사 **16/16**이 적어도 한 역할 제거 변이에서 실패했다.
두 문 각각·양방향·두 heading의 8개 옆 이동 검사와 두 역할 벽 4개가
모두 실패 목록에 포함된다. end_pos 변이의 9번째 실패는 기존 목표 경계 검사다.
변이는 `_formation` 반환의 `parts`에서 해당 역할의 차체·팔을 제거하며,
역할 입력은 유지한다. 소스 파일을 수정하지 않고 별도 프로세스 안에서만 적용한다.

[정상 출력](current-01.txt) · [수정 전 누락](before-drop-neg.txt) ·
[end_neg 제거](after-drop-neg.txt) · [end_pos 제거](after-drop-pos.txt) ·
[수정 전 CI 설정](ci-before.txt) · [재현 실행기](run_checks.py)

## 재현과 보존

worktree 루트에서 기존 Python으로 실행한다. 새 출력 경로를 사용해야 한다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
DRIVER=experiments/2026-09-30-two-door-route-interface/review_d1/run_checks.py
$PY "$DRIVER" --output /tmp/t09a-d1-clean-NEW tests/test_zone_own_executor_door_routes.py
$PY "$DRIVER" --mutation end_neg --output /tmp/t09a-d1-neg-NEW tests/test_zone_own_executor_door_routes.py
$PY "$DRIVER" --mutation end_pos --output /tmp/t09a-d1-pos-NEW tests/test_zone_own_executor_door_routes.py
```

뒤의 두 명령은 pytest exit 1이 기대값이다. 수정 전 테스트는 검토 HEAD의
`tests/test_zone_own_executor_door_routes.py`를 별도 `before/tests/` 폴더에
Git blob 그대로 저장해 `--before-tests <절대 경로>`로 넘겼다. 기대값은 62 passed다.
CI 회귀는 `--mutation ci_before`와
`tests/test_ci_fast_path.py::CiFastPathTests::test_new_commits_preserve_running_and_pending_ci`로 재현한다.

- raw/JUnit/잠금 영수증/명령: `/Users/changmin/projects/ugrp/outputs/2026-09-30-t09a-d1-fixes/`.
- Git의 `.txt`는 잠금 대기 줄과 줄 끝 공백만 제거했다. raw 로그는 보존했고
  원본 해시는 verification.json에 기록했다. Git 기록과 로컬 raw 보관은 구분한다.
- 기존 등록·harness·sim·지도·설정 **549/549** Git blob이 검토 HEAD와 같다.
  source-pinning 실패도 없었다. 기존 등록, pinned source 및 기대 해시는 수정하지 않았다.
- CI preflight 첫 검사는 sparse checkout의 기존 `.json.gz` fixture 3개 누락으로
  종료 코드 2였다. Git에 있는 원본만 복원한 뒤 3/3 통과했다. 재생성하지 않았다.
- 모든 검사 프로세스가 끝나고 각 검사 소유 잠금을 반환했다. 다른 작업은 중단하지 않았다.
- GitHub CI 완료·후속 T09b 연결·실제 통과·E2E 인수는 위 정적 검증과 별개다.


## 추가 main 통합 — 최종 검사

작업 중 main에 #304와 #313이 병합되어, `9738a3d2`에
`ad496486271f441f00eb7d95fbd44dc454999004`를 추가로 병합했다. 충돌은 없었고,
#314 계산 코드·검사·workflow와 보호 대상 549개는 위 변이 검증 때와 같다.

최종 결과는 **283 passed, 280 subtests passed, 실패/skip 0 (71.99초)**다.
위 230개에 main에서 들어온 P08 검사 40개와 s6 감사 검사 13개를 추가했다.
[최종 출력](integrated-04.txt)과 [명령·해시·잠금 반환 기록](verification_integration.json)을 따른다.
T09a 76개 및 두 소스 고정 검사 55개도 다시 통과했다.

처음 통합 명령은 importlib 모드에서 s6의 `audit` 검색 경로를 빠뜨려 수집 오류로
끝났다([출력](integrated-02.txt)). 소스 수정 없이
`PYTHONPATH=experiments/2026-09-30-s6-order-design`을 지정해 해결했다.
다음 시도는 테스트 시작 전 공용 잠금 대기만 중단했고([출력](integrated-03.txt)),
자기 대기 실행기의 잠금 확인 간격을 1초에서 0.1초로 줄여 재시작했다.
다른 작업과 CI는 중단하지 않았다. 최종 정상 실행 뒤 자기 잠금을 반환했다.

새 main 문서에서 남아 있던 CI 건너뛰기 지침도 사용자 요청대로 수정했다:
`experiments/2026-09-30-p08-stall-contract/README.md`와
`experiments/2026-09-30-process-review/LITERATURE.md`.
정상 GitHub CI의 완료 여부는 최종 PR head의 checks에서 별도로 확인해야 한다.
로컬 물리·렌더·모델 호출은 계속 0회이며 원래 변이 실패 근거도 그대로 유효하다.
