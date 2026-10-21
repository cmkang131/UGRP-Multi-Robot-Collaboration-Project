# act18 D4 장면 적합성 시험: nav v6 중립 픽업 바닥 (2026-10-21)

상태: **DONE**. 판정: **BRANCH_NAV_V5** — G(v6 C2c-HO4, N=1) = **1/4** ≤ 1/4이므로 nav v5 장면 재보정 대상이다. 이 작업은 **보고만** 했고 코드·모델·기존 결과는 고치지 않았다. v5 C2c 결과(rep1 4/4, 합계 11/12)는 문맥으로만 적고 **합산하지 않는다**.

## 1. 결론

- ACT C2c 구성(R8 step-100000 + v7 own-issued clock deadband 2)을 `UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1` 장면에서 HO4 × N=1(4 world)로 평가했다.
- **G = 1/4** (88668만 grasp done 전에 3 s stable lift 완료). Pre 2, done 3, lift 1, release 0, task 0, cap_end 2.
- 사전등록 `SCENE_FIT_PREREG.json`(FROZEN, sha256 `9c2b5ba2…`, commit `7aa8c3d`)의 판정식: G ≥ 2/4 → `UNIFY_V6`, G ≤ 1/4 → `BRANCH_NAV_V5`. 결과는 **BRANCH_NAV_V5**.
- `analysis.json`의 `acceptance.verdict`는 분석기의 일반 C2c 게이트(4/4 요구) 때문에 `FAIL`로 찍히지만, D4 사전등록 판정은 위 `BRANCH_NAV_V5`다. 두 필드를 혼동하지 않는다.

| seed | kind | grasp done | release done | stable lift(t) | G | Pre | lift | release | task | cap_end | 기록된 실패 사유 |
|---:|---|---:|---:|---:|:--:|:--:|:--:|:--:|:--:|---:|---|
| 88668 | cyan | 31.6 s | — | 22.5 s (max 15.3 s) | ✅ |  | ✅ |  |  | ✅ | release_done_not_requested |
| 88669 | red | — | — | — |  |  |  |  |  | ✅ | grasp_done_not_requested |
| 88670 | green | 31.7 s | 43.4 s | — |  | ✅ |  |  |  |  | lift_not_stable |
| 88671 | yellow | 30.2 s | 41.0 s | — |  | ✅ |  |  |  |  | lift_not_stable |

group별 SIM: group-000 90.0 s, group-001 90.0 s, group-002 44.9 s(2 world). stage wall **861.2 s**, 그룹 종료코드 3/3 = 0.

release는 픽업 바닥 위에서 하므로 v6 픽업 타일의 영향을 가장 직접 받는 지표이지만, 사전등록대로 **보고 전용**이며 판정에 쓰지 않았다.

## 2. 실행

- 호스트: gcp2 `ugrp-act-l4-gcp2` (project `ugrp-sim-b-1014`, account `changmin5781@gmail.com`, zone `asia-northeast3-a`, g2-standard-8 / L4 1).
- 브랜치 `dsh/act18-scene-v6-fit`, source **`7aa8c3d873f47abfaaea93cf9c59668de44b73fc`** (코드 commit `d46fe8af7` + 동결 prereg commit `7aa8c3d`, VM clean clone `/home/ugrp/ugrp-sim/src/act18-scene-v6-fit-7aa8c3d87`).
- checkpoint `/home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000`, model sha256 `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a` (실행 전후 동일).
- env `UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1` — `C2c-ho4-rep1/launch.json`의 `env`에 기록됨.
- 유효 run root **`/home/ugrp/ugrp-sim/runs/act18/scene-fit-v6-20261021T0304Z`**.
- `check_current_stack.py` act_eval 통과(`current-stack-check.json`: `ok=true, current_compliant=true`), LLM 호출 0, weld off, top camera 제어 없음, `held_world_reads=0`.

## 3. v6 참조 재생성 (n/N)

| 항목 | 결과 |
|---|---|
| v6 C312 참조 생성 | **4/4** (`case-068..071`) |
| 사용한 참조 root | `/home/ugrp/ugrp-sim/runs/act18/scene-fit-v6-refs-teacher-20261021T0300Z` |
| 픽업 타일 | 케이스마다 **60** |
| ngeom | 1446 / 1444 / 1446 / 1446 (v5 1387 / 1385 / 1387 / 1387 대비 **+59**) |
| eval owner XML 일치 | **4/4** — `owner/world-*/scene.xml` sha256가 참조 `runtime-scene.xml`과 정확히 일치 |
| scene_fit manifest | `world-000/scene.json`의 `act18_scene_fit.mode = v6_neutral_pickup_v1` (참조 빌드에서 확인) |

생성은 `act17_v7_prepare.py`가 쓰는 정규 경로(`act17_v7.py --action launch --mode teacher --export-compiled-only`)를 4개 index(68–71)에 대해 그대로 실행했다. 이 경로는 eval owner와 같은 `act17_v7.installed()` 주석(teal/blue beam band, `scene_profile`/`end_color_scene` custom text)을 적용하므로 XML이 바이트 일치한다.

