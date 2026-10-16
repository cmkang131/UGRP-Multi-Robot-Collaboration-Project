# PR #234 적대 리뷰 수정 — 물리 코호트 미실행

기준 `eebab596`의 P1 3건·P2 1건을 수정했다. v2와 기존 실험 기록은 바꾸지 않았다.
이 폴더는 수정 전후 단위 검사 기록이며 새 물리 실험 결과가 아니다. 커밋은 coordinator가 수행한다.

## 변경과 근거

| 항목 | 수정 | 수정 전 재현 |
|---|---|---|
| P1 배치 | `m1_owncam_memory_v3.py`: 새 pose fix + lift-top issued posture + 자기 RGB 화물 부착 + 목표 자세 확인. `occupied` 거부, `unknown` 유지. 기존 reanchor/probe를 게이트 앞에서 수행 | s162/s164/s165 저장 자세 3개에서 게이트 거부 |
| P1 반복 look | `owncam_drive_mem_v3.py`: xy뿐 아니라 yaw도 short 2° / full 3° 이하일 때만 재시도 예산 초기화. 실패 2회 뒤 `pose_unverified` | loaded/unloaded × short/full 4개에서 6회 뒤에도 미종료 |
| P1 miss yaw | `owncam_visibility_v3.py`, `owncam_memory_v3.py`: yaw ±2σ 연속 범위를 포괄하고 FOV·가림 모두 확인 | σyaw=0.5 rad에서 +2σ는 시야 밖인데 miss 허용 |
| P2 팔 가림 | 열린 SEARCH의 보수적인 시선 영역만 허용. 집게 아래 시선·미검증 자세는 miss 보류 | FOV 안의 0.42 m 상자에 팔 가림 거부 없음 |

새 검사 `tests/test_owncam_memory_v3_review.py`를 CI `TEST_PATTERNS`에 추가했다.
새 visibility 파일은 v3 runner의 소스 해시 목록에도 포함했다. 기존 v3의 “빈 슬롯만으로 배치 허가” 검사는 새 계약에 맞춰 부착 근거도 요구하도록 수정했다.

## 배치 증거의 범위

`tests/fixtures/owncam_memory_v3_place/`에 세 경로의 해제 직전 자기 RGB 2장씩, 자기 발행 servo, 자기 PF 보고서, 해제 자세 명령과 정적 목적 슬롯을 복사했다. 원본 경로·SHA-256은 `provenance.json`에 있다. 정답 좌표·접촉·물리 성공 판정은 입력에 넣지 않았다.

저장된 위치·방향에서 loaded LOOK/CARRY 전체 pan의 가시 슬롯 셀은 모두 0/4다. 동일 RGB 쌍의 기존 `compare_box_comotion(min_saturation=150)`은 3/3 통과한다. 새 게이트와 상위 제어기의 스킬 호출도 3/3 통과한다. 단, v2 기록에는 v3의 innovation/likelihood 일관성 자료가 없으므로 테스트는 새 fix의 일관성을 명시적 사전조건으로 공급한다. 세 에피소드의 v3 재실행 성공을 뜻하지 않는다.

배치 허가는 **해제 준비 확인**이다. 위치 3 cm·평균 yaw 0.04 rad 제한은 기존 도착/이동 허용 오차 수준이며 저장 seed 결과로 최적화하지 않았다. 새 영상에서 화물이 유지되고, 준비 자세가 복원되고, 목적 자세에 있어야 한다. 바닥 `unknown`은 그대로 남기며 이벤트에 `empty_slot_verified=false`를 기록한다. 알려진 장애물은 즉시 `SLOT_OCCUPIED_IN_MEMORY`로 종료한다. 보이지 않는 새 장애물 부재까지 증명하지 못한다. 성공 판정은 기존 해제 후 자체 영상 확인을 그대로 거친다.

## yaw와 자기 팔 가시성

거리 r, yaw 반폭 a에 대해 `2r sin(min(a, π)/2)`로 연속 회전 구간의 최대 이동을 감싼다. 상자·자기 위치의 2σ 반경을 합해 동시 극값도 포함한다. affine 카메라 변환과 pinhole frustum의 볼록성, fisheye 방사 다항식의 전 구간 극값을 확인한다. 알려지지 않은 확장 왜곡은 보류한다. 벽/전경 가림은 가능한 시선 전체를 감싼 사각형과 겹치면 보류하므로 시선 사이의 얇은 가림도 놓치지 않는다. 낮은 벽까지 보류할 수 있어 보수적이다.

