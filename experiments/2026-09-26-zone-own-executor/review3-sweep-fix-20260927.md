# PR #206 3차 수정 후 초기 look 회귀 — 2026-09-27

기준 HEAD `499e4fd6445614a8b647eaea11f7bb9c77e5e2bd` + 사용자가 넘긴 미커밋 3차 수정.
기존 작업을 보존하고 추가 수정했다. 커밋·push·새 물리 실험은 하지 않았다.
여기의 성공은 비물리 테스트 통과이며 실제 MuJoCo 스모크·배송 성공이 아니다.

## 원인과 근거

코디네이터 보고는 r2 1.4 / r3 2.7 SIM s의 `SWEEP_TRANSITION_BLOCKED`다.
그 시점 자기 추정·PWM 원본은 없으므로 두 실패의 정확한 제한 구체까지 확정하지 않는다.
다음은 동일 world 설정으로 확인한 재현 가능한 차단 메커니즘이다.

- `test_team_host_isolation_abort_and_horizon_on_the_real_world`와 같은
  `TaggedZoneScene.from_tagged(zone_wide_door_tags_v2, seed=703, ...)` 설정을 생성했다.
  물리 world는 만들지 않았다. 정적 지도는 테스트의 MAP과 완전히 같다.
- 설정의 spawn은 r1 `(-.85, .55)`, r2 `(-.85, -.85)`, r3 `(-.85, -2.25)`, yaw 0이다.
  초기 발행 PWM은 `{1:2000, 3:740, 4:2320, 5:1320, 6:1500}`이다.
  이 좌표는 진단 fixture에만 사용하며 실행기/실제 위치추정기에 넣지 않는다.
- 서쪽 벽 중심 x=-1.05, 반폭 .025, 높이 .10 m다. 명목 추정 σ=0 및 작은 σxy=.01,
  σyaw=.02에서는 같은 몸체 모델의 전체 look 경로가 통과한다.
- 같은 중심 추정에서 σxy=.05, σyaw=.02를 넣으면 모든 pan이 차단된다.
  회전축 구체 자체의 벽 간격은 130 mm지만 margin이
  `20 mm 기본 + 15 mm 교정 잔차 + 2×50 mm 위치 σ = 135 mm`여서 -5 mm다.
  pan을 바꿔도 이 구체는 움직이지 않는다. 시작 상완 구체까지 포함한 최소 clearance는
  원시 수평 간격 126.345 mm - margin 136.066 mm = **-9.722 mm**다.
  높이 검사에도 같은 uncertainty margin을 사용하므로 높은 팔 일부도 낮은 벽 검사에 남는다.
- `initialized=True`는 위치추정 수렴을 뜻하지 않는다. 기존 저장 smoke-v2/s700의 정지
  초기 own-report를 같은 guard에 넣어 본 보조 확인에서도 r1/r2는 최초 report부터 차단되고
  각각 7.1003 / 4.3002 SIM s에서 통과했다. 이는 다른 seed의 기존 report이며 s703 증거가 아니다.
  10 SIM초 대기는 이 관찰을 참고한 유한 복구 예산이지 수렴 보장이나 교정된 안전 상수가 아니다.
- review3는 도중 갱신된 추정으로 **남은 전체 전환**을 매 tick 재검사하고, 한 번 거절되면
  즉시 작업을 끝냈다. 시작 시 정한 pan queue도 추정 갱신 후 다시 고르지 않았다.
  안전 검사 자체의 거절을 즉시 영구 실패로 처리한 것이 비물리에서 확인한 회귀 원인이다.

margin은 한 번만 차감된다. guard의 장애물은 정적 벽/문기둥뿐이므로 바닥·자기 몸 오검출도
아니다. 명목 모델상 시작 팔 경로는 통과하지만, 불확실도를 포함한 안전성을 아직 확인하지
못한 상태다. 실제 시작 위치가 물리적으로 안전하다고 단정하거나 σ를 줄여 통과시키지 않았다.
차체 여유 및 후퇴 검사는 그대로이며 이 수정은 이동으로 빠져나가는 허가를 만들지 않는다.

## 222→0 교정과 대조

원본 `body_model_calibration.json`과 교정 상수는 변경하지 않았다.
222 contact step은 `(2.08,.18)`, 0.40 m 벽, unloaded, 문기둥 제외 조건의 전체 sweep이며
pan 1890–2030 구간이었다. 이번 spawn·0.10 m 벽·초기 위치추정 σ와 다르다.
교정에서 접촉한 pan들은 이번 추가 테스트에서도 모두 거절된다. 과거 0 contact를 현재
불확실한 시작 자세, 동시 전환, 운반 화물, 실제 문기둥의 안전 증거로 확장하지 않았다.

## 수정

