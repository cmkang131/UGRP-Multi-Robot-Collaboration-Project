"""v3s sharded collection (prereg ``sharding``): fake episodes only, no simulator.

Batch k is owned by shard k % K and planned with the unchanged rules on the view
(plans of batches < k, results of batches <= k - K).  The tests pin: K = 1 is the serial
ledger, the merged ledger does not depend on the wall-clock order of the shards (cooperative
random schedules, real threads, two run roots joined by ledger sync), a seed is never in two
running batches, the attempt cap holds with batches in flight, restarts are idempotent.
"""
import copy
import json
from pathlib import Path
import random
import shutil
import threading
import time

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import (EXP, PREREG, FakeEpisode, case_for, filled_manifest, make, recording_dir,
                                        result, runner)

SHARD_ONLY = ('train_closed', 'batch_skipped', 'run_end')


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


def outcome(seed, case):
    """Mixed yields: one hopeless bin (bin_limit), others between 1/3 and 1/2."""
    b = None
    for v in case['plan']['start_layers'].values():
        b = v['layer']
    if b == 'B5':
        return result(success=False)
    return result(success=seed % 3 == 0 or (b in ('B0', 'B1') and seed % 2 == 0))


def rejecting(prereg, seeds=(8340007, 8340041)):
    def cases(slots):
        return [dict(setup_rejected=dict(rejected={'beam_cargo_overlap': 5000}, gates=[], proposals=5000,
                                         reproduce=['python', 'collect_cases.py']))
                if s['seed'] in seeds else case_for(prereg, s) for s in slots]
    return cases


def shard_kw(prereg, **kw):
    return dict(mode=kw.pop('mode', 'training'), noise='off', batch_size=kw.pop('batch_size', 20),
                max_batches=kw.pop('max_batches', 1000), make_cases=kw.pop('make_cases', None) or make(prereg), **kw)


def step(root, prereg, i, count, episode, vm='vmA', sha='sha', **kw):
    """One cooperative step of shard i: at most one episode run, never waits."""
    return runner.run_shard(root, prereg, sha, shard=i, count=count, vm=vm, run_episode=episode,
                            wait=lambda: False, **shard_kw(prereg, max_batches=1, **kw))


TERMINAL = ('WAITING', 'MAX_BATCHES')


def run_cooperative(root, prereg, count, episodes, *, rng=None, vm_of=None, sync=None, check=None, **kw):
    """Random interleaving of single steps until every shard returns a terminal state."""
    rng = rng or random.Random(0)
    states = {}
    for _ in range(5000):
        live = [i for i in range(count) if states.get(i) in (None,) + TERMINAL]
        if not live:
            return states
        i = rng.choice(live)
        r = (sync(i) if sync else root)
        states[i] = step(r, prereg, i, count, episodes[i], vm=(vm_of or {}).get(i, 'vmA'), **kw)
        if sync:
            sync(None)
        if check:
            check()
    raise AssertionError(f'no progress: {states}')


def merged_rows(root, prereg, count):
    rep, meta = runner.merge(root, prereg, 'sha', count)
    return pc.read_ledger(Path(root) / 'merged' / 'ledger.jsonl'), rep, meta


def norm_path(v):
    v = str(v)
    return v[v.index('batches/'):] if 'batches/' in v else v


def normalize(rows):
    """Shard ledger vs serial ledger: drop shard-only rows / keys, compare paths below batches/."""
    out = []
    for r in rows:
        if r.get('type') in SHARD_ONLY:
            continue
        r = {k: v for k, v in r.items() if k not in ('shard', 'vm', 'batch_dir')}
        if r.get('type') == 'bin_limited':
            r.pop('planning_batch', None)
        if r.get('raw'):
            r['raw'] = norm_path(r['raw'])
        out.append(r)
    return out


def strip_paths(rows):
    return [dict(r, **{k: norm_path(r[k]) for k in ('raw', 'batch_dir') if r.get(k)}) for r in rows]


# ------------------------------------------------------------------ K = 1 is the serial run

