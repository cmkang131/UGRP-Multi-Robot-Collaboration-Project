"""Cross-review repro (Claude, 2026-10-21) of COLLECT_PREREG v3s, flipped for v4 (dsh/pairact-carry-r1-v4).

X1-X8 first pinned the v3s behaviour flagged in outputs/reports/claude-arch-parallel-20261019/
t2-prereg-xreview.md (8 passed on 6a68e4ca8).  v4 fixes B1-B3 and R1-R3 (owner decisions 2026-10-21,
CODEX_RESPONSE_V4.md); each test now pins the fixed behaviour.  X7 keeps the disclosed lag effect
(R4) and pins that the stop is the stop of the drained data.
"""
import json
import random

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import PREREG, FakeEpisode, attempt_row, collect, make, case_for, result, runner
from test_pairact_collect_shard import merged_rows, run_cooperative


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


OK = dict(pc.judge(result(), mode='measurement', batch_clean=True))
FAIL = dict(pc.judge(result(success=False), mode='measurement', batch_clean=True))


def _ledger(prereg, attempts, extra=()):
    slots = [dict(slot=i, seed=r['seed'], bin=r['bin'], split=r['split'], requeue=False) for i, r in enumerate(attempts)]
    rows = [pc.header('sha', mode='training', noise='off', batch_size=20),
            dict(type='batch_planned', batch=0, split='train', cases_sha256='x', slots=slots)]
    rows += [dict(r, slot=i) for i, r in enumerate(attempts)] + list(extra)
    return pc.replay(prereg, rows)


def _start(d):
    return {'r1': dict(distance_m=d, yaw_offset_rad=3.), 'r2': dict(distance_m=d, yaw_offset_rad=3.)}


def _sharded(tmp_path, prereg, k, episode_factory, seed, **kw):
    run_cooperative(tmp_path, prereg, k, {i: episode_factory() for i in range(k)}, rng=random.Random(seed), **kw)
    rows, rep, meta = merged_rows(tmp_path, prereg, k)
    return rows, pc.replay(prereg, rows), rep, meta


# X1 (BLOCKER B1, v4 fixed): train_closed can no longer change the decision class.  It is written only on
# the drained view, equals train_stop of the final data, and a ledger where it disagrees is refused.
def test_x1_train_closed_cannot_change_the_decision_class(tmp_path, prereg):
    rows = [attempt_row(8340000 + k, pc.bin_ids(prereg)[k % 6], OK, start=_start(.35 + .1 * (k % 9)))
            for k in range(160)]
    st = _ledger(prereg, rows, extra=[dict(type='train_closed', planning_batch=8, stop='STOP_DISTANCE')])
    assert pc.distance_gate(prereg, st)['passed'] and pc.train_stop(prereg, st) is None
    with pytest.raises(ValueError, match='disagrees'):
        pc.decision(prereg, st)
    from test_pairact_collect_shard import outcome
    _, st_serial, _ = collect(tmp_path / 'serial', prereg, None, episode=FakeEpisode(outcome))
    serial = pc.decision(prereg, st_serial)
    for k, seed in ((2, 1), (3, 1)):
        rows, st, rep, meta = _sharded(tmp_path / f'k{k}', prereg, k, lambda: FakeEpisode(outcome), seed)
        held = [r for r in rows if r['type'] == 'train_barrier' and r['action'] == 'hold']
        closed = next(r for r in rows if r['type'] == 'train_closed')
        assert held and held[0]['planning_batch'] < closed['planning_batch']      # the lagged stop was held ...
        assert closed['stop'] == pc.train_stop(prereg, st)                        # ... and fixed on the drained data
        assert meta['finished'] and pc.decision(prereg, st)['decision'] == serial['decision']   # same class as serial
        assert pc.decision(prereg, st)['train_stop'] == serial['train_stop'] == 'STOP_TARGET'


