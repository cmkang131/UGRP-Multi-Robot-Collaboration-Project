#!/usr/bin/env python3
"""Build ``queue-stageA.json`` for the cross-room carry Stage A gate.

The queue pins the policy source commit (visgoal C build, PR #582 draft), the
execution inputs and the stack values.  Every file that the runner or the
analysis reads is pinned by sha256 in ``input_sha256``.  Run this after the
files are final and before the freeze commit:

  python3 experiments/2026-10-18-crossroom-carry/make_queue.py
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = '/home/ugrp/ugrp-sim/runs'

FILES = [
    'experiments/2026-10-18-crossroom-carry/setups.json',
    'experiments/2026-10-18-crossroom-carry/prereg.json',
    'experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py',
    'experiments/2026-10-18-crossroom-carry/scripts/crossroom_recount.py',
    'experiments/2026-10-18-crossroom-carry/scripts/crossroom_setup_check.py',
    'experiments/2026-10-18-crossroom-carry/vendor/visual_goal_search.py',
    'experiments/2026-10-18-crossroom-carry/vendor/destination_visual_acquire.py',
    'experiments/2026-10-18-crossroom-carry/vendor/egocentric_landmark_memory.py',
    'experiments/2026-10-18-crossroom-carry/vendor/egomem_object_association.py',
    'experiments/2026-10-18-crossroom-carry/vendor/grasp_act_solo_lookback.py',
    'experiments/2026-10-18-crossroom-carry/vendor/mapbuild_command_prior.py',
    'experiments/2026-10-18-crossroom-carry/vendor/rovio_feature_statistics.py',
    'experiments/2026-10-18-crossroom-carry/vendor/scene_colour_boundary.py',
    'experiments/2026-10-18-crossroom-carry/vendor/solo_carry_obstacles.py',
    'experiments/2026-10-18-crossroom-carry/vendor/warp_act_core.py',
    'experiments/2026-10-18-crossroom-carry/vendor/warp_act_scene.py',
    'experiments/2026-10-18-crossroom-carry/vendor/warp_native_contact.py',
    'experiments/2026-10-18-crossroom-carry/vendor/own-command-calibration-r2.json',
    ('experiments/2026-10-18-crossroom-carry/vendor/'
     'walls_floor_contrast_v5_indigo110_s80-calibration.json'),
]

STAGE_FIX3_FILES = [
    'experiments/2026-10-18-crossroom-carry/prereg-stageA-fix3.json',
    'experiments/2026-10-18-crossroom-carry/scripts/vgs_fix.py',
    'experiments/2026-10-18-crossroom-carry/scripts/paint_area_filter.py',
    'experiments/2026-10-18-crossroom-carry/scripts/contact_recorder.py',
]

STAGE_FIX2_FILES = [
    'experiments/2026-10-18-crossroom-carry/prereg-stageA-fix2.json',
    'experiments/2026-10-18-crossroom-carry/scripts/vgs_fix.py',
    'experiments/2026-10-18-crossroom-carry/scripts/paint_area_filter.py',
    'experiments/2026-10-18-crossroom-carry/scripts/contact_recorder.py',
]

STAGE_FIX_FILES = [
    'experiments/2026-10-18-crossroom-carry/prereg-stageA-fix.json',
    'experiments/2026-10-18-crossroom-carry/scripts/vgs_fix.py',
    'experiments/2026-10-18-crossroom-carry/scripts/paint_area_filter.py',
    'experiments/2026-10-18-crossroom-carry/scripts/contact_recorder.py',
]

STAGE_B_FILES = [
    'experiments/2026-10-18-crossroom-carry/prereg-stageB.json',
    'experiments/2026-10-18-crossroom-carry/crossroom_carry_scene_v1.json',
    'experiments/2026-10-18-crossroom-carry/scripts/carry_state_own.py',
    'experiments/2026-10-18-crossroom-carry/scripts/stageB_settle_check.py',
]

STACK_VALUES = {
    "physics_backend": "mjwarp_batch_v1",
    "contact_profile": "warp_native_contact_v1",
    "noslip_iterations": 0,
    "scene_profile": "walls_floor_contrast_v5_indigo110_s80",
    "cargo_version": "v6",
    "scenario_version": "v7",
    "heavy_crate": False,
    "localization_path": "egocentric_landmark_memory_v1",
    "rbpf": "off",
    "localization_engine": "OpenCV",
    "held_object_hidden_v1": True,
    "held_world_reads": 0,
    "weld": False,
    "top_camera_control": False,
    "heading_mode": "on",
    "ultrasonic_front": "off",
    "wall_cap": None,
    "speed_gate": "record_only",
    "speed_metric": "wall_s/(sim_s*nworld)",
    "gcp_host": "ugrp-act-l4-gcp3",
    "gcp_guards": {"idle_minutes": 20, "budget_stop": True,
                   "credentials_on_vm": False},
    "no_pooling": True,
    "planning_cap_basis": "compute_or_sim",
    "rejection_ledger": ["reason_category", "blocked_object", "minimum_gap_m"],
    "cap_end_label": "cap_end",
    "gcp_project": "ugrp-sim-c-1016",
    "gcp_account": "changmin5781@gmail.com",
    "selfmap_map_correction": "off",
    "localization_initial_prior": "none",
    "static_map_use": "none",
    "goal_discovery": "visual_search",
}

TOGGLES = {
    "crossroom_carry_v1": "on",
    "crossroom_door_gap_v1": "on",
    "crossroom_carry_state_v1": "on",
    "crossroom_route_memory_v1": "on",
    "crossroom_safe_lookaround_v1": "on",
    "visgoal_expanding_search_v1": "on",
    "visgoal_arrival_aim_inset_v1": "off",
    "visgoal_mirror_pulse_v1": "off",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=('A_unloaded', 'B_loaded', 'A_unloaded_fix',
                                        'A_unloaded_fix2', 'A_unloaded_fix3'),
                    default='A_unloaded')
    ap.add_argument('--policy-source-sha',
                    default='c390105c2663a5b780e4ad8d69da72a5ffe1bce8')
    ap.add_argument('--prior-funnel',
                    default=f'{MAIN}/visgoal-gate-r4-lawnmower/recount.json')
    ap.add_argument('--output', default=None)
    a = ap.parse_args()
    if a.stage == 'B_loaded':
        files = FILES + STAGE_B_FILES
    elif a.stage == 'A_unloaded_fix3':
        files = FILES + STAGE_FIX3_FILES
    elif a.stage == 'A_unloaded_fix2':
        files = FILES + STAGE_FIX2_FILES
    elif a.stage == 'A_unloaded_fix':
        files = FILES + STAGE_FIX_FILES
    else:
        files = list(FILES)
    missing = [f for f in files if not (ROOT / f).is_file()]
    if missing:
        raise SystemExit('MISSING_INPUTS ' + repr(missing))
    stage_b = a.stage == 'B_loaded'
    stage_fix = a.stage == 'A_unloaded_fix'
    stage_fix2 = a.stage in ('A_unloaded_fix2', 'A_unloaded_fix3')
    stage_fix3 = a.stage == 'A_unloaded_fix3'
    toggles = dict(TOGGLES)
    stage_fields = {}
    if stage_b:
        toggles['crossroom_carry_scene_v1'] = 'on'
        stage_fields = {
            'loaded_scene': ('experiments/2026-10-18-crossroom-carry/'
                             'crossroom_carry_scene_v1.json'),
            'gripper_pwm_closed': 1500,
            'loaded_start_note': ('single red box placed in the closed gripper by the '
                                  'runner setup, 1 Sim s CPU settle, weld off'),
            'cargo_own_thresholds_file': ('experiments/2026-10-18-crossroom-carry/'
                                          'setup-validation-B.json'),
        }
    if stage_b:
        queue_name = 'queue-stageB.json'
    elif stage_fix3:
        queue_name = 'queue-stageA-fix3.json'
    elif stage_fix2:
        queue_name = 'queue-stageA-fix2.json'
    elif stage_fix:
        queue_name = 'queue-stageA-fix.json'
    else:
        queue_name = 'queue-stageA.json'
    if stage_fix:
        toggles.update({'crossroom_gap_twosided_v1': 'on',
                        'crossroom_door_align_v1': 'on',
                        'crossroom_paint_area_v1': 'on',
                        'crossroom_contacts_v1': 'on'})
    if stage_fix2:
        toggles.update({'crossroom_gap_twosided_v1': 'on',
                        'crossroom_door_align_v1': 'on',
                        'crossroom_paint_area_v1': 'on',
                        'crossroom_contacts_v1': 'on',
                        'crossroom_gap_twosided_v2_v1': 'on',
                        'crossroom_paint_area_v2_v1': 'on',
                        'crossroom_approach_escape_v1': 'on'})
    if stage_fix3:
        toggles.update({'crossroom_gap_v3_v1': 'on',
                        'crossroom_zone_edge_v1': 'on'})
    out_path = (ROOT / 'experiments/2026-10-18-crossroom-carry/' / queue_name)
    queue = {
        "schema": "ugrp.crossroom_run_queue.v1",
        "stage": a.stage,
        "flow": "self_map",
        "branch": "claude/crossroom-carry",
        "task": "crossroom",
        "goal": ("west pickup room, loaded with the red box -> divider door (0.50 m) -> "
                 "zone B arrival (loaded, single box reduced scene)" if stage_b else
                 "west pickup room -> divider door (0.50 m) -> zone B arrival, unloaded solo"),
        "source_sha": a.policy_source_sha,
        "source_note": ("policy pin: visgoal candidate C build (PR #582 draft), "
                        "vendored byte copy in experiments/2026-10-18-crossroom-carry/vendor"),
        "setups": "experiments/2026-10-18-crossroom-carry/setups.json",
        "runner": "experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py",
        "memory_implementation": "legacy_v1",
        "memory_item_schema": "ugrp.memory_item.v1",
        "static_map_use": "none",
        "localization_initial_prior": "none",
        "destination_zone": "B",
        "map_id": "zone_wide_door_geometry_v3",
        "scenario_id": "s1_normal_mixed_v7",
        "rejection_ledger": {
            "required_fields": ["reason_category", "blocked_object",
                                "minimum_gap_m"]},
        "stack_values": STACK_VALUES,
        "input_sha256": {f: sha(ROOT / f) for f in files},
        "rendered_host": "ugrp-act-l4-gcp3",
        "renderer_source": "/home/ugrp/ugrp-sim/src/16a946ff3",
        "legacy_source": "/home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25",
        "no_llm_calls": True,
        "top_camera_control": False,
        "own_rgb_count": 1,
        "run_name": ("crossroom-stageB" if stage_b else
                     "crossroom-stageA-fix3" if stage_fix3 else
                     "crossroom-stageA-fix2" if stage_fix2 else
                     "crossroom-stageA-fix" if stage_fix else "crossroom-stageA"),
        "preflight": False,
        "sim_cap_s": 180.0,
        "output": (f"{MAIN}/crossroom-stageB" if stage_b else
                   f"{MAIN}/crossroom-stageA-fix3" if stage_fix3 else
                   f"{MAIN}/crossroom-stageA-fix2" if stage_fix2 else
                   f"{MAIN}/crossroom-stageA-fix" if stage_fix else
                   f"{MAIN}/crossroom-stageA"),
        "rejection_table": (f"{MAIN}/crossroom-stageA/recount.json"
                            if stage_b else
                            f"{MAIN}/crossroom-stageA/recount.json" if stage_fix
                            else f"{MAIN}/crossroom-stageA/recount.json"
                            if stage_fix2 else a.prior_funnel),
        "prior_funnel_note": ("prior funnel is the visgoal candidate C recount "
                              "(separate condition; used only as the prior "
                              "search-budget record, not pooled)"),
        "episode_count": 16,
        "candidate": ("stage_b_loaded_single_red_box" if stage_b else
                      "stage_a_unloaded_fix3" if stage_fix3 else
                      "stage_a_unloaded_fix2" if stage_fix2 else
                      "stage_a_unloaded_fix" if stage_fix else "stage_a_unloaded"),
        "no_pooling_conditions": ["visgoal-gate-r4", "visgoal-gate-r4-mirror",
                       "visgoal-gate-r4-lawnmower", "egonav-gate-n16-09",
                       "act15", "act16a", "act18"],
        "toggles": toggles,
        "worlds_per_batch": 16,
        "cap_end_label": "cap_end",
        "input_audit": "controller_boundary_v1 (actual boundary scan; counts "
                       "are not runner-written constants)",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%SZ'),
    }
    queue.update(stage_fields)
    default_out = str(out_path)
    output = a.output if a.output else default_out
    Path(output).write_text(json.dumps(queue, indent=1) + '\n')
    print(json.dumps(dict(output=output, stage=queue['stage'],
                          input_sha256_n=len(queue['input_sha256']),
                          source_sha=queue['source_sha'],
                          prior_funnel=queue['rejection_table']), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