def test_one_shard_is_the_serial_ledger(tmp_path, prereg):
    ep_serial = FakeEpisode(outcome, drop_seeds=[8340003, 8340100])
    state = runner.run(tmp_path / 'serial', prereg, 'sha', run_episode=ep_serial,
                       **shard_kw(prereg, make_cases=rejecting(prereg)))
    serial = pc.read_ledger(tmp_path / 'serial' / 'ledger.jsonl')
    ep = FakeEpisode(outcome, drop_seeds=[8340003, 8340100])
    s = runner.run_shard(tmp_path / 'shard', prereg, 'sha', shard=0, count=1, vm='vmA', run_episode=ep,
                         wait=lambda: False, **shard_kw(prereg, make_cases=rejecting(prereg)))
    rows, rep, meta = merged_rows(tmp_path / 'shard', prereg, 1)
    assert s == state and meta['finished'] and rep['run_state'] == state
    assert any(r['type'] == 'bin_limited' for r in serial) and any(r['type'] == 'setup_rejected' for r in serial)
    assert any(r.get('requeue') for r in serial if r['type'] == 'attempt')
    assert normalize(rows)[1:] == normalize(serial)[1:]
    assert {k: v for k, v in rows[0].items() if k != 'shard'} == serial[0]
    assert ep.calls == ep_serial.calls


# ------------------------------------------------------------------ order independence

def test_merged_ledger_does_not_depend_on_the_shard_schedule(tmp_path, prereg):
    results = []
    for n in range(3):
        root = tmp_path / f'r{n}'
        eps = {i: FakeEpisode(outcome, drop_seeds=[8340003, 8340100]) for i in range(3)}

        def invariant():
            ledgers = runner.read_shards(root, 3)
            if any(ledgers.values()):
                assert all(len(b) == 1 for b in pc.running_seeds(ledgers, 3).values())
        states = run_cooperative(root, prereg, 3, eps, rng=random.Random(n), check=invariant,
                                 make_cases=rejecting(prereg))
        rows, rep, meta = merged_rows(root, prereg, 3)
        assert meta['finished'] and not meta['running']
        assert len(set(states.values())) == 1 and rep['run_state'] == states[0]
        results.append((strip_paths(rows), rep['run_state'], rep['A']['attempts']))
    assert results[0] == results[1] == results[2]
    rows = results[0][0]
    # every batch k lives in shard k % 3, seeds of one split in strictly increasing first use
    planned = [r for r in rows if r['type'] == 'batch_planned']
    assert all(r['shard'] == r['batch'] % 3 for r in planned)
    fresh = [s['seed'] for r in planned for s in r['slots'] if s['split'] == 'train' and not s['requeue']]
    rejected = [r['seed'] for r in rows if r['type'] == 'setup_rejected' and not r.get('requeue')]
    assert sorted(fresh + rejected) == list(range(8340000, 8340000 + len(fresh) + len(rejected)))
    assert len(fresh) == len(set(fresh))