자기 팔은 새 분할 모델이 아니다. 고정 기하와 발행 PWM으로 열린 SEARCH만 허용한다. 이 자세의 어깨·팔꿈치·손목은 카메라 뒤에 있다. 렌즈 원점의 tool 좌표 `(0.067, 0, 0.0136)`에서 전방으로 가며 tool z 기울기 `[0, 0.5]`인 시선은 앞 집게 상단 0.0056 m보다 높고 렌즈 외형 하단 0.016 m보다 낮다. 모든 불확실성 영역이 이 범위 안이어야 한다. 집게 사이의 실제 빈 공간도 보류하며, 나머지 팔 자세는 부재 증거로 사용하지 않는다. 실물 장착 공차와 동적 가림은 아직 검증하지 않았다.

## 검사 재현

Python `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`,
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1`.
OpenCV 5.0.0의 GCD 빌드는 이 환경변수와 양수 `setNumThreads(1)`로 제한되지 않았다. 최종 실행기는 `cv2.setNumThreads(0)`으로 병렬 영역을 끄고 `getNumThreads()==1`을 검사한다. 모든 pytest 호출에 `--basetemp=./.pytest_tmp`를 사용했고 병렬 worker는 사용하지 않았다. MuJoCo·물리·학습 프로세스를 시작하지 않았다.

| 범위 | 결과·로그 |
|---|---|
| 코드 수정 전에 추가한 네 결함 재현 | 9 failed — `before.txt` |
| 최종 테스트로 기준 코드만 다시 읽어 대조, 모든 수치 스레드 1 | 9 failed, 36 deselected — `before-single-thread.txt` |
| 새 리뷰 회귀·경계 45 + 기존 v3 45 + 관련 기존 검사 113, 모든 수치 스레드 1 | 203 passed, 382 subtests passed — `final-single-thread.txt` / `verification.json` |

수정 중의 fixture 누락, 강화된 계약에 따른 기존 테스트 수정, 부동소수점 경계 실패도 `after-initial.txt`, `after-boundaries-initial.txt`, `after-boundary-numeric.txt`에 보존했다. 수치 경계는 1e-12 m의 반올림 여유로 처리했다. `after.txt`의 90 passed와 `related-tests.txt`의 113 passed/382 subtests passed는 OpenCV 자체 제한 전의 중간 결과다. 양수 thread 설정의 사전 검사 실패도 `opencv-thread-preflight.txt`에 남겼으며, 이 호출은 테스트를 시작하지 않았다.

기준 코드 대조는 환경변수 설정 후 `python experiments/2026-09-27-zone-owncam-memory-v3/review-fixes/run_review_tests.py --baseline`으로 실행한다. `git show`로 세 기준 모듈을 메모리에만 읽고, checkout/index/소스 파일을 바꾸지 않는다. 9개 assertion 실패(exit 1)가 기대 결과다. 최종 검사는 같은 실행기에 `-q --basetemp=./.pytest_tmp`와 `tests/test_owncam_memory_v3_review.py tests/test_owncam_memory_v3.py tests/test_owncam_memory.py tests/test_m1_owncam.py tests/test_owncam_localizer.py tests/test_visual_attachment.py tests/test_wrist_zone_skill_v9.py`를 넘긴다.

## 남은 확인

- coordinator의 diff 검토·커밋·원격 CI. 이 작업은 `.git`을 쓰거나 커밋하지 않는다.
- PR #227 연결 후 dev 전용 검증: 새 부착 게이트, 가림 보류로 인한 오래된 keep-out, 불확실 pose의 명시적 실패 빈도. 새 관측원과의 기하/진단 계약을 다시 고정한다.
- `prereg_review_DRAFT.json`은 DRAFT/실행 불허다. 기존 DRAFT를 덮어쓰지 않았고 seeds도 예약하지 않았다. coordinator가 새 seeds와 조건을 최종 동결한 뒤 새 코호트를 수행한다.
- 단위/저장 입력 검사뿐이므로 성공률·속도 효과·TensorBoard 결과를 추가하지 않았다.

## 참고 자료

- coordinator가 제공한 `codex-234-review.md` 전체. 출처 경로와 파일 해시는 `verification.json`에 기록한다.
- [memory_v3 설계](../../../docs/design/2026-09-27-owncam-memory-v3.md), [초기 구현 기록](../README.md). 초기 문서의 unknown 배치 차단 설계는 이번 수정으로 대체한다.
- `harness/visual_attachment.py`, `harness/wrist_zone_skill.py`: 기존 자기 영상 부착·해제 후 확인 계약.
- `harness/visual_arm.py`, `sim/masterpi_scene_v2.xml`: 정적 팔·집게·카메라 기하. 실행 시 시뮬레이터 상태를 읽지 않는다.
