"""Consumer contracts for the frozen real producer + registered schema.

Public format fixtures are NOT admitted confirmatory data. All cohort/host
mutations below are synthetic. No simulator or blinded raw access.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('recorder_builders', Path(__file__).with_name('test_classify_review_299.py'))
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
cp = base.cp
FIXTURES = Path(__file__).parent / 'fixtures/v6h_recorder_v4c6b'


def public_record():
    golden = json.loads((FIXTURES / 'provenance.json').read_text())
    data = json.loads((FIXTURES / 'case_01.json').read_text())
    return data, {'manifest': golden['manifest'], 'case': data['case']}


def adjudicate(data, context):
    return cp.adjudicate_attempt(data['row'], data['result'], data['trace'], recorder_context=context)


@pytest.mark.parametrize('damage', ['producer', 'source', 'row', 'case', 'contact_disabled', 'registration_without_seal'])
def test_recorder_format_incompatibility_is_unclassifiable_not_task_fail(damage):
    data, context = public_record()
    if damage == 'producer':
        next(f for f in context['manifest']['source_fingerprint']['files'] if f['path'] == cp.rv.RECORDER_PATH)['sha256'] = 'f' * 64
    elif damage == 'source':
        context['manifest']['source_sha'] = None
    elif damage == 'row':
        data['result']['row']['seed'] += 1
    elif damage == 'case':
        data['case']['seed'] += 1
    elif damage == 'contact_disabled':
        data['case']['contact_track'] = False
    else:
        data['case']['registration_run_id'] = 'unaudited'
    out = adjudicate(data, context)
    assert out['class'] is None and out['state'] == 'INVALID'
    assert out['classification_status'] == 'UNCLASSIFIABLE'
    assert out['unclassified_reason'] == 'UNCLASSIFIABLE_RECORDER_FORMAT'
    selected = cp.classify_attempt_sequence([out])
    assert selected['classification_status'] == 'UNCLASSIFIABLE' and selected['class'] is None


@pytest.mark.parametrize('stage', ['before_handover', 'cleanup'])
def test_real_host_error_field_and_absent_termination_are_not_retroactively_required(stage):
    data, context = public_record()
    row, result, trace = data['row'], data['result'], data['trace']
    row.update(category='HOST_ERROR:OSError', host_error='ENOSPC')
    result['host_error'] = {'classification': 'HOST_ERROR', 'type': 'OSError', 'enospc': True}
    if stage == 'before_handover':
        trace[:] = [s for s in trace if s['t'] < 10]
        for leg in row['chain']['legs']:
            leg.clear()
        row['chain']['legs'] = [{'leg': k, 'recorded': False, 'start_sim_s': None, 'end_sim_s': None} for k in range(8)]
        row['stop_sim_s'] = None
        result.pop('termination')
        result['chain_raw'] = {}
        result.pop('gt_at_stop', None)
        result.pop('gt_at_end', None)
    # Cleanup can leave STUDY_LAYER_DONE in termination in the real except path.
    result['row'] = copy.deepcopy(row)
    out = adjudicate(data, context)
    assert out['host_error'] and out['class'] is None and not out['confirmed_task_failure'], out
    assert out['state'] == 'HOST_SAFE' and out['evidence_valid'], out
    selected = cp.classify_attempt_sequence([out])
    assert selected['class'] is None and selected['unclassified_reason']


def test_recorder_context_does_not_hide_injected_coverage_contradiction():
    data, context = public_record()
    data['result']['wall_contact']['coverage'] = {'start_sim_s': -100., 'end_sim_s': 1000.,
        'sample_period_s': .05, 'max_gap_s': .05, 'sample_count': 66}
    out = adjudicate(data, context)
    assert out['state'] == 'INVALID' and out['class'] is None


@pytest.mark.parametrize('missing', ['endpoint', 'teacher', 'entry'])
def test_real_producer_witness_deletion_cannot_restore_pass(missing):
    data, context = public_record()
    if missing == 'endpoint':
        del data['result']['chain_raw']['r1']['leg_end']['1']
    elif missing == 'teacher':
        del data['result']['teacher']['gt_after_lift']
    else:
        del data['result']['gt_at_entry']
    out = adjudicate(data, context)
    assert out['state'] == 'INVALID' and out['class'] is None


def test_positive_contact_steps_are_not_total_samples_and_must_match_episodes():
    data, context = public_record()
    data['result']['wall_contact']['steps'] = {'beam': 500}
    out = adjudicate(data, context)
    assert out['state'] == 'INVALID' and out['class'] is None


def test_positive_registered_contact_control_keeps_real_steps_semantics():
    data, context = public_record()
    # Contact before submit is outside row's stage summary but inside safety.
    data['result']['wall_contact'].update(steps={'beam': 3}, episodes=[
        {'who': 'beam', 'steps': 3, 't_first': 1.5, 't_last': 1.501, 'max_pen_m': .004}])
    out = adjudicate(data, context)
    assert out['class'] == 'PASS_CONTACT_RECOVERED' and out['evidence_valid'], out
    assert out['recorder_contract']['wall_contact']['sample_count'] == 'not_recorded'


@pytest.mark.parametrize('changed', ['placement', 'seed'])
def test_retry_must_keep_same_placement_and_seed(changed):
    row, result, trace = base.record()
    row.update(category='HOST_ERROR:ENOSPC', host_error='ENOSPC')
    result['termination']['outcome'] = 'HOST_ERROR'
    base.record_receipt(row, result, trace)
    original = cp.adjudicate_attempt(row, result, trace)
    r, s, t = base.record()
    retry = cp.adjudicate_attempt(r, s, t)
    retry[changed] = 'C02' if changed == 'placement' else 943
    selected = cp.classify_attempt_sequence([original, retry])
    assert selected['state'] == 'INVALID' and selected['class'] is None
    assert 'RETRY_PLACEMENT_SEED_MISMATCH' in selected['sequence_issues']
    retry.update(state='HARD', hard_limit_chain={'violated': True}, **{'class': 'FAIL_HARD_LIMIT'})
    assert cp.classify_attempt_sequence([original, retry])['class'] == 'FAIL_HARD_LIMIT'


@pytest.mark.parametrize('kind', ['lift_m', 'jaws', 'tilt_deg', 'timestamp'])
def test_actual_endpoint_source_to_derived_mapping(kind):
    data, context = public_record()
    leg = data['row']['chain']['legs'][1]
    if kind == 'timestamp':
        leg['end_sim_s'] += .001
    elif kind == 'jaws':
        leg[kind]['r1'] = [False, False]
    else:
        leg[kind] = 0.
    data['result']['row'] = copy.deepcopy(data['row'])
    out = adjudicate(data, context)
    assert out['state'] == 'INVALID' and out['class'] is None, out
    assert any('contradiction' in s for s in out['hard_limit_chain']['evidence_issues'])


def registered_fixture(tmp_path):
    """Builder's actual schema; values synthetic except the public worker spec.

    The registered driver emits one selected run/manifest per invocation.
    This fixture checks that its 71 absent slots stay in the admitted inventory.
    """
    data, context = public_record()
    placements, runs, specs = [], [], []
    for i in range(1, 61):
        p = {'name': f'C{i:02d}', 'x': 1., 'y': 0., 'yaw_deg': 0., 'prior': 'hR2_01', 'sheet': 'coarse'}
        placements.append(p)
        for seed in ((941, 943) if i <= 12 else (941,)):
            rid = f'v6h-{p["name"]}-s{seed}-bv6h1'
            runs.append({'id': rid, 'seed': seed, 'placement': p, 'pair_policy': 'b-v6h1', 'primary': seed == 941})
            case = copy.deepcopy(data['case'])
            case.pop('labels')
            case.update(case_id=rid, cell=p['name'], seed=seed, registration_run_id=rid, beam_xyyaw=[1., 0., 0.])
            specs.append(case)
    placefile = tmp_path / 'placements.json'
    base.write_json(placefile, placements)
    plan = {'schema': cp.rv.REGISTERED_SCHEMA, 'sealed': True, 'status': 'REGISTERED', 'registration_revision': 'v6h',
            'execution_source_sha': context['manifest']['source_sha'], 'execution_bundle_id': 'zone-pair-v83-carry-door-gain',
            'execution_authorization': None, 'registration_sha256': None,
            'v6_contract': {'source_sha256': {cp.rv.RECORDER_PATH: cp.rv.RECORDER_SHA256}},
            'placements': {'path': str(placefile), 'sha256': cp.sha256(placefile)},
            'confirmatory_plan': {'primary_seed': 941, 'sensitivity_seed': 943, 'sensitivity_n': 12,
                'default_A': {'pass_at_least': 48, 'n_placements': 60},
                'operation': {'chain_stop_leg': 1, 'policy': 'b-v6h1', 'pf_track': True, 'contact_track': True, 'enospc': 'HOST_ERROR'}},
            'runs': runs, 'cases': specs}
    plan['registration_sha256'] = cp.value_hash({k: v for k, v in plan.items() if k not in ('execution_authorization', 'registration_sha256')})
    planfile = tmp_path / 'registered.json'
    base.write_json(planfile, plan)
    seal = cp.load_sealed_manifest(planfile, cp.sha256(planfile))
    case = copy.deepcopy(specs[0])
    receipt = {'registration_sha256': plan['registration_sha256'], 'run_id': case['registration_run_id'],
               'expected_source_sha': plan['execution_source_sha']}
    case['registration'] = receipt
    manifest = {'state': 'completed', 'source_changed': False, 'registration': receipt,
                'source': {'source_sha': plan['execution_source_sha'], 'execution_tree': context['manifest']['source_fingerprint']},
                'cases': 1, 'cases_sha256': cp.value_hash([case])}
    raw = tmp_path / 'raw'
    raw.mkdir()
    base.write_json(raw / 'manifest.json', manifest)
    base.write_json(raw / 'plan.json', {'labels': data['case']['labels'], 'cases': [case]})
    row = data['row']
    row.update(case_id=case['case_id'], cell=case['cell'], seed=case['seed'])
    data['result'].update(case_id=case['case_id'], cell=case['cell'], seed=case['seed'], row=copy.deepcopy(row))
    directory = cp.ca.dra.case_dir(raw, case['case_id'])
    (directory / 'eval_only').mkdir(parents=True)
    base.write_json(directory / 'case.json', {**case, 'labels': data['case']['labels']})
    base.write_json(directory / 'result.json', data['result'])
    (directory / 'eval_only/trace.jsonl').write_text(''.join(json.dumps(s) + '\n' for s in data['trace']))
    base.write_rows(raw, [row])
    return raw, seal, planfile


def test_registered_schema_and_real_runtime_plan_are_accepted(tmp_path):
    raw, seal, _ = registered_fixture(tmp_path)
    out = cp.analyse('registered-format-only', raw, sealed_manifest=seal)
    s = out['summary']
    assert s['n_cases'] == 72 and s['n_placements'] == s['denominator'] == 60
    assert s['pass_placements'] == s['n_classified_primary'] == 1, s
    assert s['counts']['FAIL'] == 0 and len(s['unclassified_cases']) == 71
    assert s['full_verdict'] == 'NOT_EVALUABLE'


@pytest.mark.parametrize('field', ['sealed', 'source', 'run', 'receipt', 'placements', 'payload'])
def test_registered_schema_provenance_and_admission_remain_pinned(tmp_path, field):
    raw, seal, planfile = registered_fixture(tmp_path)
    if field in ('sealed', 'placements', 'payload'):
        plan = json.loads(planfile.read_text())
        if field == 'sealed':
            plan['sealed'] = False
        elif field == 'placements':
            plan['placements']['sha256'] = 'f' * 64
        else:
            plan['execution_bundle_id'] = 'different'
        base.write_json(planfile, plan)
        with pytest.raises(cp.EvidenceError):
            cp.load_sealed_manifest(planfile, cp.sha256(planfile))
    else:
        directory = cp.ca.dra.case_dir(raw, seal['cases'][0]['attempts'][0]['case_id'])
        case = json.loads((directory / 'case.json').read_text())
        if field == 'run':
            case['registration_run_id'] = 'wrong-run'
        else:
            case['registration']['expected_source_sha' if field == 'source' else 'registration_sha256'] = 'f' * (40 if field == 'source' else 64)
        base.write_json(directory / 'case.json', case)
        out = cp.analyse('bad-admission', raw, sealed_manifest=seal)
        assert out['summary']['pass_placements'] == 0
        assert out['summary']['full_verdict'] == 'NOT_EVALUABLE'


@pytest.mark.parametrize('kind', ['negative', 'reversed', 'too_few', 'too_many', 'zero_gap'])
def test_coverage_self_consistency_not_just_evaluation_window(kind):
    row, result, trace = base.record()
    wall = result['wall_contact']['coverage']
    if kind == 'negative': wall['start_sim_s'] = -1.
    elif kind == 'reversed': wall['end_sim_s'] = -1.
    elif kind == 'too_few': wall['sample_count'] = 2
    elif kind == 'too_many': wall['sample_count'] = 10000
    else: wall['max_gap_s'] = 0.
    base.record_receipt(row, result, trace)
    out = cp.adjudicate_attempt(row, result, trace)
    assert out['state'] == 'INVALID' and out['class'] is None


def test_all_contract_tests_are_in_offline_ci():
    from scripts import run_ci_tests
    collected = run_ci_tests.collect_test_files(base.ROOT, run_ci_tests.TEST_PATTERNS)
    assert 'tests/test_classify_review_299c.py' in collected
    assert 'tests/test_v6h_recorder_contract.py' in collected
