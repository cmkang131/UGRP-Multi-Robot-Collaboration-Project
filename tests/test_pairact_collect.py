"""P3 success-filtered collection controller (COLLECT_PREREG v2): fake episode outcomes only (no simulator).

Codex 01-collect-prereg-review.md items and repo audit items are named in the test docstrings;
the three counterexamples of collect-review-20261020/prereg/reproduce.py are reproduced as tests.
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from harness import pairact_collect as pc

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/2026-10-21-pairact-r1'
PREREG = EXP / 'COLLECT_PREREG_DRAFT.json'
spec = importlib.util.spec_from_file_location('run_pairact_collect', ROOT / 'scripts/run_pairact_collect.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

# teacher phases covering every validation_gate stage (approach .. complete)
PHASES = ['approach', 'align', 'ready', 'pick', 'carry:carry_hold', 'carry:door_pass', 'carry:lower', 'carry:done']
TABLE = '/runs/b/rejection_table.json'
EP_CMD = ('python wrap.py --flow beampair --cases {cases} --indices {indices} --cap-s 60 '
          '--rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --out {out}')


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


def case_for(prereg, slot):
    layers = {}
    for i, rid in enumerate(('r1', 'r2')):
        d, y = pc.draw_start(prereg, slot['seed'], slot['bin'], i)
        layers[rid] = dict(layer=slot['bin'], target_distance_m=d, yaw_bin=dict(index=None, offset_rad=y))
    return dict(plan=dict(seed=slot['seed'], start_layers=layers, roles={'r1': 'teal', 'r2': 'blue'}),
                candidate='pairact_p2_r13')


def result(success=True, grasp=True, drops=(), rr=0, handoff=False, admitted=True, status='complete',
           failure='not_through_door', outcome='route_blocked', end_reason='teacher_terminal'):
    ev = dict(success=success, failure=None if success else failure, drop_events=list(drops),
              robot_robot_contact_ticks=rr, carried_max_m=4. if success else .0006,
              funnel=dict(handover=True, carried_1m=success, door_passed=success))
    events = [dict(t=10., event='handover')]
    if not success:
        events.append(dict(t=25., event='fail', code=outcome, phase='to_west_staging', detail='blocked by box_3'))
    carry = dict(outcome='command_sequence_complete' if success else outcome, events=events)
    return dict(status=status, grasp_physical_success=grasp, carry_eval=ev if grasp else None,
                carry=carry if grasp else {'started': False, 'reason': 'no_joint_hold_3s'},
                search_handoff=handoff, approach_handoff=False, data_admitted=admitted, end_reason=end_reason,
                cap_end=end_reason == 'cap_end')


def write_streams(raw, phases=PHASES, robots=('r1', 'r2')):
    for rid in robots:
        (raw / f'teacher-{rid}.jsonl').write_text(''.join(
            json.dumps(dict(sample_id=i, teacher_phase=p)) + '\n' for i, p in enumerate(phases)))
        (raw / f'student-{rid}.jsonl').write_text(''.join(json.dumps(dict(sample_id=i)) + '\n'
                                                          for i in range(len(phases))))


class FakeEpisode:
    """Writes the root-runner layout: out/summary.json + world-XXX/raw/{result.json, streams}."""

    def __init__(self, outcome, *, crash_first=0, drop_seeds=(), status=None, code=0, streams=True):
        self.outcome, self.calls, self.crash_first, self.drop_seeds = outcome, [], crash_first, set(drop_seeds)
        self.status, self.code, self.streams = status, code, streams

    def __call__(self, cases_path, indices, out):
        self.calls.append(list(indices))
        cases = json.loads(Path(cases_path).read_text())
        out = Path(out)
        out.mkdir(parents=True)
        if len(self.calls) <= self.crash_first:
            (out / 'summary.json').write_text(json.dumps(dict(status='running')))   # killed before finally
            return -9
        worlds, lost = [], False
        for i, idx in enumerate(indices):
            seed = cases[idx]['plan']['seed']
            if seed in self.drop_seeds:
                self.drop_seeds.discard(seed)        # world lost once (HOST_ERROR mid batch)
                lost = True
                continue
            raw = out / f'world-{i:03d}' / 'raw'
            raw.mkdir(parents=True)
            r = self.outcome(seed, cases[idx])
            (raw / 'result.json').write_text(json.dumps(r))
            if self.streams:
                write_streams(raw)
            worlds.append(dict(world=i, seed=seed, carry_success=(r.get('carry_eval') or {}).get('success'),
                               raw=str(raw), sim_s=100.))
        status = self.status(len(self.calls)) if callable(self.status) else self.status
        status = status or ('HOST_ERROR' if lost else 'complete')
        (out / 'summary.json').write_text(json.dumps(dict(status=status, HOST_ERROR=int(status == 'HOST_ERROR'),
                                                          worlds=worlds, rejection_table=TABLE)))
        return self.code(len(self.calls)) if callable(self.code) else self.code


def make(prereg):
    return lambda slots: [case_for(prereg, s) for s in slots]


def collect(tmp, prereg, outcome, **kw):
    ep = kw.pop('episode', None) or FakeEpisode(outcome)
    state = runner.run(tmp, prereg, 'sha', mode=kw.pop('mode', 'training'), noise='off',
                       batch_size=kw.pop('batch_size', 20), max_batches=kw.pop('max_batches', 1000),
                       make_cases=kw.pop('make_cases', None) or make(prereg), run_episode=ep, **kw)
    return state, pc.replay(prereg, pc.read_ledger(Path(tmp) / 'ledger.jsonl')), ep


def attempt_row(seed, bin_id, j, split='train', batch=0, start=None):
    return dict(type='attempt', batch=batch, slot=0, seed=seed, bin=bin_id, split=split, start=start or {}, **j)


def ledger_state(prereg, rows, mode='training'):
    """Synthetic ledger; without explicit batch_planned rows every attempt gets its own planned slot in batch 0."""
    if not any(r['type'] == 'batch_planned' for r in rows):
        rows = [dict(r, slot=i) for i, r in enumerate(rows)]
        slots = [dict(slot=r['slot'], seed=r['seed'], bin=r['bin'], split=r['split'], requeue=False) for r in rows]
        rows = [dict(type='batch_planned', batch=0, split='train', cases_sha256='x', slots=slots)] + rows
    return pc.replay(prereg, [pc.header('sha', mode=mode, noise='off', batch_size=20)] + rows)


# --------------------------------------------------------------- prereg

def test_prereg_v2_numbers_unit_and_start_trigger(prereg):
    """Codex (1) start condition, (2) n/200, owner decisions 1-2."""
    assert prereg['schema'] == pc.PREREG_SCHEMA and prereg['status'] == 'READY_FOR_REVIEW'
    assert pc.bin_ids(prereg) == ['B0', 'B1', 'B2', 'B3', 'B4', 'B5']
    assert prereg['bins']['min_admitted_per_bin'] == 20
    t = prereg['targets']
    assert (t['admitted_target_pairs'], t['admitted_minimum_pairs'], t['attempt_cap']) == (200, 150, 600)
    assert 'never a denominator' in t['not_a_denominator']
    assert prereg['unit']['id'] == 'pair_episode'
    trig = prereg['start_trigger']
    assert 'NOT a start condition' in trig['rule'] and trig['evidence']['seeds'] == [8420001, 8420011, 8420017]
    assert trig['evidence']['report_file'].endswith('1197dc28e64711aa88b8031cb0406f9456687b56a54a6a05d23ee79c8fba75e4')
    assert prereg['bins']['bin_limit']['min_attempts'] == 20 and prereg['bins']['bin_limit']['max_success_rate'] == .2
    assert prereg['validation_gate']['min_admitted'] == 8
    assert prereg['dart_noise']['default'] == 'off'
    assert set(prereg['reporting']) >= {'A', 'B', 'C', 'pilot', 'validation'}
    # every stop rule named in the training decision
    names = [r.split(':')[0] for r in prereg['stop_rules']['list']]
    assert set(prereg['training_decision']['per_stop']) == set(names)


def test_collect_spec_no_longer_requires_p1():
    """Codex (1): COLLECT_SPEC.md:3 P1 >=38/40 required vs prereg P1 non-blocking."""
    head = (EXP / 'COLLECT_SPEC.md').read_text().splitlines()[2]
    assert '비차단' in head and 'P2 smoke' in head
    assert '통과해야 시작합니다' not in head


def test_status_table_code_matches_prereg(prereg):
    """Codex (2) status table: complete -> behavior; HOST_ERROR-like -> environment."""
    world = prereg['status_table']['world']
    for status, category in pc.WORLD_STATUS.items():
        assert world[status].startswith(category)
    assert set(world) == set(pc.WORLD_STATUS) | {'missing', 'other'}


def test_seed_ranges_disjoint_including_pilot(prereg):
    known = json.loads((EXP / 'seeds.json').read_text())['known_ranges']
    pc.check_seed_ranges(prereg, known)
    train = pc.pool(prereg, 'train')
    assert train[0] == 8340000 and train[-1] == 8340599 and train == sorted(train) and len(train) == 600
    assert pc.pool(prereg, 'pilot') == list(range(8343000, 8343040))
    with pytest.raises(ValueError, match='never collected'):
        pc.pool(prereg, 'heldout')
    bad = copy.deepcopy(prereg)
    bad['seeds']['pilot'] = {'first': 8341010, 'last': 8341049}
    with pytest.raises(ValueError, match='pilot seeds overlap validation'):
        pc.check_seed_ranges(bad)


def test_seeds_json_and_check_script_cover_pilot(prereg):
    """Owner 8: pilot seeds checked by the script (positive control: an overlapping pilot is caught)."""
    s = json.loads((EXP / 'seeds.json').read_text())
    pick = lambda r: (r['first'], r['last'])
    p = prereg['seeds']
    assert pick(p['train_primary']) == pick(s['splits']['train'])
    assert pick(p['train_extension']) == pick(s['train_extension'])
    assert pick(p['pilot']) == pick(s['pilot'])
    assert pick(p['validation']) == pick(s['splits']['validation'])
    assert pick(p['heldout']) == pick(s['splits']['heldout'])
    sp = importlib.util.spec_from_file_location('seedcheck', ROOT / 'scripts/check_pairact_r1_seeds.py')
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    assert m.check(s) == []
    bad = copy.deepcopy(s)
    bad['pilot'] = {'first': 8329000, 'last': 8329039}
    assert any('pilot' in x for x in m.check(bad))
    bad = copy.deepcopy(s)
    bad['pilot'] = {'first': 8342010, 'last': 8342049}
    assert any('heldout/pilot' in x for x in m.check(bad))


def test_training_mode_requires_frozen_prereg(tmp_path):
    with pytest.raises(ValueError, match='not allowed for training'):
        pc.load_prereg(PREREG, mode='training')
    pr, sha = pc.load_prereg(PREREG, mode='measurement')
    assert sha == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    frozen = tmp_path / 'p.json'
    frozen.write_text(json.dumps({**pr, 'status': 'FROZEN'}))
    pc.load_prereg(frozen, mode='training')
    old = tmp_path / 'v1.json'
    old.write_text(json.dumps({**pr, 'schema': 'ugrp.pairact_r1.collect_prereg.v1'}))
    with pytest.raises(ValueError, match='schema'):
        pc.load_prereg(old)


def test_draws_stay_inside_their_bin(prereg):
    for b in pc.bins(prereg):
        for seed in range(8340000, 8340050):
            for r in (0, 1):
                d, y = pc.draw_start(prereg, seed, b['id'], r)
                assert pc.bin_of(prereg, d, y) == b['id']
    assert pc.draw_start(prereg, 8340000, 'B3', 0) == pc.draw_start(prereg, 8340000, 'B3', 0)
    assert pc.yaw_class(math.pi) == 'facing' and pc.yaw_class(0.) == 'away'


# --------------------------------------------------------------- judge

def test_judge_success_failure_and_carry_subreasons():
    """Owner 13: carry failure sub-reasons straight from carry.outcome / events."""
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    assert (ok['category'], ok['success'], ok['admitted']) == ('behavior', True, True)
    assert pc.judge(result(drops=[{'kind': 'tilt'}]), mode='measurement', batch_clean=True)['success'] is False
    assert pc.judge(result(rr=3), mode='measurement', batch_clean=True)['failure_stage'] == 'carry'
    f = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    assert (f['eval_failure'], f['carry_outcome']) == ('not_through_door', 'route_blocked')
    assert f['carry_fail'] == dict(code='route_blocked', phase='to_west_staging', detail='blocked by box_3')
    assert f['carried_max_m'] == .0006 and f['funnel_last'] == 'handover'
    t = pc.judge(result(success=False, outcome='door_pass_timeout'), mode='measurement', batch_clean=True)
    assert t['carry_outcome'] == 'door_pass_timeout'
    g = pc.judge(result(grasp=False), mode='measurement', batch_clean=True)
    assert (g['category'], g['failure_stage']) == ('behavior', 'grasp')
    h = pc.judge(result(handoff=True), mode='measurement', batch_clean=True)
    assert h['success'] and not h['admitted'] and h['reason'] == 'success_not_admitted:handoff'


def test_cap_end_and_mission_failures_stay_in_the_denominator():
    """Codex (2): cap_end / mission failures were host_error (out of N) in v1."""
    for end in ('cap_end', 'planning_wall_safety_cap'):
        j = pc.judge(result(grasp=False, end_reason=end), mode='measurement', batch_clean=True)
        assert (j['category'], j['outcome'], j['reason']) == ('behavior', 'failure', end)
    j = pc.judge(result(success=False, outcome='carry_total_timeout', end_reason='cap_end'),
                 mode='measurement', batch_clean=True)
    assert j['category'] == 'behavior' and j['cap_end'] is True
    for status in ('HOST_ERROR', 'interrupted', 'running'):
        e = pc.judge(result(status=status), mode='measurement', batch_clean=True)
        assert (e['category'], e['outcome'], e['requeue_eligible']) == ('environment', 'host_error', True)
    assert pc.judge(None, mode='measurement', batch_clean=True)['category'] == 'environment'
    u = pc.judge(result(status='diagnostic_prefix_complete'), mode='measurement', batch_clean=True)
    assert u['category'] == 'record_error' and 'unregistered_status' in u['reason']


def test_missing_required_fields_are_rejected_not_defaulted():
    """Codex (1) counterexample 4: physical_success fallback and missing drop/contact were accepted."""
    partial = dict(status='complete', physical_success=True, data_admitted=True, carry_eval={'success': True})
    j = pc.judge(partial, mode='training', batch_clean=True, sidecar=dict(passed=True))
    assert j['category'] == 'record_error' and not j['success'] and not j['admitted']
    for drop in ('grasp_physical_success', 'search_handoff', 'data_admitted', 'end_reason'):
        r = result()
        del r[drop]
        assert pc.judge(r, mode='measurement', batch_clean=True)['category'] == 'record_error', drop
    for key in ('drop_events', 'robot_robot_contact_ticks', 'success', 'failure'):
        r = result()
        del r['carry_eval'][key]
        assert pc.judge(r, mode='measurement', batch_clean=True)['category'] == 'record_error', key
    r = result()
    r['carry_eval']['robot_robot_contact_ticks'] = None
    assert pc.judge(r, mode='measurement', batch_clean=True)['category'] == 'record_error'
    r = result()
    del r['carry']['outcome']
    assert pc.judge(r, mode='measurement', batch_clean=True)['category'] == 'record_error'


def test_training_success_needs_both_sidecars_and_recording(tmp_path):
    """Codex (1): eligible was counted before the sidecar ran."""
    r = result()
    no = pc.judge(r, mode='training', batch_clean=True, sidecar=None)
    assert no['success'] and not no['admitted'] and 'sidecar_failed' in no['reason']
    raw = tmp_path / 'raw'
    raw.mkdir()
    table = {'approach': 'approach', 'carry:done': 'complete'}
    assert not pc.sidecar_check(raw, phase_table=table)['passed']                    # no streams
    write_streams(raw, ['approach', 'carry:done'])
    sc = pc.sidecar_check(raw, phase_table=table)
    assert sc['passed'] and sc['stages'] == {'r1': ['approach', 'complete'], 'r2': ['approach', 'complete']}
    assert pc.judge(r, mode='training', batch_clean=True, sidecar=sc)['admitted']
    rec = pc.judge(result(admitted=False), mode='training', batch_clean=True, sidecar=sc)
    assert not rec['admitted'] and 'recording_not_admitted' in rec['reason']
    write_streams(raw, ['approach', 'carry:mystery'], robots=('r2',))
    assert 'unmapped' in pc.sidecar_check(raw, phase_table=table)['reason']
    write_streams(raw, ['approach', 'carry:done'], robots=('r2',))
    (raw / 'student-r2.jsonl').write_text(json.dumps(dict(sample_id=0)) + '\n')
    assert 'sample_id sets differ' in pc.sidecar_check(raw, phase_table=table)['reason']
    # the registered table is the pairact_r1 one (covers PHASES)
    write_streams(raw)
    assert pc.sidecar_check(raw)['passed']


# --------------------------------------------------------------- batch

def test_host_error_batch_admits_no_individual_success(tmp_path, prereg):
    """Repo audit 1 / Codex counterexample 1: batch HOST_ERROR but raw complete was eligible."""
    raw = tmp_path / 'raw'
    raw.mkdir()
    (raw / 'result.json').write_text(json.dumps(result()))
    write_streams(raw)
    ledger = tmp_path / 'ledger.jsonl'
    s = dict(slot=0, seed=8340000, bin='B0', split='train', requeue=False)
    pc.append(ledger, pc.header('sha', mode='training', noise='off', batch_size=1))
    pc.append(ledger, dict(type='batch_planned', batch=0, slots=[s], split='train', cases_sha256='x'))
    runner.ingest(ledger, 0, 1, [s], [case_for(prereg, s)],
                  dict(status='HOST_ERROR', HOST_ERROR=1, rejection_table=TABLE,
                       worlds=[dict(seed=8340000, raw=str(raw), carry_success=True)]), 0,
                  mode='training', noise='off', done_slots=set())
    st = pc.replay(prereg, pc.read_ledger(ledger))
    t = pc.totals(st)
    assert (t['attempts'], t['successes'], t['admitted']) == (1, 1, 0)
    row = st['attempt_rows'][0]
    assert row['batch_clean'] is False and 'batch_not_clean' in row['reason']


def test_exit_code_and_rejection_table_decide_batch_cleanliness():
    ok = dict(status='complete', HOST_ERROR=0, rejection_table=TABLE)
    assert pc.batch_is_clean(ok, 0)
    assert not pc.batch_is_clean(ok, 1) and not pc.batch_is_clean(ok, None)
    assert not pc.batch_is_clean(dict(ok, rejection_table='rel/table.json'), 0)
    assert not pc.batch_is_clean(dict(ok, HOST_ERROR=None), 0)
    assert not pc.batch_is_clean(dict(ok, status='admission_rejected'), 0)


def test_nonzero_exit_batch_is_judged_but_not_admitted(tmp_path, prereg):
    _, st, _ = collect(tmp_path, prereg, lambda s, c: result(), max_batches=1,
                       episode=FakeEpisode(lambda s, c: result(), code=1))
    t = pc.totals(st)
    assert t['attempts'] == 20 and t['successes'] == 20 and t['admitted'] == 0


def test_admission_rejected_batch_is_environment_and_not_requeued(tmp_path, prereg):
    def ep(cases_path, indices, out):
        out.mkdir(parents=True)
        (out / 'summary.json').write_text(json.dumps(dict(status='admission_rejected', HOST_ERROR=0, worlds=[],
                                                          error_type='PlacementRejected', rejection_table=TABLE)))
        return 1
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, episode=ep)
    t = pc.totals(st)
    assert t['attempts'] == 0 and t['env_by_kind'] == {'admission_error': 20}
    assert st['requeue'] == [] and len(st['consumed']['train']) == 20


def test_record_error_stops_collection(tmp_path, prereg):
    bad = lambda s, c: {k: v for k, v in result().items() if k != 'search_handoff'} if s == 8340003 else result()
    state, st, _ = collect(tmp_path, prereg, bad)
    assert state == 'NO_TRAIN_RECORD_ERROR' and pc.train_stop(prereg, st) == 'STOP_RECORD'
    assert len(st['batches']) == 1


def test_summary_result_carry_disagreement_is_a_record_error(tmp_path, prereg):
    class Liar(FakeEpisode):
        def __call__(self, cases_path, indices, out):
            code = super().__call__(cases_path, indices, out)
            s = json.loads((Path(out) / 'summary.json').read_text())
            s['worlds'][0]['carry_success'] = False
            (Path(out) / 'summary.json').write_text(json.dumps(s))
            return code
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, episode=Liar(lambda s, c: result()))
    assert st['attempt_rows'][0]['category'] == 'record_error'


# --------------------------------------------------------------- counts / report

def test_report_separates_S_A_N_validation_and_200_is_not_a_denominator(tmp_path, prereg):
    """Codex (2) n/200: S/N, A/N and validation S/20, A/20 are separate; pair episode unit."""
    collect(tmp_path, prereg, lambda s, c: result(success=s % 3 != 0, handoff=s % 7 == 0), max_batches=2)
    rep = json.loads((tmp_path / 'report.json').read_text())
    a = rep['A']
    assert a['attempts'] == 40 and a['successes'] < 40 and a['admitted'] < a['successes']
    assert f"물리 성공 {a['successes']} / 시도 {a['attempts']}" in a['text']
    assert f"최종 채택 {a['admitted']} / 시도 {a['attempts']}" in a['text'] and '분모가 아님' in a['text']
    assert '/ 200' not in a['text'] and 'pair episode' in rep['unit']
    assert rep['validation']['text'].startswith('validation: 물리 성공 0 / 20, 채택 0 / 20')
    assert sum(b['attempts'] for b in a['bins']) == 40
    assert set(a['by_seed_phase']) == {'primary', 'extension'}


def test_failure_subreasons_are_reported_per_bin(tmp_path, prereg):
    collect(tmp_path, prereg, lambda s, c: result(success=False) if s % 2 else result(), max_batches=1)
    rep = json.loads((tmp_path / 'report.json').read_text())
    subs = [b['failure_subreasons'] for b in rep['A']['bins']]
    assert sum(sum(x.values()) for x in subs) == 10
    assert all(set(x) <= {'carry:not_through_door:route_blocked'} for x in subs)


def test_ks_is_pair_level_over_three_groups(prereg):
    """Codex (3): success-not-admitted was dropped and the two robots were independent samples."""
    rows = []
    for i, (success, admitted) in enumerate([(False, False)] * 5 + [(True, False)] * 4 + [(True, True)] * 6):
        start = {'r1': dict(distance_m=.4 + .05 * i, yaw_offset_rad=3.), 'r2': dict(distance_m=.5, yaw_offset_rad=.1)}
        rows.append(dict(category='behavior', success=success, admitted=admitted, start=start))
    ks = pc.ks_groups(rows)
    assert ks['n'] == dict(physical_failure=5, success_not_admitted=4, admitted=6)
    assert set(ks['comparisons']) == {'physical_failure__vs__success_not_admitted',
                                      'physical_failure__vs__admitted', 'success_not_admitted__vs__admitted'}
    assert ks['comparisons']['physical_failure__vs__admitted']['distance_m']['n1'] == 5   # pairs, not robots
    assert pc.pair_values(rows[0])['distance_m'] == pytest.approx(.45)


def test_ks_statistic():
    r = pc.ks_2samp([1, 2, 3, 4], [1, 2, 3, 4])
    assert r['D'] == 0 and r['p'] == 1.
    r = pc.ks_2samp([0, 0, 0, 0, 0], [1, 1, 1, 1, 1])
    assert r['D'] == 1. and r['p'] < .05
    assert pc.ks_2samp([], [1])['D'] is None


# --------------------------------------------------------------- stop rules / decision

def test_stop_target_needs_every_bin_and_overshoot_is_kept(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, lambda s, c: result(), batch_size=25)
    t, per = pc.totals(st), pc.bin_counts(prereg, st)
    assert pc.train_stop(prereg, st) == 'STOP_TARGET' and t['admitted'] >= 200
    assert t['admitted'] == 200    # 8 batches of 25 cross 200 exactly; with batch 30 the overshoot is kept:
    assert all(per[b]['admitted'] >= 20 for b in per)
    _, st30, _ = collect(tmp_path / 'b30', prereg, lambda s, c: result(), batch_size=30)
    assert pc.totals(st30)['admitted'] == 210 and state == 'TRAIN'


def _cap_state(prereg, n_ok, skip_bin=None):
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    fail = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    rows = []
    for k in range(600):
        b = pc.bin_ids(prereg)[k % 6]
        d, y = pc.draw_start(prereg, 8340000 + k, b, 0)
        start = {'r1': dict(distance_m=d, yaw_offset_rad=y), 'r2': dict(distance_m=d, yaw_offset_rad=y)}
        rows.append(attempt_row(8340000 + k, b, ok if k < n_ok and b != skip_bin else fail, start=start))
    return ledger_state(prereg, rows)


def test_training_decision_four_tiers(prereg):
    """Owner answer 2026-10-21: 150 / per-bin 20 / 80 floor, fixed before any result."""
    t = prereg['training_decision']
    assert len(t['tiers']) == 4 and prereg['targets']['admitted_floor_pairs'] == 80
    assert '진행 가능한 최소치 150' in prereg['targets']['replaces_decision_doc']
    st = _cap_state(prereg, 180)                       # A = 180, every bin 30
    d = pc.decision(prereg, st)
    assert d['train_stop'] == 'STOP_CAP' and d['decision'] == 'TRAIN' and d['labels'] == []
    st = _cap_state(prereg, 120)                       # A = 120 -> small data
    d = pc.decision(prereg, st)
    assert pc.totals(st)['admitted'] == 120 and d['decision'] == 'TRAIN_SMALL_DATA'
    assert d['labels'] == ['소량 데이터(A<150): 결과 해석은 단계 퍼널 중심으로 제한']
    st = _cap_state(prereg, 96, skip_bin='B5')         # A = 80, B5 = 0 -> small data + range label
    d = pc.decision(prereg, st)
    assert pc.totals(st)['admitted'] == 80 and d['decision'] == 'TRAIN_SMALL_DATA'
    assert d['labels'][1] == '데이터 범위 제한(구간 부족: B0, B1, B2, B3, B4, B5)'   # 16 each, B5 0
    st = _cap_state(prereg, 78)                        # A = 78 < 80 -> no training, back to P2
    assert pc.decision(prereg, st)['decision'] == 'NO_TRAIN_BELOW_FLOOR'


def test_stop_cap_decisions_range_limited(prereg):
    # 160 admitted, B5 short of 20 -> data range limited
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    fail = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    rows = []
    for k in range(600):
        b = pc.bin_ids(prereg)[k % 6]
        d_, y = pc.draw_start(prereg, 8340000 + k, b, 0)
        start = {'r1': dict(distance_m=d_, yaw_offset_rad=y), 'r2': dict(distance_m=d_, yaw_offset_rad=y)}
        good = (k < 180 and b != 'B5') or (b == 'B5' and k < 60)
        rows.append(attempt_row(8340000 + k, b, ok if good else fail, start=start))
    st = ledger_state(prereg, rows)
    d = pc.decision(prereg, st)
    assert pc.totals(st)['admitted'] == 160
    assert d['decision'] == 'TRAIN_DATA_RANGE_LIMITED' and [x['bin'] for x in d['limited_bins']] == ['B5']
    assert d['limited_bins'][0]['cause'] == 'STOP_CAP' and d['validation'] == 'pending'
    assert d['labels'] == ['데이터 범위 제한(구간 부족: B5)']


def test_stop_seeds_with_599_attempts_after_final_host_error(tmp_path, prereg):
    """Codex (2) direct reproduction: a final HOST_ERROR consumes a seed but is not an attempt."""
    host = pc.judge(result(status='HOST_ERROR'), mode='measurement', batch_clean=False)
    fail = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    rows = [attempt_row(s, 'B0', host if s == 8340599 else fail) for s in pc.pool(prereg, 'train')]
    planned = [dict(type='batch_planned', batch=0, split='train', cases_sha256='x',
                    slots=[dict(slot=0, seed=s, bin='B0', split='train', requeue=False) for s in pc.pool(prereg, 'train')]),
               dict(type='batch_planned', batch=1, split='train', cases_sha256='x',
                    slots=[dict(slot=0, seed=8340599, bin='B0', split='train', requeue=True)])]
    st = ledger_state(prereg, planned + rows + [attempt_row(8340599, 'B0', host, batch=1)])
    assert pc.totals(st)['attempts'] == 599 and pc.totals(st)['env_failures'] == 2
    assert pc.train_stop(prereg, st) == 'STOP_SEEDS'
    assert pc.decision(prereg, st)['decision'] == 'NO_TRAIN_BELOW_FLOOR'
    assert 'STOP_SEEDS' in prereg['stop_rules']['seed_consumption_note'] and '599' in \
        prereg['stop_rules']['seed_consumption_note']


def test_stop_host_after_two_unclean_batches_and_validation_needs_host_fix(tmp_path, prereg):
    """Owner 4: STOP_HOST keeps the CAP decision rule; validation waits for the reported host fix."""
    ep = FakeEpisode(lambda s, c: result(), status=lambda n: 'HOST_ERROR' if n in (7, 8) else 'complete')
    state, st, _ = collect(tmp_path, prereg, None, episode=ep, batch_size=25)
    assert state == 'STOP_HOST' and pc.train_stop(prereg, st) == 'STOP_HOST'
    t = pc.totals(st)
    assert (t['attempts'], t['successes'], t['admitted']) == (200, 200, 150)     # unclean batches admit nothing
    assert pc.decision(prereg, st)['validation'] == 'pending' and not pc.split_rows(st, 'validation')
    state, st, _ = collect(tmp_path, prereg, None, episode=FakeEpisode(lambda s, c: result()), batch_size=25)
    assert state == 'STOP_HOST' and not pc.split_rows(st, 'validation')       # no flag: still waiting
    state, st, _ = collect(tmp_path, prereg, None, episode=FakeEpisode(lambda s, c: result()), batch_size=25,
                           validation_after_host_fix=True)
    assert len(pc.split_rows(st, 'validation')) == 20 and state == 'TRAIN'
    assert pc.totals(st)['attempts'] == 200                                    # no train attempt after STOP_HOST


def test_distance_gate_uses_admitted_starts_and_stops(prereg):
    """Owner 6 / Codex (3): gate on admitted starts, part of the stop rules, no post-hoc selection."""
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    fail = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    near = {'r1': dict(distance_m=.35, yaw_offset_rad=3.), 'r2': dict(distance_m=.45, yaw_offset_rad=3.)}
    far = {'r1': dict(distance_m=1.15, yaw_offset_rad=3.), 'r2': dict(distance_m=1.05, yaw_offset_rad=3.)}
    rows = [attempt_row(8340000 + k, 'B0', ok, start=near) for k in range(150)]
    rows += [attempt_row(8340150 + k, 'B4', fail, start=far) for k in range(20)]     # failures do not count
    st = ledger_state(prereg, rows)
    g = pc.distance_gate(prereg, st)
    assert g['robot_starts'] == 300 and not g['passed'] and g['share_over_0p8'] == 0.
    assert pc.train_stop(prereg, st) == 'STOP_DISTANCE'
    assert pc.decision(prereg, st)['decision'] == 'NO_TRAIN_DISTANCE_GATE'
    spread = [attempt_row(8341000 + k, 'B0', ok, start={'r1': dict(distance_m=.3 + .1 * (k % 9) + .05, yaw_offset_rad=3.),
                                                        'r2': dict(distance_m=1.1, yaw_offset_rad=3.)}) for k in range(18)]
    assert pc.distance_gate(prereg, ledger_state(prereg, spread))['passed']


def test_bin_limit_closes_hopeless_bin_and_marks_range_limited(tmp_path, prereg):
    """Owner 13: a bin with >= 20 attempts and < 20% carry success gets no more attempts."""
    outcome = lambda s, c: result(success=c['plan']['start_layers']['r1']['target_distance_m'] < .9)
    state, st, _ = collect(tmp_path, prereg, None, episode=FakeEpisode(outcome))
    assert set(st['limited']) == {'B4', 'B5'}
    per = pc.bin_counts(prereg, st)
    for b in ('B4', 'B5'):
        lim = st['limited'][b]
        assert lim['attempts'] >= 20 and lim['success_rate'] < .2
        assert per[b]['attempts'] == lim['attempts']          # nothing allocated after closing
    assert pc.train_stop(prereg, st) in ('STOP_TARGET', 'STOP_DISTANCE')
    d = pc.decision(prereg, st)
    assert d['decision'] in ('TRAIN_DATA_RANGE_LIMITED', 'NO_TRAIN_DISTANCE_GATE', 'NO_TRAIN_VALIDATION_INSUFFICIENT')
    assert {x['bin'] for x in d['limited_bins']} == {'B4', 'B5'}
    assert all(x['cause'] == 'bin_limited' for x in d['limited_bins'])
    rep = json.loads((tmp_path / 'report.json').read_text())
    assert {r['bin'] for r in rep['A']['bin_limited']} == {'B4', 'B5'}


def test_all_bins_limited_stops(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, lambda s, c: result(success=False))
    assert pc.train_stop(prereg, st) == 'STOP_ALL_BINS_LIMITED' and state == 'NO_TRAIN_BELOW_FLOOR'
    per = pc.bin_counts(prereg, st)
    assert all(per[b]['attempts'] >= 20 for b in per) and 120 <= pc.totals(st)['attempts'] <= 160


# --------------------------------------------------------------- allocation / seeds

def test_warmup_while_any_bin_below_four_is_round_robin(prereg):
    """Codex (4): document said 'every bin < 4', code 'any bin < 4'; v2 document = code."""
    assert 'ANY open bin' in prereg['allocation']['warmup']
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    rows = [attempt_row(8340000 + k, b, ok) for k, b in enumerate(['B0'] * 30 + ['B1', 'B2', 'B3', 'B4'] * 4)]
    st = ledger_state(prereg, rows)
    st['last_rr'] = 0
    assert pc.allocate(prereg, st, 6) == ['B1', 'B2', 'B3', 'B4', 'B5', 'B0']


def test_deficit_uses_admitted_counts_and_is_deterministic(prereg):
    """Codex (4): success_b vs eligible — v2 uses A_b in allocation and stop rules."""
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    hand = pc.judge(result(handoff=True), mode='measurement', batch_clean=True)
    rows = []
    for k, b in enumerate(pc.bin_ids(prereg) * 4):
        rows.append(attempt_row(8340000 + k, b, hand if b == 'B2' else ok))   # B2 successes are never admitted
    st = ledger_state(prereg, rows)
    slots = pc.allocate(prereg, st, 20)
    assert slots == pc.allocate(prereg, st, 20)
    assert slots.count('B2') > slots.count('B0')


def test_in_order_seed_consumption_and_cap(tmp_path, prereg):
    state, st, ep = collect(tmp_path, prereg, lambda s, c: result(success=False, grasp=s % 4 == 0),
                            make_cases=make(prereg))
    seen = [s['seed'] for b in sorted(st['batches']) for s in st['batches'][b]['slots'] if s['split'] == 'train']
    assert seen == sorted(seen) and seen[0] == 8340000
    assert pc.totals(st)['attempts'] <= 600


def test_measurement_mode_uses_pilot_seeds_only(tmp_path, prereg):
    """Owner 8 / Codex (3): measurement ran validation first in v1."""
    state, st, _ = collect(tmp_path, prereg, lambda s, c: result(), mode='measurement')
    assert state == 'PILOT_DONE'
    assert set(st['consumed']) == {'pilot'} and st['consumed']['pilot'] == set(range(8343000, 8343040))
    assert all(r['bin'] == pc.bin_ids(prereg)[(r['seed'] - 8343000) % 6] for r in st['attempt_rows'])
    rep = json.loads((tmp_path / 'report.json').read_text())
    assert '수율 측정, 시연 아님' in rep['pilot']['text'] and 'A' not in rep
    assert [r['seed'] for r in pc.probe_slots(st)] == [8343000, 8343001, 8343002]


def test_validation_runs_only_after_train_stop_and_gate(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, lambda s, c: result())
    order = [st['batches'][k]['split'] for k in sorted(st['batches'])]
    assert order[0] == 'train' and order[-1] == 'validation' and order.index('validation') == len(order) - 1
    assert state == 'TRAIN' and pc.decision(prereg, st)['validation']['passed']
    # too few admitted validation episodes -> NO_TRAIN_VALIDATION_INSUFFICIENT
    outcome = lambda s, c: result(success=s < 8341000 or s < 8341005)
    state, st, _ = collect(tmp_path / 'v', prereg, None, episode=FakeEpisode(outcome))
    assert state == 'NO_TRAIN_VALIDATION_INSUFFICIENT'
    assert pc.decision(prereg, st)['validation']['admitted'] == 5


def test_validation_stage_coverage_is_required(prereg):
    ok = pc.judge(result(), mode='training', batch_clean=True, sidecar=dict(passed=True))
    rows = [attempt_row(8341000 + k, 'B0', ok, split='validation') for k in range(10)]
    for r in rows:
        r['sidecar'] = dict(passed=True, stages={'r1': ['approach', 'carry'], 'r2': ['complete']})
    g = pc.validation_gate(prereg, ledger_state(prereg, rows))
    assert g['admitted'] == 10 and not g['passed'] and 'place' in g['missing_stages']


# --------------------------------------------------------------- restart / crash recovery

def test_restart_continues_and_matches_one_shot_run(tmp_path, prereg):
    outcome = lambda s, c: result(success=s % 3 == 0)
    _, one, _ = collect(tmp_path / 'one', prereg, outcome, max_batches=6)
    for _ in range(6):
        collect(tmp_path / 'two', prereg, outcome, max_batches=1)
    two = pc.replay(prereg, pc.read_ledger(tmp_path / 'two' / 'ledger.jsonl'))
    assert pc.totals(one) == pc.totals(two)
    assert [b['slots'] for b in one['batches'].values()] == [b['slots'] for b in two['batches'].values()]


def test_case_generation_crash_is_recoverable(tmp_path, prereg):
    """Codex follow-up counterexample 2: b000 left behind by a crash during make_cases -> FileExistsError."""
    def boom(slots):
        raise RuntimeError('simulated termination during make_cases')
    with pytest.raises(RuntimeError):
        collect(tmp_path, prereg, None, make_cases=boom, max_batches=1, episode=FakeEpisode(lambda s, c: result()))
    assert not (tmp_path / 'batches').exists()
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, episode=FakeEpisode(lambda s, c: result()))
    assert pc.totals(st)['attempts'] == 20


def test_crash_after_batch_planned_regenerates_identical_cases(tmp_path, prereg):
    calls = []

    def ep_crash(cases_path, indices, out):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        collect(tmp_path, prereg, None, max_batches=1, episode=ep_crash)
    (tmp_path / 'batches' / 'b000' / 'cases.json').unlink()      # lost with the crash
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, episode=FakeEpisode(lambda s, c: result()))
    assert pc.totals(st)['attempts'] == 20
    path = tmp_path / 'batches' / 'b000' / 'cases.json'
    path.write_text(path.read_text().replace('8340001', '8340999'))
    with pytest.raises(ValueError, match='sha256'):
        runner.batch_cases(path.parent, st['batches'][0], st['batches'][0]['slots'], make(prereg))
    assert calls == []


def test_finished_but_uningested_batch_is_ingested_not_rerun(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result())
    collect(tmp_path, prereg, None, max_batches=1, episode=ep)
    rows = pc.read_ledger(tmp_path / 'ledger.jsonl')
    keep = [r for r in rows if r['type'] not in ('attempt', 'batch_done')]
    (tmp_path / 'ledger.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in keep))
    ep2 = FakeEpisode(lambda s, c: result())
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, episode=ep2)
    assert pc.totals(st)['attempts'] == 40 and len(ep2.calls) == 1      # b000 ingested, one new batch


def test_interrupted_batch_retries_once_then_closes(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result(), crash_first=2)
    collect(tmp_path, prereg, None, max_batches=3, episode=ep)
    st = pc.replay(prereg, pc.read_ledger(tmp_path / 'ledger.jsonl'))
    b0 = st['batches'][0]
    assert b0['done'] and b0['clean'] is False
    assert pc.totals(st)['env_by_kind'] == {'host_error': 20}
    assert len(st['requeue']) == 0 or all(q['split'] == 'train' for q in st['requeue'])


def test_host_error_world_is_requeued_once_with_same_seed_and_bin(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result(), drop_seeds=[8340003])
    _, st, _ = collect(tmp_path, prereg, None, max_batches=2, episode=ep)
    b1 = st['batches'][1]['slots']
    assert b1[0]['seed'] == 8340003 and b1[0]['requeue'] and b1[0]['bin'] == st['batches'][0]['slots'][3]['bin']
    assert st['batches'][0]['clean'] is False       # batch with a lost world admits nothing
    assert pc.totals(st)['admitted'] == 20          # batch 1 (clean) only


def test_setup_rejection_is_in_the_ledger_and_consumes_the_seed(tmp_path, prereg):
    """Codex (4) / owner 11: generator budget exhaustion failed before the ledger."""
    def cases(slots):
        return [dict(setup_rejected=dict(rejected={'beam_cargo_overlap': 5000}, gates=[], proposals=5000,
                                         reproduce=['python', 'collect_cases.py']))
                if s['seed'] == 8340002 else case_for(prereg, s) for s in slots]
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, make_cases=cases,
                       episode=FakeEpisode(lambda s, c: result()))
    assert [r['seed'] for r in st['setup_rows']] == [8340002]
    assert 8340002 in st['consumed']['train'] and len(st['batches'][0]['slots']) == 19
    assert pc.totals(st)['attempts'] == 19
    rep = json.loads((tmp_path / 'report.json').read_text())
    assert rep['setup_rejections']['n'] == 1


def test_ledger_header_must_not_change(tmp_path, prereg):
    collect(tmp_path, prereg, lambda s, c: result(), max_batches=1)
    with pytest.raises(ValueError, match='header mismatch'):
        runner.run(tmp_path, prereg, 'sha', mode='training', noise='off', batch_size=10, max_batches=1,
                   make_cases=make(prereg), run_episode=FakeEpisode(lambda s, c: result()))


def test_deadline_stops_before_new_batch(tmp_path, prereg):
    import datetime as dt
    t0 = dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc)
    state, st, _ = collect(tmp_path, prereg, lambda s, c: result(), deadline=t0, now=lambda: t0)
    assert state == 'DEADLINE' and not st['batches']


# --------------------------------------------------------------- report / convert sha binding

def test_report_and_convert_refuse_another_prereg_sha(tmp_path, prereg):
    """Repo audit 2 / Codex counterexample 3: report relabelled the ledger under a new sha."""
    collect(tmp_path, prereg, lambda s, c: result(), max_batches=1)
    st = pc.replay(prereg, pc.read_ledger(tmp_path / 'ledger.jsonl'))
    with pytest.raises(ValueError, match='prereg sha256'):
        pc.report(prereg, st, prereg_sha='different-frozen-sha')
    with pytest.raises(ValueError, match='prereg sha256'):
        pc.convert_input(prereg, st, tmp_path / 'conv', prereg_sha='different-frozen-sha', teacher_sha='t')
    assert pc.report(prereg, st, prereg_sha='sha')['prereg_sha256'] == 'sha'


def test_convert_input_only_after_trainable_decision(tmp_path, prereg):
    collect(tmp_path, prereg, lambda s, c: result(), max_batches=1)
    st = pc.replay(prereg, pc.read_ledger(tmp_path / 'ledger.jsonl'))
    with pytest.raises(ValueError, match='COLLECTING'):
        pc.convert_input(prereg, st, tmp_path / 'c0', prereg_sha='sha', teacher_sha='t')
    outcome = lambda s, c: result(success=s % 5 != 0)
    state, st, _ = collect(tmp_path / 'full', prereg, None, episode=FakeEpisode(outcome))
    assert state == 'TRAIN'
    proto = pc.convert_input(prereg, st, tmp_path / 'conv', prereg_sha='sha', teacher_sha='abc')
    admitted = [r for r in st['attempt_rows'] if r['admitted']]
    assert len(proto['train_seeds']) + len(proto['validation_seeds']) == len(admitted)
    assert all(s % 5 != 0 for s in proto['train_seeds'] + proto['validation_seeds'])
    assert proto['prereg_sha256'] == 'sha' and proto['decision'] == 'TRAIN' and not proto['data_range_limited']
    assert all(8341000 <= s <= 8341019 for s in proto['validation_seeds'])
    assert (tmp_path / 'conv' / f"seed-{proto['train_seeds'][0]}" / 'raw').is_symlink()


# --------------------------------------------------------------- manifest / episode command

def test_episode_command_needs_absolute_rejection_table_and_cap():
    """Codex (4) audit outputs: the queue's rejection_table must be an absolute path."""
    a = pc.episode_cmd_audit(EP_CMD)
    assert a['rejection_table_input'].startswith('/') and a['cap_s'] == 60.
    assert a['template_sha256'] == hashlib.sha256(EP_CMD.encode()).hexdigest()
    with pytest.raises(ValueError, match='absolute'):
        pc.episode_cmd_audit(EP_CMD.replace('/home/ugrp/ugrp-sim/runs', 'runs'))
    with pytest.raises(ValueError, match='--cap-s'):
        pc.episode_cmd_audit(EP_CMD.replace('--cap-s 60 ', ''))
    with pytest.raises(ValueError, match='{out}'):
        pc.episode_cmd_audit(EP_CMD.replace('{out}', 'x'))


