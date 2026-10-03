"""New v96 admission: v92 measured HIGH calibration, no v88 relabelling."""
from __future__ import annotations

import copy
from harness import zone_final_pair_calibration_v92_contract as d5

from harness import zone_final_pair_contract as previous
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_grip as grip

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
# Coordinator amendment (decided a priori from physics before any P03 run):
# per-case student cap 300 SIM s replaces the inherited 3x120 (fix363
# COORDINATOR_DECISION.md). Lower bounds 63.8/104.2/184.6 s per checkpoint and
# 190-219 s full carry; 300 s ~ 1.4x the largest bound.
CASE_CAP_S = 300.
CAP_DECISION = 'experiments/2026-10-03-pair-carry-highpose/fix363/COORDINATOR_DECISION.md'
# Coordinator DEV_PILOT admission (2026-10-03): a non-confirmatory functional
# pilot on one exact-sha256 calibration while the v92 MEASURED_SIM assembly is
# PARTIAL. The MEASURED_SIM path below is unchanged and its list stays empty.
MEASURED_SIM, DEV_PILOT = 'MEASURED_SIM', 'DEV_PILOT'
DEV_PILOT_RULE = 'DEV_PILOT_C0_ZERO_v1'
DEV_PILOT_PRECONDITION = 'V96_DEV_PILOT_CALIBRATION_REQUIRED'
DEV_PILOT_LABELS = {'admission_mode': DEV_PILOT, 'run_status': 'FUNCTIONAL_DEV',
                    'cohort_role': 'DEV_PILOT_FUNCTIONAL_DEV', 'tensorboard_cohort': 'v96-dev-pilot-functional',
                    'confirmation_sample': False, 'promotable': False, 'measured_sim_evidence': False}
NOT_PROMOTABLE = 'DEV_PILOT_RESULT_NOT_PROMOTABLE'


def registry():
    reg = base.read(ROOT / REGISTRY)
    if (reg['execution_bundle_id'] != BUNDLE_ID or reg['workflow_id'] != WORKFLOW_ID
            or reg['workflow_version'] != WORKFLOW_VERSION or reg['runnable'] is not False
            or reg['precondition'] != PRECONDITION or reg['provider_id'] != PROVIDER_ID
            or reg['calibration_contract_sha256'] != base.sha(ROOT / CALIBRATION_CONTRACT)
            or reg.get('case_cap', {}).get('sim_cap_s') != CASE_CAP_S
            or reg['case_cap'].get('decision') != CAP_DECISION
            or reg['case_cap'].get('decided_before_p03_data') is not True
            or reg.get('grip_monitor', {}).get('scope') != grip.MONITOR_SCOPE
            or reg['grip_monitor'].get('in_run_grip_loss_detection') is not False):
        raise ValueError('v96 registry mismatch')
    dev = reg.get('dev_pilot', {})
    if (dev.get('calibration_status') != DEV_PILOT or dev.get('rule') != DEV_PILOT_RULE
            or dev.get('rule_key') != 'dev_rule' or 'unloaded_motion_fill' not in dev
            or any(dev.get(k) != v for k, v in DEV_PILOT_LABELS.items())
            or not isinstance(dev.get('admitted_calibration_sha256'), list)):
        raise ValueError('v96 DEV_PILOT registry mismatch')
    return reg


def dev_pilot_admission():
    """Registered DEV_PILOT trust root (exact sha256 list); tests monkeypatch it."""
    return registry()['dev_pilot']


