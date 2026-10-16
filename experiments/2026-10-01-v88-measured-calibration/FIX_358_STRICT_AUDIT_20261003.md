# PR #358 P2 수정 — 동시각 qpos 감사 (2026-10-03)

검토 기준: `origin/codex/review-358`의 `REVIEW_358.md`와 [댓글 5959693426](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/358#issuecomment-5959693426).
수정·실행 소스: `d36ffc3f9a34749770b995bc8f92d5aa5c97091d`. 이 기록은 실행 뒤 추가했다.

## 지적 → 수정

| 지적 | 수정·검증 |
|---|---|
| P2: 1e-4 m / 2e-3 감사가 실제 50 ms 이웃도 수용 | 라벨의 chassis pose를 같은 timestamp의 `trajectory.qpos` free-joint 위치·quaternion과 직접 비교. 위치·회전행렬 원소 모두 `atol=1e-8, rtol=0`으로 복구 |
| 같은 timestamp의 pose는 실제로 한 substep 전 기구학 | 기록 XML의 joint 순서·종류로 qpos/qvel 주소를 계산. `implicitfast`, dt=0.00025 s를 검사하고 `p-dt*v`, `R @ Exp(-dt*w_local)`와 기록 pose를 별도 비교. reset 첫 표본은 현 qpos와 비교. fit용 pose는 교체·보정하지 않음 |
| 임의 1 mm 이동 시험은 실제 이웃/회전 반례가 아님 | 실제 loaded r1 2088/2089, label 522의 원본 수치·시각·출처 해시를 `tests/fixtures/review_358_chassis.json`에 보존. 위치만/회전만/둘 다 × pose/label/qpos의 9가지 교체를 거부. 원래 값은 모두 통과 |
| 모든 이웃 시각을 구분한다는 설명이 과장됨 | 코드 주석·최초 수정 기록을 정정. 정지에서 동일 상태값만으로 시간 식별은 불가능함을 명시하고 clock/순서/ID/hash 검사를 유지. pose/trajectory clock과 label/trajectory clock은 같은 값이어야 함 |

누락·길이·비유한 qpos/qvel, 영/비정규 quaternion, 1 ns trajectory clock 변경도 거부하는 9개 회귀시험을 추가했다. 합성 fixture에는 같은 instant의 qpos/qvel과 XML joint 구조를 넣었다. writer·번들·fit·동결 기준은 변경하지 않았다.

## 검증

```text
423 passed in 507.47s (0:08:27)
```

- `tests/test_final_pair_calibration_assembly.py`: **384 passed**.
- `tests/test_review_355.py`: **39 passed**. 실패·오류·skip 0. 시간은 pytest 출력이며 속도 벤치마크가 아니다.
- [실행 명령·파일별 집계·로그 해시](fix-358-evidence/verification.json), [stdout](fix-358-evidence/related.txt), [JUnit](fix-358-evidence/related.xml).
- 수정 전 `9b8a89c4` IO만 메모리에 로드하면 새 `both-pose`, `rotation-label` 시험이 둘 다 `DID NOT RAISE ValueError`로 실패한다([출력](fix-358-evidence/regression-before.txt)). 파일을 되돌리거나 raw를 수정하지 않았다.
- 실제 원본 loaded 수집에서도 pose[2088]의 시각/index를 유지하고 pose[2089]의 위치만·회전만·둘 다를 교체하는 세 경우가 모두 `recorded chassis pose differs from trajectory pre-substep state`로 거부됐다. 세 정상 수집은 PASS이고 해시 재검증도 통과했다([기록](fix-358-evidence/real-audit.json)).
- 개발 중 첫 집중 시험은 SciPy의 선택적 Torch 감지가 기존 오프라인 차단 fixture와 충돌해 10 failed/8 passed였다. 최종 구현은 NumPy만 사용하며 집중 시험 18 passed, 위 전체 시험 423 passed를 확인했다.
- [25개 파일의 바이트/해시 비교](fix-358-evidence/unchanged.json): B/B′, r4와 보고서, assembler 본체, motion/camera fit, writer·의존 파일, bundle·workflow·contract가 수정 전과 동일하다. `.github/workflows`도 변경 없음.

## 새 v88 조립

기존 완료 수집 세 개만 임시 symlink root로 묶었다. 입력은 아래 경로이며 원본 변경 없음이다.

- unloaded: `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded`
- fine: `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001-r6/calibration-fine`
- loaded: `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001-r8/calibration-loaded`

새 출력: `/Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-fix358-20261003-140522`.
[정확한 argv/exit code](fix-358-evidence/assembly-command.json), [출력](fix-358-evidence/assembly.txt), [결과·비교·SHA256](fix-358-evidence/assembly-verification.json).

**unloaded PASS / fine PASS / loaded PASS**, exit **2**, 상태 **PARTIAL**, 누락 **42개**.

| 누락 사유 | 필드 수 |
|---|---:|
| 동결 B unloaded 3축 판정 null, 완전 프로필 미승인 | 10 |
| loaded motion `fit convergence/rank/boundary failure: rank 13/13` | 16 |
| pair model `measurement not available` | 5 |
| loaded pan 같은 arm 기준 양부호 정지 표본 부족 | 1 |
| loaded camera: 안정·상승·양손 접촉 표본 없음 | 5 |
| loaded camera: residual/count gate 거부 | 5 |

loaded selection은 lifted **6839**, not_lifted **553**, missing_bilateral_grip **9**다. 이전 독립 리뷰 출력 `final-pair-v88-measured-review358-20261003-035937`과 `status/params/pair_model/pan_base_yaw/camera_models/missing`이 전부 동일하며, **fit_report.json 전체 바이트도 동일**하다. 누락 필드 이름과 사유를 새 calibration.json에서 모두 대조했다.

input_manifest: `execution_source_sha=d36ffc3f…`, `working_tree_dirty=false`, `raw_unchanged=true`, 입력·소스 **11,360파일**, Python **3.12.13**, NumPy **2.5.2**.

| 산출물 | SHA256 |
|---|---|
| calibration.json | `7ad491338ef32dc94c6a73bc4e02f50f92a1324c48ab083ab02194d342c40843` |
| fit_report.json | `121b870fa52c7357fdfa946aa0f5999c8c209c3cee5830406888fc50685d03b7` |
| input_manifest.json | `3eae04111646078363caabc5c07cb7e16bba166698bc43c5f10bcc93bd5baf7e` |

## 범위와 남은 일

v91 held-out raw 접근·채점, 물리·렌더·모델 호출 없음. 기존 v88 코호트의 오프라인 재조립이며 fit 결과가 바이트 동일하므로 TensorBoard 중복 변환·뷰어를 시작하지 않았다. raw와 전체 조립 출력은 로컬 보관이며 원격 raw 백업을 뜻하지 않는다.

이번 수정은 P2 입력 감사를 고친 것이다. PARTIAL의 기존 42개 누락과 MEASURED_SIM/물리 성공 미승인은 유지한다. 변경 범위의 독립 재검토와 PR CI 확인은 별도이며, 이 기록에서 병합 완료를 주장하지 않는다.