- `harness/zone_own_sweep.py`: 불확실하거나 명목 경로는 통과하지만 inflated 경로가 막힌
  경우 **정지한 채 자기 RGB를 계속 받아 재검사**한다. 한 sweep당 누적 최대 10 SIM초이며
  잠깐 통과하거나 target이 바뀌어도 소진 예산을 초기화하지 않는다. 개선 없으면 기존
  `SWEEP_TRANSITION_BLOCKED`로 종료한다. 신뢰도 높은 명목 충돌은 즉시 거절한다.
- 직접 look/pre-deliver, M1 sweep, guarded driver에 적용했다. 재개는 동일한 전체 전환
  검사를 통과해야 한다. 팔 전환을 기다렸다면 최신 추정으로 원래 요청 pan 목록을 다시
  계획하여 전체 가능한 sweep을 복구한다.
- 도중 막힌 pan은 현재 PWM에서 전 경로가 통과하는 남은 pan으로만 바꾼다. 현재 pan을
  대신 쓸 때도 검사한다. 안전 대안이 없으면 정지·재검사/실패한다. 복원 검사도 유지한다.
- margin, 몸체 교정, wall 높이, 60 PWM 명령 및 ≤20 PWM 검사 간격, 후퇴 전체 경로,
  현재 σ interlock은 완화하지 않았다. 전환 검사에 시작 PWM도 명시적으로 포함했다.
- 실패 이벤트 `detail.guard`에 자기 추정 x/y/yaw·σ, 현재/목표 PWM, 제한 sample PWM,
  구체 번호·부위·중심·반경, 벽 ID, 원시 간격·margin·최종 clearance·overlap(mm),
  stage·누적 대기 시간을 넣는다. direct / goto / M1의 driver 실패도 외부 terminal event로
  전달한다. 해당 상세 딕셔너리는 진단 출력 전용이며 행동 판정에 다시 사용하지 않는다.
  `overlap_mm`는 **안전 여유를 포함한 기하 모델**의 값이며 측정 접촉/침투량이 아니다.

## 검증

- 수정 전 작업 트리 소스를 `/private/tmp/pr206-sweep-before/`에 보관하고 import hook으로
  같은 행동 테스트를 실행: **8 failed, 9 deselected**. 시작 작업 수명/재개/유한 정지/
  도중 σ 변화/세 호출부 pan 재선택의 행동 반례다. 누락 API만으로 실패한 수치가 아니다.
- 최종 관련 묶음: **179 passed, 1 deselected, 177 subtests passed**.
  기존 162개 안의 review3 신규 24개를 모두 유지했다. 새 비물리 17개를 추가했다.
- 같은 world 설정, 명목/불확실도 입력 구분, 3 SIM초 host abort/horizon, 수렴 뒤 전체 pan과
  원래 자세 복원, 이동 없는 대기, 10초 상한, 수렴 전/후 모든 발행 전환의 guard 통과,
  누적 예산 유지, 실제 위험 구간 거절, 상세 terminal event를 확인했다.
- 1.4/2.7초에 σ를 높인 테스트는 제어된 반례다. 실제 실패 당시 σ를 복원한 로그가 아니다.
- `git diff --check` 통과. 전체 저장소 CI, 새 seed 물리 스모크, 배송 성공은 검증하지 않았다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_own_executor_sweep_start.py tests/test_zone_own_executor_review3.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_guards.py \
  tests/test_zone_own_executor_boundaries.py tests/test_zone_own_executor_host.py \
  tests/test_m1_owncam.py tests/test_owncam_localizer.py \
  --basetemp=./.pytest_tmp -q \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world'
```

근거: `review3-sweep-before.txt`, `review3-sweep-after.txt`,
`review3-sweep-validation.json`(입력·수치·소스/지도/교정 SHA-256).
기존 review3, smoke, raw, calibration, TensorBoard 자료는 덮어쓰지 않았다.
이번 결과는 단위/기하 회귀검사이며 새 실험·학습·평가 episode가 없어 TensorBoard 변환 대상은 없다.

## 환경 제한과 남은 확인

- fetch는 공용 Git 쓰기 제한, PR 조회는 네트워크 제한, 잠금 획득은 공용 outputs 쓰기
  제한으로 실패했다. 원격 최신화·PR 코멘트는 하지 못했다.
- 묶음 실행 중 물리 제외 옵션을 한 번 빠뜨렸다. 해당 테스트는 renderer 생성의
  `invalid CoreGraphics connection`으로 실패했고 host run/제어 루프에 들어가지 못했다.
  오류 로그는 `review3-sweep-render-error.txt`에 보존했다. 이후 정확한 제외 조건으로
  비물리 결과를 확인했다. `.pytest_tmp` 및 일시 사용한 `.pytest_tmp_before`는 삭제했다.
- 코디네이터가 MuJoCo host 테스트를 다시 실행해야 한다. 재실패 시 `job_failed.detail.guard`의
  추정·PWM·limiting을 확인하면 모델상 실제 위험 경로와 uncertainty margin 차단을 구별할
  수 있다. 10초 대기 중 RGB가 수렴하지 않는 조건의 물리적 대안은 여전히 별도 검증 대상이다.
