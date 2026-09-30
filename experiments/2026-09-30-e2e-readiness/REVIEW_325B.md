# PR #325 독립 수정 검증 — 2026-10-01

**판정: MERGE AFTER FIXES.** 이전 P1 `G-325-1`은 해소됐다. 현재 v6e의 고정
소스와 등록 원본이 보존되고 원문 반례도 통과한다. 다만 실제 호출 경로에서
확인한 새 P2 두 건을 수정하고 재검증해야 한다. 물리 인수나 T03 전체 완료
판정은 아니다. 검토자는 제품 코드·workflow를 수정하거나 PR을 병합하지 않았다.

- 후보: `9db1bbb6c035be711037bcea28eb984471dc300b` (`codex/red-green-m1`).
- 비교 main: `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
- 이전 후보: `be97d9dd53638a1efbda7627b420bd9b1cbd9880`; 이전 검토:
  `01edc483e4c56fc606cb3f79b2bc8c0ad41d83be`의 `REVIEW_E2E_BATCH_G.md`.
- `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`,
  `experiments/2026-09-30-scenario-capabilities/TASKS.md`의 T03과
  [작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/325#issuecomment-5914816780)을 대조했다.
- `git fetch` 후 `git archive origin/codex/red-green-m1 | tar -x -C <scratch>`로
  추출했다. 추가 worktree 없음. 기존 Python 환경과 MuJoCo/Torch import·네트워크
  차단 guard를 사용했다. #328에 따라 호스트 잠금을 획득·대기·해제하지 않았다.

## 새 지적 한 묶음

### R325B-1 / P2 — 실제 target 소실 경로가 정렬의 과거 표를 지우지 않는다

위치: 후보의 `harness/m1_color_perception.py:398–403`, 호출부
`harness/wrist_color_boxes.py:93–95`.

실제 `KindBoxSkill.decide()`에 같은 kind의 정상 floor 영상 2개 → 검은 화면
또는 다른 kind 또는 가린 영상 1개 → 원래 kind의 정상 영상 1개를 전달했다.
소실 시 `last_target=None`이므로 aligner에 `target_xy=()`가 들어간다.
이때 `INVALID_TARGET_XY`로 먼저 반환하여 아래 `not ok`의 `_fits.clear()`에
도달하지 않는다. 다시 보이는 첫 영상에서 소실 전 2표와 합쳐 **3표·ready=True**가 된다.
cyan/red/green × 소실 3종 = **9/9 반례**다. 다른 kind 자체를 목표로 승인한
것은 아니지만, 목표를 잃은 뒤 요구되는 새 정렬 근거를 모으지 않고 확신을 되살린다.

기존 `test_edge_vote_clears_after_current_color_is_lost`는 검은 영상에도 정상
`target_xy=(.32, 0.)`를 직접 넣어서 통과한다. 실제 호출부의 빈 target 경로를
검사하지 않는다. 정상 영상 3개를 연속 입력한 양성 대조는 세 kind 모두 통과한다.

수정 조건: 빈 값·비유한 값 등 target 유효성 검사에서 일찍 반환하는 경로도
현재 근거 거절과 같은 표 초기화 규칙을 적용한다. 새 영상 하나로 과거 표를
되살리지 않는지 실제 `decide()` 연쇄에서 검증한다. 이를 실제 오파지·접촉 사고가
발생했다는 주장으로 확대하지 않는다.

### R325B-2 / P2 — 문서의 기본 factory 연결이 M1 모드를 잃는다

위치: 후보의 `harness/zone_color_box_executor.py:125–131`,
`harness/wrist_color_boxes.py:252–254`; 사용 안내 `README.md:11`
(`experiments/2026-09-30-cap-t03-redgreen/` 안의 문서).

문서대로 `ZoneColorBoxExecutor(..., skill_factory=WristColorBoxDelivery)`를
만들면 executor는 `mode='m1'`인데 `_skill_for(job)(order)`가 반환한 skill은
상속된 기본값 때문에 **`mode='diagnostic'`**이다. 현재 factory 검사는 profile과
kind만 검사한다. 세 kind 모두 이 경로의 skill에 `gt_stub_eval_only` PoseEstimate와
유효한 자기 영상을 직접 주면 거절하지 않고 mecanum 명령을 반환했다. 같은 frame의
`confirm_placement`도 `in_slot=True`, `mode=diagnostic`, `counts_as_m1_input=False`를
반환한다. 명시적 `mode='m1'` skill은 같은 입력을 거절한다.

이는 **새로 문서화된 기본 연결의 모드·하위 입력 계약 결함**이다. 외부
`M1OwnCamDelivery._estimate`의 자기 위치 출처 검사는 그대로 있으므로, 정상
executor 연쇄에 GT가 실제 유입됐다거나 diagnostic 결과가 물리 성공으로 기록됐다는
증거는 아니다. 기본 경로가 의도한 M1 skill을 만들고, M1 executor에 잘못된 모드를
반환하는 factory를 조기에 거절하도록 해야 한다. 기존 cyan 봉인 파일을 고쳐
해결하지 않는다.

## 이전 지적의 해소와 보존 확인

| 확인 대상 | 직접 확인한 결과 |
|---|---|
| G-325-1의 5개 소스 | `owncam_delivery_shared`, `zone_own_deliver`, `zone_own_executor`, `zone_own_status`, `zone_own_team_host` 모두 main과 바이트 동일 |
| 현재 등록 전체 | v6 source 85개 + scene source 12개 각각 main 바이트·기존 SHA-256 일치. 두 집합의 중복을 제외한 고유 파일 수라는 뜻은 아님 |
| 등록 JSON | 원본 SHA-256 `64c2680781f1b989312c3ac091c6e0458579ced7ed65d9e9730aadbc416f4bfd` 유지 |
| 원문 검토 반례 | Batch G 원문에 `--runxfail` 적용, **6 passed** |
| 실제 수정 전 바이트 대조 | 같은 복원 검사에 이전 `be97d9dd`의 5파일을 입력하면 **5 failed**, 모두 assertion. Git 조회·setup 오류로 실패시킨 것이 아님 |
| 확장 격리 | 봉인 코드의 closure에 새 색 모듈 없음. 별도 executor + 선택 wrist skill의 189개 Python 의존 소스와 작성자의 기록 일치 |
| archive 전체 | 8,105파일 / 1,171,629,948바이트를 후보 Git blob과 대조, 불일치 0 |
| workflow | main 직접 비교 및 merge-base 비교 모두 `.github/workflows` 차이 0. 검토 브랜치에서도 수정 없음 |

기존 등록을 다시 봉인하거나 hash 검사를 완화한 우회는 발견하지 못했다.
`tests/test_owncam_memory.py`의 두 허용 hash 추가는 PR이 변경하지 않은 기존
main 소스의 이력을 명시한 것이며, 위 등록 소스의 바이트 보존 검사와 구분했다.

## 직접 실행한 회귀와 변이

관련 37파일에서 **1,104 passed + 291 subtests passed, 7 deselected**, 실패·오류 0을
확인했다. 필수 `tests/test_zone_pair_registered_source.py` **22 passed**,
`tests/test_zone_study_source_pinning.py` **34 passed**, door-relax 20개,
색/봉인 161개, M1 21개와 T07 역할 확장 145개를 포함한다. 기존 cyan·기억·입력 경계
회귀도 이 목록에 포함된다. World/물리 3개와 MuJoCo geometry/projection 4개는
사전에 이름으로 제외했다. 전체 저장소의 모든 테스트나 물리 회귀를 실행한 것은 아니다.
실행 전후 후보의 추적 파일 8,105개 SHA-256도 일치했다.

| 검사 | 결과와 의미 |
|---|---|
| 새 독립 검토 테스트 | **13 passed, 12 xfailed**; `strict=True, raises=AssertionError` |
| 새 반례의 xfail 해제 | **13 passed, 12 failed**, 수집/setup 오류 0. 9개는 R325B-1, 3개는 R325B-2 |
| 새 반례의 원인 대조 | 임시 subprocess 메모리에서만 invalid-target의 표 초기화와 색 skill의 M1 기본값을 적용하면 `--runxfail`로 **25 passed**. 제품 수정·최종 수정본 검증으로 세지 않음 |
| 기존 색 논리 변이 | **10/10 검출**. cyan-only dispatch 복귀, search kind 필터 제거, red hue를 cyan으로 교체, attachment/clip의 kind를 cyan으로 고정, placement/holding kind 장벽 제거, slot 필터 제거, controller 검색의 cyan 복귀, 종료 후 kind 소실. 모두 assertion failure이고 수집/setup 오류 0 |

변이 스크립트는 후보의 `mutation_checks.py`를 읽고 직접 실행했다. 선택한 10개
변이에 대한 결과이며 전체 mutation coverage 수치가 아니다. 원문·새 반례·변이
재실행의 건수는 위 회귀와 합산하지 않는다. 소스는 변경하지 않았다.

원인 대조의 첫 시도는 검토 worktree에서 plugin을 먼저 import하여
`ModuleNotFoundError`로 종료했다. 검출 성공으로 세지 않았고 로그를 보존했다.
후보 archive를 cwd로 지정한 `causal-repair-positive-v2`에서 위 25개 통과를 확인했다.

## 원격 CI

검토 SHA의 [Actions run 36739858172](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36739858172)는
**32 SUCCESS + 1 CANCELLED**다. `offline-regressions`는 SUCCESS지만
`ubuntu-simulation-scenarios`는 CANCELLED여서 전체 CI 통과로 보고하지 않는다.
취소 원인을 제품 결함으로 추정하지 않는다. 정상 CI 완료는 수정 후 병합 조건으로
남는다. PR은 DRAFT이며 검토자가 CI를 취소·면제·재실행하거나 workflow를 바꾸지 않았다.

## 입력·네 조건·인수 범위

- 새 색 경로의 실제 정보는 자기 RGB, 자기 발행 servo/PWM·명령 이력,
  자기 영상 위치 추정, 공개 coarse order, 정적 지도·보정이다. 새 world/GT/접촉/
  상대 private 상태 조회나 이를 이용한 단계 전환은 발견하지 못했다. R325B-2의
  기본 skill 모드 결함은 별도로 해결해야 한다.
- 세 kind는 동일 wrist 상태 기계와 공통 confidence/형상 규칙을 사용한다.
  unknown·can·tile·crate·beam은 색 배송 경로에서 계속 거절한다.
- 네 통신 조건의 가짜 API 입력에서 같은 executor/profile/factory를 쓰며,
  새 여섯 모듈에는 condition별 제어 분기가 없다. **실제 네 조건의 host/runner와
  새 실행 bundle은 아직 연결되지 않았다.** 따라서 실행 구성 해시의 네 조건
  동일성이나 메시지 전달까지 포함한 E2E 완료를 확인한 것은 아니다.
- 25개 RGB fixture는 독립 제작 규칙의 **합성 라벨**이다. PNG/JPEG와 해시는
  보존됐다. 최초 구현과 같은 `ae9726a3` 커밋이므로 구현 전에 고정됐다는 시간
  순서는 독립 입증할 수 없다. 작성자가 이 한계를 수정 기록에 반영했다.
- 로컬 물리/SIM/렌더/실제 모델 호출 **0회**. v3 FK/IK·카메라/provider admission,
  host 연결·새 bundle, distractor의 실제 가시성과 red→B/green→C 정상·실패
  4셀의 인수는 미검증이다. staging 포함 4×900=3,600 SIM초는 미실행 제안이다.
- 새 실험·학습·평가 코호트가 없어 TensorBoard 변환·viewer를 만들지 않았다.
  코드/fixture 회귀를 물리 결과로 변환하지 않았다. Drive 작업 없음.

## 재현과 증거 위치

원본 로그·JUnit·실행 명령·환경·archive 대조와 변이 기록:
`/Users/changmin/projects/ugrp/outputs/review-325b-20261001/`.
이 raw는 로컬 보관이며 원격 백업이 아니다. 검토 문서와 테스트는 Git에 보존한다.

```sh
git archive origin/codex/red-green-m1 | tar -x -C <scratch>
export REVIEW_325B_TREE=<scratch>
export PYTHONPATH=<scratch>/experiments/2026-09-30-cap-t03-redgreen:<scratch>
export PYTHONDONTWRITEBYTECODE=1
# 검토 worktree에서, 기존 .venv-sim-worker-mac/bin/python 사용
python -m pytest -p offline_guard -p no:cacheprovider --import-mode=importlib -q \
  tests/test_review_325b.py