# X2 (BLOCKER B2, v4 fixed): STOP_SEEDS seen while the last batch is in flight is held; its HOST_ERROR
# re-queue runs before the stop is fixed, as in the serial run.
def test_x2_stop_seeds_waits_for_the_in_flight_requeue(tmp_path, prereg):
    def outcome(seed, case):
        return result(success=seed % 4 == 0)

    def cases(slots):        # 10% setup rejections: seeds run out before the 600 attempt cap
        return [dict(setup_rejected=dict(rejected={'x': 1}, gates=[], proposals=1, reproduce=['x']))
                if s['seed'] % 10 == 0 else case_for(prereg, s) for s in slots]
    drop = [8340599]
    serial_state, st_serial, _ = collect(tmp_path / 'serial', prereg, None, make_cases=cases,
                                         episode=FakeEpisode(outcome, drop_seeds=drop))
    rows, st_k2, rep, meta = _sharded(tmp_path / 'k2', prereg, 2, lambda: FakeEpisode(outcome, drop_seeds=drop), 1,
                                      make_cases=cases)
    assert pc.train_stop(prereg, st_serial) == pc.train_stop(prereg, st_k2) == 'STOP_SEEDS'
    rq = lambda st: [r for r in pc.split_rows(st, 'train') if r['requeue']]
    assert len(rq(st_serial)) == len(rq(st_k2)) == 1                               # re-queued once in both
    assert pc.totals(st_serial)['attempts'] == pc.totals(st_k2)['attempts']
    assert pc.decision(prereg, st_serial)['decision'] == pc.decision(prereg, st_k2)['decision']
    assert any(r['type'] == 'train_barrier' and r['stop'] == 'STOP_SEEDS' for r in rows)


# X3 (BLOCKER B3, v4 fixed): one HOST_ERROR world in the validation batch re-queues every judged world of
# that batch once (environment, not in N); the clean re-run is judged and admitted -> TRAIN.
def test_x3_one_host_error_in_validation_batch_is_requeued(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, None, episode=FakeEpisode(lambda s, c: result(), drop_seeds=[8341003]))
    v = pc.totals(st, 'validation')
    assert (v['attempts'], v['successes'], v['admitted'], v['env_failures']) == (20, 20, 20, 20)
    assert v['env_by_kind'] == {'host_error': 1, 'unclean_batch_requeue': 19}
    assert state == 'TRAIN'


# X4 (권고 R1, v4 fixed): bin_limit reads A_b / N_b like the allocation; a bin with physical successes but
# no admissions is limited and gets no slot.
def test_x4_bin_with_successes_but_no_admissions_is_limited(prereg):
    handoff_ok = dict(pc.judge(result(handoff=True), mode='measurement', batch_clean=True))
    rows = []
    for k, b in enumerate(b for b in pc.bin_ids(prereg) for _ in range(30)):
        i = k % 30
        if b == 'B5':
            j = handoff_ok if i < 15 else FAIL
        else:
            j = OK if i < 10 else FAIL
        rows.append(attempt_row(8340000 + k, b, j))
    st = _ledger(prereg, rows)
    lim = pc.pending_bin_limits(prereg, st)
    assert pc.bin_counts(prereg, st)['B5']['admitted'] == 0 and [r['bin'] for r in lim] == ['B5']
    assert lim[0]['admitted_rate'] == 0 and lim[0]['success_rate'] == .5           # S/N reported only
    st = _ledger(prereg, rows, extra=lim)
    assert 'B5' not in pc.allocate(prereg, st, 20)


# X5 (권고 R2, v4 fixed): with B4 and B5 both bin_limited the 0.9-1.2 m band leaves the distance gate
# (denominator, cells, scaled share) and the result carries the label.
def test_x5_both_far_bins_limited_leave_the_distance_gate(prereg):
    rows, k = [], 0
    for b, n, ok in (('B0', 38, 38), ('B1', 38, 38), ('B2', 38, 38), ('B3', 38, 38), ('B4', 20, 3), ('B5', 20, 3)):
        for i in range(n):
            seed = 8340000 + k
            d0, _y = pc.draw_start(prereg, seed, b, 0)
            d1, _y = pc.draw_start(prereg, seed, b, 1)
            rows.append(attempt_row(seed, b, OK if i < ok else FAIL,
                                    start={'r1': dict(distance_m=d0, yaw_offset_rad=3.),
                                           'r2': dict(distance_m=d1, yaw_offset_rad=3.)}))
            k += 1
    st = _ledger(prereg, rows)
    assert pc.totals(st)['admitted'] == 158 and not pc.distance_gate(prereg, st)['passed']     # not limited yet
    lim = pc.pending_bin_limits(prereg, st)
    assert sorted(r['bin'] for r in lim) == ['B4', 'B5']
    st = _ledger(prereg, rows, extra=lim)
    g = pc.distance_gate(prereg, st)
    assert g['range_excluded'] == [[0.9, 1.2]] and g['robot_starts'] == 152 * 2
    assert g['min_share_required'] == pytest.approx(.25 * (.1 / .6) / (.4 / .9))
    assert g['share_over_0p8'] < .25 and g['passed'] and '거리 관문 축소' in g['label']
    st = _ledger(prereg, rows, extra=[r for r in lim if r['bin'] == 'B5'])        # one far bin open: no exclusion
    assert pc.distance_gate(prereg, st)['range_excluded'] == []


