"""Source/behavior identity of the pair relook candidate; no physical imports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
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
        'profile': 'zone_pair_grasp_relook_v2',
        'executor_profile': 'zone_pair_executor_v6_dev', 'status_profile': 'zone_pair_status_v5',
        'workflow': {'id': 'zone-pair-dev', 'version': '0.4.0'},
        'align_relook': {
            'reset': 'hold -> wait for fresh initialized post-stop own report and bounded stationary guard cache -> PF reset; wait counts in existing per-look and cumulative limits',
            'tag_gap_s': 6., 'early_xy_m': .055, 'early_yaw_deg': 2.5,
            'max_looks_per_job': 8, 'max_s_per_look': 8., 'max_total_s': 40., 'max_directions_per_look': 3,
            'selection': 'safe LOOK_P20 pans ranked by static tag projected pixel area; own pose and issued PWM only; actual new accepted own RGB tag required',
            'resume': 'same shared pose, fresh report, new accepted tag after stop, unchanged 5 cm/3 deg readiness and scheduling reserve; restore beam view; original align deadline retained',
            'status': 'aligning/abort only; existing close readiness barrier holds partner open',
            'basis': 'dev08 own report at 166.3: tag age 6 s, XY sigma .05486 m; 9.3 s before 175.6 HIGH .07004 m. Scheduling reserve is a dev bound, not calibrated safety/completion proof',
        },
        'relook': 'mandatory at each grasp; shared own.pose/last_report; new tag in this sweep; no VO bypass',
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
