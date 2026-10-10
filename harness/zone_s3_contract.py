"""Opt-in S3 DEV admission and source closure. Existing bundle pins are untouched."""
from __future__ import annotations

import re

from harness import zone_solo_cyan_contract_v106 as solo
from harness import zone_environment_registry as registry
from harness.python_source_closure import source_closure
from harness.zone_robot_model_runtime import require_v3_consumers
from harness.zone_study_inputs import OrderSheetSource
from harness.zone_s3_host import public_tasks, pair_task, ROLES, build_pair_provider

ROOT, hp = solo.ROOT, solo.hp
BUNDLE_ID = 'zone-s3-host-v107'
WORKFLOW_VERSION = '3.14.0'
SCENARIO_PATH = 'configs/zone_study_dev/dev_s1lite.json'
WORKFLOW = 'configs/simulation_workflows.json'
LAUNCH = 'experiments/2026-10-06-s3-host/launch_dev.zsh'
SEEDS = (601, 602, 603)
CAP_S, SETTLE_S = 1800., 3.


def inputs():
    scenario = hp.base.read(ROOT/SCENARIO_PATH)
    if scenario['scenario_id'] != 'dev_s1lite' or tuple(scenario['seeds']) != SEEDS:
        raise ValueError('S3 scenario/seed registration changed')
    if scenario['eval']['hidden_events']:
        raise ValueError('S3 has no hidden events')
    if scenario['map_id'] != solo.MAP_ID:
        raise ValueError('S3 requires final v3 wide-door map')
    report = registry.validate(scenario)
    if not report.ok:
        raise ValueError(f'S3 invalid scenario: {report.problems}')
    map_bundle = registry.bundle_for(scenario)
    sheet = OrderSheetSource(scenario, map_bundle).sheet()
    public_tasks(sheet['orders'])
    return scenario, map_bundle, sheet


def bundle(source_sha, *, seed=601, speedups='v98-exact-v6'):
    if not re.fullmatch('[0-9a-f]{40}', source_sha):
        raise ValueError('S3 requires a full source SHA')
    if type(seed) is not int or seed not in SEEDS or speedups not in ('none', 'v98-exact-v6'):
        raise ValueError('S3 unregistered DEV seed/speedups')
    scenario, map_bundle, sheet = inputs()
    static = hp.resolve(solo.MAP_ID)[0]
    require_v3_consumers({'skill_module': 'harness.zone_solo_cyan_v106'}, solo.build_provider)
    require_v3_consumers({'skill_module': 'harness.zone_s3_host'}, build_pair_provider)
    # Parent bundles are reused as source/calibration/timing provenance, not as
    # admission of new seeds or mixed placements, and never as success evidence.
    parent = solo.bundle(source_sha)
    paths = set(parent['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s3_contract.py', 'scripts/run_s3_host.py', 'sim/zone_s3_host.py']))
    paths.update((SCENARIO_PATH, WORKFLOW, LAUNCH))
    from sim.final_pair_highpose_clock import record as clock_record
    from sim.final_pair_highpose_nearclip import record as render_record
    from harness.zone_study_referee import profile
    return {'schema': 'ugrp.s3_host_bundle.v107', 'execution_bundle_id': BUNDLE_ID,
        'workflow_version': WORKFLOW_VERSION, 'source_sha': source_sha, 'check': 's3-host-dev',
        'scenario_id': scenario['scenario_id'], 'scenario_sha256': hp.base.digest(scenario),
        'map_id': solo.MAP_ID, 'map_sha256': hp.base.digest(static),
        'map_bundle_sha256': hp.base.digest(map_bundle), 'order_sheet_sha256': hp.base.digest(sheet),
        'robot_model': 'masterpi_v3', 'contact_profile': 'cargo_noslip_v1', 'weld': 'off',
        'seed': seed, 'provider_seeds': {'r1': seed, 'r2': seed+1, 'r3': seed+2},
        'pair_role_assignment': dict(ROLES), 'solo_robot': 'r3', 'model_calls': 0,
        'parent_bundles': [solo.BUNDLE_ID, hp.BUNDLE_ID],
        'parent_source_manifest_sha256': hp.base.digest(parent['source_sha256']),
        'calibration': solo.CALIBRATION, 'calibration_sha256': solo.CALIBRATION_SHA,
        'pair_search_prior': pair_task(static, public_tasks(sheet['orders'])['long_beam'])['sheet'],
        'host_clock': clock_record(), 'render_nearclip': render_record(),
        'case_cap_s': CAP_S, 'reset_cap_s': hp.RESET_CAP_S, 'tick_s': hp.TICK_S, 'settle_s': SETTLE_S,
        'speedups': speedups, 'referee': profile(), 'referee_feedback': False,
        'controller_inputs': ['own_rgb', 'static_map', 'own_command_history'],
        'inter_robot_channels': ['existing_pair_fixed_enum_status'],
        'admission_mode': hp.DEV_PILOT, 'dev_light': True, 'cohort_role': 'FUNCTIONAL_DEV',
        'research_result': False, 'confirmation_sample': False, 'physical_success': None,
        'in_run_drop_tilt_contact_detection': False,
        'source_sha256': {p: hp.base.sha(ROOT/p) for p in sorted(paths)}}


def verify(value):
    expected = bundle(value['source_sha'], seed=value['seed'], speedups=value['speedups'])
    if hp.base.digest(value) != hp.base.digest(expected):
        raise ValueError('S3 bundle/source/config mismatch')
