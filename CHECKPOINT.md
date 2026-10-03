# CHECKPOINT (v6f set-down, 2026-09-29 10:50 KST) -- do NOT commit this file

Stopped on the coordinator's order (user away, battery/wifi). Nothing physical was run. Nothing committed, pushed or opened as PR.

## State
- Worktree: /Users/changmin/projects/ugrp-wt/claude-v6e-place, branch claude/pair-v6e-place, base origin/main 1e7bdfe0 (includes #266, #264). #265 (b-v6d) still open.
- All changes are UNCOMMITTED (git status: 8 modified files + tests/test_zone_pair_v6f.py new). Delete or move this CHECKPOINT.md before any `--execute` run (clean-tree check) and never `git add` it.
- No physics run was started: agent lock was free (`python3 scripts/agent_lock.py status` -> null), no run_pair_stage_probes/pytest process of mine is alive.
- Baseline raws for comparison: /Users/changmin/projects/ugrp/outputs/pair-stage-probes-b604499d-sdEnd (0/13 staged, 19 planned) and ...-sdPickup (3/3).

## Code done (uncommitted)
- harness/zone_pair_v6_policy.py: PairPolicy.own_image_ob, PairPolicy.bounded_retreat (default False); probe policies b-v6f-a (image only), b-v6f-b (retreat only), b-v6f (both) = b-v6c + flags. REVISION_POLICIES / EXECUTION_BUNDLE_ID unchanged (registration is NOT mine; see below).
- harness/zone_pair_vision.py: valid_frame untouched; valid_frame_ob (dark level = optical-black median + 2 LSB, capped at legacy 7), frame_gate(policy).
- harness/zone_pair_executor.py (2 sites), zone_pair_guards.py (preclose_check, observe_standoff, _bounded_retreat + hold branch in check), zone_pair_grasp.py (_frame_gate + 2 sites): use frame_gate / bounded retreat.
- harness/pair_stage_probe.py (PROBE_VERSION 0.4.6, POLICIES), scripts/run_pair_stage_probes.py (--omp-threads, image_valid_off also forces valid_frame_ob), scripts/build_pair_stage_probe_views.py (POLICY_SHORT).
- tests/test_zone_pair_v6f.py: 10 tests, all pass.

## Tests
- Full suite (`pytest tests -q -p no:cacheprovider`) was stopped at 87 % (log: /private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/full_tests.txt). It showed 11 F in the first 44 % (progress dots only; names are printed at the end and were lost). Expected causes: tests pinned to the v6c registration (source hashes, policy_flags): tests/test_zone_pair_registered_source.py::test_v6c_records_current_scene_and_full_source_closure, tests/test_zone_pair_v6.py (~340/418), tests/test_zone_pair_v6c.py (~92), tests/test_owncam_bootstrap_v6b.py (~489-505, expects exact vars(PairPolicy) dict: needs own_image_ob/bounded_retreat added, and the v6e carry worktree edits the same dict). Not verified which of the 11 are these.
- Next: rerun with `-rf` (or `--tb=line`) to get names, only the suspected files first: tests/test_zone_pair_registered_source.py tests/test_zone_pair_v6.py tests/test_zone_pair_v6c.py tests/test_owncam_bootstrap_v6b.py tests/test_pair_stage_probe.py, then the full suite in the background.

## Coordinator instructions received during this task (10:43)
1. Do NOT register (no RUNNABLE_ID, catalog, prereg seal, simulation_workflows.json, llm_driver.json). The v6e carry agent (branch claude/pair-v6e-carry, worktree /Users/changmin/projects/ugrp-wt/claude-v6e-carry) registers v81 / 2.14.0 / v6e once, including my changes.
2. Max 2 physical workers; push only in the final state (each push = ~20 min CI).
3. Re-measure only failing + representative cells while fixing; the full 13 cells and held-out ONCE at the final candidate. Then draft PR, stop at green CI, no merge.
4. Fetch the v6e branch periodically and tell them about overlaps.

## Known conflict with the v6e carry worktree (uncommitted edits there, read-only look at 10:44)
Both touch: harness/zone_pair_v6_policy.py (fields + POLICIES), harness/zone_pair_executor.py (different sites; mine are in the step/observe wiring, theirs in m2_controller and PairTeam.__init__), harness/pair_stage_probe.py (PROBE_VERSION 0.4.6 vs 0.6.0; POLICIES tuple), scripts/run_pair_stage_probes.py (--omp-threads is textually identical on purpose; manifest line differs: theirs adds 'pf_track'), scripts/build_pair_stage_probe_views.py (POLICY_SHORT), tests/test_owncam_bootstrap_v6b.py (exact dict of policy fields). Not yet told to them (SendMessage not sent). Merge order suggestion: v6e takes PROBE_VERSION 0.6.0 (max), union of POLICY tuples, union of dataclass fields.

## Open problem: CI green vs "no registration"
Any source edit in zone_pair_{executor,guards,grasp,vision,v6_policy}.py breaks the v6c pins (tests above), so this branch cannot be CI-green on its own without re-sealing the prereg (forbidden by instruction 1). Tell the coordinator: either (a) the PR stays red on exactly those pin tests until the carry agent's single registration, or (b) hand the change to the carry agent as a patch/branch to merge before their registration. Decide with the coordinator; do not touch registration files.

## Measurement plan (not started)
Runner: /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.run_pair_stage_probes ... --workers 2 --omp-threads 1 --execute --lock-owner claude --output /Users/changmin/projects/ugrp/outputs/pair-stage-probes-<sha8>-<tag>. Driver (takes lock by its own PID, logs load avg): scratchpad/driver.sh <batch> <minutes> <spec>, launched via `python3 scripts/ugrp_session.py run <name> -- bash <driver> ...`. Needs a WIP source commit first (clean tree). zsh: pass cell names literally (unquoted $CELLS is not split).
Destination cells (13): nominal(s911,912,913) along-/same lat+/same lat+/opp lat-/same lat-/opp yaw+/same yaw+/opp yaw-/same yaw-/opp corner--/same; args: `--stage setdown --sources teacher --policies b-v6f --prior-std e2e --legs end --cells <cells>`.
Old pickup (3): `--stage setdown --sources teacher --policies <p> --prior-std e2e --cells nominal` (no --legs).
1) Representative first: b-v6f on nominal (s911), lat+/same, yaw-/opp, corner--/same (4 cells, ~10 min).
2) If OK and no further code changes: final candidate = full 13 for b-v6f, ablations b-v6f-a / b-v6f-b (13 each), old pickup for b-v6f/-a/-b/b-v6c, b-v6c control (OMP=1) on 13, held-out = same 13 cells with new PF seeds (--seeds 921 --nominal-seeds 921 922 923) for b-v6f and b-v6c. Held-out changes only PF seeds (boundary source exists only for grasp_lift), so it is not independent geometry: say so.
3) Then README experiments/2026-09-29-pair-v6f-place/README.md (Korean; style of experiments/2026-09-29-pair-v6c-carry/README.md), TensorBoard snapshot per docs/tensorboard.md (own key only), fetch + merge origin/main, draft PR with "참고 자료" and Refs #221, stop at CI result, no merge.