def test_threads_never_run_one_seed_twice_and_match_the_cooperative_run(tmp_path, prereg):
    lock, running, seen = threading.Lock(), set(), []

    class Tracked(FakeEpisode):
        def __call__(self, cases_path, indices, out):
            cases = json.loads(Path(cases_path).read_text())
            seeds = {(c['plan']['seed']) for c in (cases[i] for i in indices)}
            with lock:
                assert not running & seeds, f'seed run twice at once: {running & seeds}'
                running.update(seeds)
                seen.append(sorted(seeds))
            time.sleep(0.002)
            try:
                return super().__call__(cases_path, indices, out)
            finally:
                with lock:
                    running.difference_update(seeds)
    root = tmp_path / 'threads'
    states, errors = {}, []

    def go(i):
        try:
            states[i] = runner.run_shard(root, prereg, 'sha', shard=i, count=4, vm='vmA', run_episode=Tracked(outcome),
                                         wait=lambda: (time.sleep(0.001), True)[1], **shard_kw(prereg))
        except BaseException as error:        # surfaced below
            errors.append(error)
    threads = [threading.Thread(target=go, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert not errors, errors
    rows, rep, meta = merged_rows(root, prereg, 4)
    assert meta['finished'] and set(states.values()) == {rep['run_state']}
    coop = tmp_path / 'coop'
    run_cooperative(coop, prereg, 4, {i: FakeEpisode(outcome) for i in range(4)}, rng=random.Random(7))
    rows2, _, _ = merged_rows(coop, prereg, 4)
    assert strip_paths(rows) == strip_paths(rows2)
    assert len(seen) == len([r for r in rows if r['type'] == 'batch_planned'])


# ------------------------------------------------------------------ cap / overshoot / in-flight

def test_cap_holds_with_batches_in_flight_and_every_planned_batch_is_ingested(tmp_path, prereg):
    eps = {i: FakeEpisode(lambda s, c: result(success=(s * 7) % 10 < 3)) for i in range(4)}
    states = run_cooperative(tmp_path, prereg, 4, eps, rng=random.Random(3))
    rows, rep, meta = merged_rows(tmp_path, prereg, 4)
    st = pc.replay(prereg, rows)
    assert pc.totals(st)['attempts'] == prereg['targets']['attempt_cap']
    assert pc.decision(prereg, st)['train_stop'] == 'STOP_CAP'
    assert meta['finished'] and all(b['done'] for b in st['batches'].values())
    assert any(r['type'] == 'batch_skipped' for r in rows)       # in-flight reservation reached the cap
    assert set(states.values()) == {rep['run_state']}


def test_target_overshoot_of_in_flight_batches_is_kept(tmp_path, prereg):
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(3)}
    run_cooperative(tmp_path, prereg, 3, eps, rng=random.Random(5))
    rows, rep, meta = merged_rows(tmp_path, prereg, 3)
    st = pc.replay(prereg, rows)
    closed = next(r for r in rows if r['type'] == 'train_closed')
    assert closed['stop'] == 'STOP_TARGET' and pc.decision(prereg, st)['train_stop'] == 'STOP_TARGET'
    assert pc.totals(st)['admitted'] == pc.totals(st)['attempts'] > prereg['targets']['admitted_target_pairs']
    assert rep['run_state'] == 'TRAIN' and meta['finished']


def test_reserved_slots_count_against_the_cap(prereg):
    st = pc.replay(prereg, [pc.header('sha', mode='training', noise='off', batch_size=20)])
    assert len(pc.plan_batch(prereg, st, 20, reserved=590)) == 10
    assert pc.plan_batch(prereg, st, 20, reserved=600) == []
    assert len(pc.plan_batch(prereg, st, 20)) == 20


# ------------------------------------------------------------------ restart / lock / headers

def test_restart_after_crashes_matches_the_uninterrupted_run(tmp_path, prereg):
    ref = tmp_path / 'ref'
    run_cooperative(ref, prereg, 3, {i: FakeEpisode(outcome) for i in range(3)}, rng=random.Random(1))
    rows_ref, _, _ = merged_rows(ref, prereg, 3)
    root = tmp_path / 'crash'
    rng = random.Random(2)
    for _ in range(4000):
        i = rng.randrange(3)
        crash = rng.random() < 0.15

        def ep(cases_path, indices, out, _crash=crash):
            if _crash:
                raise KeyboardInterrupt          # process killed while the episode runs
            return FakeEpisode(outcome)(cases_path, indices, out)
        try:
            state = step(root, prereg, i, 3, ep)
        except KeyboardInterrupt:
            continue
        ledgers = runner.read_shards(root, 3)
        view = pc.shard_view(ledgers, 3)
        if view and view[1]['finished'] and state not in TERMINAL:
            break
    rows, _, meta = merged_rows(root, prereg, 3)
    assert meta['finished']
    assert strip_paths(rows) == strip_paths(rows_ref)


def test_second_process_on_the_same_shard_is_refused(tmp_path, prereg):
    with runner.shard_lock(runner.shard_dir(tmp_path, 1)):
        with pytest.raises(RuntimeError, match='shard already running'):
            step(tmp_path, prereg, 1, 3, FakeEpisode(lambda s, c: result()))


def test_shard_headers_must_agree(tmp_path, prereg):
    step(tmp_path, prereg, 0, 3, FakeEpisode(lambda s, c: result()))
    with pytest.raises(ValueError, match='header mismatch'):
        step(tmp_path, prereg, 0, 3, FakeEpisode(lambda s, c: result()), vm='vmB')
    with pytest.raises(ValueError, match='differs from the other shards'):
        step(tmp_path, prereg, 1, 3, FakeEpisode(lambda s, c: result()), batch_size=10)
    with pytest.raises(ValueError, match='expected index'):
        pc.shard_view({0: runner.read_shards(tmp_path, 3)[0]}, 4)


def test_a_batch_in_the_wrong_shard_ledger_is_refused(tmp_path, prereg):
    for i in (0, 1):
        step(tmp_path, prereg, i, 2, FakeEpisode(lambda s, c: result()))
    ledgers = runner.read_shards(tmp_path, 2)
    bad = copy.deepcopy(ledgers)
    row = next(r for r in bad[0] if r['type'] == 'batch_planned')
    bad[1].append(dict(row))
    with pytest.raises(ValueError, match='owner'):
        pc.shard_view(bad, 2)


def test_parse_shard():
    assert pc.parse_shard('2/4') == (2, 4)
    for bad in ('4/4', '-1/3', '1', 'a/b', '0/0'):
        with pytest.raises(ValueError):
            pc.parse_shard(bad)


# ------------------------------------------------------------------ STOP_HOST

def test_stop_host_waits_for_the_host_fix_then_runs_validation(tmp_path, prereg):
    # batches 10 and 11 (6th call of each shard) unclean after ~100 admitted (A >= 80: validation pending)
    ep = {i: FakeEpisode(lambda s, c: result(success=s % 2 == 0), status=lambda n: 'HOST_ERROR' if n == 6 else None)
          for i in range(2)}
    states = run_cooperative(tmp_path, prereg, 2, ep, rng=random.Random(6))
    assert set(states.values()) == {'STOP_HOST'}
    rows, rep, meta = merged_rows(tmp_path, prereg, 2)
    assert meta['ended'] is None and rep['run_state'] == 'STOP_HOST'
    assert not any(r['split'] == 'validation' for r in rows if r['type'] == 'batch_planned')
    ep = {i: FakeEpisode(lambda s, c: result(success=s % 2 == 0)) for i in range(2)}
    run_cooperative(tmp_path, prereg, 2, ep, rng=random.Random(6), validation_after_host_fix=True)
    rows, rep, meta = merged_rows(tmp_path, prereg, 2)
    assert meta['finished'] and any(r['split'] == 'validation' for r in rows if r['type'] == 'batch_planned')


# ------------------------------------------------------------------ two VMs (ledger sync)

def test_two_vms_with_ledger_sync_equal_one_vm(tmp_path, prereg):
    """VM A runs shards 0,1 under rootA, VM B shards 2,3 under rootB; only ledgers are copied."""
    vm_of = {0: 'gcp6', 1: 'gcp6', 2: 'gcp2', 3: 'gcp2'}
    roots = dict(gcp6=tmp_path / 'A' / 'run', gcp2=tmp_path / 'B' / 'run')

    def sync(i):
        if i is not None:
            return roots[vm_of[i]]
        for j, vm in vm_of.items():          # rsync of remote shard ledgers (whole-file replace)
            src = runner.shard_dir(roots[vm], j) / 'ledger.jsonl'
            if src.exists():
                for other, r in roots.items():
                    if other != vm:
                        dst = runner.shard_dir(r, j) / 'ledger.jsonl'
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(src, dst)
        return None
    eps = {i: FakeEpisode(outcome) for i in range(4)}
    states = run_cooperative(None, prereg, 4, eps, rng=random.Random(8), vm_of=vm_of, sync=sync)
    rows_a, rep_a, meta_a = merged_rows(roots['gcp6'], prereg, 4)
    one = tmp_path / 'one'
    run_cooperative(one, prereg, 4, {i: FakeEpisode(outcome) for i in range(4)}, rng=random.Random(9), vm_of=vm_of)
    rows_1, rep_1, _ = merged_rows(one, prereg, 4)
    assert meta_a['finished'] and strip_paths(rows_a) == strip_paths(rows_1)
    assert set(states.values()) == {rep_1['run_state']}
    assert {r['vm'] for r in rows_a if r['type'] == 'batch_planned'} == {'gcp6', 'gcp2'}


# ------------------------------------------------------------------ RUN_MANIFEST sharding

def test_manifest_sharding_binds_count_vm_and_per_vm_recording_check(tmp_path, prereg):
    pre = dict(prereg, status='FROZEN')
    d, rec = recording_dir(tmp_path)
    m = filled_manifest(pre, status='FROZEN', recording=rec)
    assert m['sharding']['count'] >= 1
    m['sharding'].update(count=4, lag_batches=4, assignment={'gcp6': [0, 1], 'gcp2': [2, 3]}, primary_vm='gcp6',
                         vm_recording_check={})
    with pytest.raises(ValueError, match='non-primary VMs'):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d, shard=(0, 4, 'gcp6'))
    core_before = pc.core_sha256(pre, m)
    d2 = tmp_path / 'b'
    shutil.copytree(d, d2)
    (d2 / 'recording-check.json').write_text(json.dumps(dict(qualified=True, N=3, n=3, vm='gcp2')) + '\n')
    m['sharding']['vm_recording_check'] = {'gcp2': {k: pc.file_sha256(d2 / n) for k, n in pc.RECORDING_FILES.items()}}
    assert pc.core_sha256(pre, m) == core_before                 # filled at FROZEN, not part of the core
    pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d, shard=(1, 4, 'gcp6'))
    pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d2, shard=(2, 4, 'gcp2'))
    with pytest.raises(ValueError, match='recording_check.recording_check_sha256 differs'):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d, shard=(2, 4, 'gcp2'))
    with pytest.raises(ValueError, match='not assigned'):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d, shard=(2, 4, 'gcp6'))
    with pytest.raises(ValueError, match='shard count'):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d, shard=(0, 1, None))   # serial run
    bad = copy.deepcopy(m)
    bad['sharding']['assignment'] = {'gcp6': [0, 1], 'gcp2': [1, 3]}
    with pytest.raises(ValueError, match='exactly once'):
        pc.check_run_manifest(bad, stage='final', prereg=pre, recording_dir=d)
    bad = copy.deepcopy(m)
    bad['sharding']['lag_batches'] = 2
    with pytest.raises(ValueError, match='lag_batches'):
        pc.check_run_manifest(bad, stage='final', prereg=pre, recording_dir=d)
    bad = copy.deepcopy(m)
    bad['sharding']['count'] = 2
    assert pc.core_sha256(pre, bad) != core_before                # the shard count is core content


