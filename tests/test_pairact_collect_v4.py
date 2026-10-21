"""COLLECT_PREREG v4 additions (dsh/pairact-carry-r1-v4): fake episodes and pure functions only.

Stop barrier details, order-based STOP_HOST, validation unclean re-queue (second unclean run not admitted),
merge append-only and seed-history audits, merged-root finished / raw presence, stack head check.
X1-X8 live in test_pairact_prereg_xreview.py.
"""
import json
from pathlib import Path
import random
import shutil

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import PREREG, FakeEpisode, attempt_row, collect, result, runner
from test_pairact_collect_shard import merged_rows, run_cooperative, step


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


def _batches(prereg, flags, count=None):
    """Synthetic ledger: one finished train batch per flag (clean True / False), no attempts."""
    h = pc.header('sha', mode='training', noise='off', batch_size=20,
                  shard=None if count is None else dict(count=count, lag_batches=count, merged=True))
    rows = [h]
    for k, clean in enumerate(flags):
        rows += [dict(type='batch_planned', batch=k, split='train', cases_sha256='x', slots=[]),
                 dict(type='batch_done', batch=k, split='train', clean=clean)]
    return pc.replay(prereg, rows)


def test_stop_host_is_a_property_of_the_ordered_results(prereg):
    # Codex H1: two unclean in a row stay a host stop when later batches are clean
    st = _batches(prereg, [True, False, False, True, True, True])
    assert pc.consecutive_unclean_batches(st) == 0 and pc.train_stop(prereg, st) == 'STOP_HOST'
    assert pc.train_stop(prereg, _batches(prereg, [True, False, True, False, True])) is None


def test_shard_host_consecutive_and_ratio_prefix(prereg):
    r = prereg['stop_rules']['shard_host']
    assert (r['consecutive'], r['min_batches'], r['max_share']) == (3, 6, .3)
    # K = 2, shard 1 (odd batches) unclean three times in a row, never two consecutive globally
    flags = [True, False] * 3 + [True] * 4
    st = _batches(prereg, flags, count=2)
    assert not pc.host_unclean_pair(st) and [s['shard'] for s in pc.shard_host(prereg, st)] == [1]
    # K = 1: 2 of the first 6 unclean (33%) is a stop even if later batches dilute it below 30%
    st = _batches(prereg, [False, True, True, False, True, True] + [True] * 10)
    assert pc.shard_host(prereg, st)[0]['ratio_prefix'] == 6 and pc.train_stop(prereg, st) == 'STOP_HOST'
    assert pc.shard_host(prereg, _batches(prereg, [False, True, True, True, True, True, False])) == []


def _validation_unclean_twice():
    seen = {'n': 0}
    inner_bad, inner_ok = FakeEpisode(lambda s, c: result(), status='HOST_ERROR'), FakeEpisode(lambda s, c: result())

    def ep(cases_path, indices, out):
        seeds = [json.loads(Path(cases_path).read_text())[i]['plan']['seed'] for i in indices]
        if min(seeds) >= 8341000 and seen['n'] < 2:
            seen['n'] += 1
            return inner_bad(cases_path, indices, out)
        return inner_ok(cases_path, indices, out)
    return ep


def test_validation_requeue_unclean_again_is_judged_not_admitted(tmp_path, prereg):
    state, st, _ = collect(tmp_path, prereg, None, episode=_validation_unclean_twice())
    val = pc.split_rows(st, 'validation')
    first, second = val[:20], val[20:]
    assert all(r['outcome'] == 'unclean_batch_requeue' and r['requeue_eligible'] for r in first)
    assert len(second) == 20 and all(r['requeue'] and r['success'] and not r['admitted'] for r in second)
    assert all('batch_not_clean' in r['reason'] for r in second)
    v = pc.totals(st, 'validation')
    assert (v['attempts'], v['successes'], v['admitted']) == (20, 20, 0)          # no third run
    assert state == 'NO_TRAIN_VALIDATION_INSUFFICIENT'
    vb = [b for b in st['batches'].values() if b['split'] == 'validation']
    assert len(vb) == 2


def test_train_unclean_batch_is_not_requeued(prereg):
    j = pc.judge(result(), mode='measurement', batch_clean=False)
    assert pc.validation_unclean(j, split='train', requeue=False, batch_clean=False) == j
    assert pc.validation_unclean(j, split='validation', requeue=True, batch_clean=False) == j


def test_stop_barrier_rows(prereg):
    st = _batches(prereg, [False, False])
    hold = pc.stop_control(prereg, st, 2, [1])
    assert hold['action'] == 'hold' and hold['stop'] == 'STOP_HOST'
    st2 = pc.replay(prereg, [st['header']] + [dict(hold, type='train_barrier')])
    assert st2['barrier'] is not None and pc.stop_control(prereg, st2, 3, [1]) is None    # still in flight: wait
    closed = pc.stop_control(prereg, st, 3, [])
    assert closed['type'] == 'train_closed' and closed['stop'] == 'STOP_HOST'
    st3 = pc.replay(prereg, [st['header'], dict(hold, type='train_barrier')])
    rel = pc.stop_control(prereg, st3, 4, [])          # drained, no stop on this ledger: release
    assert rel['action'] == 'release' and rel['held_stop'] == 'STOP_HOST'


