"""Cross-review repro (Claude, 2026-10-21) of COLLECT_PREREG v3s (dsh/pairact-carry-r1-v3-shard 6a68e4ca8).

These tests pin the *current* behaviour that the review flags (outputs/reports/claude-arch-parallel-20261019/
t2-prereg-xreview.md).  They pass on 6a68e4ca8; a fix should flip the marked assertion.  No collector
code is changed here.
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


# X1 (BLOCKER a/c): train_closed is only the LAST fallback of train_stop; the final decision is
# re-evaluated on data that includes in-flight batches finished after the close.
def test_x1_sharded_stop_distance_close_can_end_as_train(prereg):
    # 160 admitted, distances spread so the distance gate passes on the FINAL set
    rows = [attempt_row(8340000 + k, pc.bin_ids(prereg)[k % 6], OK, start=_start(.35 + .1 * (k % 9)))
            for k in range(160)]
    st = _ledger(prereg, rows, extra=[dict(type='train_closed', planning_batch=8, stop='STOP_DISTANCE')])
    assert pc.distance_gate(prereg, st)['passed']
    d = pc.decision(prereg, st)
    assert d['train_stop'] == 'STOP_DISTANCE'                      # the recorded stop ...
    assert d['decision'] == 'TRAIN'                                # ... but not NO_TRAIN_DISTANCE_GATE (per_stop)
    assert 'NO_TRAIN_DISTANCE_GATE' in prereg['training_decision']['per_stop']['STOP_DISTANCE']


# X2 (BLOCKER a/c): with K > 1, STOP_SEEDS is seen while the last batch is in flight, so its
# HOST_ERROR re-queue is never run; the serial run re-queues it ("re-queued as in the serial run").
def test_x2_stop_seeds_drops_in_flight_requeue(tmp_path, prereg):
    def outcome(seed, case):
        return result(success=seed % 4 == 0)

    def cases(slots):        # 10% setup rejections: seeds run out before the 600 attempt cap
        return [dict(setup_rejected=dict(rejected={'x': 1}, gates=[], proposals=1, reproduce=['x']))
                if s['seed'] % 10 == 0 else case_for(prereg, s) for s in slots]
    drop = [8340599]
    serial_state, st_serial, _ = collect(tmp_path / 'serial', prereg, None, make_cases=cases,
                                         episode=FakeEpisode(outcome, drop_seeds=drop))
    eps = {i: FakeEpisode(outcome, drop_seeds=drop) for i in range(2)}
    run_cooperative(tmp_path / 'k2', prereg, 2, eps, rng=random.Random(1), make_cases=cases)
    rows, rep, meta = merged_rows(tmp_path / 'k2', prereg, 2)
    st_k2 = pc.replay(prereg, rows)
    assert pc.train_stop(prereg, st_serial) == pc.train_stop(prereg, st_k2) == 'STOP_SEEDS'
    rq = lambda st: [r for r in pc.split_rows(st, 'train') if r['requeue']]
    assert len(rq(st_serial)) == 1                                  # serial: re-queued once
    assert rq(st_k2) == []                                          # K = 2: lost
    assert pc.totals(st_serial)['attempts'] == pc.totals(st_k2)['attempts'] + 1


# X3 (BLOCKER b): validation is one batch of 20; a single HOST_ERROR world makes the batch unclean,
# every validation success is then not admitted and the gate (>= 8) fails -> NO_TRAIN.
def test_x3_one_host_error_in_validation_batch_blocks_training(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, None, episode=FakeEpisode(lambda s, c: result(), drop_seeds=[8341003]))
    v = pc.totals(st, 'validation')
    assert (v['successes'], v['admitted'], v['env_failures']) == (20, 1, 1)
    assert state == 'NO_TRAIN_VALIDATION_INSUFFICIENT'


# X4 (권고 b): bin_limit retires on S/N, the allocator weights on A; a bin with S/N >= 0.2 but
# A ~ 0 (handoff successes) is never retired and takes most of every batch.
def test_x4_bin_with_successes_but_no_admissions_is_never_limited_and_dominates(prereg):
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
    assert pc.bin_counts(prereg, st)['B5']['admitted'] == 0 and pc.pending_bin_limits(prereg, st) == []
    slots = pc.allocate(prereg, st, 20)
    assert slots.count('B5') >= 14


# X5 (권고 b): with both far bins limited the 25% share > 0.8 m cannot be met from B2/B3 alone,
# contrary to distance_gate.rationale ("allowing the far bins to be bin_limited").
def test_x5_both_far_bins_limited_fail_the_distance_gate(prereg):
    rows, k = [], 0
    for b, n in (('B0', 38), ('B1', 38), ('B2', 38), ('B3', 38), ('B4', 3), ('B5', 3)):
        for _ in range(n):
            seed = 8340000 + k
            d0, _y = pc.draw_start(prereg, seed, b, 0)
            d1, _y = pc.draw_start(prereg, seed, b, 1)
            rows.append(attempt_row(seed, b, OK, start={'r1': dict(distance_m=d0, yaw_offset_rad=3.),
                                                         'r2': dict(distance_m=d1, yaw_offset_rad=3.)}))
            k += 1
    st = _ledger(prereg, rows)
    g = pc.distance_gate(prereg, st)
    assert pc.totals(st)['admitted'] == 158 and g['share_over_0p8'] < .25 and not g['passed']


# X6 (정보 a): with K > 1 validation is planned while train batches are still in flight
# (prereg seeds.validation: "only after the train stop (never during ... collection)").
def test_x6_validation_planned_with_train_batches_in_flight(tmp_path, prereg):
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(3)}
    run_cooperative(tmp_path, prereg, 3, eps, rng=random.Random(5))
    rows, rep, meta = merged_rows(tmp_path, prereg, 3)
    planned = {r['batch']: r['split'] for r in rows if r['type'] == 'batch_planned'}
    v = min(j for j, s in planned.items() if s == 'validation')
    assert any(planned.get(j) == 'train' for j in range(v - 2, v))


# X7 (권고 a): bin_limit reads lagged counts; a hopeless bin keeps its high deficit weight
# (need / p_floor) for K - 1 more batches, so it receives more attempts than in the serial run.
def test_x7_hopeless_bin_gets_more_attempts_with_k4(tmp_path, prereg):
    from test_pairact_collect_shard import outcome
    _, st_serial, _ = collect(tmp_path / 'serial', prereg, None, episode=FakeEpisode(outcome))
    eps = {i: FakeEpisode(outcome) for i in range(4)}
    run_cooperative(tmp_path / 'k4', prereg, 4, eps, rng=random.Random(2))
    rows, rep, meta = merged_rows(tmp_path / 'k4', prereg, 4)
    st_k4 = pc.replay(prereg, rows)
    n = lambda st: pc.bin_counts(prereg, st)['B5']['attempts']
    assert 'B5' in st_serial['limited'] and 'B5' in st_k4['limited']
    assert n(st_k4) > n(st_serial)                                  # 36 vs 22 on this fake
    # same fake outcome function, different terminal class (BLOCKER a): serial STOP_TARGET (A 204),
    # K = 4 STOP_DISTANCE -> NO_TRAIN_DISTANCE_GATE (A 181, N 380)
    assert pc.train_stop(prereg, st_serial) == 'STOP_TARGET'
    assert pc.train_stop(prereg, st_k4) == 'STOP_DISTANCE'
    assert pc.decision(prereg, st_k4)['decision'] == 'NO_TRAIN_DISTANCE_GATE'


# X8 (권고 c): STOP_HOST needs two *consecutive* unclean batches by global index; with
# interleaved ownership a permanently broken shard (every K-th batch unclean) never triggers it,
# and its batches still count in N (judged, never admitted).
def test_x8_one_broken_shard_never_triggers_stop_host(tmp_path, prereg):
    ok = lambda s, c: result(success=s % 3 == 0)
    eps = {0: FakeEpisode(ok), 1: FakeEpisode(ok, status='HOST_ERROR')}
    run_cooperative(tmp_path, prereg, 2, eps, rng=random.Random(4))
    rows, rep, meta = merged_rows(tmp_path, prereg, 2)
    st = pc.replay(prereg, rows)
    unclean = [k for k, b in st['batches'].items() if b['split'] == 'train' and b['done'] and not b['clean']]
    assert len(unclean) >= 10
    assert pc.train_stop(prereg, st) != 'STOP_HOST'
    assert pc.totals(st)['attempts'] == prereg['targets']['attempt_cap']     # half the cap spent on unclean batches
