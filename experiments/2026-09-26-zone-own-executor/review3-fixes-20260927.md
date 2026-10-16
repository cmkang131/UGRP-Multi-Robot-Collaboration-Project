# PR #206 재리뷰 3 수정 — 2026-09-27

기준 브랜치 `kiro/zone-own-executor`, HEAD `499e4fd6445614a8b647eaea11f7bb9c77e5e2bd`.
사용자 지정 재리뷰의 P1 4건·P2 3건을 수정했다. 커밋·push·물리 재실행은 하지 않았다.
아래는 Python 모의 제어·스케줄러·기하 모델의 회귀 결과이며 새 물리 성공 결과가 아니다.

## 변경

| 항목 | 수정과 파일 | 수정 전 반례 → 수정 후 |
|---|---|---|
| P1-1 | `harness/zone_own_guards.py`, `zone_own_driver.py`, `zone_own_executor.py`: 이벤트 hysteresis와 현재 σ interlock 분리. gate가 ok여도 HIGH 초과/비정상 σ이면 이동·후퇴·도착·최종 확인 차단 | 진입 dwell 중 전진/arrived/confirmed → hold·재관측/미확인 |
| P1-2 | 위 3개와 `harness/zone_own_deliver.py`: 거절된 전환은 `SWEEP_TRANSITION_BLOCKED`(driver는 소문자)로 종료. 현재 pan에서 팔 전환, 이후 pan. 실제 60 PWM/tick 보간 경로를 20 PWM 이하 간격으로 검사하며 복원도 같은 검사 적용 | M1/직접 sweep의 거절 무시 및 세 호출 경로의 위험 복원 → 명령 발행 없이 종료 |
| P1-3 | `zone_own_guards.py`, `zone_own_driver.py`: 현재 발행 PWM의 차체·팔·손가락·화물을 후퇴 전 구간에서 검사. gain 0–1.6, 최대 5 mm 샘플 간격과 간격 절반의 추가 여유로 샘플 사이도 덮음 | 차체 끝점은 통과하지만 화물이 벽과 겹치는 후퇴 및 경로 중간 충돌 → 거절 |
| P1-4 | `zone_own_guards.py`, `zone_own_driver.py`, `zone_own_deliver.py`, `zone_own_executor.py`: leg별 재관측 실패 3회 한도. monitor reset/복구로 초기화하지 않고 `progress_unconfirmed` 종료. 요약에 실패 횟수 보존 | 정상 초기 추정 뒤 stale tag·σxy=.065 고정 추정에서 LOCAL_TIMEOUT → GOTO_progress_unconfirmed, 150 SIM s 이전 |
| P2-1 | `harness/zone_own_team_host.py`: 초기 안정화·다음 wake·종료 안정화 모두 horizon으로 제한. 비정수 timestep 예산은 한도 이내 마지막 tick에서 종료 | 5초 wait macro가 1초 horizon을 초과 → 한도 이내 종료; 0/.2/1/1.03초 검사 |
| P2-2 | `experiments/2026-09-26-zone-own-executor/run_smoke_v2.py`: delivery leg의 `recoveries` 및 goto `stall_recovery` 사건으로 집계 | keep-out 없는 복구가 0 → 실제 3회(leg 2 + goto 1) |
| P2-3 | `zone_own_team_host.py`: carry phase의 배정 화물–벽 접촉을 평가 전용 `cargo_wall` 및 전체 `wall`에 포함 | 화물–벽만 접촉하면 빈 집합 → wall/cargo_wall; 다른 로봇·비운반 단계·손가락 유지 지표는 오염되지 않음 |

실시간 GT·접촉·측정 관절을 제어 입력에 추가하지 않았다. 접촉 변경은 호스트 평가 집계에만 있다.
위험 전환 차단이 실제 배송 완주율에 미치는 영향은 아직 물리 검증하지 않았다.
위치 미초기화 상태의 기존 정지 상태 bootstrap look 정책은 유지한다.

기존 스모크 result JSON, raw, calibration, TensorBoard snapshot은 변경하지 않았다.
과거 `stall_recoveries`와 화물 접촉 지표를 소급 교정했다고 주장하지 않는다.
재집계를 수행한다면 원본 로그에서 별도 새 파일로 만들어야 한다.

