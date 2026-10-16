# PR #234 5차 리뷰 수정

기준 HEAD `2fadd08a0a49d94af21f54275f60e07645fb6677`, 브랜치 `codex/zone-owncam-memory-v3`.
제공된 `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-234-review5.md`의 P1 두 건과 coordinator의 ON/OFF 안전 조건 통일 결정을 반영했다. 단위·저장 입력 재생 검사이며 새 물리 실행이나 코호트 결과가 아니다. 커밋·push·PR 수정·병합은 하지 않았다.

## 변경과 비교 범위

- **P1-1:** 공통 `harness/owncam_safety_v3.py`의 fix 인정은 short/full 동일하게 unloaded xy 0.04 m / loaded 0.05 m, yaw 2°다. 이동 상한 xy 0.05/0.07 m, yaw 3°는 유지한다. 도착 fix는 yaw 1.3°로 여유를 두고 복귀 후 기존 도착 상한 xy 0.05/0.06 m, yaw 2°를 재검사한다. 현재 σ를 이동량으로 우회하지 않는다. 실패 2회면 `pose_unverified`; 정상 fix로 초기화되지 않는 별도 정체 예산(최대 4 looks 또는 60 SIM s)을 두어 `look_stagnation`으로 종료한다. 주행 상태에서 발행된 비영 이동 명령과 자기 추정의 목표 거리 0.10 m 이상 감소가 함께 있어야 정체 예산을 초기화한다. hold/stop은 이동 명령 증거를 지운다.
- **P1-2:** 초기 sweep 거부 시 팔·pan·차체를 움직이지 않고 hold/capture로 추가 관측한다. 첫 거부부터 8 SIM s / capture 요청 20회 / 0.2 SIM s 간격, 전체 초기화 30 SIM s의 한도를 고정한다. 같은 시각 capture 반복·오래된 프레임 재시도를 막는다. 거부된 sweep은 실제 look 예산에서 빼고 수렴한 새 프레임으로만 재시도한다. 복구 시간은 재거부·sweep 생성으로 연장되지 않는다. 한도 초과는 `NOT_INITIALIZED`. 재개된 sweep도 공통 충돌 검사와 발행 직전 재검사를 통과해야 한다.
- **조건 통일:** v3 runner의 `off`는 `M1OwnCamDeliveryOffV3`로 연결한다. ON과 같은 제어기/안전 메서드에서 `memory_look_enabled=False`만 다르다. 현재 σ, 일관성, fix/도착, sweep/명령 충돌, 실패·정체·초기화 상한뿐 아니라 트랙/keep-out·목표 선택·조작·슬롯 안전도 공유한다. 차이는 주행 재관측 trigger, gate/주행 short/full pans·조기 종료, 탐색 coverage에 따른 관측점/pan 생략이다. OFF는 고정 trigger·full sweep을 쓴다. **전체 메모리 제거 효과가 아니라 기억 기반 재관측 결정의 ablation**이다.
- 과거 OFF는 `off_legacy`, v2는 `memory_v2`로 재현 가능하며 원본 소스/기록 23개 SHA-256 보존 검사를 통과했다. 이 둘은 matched 비교에서 제외한다. 기존 REGISTERED prereg의 `off` 의미가 바뀌지 않도록 새 안전 계약이 없는 비교 실행을 거부한다. runner에 조건 역할·안전 계약·공통 모듈 해시를 기록한다. 설계 문서와 최상위 prereg 초안을 갱신했고, 과거 리뷰별 DRAFT 스냅샷은 보존했다. 최신 prereg도 DRAFT/실행 미허가다.

## 수정 전/후 근거

| 검사 | 수정 전 | 수정 후 |
|---|---|---|
| P1-1, 실제 태그 계획기 + loaded PF 예측 + 상태기계, 합성 posterior yaw 2.9° | 160 SIM s: short 13, full 12, 이동 명령 0, 종료 없음 | 12.3 SIM s: short 1, full 1, 이동 명령 0, `pose_unverified` |
| P1-1, 반복 정상 fix / 이동 없음 | 8회에도 종료 없음 | 4 look 뒤 다음 요청에서 `look_stagnation`; 시간 상한도 별도 검사 |
| 정상 회복 대조, 합성 full posterior yaw 1.95° | 비교 성능 표본 아님 | 실제 PF 복귀 예측 후 OFF 9.2 / ON 13.1 SIM s에 첫 이동 명령. carry 발행 PWM과 현재 σ 상한 확인 |
| 도착 회복 대조, 합성 full posterior yaw 1.25° | 비교 성능 표본 아님 | 양 조건 모두 복귀 뒤 도착 상한 재검사 및 `arrived` |
| P1-2, dev s151 원본 초기 입력 | 1.8 s의 xy≈(−0.868, 0.592), σxy≈0.168 m에서 `LOOK_COLLISION_UNVERIFIED` | 위험 동작 없이 정지·재촬영. 이후 관측 없음/요청 예산 소진은 `NOT_INITIALIZED`, 합성 수렴 프레임 대조는 탐색 단계로 진행 |
| 동일 σ 3.1° / 최근 fix / 이동량 0 | 옛 OFF만 mecanum 발행 | ON/OFF 모두 이동 차단 |
| 동일 정적 벽/자세의 unsafe sweep | 옛 OFF만 허용 | ON/OFF 모두 충돌 미검증 종료 |

