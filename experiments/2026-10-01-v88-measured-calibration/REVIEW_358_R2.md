# PR #358 독립 재검토 R2 — MERGE AFTER FIXES

- 검토자: Codex. 대상 PR head: `576bf4dad2d1fa1d6d8613564929d0f4b7b455bf`.
- PR diff 기준 base: `0bf41800272ec4c4bfa035cfc5609af8850e3e48`. 종료 전 fetch의 `origin/main`은 `db37ee4aae073dbd1c2d1a206b31dd64412fbea5`이며 PR head는 그대로다. 이전 검토: `REVIEW_358.md`, 수정 답변: [5965864829](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/358#issuecomment-5965864829).
- 실행일: 2026-10-03 KST. 실행 checkout: `codex/review-358`, clean `4447e389f5a00aa436c35eb50002cf64da29c7d1`. 이전 리뷰를 보존하고 PR head를 merge한 기록용 SHA이며, PR head와 `scripts/`, `harness/`, `sim/`, `tests/`, `configs/`, `.github/`의 모든 바이트가 같다.
- 결론: **앞선 qpos/50 ms 지적은 해소됐다. 아래 P2 회귀시험 수정과 최신 CI 전체 통과가 남아 있어 지금은 병합 불가다.** 새 P0/P1은 발견하지 않았다. 소스·시험을 고치는 대신 독립 검토와 증거만 기록했다.

## 지적 한 묶음

**P2 — `sim_time` 전환에 빠진 기존 회귀시험 때문에 필수 CI가 실패한다.**

위치: `tests/test_review_351b.py:103–109,122`; 관련 변경 `tests/test_final_pair_calibration_assembly.py:144,205`, 소비처 `scripts/final_pair_calibration_io.py:287–289`.

기존 `test_nonfinite_times_in_each_sample_record_fail_closed[frame]`은 모든 레코드에 `['t']`를 쓴다. 그러나 이 PR의 공용 합성 fixture와 실제 writer의 frame 시간은 `sim_time`이다. 이 시험은 정상 `sim_time`을 그대로 둔 채 사용하지 않는 `t=NaN/±Inf`를 추가하므로 r1/r2 여섯 경우 모두 loader가 통과한다. 이는 실제 frame 시간의 비유한 값을 허용하는 reader 결함이 아니라 **회귀시험의 스키마 이관 누락**이다.

- 해당 parametrized 시험 6개를 로컬 재실행: **1 failed, 5 passed in 172.43s**. `[frame]`만 실패하며 GitHub와 동일한 `AssertionError`를 재현했다.
- [CI run 37099156448](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37099156448)은 대상 SHA에서 `offline-regression-shard (0/8)`와 필수 집계 `offline-regressions`가 **FAILURE**다. shard 0은 `1 failed, 1340 passed, 18 skipped, 13 xfailed, 7 subtests passed`이며 동일 시험이 유일한 실패다. 확인 당시 PR은 `MERGEABLE`, `BEHIND`다.
- 저장소 파일은 바꾸지 않고, 시험 소스를 메모리에 로드해 해당 키만 `['sim_time' if record == 'frame' else 't']`로 치환하는 진단을 실행했다. r1/r2 × NaN/+Inf/−Inf **6/6 거부**, 모두 `frame clock must be a finite numeric time`이었다. 이는 제안 수정의 진단이며 현재 저장소 시험 통과로 합산하지 않는다.

**요청:** frame에만 `sim_time`을 오염시키도록 위 시험을 이관하고 나머지 다섯 레코드의 `t` 검증을 유지한다. 해당 회귀시험과 관련 시험을 재실행하고 최신 base 반영·최종 head의 필수 CI 전체 통과를 확인한다. 이 문제를 workflow 제외/skip이나 reader의 옛 `t` 지원으로 우회할 이유는 없다.

증거: [로컬 실패](review358r2-evidence/nonfinite-times.txt), [JUnit](review358r2-evidence/nonfinite-times.xml), [CI 원문 발췌](review358r2-evidence/ci-failure-excerpt.txt), [키 치환 진단](review358r2-evidence/corrected-frame-key.json), [CI 상태](review358r2-evidence/pr-ci.json).

## 이전 P2 수정 검증

1. `scripts/final_pair_calibration_io.py:20–25,132–183,266–271,306–321`: XML의 joint 순서·종류에서 실제 qpos/qvel 주소를 구하고, 같은 timestamp의 qpos 위치·quaternion과 label을 `atol=1e-8, rtol=0`으로 비교한다. `implicitfast`, dt=0.00025 s를 검사하고 pose는 `p-dt*v`, `R @ Exp(-dt*w_local)`의 직전 substep 상태와 별도 비교한다. fit용 배열은 원본 pose의 x/y/yaw와 **정확히 동일**했다. 복원값을 fit에 대체하지 않는다.
2. 독립 NumPy/SciPy 계산으로 세 수집 × 두 로봇의 **11,106 label / 44,406 pose**를 확인했다. label 대 같은 instant qpos의 최대 위치 오차는 **0 m**, 회전행렬 원소 오차는 **2.3314683517128287e-15**. 첫 reset 표본은 현 qpos와 비교하고, 나머지는 역산한 pose와 비교할 때 전체 최대 위치 **1.1102230246251565e-16 m**, 회전 원소 **2.4424906541753444e-15**다. 모두 `1e-8` 이내다.
3. `tests/fixtures/review_358_chassis.json`의 원본 scene/trajectory/pose/label 해시 4개와 전체 label 522, pose 2088/2089, qpos/qvel 배열을 실제 loaded raw와 직접 비교했다. 모두 정확히 같고 실제 시각 차이는 **0.04999999999881766 s**다.
4. `tests/test_final_pair_calibration_assembly.py:747–825`는 실제 두 표본의 위치만/회전만/둘 다 × pose/label/qpos **9개 오정렬**, qpos/qvel·quaternion·clock **9개 오류**를 검사한다. 별도로 실제 raw를 읽는 loader에서 pose[2088]의 위치만·회전만·둘 다를 2089 값으로 교체하고, label[522]의 회전만 이웃 pose로 바꾸는 **4개 in-memory 반례**를 실행했다. 수정 전 `9b8a89c4` IO는 4/4 수용하고 현재 IO는 4/4 거부했다. 시각/index는 유지했고 원본 파일은 변경하지 않았다.
5. clock/순서/ID/hash 검사가 유지됐고, 정지의 동일 상태값으로 모든 이웃 시각을 증명할 수 없다는 한계도 코드와 수정 기록에 반영됐다.

[독립 계산·실제 반례 결과](review358r2-evidence/independent-audit.json), [실행 코드](review358r2-evidence/independent-audit.py).

## 방법·임계값·동결 기준

25파일을 이전 검토 head 및 base와 직접 바이트 비교했다([전체 비교와 SHA256](review358r2-evidence/unchanged.json)). B/B′, r4 및 보고서, assembler 본체, motion fit과 B validator, writer·의존 파일, bundle registry, simulation workflows, contract가 불변이다. camera fit 모듈은 이전 검토 head와 바이트 동일하고 base 대비 변경은 `['t']` → `['sim_time']` 세 곳뿐이다.

따라서 **fit 방법·선별/수치 임계값·동결 판정 기준은 그대로**다. 이번에 바뀐 `1e-8`은 입력 pose 감사의 허용오차이며, 앞선 `1e-4/2e-3` 완화를 되돌린 것이다. `.github/workflows`는 base 대비 및 작업 중 변경이 없다.

| 동결 파일 | SHA256 |
|---|---|
| B | `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f` |
| B′ | `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33` |
| r4 | `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071` |

## 재실행

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python` 사용. Python **3.12.13**, NumPy **2.5.2**. 아래 시간은 pytest 출력이며 성능 비교가 아니다.

```sh
python -m pytest -q tests/test_final_pair_calibration_assembly.py tests/test_review_355.py --junitxml=<evidence>/tests.xml
python -m pytest -q tests/test_review_351b.py::test_nonfinite_times_in_each_sample_record_fail_closed --junitxml=<evidence>/nonfinite-times.xml
```

- 조립기 + #355 관련 시험: **423 passed in 677.66s (384 + 39, 실패/오류/skip 0)**. [stdout](review358r2-evidence/tests.txt), [JUnit](review358r2-evidence/tests.xml).
- 추가 CI 실패 재현: 위의 **5 passed / 1 failed**. 이 실패를 제외한 성공으로 전체 CI 통과를 주장하지 않는다.

완료된 v88 세 수집만 새 임시 symlink root `/tmp/review358r2-20261003-145855/raw`에 연결해 **실제 assembly 1회**를 실행했다. 원본 경로의 공통 접두사는 `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001`이며, unloaded는 `/calibration-unloaded`, fine은 `-r6/calibration-fine`, loaded는 `-r8/calibration-loaded`다.

```sh
python -m scripts.assemble_final_pair_calibration \
  --raw-root /tmp/review358r2-20261003-145855/raw \
  --output /Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-review358r2-20261003-145855
```

**exit 2 / PARTIAL / collection_audit PASS ×3 / missing 42**. 실행 SHA `4447e389…`, `working_tree_dirty=false`, `raw_unchanged=true`, input manifest **11,360파일**. 이전 검토 출력과 `status/params/pair_model/pan_base_yaw/camera_models/missing` 전부 동일하고 `fit_report.json`도 전체 바이트 동일하다. loaded selection도 lifted **6839**, not_lifted **553**, missing_bilateral_grip **9**로 동일하다.

| missing 사유 | 개수 |
|---|---:|
| frozen B의 unloaded 3축 판정 null / 완전 프로필 미승인 | 10 |
| loaded motion `fit convergence/rank/boundary failure: rank 13/13` | 16 |
| pair `measurement not available` | 5 |
| loaded pan 동일 arm 기준 양부호 정지 표본 부족 | 1 |
| loaded camera 안정·상승·양손 접촉 표본 없음 | 5 |
| loaded camera residual/count gate 거부 | 5 |
| 합계 | **42** |

[명령·exit code](review358r2-evidence/assembly-command.json), [결과 대조·정확한 사유 문자열·해시](review358r2-evidence/assembly-verification.json).

| 새 산출물 | SHA256 |
|---|---|
| calibration.json | `a198d3424e0aa4458ad3509ca7cc5a831dd25c76bcc4aa2dcc4f53aae9cead47` |
| fit_report.json | `121b870fa52c7357fdfa946aa0f5999c8c209c3cee5830406888fc50685d03b7` |
| input_manifest.json | `0ab7f4238cecd0cb1e949e53826bcbd4b0773a6b258aa0ac8f8ac343265a375b` |

## 범위

v91 held-out 데이터는 identity 필드도 읽지 않았다. 물리·렌더·모델 호출, 기존 프로세스 조작, workflow 수정 없음. 허용된 v88 raw는 읽기 전용으로 사용하고 각 독립 감사 뒤 해시를 재검증했다. 새 실험 코호트가 아닌 기존 결과의 동일한 재조립이므로 TensorBoard 중복 변환·뷰어 시작을 하지 않았다. raw/전체 조립 출력은 로컬 보관이며 원격 raw 백업을 뜻하지 않는다. 기존 **42개 누락, MEASURED_SIM/물리 성공 미승인**은 유지한다. PR 병합은 수행하지 않았다.