def test_merge_refuses_a_rewritten_shard_ledger(tmp_path, prereg):
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(2)}
    for _ in range(6):
        for i in range(2):
            step(tmp_path, prereg, i, 2, eps[i])
    merged_rows(tmp_path, prereg, 2)
    meta = json.loads((tmp_path / 'merged' / 'merge.json').read_text())
    assert set(meta['shard_ledger_bytes']) == {'s00', 's01'}
    led = runner.shard_dir(tmp_path, 1) / 'ledger.jsonl'
    keep = led.read_bytes()
    led.write_bytes(keep[:len(keep) // 2])                      # wrong-direction sync: older copy
    with pytest.raises(ValueError, match='append-only'):
        runner.merge(tmp_path, prereg, 'sha', 2)
    led.write_bytes(keep)
    runner.merge(tmp_path, prereg, 'sha', 2)


def test_seed_history_audit():
    plan = lambda b, seeds, rq=False: dict(type='batch_planned', batch=b, split='train',
                                           slots=[dict(seed=s, split='train', requeue=rq) for s in seeds])
    env = dict(type='attempt', split='train', seed=2, category='environment')
    assert pc.check_seed_history([plan(0, [1, 2]), env, plan(1, [2], rq=True)]) == dict(fresh=2, requeued=1)
    with pytest.raises(ValueError, match='fresh twice'):
        pc.check_seed_history([plan(0, [1, 2]), plan(3, [2])])
    with pytest.raises(ValueError, match='without an earlier environment failure'):
        pc.check_seed_history([plan(0, [1, 2]), plan(1, [1], rq=True)])
    with pytest.raises(ValueError, match='twice'):
        pc.check_seed_history([plan(0, [2]), env, plan(1, [2], rq=True), plan(2, [2], rq=True)])


def test_merged_meta_needs_a_finished_matching_merge(tmp_path, prereg):
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(2)}
    for i in range(2):
        step(tmp_path, prereg, i, 2, eps[i])
    rows, rep, meta = merged_rows(tmp_path, prereg, 2)
    with pytest.raises(ValueError, match='sharded run root'):
        runner.merged_meta(tmp_path, require_finished=True)
    assert runner.merged_meta(tmp_path / 'merged', require_finished=False)['count'] == 2
    with pytest.raises(ValueError, match='merge not finished'):
        runner.merged_meta(tmp_path / 'merged', require_finished=True)
    run_cooperative(tmp_path, prereg, 2, eps, rng=random.Random(1))
    merged_rows(tmp_path, prereg, 2)
    assert runner.merged_meta(tmp_path / 'merged', require_finished=True)['finished']
    with open(tmp_path / 'merged' / 'ledger.jsonl', 'a') as f:
        f.write('\n')
    with pytest.raises(ValueError, match='differs from merge.json'):
        runner.merged_meta(tmp_path / 'merged', require_finished=True)
    assert runner.merged_meta(tmp_path / 'serial-like', require_finished=True) is None


def test_convert_input_refuses_missing_world_raw(tmp_path, prereg):
    state, st, _ = collect(tmp_path / 'run', prereg, lambda s, c: result())
    assert state == 'TRAIN'
    shutil.rmtree(next(r['raw'] for r in st['attempt_rows'] if r['admitted']))
    with pytest.raises(ValueError, match='raw directories missing'):
        pc.convert_input(prereg, st, tmp_path / 'out', prereg_sha='sha', teacher_sha='t' * 40)
    assert not (tmp_path / 'out').exists()


def test_stack_heads_must_match_the_manifest_pins():
    m = dict(stack={r: dict(sha=c * 40) for r, c in (('teacher', 'a'), ('adapter', 'b'), ('root', 'c'))})
    roots = dict(teacher='T', adapter='A', root='R')
    heads = dict(T=('a' * 40, False), A=('b' * 40, False), R=('c' * 40, False))
    assert pc.check_stack_heads(m, roots, rev_parse=heads.get) == dict(teacher='a' * 40, adapter='b' * 40, root='c' * 40)
    with pytest.raises(ValueError, match='RUN_MANIFEST pins'):
        pc.check_stack_heads(m, roots, rev_parse=dict(heads, A=('d' * 40, False)).get)
    with pytest.raises(ValueError, match='tracked changes'):
        pc.check_stack_heads(m, roots, rev_parse=dict(heads, R=('c' * 40, True)).get)
    with pytest.raises(ValueError, match='path required'):
        pc.check_stack_heads(m, dict(roots, adapter=None), rev_parse=heads.get)


def test_distance_gate_label_reaches_the_decision(prereg):
    ok = pc.judge(result(), mode='measurement', batch_clean=True)
    fail = pc.judge(result(success=False), mode='measurement', batch_clean=True)
    rows = []
    for k in range(600):
        b = pc.bin_ids(prereg)[k % 6]
        d0, y = pc.draw_start(prereg, 8340000 + k, b, 0)
        d1, _ = pc.draw_start(prereg, 8340000 + k, b, 1)
        good = b in ('B0', 'B1', 'B2', 'B3') and k < 280
        rows.append(attempt_row(8340000 + k, b, ok if good else fail,
                                start={'r1': dict(distance_m=d0, yaw_offset_rad=y), 'r2': dict(distance_m=d1, yaw_offset_rad=y)}))
    from test_pairact_collect import ledger_state
    st = ledger_state(prereg, rows)
    lim = pc.pending_bin_limits(prereg, st)
    st = ledger_state(prereg, [dict(type='batch_planned', batch=0, split='train', cases_sha256='x',
                                    slots=[dict(slot=i, seed=r['seed'], bin=r['bin'], split='train', requeue=False)
                                           for i, r in enumerate(rows)])] + [dict(r, slot=i) for i, r in enumerate(rows)] + lim)
    d = pc.decision(prereg, st)
    assert d['train_stop'] == 'STOP_CAP' and d['decision'] == 'TRAIN_DATA_RANGE_LIMITED'
    assert any(x.startswith('거리 관문 축소(제한 구간 제외: 0.9-1.2 m') for x in d['labels'])
