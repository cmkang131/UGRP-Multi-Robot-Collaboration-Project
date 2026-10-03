# CHECKPOINT: flaky test_worker_guard_logs_actual_duration_separately_from_late_poll[2.0-1.0-False]

Worktree: /Users/changmin/projects/ugrp-wt/claude-flaky-guard (branch claude/fix-flaky-worker-guard, base origin/main 1e7bdfe0). No edits, no commit, no push/PR yet.
No load processes (yes/loops) were started or left running.

## Cause (code-read + arithmetic check; NOT yet reproduced by running the test)
- harness/rgb_skill_execution.py ~L949-953: `polled = time.monotonic()`; reject if `polled - r.started_wall > 2.`
  and `self._now_s - observed_at_s > 1.`. With tick(0.), sim age = 0 - (-1.0) = 1.0 exactly -> sim side is deterministic,
  no clock drift (the sim clock is not involved in that comparison).
- The test patches monotonic to `runner.started_wall + wall_age`. `started_wall` is the REAL time.monotonic()
  (uptime seconds). `(s + 2.0) - s` is NOT always exactly 2.0 in floating point: when s is within 2 s below a power of two
  (126..128, 254..256, 510..512, 1022..1024, ...), s+2.0 crosses a binade, rounds up by 1 ULP and the difference becomes
  2.000000000000014 etc. -> `> 2.` is True -> RGB_WORKER_REJECTED -> `assert True is False`.
  Verified numerically: for k=7..10 about half of the sub-ULP grid points in [2^k-2, 2^k) give diff > 2.0.
- Fits the CI symptom: fresh CI VM with small uptime, the test ran in one such 2-second window. Not load-dependent
  (machine load 12-20 was likely coincidence/only shifts timing).
- Product defect? No. The product compares two real monotonic readings; only the test builds an exact-boundary value by
  adding to a float. No product change, so the execution bundle hash is unaffected (still to be confirmed with the bundle check).

## Planned fix (test only)
In the test, before monkeypatching time, pin `runner.started_wall = float(math.floor(runner.started_wall))`
(integer-valued float; s + 2.0 is exact for any integer < 2^53, so polled - started == wall_age exactly for 2.0).
Keep params (2.0,1.0,False), (2.01,.05,True), (.01,1.01,True) and all assertions unchanged. Needs `import math` if missing.
(Timing snapshot fields like worker_queue_wall_s shift by <1 s; the test does not assert them.)

## Remaining
1. Deterministic repro: temporarily set runner.started_wall = 510.00000000000017 (or similar) in the test before patching -> expect failure on current code.
2. Apply fix, run full tests/test_rgb_execution_skills.py + related tests, and repeat the same start values (edge values 126/254/510/1022 + ULP) to show 0 failures.
   Optional load repro (yes x4-6, kill after) only when the user is back / allowed.
3. Check bundle hash tests (test files should not be in the bundle), then commit (only after pass line), push, draft PR
   (참고 자료: 없음(저장소 코드만 사용)), wait for CI green, report. Do not merge.