def dev_pilot_calibration(path, expected_sha, map_id):
    """Exact-sha DEV_PILOT calibration: v92 output structure, c0 = 0. Never MEASURED_SIM.

    The only permitted gap is the 10 unloaded params.motion fields (no approved
    unloaded three-axis profile); they are filled from the registered DEV
    source (registry dev_pilot.unloaded_motion_fill, pinned by file sha256).
    Structural checks are the unchanged v92 loader run on a copy whose status
    alone is normalized. The returned calibration records the fill.
    """
    import json
    import math
    import tempfile
    from pathlib import Path
    if path is None or expected_sha is None:
        raise ValueError(DEV_PILOT_PRECONDITION)
    resolve(map_id)
    dev = dev_pilot_admission()
    if expected_sha not in dev['admitted_calibration_sha256']:
        raise ValueError(DEV_PILOT_PRECONDITION+': calibration sha256 not admitted')
    if base.sha(path) != expected_sha:
        raise ValueError('DEV_PILOT calibration hash mismatch')
    cal = base.read(path)
    if (cal.get('status') != DEV_PILOT or cal.get(dev['rule_key']) != DEV_PILOT_RULE
            or cal.get('confirmatory') is not False):
        raise ValueError('DEV_PILOT calibration status/rule mismatch')
    deadband = cal.get('params', {}).get('motion_loaded', {}).get('deadband', {})
    c0, u1 = deadband.get('c0'), deadband.get('u1')
    if (not isinstance(c0, list) or [float(v) for v in c0] != [0., 0., 0.]
            or not isinstance(u1, list) or len(u1) != 3
            or not all(math.isfinite(float(v)) and float(v) > 0 for v in u1)):
        raise ValueError('DEV_PILOT_C0_ZERO_v1 requires c0 == [0,0,0] and u1 > 0')
    fill = dev['unloaded_motion_fill']
    missing = [row['field'] if isinstance(row, dict) else row for row in cal.get('missing', [])]
    motion = cal['params'].get('motion') or {}
    if missing:
        from harness.owncam_localizer import DEFAULT_PARAMS
        if (sorted(missing) != sorted(fill['fields'])
                or any(motion.get(f.rsplit('.', 1)[1]) is not None for f in fill['fields'])):
            raise ValueError('DEV_PILOT calibration may miss only the registered unloaded motion fields')
        if (base.sha(ROOT/fill['source'].split()[0]) != fill['source_sha256']
                or fill['values'] != {**DEFAULT_PARAMS['motion'], 'tau_stop_s': DEFAULT_PARAMS['motion']['tau_s']}):
            raise ValueError('DEV_PILOT unloaded motion fill source changed')
        cal = copy.deepcopy(cal)
        cal['params']['motion'] = copy.deepcopy(fill['values'])   # null keys dropped -> code defaults
        cal['missing'] = []
        cal['dev_pilot_fill'] = {'fields': fill['fields'], 'source': fill['source'],
                                 'source_sha256': fill['source_sha256'], 'label': 'DEV'}
    # DEV provenance (not the MEASURED assembler): sibling dev manifest, clean
    # source, script hash and the PARTIAL measured parent it was derived from.
    import re
    manifest_path = Path(path).parent/'input_manifest_dev.json'
    manifest = base.read(manifest_path)
    parent = cal.get('measured_parent', {})
    if (not re.fullmatch('[0-9a-f]{40}', str(cal.get('source_sha', '')))
            or base.sha(manifest_path) != cal.get('dev_manifest_sha256')
            or manifest.get('schema') != 'ugrp.v92_dev_pilot_inputs.v1'
            or manifest.get('execution_source_sha') != cal['source_sha']
            or manifest.get('working_tree_dirty') is not False
            or not re.fullmatch('[0-9a-f]{64}', str(manifest.get('script_sha256', '')))
            or parent.get('status') != 'PARTIAL'
            or not re.fullmatch('[0-9a-f]{64}', str(parent.get('sha256', '')))):
        raise ValueError('DEV_PILOT provenance mismatch')
    cal = copy.deepcopy(cal)
    cal['dev_pilot_provenance'] = {'dev_manifest_sha256': cal['dev_manifest_sha256'],
                                   'dev_script_sha256': manifest['script_sha256'],
                                   'measured_parent': copy.deepcopy(parent), 'source_sha': cal['source_sha']}
    # Structure-only probe through the unchanged v92 loader. Its MEASURED
    # provenance slots carry the DEV hashes above; nothing is invented.
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp)/'structure.json'
        probe.write_text(json.dumps({**cal, 'status': MEASURED_SIM,
                                     'measurement_manifest_sha256': cal['dev_manifest_sha256'],
                                     'assembler_sha256': manifest['script_sha256']}))
        d5.measured_calibration(probe, base.sha(probe), map_id)
    return cal


def admitted_calibration(path, expected_sha, map_id):
    """Provider entry: DEV_PILOT only by exact admitted sha256, else MEASURED_SIM."""
    if expected_sha is not None and expected_sha in dev_pilot_admission()['admitted_calibration_sha256']:
        return dev_pilot_calibration(path, expected_sha, map_id)
    return measured_calibration(path, expected_sha, map_id)


