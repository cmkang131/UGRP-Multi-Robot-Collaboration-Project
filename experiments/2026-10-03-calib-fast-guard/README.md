# v91 빠른 검사·동시 SIM 슬롯 — DRAFT

Refs #344. 기준 `origin/main=6f8460ad61ed858025a9e1d5d6ce77d7b92d9b1f`,
작업 브랜치 `codex/calib-fast-guard`. 번들 `zone-final-pair-v91`,
workflow `zone-final-pair-heldout-v91` **3.3.0**. 이 PR은 병합하지 않는다.

## 변경과 보존

두 held-out 지도 `zone_wide_corridor_final_v3`, `zone_wide_door_geometry_v3`의
unloaded 수집만 허용한다. seed 911, 370 SIM초 + reset≤5초, pose 0.05초,
RGB 0.2초, floor_light_v1, cargo_noslip_v1, weld OFF를 v90과 동일하게 유지한다.
HELD_OUT_VALIDATION / training_eligible=false / teacher_only=true는
plan·bundle·사례 결과·전체 결과에 유지한다. schedule.json의 실제 writer 바이트 SHA-256은
`8e9a126cfdcbc5961cacac4165b76ac65da3310aa40b758f0590d999917813db`다.
Fake 전체 수집에서 두 지도 모두 v90과 명령 순서·pose 7,401개·RGB 1,851회가 같다.

[번호 조회](reservation_scan.json)는 main과 열린 PR 4개의 ref/SHA 및 git grep 결과를 보존한다.
최댓값 v90 / 3.2.0 다음 번호를 사용한다. [최종 확장 조회](reservation_final.json)에서도
모든 bundle 식별자와 workflow 번호에 같은 결론을 확인했다. [보존 확인](preservation.json)의 기존 파일
18개는 바이트 동일하며 PHYSICS_HANDOFF.md의 기존 52,361바이트는 그대로 두고 새 절만 붙였다.
`.github/workflows`, v88/v90 등록, 동결 consumer criterion B와 validator를 수정하지 않았다.

v91은 전용 contract·runner·backend로 분리했다. 기존 v88/v90 물리/수집 메서드는 유지한다.
공용 `agent_lock.py`는 새 API가 추가되어 실제 소스 해시가 달라진다. 과거 기록의 해시는
변경하지 않으며 현재 production bundle에는 실제 새 해시를 기록한다. 역사 보존 검사는
이 한 파일을 명시적으로 구분하고 기본 잠금의 acquire/status/release 결과·오류·해제 기록을
과거 구현과 직접 비교한다. 나머지 v88 bundle/plan의 과거 writer 바이트도 확인한다.

## Guard 동등성

- excitation plan은 guard 초기화에서 한 번 계산하고 정적 벽의 배열을 캐시한다.
- 벽 offset·모든 sphere clearance·로봇 envelope를 NumPy 배열로 계산한다.
  chassis clearance의 hypot은 기존 math.hypot을 써서 반올림까지 유지한다.
- sphere gap·clearance_min·abort 이유·hold·eval_only abort 기록·이전 위치 배열은 정확히 비교한다.
- envelope norm에서만 BLAS dot과 NumPy 축 합산 순서의 차이로 최대 2 ulp를 허용하는
  property 검사를 둔다. [이 Mac의 실제 비교](property_equivalence.json)에서는 16,000개 모두
0 ulp 차이였다. 이 envelope 숫자는 실행 결과에 기록하지 않는다. 0.40 m 판정 경계의 8 ulp
  이내 값은 기존 scalar norm으로 재계산하므로 판정에는 tolerance를 적용하지 않는다.
- 한 advance_to 내부의 성공한 post-check 다음 pre-check만 생략할 수 있다. 같은 model/data,
  d.time, qpos/qvel 원시 바이트, geom/body 위치, ngeom, geom_rbound가 모두 같아야 한다.
  command/eval/capture/reset 경계를 넘는 캐시는 없다. post-check는 항상 실행한다.
  0.30+0.05 m, 기존 1e-10 수치 여유, 0.01 m substep 변위 판정과 갱신 순서를 보존한다.

고정 seed property 검사는 지도 3개×1,000 상태, envelope 16,000개,
0.35 m 인접 부동소수점 101개, 0.40 m envelope 한계 505개, 변위 한계 인접 1,000개,
NaN/Inf/누락/잘못된 반경, cache 무효화와 substep 중단을 비교한다.

`tests/test_final_pair_fast_replay.py`는 완료된 v88 unloaded와 r6 fine 원본의
각각 7,401개 full qpos/qvel을 render=False 모델에 넣고 mj_kinematics 후
각 행을 독립 검사해 wall/envelope/clearance_min/abort/hold 출력을 비교하고,
별도 관찰자 두 개로 순차 변위 상태도 비교한다. 로컬 두 파일 모두 통과했으며, CI에 raw나 MuJoCo가
없으면 명시적으로 skip한다. 50 ms 기록 재생이며 중간 0.25 ms 물리 궤적을 복원한 것이 아니다.
행별 출력은 **14,802/14,802 정확히 일치**, 행별 abort 0건이다. 순차 비교도 전부
일치하지만 50 ms 간격을 substep으로 취급하면 각 파일 7,286행에서 변위 중단이 누적된다.
이는 downsample된 기록의 합성 검사이며 실제 수집 실패가 아니다.
[첫 순차 전용 비교](replay_benchmark_initial.json)도 보존한다.
원본은 읽기만 했고 r8 raw·프로세스는 수정하거나 중지하지 않았다.

## 동시 실행

