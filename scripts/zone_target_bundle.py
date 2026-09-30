"""T13 v86 final-environment candidate; historical v85 bytes stay unchanged."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

from harness.python_source_closure import source_closure
from harness.zone_study_contract import digest
from harness.zone_target_identity import PublicVisualCatalogue
from harness.zone_target_environment import environment_contract, execution_blockers

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'configs/t13_target_checks.json'
BUNDLE = 'config/rgb_execution_bundles/zone-target-v86.json'
BUNDLE_ID = 'zone-target-v86'
WORKFLOW_VERSION = '2.19.0'
WORKFLOW = 'configs/simulation_workflows.d/target_v86.json'


def load_config(root=ROOT):
    cfg = json.loads((Path(root)/CONFIG).read_text())
    if (cfg['execution_bundle_id'] != BUNDLE_ID or cfg['map_id'] != 'zone_wide_door_geometry_v3'
            or cfg['robot_model'] != 'masterpi_v3' or cfg['pose_provider'] != 'vision_zero_tag_final_v3_p03'
            or cfg['sim_cap_s_per_cell'] != 900 or cfg['weld'] is not False
            or cfg['sensor'] != 'off' or cfg['contact_profile'] != 'cargo_noslip_v1'
            or cfg['conditions'] != ['no_comm', 'peer_ko', 'leader_ko', 'structured']):
        raise ValueError('unsupported T13 controller/environment/config')
    PublicVisualCatalogue(cfg['public_visual_catalogue'])
    environment_contract(cfg, root=root)
    return cfg


def cell_inputs(cfg, name):
    cell = copy.deepcopy(cfg['cells'][name])
    catalogue = copy.deepcopy(cfg['public_visual_catalogue'])
    placements = copy.deepcopy(cfg['setup_only']['placements'])
    events = copy.deepcopy(cfg['hidden_events'])
    if cell.get('duplicate_cyan'):
        catalogue['objects'].append({**copy.deepcopy(catalogue['objects'][0]), 'item_id': 'cyan_2'})
        placements.append({'item_id': 'cyan_2', 'kind': 'cyan', 'order_id': 'unrequested-distractor',
                           'slot': 'P1-3', 'pose_m': [-.2, .75, 0.]})
        # Dev-only swap, both conditional on not held, at the original move
        # time. The native effect log determines whether the swap occurred.
        events.append({'event_id': 'cyan_2_swapped', 'kind': 'item_moved',
                       'trigger': {'kind': 'sim_time', 'at_sim_s': 30.},
                       'target': {'item_id': 'cyan_2', 'to_pose_m': [.4, -2.45, 0.]},
                       'discovery': {'kind': 'own_camera_self'}})
    spec = {'map': cfg['map_id'], 'seed': cfg['seed'], 'goal': {'A': {'cyan': 1}, 'B': {'red': 2}},
            'extra_boxes': {}, 'contact_profile': cfg['contact_profile'], 'job_sim_limit_s': 900.,
            'order_sheet': {'orders': copy.deepcopy(cfg['public_orders'])}, 'pair_order_sheets': {},
            'team_cargo': [{'item_id': p['item_id'], 'kind': p['kind'], 'pose': p['pose_m']}
                           for p in placements if p['kind'] == 'can'],
            'pose_priors': copy.deepcopy(cfg['public_dock_priors']), 'target_placements': placements,
            'visual_catalogue': catalogue, 'render_profile': cfg['render_profile'],
            'robot_model': cfg['robot_model']}
    return cell, spec, {'eval': {'hidden_events': events}}


def candidate_bundle(root=ROOT):
    root = Path(root)
    cfg = load_config(root)
    from harness import zone_final_environment as final
    parent = final.bundle(cfg['map_id'], check='p01', root=root)
    roots = ('scripts/run_zone_target_checks.py', CONFIG, WORKFLOW,
             'sim/masterpi_scene_v2.xml',  # template transformed by the v3 environment hook
             'configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json')
    files = sorted(set(source_closure(root, roots)) | set(parent['source_sha256']))
    from scripts.zone_pair_dev_contract import profile_contract
    return {'schema': 'ugrp.target_execution_bundle.v1', 'bundle_id': BUNDLE_ID,
            'status': 'experimental_unqualified', 'workflow_id': 'zone-target-checks',
            'runnable': not execution_blockers(cfg, root=root),
            'blocked_on': execution_blockers(cfg, root=root),
            'workflow_version': WORKFLOW_VERSION, 'scope': cfg['scope'],
            'parent_reference': 'zone-final-environment-v84 (PR #338); no inherited physical result',
            'final_environment': parent,
            'controller_inputs': parent['controller_inputs'],
            'controller_config_sha256': digest({k: v for k, v in cfg.items() if k != 'cells'}),
            'condition_overrides': False, 'role_assignment_in_controller_hash': False,
            'camera': {'sensor': 'own_robot_cam', 'width': 640, 'height': 480,
                       'raw': 'jpeg', 'skill': 'target-only PNG, original pixels, selected hue 92',
                       'source_profile': 'sim/masterpi_camera_profile.py'},
            'commands': {'executor': 'TargetOwnExecutor + unchanged OwnCamTeamHost macro timeline',
                         'tick_s': .1, 'frame_s': .2, 'maximum_frame_age_s': .25,
                         'cancel': 'drop own scheduled macro commands and hold immediately',
                         'capture': 'one observation per robot per exact SIM timestamp'},
            'contact': profile_contract(),
            'pose_provider': cfg['pose_provider'], 'sensors': 'off',
            'sources': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files},
            'assets': parent['model'],
            'verification': {'offline': 'see experiment record', 'physics': 'not_run', 'e2e': 'not_run'}}


def verify_bundle(root=ROOT):
    expected = json.loads((Path(root)/BUNDLE).read_text())
    actual = candidate_bundle(root)
    if expected != actual:
        raise ValueError('T13 registered bundle/source mismatch; register a new candidate before execution')
    return actual, digest(actual)
