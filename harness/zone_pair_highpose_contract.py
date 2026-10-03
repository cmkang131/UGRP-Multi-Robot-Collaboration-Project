"""New v96 admission: v92 measured HIGH calibration, no v88 relabelling."""
from __future__ import annotations

import copy
from harness import zone_final_pair_calibration_v92_contract as d5

from harness import zone_final_pair_contract as previous
from harness import zone_pair_highpose as pose

base, ROOT = previous.base, previous.ROOT
BUNDLE_ID = 'zone-final-pair-highpose-v96'
WORKFLOW_ID, WORKFLOW_VERSION = 'zone-final-pair-highpose-v96', '3.8.0'
REGISTRY = 'configs/zone_pair_highpose_v96.json'
WORKFLOW = 'configs/simulation_workflows.d/pair_highpose_v96.json'
CALIBRATION_CONTRACT = d5.CALIBRATION_CONTRACT
D5_ADMISSION = 'configs/calibration/zone_pair_highpose_d5_admission.json'
REGISTRY_BLOCK = 'HIGHPOSE_BUNDLE_RUNNABLE_FALSE'
PROVIDER_ID = 'opencv_owncam_final_pair_highpose_v96'
PRECONDITION = 'V92_MEASURED_SIM_HIGHPOSE_CALIBRATION_REQUIRED'
CHECKS, ROBOTS = ('p03', 'carry'), previous.ROBOTS
RESET_CAP_S, TICK_S, COLLECTION_FRAME_S = previous.RESET_CAP_S, previous.TICK_S, previous.COLLECTION_FRAME_S
camera_record = previous.camera_record


def registry():
    reg = base.read(ROOT / REGISTRY)
    if (reg['execution_bundle_id'] != BUNDLE_ID or reg['workflow_id'] != WORKFLOW_ID
            or reg['workflow_version'] != WORKFLOW_VERSION or reg['runnable'] is not False
            or reg['precondition'] != PRECONDITION or reg['provider_id'] != PROVIDER_ID
            or reg['calibration_contract_sha256'] != base.sha(ROOT / CALIBRATION_CONTRACT)):
        raise ValueError('v96 registry mismatch')
    return reg


def resolve(map_id):
    static, row, _ = previous.resolve(map_id)
    reg = registry()
    contract = base.read(ROOT / CALIBRATION_CONTRACT)
    if (map_id not in reg['maps'] or contract['maps'][map_id] != base.digest(static)
            or contract['loaded_pose_id'] != pose.POSE_ID
            or contract['loaded_camera_keys'] != ['896,2035,1894,1500']):
        raise ValueError('v96 static map/pose contract mismatch')
    for path, digest in contract['static_sources_sha256'].items():
        if base.sha(ROOT / path) != digest:
            raise ValueError('v96 static source mismatch: '+path)
    return static, row, contract


def d5_admission():
    """Reviewed trust roots, never supplied by CLI/calibration JSON."""
    admission = base.read(ROOT / D5_ADMISSION)
    path = ROOT / admission['assembler_registration']
    if base.sha(path) != admission['assembler_registration_sha256']:
        raise ValueError('D5 assembler registration changed')
    registration = base.read(path)
    for key, relative in (('assembler_sha256', registration['assembler_entry_point']),
                          ('loader_contract_sha256', CALIBRATION_CONTRACT)):
        if base.sha(ROOT / relative) != registration[key]:
            raise ValueError('unapproved D5 implementation: '+relative)
    return admission, registration


