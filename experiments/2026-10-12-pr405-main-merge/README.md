# PR #405 main 병합 정리 (2026-10-12)

물리·렌더·모델 호출 0회. `claude/ego-wall-map`에 `origin/main`(ac45025b)을 병합하면서 생긴 정리만 기록한다.

- 텍스트 충돌 2건: `experiments/README.md`(색인 양쪽 유지), `scripts/run_ci_tests.py`(시험 목록 합집합). 중복 4개는 main에 이미 있던 것.
- `sim/v7_exact_speedups.py`: main 활성 번들 `zone-s3-recovery-v195`의 source seal(`b60cf83f…`)을 지키려고 main 바이트 그대로 둔다. #405가 넣었던 `CachedParameters.__reduce__`(egomap60 checkpoint 복원)는 PR 소유 `scripts/dev_pair_checkpoint.CheckpointPickler.reducer_override`로 옮겼다(같은 동작: 빈 캐시로 재구성).
- egomap64/65 checkpoint 재개 계획 2개(`own-route-full-budget`, `own-route-heading-stability`)는 frozen module 14개가 바뀌어 **퇴역**한다. 원본 바이트는 제자리와 `retired-plan/`에 보존, 기록은 [retired-plans.json](retired-plans.json). 새 해시로 재등록하지 않는다: 그러면 6f1fa925에서 만든 pickle이 다른 코드로 재개될 수 있다. Oracle x86은 2026-10-11 정지. 실행 시 `admit_checkpoint`가 `FROZEN_MODULE_CHANGED`로 거부한다.
- `freeze.json`(goal-route continuous/motion-audit/preflight)은 실행 시에만 읽히며 바뀐 소스로는 실행을 거부한다. 과거 기록으로 둔다.