기존 agent_lock CLI에 `--sim-slot sim-<이름>`과 `status --sim-slots`를 추가했다.
서로 다른 owner/branch의 슬롯은 공존한다. `timing_sensitive=true` physics 잠금과는
양쪽 획득 순서 모두 차단하며 flock으로 획득 경쟁을 직렬화한다. 기본 physics 잠금과
기존 실행기의 owner/branch 요구는 그대로다. 불완전/죽은 점유자는 자동 정리하지 않는다.

실행기는 동일 owner/branch의 살아 있는 슬롯과 배타 잠금 부재를 시작 직전에 검사한다.
plan에 host_start, 사례/전체 result에 host_start/host_end를 기록한다. 각 snapshot에는
loadavg, concurrent_holders, physics_holder가 있다. 중단 시에도 부분 raw와 해시를 보존한다.
두 지도 실행 명령·새 출력 루트·SHA 요구는 [PHYSICS_HANDOFF](../../PHYSICS_HANDOFF.md)의
맨 끝 v91 절에 있다. 새 수집·렌더링은 이 작업에서 실행하지 않는다.

## 검증 기록

로컬 JUnit 원본은 `/Users/changmin/projects/ugrp/outputs/calib-fast-guard-validation/local-junit/`에
보존한다. `scripts/refresh_ci_durations.py`로 새 4개 파일의 로컬 시간을 추출하고 기존
CI 측정값은 그대로 유지했다. 시간 자료 coverage는 **413/416 = 99.28%**다.
새 replay 파일 추정은 강화한 최종 JUnit의 **67.40초**다.
[검증 기록](verification.json)에 명령별 JUnit 해시와 중복 제거한 **507 passed**를 기록했다.
최종 변경 범위 88개, 재생 강화 2개, CI 관련 92개를 모두 재확인했다.
전체 목록은 8 shard에서 빠짐·중복 없이 배정한다. frozen fixture 3개·v63 static bundle·
기존 registry 보존·media-size 검사를 통과했다. 기존 unrelated process-cleanup 검사 1개는
이번 관련 회귀에서 제외하며 CI 등록은 유지한다.

초기 실패도 보존한다. 공용 lock 소스 변경으로 역사적 바이트 기대 검사가 실패했고,
위의 명시적 successor 비교로 고쳤다. 새 인계 파서 테스트는 ugrp_session wrapper의
토큰 위치를 잘못 가정해 1회 실패했으며 scripts.sim_cli 토큰을 찾아 파싱하도록 고쳤다.
이는 테스트 기대 수정이며 guard 수치 동등성 실패는 없었다.

## 최종 CPU 측정

실행 소스 **`1cbb1ad4f0a38c1b08f0c559419f5339612eb8ed`**에서
[최종 전체 raw 재생·CPU 보고서](replay_benchmark.json)를 생성했다. Guard 구현은
첫 구현 커밋 `fb3f23b5077d8be29d1c87832c9a0d1ba3595c32` 이후 바이트 동일하다.
이후 커밋은 실험 기록·인계 문서만 추가하며, 실행할 때는 PR 최종 인계의 실제 전체 HEAD를
`V91_SOURCE_SHA`와 `--expected-source-sha`로 사용한다.

| raw | 비교 행 / 불일치 | 기존 guard 중앙 CPU/호출 | 새 guard 중앙 CPU/호출 | 배수 |
|---|---:|---:|---:|---:|
| unloaded | 7,401 / 0 | 2.086717 ms | 0.082813 ms | 25.1978 |
| fine r6 | 7,401 / 0 | 2.203333 ms | 0.088390 ms | 24.9274 |

Python 3.12.13, NumPy 2.5.2, MuJoCo 3.12.0, macOS arm64다. 교대로 old/new 각
300회×7번을 process_time_ns로 측정하고 중앙값을 사용했다. 환경·시작/종료 loadavg·
7회 원값·raw/bundle/result SHA-256·clearance_min 시계열 해시는 JSON에 있다.
r8의 실행이나 잠금을 바꾸지 않았다. 이 값은 오프라인 guard CPU 비용이며 배타 wall-time,
캐시를 포함한 전체 substep 시간, 두 지도 실제 collection 처리율은 측정하지 않았다.
새로운 로컬 결과 위치는 `/Users/changmin/projects/ugrp/outputs/calib-fast-guard-validation/`이며
원본 raw와 전체 JUnit/log는 로컬 보관이다. GitHub에는 소스와 이 요약/해시만 올린다.

## 남은 검증 범위

새 held-out 코호트 수집·동시 실제 collection throughput·criterion B 수용·학생/실물 성공은
검증하지 않았다. 기존 raw 재생과 코드/CPU 회귀라서 새 TensorBoard 코호트나 서버를 만들지
않았다. 실제 새 결과 회수 뒤에 기존 지침대로 새 snapshot을 만들고 표시를 검증해야 한다.
Drive를 사용하지 않았다. `/private/tmp` extraction 디렉터리를 만들지 않았으며 다른 작업의
임시 디렉터리·프로세스·raw는 정리하지 않았다.

## 참고 자료

- [v88 보정 어댑터 #344](https://github.com/kcm0127-dotcom/ugrp/pull/344)
- [v90 held-out 수집](../2026-10-01-calib-heldout-maps/README.md)
- [v91 번호 조회](reservation_scan.json), [최종 조회](reservation_final.json), [보존 해시](preservation.json)
- [최종 재생·CPU 수치](replay_benchmark.json), [property 비교](property_equivalence.json), [JUnit 검증](verification.json)
- [동결 consumer criterion B](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)
- [v91 실행 인계](../../PHYSICS_HANDOFF.md), [기존 TensorBoard 절차](../../docs/tensorboard.md)