## 테스트

신규 파일: `tests/test_zone_own_executor_review3.py` (24개 사례).
`scripts/run_ci_tests.py`의 기존 `tests/test_zone_own_executor*.py` 패턴이 신규 파일을 포함한다.
`tests/test_zone_own_executor_boundaries.py`의 고정 파일 수 4 단정은 신규 파일의 포함 단정으로 바꿨다.

동일한 최종 신규 테스트 파일을 `git archive 499e4fd6`의 격리된 소스에서 실행:

- **23 failed, 1 passed (6.80 s)** — [원본 실패 로그](review3-before.txt).
- 7항목 모두 기존 API의 행동 반례가 포함된다. 이 숫자는 독립적인 버그 23건을 의미하지 않는다.
- 새 translation API 및 별도 실패 예산 검사도 포함한다. 통과 1건은 비운반 화물 접촉의 음성 대조다.

수정본과 기존 관련 파일 6개를 함께 실행:

- **162 passed, 1 deselected, 177 subtests passed (17.25 s)** — [수정 후 로그](review3-after.txt).
- 신규 24개 모두 통과. 기존 실행기·경계·guard·호스트 스케줄러·M1·위치추정 회귀 포함.
- 실제 MuJoCo world를 생성하는 `test_team_host_isolation_abort_and_horizon_on_the_real_world` 1개는 사용자 요청대로 제외했다.
- 전체 저장소 CI를 실행한 결과는 아니다. `git diff --check` 및 신규 파일의 CI 패턴 포함 검사 통과.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_own_executor_review3.py tests/test_zone_own_executor.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_zone_own_executor_host.py tests/test_m1_owncam.py tests/test_owncam_localizer.py \
  --basetemp=./.pytest_tmp -q -k 'not test_team_host_'
```

기존 guard 테스트의 `(2.08, .18)`은 시작부터 차체의 불확실도 포함 안전 여유를 침범했다.
이 위치의 후퇴 거절을 새 회귀로 남기고, 정상 후퇴 테스트 두 곳은 y=.14로 옮겼다.
충돌 pan 제한·후퇴·안전성 단정은 유지했다. 기존 교정 기록은 변경하지 않았다.

공용 Git FETCH_HEAD 및 테스트 잠금 경로는 sandbox 쓰기 제한으로 접근 실패했고,
GitHub PR 조회는 네트워크 제한으로 실패했다. 원격 최신 상태는 확인하지 못했다.
물리·학습·속도 측정 없이 사용자가 지정한 단일 스레드 모의 pytest만 직접 실행했다.
테스트 완료 후 작업 트리와 격리 원본의 `.pytest_tmp`를 삭제했다.

## 남은 물리 검증 (실행하지 않음)

1. 실제 own-camera 추정이 정상→HIGH로 바뀔 때 전진·후퇴의 정지, 정상 재관측 이후 재개 및 도착 확인 여부.
2. 0.40 m 벽·문기둥에서 search/carry/look 전환과 pan·복원. 명령 보간과 실제 동시 관절 동작의 차이 및 거절 뒤 안전 정지 확인.
3. 화물 유무·열린 손가락·현재 pan별 정체/look 후퇴 전 구간. 1.6 gain 범위와 실제 미끄러짐·정지 지연, 차체/팔/화물 접촉을 평가 전용으로 확인.
4. stale tag·재관측 불발이 반복되는 실제 정체에서 3회 실패 한도와 terminal event 1회·정지 확인.
5. 실제 MuJoCo host의 긴 wait/arm macro, timestep 경계에 맞지 않는 horizon, 초기·종료 안정화에서 한도 초과가 없는지 확인. 제외한 host 테스트 포함.
6. 로봇 geom 접촉 없이 화물만 벽에 닿는 실제 carry episode에서 `cargo_wall`/`wall` 집계 및 false-zero 방지 확인.
7. 최종 소스를 별도 고정·사전 등록한 뒤 새 seed로 3대 전체 smoke. 기존 result 파일과 분리하며 실제 복구 수·접촉·배송 확인을 대조. 완료 시 별도 TensorBoard snapshot/영상 등록 필요.