이동 명령은 실제 이동/운반 성공이 아니다. 표의 SIM초는 오프라인 상태기계 시간이며 실제 성능 비교가 아니다. s151은 첫 RGB 3장과 초기 명령만 재생했고, 그 뒤 수렴 프레임 대조는 합성 입력이다. 미래 미개봉 test/성과에 포함하지 않는다.

| 실행 | 결과 | 로그 |
|---|---|---|
| runtime 수정 전 핵심 7개 | 7 failed | `before.txt` |
| 최종 테스트의 핵심 8개 + 원본 2fadd08a runtime/runner 메모리 내 로딩 | 8 failed, 15 deselected (당시 테스트 23개) | `before-confirmed.txt` |
| 최초 수정 후 핵심 7개 | 7 passed | `after-initial.txt` |
| 새 5차 회귀 전체 | **30 passed** | `after.txt` |
| 관련 14개 테스트 파일 | **366 passed, 382 subtests passed, 1 failed** | `related-tests.txt` |
| 외부 CI cap 2, 내부 `mock.patch.dict` cap 1 | **6 passed** | `ci-caps.txt` |

관련 묶음의 실패 1개는 변경하지 않은 `test_simulation_workflow_manager.py::WorkflowManagerTests::test_parent_exit_cleans_background_child`에서 `ps` 실행이 샌드박스에 거부된 것이다(`PermissionError: [Errno 1] Operation not permitted: 'ps'`). 테스트를 skip/수정하지 않았다. 샌드박스 밖 확인은 남는다. 관련 묶음 실행 당시 새 회귀 27개였고, 이후 추가한 시간 상한·반복 초기 거부·prereg 수치 일치 3개는 최종 30개 실행에서 통과했다. 초기 관련 검사에서 이전 조건을 고정한 assertion과 초기화가 아닌 슬롯 fixture까지 초기 deadline을 적용한 문제가 드러나 수정했으며 `related-initial.txt`에 보존했다.

## 재현과 저장 입력

기존 환경 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 재사용했다. pytest마다 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`과 `--basetemp=./.pytest_tmp`를 사용했다. 기존 wrapper의 OpenCV `setNumThreads(0)`으로 GCD 병렬 영역을 끄고 실제 thread 수 1을 확인했다. runner 테스트의 thread cap은 `mock.patch.dict`로 고정한다. 마지막에 `.pytest_tmp`를 삭제했다.

- 새 회귀: `review-fixes/run_review_tests.py -q -s --basetemp=./.pytest_tmp tests/test_owncam_memory_v3_review5.py`.
- 수정 전: `review5-fixes/reproduce_baseline.py`. `git show 2fadd08a:<path>`로 세 모듈을 메모리에만 로딩한다. exit 1과 8 failed가 기대값이다. 소스/checkout/index는 바꾸지 않는다. 테스트 추가 후 deselected 수는 달라질 수 있다.
- thread 격리: `review5-fixes/check_ci_caps.py`는 수치 라이브러리를 cap 1로 초기화한 뒤 환경만 cap 2로 mock한다. 각 runner 테스트가 cap 1로 patch하며 종료 후 환경 복원도 확인한다.
- 관련 묶음: 위 wrapper에 `test_owncam_memory_v3{,_review,_review2,_review3,_review4,_review5}.py`, `test_owncam_memory.py`, `test_m1_owncam.py`, `test_owncam_localizer.py`, `test_visual_attachment.py`, `test_wrist_zone_skill_v9.py`, `test_map_goto.py`, `test_visual_box_skill.py`, `test_simulation_workflow_manager.py`를 전달했다.
- s151 fixture: `tests/fixtures/owncam_memory_v3_init/{manifest.json,stationary.jpg}`. 원본 `dev-a1/off/m1mem-dev-s151`의 manifest/commands/frames 파일을 기존 `raw_index.json` SHA-256으로 확인했다. 세 프레임의 JPEG 바이트는 모두 동일하여 한 장만 보존하고 각 원래 시각/ID/발행 PWM을 기록했다. 각 JPEG 해시는 저장 frame manifest와 대조했다. 과거 PF 보고서/평가 좌표는 입력에 넣지 않았다. 원본은 삭제하지 않았다.

## 검증 한계

`git fetch origin`은 공용 Git `FETCH_HEAD` 쓰기 제한, `gh pr list`는 GitHub 연결 실패로 최신 원격 확인이 불가능했다. 기준은 제공된 로컬 HEAD이며 원격 CI는 실행하지 않았다. 시작 시 공용 물리 잠금은 비점유였다. 공용 잠금 경로는 이 샌드박스의 쓰기 범위 밖이므로 잠금을 획득하지 못한 상태에서 사용자 지정의 단일 thread 오프라인 pytest만 실행했다. 물리·학습·속도 측정·서버는 시작하지 않았다.

실제 초기화 추가 촬영의 수렴률, 보수적 fix/정체 문턱의 거부율, 새로운 matched dev 주행·운반 성공은 아직 검증하지 않았다. 새 실험/학습/평가 결과가 없으므로 TensorBoard snapshot이나 영상은 생성하지 않았다. UGRP 예외에 따라 Google Drive 작업은 없다. 소스·fixture·검증 로그의 해시는 `verification.json`에 기록한다.
