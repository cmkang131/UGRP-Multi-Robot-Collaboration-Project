"""P07: read-only E2E planning and evidence admission, never execution.

Only stdlib and the AST source walker are imported. Runtime modules are read as
bytes, not imported. Content digests identify a DRAFT, not a sealed run bundle.
The coordinator must produce a separate registration after the listed gates.
"""
from __future__ import annotations

from collections import Counter
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
import re

from harness.python_source_closure import source_closure

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ugrp.zone_e2e_plan_draft.v1'
AUDIT_MAIN = 'a8094cc14e098a55483f53a3c49bf6a0b116043d'
PLANNING_BASE = 'd17ca4345affef8cf027e121cf1f3197b36c23e0'
DEFAULT_RAW_ROOT = '/Users/changmin/projects/ugrp/outputs'
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
ROBOTS = ('r1', 'r2', 'r3')
CLAIMS_PATH = 'configs/zone_e2e_plan/claims_v1.json'
CATALOG_PATH = 'maps/zones_final/catalog.json'
P01_PATH = 'configs/zone_final_environment_registry_v1.json'
# P03 owns this existing registry. Do not invent a future pin-contract path.
P03_PATH = 'configs/zone_study_integration/pose_providers.json'
CLAIM_IDS = tuple(f'S{i:02}' for i in range(1, 16)) + (
    'PR292_ACCEPTANCE', 'PR293_CONFIRMATION', 'M1_FINAL', 'M2_FINAL',
    'C5A', 'C5B', 'C6', 'C7')
ENTRY_PATHS = (
    'scripts/run_zone_study_integration.py', 'scripts/run_zone_study_sensors.py',
    'harness/zone_study_llm_transport.py', 'harness/vision_pose_source.py',
    'harness/wrist_zone_skill_v9.py', 'harness/owncam_memory_v3.py',
    'sim/render_profile.py', 'sim/zone_eval_top.py',
)
ASSET_PATHS = (
    CATALOG_PATH, CLAIMS_PATH, 'configs/simulation_workflows.json',
    'requirements-sim.txt', 'requirements-reference-act.txt',
    'configs/zone_study_integration/pose_providers.json',
    'configs/zone_study_integration/llm_driver.json', 'configs/vision_loc_worker.json',
    'configs/model_artifacts.json', 'configs/masterpi_v3_scenes.json',
    'configs/zone_study_integration/pair_dev_DRAFT.json',
    'configs/zone_study_integration/multiturn_dev_DRAFT.json',
    'experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md',
    'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json',
    'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_dr_fit_cal1.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_pair_fit.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_general_fit.json',
)
COORDINATOR_GATES = (
    'DRAFT_ONLY: 계획 생성은 실행 승인이 아니다; 이 도구에는 execute가 없다',
    'FINAL_FREEZE: 합성·독립 검토 후 새 실행 source SHA와 봉인 파일을 별도 커밋',
    'BUNDLE_RESERVATION: main/열린 PR 최댓값 확인 후 새 번호 예약; #292 v83/2.16.0 사용 금지',
    'COST_APPROVAL: 실제 모델/실효 모델·토큰 상한·비용 승인 및 새 예산 DB는 코디네이터 작업',
    'HOST_ADMISSION: 실행 직전 소유 잠금·10 GiB·부하·raw 경로를 재확인; ENOSPC=HOST_ERROR',
    'STANDARD_ENTRY: 최종 후보를 표준 sim_cli workflow에 등록하고 그 경로에서만 실행',
    'RESULT_DELIVERY: 실패/미도달 포함 raw·원장·평가와 TensorBoard 로딩/영상/화면 대조',
)


