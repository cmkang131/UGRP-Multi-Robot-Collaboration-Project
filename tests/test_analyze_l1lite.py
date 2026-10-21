"""Fake-data tests for scripts/analyze_l1lite.py (no physics, no LLM, no run)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from harness import e2ewarp_l1lite as L
from harness import e2ewarp_l1lite_eval as E
from scripts import analyze_l1lite as A

SHA = 'f' * 40
PREREG = (Path(__file__).resolve().parents[1]
          / 'experiments/2026-10-20-l1lite-alloc/PREREG_L1LITE.md')


def _allocation(**overrides):
    value = dict(errors=[], fatal=False, success_eligible=True, messages=[],
                 utterances=2, deadlock=False)
    value.update(overrides)
    return value


def good_eval(seed, **overrides):
    constraints = L.all_constraints(seed)
    slots = {'r1': 'left', 'r2': 'right'}
    for robot, slot in constraints.items():
        if slot is not None:
            slots[robot] = slot
            slots[next(r for r in L.ROBOTS if r != robot)] = (
                'left' if slot == 'right' else 'right')
    gt = {r: E.slot_zone(E.ZONE_B, s)['center_m'] for r, s in slots.items()}
    kwargs = dict(slots=slots, constraints=constraints, final_gt=gt,
                  claims={'r1': True, 'r2': True}, zone=E.ZONE_B,
                  contacts_available=True, robot_robot_contacts=0,
                  claim_sim_s={'r1': 39.7, 'r2': 40.1}, sim_s=40.1,
                  allocation=_allocation(),
                  usage=[dict(usage=dict(prompt_tokens=1000, completion_tokens=20))] * 2,
                  min_center_distance_m=0.3, min_body_gap_m=0.1, messages=[])
    kwargs.update(overrides)
    return E.evaluate(**kwargs)


def write_eval(tmp_path, name, report):
    path = tmp_path / (name + '.json')
    path.write_text(json.dumps(report))
    return path.name


def full_ledger(tmp_path, evals=None, skip=(), host_error=(), extra=()):
    """One main row per planned cell in the pre-registered order."""
    evals = evals or {}
    runs = []
    for row in A.run_order():
        key = (row['condition'], row['seed'])
        if key in skip:
            continue
        item = dict(order=row['order'], condition=row['condition'], seed=row['seed'],
                    kind='main', source_sha=SHA, status='NAV_ARRIVAL_UNVERIFIED')
        if key in host_error:
            item['status'] = A.HOST_ERROR
        else:
            report = evals.get(key) or good_eval(row['seed'])
            item['evaluation_path'] = write_eval(
                tmp_path, f'{row["condition"]}-{row["seed"]}', report)
        runs.append(item)
    runs.extend(extra)
    return dict(schema=A.LEDGER_SCHEMA, frozen_source_sha=SHA, runs=runs)


# ---------------------------------------------------------------------------
# Pre-registered order


def test_run_order_covers_every_cell_once_and_is_deterministic():
    order = A.run_order()
    assert [r['order'] for r in order] == list(range(1, 25))
    cells = {(r['condition'], r['seed']) for r in order}
    assert cells == {(c, s) for c in L.CONDITIONS for s in L.TABLE_SEEDS}
    assert A.run_order() == order
    assert {r['part'] for r in order if r['seed'] <= 603} == {1}
    assert {r['part'] for r in order if r['seed'] >= 604} == {2}


def test_williams_rows_balance_first_order_carryover():
    pairs = [(row[i], row[i + 1]) for row in A.WILLIAMS_ROWS for i in range(3)]
    assert len(pairs) == len(set(pairs)) == 12
    for pos in range(4):
        assert sorted(row[pos] for row in A.WILLIAMS_ROWS) == [0, 1, 2, 3]


def test_prereg_order_table_matches_the_generator():
    text = PREREG.read_text()
    rows = re.findall(r'^\| (\d+) \| ([12]) \| (\d) \| (\d{3}) \| (\w+) \|$', text, re.M)
    assert [(int(o), int(p), int(b), int(s), c) for o, p, b, s, c in rows] == [
        (r['order'], r['part'], r['block'], r['seed'], r['condition'])
        for r in A.run_order()]


def test_prereg_names_ready_for_review_and_the_constraint_digest():
    text = PREREG.read_text()
    assert 'READY_FOR_REVIEW' in text
    assert L.constraint_table_digest() in text


# ---------------------------------------------------------------------------
# Denominator rules


def test_all_success_gives_six_of_six(tmp_path):
    summary = A.analyze(full_ledger(tmp_path), base=tmp_path)
    for condition in L.CONDITIONS:
        assert summary['table'][condition]['n_success'] == 6
        assert summary['table'][condition]['n_total'] == 6
    assert summary['statistical_test'] is None
    assert not summary['protocol_deviations']


def test_not_run_and_host_error_stay_in_the_denominator(tmp_path):
    ledger = full_ledger(tmp_path, skip={('peer_en', 602)},
                         host_error={('peer_en', 603)})
    row = A.analyze(ledger, base=tmp_path)['table']['peer_en']
    assert (row['n_success'], row['n_total']) == (4, 6)
    assert row['primary_failure_reasons'] == {'NOT_RUN': 1, 'HOST_ERROR': 1}
    assert row['not_run'] == 1 and row['host_error'] == 1


def test_sha_mismatch_counts_as_failure_and_is_a_deviation(tmp_path):
    ledger = full_ledger(tmp_path)
    target = next(r for r in ledger['runs'] if (r['condition'], r['seed']) == ('structured', 601))
    target['source_sha'] = 'e' * 40
    summary = A.analyze(ledger, base=tmp_path)
    assert summary['table']['structured']['n_success'] == 5
    assert summary['table']['structured']['primary_failure_reasons'] == {'SHA_MISMATCH': 1}
    assert any(d['condition'] == 'structured' for d in summary['protocol_deviations'])


def test_missing_evaluation_is_a_failure_not_a_skip(tmp_path):
    ledger = full_ledger(tmp_path)
    target = next(r for r in ledger['runs'] if (r['condition'], r['seed']) == ('leader_en', 604))
    target['evaluation_path'] = 'does-not-exist.json'
    row = A.analyze(ledger, base=tmp_path)['table']['leader_en']
    assert row['n_success'] == 5
    assert row['primary_failure_reasons'] == {'EVAL_MISSING': 1}


def test_smoke_and_dev_rows_are_excluded_never_pooled(tmp_path):
    extra = [dict(order=None, condition='no_comm', seed=701, kind='dev', source_sha=SHA,
                  status='NAV_ARRIVAL_UNVERIFIED',
                  evaluation_path=write_eval(tmp_path, 'dev', good_eval(701))),
             dict(order=None, condition='peer_en', seed=601, kind='smoke', source_sha=SHA,
                  status='NAV_ARRIVAL_UNVERIFIED',
                  evaluation_path=write_eval(tmp_path, 'smoke', good_eval(601)))]
    ledger = full_ledger(tmp_path, skip={('peer_en', 601)}, extra=extra)
    summary = A.analyze(ledger, base=tmp_path)
    # The smoke success on peer_en/601 does not fill the missing main cell.
    assert summary['table']['peer_en']['n_success'] == 5
    assert summary['table']['peer_en']['per_seed']['601'] is False
    assert {r['reason'] for r in summary['excluded']} == {'kind=dev', 'kind=smoke'}


def test_a_rerun_never_replaces_the_first_attempt(tmp_path):
    failed = good_eval(605, claims={'r1': True, 'r2': False})
    ledger = full_ledger(tmp_path, evals={('structured', 605): failed})
    ledger['runs'].append(dict(order=25, condition='structured', seed=605, kind='main',
                               source_sha=SHA, status='NAV_ARRIVAL_UNVERIFIED',
                               evaluation_path=write_eval(tmp_path, 'rerun', good_eval(605))))
    summary = A.analyze(ledger, base=tmp_path)
    cell = next(c for c in summary['cells'] if (c['condition'], c['seed']) == ('structured', 605))
    assert cell['success'] is False and cell['counted_order'] == 19
    assert cell['deviations'] == ['EXTRA_ATTEMPTS_NOT_COUNTED:25']
    assert summary['table']['structured']['n_success'] == 5


def test_order_deviation_is_recorded_but_does_not_change_success(tmp_path):
    ledger = full_ledger(tmp_path)
    a = next(r for r in ledger['runs'] if r['order'] == 1)
    b = next(r for r in ledger['runs'] if r['order'] == 2)
    a['order'], b['order'] = 2, 1
    summary = A.analyze(ledger, base=tmp_path)
    assert summary['table']['no_comm']['n_success'] == 6
    items = [i for d in summary['protocol_deviations'] for i in d['items']]
    assert any(i.startswith('ORDER_DEVIATION') for i in items)


def test_ledger_schema_and_frozen_sha_are_required(tmp_path):
    with pytest.raises(ValueError, match='schema'):
        A.analyze(dict(runs=[]), base=tmp_path)
    with pytest.raises(ValueError, match='frozen source SHA'):
        A.analyze(dict(schema=A.LEDGER_SCHEMA, runs=[]), base=tmp_path)


# ---------------------------------------------------------------------------
# Failure reasons and auxiliary metrics


def test_no_comm_collision_reports_duplicate_slot_first(tmp_path):
    # 601: r1 must take right, r2 defaults to its right lane -> collision.
    report = good_eval(601, slots={'r1': 'right', 'r2': 'right'},
                       allocation=_allocation(errors=['L1LITE_DUPLICATE_SLOT'],
                                              success_eligible=False))
    reasons = A.failure_reasons(report)
    assert reasons[0] == 'L1LITE_DUPLICATE_SLOT'
    assert 'SLOTS_NOT_DISTINCT' in reasons
    assert report['success'] is False


def test_each_component_maps_to_one_reason():
    assert A.failure_reasons(good_eval(603)) == []
    assert A.failure_reasons(None) == ['EVAL_MISSING']
    assert 'CONSTRAINT_VIOLATION' in A.failure_reasons(
        good_eval(603, slots={'r1': 'right', 'r2': 'left'},
                  final_gt={'r1': E.slot_zone(E.ZONE_B, 'right')['center_m'],
                            'r2': E.slot_zone(E.ZONE_B, 'left')['center_m']}))
    assert A.failure_reasons(good_eval(603, final_gt={'r1': [0.0, 0.0],
                                                      'r2': [4.6, -2.45]})) == [
        'GT_NOT_IN_CHOSEN_SLOT']
    assert A.failure_reasons(good_eval(603, final_gt={'r1': None, 'r2': None})) == [
        'GT_UNMEASURED']
    assert A.failure_reasons(good_eval(603, contacts_available=False)) == [
        'CONTACT_UNAVAILABLE']
    assert A.failure_reasons(good_eval(603, robot_robot_contacts=2)) == ['ROBOT_CONTACT']
    fatal = good_eval(603, allocation=_allocation(errors=['L1LITE_NO_DECISION'],
                                                  fatal=True, success_eligible=False),
                      slots={}, final_gt={}, claims={})
    assert A.failure_reasons(fatal)[0] == 'L1LITE_NO_DECISION'


def test_aux_summary_per_condition(tmp_path):
    slow = good_eval(602, claim_sim_s={'r1': 50.0, 'r2': 52.0}, sim_s=52.0,
                     min_body_gap_m=0.02)
    talk = good_eval(603, messages=[dict(sender='r1', sim_s=0.0,
                                         body={'text': 'I will take slot middle.'})])
    ledger = full_ledger(tmp_path, evals={('peer_en', 602): slow, ('peer_en', 603): talk})
    aux = A.analyze(ledger, base=tmp_path)['table']['peer_en']['aux']
    assert aux['runs_with_eval'] == 6
    assert aux['completion_sim_s_success_median'] == pytest.approx(40.1)
    assert sorted(aux['completion_sim_s_success'])[-1] == 52.0
    assert aux['min_body_gap_m_min'] == 0.02
    assert aux['llm_calls_total'] == 12
    assert aux['llm_tokens_total'] == 12 * 1020
    assert aux['llm_cost_usd_total'] == pytest.approx(12 * (1000 * 0.1 + 20 * 0.34) / 1e6)
    assert aux['hallucination_total'] == 1 and aux['hallucination_runs'] == 1
    assert aux['deadlock_runs'] == 0


def test_markdown_and_cli_round_trip(tmp_path):
    ledger = full_ledger(tmp_path, host_error={('no_comm', 606)})
    path = tmp_path / 'ledger.json'
    path.write_text(json.dumps(ledger))
    out_json, out_md = tmp_path / 'summary.json', tmp_path / 'summary.md'
    assert A.main([str(path), '--out-json', str(out_json), '--out-md', str(out_md)]) == 0
    summary = json.loads(out_json.read_text())
    assert summary['table']['no_comm']['n_success'] == 5
    assert len(summary['ledger']['sha256']) == 64
    md = out_md.read_text()
    assert '| no_comm | 5/6 |' in md
    assert 'HOST_ERROR' in md


def test_raw_recount_path_uses_evaluate_run(tmp_path):
    """A row without evaluation_path is recounted from its raw run directory."""
    run = tmp_path / 'o03-structured-s601'
    (run / 'world-00').mkdir(parents=True)
    (run / 'world-00' / 'eval-geometry.json').write_text(json.dumps(dict(
        robot_qpos_adr={'r1': 0, 'r2': 10},
        destination=dict(center_m=[4.6, -2.1], half_extents_m=[0.3, 0.7]))))
    qpos = np.zeros((3, 1, 30))
    qpos[:, 0, 3] = qpos[:, 0, 13] = 1.0
    qpos[-1, 0, :2] = [4.6, -2.45]   # r1 -> right (601: r1 constrained to right)
    qpos[-1, 0, 10:12] = [4.6, -1.75]  # r2 -> left
    qpos[:-1, 0, 0], qpos[:-1, 0, 10] = -0.9, -0.9
    qpos[:-1, 0, 1], qpos[:-1, 0, 11] = -2.375, -2.875
    np.savez_compressed(run / 'evaluation-state.npz', qpos=qpos, dt=.1)
    (run / 'result.json').write_text(json.dumps(dict(status='NAV_ARRIVAL_UNVERIFIED',
                                                     sim_s=41.0, source_sha=SHA)))
    (run / 'nav-events.json').write_text(json.dumps({
        '0:r1': [dict(sim_s=40.0, after='ARRIVED')],
        '0:r2': [dict(sim_s=41.0, after='ARRIVED')]}))
    (run / 'contact-ledger.json').write_text(json.dumps(dict(
        contacts_available=True, contact_pairs_total=0)))
    (run / 'slot-decisions.json').write_text(json.dumps(_allocation(
        decisions={'r1': 'right', 'r2': 'left'}, constraints=L.all_constraints(601))))
    ledger = full_ledger(tmp_path)
    target = next(r for r in ledger['runs'] if (r['condition'], r['seed']) == ('structured', 601))
    target.pop('evaluation_path')
    target['run_dir'] = run.name
    summary = A.analyze(ledger, base=tmp_path)
    cell = next(c for c in summary['cells'] if (c['condition'], c['seed']) == ('structured', 601))
    assert cell['success'] is True, cell
    assert cell['aux']['completion_sim_s'] == 41.0