**초안 경로 실패(사용 불가)**: `COMMANDS_DRAFT.md`가 지시한 `scripts/act17_v7_rebuild_compiled_references.py`로 만든 참조(4/4 생성)는 eval owner XML과 **불일치(사용 가능 0/4)** 했다. 이 도구는 owner scene을 `act17_v7` 주석 없이 빌드한다(beam band 검정, custom text 없음). 그래서 첫 평가 시도가 `simalt_compiled_compat.apply_geometry: compiled geometry reference version/XML/hash mismatch`로 fail-closed 했다. 원본 참조 디렉터리는 삭제하지 않고 보존했다: `/home/ugrp/ugrp-sim/runs/act18/scene-fit-v6-refs-20261021T0248Z`. 코드 수정 금지 조건에 따라 도구는 고치지 않았다.

## 4. HOST_ERROR 시도 1과 재실행

- 시도 1 run root `/home/ugrp/ugrp-sim/runs/act18/scene-fit-v6-20261021T0248Z`: 그룹 3/3 exit 1, **HOST_ERROR**, 판정에 사용하지 않음. 사유는 위 참조 XML hash 불일치.
- 사전등록의 HOST_ERROR 규칙("판정 없음, 고친 뒤 새 root에서 재실행")에 따라 **새 root** `…0304Z`에서 1회 재실행했고 이번에는 3/3 exit 0, **DONE**.
- 동결 prereg의 `run_root` 필드는 `…0248Z`로 적혀 있으나, 실제 유효 결과는 HOST_ERROR 재실행 규칙에 따라 `…0304Z`에 있다. prereg 파일은 동결 후 수정하지 않았다.

## 5. 검증

- **원본 재계수**: `evaluation-only.jsonl` + `evaluation/summary.json`의 `student_scores` + `initial-plans.json`에서 G/Pre/lift/release/task/cap_end를 다시 계산해 `analysis.json`과 일치(4 world, G 1, Pre 2, done 3, lift 1, release 0, task 0, cap_end 2).
- **장면 적용**: eval owner `scene.xml` 4/4가 v6 참조 XML과 sha256 일치, 각 60 타일. launch env에 `v6_neutral_pickup_v1` 기록.
- **시드**: HO4 88668–88671만 허용(evaluator `diag_holdout`), TRAIN4/VAL8/FINAL40과 겹치지 않음.
- **체크포인트**: 실행 전후 sha256 동일, 변경 없음.
- **영상**: review-own/failure-window에서 17프레임을 확인(몽타주 `outputs/act18-scene-fit-20261021/raw/frames/montage.jpg`, sha256 `473cee0e…`). t=1 s 프레임에서 회색 픽업 타일 바닥이 보인다. 프레임만으로 조기 done·과노출의 제어 원인을 진단하지 않았다(지표 기록만).
- **원본 불변**: 기존 run root·참조·학습 산출물을 수정·삭제하지 않았다. 코드 변경 0, 추가 commit은 동결 prereg 1개뿐.

## 6. 원본·SHA·비용

- VM 원본: `/home/ugrp/ugrp-sim/runs/act18/scene-fit-v6-20261021T0304Z` (74 MB, 파일 전체 sha256 목록 `raw/scene-fit-run-full-sha256.txt`), 참조 `…-refs-teacher-20261021T0300Z` (8.4 MB, `raw/scene-fit-refs-full-sha256.txt`), HOST_ERROR 원본 `…-20261021T0248Z`.
- 로컬 사본: `/home/ubuntu/UGRP/outputs/act18-scene-fit-20261021/raw` (run logs/JSON/JSONL, refs, 선택 프레임 17장, 몽타주). 검색용 tar 3개와 SHA는 같은 디렉터리, 파일별 sha256은 이 실험 디렉터리의 `SHA256SUMS.json`(178 files).
- tarball sha256: run `337d337a…`, refs `09c0baa6…`, frames `dc5940ba…` (VM `sha256sum`과 로컬 값 일치).
- VM 시간: 2026-10-21T02:44:20Z start → 03:17:35Z stop, **33분 15초**. L4 GPU 시간 약 0.554 h. 비용 추정 **약 $0.61**(기록된 1.096 USD/h 기준, 약 870 KRW/1,430원 가정). 실제 청구 원장 금액은 **미확인**.
- 종료 확인: 프로세스 0, GPU 0 %, 이 작업 lease 제거, gcp2 **TERMINATED** 확인.

## 7. 미확인·남은 일

- 창민 직접 승인 문구는 이 작업자가 확인하지 못했다(상위 DSH 세션의 위임 지시로 실행, 11:45 KST 피크 완화 창).
- GCP 청구 원장 금액 미확인(위 비용은 추정).
- `leases/`에 이전 작업의 stale lease 5개가 남아 있다(2026-10-18/19, 프로세스 없음). 이 작업 lease는 제거했고 다른 lease 파일은 건드리지 않았다.
- 실패 원인은 지표로만 기록했다. 조기 done(88670/88671)·과노출 프레임의 제어 원인은 독립 진단하지 않았다.
- 초안의 `act17_v7_rebuild_compiled_references.py` 경로는 이 eval 경로에 재사용할 수 없다. 코드 수정 금지로 고치지 않았으므로, 이 도구를 다시 쓰려면 별도 수정·검증이 필요하다.
- nav v5 재보정은 이 작업 범위 밖이며 **보고만** 한다. R3 재학습·VAL8·FINAL40은 열지 않는다(`r3_retraining=no-go`).