def test_run_manifest_draft_is_complete_except_vm_fields_and_blocks_training(prereg):
    """Codex (4) / owner 10: one RUN_MANIFEST.json frozen with the prereg."""
    m = json.loads((EXP / 'RUN_MANIFEST.json').read_text())
    for key in ('stack', 'collector', 'generator', 'command', 'limits', 'assets', 'host', 'smoke', 'recording_check',
                'prereg'):
        assert key in m, key
    unfilled = pc.manifest_unfilled(m)
    assert unfilled and all(p.split('.')[0] in ('host', 'assets', 'smoke', 'recording_check', 'command', 'collector',
                                                'prereg', 'generator', 'stack', 'seed_check') for p in unfilled)
    assert pc.check_run_manifest(m, mode='measurement', prereg_sha='x') == []
    with pytest.raises(ValueError, match='unfilled'):
        pc.check_run_manifest(m, mode='training', prereg_sha='x')
    filled = json.loads(json.dumps(m, ensure_ascii=False).replace(pc.VM_FILL, 'v'))
    filled['status'] = 'FROZEN'
    filled['prereg']['sha256'] = 'sha'
    filled['collector']['source_sha'] = 'c'
    filled['command']['episode_template_sha256'] = pc.episode_cmd_audit(EP_CMD)['template_sha256']
    filled['command']['batch_size'] = 20
    assert pc.check_run_manifest(filled, mode='training', prereg_sha='sha', collector_sha='c',
                                 episode=pc.episode_cmd_audit(EP_CMD), batch_size=20) == []
    with pytest.raises(ValueError, match='prereg sha256 differs'):
        pc.check_run_manifest(filled, mode='training', prereg_sha='other')
    with pytest.raises(ValueError, match='batch size'):
        pc.check_run_manifest(filled, mode='training', prereg_sha='sha', batch_size=25)
    s = m['stack']
    assert s['teacher']['branch'] == 'dsh/pairact-p2-carrypath-c2' and s['adapter']['branch'] == 'dsh/pairact-p2-carrypath-a-c2'
    assert s['root']['branch'] == 'dsh/pairact-p2-carrypath-r-c2'


