"""Seeded generative specification: 10,000 cases, five invariants per case.

Hypothesis is absent from the shared .venv-sim. The seed, count, mutation family
and case index are included in failures; no physics or external services.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import random

SPEC = importlib.util.spec_from_file_location('property_builders', Path(__file__).with_name('test_classify_review_299.py'))
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)
cp = base.cp
SEED = 202609300299
GENERATED_CASES = 10_000


def corrupt(rng, row, result, trace):
    """Information loss / malformed evidence; never substitute a new outcome."""
    kind = rng.randrange(12)
    if kind == 0:
        del row['wall_contact']
    elif kind == 1:
        del result['failures']
    elif kind == 2:
        trace[:] = trace[:rng.randrange(len(trace))]
    elif kind == 3:
        trace.pop(rng.randrange(len(trace)))
    elif kind == 4:
        trace[rng.randrange(len(trace))]['tilt_deg'] = 'corrupt'
    elif kind == 5:
        result['evaluation_coverage']['trace_count'] += 1
    elif kind == 6:
        del row['chain']['legs'][rng.randrange(2)]['jaws']
    elif kind == 7:
        result['termination']['sim_s'] = None
    elif kind == 8:
        row['wall_contact']['max_penetration_m'] = None
    elif kind == 9:
        del row['chain']['first_failure']
    elif kind == 10:
        trace[rng.randrange(1, len(trace))]['t'] = -1
    else:
        result['wall_contact']['coverage']['max_gap_s'] = 5
    return kind


def event(row, result, trace):
    return cp.adjudicate_attempt(row, result, trace)


def normalized(summary):
    return json.dumps(summary, sort_keys=True, allow_nan=False)


def test_ten_thousand_generated_evidence_chains():
    rng = random.Random(SEED)
    counts = {str(k): 0 for k in range(12)}
    statuses = {}
    for index in range(GENERATED_CASES):
        row, result, trace = base.record()
        if rng.choice((False, True)):
            row['chain']['n_legs'] = rng.randrange(3, 9)
            row['chain']['legs'].extend({'leg': k, 'recorded': False, 'start_sim_s': None, 'end_sim_s': None}
                for k in range(2, row['chain']['n_legs']))
        # Vary valid numeric evidence, source of failure, retry ordering and sizes.
        end_error = rng.uniform(.101, .9)
        leg = rng.randrange(2)
        row['chain']['legs'][leg]['end_error_m'] = end_error
        failure = {'phase': 'carry', 'leg': leg, 'code': 'END_ERROR', 'sim_s': row['chain']['legs'][leg]['end_sim_s']}
        row['chain']['first_failure'] = failure
        if rng.choice((False, True)):
            result['failures']['r1'] = copy.deepcopy(failure)
        if rng.choice((False, True)):
            row.update(category='HOST_ERROR:ENOSPC', host_error='cleanup')
            result['termination']['outcome'] = 'HOST_ERROR'
        base.record_receipt(row, result, trace)
        original = event(row, result, trace)
        assert original['class'] not in cp.PASS, (SEED, index, original)
        r, s, t = copy.deepcopy((row, result, trace))
        kind = corrupt(rng, r, s, t)
        counts[str(kind)] += 1
        mutated = event(r, s, t)
        assert mutated['class'] not in cp.PASS, (SEED, index, kind, mutated)  # (a)
        # An otherwise valid successful retry cannot erase a terminal result.
        retry_row, retry_result, retry_trace = base.record()
        retry_row['case_id'] += ':retry1'
        base.record_receipt(retry_row, retry_result, retry_trace)
        good_retry = event(retry_row, retry_result, retry_trace)
        assert good_retry['class'] in cp.PASS
        for first in (original, mutated):
            out = cp.classify_attempt_sequence([first, good_retry])
            assert out['class'] not in cp.PASS, (SEED, index, kind, out)
        # Put a hard violation in every supported type of safety record in turn,
        # including malformed/partial HOST_ERRORs and the auxiliary seed.
        hard_row, hard_result, hard_trace = copy.deepcopy((r, s, t))
        source = index % 5
        value = rng.uniform(15.001, 35.)
        if source == 0:
            hard_result['gt_at_stop'] = {'tilt_deg': value}
        elif source == 1:
            hard_row.setdefault('wall_contact', {})['max_tilt_deg_stage'] = value
        elif source == 2:
            hard_row.setdefault('wall_contact', {})['max_penetration_m'] = rng.uniform(.005001, .1)
        elif source == 3:
            hard_trace.append({'t': 4., 'tilt_deg': value})
        else:
            hard_row['chain']['legs'][leg]['tilt_deg'] = value
        hard = event(hard_row, hard_result, hard_trace)
        assert hard['class'] == 'FAIL_HARD_LIMIT', (SEED, index, source, hard)
        assert cp.classify_attempt_sequence([hard, good_retry])['class'] == 'FAIL_HARD_LIMIT'  # (b)
        # Deleting an OPTIONAL observation or changing it to a plausible good
        # value must also fail, even when it was the sole positive witness.
        hr, hs, ht = base.record()
        hs['gt_at_stop'] = {'t': 3.01, 'tilt_deg': value}
        base.record_receipt(hr, hs, ht)
        assert event(hr, hs, ht)['class'] == 'FAIL_HARD_LIMIT'
        if index % 2:
            del hs['gt_at_stop']
        else:
            hs['gt_at_stop']['tilt_deg'] = 1.
        erased = event(hr, hs, ht)
        assert erased['class'] is None and not erased['evidence_valid'], (SEED, index, erased)
        # Only a complete, validated, failure-free HOST_ERROR may lead to PASS.
        safe_row, safe_result, safe_trace = base.record()
        safe_row.update(category='HOST_ERROR:ENOSPC', host_error='cleanup')
        safe_result['termination']['outcome'] = 'HOST_ERROR'
        if rng.choice((False, True)):
            safe_row["first_failure"] = {"robot_id": None, "sim_s": None, "reason": "HOST_ERROR"}
        base.record_receipt(safe_row, safe_result, safe_trace)
        safe_host = event(safe_row, safe_result, safe_trace)
        good_chain = cp.classify_attempt_sequence([safe_host, good_retry])
        assert good_chain['class'] in cp.PASS and all(a['evidence_valid'] for a in (safe_host, good_retry))
        corrupt(rng, safe_row, safe_result, safe_trace)
        bad_chain = cp.classify_attempt_sequence([event(safe_row, safe_result, safe_trace), good_retry])
        assert bad_chain['class'] not in cp.PASS and bad_chain['invalid_evidence']  # (d)
        # All admitted placements remain: missing records use invalid placeholders.
        cases = []
        n = rng.randrange(1, 7)
        for cell in range(n):
            candidate = copy.deepcopy(rng.choice((original, mutated, hard, good_retry)))
            candidate.update(placement=f'C{cell:02}', case_id=f'case:{cell}', seed=941)
            cases.append(candidate)
        _, before = cp.summarize(cases)
        rng.shuffle(cases)
        _, after = cp.summarize(cases)
        # ID lists are a set-valued diagnostic; normalize before comparing.
        for summary in (before, after):
            summary['hard_limit_attempt_case_ids'].sort()
            summary['unclassified_cases'].sort()
        assert normalized(before) == normalized(after), (SEED, index)  # (c)
        assert after['n_placements'] == n == after['n_classified_primary'] + len(after['unclassified_placements'])  # (e)
        assert sum(after['counts'].values()) + len(after['unclassified_placements']) == n
        statuses[mutated['state']] = statuses.get(mutated['state'], 0) + 1
    report = {'seed': SEED, 'generated_cases': GENERATED_CASES, 'invariants_per_case': 5,
              'mutation_counts': counts, 'mutated_states': statuses, 'physics_runs': 0}
    if os.environ.get('V6H_PROPERTY_REPORT'):
        path = Path(os.environ['V6H_PROPERTY_REPORT'])
        path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


def test_empty_attempt_chain_is_total_and_fail_closed():
    out = cp.classify_attempt_sequence([])
    assert out['class'] is None and out['reason_code'] == 'MISSING_ORIGINAL'


def test_generated_file_loss_keeps_all_admissions_and_hard_evidence(tmp_path):
    rng = random.Random(SEED + 1)
    for index, mutation in enumerate(('missing_row', 'bad_row', 'missing_result', 'bad_result',
                                       'empty_trace', 'bad_trace_tail', 'duplicate_row', 'missing_summary', 'missing_retry_row')):
        root = tmp_path / str(index)
        root.mkdir()
        raw, seal, rows, identity = base.sealed_cohort(root, retry_seed=941 if mutation == 'missing_retry_row' else None)
        victim = 0 if mutation == 'missing_retry_row' else rng.randrange(len(rows))
        cid = rows[victim]['case_id']
        directory = cp.ca.dra.case_dir(raw, cid)
        if mutation == 'missing_row':
            rows.pop(victim)
            base.write_rows(raw, rows)
        elif mutation == 'bad_row':
            path = raw / 'cases.jsonl'
            records = path.read_bytes().splitlines()
            records[victim] = b'{"truncated":'
            path.write_bytes(b'\n'.join(records) + b'\n')
        elif mutation == 'missing_result':
            (directory / 'result.json').unlink()
        elif mutation == 'bad_result':
            (directory / 'result.json').write_bytes(b'{"truncated":')
        elif mutation == 'empty_trace':
            (directory / 'eval_only/trace.jsonl').write_bytes(b'')
        elif mutation == 'bad_trace_tail':
            with (directory / 'eval_only/trace.jsonl').open('ab') as stream:
                stream.write(b'{"t":4.,')
        elif mutation == 'duplicate_row':
            rows.append(copy.deepcopy(rows[victim]))
            rows[-1]['wall_contact']['max_tilt_deg_stage'] = 16.
            base.write_rows(raw, rows)
        elif mutation == 'missing_summary':
            del rows[victim]['wall_contact']
            base.write_rows(raw, rows)
        else:
            retry_row, retry_result, retry_trace = base.record()
            retry_row['case_id'] = seal['cases'][0]['attempts'][1]['case_id']
            retry_result['gt_at_stop'] = {'tilt_deg': 16.}
            # Artifact remains even though the retry's cases.jsonl row is lost.
            base.write_record(raw, retry_row, retry_result, retry_trace, identity)
        report = cp.analyse('generated-files', raw, sealed_manifest=seal)
        s = report['summary']
        assert s['n_cases'] == 72 and s['denominator'] == s['admitted_placement_count'] == 60
        assert s['full_verdict'] == ('FAIL_A_B_SAFETY' if mutation in ('duplicate_row', 'missing_retry_row') else 'NOT_EVALUABLE'), (index, mutation, s)
        assert cid in s['selected_case_ids']
        if mutation == 'duplicate_row':
            assert cid in s['hard_limit_attempt_case_ids']
        if mutation == 'missing_retry_row':
            assert retry_row['case_id'] in s['hard_limit_attempt_case_ids']
            assert s['n_adjudicated_attempt_slots'] == 73
        # Permuting unrelated rows cannot affect the adjudicated outcomes.
        if mutation not in ('bad_row', 'duplicate_row'):
            rng.shuffle(rows)
            base.write_rows(raw, rows)
            again = cp.analyse('generated-files', raw, sealed_manifest=seal)
            assert again['summary'] == s


def test_stored_summary_contradiction_and_nonstandard_json_are_invalid(tmp_path):
    row, result, trace = base.record()
    result['max_tilt_deg'] = 2.
    base.record_receipt(row, result, trace)  # good checksum cannot excuse a schema contradiction
    out = event(row, result, trace)
    assert out['state'] == 'INVALID'
    assert any('summary differs' in issue for issue in out['hard_limit_chain']['evidence_issues'])
    reader = cp.EvidenceReader(tmp_path)
    path = tmp_path / 'bad.jsonl'
    path.write_text('{"t":0,"t":1}\n{"unrelated":NaN}\n')
    records, errors = reader.read(path, lines=True)
    assert len(records) == 2
    assert any('DUPLICATE_JSON_KEY' in e for e in errors)
    assert any('NONFINITE_JSON_NUMBER' in e for e in errors)


def test_terminal_failure_keeps_original_identity_with_later_hard_violation():
    r, s, t = base.record()
    r['chain']['legs'][1]['end_error_m'] = .11
    base.record_receipt(r, s, t)
    original = event(r, s, t)
    rr, ss, tt = base.record()
    rr['case_id'] += ':retry1'
    ss['gt_at_stop'] = {'tilt_deg': 16.}
    base.record_receipt(rr, ss, tt)
    out = cp.classify_attempt_sequence([original, event(rr, ss, tt)])
    assert original['class'] == 'FAIL'
    assert out['case_id'] == original['case_id']
    assert out['class'] == 'FAIL_HARD_LIMIT' and out['hard_limit_chain']['max_tilt_deg'] == 16.
    assert out['invalid_evidence'] and out['sequence_issues']
