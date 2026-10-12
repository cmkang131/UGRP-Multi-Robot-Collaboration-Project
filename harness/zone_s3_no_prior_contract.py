"""New finite mixed smoke; v107/v108 and S2 cohort contracts are not resealed."""
import copy
import json
import re

from harness import zone_s3_contract as old
from harness import zone_s3_door_yield as door
from harness.zone_s3_no_prior import public_tasks
from harness.python_source_closure import source_closure

ROOT, hp = old.ROOT, old.hp
BUNDLE_ID = 'zone-s3-no-prior-v142'
WORKFLOW_VERSION = '7.35.0'
OPTION = 'v141_mixed_v1'
SCENARIO_PATH = 'configs/zone_study_dev/s3_no_prior_v142.json'
PLAN = 'experiments/2026-10-09-s3-no-prior/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_no_prior_v142.json'
SEEDS = (14201,)


def inputs():
    scenario = hp.base.read(ROOT/SCENARIO_PATH)
    if scenario['seeds'] != [14201, 14202, 14203] or scenario['eval']['hidden_events']:
        raise ValueError('exact single smoke registration required')
    report = old.registry.validate(scenario)
    if not report.ok:
        raise ValueError(report.problems)
    mapped = old.registry.bundle_for(scenario)
    sheet = old.OrderSheetSource(scenario, mapped).sheet()
    public_tasks(sheet['orders'])
    return scenario, mapped, sheet


def controller_config():
    template = hp.base.read(ROOT/'configs/s2_v133_full_template.json')
    plan = hp.base.read(ROOT/'experiments/2026-10-06-s2-realism/unknown-start-registration.json')
    if hp.base.sha(ROOT/'configs/s2_v133_full_template.json') != plan['template_sha256']:
        raise ValueError('S2 template hash differs')
    keys = ('motion_model', 'pulse_calibration', 'extrinsic_calibration', 'floor_appearance',
            'stiff_camera_table', 'look_ahead_calibration')
    result = {k: copy.deepcopy(template[k]) for k in keys}
    result['options'] = {**copy.deepcopy(plan['baseline_options']),
        'start_prior': 'none_v1', 'global_localization': 'augmented_active_v1',
        'particle_sampling': 'kld_global_v1', 'active_localization': 'discriminating_views_v1',
        'active_rotation_guard': 'rgb_homography_bound_v1', 'idle_robot_contacts': 'off'}
    return result


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    if not re.fullmatch('[0-9a-f]{40}', sha) or seed not in SEEDS or speedups != 'v98-exact-v6':
        raise ValueError('full SHA, registered seed and exact speedups required')
    scenario, mapped, sheet = inputs()
    # Parent metadata only; the registered S2/S3 execution paths are unchanged.
    value = old.bundle(sha, seed=old.SEEDS[0], speedups=speedups)
    config = controller_config()
    value.update(schema='ugrp.s3_no_prior_bundle.v142', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, seed=seed, provider_seeds={r: seed+i for i, r in enumerate(old.ROLES.values())},
        scenario_id=scenario['scenario_id'], scenario_sha256=hp.base.digest(scenario),
        map_bundle_sha256=hp.base.digest(mapped), order_sheet_sha256=hp.base.digest(sheet),
        no_prior=OPTION, controller_config=config, options=config['options'],
        door_yield=door.PROFILE, door_protocol=door.specification(),
        controller_inputs=['own_rgb', 'static_map', 'own_command_history'],
        known_start_information=False, weld='off', model_calls=0,
        case_cap_s=1800., wall_cap_s=10800., raw_budget_bytes=6*1024**3,
        idle_robot_contacts='off', drive_profile='masterpi_drive_friction_v7',
        pair_v7_loaded_motion_qualified=False,
        parent_bundles=['zone-s3-host-v107', 'zone-s3-door-yield-v108', 'zone-s2-realism-v141'],
        preregistration=hp.base.read(ROOT/PLAN),
        inter_robot_channels=['existing_pair_fixed_enum_status', door.PROFILE])
    value['provider_seeds'] = {r: seed+i for i, r in enumerate(('r1', 'r2', 'r3'))}
    paths = set(value['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s3_no_prior_contract.py', 'scripts/run_s3_no_prior.py', 'sim/zone_s3_no_prior.py']))
    paths.update((SCENARIO_PATH, PLAN, WORKFLOW, 'configs/s2_v133_full_template.json',
        'experiments/2026-10-06-s2-realism/unknown-start-registration.json'))
    value['source_sha256'] = {p: hp.base.sha(ROOT/p) for p in sorted(paths)}
    return value


def verify(value):
    if value != bundle(value['source_sha'], seed=value['seed'], speedups=value['speedups']):
        raise ValueError('S3 no-prior source/config mismatch')