def test_draft_manifest_and_prereg_carry_the_sharding_rule(prereg):
    m = json.loads((EXP / 'RUN_MANIFEST.json').read_text())
    sh = m['sharding']
    assert sh['count'] == sh['lag_batches'] and sorted(i for v in sh['assignment'].values() for i in v) == \
        list(range(sh['count']))
    assert sh['primary_vm'] in sh['assignment'] and sh['vm_recording_check'] == {}
    rule = prereg['sharding']
    assert 'execution' in rule['scope'] and rule['lag_batches'] == 'K'
    assert prereg['status'] == 'READY_FOR_REVIEW'


def test_freeze_final_fills_the_second_vm_recording_check_without_moving_core(tmp_path, prereg, monkeypatch):
    import importlib.util
    from test_pairact_collect import G, ROOT
    spec = importlib.util.spec_from_file_location('pairact_r1_freeze', ROOT / 'scripts/pairact_r1_freeze.py')
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    monkeypatch.setattr(pc, 'collector_provenance', lambda repo, sha, files: [])
    pp, mp = tmp_path / 'prereg.json', tmp_path / 'manifest.json'
    pp.write_text(PREREG.read_text())
    m = filled_manifest(prereg, status='DRAFT_VM_FILL')
    for k in pc.RECORDING_FIELDS:
        m['recording_check'][k] = '[VM 기입] filled at FROZEN'
    m['sharding'].update(count=6, lag_batches=6, assignment={'gcp6': [0, 1, 2], 'gcp2': [3, 4, 5]})
    mp.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    out = fz.freeze('core', prereg_path=pp, manifest_path=mp, repo=ROOT, collector_sha=G('f'))
    d, _ = recording_dir(tmp_path)
    with pytest.raises(ValueError, match='non-primary VMs'):
        fz.freeze('final', prereg_path=pp, manifest_path=mp, repo=ROOT, recording_dir=d)
    (tmp_path / 'b').mkdir()
    d2, _ = recording_dir(tmp_path / 'b')
    fin = fz.freeze('final', prereg_path=pp, manifest_path=mp, repo=ROOT, recording_dir=d,
                    expect_core=out['core_sha256'], vm_recording_dirs={'gcp2': str(d2)})
    assert fin['core_sha256'] == out['core_sha256']
    assert set(json.loads(mp.read_text())['sharding']['vm_recording_check']) == {'gcp2'}


