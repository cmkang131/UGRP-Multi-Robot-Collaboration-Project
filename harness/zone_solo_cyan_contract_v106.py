"""Immutable inputs and DEV-only admission for S2; source closure generated offline."""
from __future__ import annotations

from harness import zone_pair_highpose_contract as hp
from harness.python_source_closure import source_closure
from harness.zone_robot_model_runtime import require_v3_consumers
from harness.zone_solo_cyan_v106 import build_provider, PROFILE, MOTION_PROXY, CAP_S

ROOT = hp.ROOT
BUNDLE_ID = 'zone-solo-cyan-v106'
WORKFLOW_VERSION = '3.13.0'
REGISTRY = 'configs/zone_solo_cyan_v106.json'
WORKFLOW = 'configs/simulation_workflows.d/solo_cyan_v106.json'
MAP_ID = 'zone_wide_door_geometry_v3'
CALIBRATION = 'experiments/2026-10-05-loaded-rest-calibration-v104/products_noise/calibration_dev_pilot_loaded_v102_rest_noise.json'
CALIBRATION_SHA = 'a75fc9325f8a8b89a158c2be0872cebfd4d11c8d2a7482c720eb9e1f99c41501'


def validate(*, robot_id, pickup_slot, destination, passage_id, seed, admission='dev-pilot'):
    from harness.zone_own_contract import pickup_slots
    from harness.zone_solo_cyan_v106 import passage_route
    if admission != 'dev-pilot':
        raise ValueError('SOLO_CYAN_DEV_ONLY')
    if robot_id not in ('r1', 'r2', 'r3') or seed not in (911, 912, 913, 914):
        raise ValueError('DEV robot/seed not registered')
    static = hp.resolve(MAP_ID)[0]
    if pickup_slot not in pickup_slots(static) or destination not in ('A', 'B', 'C'):
        raise ValueError('unknown static task vocabulary')
    passage_route(static, passage_id, destination)
    require_v3_consumers({'skill_module': 'harness.zone_solo_cyan_v106'}, build_provider)
    hp.calibration_for(hp.DEV_PILOT, ROOT/CALIBRATION, CALIBRATION_SHA, MAP_ID)
    reg = hp.base.read(ROOT/REGISTRY)
    if reg['execution_bundle_id'] != BUNDLE_ID or reg['runnable_modes'] != ['DEV_PILOT']:
        raise ValueError('solo registry mismatch')
    return static


def bundle(source_sha, *, robot_id='r3', pickup_slot='P1-2', destination='B', passage_id='door_1', seed=911,
           stage_probe='place', speedups='v98-exact-v6'):
    if stage_probe not in ('pick', 'door', 'place') or speedups not in ('none', 'v98-exact-v6'):
        raise ValueError('unregistered solo stage/speedups')
    args = dict(robot_id=robot_id, pickup_slot=pickup_slot, destination=destination, passage_id=passage_id, seed=seed)
    static = validate(**args)
    # Include the pair stack's explicit data reads/dynamic VIS3 files as well as our AST closure.
    parent = hp.bundle(MAP_ID, 'carry', hp.DEV_PILOT)
    paths = set(parent['source_sha256']) | set(source_closure(ROOT,
        ['harness/zone_solo_cyan_contract_v106.py', 'sim/solo_cyan_v106.py', 'scripts/run_solo_cyan.py']))
    paths.update((REGISTRY, WORKFLOW, CALIBRATION, 'experiments/2026-10-05-solo-cyan-v106/launch_dev.zsh'))
    from sim.final_pair_highpose_clock import record as clock_record
    from sim.final_pair_highpose_nearclip import record as render_record
    return {'schema': 'ugrp.solo_cyan_bundle.v106', 'execution_bundle_id': BUNDLE_ID,
        'workflow_version': WORKFLOW_VERSION, 'source_sha': source_sha, 'check': 'solo-cyan-dev',
        'map_id': MAP_ID, 'map_sha256': hp.base.digest(static), 'robot_model': 'masterpi_v3',
        'contact_profile': 'cargo_noslip_v1', 'weld': 'off', 'render_nearclip': render_record(),
        'host_clock': clock_record(), 'profile': PROFILE, 'motion_proxy': MOTION_PROXY,
        'parent_stack': hp.BUNDLE_ID, 'calibration_sha256': CALIBRATION_SHA,
        'case_cap_s': CAP_S, 'tick_s': hp.TICK_S, 'task': args,
        'controller_inputs': ['own_rgb', 'static_map', 'own_command_history'],
        'cohort_role': 'FUNCTIONAL_DEV', 'research_result': False, 'confirmation_sample': False,
        'dev_light': True, 'physical_success': None,
        'stage_probe': stage_probe, 'speedups': speedups,
        'in_run_drop_tilt_contact_detection': False,
        'source_sha256': {p: hp.base.sha(ROOT/p) for p in sorted(paths)}}