python -m pytest -p offline_guard -p no:cacheprovider --import-mode=importlib -q \
  --runxfail tests/test_review_325b.py
# 실제 수정 전 bytes에 같은 복원 assertion을 적용
REVIEW_325B_PIN_REF=be97d9dd53638a1efbda7627b420bd9b1cbd9880 \
  python -m pytest -p offline_guard -p no:cacheprovider -q \
  tests/test_review_325b.py -k g3251_restored
```

`run_baseline.py`와 `baseline-command.json`은 정확한 37파일·제외 표현식·환경을
기록한다. archive의 Git 이력 조회에는 실제 저장소의 `GIT_DIR`, archive의
`GIT_WORK_TREE`, `GIT_OPTIONAL_LOCKS=0`을 지정했다. 새 테스트는 candidate 경로를
지정하지 않으면 Git blob 보존 검사만 실행하고 18개 행동 검사는 명시적으로
skip한다. 위 결과는 candidate를 지정한 실행이며 skip으로 통과시킨 것이 아니다.

## 증거 해시

`verification.json`에 명령·환경·검사별 실패/오류·소스 불변성·전체 raw 해시를 묶었다.
최종 fetch에서도 main과 후보 SHA는 위 값 그대로였다.

| 로컬 파일 | SHA-256 |
|---|---|
| `baseline.xml` | `fab6875207357b3398b1cfe6bb3afdaf26d88adbda0e5c5d1d22687e7fedb4bd` |
| `candidate-audit.json` | `544774842c00a6a5641b10ae04046a855d35363904f5c4a07769a6c03f5cc9d7` |
| `counterexamples-unmasked.xml` | `bfb52d99d6e59e1d5f98373b371dada7bc11809716b60a5e638410fa3a74bfad` |
| `mutations/summary.json` | `42abccab6ed304771b4968063dd1950910585cae8dc24ba0b9a768a4103c311c` |
| `causal-repair-positive-v2.xml` | `a9e8b5ce594dc1fff553ee91985d0bf7dd702c7f42bc5be92b1e4deae1da7d82` |
| `verification.json` | `fb3e915e1825e772fb11afaa26ed0773df1a9656087346a1d2f97c1fcadc3cf6` |
