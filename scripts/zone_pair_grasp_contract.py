"""Source/behavior identity of the pair relook candidate; no physical imports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    'harness/zone_pair_grasp.py', 'harness/zone_pair_executor.py',
    'harness/zone_pair_guards.py', 'harness/zone_pair_geometry.py',
    'harness/zone_pair_status.py', 'harness/zone_pair_vision.py',
    'harness/owncam_pose_source.py', 'harness/owncam_localizer.py',
    'harness/zone_own_guards.py', 'scripts/run_zone_pair_dev.py',
    'scripts/zone_pair_dev_runtime.py', 'scripts/zone_pair_grasp_contract.py', 'scripts/evaluate_zone_pair_dev.py',
    'configs/simulation_workflows.json',
)


def grasp_contract():
    value = {
        'profile': 'zone_pair_grasp_relook_v1',
        'executor_profile': 'zone_pair_executor_v5_dev', 'status_profile': 'zone_pair_status_v5',
        'workflow': {'id': 'zone-pair-dev', 'version': '0.3.0'},
        'relook': 'mandatory at each grasp; shared own.pose/last_report; new tag in this sweep; no VO bypass',
        'max_std_xy_m': .05, 'max_std_yaw_deg': 3., 'base_margin_plus_residual_m': .035,
        'sweeps_max': 2, 'close_wait_s': 20.,
        'attachment': 'own RGB grip-view after issued CLOSED, segment bound; cleared on issued OPEN; post-lift co-motion still required',
        'close': 'own open grip-view and pose readiness -> close_ready_i -> same-grid close_go_i; evidence TTL 0.6 s',
        'evaluation_state_equivalence': {'pregrasp_descend': 'grasp', 'wait_close': 'grasp'},
        'contact_profile': 'cargo_noslip_v1', 'weld': False,
        'qualification': 'not physically executed; no inherited result',
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE_PATHS},
    }
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value