def measured_calibration(path, expected_sha, map_id):
    """Exact D5 validator plus independently pinned completion evidence.

    Self-declared hex strings are not evidence. Production has no synthetic
    flag, environment override, or caller-provided trust list. Tests replace
    d5_admission with an isolated fixture trust root.
    """
    if path is None or expected_sha is None:
        raise ValueError(PRECONDITION)
    resolve(map_id)
    cal = d5.measured_calibration(path, expected_sha, map_id)
    admission, registration = d5_admission()
    if (cal['assembler_sha256'] != registration['assembler_sha256']
            or cal['loaded_schedule_sha256'] != registration['loaded_schedule_sha256']
            or cal['criterion_sha256'] != registration['criterion_B_double_prime_sha256']):
        raise ValueError('unapproved D5 assembler/schedule/criterion')
    approved = next((row for row in admission['completed_measurements']
                     if row['calibration_sha256'] == expected_sha), None)
    if approved is None:
        raise ValueError(PRECONDITION+': completed measurement not registered')
    for key in ('source_sha', 'measurement_manifest_sha256', 'collection_sources'):
        if cal[key] != approved[key]:
            raise ValueError('D5 completed measurement provenance mismatch: '+key)
    if cal.get('missing') != []:
        raise ValueError('D5 completed measurement has missing fields')
    evidence = approved.get('completed_collections', {})
    if set(evidence) != {'unloaded', 'fine', 'loaded'}:
        raise ValueError('D5 completed collection evidence required')
    for name, row in evidence.items():
        if (row.get('source_sha') != cal['collection_sources'][name]
                or row.get('status') != 'COLLECTED_UNQUALIFIED'
                or row.get('protocol_complete') is not True
                or row.get('source_unchanged') is not True
                or row.get('partial_data_retained') is not False
                or row.get('unattempted') != [] or row.get('failure') is not None):
            raise ValueError('D5 PARTIAL/incomplete collection: '+name)
    # Only D5 sibling products are read, never manifest-referenced raw paths.
    from pathlib import Path
    folder = Path(path).parent
    manifest_path, report_path = folder/'input_manifest.json', folder/'fit_report.json'
    if (base.sha(manifest_path) != cal['measurement_manifest_sha256']
            or base.sha(report_path) != approved['fit_report_sha256']):
        raise ValueError('D5 completion product hash mismatch')
    manifest, report = base.read(manifest_path), base.read(report_path)
    if (manifest.get('schema') != 'ugrp.v92_calibration_inputs.v1'
            or manifest.get('execution_source_sha') != cal['source_sha']
            or manifest.get('raw_unchanged') is not True
            or manifest.get('working_tree_dirty') is not False
            or any(report.get(name, {}).get('collection_audit') != 'PASS' for name in evidence)):
        raise ValueError('D5 completed measurement audit required')
    return cal


STATIC_PF_DEFAULTS = 'harness/owncam_localizer.py'


def student_calibration(cal):
    """D5 measured fields over the frozen localizer's static PF options.

    The D5 assembler writes only measured fields (motion/loaded/fine, pair
    model, cameras, pan). Particle count, map clearance, measurement noise and
    reset options are fixed algorithm settings from DEFAULT_PARAMS, never
    measured values; every measured key overrides them. Nothing is inferred.
    """
    from harness.owncam_localizer import DEFAULT_PARAMS
    out = copy.deepcopy(cal)
    params = copy.deepcopy(DEFAULT_PARAMS)
    for key, value in cal['params'].items():
        if isinstance(value, dict) and isinstance(params.get(key), dict):
            params[key] = {**params[key], **copy.deepcopy(value)}
        else:
            params[key] = copy.deepcopy(value)
    out['params'] = params
    out['student_params_source'] = {'measured': 'D5 calibration params (override)',
        'static_defaults': STATIC_PF_DEFAULTS, 'static_defaults_sha256': base.sha(ROOT/STATIC_PF_DEFAULTS)}
    return out


def require_runnable(value):
    if registry()['runnable'] is not True or value.get('runnable') is not True:
        raise ValueError(REGISTRY_BLOCK)


def cases(check, map_id=None):
    if check not in CHECKS:
        raise ValueError('v96 supports student P03/carry only')
    return previous.cases(check, map_id)


def execution_timing(check):
    cases(check)
    timing = previous.execution_timing(check)
    timing['stabilization']['high_pose'] = pose.record()
    timing['high_checkpoint_policy'] = {'remain_high': True, 'open': False, 'reobserve_min_s': 1.2}
    timing['parent_differences'].append('single low lift/HIGH raise; stay HIGH at intermediate stop/reobserve; lower/open only at final release')
    return timing


def bundle(map_id, check):
    from harness.python_source_closure import source_closure
    static, _, contract = resolve(map_id)
    cases(check, map_id)
    value = copy.deepcopy(previous.bundle(map_id, check))
    value.update(schema='ugrp.final_pair_bundle.v96', execution_bundle_id=BUNDLE_ID,
        workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, runnable=False,
        blocked_on=[PRECONDITION], provider_id=PROVIDER_ID,
        controller_variant='b-v6h1-v3-highpose-opencv', revision='D1 new candidate; no inherited acceptance',
        localization='OpenCV wall-band detector + static map particle filter; no learned segmentation',
        timing=execution_timing(check), high_pose=pose.record(), calibration_contract=contract,
        calibration_selection='D5 v92 loader v2 + registered complete measurement evidence; HIGH only')
    entries = ['scripts/run_pair_highpose.py', 'harness/zone_pair_highpose_runtime.py',
               'harness/vision_pose_source_highpose.py']
    paths = set(value['source_sha256']) | set(source_closure(ROOT, entries)) | {REGISTRY, WORKFLOW, CALIBRATION_CONTRACT, D5_ADMISSION,
        'configs/zone_final_pair_v92_schedule.json.gz',
        'configs/zone_pair_highpose_confirmation_v96.json',
        'experiments/2026-10-03-v92-loaded-schedule/criterion_B_double_prime.json',
        'experiments/2026-10-03-v92-loaded-schedule/assembly/registration.json'}
    value['source_sha256'] = {p: base.sha(ROOT / p) for p in sorted(paths)}
    return value