def test_cli_shard_needs_vm_and_merge_writes_the_merged_root(tmp_path, prereg):
    import subprocess
    import sys
    from test_pairact_collect import EP_CMD, ROOT

    def cli(*args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/run_pairact_collect.py'), *args],
                              capture_output=True, text=True, timeout=120)
    out = cli('collect', '--prereg', str(PREREG), '--run-root', str(tmp_path / 'x'), '--episode-cmd', EP_CMD,
              '--shard', '0/2')
    assert out.returncode != 0 and '--shard needs --vm' in out.stderr
    out = cli('collect', '--prereg', str(PREREG), '--run-root', str(tmp_path / 'x'), '--episode-cmd', EP_CMD,
              '--shard', '2/2', '--vm', 'gcp6')
    assert out.returncode != 0 and 'need 0 <= i < K' in out.stderr
    root = tmp_path / 'm'
    _, real_sha = pc.load_prereg(PREREG)
    run_cooperative(root, prereg, 2, {i: FakeEpisode(lambda s, c: result()) for i in range(2)}, mode='measurement',
                    sha=real_sha)
    out = cli('merge', '--prereg', str(PREREG), '--run-root', str(root), '--shards', '2')
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res['state'] == 'PILOT_DONE' and res['finished'] and (root / 'merged' / 'report.json').exists()
    out = cli('report', '--prereg', str(PREREG), '--run-root', str(root / 'merged'))
    assert out.returncode == 0 and '수율 측정' in out.stdout