def test_run_manifest_file_hashes_match_this_checkout():
    """The frozen manifest names the exact collector / generator files (stale hash = test failure)."""
    m = json.loads((EXP / 'RUN_MANIFEST.json').read_text())
    files = dict(m['collector']['file_sha256'], **{m['generator']['file']: m['generator']['file_sha256']})
    for path, sha in files.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path


def test_eval_prereg_heldout_rule_matches_collection(prereg):
    """Codex (3) heldout: rule A static check, no replacement, no access before the checkpoint freeze."""
    e = json.loads((EXP / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json').read_text())
    assert (e['seeds']['first'], e['seeds']['last']) == (prereg['seeds']['heldout']['first'],
                                                         prereg['seeds']['heldout']['last'])
    ex = e['exclusions']
    assert 'rule A' in ex['pre_run_static_check'] and 'no replacement' in ex['denominator']
    assert 'checkpoint' in e['heldout_access'] and 'never collected' in e['seeds']['rule']
    assert 'rule A' in prereg['heldout_link']


# ------------------------------------------------- recording (-c stack) hand-off

def test_collect_env_only_in_training_and_needs_check(tmp_path, monkeypatch):
    monkeypatch.setenv('PAIRACT_P3_COLLECT_PREREG', '/stale')
    env = runner.collect_env('measurement', PREREG, 'sha')
    assert not any(k in env for k in pc.COLLECT_ENV)          # measurement: recording off, stale env cleared
    with pytest.raises(ValueError, match='recording-check'):
        runner.collect_env('training', PREREG, 'sha')
    check = tmp_path / 'check.json'
    check.write_text('{}')
    env = runner.collect_env('training', PREREG, 'sha', check)
    assert env['PAIRACT_P3_COLLECT_PREREG_SHA256'] == 'sha' and env['PAIRACT_P3_RECORDING_PROBE'] == '0'
    assert env['PAIRACT_P3_RECORDING_CHECK'] == str(check.resolve())
    probe = runner.collect_env('training', PREREG, 'sha', probe=True)
    assert probe['PAIRACT_P3_RECORDING_PROBE'] == '1' and 'PAIRACT_P3_RECORDING_CHECK' not in probe
    assert pc.CANDIDATE_BY_MODE == {'measurement': 'pairact_p2_r13', 'training': 'pairact_p3_collect'}


def test_check_rows():
    res = dict(result(), source_sha='t', teacher_profile='visible_only', search20='search20_v1',
               observation_sampling={'rgb_size': [640, 480], 'rgb_hz': 10}, physical_success=True)
    row = pc.check_row(res, 8343001, search15_keys=['search20'])
    assert row['index'] == 8343001 and row['exit'] == 0 and row['search20'] == 'search20_v1'
    assert row['observation_sampling']['rgb_size'] == [640, 480]


# ------------------------------------------------- case generator (setup only)

def _geometry():
    import sys
    sys.path.insert(0, str(EXP))
    try:
        import collect_cases as cc
        return cc, cc.Geometry(setup_validity=False)
    except ModuleNotFoundError as error:
        pytest.skip(f'geometry imports unavailable: {error}')


def test_collect_cases_geometry_respects_bins_and_carries_audit(prereg):
    cc, geo = _geometry()
    for b in pc.bins(prereg):
        for seed in (8340000, 8340001, 8340599):
            case = cc.make_case(geo, prereg, dict(seed=seed, bin=b['id'], split='train'))
            plan = case['plan']
            assert plan['seed'] == seed and plan['collect_bin'] == b['id'] and case['candidate'] == 'pairact_p2_r13'
            assert plan['roles']['r1'] == cc.role_of(seed)
            for rid in ('r1', 'r2'):
                d = math.dist(plan['spawns'][rid][:2], plan['assigned_end_xy'][rid])
                assert abs(d - plan['start_layers'][rid]['target_distance_m']) < 1e-9
                assert pc.bin_of(prereg, d, plan['start_layers'][rid]['yaw_bin']['offset_rad']) == b['id']
            assert case == cc.make_case(geo, prereg, dict(seed=seed, bin=b['id'], split='train'))
            audit = plan['setup_audit']
            assert [g['gate'] for g in audit['gates']] == list(cc.GATES)
            assert audit['gates'][-1]['passed_cumulative'] == 1 and audit['proposals'] == plan['proposal_attempts']
            assert audit['reproduce'][1].endswith('collect_cases.py') and audit['generator']['file_sha256']
    for k in range(6):
        roles = {cc.role_of(8340000 + k + 6 * j) for j in range(20)}
        assert roles == {'teal', 'blue'}


def test_collect_cases_budget_exhaustion_returns_ledger_audit(prereg, monkeypatch):
    cc, geo = _geometry()
    monkeypatch.setattr(cc, 'PROPOSALS', 30)
    geo.validity = lambda pose: dict(accepted=False)
    out = cc.make_cases(geo, prereg, [dict(seed=8340000, bin='B0', split='train')])
    audit = out[0]['setup_rejected']
    assert audit['seed'] == 8340000 and audit['proposals'] == 30
    gates = {g['gate']: g for g in audit['gates']}
    assert gates['placement_graspable_filter']['rejected'] == sum(audit['rejected'].values()) - \
        audit['rejected'].get('beam_static_overlap', 0) - audit['rejected'].get('beam_cargo_overlap', 0)
    assert sum(audit['rejected'].values()) == 30
    assert any(k.startswith('placement_graspable_filter:') for k in audit['blocked_objects'])
    assert audit['reproduce'] and audit['generator']['file_sha256']


# ------------------------------------------------- v3: Codex v2 re-review B4 / B5

def _real_rejection_cases(prereg, monkeypatch, reject_seeds):
    """make_cases through the real generator: rejected seeds exhaust a 30-proposal budget (real audit payload)."""
    cc, geo = _geometry()
    monkeypatch.setattr(cc, 'PROPOSALS', 30)

    def cases(slots):
        out = []
        for s in slots:
            geo.validity = (lambda pose: dict(accepted=False, ends={})) if s['seed'] in reject_seeds else None
            out.extend(cc.make_cases(geo, prereg, [{k: v for k, v in s.items() if k != 'slot'}]))
        return out
    return cases


def test_real_generator_setup_rejection_is_written_not_typeerror(tmp_path, prereg, monkeypatch):
    """B4: the real audit carries seed/bin/split; v2 expanded it next to the same keywords -> TypeError."""
    cases = _real_rejection_cases(prereg, monkeypatch, {8340002})
    audit = cases([dict(seed=8340002, bin='B2', split='train')])[0]['setup_rejected']
    assert {'seed', 'bin', 'split'} <= set(audit)                       # the payload that broke v2
    with pytest.raises(TypeError):
        dict(type='setup_rejected', seed=8340002, bin='B2', split='train', **audit)
    _, st, _ = collect(tmp_path, prereg, None, max_batches=1, make_cases=cases,
                       episode=FakeEpisode(lambda s, c: result()))
    rows = st['setup_rows']
    assert [r['seed'] for r in rows] == [8340002] and rows[0]['planning_batch'] == 0
    assert rows[0]['gates'] and rows[0]['reproduce'] and rows[0]['requeue'] is False
    assert pc.totals(st)['attempts'] == 19


def test_setup_rejected_row_refuses_a_disagreeing_audit():
    with pytest.raises(ValueError, match='seed'):
        runner.setup_rejected_row(0, dict(seed=1, bin='B0', split='train'), dict(seed=2, bin='B0', split='train'))
    row = runner.setup_rejected_row(3, dict(seed=1, bin='B0', split='train', requeue=True), dict(proposals=5))
    assert row == dict(proposals=5, type='setup_rejected', planning_batch=3, seed=1, bin='B0', split='train',
                       requeue=True)


def test_setup_rejected_requeue_slot_leaves_the_queue(tmp_path, prereg, monkeypatch):
    """B5: a host-error seed re-queued once and then rejected by the generator is never selected again."""
    cases = _real_rejection_cases(prereg, monkeypatch, set())
    calls = []

    def flaky(slots):
        calls.append([(s['seed'], bool(s.get('requeue'))) for s in slots])
        out = cases(slots)
        return [dict(setup_rejected=dict(seed=s['seed'], bin=s['bin'], split=s['split'], proposals=30))
                if s.get('requeue') else c for s, c in zip(slots, out)]
    ep = FakeEpisode(lambda s, c: result(), drop_seeds=[8340003])
    _, st, _ = collect(tmp_path, prereg, None, max_batches=3, make_cases=flaky, episode=ep)
    rej = [r for r in st['setup_rows'] if r['seed'] == 8340003]
    assert len(rej) == 1 and rej[0]['requeue'] is True
    assert st['requeue'] == []
    planned = [s['seed'] for b in st['batches'].values() for s in b['slots']]
    assert planned.count(8340003) == 1                                   # only the original slot
    assert sum(c.count((8340003, True)) for c in calls) == 1              # re-queued once, then gone