## Sources actually opened (cite only these)
e-con Systems "Black Level Correction in Image Sensors" (e-consystems.com blog); arXiv 2607.14760; arXiv 1608.02385 (Hagui et al.); Zhang/Forster/Scaramuzza ICRA 2017 Active Exposure Control + github.com/uzh-rpg/active_camera_exposure_control; MoveIt Task Constructor core/src/stages/move_relative.cpp/.h and the Pick and Place MTC tutorial.

## Corpus check (for README)
3000 random frames of 275,205: legacy valid_frame fails 49 (all r1), valid_frame_ob fails 0; any dark level k=0..6 gives identical corpus behaviour, only k=7 (legacy) fails. Data: scratchpad/ob/margin.json, scan.json, margin.py. Limit: a near-black cover with V 3..7 above the OB level is treated as low light.

## Notes for the final report
- Worktree was created with --allow-over-cap --reason (claude agent had 30 registered worktrees, cap 8): mention it.
- Retreat geometry: clearance 0.174 m at sigma 0 vs 0.163 m needed; any std_xy >= 0.012 leaves too little room.

## UPDATE 2026-09-29 (code-only phase finished)
- Committed locally: 5c80765a on claude/pair-v6e-place (no push/PR/registration). Only harness/scripts/tests files; CHECKPOINT.md stays untracked, delete before retire.
- Targeted run (39 test files touching the changed modules, no physics, OMP=1): 1261 passed, 10 failed.
  - 5 = tests/test_zone_pair_registered_source.py (v6_contract hash pins, ValueError 'source contract/hash mismatch'): expected until final registration.
  - 4 = pre-existing on HEAD without my changes (verified in a detached clean worktree): test_zone_pair_v5c dev10_r1_1240.jpg tag ids; test_zone_study_pair_delay x3 (PAIR_REOBSERVE_TIMEOUT).
  - 1 = tests/test_owncam_bootstrap_v6b.py exact PairPolicy dict: FIXED (v6c_off dict now includes own_image_ob/bounded_retreat False); merge note: carry agent edits the same line.
- The earlier '11 unexplained failures' were these classes. Measurement plan above is unchanged and NOT started.
