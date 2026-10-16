"""Source/behavior identity of the pair relook candidate; no physical imports."""
import hashlib
import json
from pathlib import Path

from harness.owncam_memory_time import TIME_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    'harness/owncam_memory.py', 'harness/owncam_memory_time.py',
    'harness/owncam_delivery_shared.py', 'harness/owncam_memory_delivery.py',
    'harness/owncam_memory_inputs.py', 'harness/owncam_pose_guard_provider.py',
    'harness/owncam_pose_guard_v3.py', 'configs/zone_pair_authorization.json',
    'harness/owncam_drive_mem_v3.py', 'harness/m1_owncam_memory_v3.py',
    'harness/vision_motion_init.py', 'harness/m2_provider_adapter.py',
    'harness/zone_own_deliver.py', 'harness/zone_own_team_host.py',
    'scripts/zone_pair_authorization.py', 'scripts/run_zone_study_integration.py',
    'scripts/run_m1_owncam_memory_v3.py', 'sim/zone_geometry_scene.py',
    'configs/zone_study_integration/pose_providers.json',
    'maps/zones/zone_wide_door_geometry_v2.json',
    'harness/pose_provider.py', 'harness/vision_pose_source.py', 'harness/zone_study_pose_delay.py',
    'harness/zone_own_driver.py', 'harness/owncam_drive_shared.py', 'sim/zone_own_scene_provider.py',
    'harness/owncam_time.py', 'harness/zone_own_contract.py',
    'harness/zone_own_executor.py', 'harness/zone_own_status.py',
    'harness/zone_own_perception.py', 'harness/zone_pair_obstruction.py',
    'harness/zone_pair_grasp.py', 'harness/zone_pair_executor.py',
    'harness/zone_pair_beam_track.py',
    'harness/zone_pair_align.py',
    'harness/zone_pair_guards.py', 'harness/zone_pair_geometry.py',
    'harness/zone_pair_status.py', 'harness/zone_pair_vision.py',
    'harness/owncam_pose_source.py', 'harness/owncam_localizer.py',
    'harness/owncam_pair_beam.py', 'harness/owncam_pair_beam_v2.py', 'harness/owncam_view.py',
    'harness/zone_own_guards.py', 'scripts/run_zone_pair_dev.py',
    'scripts/zone_pair_dev_runtime.py', 'scripts/zone_pair_grasp_contract.py', 'scripts/evaluate_zone_pair_dev.py',
    'configs/simulation_workflows.json',
)


def grasp_contract():
    value = {
        'profile': 'zone_pair_grasp_relook_v3',
        'executor_profile': 'zone_pair_executor_v7_dev', 'status_profile': 'zone_pair_status_v5',
        'workflow': {'id': 'zone-pair-dev', 'version': '0.5.0'},
        'memory_time_contract': TIME_CONTRACT,
        'pose_time': {'rounding_s': .0001, 'accepted_fix': 'raw accepted capture; strict after align start; report bounds tolerant in both directions; failed conjuncts logged'},
        'command_time': 'raw SIM time in host _apply/_hold and standalone LoggingPort apply/hold, identical to port/capture/relook clock; no command rounding; stop-wait failed conjuncts logged; memory look-fix capture time raw',
        'pose_contract': 'raw last_fix_t; fix_age_s; fix_source; std_xy_m/std_yaw_rad; observation_quality; provider-owned expected_observability and relocalization',
        'target_obstruction': 'active own pair job only; coarse order at initial pickup or fresh segment own RGB anchor; full band + colour/geometry/component support; merged/unknown/other objects retained; no collision guard changes',
        'align_relook': {
            'reset': 'hold -> wait for fresh initialized post-stop own report and bounded stationary guard cache -> PF reset; wait counts in existing per-look and cumulative limits',
            'fix_gap_s': 6., 'early_xy_m': .055, 'early_yaw_deg': 2.5,
            'max_looks_per_job': 8, 'max_s_per_look': 8., 'max_total_s': 40., 'max_directions_per_look': 3,
            'selection': 'safe LOOK_P20 pans ranked by provider expected_observability score; own pose and issued PWM only; actual new accepted own RGB observation required',
            'resume': 'same shared pose, fresh report, new accepted observation after stop, unchanged 5 cm/3 deg readiness and scheduling reserve; restore beam view; original align deadline retained',
            'status': 'aligning/abort only; existing close readiness barrier holds partner open',
            'basis': 'dev08 own report at 166.3: tag age 6 s, XY sigma .05486 m; 9.3 s before 175.6 HIGH .07004 m. Scheduling reserve is a dev bound, not calibrated safety/completion proof',
        },
        'relook': 'mandatory at each grasp; shared own.pose/last_report; new observation fix in this sweep; no VO bypass',
        'max_std_xy_m': .05, 'max_std_yaw_deg': 3., 'base_margin_plus_residual_m': .035,
        'sweeps_max': 2, 'close_wait_s': 20.,
        'attachment': 'own RGB grip-view after issued CLOSED, segment bound; cleared on issued OPEN; post-lift co-motion still required',
        'close': 'own open grip-view, pose readiness and fresh stationary RGB beam clearance -> close_ready_i -> same-grid close_go_i; recheck beam before every close PWM; evidence TTL 0.6 s',
        'stationary_beam': 'full own RGB standoff band centre + paired-edge axis; segment-local issued-command prediction including stall/slip uncertainty; clipped visible patch only checks consistency, never resets pose/age/sigma; no planned/stored-grip or wrist-attachment fallback; unchanged whole-beam distance and 35 mm + own pose + beam uncertainty inflation',
        'beam_track': {'max_age_s': 30., 'std_xy_floor_m': .015, 'std_yaw_floor_deg': 1.,
                       'drift_xy_m_s': .0005, 'drift_yaw_rad_s': .0005,
                       'arm_xy_m_pwm': .000001, 'arm_yaw_rad_pwm': .000002,
                       'motion_gain_bound': 1.6, 'partial_min_support': .95,
                       'partial_reasons': ['BAND_CLIPPED', 'END_CLIPPED'],
                       'qualification': 'dev bounds, not measured motion success or calibrated accuracy'},
        'evaluation_state_equivalence': {'pregrasp_standoff': 'grasp', 'pregrasp_descend': 'grasp', 'wait_close': 'grasp'},
        'contact_profile': 'cargo_noslip_v1', 'weld': False,
        'qualification': 'not physically executed; no inherited result',
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_PATHS},
    }
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value