# X6 (정보/R5, v4 fixed): validation is planned only after train_closed, never with a train batch in flight.
def test_x6_validation_never_planned_with_train_batches_in_flight(tmp_path, prereg):
    rows, st, rep, meta = _sharded(tmp_path, prereg, 3, lambda: FakeEpisode(lambda s, c: result()), 5)
    planned = {r['batch']: r['split'] for r in rows if r['type'] == 'batch_planned'}
    v = min(j for j, s in planned.items() if s == 'validation')
    assert not any(planned.get(j) == 'train' for j in range(v - 2, v))
    closed = next(i for i, r in enumerate(rows) if r['type'] == 'train_closed')
    first_val = next(i for i, r in enumerate(rows) if r['type'] == 'batch_planned' and r['split'] == 'validation')
    assert closed < first_val and rep['run_state'] == 'TRAIN'


# X7 (권고 R4 + owner decision D-v4-1): bin_limit reads lagged counts, so a hopeless bin gets more attempts
# with K > 1 (disclosed).  With STOP_DISTANCE deferred until B4 / B5 are settled, serial, K = 2 and K = 3 end in
# the same class on this fake; K = 4 still does not (lagged bin_limit closes B2 and B4 at 2/22, 2/21 on this
# seed-periodic fake -> STOP_DISTANCE, A 181), so K is capped at 3 (prereg sharding.K_max, disclosed in sharding.K).
def test_x7_serial_k2_k3_same_class_and_k4_is_the_disclosed_case(tmp_path, prereg):
    from test_pairact_collect_shard import outcome
    _, st_serial, _ = collect(tmp_path / 'serial', prereg, None, episode=FakeEpisode(outcome))
    serial = pc.decision(prereg, st_serial)
    assert (serial['train_stop'], pc.totals(st_serial)['admitted']) == ('STOP_TARGET', 204)
    n = lambda st: pc.bin_counts(prereg, st)['B5']['attempts']
    got = {}
    for k in (2, 3, 4):
        rows, st, rep, meta = _sharded(tmp_path / f'k{k}', prereg, k, lambda: FakeEpisode(outcome), 2)
        closed = next(r for r in rows if r['type'] == 'train_closed')
        assert closed['stop'] == pc.train_stop(prereg, st) and closed['admitted'] == pc.totals(st)['admitted']
        assert 'B5' in st['limited'] and n(st) > n(st_serial)                 # disclosed lag effect (22 serial)
        got[k] = (pc.decision(prereg, st)['decision'], pc.totals(st)['admitted'])
    assert got[2] == (serial['decision'], 218) and got[3] == (serial['decision'], 235)
    assert got[4] == ('NO_TRAIN_DISTANCE_GATE', 181) != (serial['decision'], 204)
    assert pc.MAX_SHARDS == prereg['sharding']['K_max'] == 3
    assert 'K = 4 ends STOP_DISTANCE' in prereg['sharding']['K']


# X8 (권고 R3, v4 fixed): a permanently broken shard triggers STOP_HOST through stop_rules.shard_host
# (3 unclean in a row of its own batches) long before the cap.
def test_x8_one_broken_shard_triggers_stop_host(tmp_path, prereg):
    ok = lambda s, c: result(success=s % 3 == 0)
    eps = {0: FakeEpisode(ok), 1: FakeEpisode(ok, status='HOST_ERROR')}
    states = run_cooperative(tmp_path, prereg, 2, eps, rng=random.Random(4))
    rows, rep, meta = merged_rows(tmp_path, prereg, 2)
    st = pc.replay(prereg, rows)
    unclean = [k for k, b in st['batches'].items() if b['split'] == 'train' and b['done'] and not b['clean']]
    d = pc.decision(prereg, st)
    assert d['train_stop'] == 'STOP_HOST' and set(states.values()) == {rep['run_state']} == {'NO_TRAIN_BELOW_FLOOR'}
    assert [s['shard'] for s in d['host_stop']['shards']] == [1] and len(unclean) == 3
    assert pc.totals(st)['attempts'] < 200