class PlanError(ValueError):
    """Invalid or stale draft, never a request to fall back to runtime defaults."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def local_file(root, relative):
    if not isinstance(relative, str):
        raise PlanError('file path must be a repository-relative string')
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or str(p) != relative:
        raise PlanError(f'nonlocal file: {relative}')
    path = Path(root) / relative
    if not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
        raise PlanError(f'missing/nonlocal file: {relative}')
    return path


def file_sha(root, path):
    return hashlib.sha256(local_file(root, path).read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise PlanError(f'duplicate JSON key: {key}')
            out[key] = value
        return out
    def invalid(value):
        raise PlanError(f'non-finite JSON value: {value}')
    try:
        return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f'cannot read JSON: {path}: {exc}') from exc


def pin(root, path):
    return {'path': path, 'sha256': file_sha(root, path)}


def _literal(root, path, name):
    """Read a published literal without importing a runtime module."""
    for node in ast.parse(local_file(root, path).read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise PlanError(f'missing static declaration: {path}:{name}')


def _vision_inputs(root):
    base = Path(root) / 'experiments/2026-09-26-vision-loc'
    prereg_path = 'experiments/2026-09-26-vision-loc/prereg_v3.json'
    student = read_json(local_file(root, prereg_path))['student']
    want = dict(student['frozen_files_sha256'])
    want['selected_config_v3.json'] = student['config']['sha256']
    selected = _literal(root, 'harness/vision_loc_protocol.py', 'FROZEN_FILES') + ('selected_config_v3.json',)
    files = {prereg_path: file_sha(root, prereg_path)}
    for name in selected:
        path = (base / name).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise PlanError('nonlocal VIS3 input')
        relative = path.relative_to(Path(root).resolve()).as_posix()
        actual = file_sha(root, relative)
        if actual != want[name]:
            raise PlanError(f'VIS3 frozen source/calibration mismatch: {relative}')
        files[relative] = actual
    return files


def _enum(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        raise PlanError(f'unknown {name}: {value!r}; expected {choices}')


def _options(options):
    keys = {'plan_id', 'raw_root', 'render_profile', 'memory', 'ultrasonic_front'}
    if not isinstance(options, dict) or set(options) != keys:
        raise PlanError('missing/unknown options (no implicit defaults in a saved draft)')
    if not isinstance(options['plan_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{2,79}', options['plan_id']):
        raise PlanError('invalid plan_id')
    raw = options['raw_root']
    if not isinstance(raw, str) or not Path(raw).is_absolute() or str(Path(raw)) != raw or '..' in Path(raw).parts:
        raise PlanError('raw_root must be an explicit canonical absolute path')
    _enum(options['render_profile'], ('shadows_v1', 'noshadow_v1', 'noshadow_bright_v1', 'floor_light_v1'), 'render profile')
    _enum(options['memory'], ('off', 'owncam_memory_v3'), 'memory')
    _enum(options['ultrasonic_front'], ('off', 'on_v1'), 'sensor')
    return dict(options)


def default_options(plan_id, *, raw_root=DEFAULT_RAW_ROOT, render_profile='shadows_v1',
                    memory='off', ultrasonic_front='off'):
    return _options(dict(plan_id=plan_id, raw_root=str(raw_root), render_profile=render_profile,
                         memory=memory, ultrasonic_front=ultrasonic_front))


def _scenarios(root):
    catalog = read_json(local_file(root, CATALOG_PATH))
    if catalog['wall_profile'] != 'walls_v3' or type(catalog['tags']) is not int or catalog['tags'] != 0:
        raise PlanError('final-map catalog must be walls_v3/tag0')
    scenarios = {}
    for sid, spec in sorted(catalog['scenarios'].items()):
        scenario = read_json(local_file(root, spec['file']))
        mid = spec['map_id']
        if mid not in catalog['maps']:
            raise PlanError('unknown map')
        m = catalog['maps'][mid]
        static = read_json(local_file(root, m['file']))
        if (file_sha(root, spec['file']) != spec['file_sha256']
                or file_sha(root, m['file']) != m['file_sha256']
                or scenario['scenario_id'] != sid or scenario['map_id'] != mid
                or scenario.get('landmark_detail') != 'none'
                or scenario['eval']['setup']['map_file_sha256'] != m['file_sha256']
                or static['map_id'] != mid or digest(static) != m['static_map_sha256']):
            raise PlanError(f'source/map/scenario mismatch: {sid}')
        scenarios[sid] = {'scenario': pin(root, spec['file']), 'map_id': mid,
                          'map': pin(root, m['file']), 'static_map_sha256': digest(static),
                          'declared_seeds': scenario['seeds']}
    if len(scenarios) != 6 or {s[:2] for s in scenarios} != {f's{i}' for i in range(1, 7)}:
        raise PlanError('the full milestone requires all six original v2 scenarios')
    return catalog, scenarios


def _configuration(root, options):
    worker = read_json(local_file(root, 'configs/vision_loc_worker.json'))
    profiles = read_json(local_file(root, 'configs/zone_study_integration/llm_driver.json'))
    llm = profiles['driver_profiles']['main_study_gemini_v1']
    return {
        'robot_model': 'masterpi_v3', 'wall_profile': 'walls_v3', 'tags': 0,
        'render_profile': options['render_profile'],
        'camera': {'profile': 'native_robot_cam_wrist_fisheye', 'geometry_fov': 'unchanged',
                   'calibration': 'pending_p03_final_v3',
                   'legacy_reference': pin(root, 'experiments/2026-09-26-vision-loc/calibration_train.json')},
        'pose_provider': {'id': 'vision_zero_tag_v2', 'worker': pin(root, 'configs/vision_loc_worker.json'),
                          'model': worker['model'], 'motion_calibration': 'pending_p03_final_v3',
                          'dock_prior': 'own_dock_once_no_gt_reset',
                          'delay': {'wrapper_sim_s': 0.16, 'worker_sim_s': 0.0, 'effective_sim_s': 0.16}},
        'memory': options['memory'], 'sensors': {'ultrasonic_front': options['ultrasonic_front']},
        'pair_policy': {'id': 'b-v6h1', 'adoption': 'pending_pr292_acceptance_and_review',
                        'roles': 'r1_end_neg_r2_end_pos_r3_solo', 'status_channel': 'same_all_four_conditions'},
        'contact_profile': 'cargo_noslip_v1', 'weld': 'off',
        'timing': {'mode': 'sync_sim', 'frame_period_s': 0.2, 'executor_tick_s': 0.1},
        'llm': {'driver_profile': 'main_study_gemini_v1', 'requested_model': llm['model'],
                'effective_model': 'unmeasured_requires_coordinator_preflight',
                'speech_cap_profile': 'main_pilot_10_30',
                'speech_caps': profiles['speech_cap_profiles']['main_pilot_10_30'],
                'call_caps': {'logical_per_robot': 30, 'logical_per_trial': 90,
                              'http_per_robot': 30, 'http_per_trial': 90},
                'call_policy': {'min_interval_s': 2.0, 'max_outstanding_per_actor': 1,
                                'idle_reask_s': 10.0, 'busy_reask_s': 60.0,
                                'observe_period_s': 1.0, 'trigger_on_message': True,
                                'max_retries': 0, 'max_calls_per_actor': 30,
                                'max_http_attempts_per_actor': 30, 'max_attempts_total': 90},
                'budget': {'status': 'unapproved', 'token_cap': 'pending_coordinator',
                           'ledger': 'new_database_after_approval', 'unknown_usage': 'retain_and_reconcile'},
                'min_request_interval_wall_s': llm['min_request_interval_s']},
        'sim_cost': {'profile': 'zone_sim_cost.v1', 'scale': 1.0, 'provisional': True,
                     'source': pin(root, 'harness/zone_sim_cost.py')},
        'evaluation': {'referee': 'zone_study_referee.v2', 'top_camera': 'zone_eval_top_v2',
                       'boundary': 'eval_only', 'false_success_required': 0,
                       'failures': 'all_failures_unreached_and_HOST_ERROR_remain_in_denominator'},
        'environment': {'runtime_versions': 'pending_coordinator_final_environment',
                        'python': '3.12', 'omp_blas_threads': 1},
    }


def _v3_maps(root):
    catalog = read_json(local_file(root, 'configs/masterpi_v3_scenes.json'))
    paths = []
    for mid, spec in catalog['scenes'].items():
        static = read_json(local_file(root, spec['map_file']))
        if (file_sha(root, spec['map_file']) != spec['file_sha256']
                or digest(static) != spec['static_map_sha256'] or static['map_id'] != mid
                or static.get('robot_model') != 'masterpi_v3'
                or static.get('wall_profile', {}).get('id') != 'walls_v3'
                or 'landmarks' in static):
            raise PlanError(f'v3 source/map mismatch: {mid}')
        paths.append(spec['map_file'])
    return paths


def _claims(root):
    rows = read_json(local_file(root, CLAIMS_PATH))
    if not isinstance(rows, dict) or set(rows) != set(CLAIM_IDS):
        raise PlanError('required claim missing or unknown claim')
    keys = {'sources', 'tests', 'existing_results', 'conditions', 'unmeasured', 'execution_approval', 'completed'}
    for cid, row in rows.items():
        if (not isinstance(row, dict) or set(row) != keys or row['completed'] is not False
                or row['execution_approval'] is not None):
            raise PlanError(f'false completion/approval or malformed claim: {cid}')
        for field in ('sources', 'tests', 'existing_results', 'conditions', 'unmeasured'):
            if not isinstance(row[field], list) or not row[field] or any(not isinstance(x, str) or not x.strip() for x in row[field]):
                raise PlanError(f'claim {cid} requires explicit {field}')
    return rows


def _cohorts(scenarios):
    ids = sorted(scenarios)
    dev = [{'scenario_id': 'p02_cyan1_beam1_dev_pending', 'map_id': 'zone_wide_door_geometry_v3',
            'seed': 17001, 'scenario_binding': 'pending_P02_new_final_v3_scenario'}]
    smoke = [{'scenario_id': sid, 'map_id': scenarios[sid]['map_id'], 'seed': 17100 + i,
              'scenario_binding': 'new_smoke_seed_requires_new_scenario_version'} for i, sid in enumerate(ids)]
    pilot = [{'scenario_id': sid, 'map_id': scenarios[sid]['map_id'], 'seed': seed,
              'scenario_binding': 'original_v2_external_pilot'}
             for sid in ids for seed in scenarios[sid]['declared_seeds']]
    definitions = [
        ('C5a', 'cyan_beam_dev_fixture_4', 'dev_connection_only', 'fixture_no_llm', dev, ['C4']),
        ('C5b', 'cyan_beam_dev_llm_4', 'dev_korean_connection_only', 'live_llm_proposed', dev, ['C5a']),
        ('C6', 'formal_six_scenario_no_llm_24', 'milestone_224_smoke_only', 'fixture_no_llm', smoke, ['C5b', 'P09_ALL_CAPABILITIES']),
        ('C7', 'external_pilot_72', 'external_pilot_excluded_from_confirmatory', 'live_llm_proposed', pilot, ['C6']),
    ]
    rows = []
    for index, (step, cid, scope, actor, blocks, dependencies) in enumerate(definitions):
        blocks = [dict(b) for b in blocks]
        rng = random.Random(20260928 + index)
        rng.shuffle(blocks)
        trials = []
        for block in blocks:
            order = list(CONDITIONS)
            rng.shuffle(order)
            for condition in order:
                trials.append({**block, 'condition': condition,
                               'leader': ROBOTS[block['seed'] % 3] if condition == 'leader_ko' else 'not_applicable',
                               'sim_cap_s': 1800})
        rows.append({'step': step, 'cohort_id': cid, 'claim_scope': scope, 'actor': actor,
                     'depends_on': dependencies, 'conditions': list(CONDITIONS), 'trials': trials,
                     'planned_runs': len(trials), 'completed_runs': 0, 'completed_claims': [],
                     'total_sim_cap_s': 1800 * len(trials)})
    if [c['planned_runs'] for c in rows] != [4, 4, 24, 72]:
        raise PlanError('cohort denominator must be 4/4/24/72')
    return rows


def _prerequisites():
    return [
        {'step': 'C0', 'depends_on': [], 'segments': [], 'total_sim_cap_s': 0},
        {'step': 'C1', 'depends_on': ['C0'], 'segments': [
            {'name': 'map_reset', 'runs': 3, 'cap_s': 30},
            {'name': 'approach_grasp_relocalize', 'runs': 3, 'cap_s': 300},
            {'name': 'invalid_frame_one_sided_grasp', 'runs': 2, 'cap_s': 60}], 'total_sim_cap_s': 1110},
        {'step': 'C2', 'depends_on': ['C1', 'PR292_INDEPENDENT_REVIEW'], 'segments': [
            {'name': 'registered_acceptance', 'runs': 5, 'cap_s': 180},
            {'name': 'final_door_chain', 'runs': 3, 'cap_s': 300},
            {'name': 'destination_leg', 'runs': 3, 'cap_s': 60}], 'total_sim_cap_s': 1980},
        {'step': 'C3', 'depends_on': ['C2', 'PR293_PREREG_REVIEW'], 'segments': [
            {'name': 'd1_stalled', 'runs': 30, 'cap_s': 120},
            {'name': 'd1_normal', 'runs': 60, 'cap_s': 120},
            {'name': 'abort_flow', 'runs': 3, 'cap_s': 120}], 'total_sim_cap_s': 11160},
        {'step': 'C4', 'depends_on': ['C2', 'C3'], 'segments': [
            {'name': 'M1_final', 'runs': 6, 'cap_s': 900},
            {'name': 'M2_final', 'runs': 6, 'cap_s': 900}], 'total_sim_cap_s': 10800},
    ]


def _support_contract(root, path, owner, configuration, map_ids):
    if not (Path(root) / path).exists():
        return {'owner': owner, 'status': 'unavailable', 'expected_path': path,
                'admitted_combinations': []}
    data = read_json(local_file(root, path))
    expected_schema = {'P01': 'ugrp.zone_final_environment_registry.v1',
                       'P03': 'ugrp.zone_study_pose_providers.v1'}[owner]
    if data.get('schema') != expected_schema:
        raise PlanError(f'{owner} unknown support schema')
    references = {}
    if owner == 'P01':
        if data.get('status') != 'DRAFT_UNSEALED':
            raise PlanError('P01 unexpected registration status')
        for catalog in data['catalogs'].values():
            actual = file_sha(root, catalog['file'])
            if actual != catalog['sha256']:
                raise PlanError('P01 catalog hash mismatch')
            references[catalog['file']] = actual
    else:
        provider = data['providers'][configuration['pose_provider']['id']]
        if provider['uses_landmark_tags'] is not False or provider['research_result'] is not False:
            raise PlanError('P03 tag/research boundary mismatch')
        for name in (*provider['source_files'], provider['calibration']):
            references[name] = file_sha(root, name)
    rows = []
    for map_id in sorted(map_ids):
        reasons = []
        if owner == 'P01':
            entry = data['maps'].get(map_id)
            if entry is None:
                reasons.append('map not registered')
            else:
                if entry['robot_model'] != configuration['robot_model']:
                    reasons.append('map robot_model differs from proposed masterpi_v3')
                if entry['wall_profile'] != configuration['wall_profile']:
                    reasons.append('wall profile mismatch')
                provider = entry['providers'].get(configuration['pose_provider']['id'])
                if provider is None or provider.get('supported') is not True:
                    reasons.append('provider/calibration unsupported')
                else:
                    actual = file_sha(root, provider['calibration'])
                    if actual != provider['calibration_sha256']:
                        raise PlanError('P01 calibration hash mismatch')
                    references[provider['calibration']] = actual
                    if provider['calibration'] != configuration['pose_provider']['motion_calibration']:
                        reasons.append('motion calibration differs from proposed final calibration')
        else:
            if map_id not in provider['maps']:
                reasons.append('map outside provider allow-list')
            if provider['calibration'] != configuration['pose_provider']['motion_calibration']:
                reasons.append('motion calibration differs from proposed final calibration')
        # These legacy contracts do not certify the full render/model/camera tuple.
        # Even map membership and valid bytes cannot qualify that missing binding.
        reasons.append('final v3 render/model/camera tuple requires P01/P03 integration review')
        rows.append({'map_id': map_id, 'supported_for_proposal': False, 'reasons': reasons})
    return {'owner': owner, 'status': 'blocked', 'file': pin(root, path),
            'reference_files_sha256': references, 'combinations': rows,
            'admitted_combinations': []}


def build_draft(options, *, root=ROOT):
    options = _options(options)
    catalog, scenarios = _scenarios(root)
    claims = _claims(root)
    runtime_entries = _literal(root, 'scripts/run_zone_study_integration.py', 'RUNTIME_ENTRY_POINTS')
    runtime_assets = _literal(root, 'scripts/run_zone_study_integration.py', 'RUNTIME_ASSETS')
    sensor_modules = (_literal(root, 'harness/ultrasonic_input.py', 'RUNTIME_MODULES')
                      if options['ultrasonic_front'] == 'on_v1' else ())
    paths = set(source_closure(Path(root), (*ENTRY_PATHS, *runtime_entries), modules=sensor_modules))
    paths.update((*ASSET_PATHS, *runtime_assets))
    paths.update(_vision_inputs(root))
    paths.update(v['file'] for v in catalog['maps'].values())
    paths.update(v['file'] for v in catalog['scenarios'].values())
    paths.update(_v3_maps(root))
    configuration = _configuration(root, options)
    map_ids = {s['map_id'] for s in scenarios.values()} | {
        'zone_wide_door_geometry_v3', 'zone_wide_door_geometry_v3_dock_v1'}
    contracts = {owner: _support_contract(root, path, owner, configuration, map_ids)
                 for owner, path in (('P01', P01_PATH), ('P03', P03_PATH))}
    for contract in contracts.values():
        if 'file' in contract:
            paths.add(contract['file']['path'])
            paths.update(contract['reference_files_sha256'])
    draft = {
        'schema': SCHEMA, 'status': 'DRAFT', 'runnable': False, 'physical_ready': False,
        'audit_main_sha': AUDIT_MAIN, 'planning_base_sha': PLANNING_BASE,
        'reference_pr_heads': {
            '285': {'sha': '76e0f9ce793f8cbbff2349b2be2bbaa359250a42', 'scope': 'feature_exploration_not_main'},
            '292': {'sha': '3afc61b00f2c127ac3fbe2be5e7bb57da989b15a', 'scope': 'draft_unsealed_acceptance_missing'},
            '293': {'sha': 'd86cc82eedbe0c6693eaf808c54ce43387723f1d', 'scope': 'draft_no_confirmatory_cohort'},
            '294': {'sha': '9a63140edfaaf69f2ca92466384194d989e33c03', 'scope': 'merged_into_285_feature_only'},
        },
        'execution_source_sha': None, 'execution_bundle_id': None, 'bundle_sha256': None,
        'registered': None, 'execution_approval': None, 'cost_approval': None,
        'options': options, 'configuration': configuration, 'support_contracts': contracts,
        'runtime_files_sha256': {p: file_sha(root, p) for p in sorted(paths)},
        'planner_files_sha256': {p: file_sha(root, p) for p in (
            'harness/zone_e2e_manifest.py', 'harness/python_source_closure.py',
            'scripts/plan_zone_e2e.py', CLAIMS_PATH)},
        'evidence_files_sha256': {p: file_sha(root, p) for p in sorted({
            p for row in claims.values() for kind in ('sources', 'tests', 'existing_results')
            for p in row[kind] if not p.startswith('https://')})},
        'scenarios': scenarios, 'claims': claims, 'prerequisites': _prerequisites(),
        'cohorts': _cohorts(scenarios), 'coordinator_checklist': list(COORDINATOR_GATES),
    }
    draft['draft_content_sha256'] = digest(draft)
    return draft


def _different(a, b, path='manifest'):
    """First precise mismatch, with bool/int and missing/null distinguished."""
    if type(a) is not type(b):
        return path
    if isinstance(a, dict):
        if set(a) != set(b):
            return path + '.keys'
        for key in b:
            mismatch = _different(a[key], b[key], f'{path}.{key}')
            if mismatch:
                return mismatch
    elif isinstance(a, list):
        if len(a) != len(b):
            return path + '.length'
        for i, (left, right) in enumerate(zip(a, b)):
            mismatch = _different(left, right, f'{path}[{i}]')
            if mismatch:
                return mismatch
    elif a != b:
        return path
    return None


def _raw_destinations(draft, *, primary_outputs):
    base = Path(draft['options']['raw_root'])
    primary = Path(primary_outputs)
    if base != primary or base.resolve() != primary.resolve():
        raise PlanError('raw_root must equal the configured primary checkout outputs root')
    target = base / draft['options']['plan_id']
    # lexists semantics: dangling symlinks and even empty previous directories
    # are occupied. No directories, reservation files, or DBs are created here.
    if target.exists() or target.is_symlink():
        raise PlanError('raw destination already exists; previous raw reuse/write conflict')
    ancestor = base
    while not ancestor.exists():
        if ancestor.is_symlink():
            raise PlanError('raw parent has a dangling symlink')
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise PlanError('raw parent is not a directory')
    destinations = []
    for step in draft['prerequisites']:
        for segment in step['segments']:
            for i in range(segment['runs']):
                destinations.append(str(target / step['step'] / f'{segment["name"]}-{i + 1:03}'))
    for cohort in draft['cohorts']:
        for index, trial in enumerate(cohort['trials'], 1):
            destinations.append(str(target / cohort['cohort_id'] / f'{index:03}-{trial["scenario_id"]}-s{trial["seed"]}-{trial["condition"]}'))
    if len(destinations) != len(set(destinations)):
        raise PlanError('duplicate raw destinations/write conflict')
    return destinations


def check_draft(draft, *, root=ROOT, primary_outputs=DEFAULT_RAW_ROOT):
    """Structural admission only. No claim can become physical_ready here.

    Re-derive every row/pin/enum from the versioned proposal. Hand-edited nulls,
    reduced denominators, resealed source/map changes and false completion all
    fail. Change a proposal in a reviewed new version, then regenerate it.
    """
    if not isinstance(draft, dict) or 'options' not in draft:
        raise PlanError('manifest/options required')
    # Reject obvious forged completion/invalid inputs before walking hundreds
    # of source files. The full comparison below still checks every field.
    fixed = {'schema': SCHEMA, 'status': 'DRAFT', 'runnable': False, 'physical_ready': False,
             'audit_main_sha': AUDIT_MAIN, 'planning_base_sha': PLANNING_BASE,
             'execution_source_sha': None, 'execution_bundle_id': None, 'bundle_sha256': None,
             'registered': None, 'execution_approval': None, 'cost_approval': None}
    options = _options(draft['options'])
    for key, value in fixed.items():
        if key not in draft or _different(draft[key], value):
            raise PlanError(f'draft/source/approval mismatch at manifest.{key}')
    _, scenarios = _scenarios(root)
    for key, value in (('claims', _claims(root)), ('configuration', _configuration(root, options)),
                       ('scenarios', scenarios), ('cohorts', _cohorts(scenarios)),
                       ('prerequisites', _prerequisites())):
        difference = _different(draft.get(key), value, f'manifest.{key}')
        if difference:
            raise PlanError(f'draft/source/map/claim mismatch at {difference}')
    expected = build_draft(draft['options'], root=root)
    difference = _different(draft, expected)
    if difference:
        raise PlanError(f'draft/source/map/claim mismatch at {difference}; regenerate after review')
    destinations = _raw_destinations(draft, primary_outputs=primary_outputs)
    unmet = list(COORDINATOR_GATES)
    for name, contract in draft['support_contracts'].items():
        unmet.append(f'{name}_SUPPORTED_COMBINATION: {contract["status"]}; v3/map/render/provider/model/calibration not admitted')
    unmet += [f'{cid}: ' + '; '.join(draft['claims'][cid]['unmeasured']) for cid in CLAIM_IDS]
    unmet.extend((
        'P02_SCENARIO: cyan1+long_beam1/r1-r2 pair/r3 solo 최종 v3 dev 시나리오 합성·pin 필요; v2 명세 승계 금지',
        'SMOKE_SEEDS: C6 신규 seed는 기존 v2에 없음; 원본 보존 후 새 버전 시나리오 등록 필요',
        'P09_ALL_CAPABILITIES: C6/C7는 6종 물건·역할·경로·숨은 사건 전체 검증 필요',
        'FINAL_CALIBRATION: v3 카메라/명령 보정 미선택; legacy 보정의 암묵적 승계 금지',
    ))
    if draft['options']['memory'] != 'off':
        unmet.append('MEMORY_ON: 최종 무표식 환경에서 별도 검증 필요; OFF와 별도 cohort')
    if draft['options']['ultrasonic_front'] != 'off':
        unmet.append('SENSOR_ON: 네 조건 공통 새 bundle/입력 검증 필요; OFF와 별도 cohort; 현재 제어기 판독 없음')
    if draft['options']['render_profile'] != 'shadows_v1':
        unmet.append('RENDER_VARIANT: 해당 바닥/조명과 모델/보정 조합의 P01/P03 검증 필요')
    order = [{'step': s['step'], 'depends_on': s['depends_on'],
              'segments': s['segments'], 'sim_cap_s': s['total_sim_cap_s']} for s in draft['prerequisites']]
    leaders = {}
    for c in draft['cohorts']:
        order.append({'step': c['step'], 'cohort_id': c['cohort_id'], 'claim_scope': c['claim_scope'],
                      'actor': c['actor'], 'depends_on': c['depends_on'], 'trials': c['trials'],
                      'sim_cap_s': c['total_sim_cap_s']})
        counts = Counter(t['leader'] for t in c['trials'] if t['condition'] == 'leader_ko')
        leaders[c['cohort_id']] = {r: counts[r] for r in ROBOTS}
        if c['step'] in ('C6', 'C7') and len(set(counts.values())) != 1:
            raise PlanError('formal cohort leaders must be balanced')
    unmet.append('DEV_LEADER_SCOPE: C5a/C5b는 각각 1 seed/leader 1종; 지휘자 균형·일반화 claim 없음')
    return {'execution_order': order, 'total_sim_cap_s': sum(s['sim_cap_s'] for s in order),
            'leader_balance': leaders, 'raw_destinations': destinations, 'unmet_conditions': unmet}
