# PR #405 main 병합 정리 (2026-10-12)

물리·렌더·모델 호출 0회. `claude/ego-wall-map`에 `origin/main`(ac45025b)을 병합하면서 생긴 정리만 기록한다.

- 텍스트 충돌 2건: `experiments/README.md`(색인 양쪽 유지), `scripts/run_ci_tests.py`(시험 목록 합집합). 중복 4개는 main에 이미 있던 것.
- `sim/v7_exact_speedups.py`: main 활성 번들 `zone-s3-recovery-v195`의 source seal(`b60cf83f…`)을 지키려고 main 바이트 그대로 둔다. #405가 넣었던 `CachedParameters.__reduce__`(egomap60 checkpoint 복원)는 PR 소유 `scripts/dev_pair_checkpoint.CheckpointPickler.reducer_override`로 옮겼다(같은 동작: 빈 캐시로 재구성).
- egomap64/65 checkpoint 재개 계획 2개(`own-route-full-budget`, `own-route-heading-stability`)는 frozen module 14개가 바뀌어 **퇴역**한다. 원본 바이트는 제자리와 `retired-plan/`에 보존, 기록은 [retired-plans.json](retired-plans.json). 새 해시로 재등록하지 않는다: 그러면 6f1fa925에서 만든 pickle이 다른 코드로 재개될 수 있다. Oracle x86은 2026-10-11 정지. 실행 시 `admit_checkpoint`가 `FROZEN_MODULE_CHANGED`로 거부한다.
- `freeze.json`(goal-route continuous/motion-audit/preflight)은 실행 시에만 읽히며 바뀐 소스로는 실행을 거부한다. 과거 기록으로 둔다.

## CI 정리 (run 38189056056 실패 분석)

이번 병합 전 마지막 완료 CI(af2eaa43, run 38063060822)부터 이미 실패하던 PR 시험을 고쳤다. 병합 때문에 새로 생긴 실패는 shard 시간표 커버리지(551/634)뿐이었다.
- `configs/simulation_workflows.json`은 main 바이트(`fc5bdf91…`, criterion_b_v91·final_pair_loaded 고정)로 되돌리고, PR의 `own-map-goal-dev`·`goal-route-continuous-dev`는 `configs/simulation_workflows.d/` 조각으로 옮겼다. workflow manager 시험에 PR workflow 14개의 계획 표본을 추가했다(계획만, 실행 없음).
- 동결 사본 시험(`wall_contact_types`, `servo_camera_fk`): 동결 코드에 현행과 같은 `wall_column_calibration.adapter`를 주입한다. 출력 바이트 동일 비교는 그대로다.
- 동결 기록 대조(`wall_texture` freeze, coela 과거 번들): 현재 파일이 다르면 그 해시가 git 이력(freeze를 쓴 커밋 또는 해당 경로 이력)에 있어야 통과한다. 실행기 자체의 해시 거부는 그대로다.
- Linux/macOS 마지막 자리 부동소수 차이(`wall_texture` layout, `arena_wall_map` plan): 구조·정수·문자열은 정확히, 실수는 상대 1e-12로 비교한다.
- MuJoCo 없는 CI shard: `goal_route_continuous` 2개는 `importorskip`, `self_map_causal`은 MuJoCo가 없으면 native 차단 패치만 건너뛴다.
- `controller_exact_speedups`: main의 선택적 가속은 PR 모듈(self_map_rbpf 등)이 있으면 5개를 더 적용한다. 기본 5개 순서는 정확히 확인하고, 추가분은 허용 목록 안에서만 허용한다.
- 초음파: `sim/goal_route_continuous.py`·`scripts/run_own_route_particle_stages.py`를 등록 소비자로 명시했다(#221, 번들 `ultrasonic_front=on_v1`에서만 리그 생성, 기본 off). 게이트 문자열이 사라지면 시험이 실패한다. 그 밖의 새 판독 코드는 여전히 실패한다.
- shard 시간표: run 38189056056의 8개 JUnit으로 새 파일 83개 측정값을 추가했다(기존 값은 유지하고 겹치면 큰 값). 커버리지 634/634, 예상 shard 28.4분.
- 2차/3차 CI(run 38193573824, 38196268555) 정리: pytest가 shard의 모든 시험 모듈을 수집 시점에 import하므로 다른 실험의 같은 이름 모듈(`common`/`replay`)과 sys.path가 먼저 들어온다. `tests/isolated_code_dir.py`는 적재 동안 experiments/ 아래 모듈·경로를 모두 치웠다가 그대로 복원한다. shard 5 전체 수집 재현에서 수정 전 실패, 수정 후 통과. `copied-sources.json`도 freeze와 같은 기록 커밋 대조를 쓴다. `self_map_causal`은 센서가 `sim.masterpi_model_v3`(MuJoCo)를 쓰므로 `importorskip`.
