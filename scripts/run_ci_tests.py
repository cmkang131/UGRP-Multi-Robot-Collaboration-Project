#!/usr/bin/env python3
"""Run the portable UGRP regression suite used by GitHub Actions."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from statistics import median
import time


ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

from scripts import agent_lock
from scripts.check_ci_fixtures import check_fixtures

TEST_PATTERNS = (
    "tests/test_ci_fast_path.py",
    "tests/test_owncam_memory_v3.py",
    "tests/test_owncam_memory_time.py",
    "tests/test_record_owncam_time.py",
    "tests/test_owncam_memory_v3_review.py",
    "tests/test_owncam_memory_v3_review2.py",
    "tests/test_owncam_memory_v3_review3.py",
    "tests/test_owncam_memory_v3_review4.py",
    "tests/test_owncam_memory_v3_review5.py",
    "tests/test_owncam_memory_v3_review6.py",
    "tests/test_model_artifacts.py",
    "tests/test_simulation_session.py",
    "tests/test_agent_lock.py",
    "tests/test_ci_host_lock.py",
    "tests/test_simulation_console.py",
    "tests/test_simulation_dispatch.py",
    "tests/test_dispatch_replay.py",
    "tests/test_dispatch_plan_guidance.py",
    "tests/test_dynamic_coordination.py",
    "tests/test_dispatch_regrasp_binding.py",
    "tests/test_dispatch_regrasp_coarse.py",
    "tests/test_simulation_extensions.py",
    "tests/test_simulation_scenes.py",
    "tests/test_simulation_workflow_manager.py",
    "tests/test_simulation_input_provenance.py",
    "tests/test_simulation_launch_options.py",
    "tests/test_simulation_start_menu.py",
    "tests/test_simulation_interrupt_cleanup.py",
    "tests/test_dispatch_scene_parity.py",
    "tests/test_cloud_preflight.py",
    "tests/test_carry_failure_measurement.py",
    "tests/test_repeated_skill_summary.py",
    "tests/test_colab_simulation.py",
    "tests/test_cpu_model_diagnostic.py",
    "tests/test_mac_skill_cohort.py",
    "tests/test_model_mailbox.py",
    "tests/test_kaggle_simulation.py",
    "tests/test_kaggle_cli_auth.py",
    "tests/test_kaggle_gpu_recovery.py",
    "tests/test_kaggle_egl.py",
    "tests/test_cloud_collection.py",
    "tests/test_colab_recovery.py",
    "tests/test_colab_relay_pipeline.py",
    "tests/test_colab_egl.py",
    "tests/test_multi_object_plan.py",
    "tests/test_multi_object_scene.py",
    "tests/test_multi_object_execution.py",
    "tests/test_zone_dispatch.py", "tests/test_zone_comm_boundary.py",
    "tests/test_zone_cargo.py", "tests/test_zone_team_jobs.py", "tests/test_zone_rgb_outcome.py",
    "tests/test_zone_cargo_perception.py",
    "tests/test_zone_dialogue_ko.py",
    "tests/test_pilot_korean_dialogue_records.py",
    "tests/test_zone_hard_routes.py",
    "tests/test_zone_team_a2.py",
    "tests/test_zone_teacher_fix.py",
    "tests/test_zone_cargo_perception_v2.py",
    "tests/test_zone_study_contract.py", "tests/test_zone_study_inputs.py",
    "tests/test_zone_identity_jobs.py",  # T13a: own-RGB identity/count and target-job seam (fake only)
    "tests/test_zone_study_scenarios.py", "tests/test_zone_study_protocol.py",
    "tests/test_zone_final_env.py",
    "tests/test_zone_environment_registry.py",
    "tests/test_zone_final_environment_runnable.py",
    "tests/test_zone_final_environment_floor_light.py",
    "tests/test_review_e2e_batch_k.py",  # K1: final environment CI collection regression
    "tests/test_scenario_capabilities_docs.py",
    "tests/test_zone_sim_cost.py", "tests/test_zone_event_scheduler.py",
    "tests/test_zone_study_eval.py", "tests/test_zone_study_offline.py",
    "tests/test_zone_study_review_fixes.py", "tests/test_zone_study_review_r5.py",
    "tests/test_zone_study_review_r6*.py", "tests/test_zone_study_review_r7*.py",
    "tests/test_zone_study_integration.py", "tests/test_zone_study_integration_seams.py",
    "tests/test_zone_study_integration_pair.py", "tests/test_zone_study_source_pinning.py",
    "tests/test_zone_mixed_jobs.py",  # P02: pure inventory and independent fake-port mixed jobs
    "tests/test_zone_e2e_manifest.py",  # P07: planning/admission only, runtime side effects forbidden
    "tests/test_zone_study_llm_driver.py",
    "tests/test_zone_study_pair_delay.py",
    "tests/test_zone_study_referee.py", "tests/test_zone_hidden_events.py",
    "tests/test_zone_study_evidence.py",
    "tests/test_zone_study_evidence_join.py",
    "tests/test_zone_study_evidence_review_a303.py",
    "tests/test_zone_study_evidence_review_f303.py",
    "tests/test_review_303c.py",
    "tests/test_review_303d.py",
    "tests/test_review_303e.py",
    "tests/test_zone_referee_ownership.py",
    "tests/test_zone_referee_replay.py",
    "tests/test_zone_study_evidence_review_c303.py",
    "tests/test_zone_study_multiturn.py",
    "tests/test_zone_study_review_r8*.py", "tests/test_zone_study_review_r9*.py",
    "tests/test_zone_study_review_r10*.py",
    "tests/test_zone_study_fenced_reply.py", "tests/test_zone_pilot_source_migration.py",
    "tests/test_zone_pilot_proxy_log.py",
    "tests/test_zone_pilot_settlement.py",
    "tests/test_zone_own_perception.py", "tests/test_zone_own_perception_v2.py",
    "tests/test_zone_own_perception_v3.py", "tests/test_zone_own_perception_v3_1.py",
    "tests/test_zone_own_executor*.py",
    "tests/test_review_325b.py",  # T03: mandatory independent loss/mode counterexamples
    "tests/test_review_e2e_batch_i.py",  # T04/T09b: issued arm sweep and delayed own capture counterexamples
    "tests/test_zone_pair_executor.py", "tests/test_zone_pair_status.py", "tests/test_zone_pair_review.py",
    "tests/test_zone_pair_role_exchange.py",  # T07: six explicit role assignments; fake ports only
    "tests/test_stall_observation_contract.py",  # P08: synthetic observation/stop contract only
    "tests/test_zone_pair_review2.py",
    "tests/test_zone_pair_rendezvous.py",
    "tests/test_zone_pair_rendezvous_t07.py",
    "tests/test_zone_pair_review3.py",
    "tests/test_zone_pair_review4.py",
    "tests/test_zone_pair_review5.py",
    "tests/test_zone_pair_review6.py",
    "tests/test_zone_pair_review7.py",
    "tests/test_zone_pair_dev.py",
    "tests/test_zone_pair_grasp.py", "tests/test_zone_pair_preclose.py", "tests/test_zone_pair_standoff.py",
    "tests/test_zone_pair_v5.py", "tests/test_pose_provider_contract.py", "tests/test_pose_provider_boundary.py",
    "tests/test_zone_start_dock.py",
    "tests/test_zone_pair_admission.py",
    "tests/test_pair_chain_probe.py",
    "tests/test_zone_pair_chain_contract.py",  # P04 fake-port transitions; no physics/models
    "tests/test_pair_passage_plan.py",  # 2026-09-29: opt-in corridor/door route planning for the pair carry (static geometry)
    "tests/test_beam_initial_pose_plan.py",  # T08a: static north/south setup sheet and role geometry, no execution
    # 2026-09-29: v6 is audited as history; these guard its receipt and the current v6-family path.
    "tests/test_zone_pair_v6.py", "tests/test_zone_pair_registered_source.py",
    "tests/test_execution_dependency_contract.py", "tests/test_seal_v2_review_301.py",
    "tests/test_seal_v2_fail_closed.py", "tests/test_seal_runtime_provenance.py",
    "tests/test_seal_v2_review_301b.py", "tests/test_seal_v2_review_301c.py",
    "tests/test_seal_v2_review_301d.py", "tests/test_seal_runtime_outputs.py",
    "tests/test_owncam_bootstrap_v6b.py",
    "tests/test_zone_pair_v6c.py",  # v6c (bundle v76): exact PF fix clock + grasp-range entry
    "tests/test_zone_pair_v6d.py",  # v6d (bundle v80): wide-hue beam heading + M1 fine align motion
    "tests/test_zone_pair_v6e.py",  # v6e carry flags (dead-reckoning model, lateral lag); flags off = v6c
    "tests/test_zone_pair_v6f.py",  # v6f place flags (optical-black dark reference, bounded retreat); flags off = v6c
    "tests/test_zone_pair_v6e_yaw.py",  # v6e yaw flags (pair-mean plant yaw, beam-edge relative yaw); flags off = v6e
    "tests/test_zone_pair_v6g.py",  # v6g carry_dr_general (lateral breakaway ramp, cross-axis drift) + route end inset; flags off = v6e
    "tests/test_zone_pair_door_relax.py",  # b-v6h stage-probe door-guard relaxation (process-local; registered sources untouched)
    "tests/test_door_relax_envelope.py",  # envelope grid + chain early stop of the stage-probe runner (opt-in flags)
    "tests/test_chain_analysis_hard_limit.py",  # chain_analysis leg_class: hard limit takes precedence over ordinary failure
    "tests/test_render_pair_probe_video.py",  # stage-probe report video renderer (reads saved cases only)
    "tests/test_render_profile.py",  # opt-in shadow/reflection render profiles (default path unchanged)
    "tests/test_carry_relocalization_b1.py",  # 2026-09-29: offline B1 relocalization measurement (pure arithmetic/thresholds)
    "tests/test_carry_lateral_error_model.py",  # offline endpoint extraction, grouped validation and paired prediction
    "tests/test_m2_pair_door_v3.py", "tests/test_pair_owncam_approach.py", "tests/test_zone_tagged_cargo_scene.py",
    "tests/test_owncam_localizer.py", "tests/test_zone_landmarks_sim.py",
    "tests/test_zone_eval_top.py",
    "tests/test_m1_owncam.py",
    "tests/test_rgb_execution*.py",
    "tests/test_rgb_communication*.py",
    "tests/test_act_map_suite.py",
    "tests/test_jev_execution_shadow.py",
    "tests/test_jev_motion.py",
    "tests/test_tensorboard_export.py",
    "tests/test_tensorboard_launcher.py",
    "tests/test_offline_audit_export.py",
    "tests/test_owncam_loop_views.py",
    "tests/test_colab_carry_bundle.py",
    "tests/test_carry_training_checkpoint_optional.py",
    "tests/test_act_route_teacher*.py",
    "tests/test_jev_skill_motion.py",
    "tests/test_act_speed_generalization.py",
    "tests/test_act_recovery.py", "tests/test_recovery_commands.py",
    "tests/test_reference_approach_data.py",
    "tests/test_camera_pair*.py",
    "tests/test_pair_carry*.py",
    "tests/test_task_stage_sync.py",
    "tests/test_task_stage_execution.py",
    "tests/test_research_camera_e2e.py",
    "tests/test_research_entry_stop.py",
    "tests/test_research_cohort_admission.py",
    "tests/test_saved_act_inputs.py",
    "tests/test_carry_termination_audit.py",
    "tests/test_matched_carry_cohort.py",
    "tests/test_matched_carry_shards.py",
    "tests/test_carry_failure_measurement.py",
    "tests/test_research_execution_recovery.py",
    "tests/test_research_visual_evidence.py",
    "tests/test_camera_goal_transport.py",
    "tests/test_three_robot_plan.py",
    "tests/test_three_robot_mission.py",
    "tests/test_three_robot_physical_controls.py",
    "tests/test_dispatch_research.py",
    "tests/test_dispatch_execution.py",
    "tests/test_dispatch_skill_binding.py",
    "tests/test_dispatch_box_identity.py",
    "tests/test_dispatch_beam_scan_cache.py",
    "tests/test_pair_coarse_pixel_cache.py",
    "tests/test_pair_coarse_concurrency.py",
    "tests/test_pair_navigation*.py",
    "tests/test_pair_transport*.py",
    "tests/test_pair_owncam_approach.py", "tests/test_zone_tagged_cargo_scene.py", "tests/test_m2_pair_door_v3.py",
    "tests/test_dispatch_adaptive.py",
    "tests/test_dispatch_pair_navigation.py",
    "tests/test_dispatch_evaluation.py",
    "tests/test_dispatch_feasibility.py",
    "tests/test_camera_action_learning.py",
    "tests/test_camera_local_servo.py",
    "tests/test_camera_visual_observer.py",
    "tests/test_camera_motion_identity.py",
    "tests/test_camera_landmark_tracker.py",
    "tests/test_camera_grasp_controller.py",
    "tests/test_camera_robot_port.py",
    "tests/test_camera_beam_features.py",
    "tests/test_camera_beam_shaft.py",
    "tests/test_camera_beam_fast_exact.py",
    "tests/test_dispatch_translation_skew_fallback.py",
    "tests/test_dispatch_pair_prefetch.py",
    "tests/test_communication_observer.py",
    "tests/test_dispatch_solo_cadence.py",
    "tests/test_fine_gain_schedule.py",
    "tests/test_dispatch_coarse_handoff.py",
    "tests/test_camera_varied_start_runner.py",
    "tests/test_dispatch_pair_pending_renewal.py",
    "tests/test_dispatch_solo_budget.py",
    "tests/test_rolling_view_recovery.py",
    "tests/test_settled_view_recovery.py",
    "tests/test_camera_gripper_motion.py",
    "tests/test_camera_pixel_grasp.py",
    "tests/test_camera_sweep_trial.py",
    "tests/test_camera_pixel_resume.py",
    "tests/test_camera_pixel_jacobian.py",
    "tests/test_camera_teacher_student.py",
    "tests/test_camera_recovery_student.py",
    "tests/test_audit_camera_grasp_student.py",
    "tests/test_camera_grasp_teacher.py",
    "tests/test_grasp_recovery_teacher.py",
    "tests/test_grasp_recovery_cohort.py",
    "tests/test_camera_approach_student.py",
    "tests/test_camera_approach_scene.py",
    "tests/test_audit_camera_approach_student.py",
    "tests/test_camera_varied_start*.py",
    "tests/test_camera_short_transport*.py",
    "tests/test_known_map*.py",
    "tests/test_rgb_traffic*.py",
    "tests/test_markerless*.py",
    "tests/test_vision_loc*.py",  # VIS4 motion, covariance calibration, split and geometry-budget regressions
    "tests/test_vision_pose_source.py",
    "tests/test_ultrasonic_range.py",
    "tests/test_ultrasonic_carry.py",
    "tests/test_ultrasonic_input.py",
    "tests/test_door_ultrasonic_sweep.py",
    "tests/test_visual_attachment*.py",
    "tests/test_placement_guidance.py",
    "tests/test_visual_placement*.py",
    "tests/test_gemini_transport_policy.py",
    "tests/test_transport_context.py",
    "tests/test_budget_repair_regressions.py",
    "tests/test_navigation_evidence.py",
    "tests/test_navigation_temporal.py",
    "tests/test_ugrp_session.py",
    "tests/test_sim_speed_tools.py",
    "tests/test_sim_speed_review2.py",
    "tests/test_sim_speed_review3.py",
    "tests/test_sim_speed_review4.py",
    "tests/test_sim_speed_review5.py",
    "tests/test_sim_speed_review6.py",
    "tests/test_sim_slots.py",
    "tests/test_agent_worktree.py", "tests/test_disk_report.py", "tests/test_check_media_size.py",
    "tests/test_frame_storage.py",
    "tests/test_tree_manifest.py",
    "tests/test_seed_validation_model.py",
    "tests/test_semantic_pick_policy.py",
    "tests/test_pick_match*.py",
    "tests/test_replay_pick_match.py",
    "tests/test_masterpi_model_v3.py",
    "tests/test_zone_masterpi_v3_scene.py",
    "tests/test_zone_model_conventions.py",
    "tests/test_visual_arm_v3.py",
    "tests/test_masterpi_v3_static_audit.py",
    "tests/test_masterpi_robot_models.py",
)


def local_lock_root(primary: Path | None = None) -> Path | None:
    """Share the experiment lock only with worktrees of the local primary repo.

    A GitHub runner or unrelated clone must not create a developer's Mac path.
    Do not use CI=true as an escape hatch: local offline tests also set it.
    """
    primary = primary or agent_lock.DEFAULT_ROOT.parent.parent
    if not (primary / ".git").is_dir():
        return None
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True,
    ).strip()
    if (ROOT / common).resolve() != (primary / ".git").resolve():
        return None
    return primary / "outputs" / "agent-locks"


def run_locked(command: list[str], env: dict, lock_root: Path) -> int:
    """Fail before spawn when busy; retain the lock until our group is gone."""
    from scripts import ugrp_session

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True,
    ).strip() or "detached"
    owner = branch.split("/", 1)[0] if branch.startswith(("codex/", "claude/")) else "local-tests"
    try:
        acquired = agent_lock.acquire(
            lock_root, owner=owner, branch=branch, purpose="local offline regression tests",
            pid=os.getpid(), expected_minutes=10, timing_sensitive=True,
        )
    except RuntimeError as error:
        print(f"Tests not started: {error}", file=sys.stderr)
        return 3

    child = None
    requested_signal = None
    previous = {}
    cleanup_verified = False

    def request_stop(signum, _frame):
        nonlocal requested_signal
        if requested_signal is None:
            requested_signal = signum

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, request_stop)
        child = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)
        deadline = None
        while True:
            if requested_signal is not None and deadline is None:
                try:
                    os.killpg(child.pid, requested_signal)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 5
            try:
                code = child.wait(timeout=0.1)
                return 128 + (-code) if code < 0 else code
            except subprocess.TimeoutExpired:
                if deadline is not None and time.monotonic() >= deadline:
                    ugrp_session.stop_group(child.pid, grace=1)
    finally:
        try:
            if child is not None:
                try:
                    ugrp_session.stop_group(child.pid, grace=1)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
                # wait() reaps the leader, not the process group. In particular,
                # macOS may still report an exiting group (including EPERM),
                # and stop_group's last SIGKILL is asynchronous. Confirm actual
                # disappearance with a bound; never unlock on an uncertain probe.
                deadline = time.monotonic() + 5
                while ugrp_session.process_group_alive(child.pid):
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.02)
                else:
                    cleanup_verified = True
            else:
                cleanup_verified = True
        finally:
            held = agent_lock.status(lock_root)
            ours = held and all(held.get(key) == acquired[key] for key in ("owner", "pid", "acquired_unix"))
            if cleanup_verified and ours:
                agent_lock.release(lock_root, owner=owner)
            elif ours:
                print("Test process cleanup unconfirmed; host lock retained for inspection", file=sys.stderr)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if not cleanup_verified:
                raise RuntimeError("Owned test group cleanup unconfirmed; inspect the retained lock")


def collect_test_files(root: Path, patterns: tuple[str, ...]) -> list[str]:
    """Keep the original glob expansion, de-duplication and sorted file order."""
    return sorted(
        {
            str(path.relative_to(root))
            for pattern in patterns
            for path in root.glob(pattern)
        }
    )


def validate_shards(tests: list[str], shards: list[list[str]]) -> None:
    """Reject missing, unexpected or repeated files (set equality is not enough)."""
    expected = Counter(tests)
    actual = Counter(path for shard in shards for path in shard)
    duplicate_input = sorted(path for path, count in expected.items() if count != 1)
    duplicates = sorted(path for path, count in actual.items() if count != 1)
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    if duplicate_input or duplicates or missing or unexpected:
        raise ValueError(
            f"Invalid shard coverage: duplicate_input={duplicate_input}, "
            f"duplicates={duplicates}, missing={missing}, unexpected={unexpected}"
        )


def shard_test_files(
    tests: list[str], count: int, durations: dict[str, float] | None = None,
) -> list[list[str]]:
    """Deterministic file-count balancing, or longest-first measured-cost balancing.

    Unknown files use the median known cost. Path order and then shard index
    break ties, so input/duration-map iteration order cannot change ownership.
    """
    if type(count) is not int or count < 1:
        raise ValueError("shard count must be a positive integer")
    if durations is not None and (
        not isinstance(durations, dict)
        or any(not isinstance(path, str) or type(value) not in (int, float)
               or not math.isfinite(value) or value < 0
               for path, value in durations.items())
    ):
        raise ValueError("durations must map file paths to finite nonnegative seconds")
    durations = durations or {}
    known = [durations[path] for path in tests if path in durations]
    fallback = median(known) if known else 1.0
    costs = {path: durations.get(path, fallback) for path in tests}
    shards: list[list[str]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for path in sorted(tests, key=lambda path: (-costs[path], path)):
        index = min(range(count), key=lambda i: (loads[i], len(shards[i]), i))
        shards[index].append(path)
        loads[index] += costs[path]
    # Preserve the original pytest collection order within each selected shard.
    shards = [sorted(shard) for shard in shards]
    validate_shards(tests, shards)
    return shards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, help="zero-based shard to execute")
    parser.add_argument("--list-shards", action="store_true", help="print JSON without running pytest or taking a lock")
    parser.add_argument("--durations-json", type=Path, help="optional JSON mapping test paths to measured seconds")
    parser.add_argument("--junitxml", type=Path, help="save pytest results and per-test durations")
    parser.add_argument("--host-lock", action="store_true", default=os.environ.get("UGRP_TEST_HOST_LOCK") == "1",
                        help="opt into the exclusive local host lock (also UGRP_TEST_HOST_LOCK=1)")
    args = parser.parse_args(argv)
    if args.shard_count < 1:
        parser.error("--shard-count must be positive")
    if args.shard_index is not None and not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index must satisfy 0 <= INDEX < COUNT")
    if not args.list_shards and args.shard_count > 1 and args.shard_index is None:
        parser.error("--shard-index is required when executing multiple shards")

    tests = collect_test_files(ROOT, TEST_PATTERNS)
    if not tests:
        print("No CI tests matched", file=sys.stderr)
        return 2
    try:
        durations = json.loads(args.durations_json.read_text()) if args.durations_json else None
        if args.durations_json and not isinstance(durations, dict):
            raise ValueError("durations JSON must be an object")
        shards = shard_test_files(tests, args.shard_count, durations)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.list_shards:
        print(json.dumps({
            "total_files": len(tests), "shard_count": len(shards),
            "coverage_verified": True,
            "balance": "durations" if durations and any(path in durations for path in tests) else "file_count",
            "shards": shards,
        }, indent=2))
        return 0

    index = args.shard_index if args.shard_index is not None else 0
    tests = shards[index]
    if not tests:
        print(f"Shard {index}/{args.shard_count} has no test files", file=sys.stderr)
        return 2  # Never invoke pytest with no paths: that collects the whole repo.

    if not check_fixtures(ROOT):
        return 2  # Refuse before pytest or the shared host lock is started.

    env = os.environ.copy()
    for name in tuple(env):
        if name.endswith("_API_KEY") or name in {"GOOGLE_APPLICATION_CREDENTIALS"}:
            env.pop(name)
    env.update({"CI": "true", "PYTHONDONTWRITEBYTECODE": "1"})
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    if args.junitxml:
        command.extend([f"--junitxml={args.junitxml}", "-o", "junit_family=legacy"])
    print(f"Running {len(tests)} offline test modules (shard {index}/{args.shard_count})", flush=True)
    lock_root = local_lock_root()
    if lock_root is not None:
        if args.host_lock:
            return run_locked(command, env, lock_root)
        try:
            held = agent_lock.status(lock_root)
        except (OSError, ValueError) as error:
            print(f"Warning: cannot read host lock ({error}); running offline tests without it", file=sys.stderr)
        else:
            if held and held.get("timing_sensitive") is True:
                print(f"Warning: timing-sensitive host lock held by {held.get('owner')}: "
                      f"{held.get('purpose')}; running offline tests without the host lock", file=sys.stderr)
    return subprocess.call(command, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