def calibration_for(mode, path, expected_sha, map_id):
    if mode == DEV_PILOT:
        return dev_pilot_calibration(path, expected_sha, map_id)
    if mode != MEASURED_SIM:
        raise ValueError('unknown admission mode')
    return measured_calibration(path, expected_sha, map_id)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def require_promotable(record):
    """Confirmatory/MEASURED_SIM consumers call this first; DEV_PILOT never passes.

    Labels alone are not trusted (REVIEW_363 re-review #2): any record that
    carries a DEV-admitted calibration sha256 anywhere is refused, so a
    relabelled or label-stripped DEV record cannot be promoted either.
    """
    dev = set(dev_pilot_admission().get('admitted_calibration_sha256') or [])
    if dev & set(_strings(record)):
        raise ValueError(NOT_PROMOTABLE)
    if (record.get('admission_mode', MEASURED_SIM) != MEASURED_SIM or record.get('promotable') is False
            or record.get('run_status') == DEV_PILOT_LABELS['run_status']
            or record.get('cohort_role') == DEV_PILOT_LABELS['cohort_role']
            or record.get('measured_sim_evidence') is False):
        raise ValueError(NOT_PROMOTABLE)
    for row in record.get('cases', []):          # multi-case result wrappers
        require_promotable(row)
    if isinstance(record.get('checkpoint'), dict):
        require_promotable(record['checkpoint'])
    return record


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
    if value.get('admission_mode', MEASURED_SIM) == DEV_PILOT:
        dev = dev_pilot_admission()
        if (dev.get('runnable') is not True or value.get('runnable') is not True
                or any(value.get(k) != v for k, v in DEV_PILOT_LABELS.items())):
            raise ValueError(REGISTRY_BLOCK+':DEV_PILOT')
        return
    if registry()['runnable'] is not True or value.get('runnable') is not True:
        raise ValueError(REGISTRY_BLOCK)


def cases(check, map_id=None):
    if check not in CHECKS:
        raise ValueError('v96 supports student P03/carry only')
    rows = copy.deepcopy(previous.cases(check, map_id))
    for row in rows:
        row['sim_cap_s'] = CASE_CAP_S
    return rows


def execution_timing(check):
    cases(check)
    timing = previous.execution_timing(check)
    timing['stabilization']['high_pose'] = pose.record()
    timing['high_checkpoint_policy'] = {'remain_high': True, 'open': False, 'reobserve_min_s': 1.2}
    # look_every_s (0.4) is the inherited carry/hold look cadence. Arm transits
    # (raise/lower) observe own RGB every SAMPLE_S with a frame-age limit.
    timing['observation'] = {'carry_hold_look_every_s': timing.get('look_every_s'),
        'transit_rgb_sample_s': grip.SAMPLE_S, 'transit_max_frame_age_s': grip.MAX_FRAME_AGE_S,
        'transit_max_command_lag_s': grip.MAX_COMMAND_LAG_S}
    timing['case_sim_cap_s'] = CASE_CAP_S
    timing['executor_job_sim_limit_s'] = CASE_CAP_S   # overrides the parent runtime's 120 s
    timing['parent_differences'].append('single low lift/HIGH raise; stay HIGH at intermediate stop/reobserve; lower/open only at final release')
    return timing


def bundle(map_id, check, admission=MEASURED_SIM):
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
    paths = set(value['source_sha256']) | set(source_closure(ROOT, entries)) | {REGISTRY, WORKFLOW, CALIBRATION_CONTRACT, D5_ADMISSION, CAP_DECISION,
        'configs/zone_final_pair_v92_schedule.json.gz',
        'configs/zone_pair_highpose_confirmation_v96.json',
        'experiments/2026-10-03-v92-loaded-schedule/criterion_B_double_prime.json',
        'experiments/2026-10-03-v92-loaded-schedule/assembly/registration.json'}
    value['source_sha256'] = {p: base.sha(ROOT / p) for p in sorted(paths)}
    if admission == DEV_PILOT:
        dev = dev_pilot_admission()
        value.update(DEV_PILOT_LABELS, runnable=dev['runnable'] is True, blocked_on=[],
                     dev_pilot_rule=DEV_PILOT_RULE,
                     dev_pilot_unloaded_motion_fill=copy.deepcopy(dev['unloaded_motion_fill']),
                     calibration_selection='DEV_PILOT: one exact registered sha256 (c0 = 0); non-confirmatory')
    elif admission != MEASURED_SIM:
        raise ValueError('unknown admission mode')
    return value
