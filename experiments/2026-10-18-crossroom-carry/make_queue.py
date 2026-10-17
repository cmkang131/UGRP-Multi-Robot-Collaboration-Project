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
    "visgoal_mirror_pulse_v1": "off",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--policy-source-sha',
                    default='c390105c2663a5b780e4ad8d69da72a5ffe1bce8')
    ap.add_argument('--prior-funnel',
                    default=f'{MAIN}/visgoal-gate-r4-lawnmower/recount.json')
    ap.add_argument('--output', default=str(
        ROOT / 'experiments/2026-10-18-crossroom-carry/queue-stageA.json'))
    a = ap.parse_args()
    missing = [f for f in FILES if not (ROOT / f).is_file()]
    if missing:
        raise SystemExit('MISSING_INPUTS ' + repr(missing))
    queue = {
        "schema": "ugrp.crossroom_run_queue.v1",
        "stage": "A_unloaded",
        "flow": "self_map",
        "branch": "claude/crossroom-carry",
        "task": "crossroom",
        "goal": "west pickup room -> divider door (0.50 m) -> zone B arrival, unloaded solo",
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
        "input_sha256": {f: sha(ROOT / f) for f in FILES},
        "rendered_host": "ugrp-act-l4-gcp3",
        "renderer_source": "/home/ugrp/ugrp-sim/src/16a946ff3",
        "legacy_source": "/home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25",
        "no_llm_calls": True,
        "top_camera_control": False,
        "own_rgb_count": 1,
        "run_name": "crossroom-stageA",
        "preflight": False,
        "sim_cap_s": 180.0,
        "output": f"{MAIN}/crossroom-stageA",
        "rejection_table": a.prior_funnel,
        "prior_funnel_note": ("prior funnel is the visgoal candidate C recount "
                              "(separate condition; used only as the prior "
                              "search-budget record, not pooled)"),
        "episode_count": 16,
        "candidate": "stage_a_unloaded",
        "no_pooling_conditions": ["visgoal-gate-r4", "visgoal-gate-r4-mirror",
                       "visgoal-gate-r4-lawnmower", "egonav-gate-n16-09",
                       "act15", "act16a", "act18"],
        "toggles": TOGGLES,
        "worlds_per_batch": 16,
        "cap_end_label": "cap_end",
        "input_audit": "controller_boundary_v1 (actual boundary scan; counts "
                       "are not runner-written constants)",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%SZ'),
    }
    Path(a.output).write_text(json.dumps(queue, indent=1) + '\n')
    print(json.dumps(dict(output=a.output,
                          input_sha256_n=len(queue['input_sha256']),
                          source_sha=queue['source_sha'],
                          prior_funnel=a.prior_funnel), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
