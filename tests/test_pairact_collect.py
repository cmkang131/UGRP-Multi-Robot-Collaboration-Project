"""P3 success-filtered collection controller: fake episode outcomes only (no simulator)."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from harness import pairact_collect as pc

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / 'experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json'
spec = importlib.util.spec_from_file_location('run_pairact_collect', ROOT / 'scripts/run_pairact_collect.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


def case_for(prereg, slot):
    layers = {}
    for i, rid in enumerate(('r1', 'r2')):
        d, y = pc.draw_start(prereg, slot['seed'], slot['bin'], i)
        layers[rid] = dict(layer=slot['bin'], target_distance_m=d, yaw_bin=dict(index=None, offset_rad=y))
    return dict(plan=dict(seed=slot['seed'], start_layers=layers), candidate='pairact_p2_r13')


def result(success=True, grasp=True, drops=(), rr=0, handoff=False, admitted=True, status='complete'):
    ev = dict(success=success, failure=None if success else 'not_in_zone', drop_events=list(drops),
              robot_robot_contact_ticks=rr, funnel=dict(handover=True, carried_1m=True, door=success))
    return dict(status=status, grasp_physical_success=grasp, carry_eval=ev if grasp else None,
                carry={'started': grasp} if grasp else {'started': False, 'reason': 'no_joint_hold_3s'},
                search_handoff=handoff, approach_handoff=False, data_admitted=admitted)


class FakeEpisode:
    """Writes the root-runner layout: out/summary.json + world-XXX/raw/result.json."""

    def __init__(self, outcome, *, crash_first=0, drop_seeds=()):
        self.outcome, self.calls, self.crash_first, self.drop_seeds = outcome, [], crash_first, set(drop_seeds)

    def __call__(self, cases_path, indices, out):
        self.calls.append(list(indices))
        cases = json.loads(Path(cases_path).read_text())
        out = Path(out)
        out.mkdir(parents=True)
        if len(self.calls) <= self.crash_first:
            (out / 'summary.json').write_text(json.dumps(dict(status='running')))   # killed before finally
            return -9
        worlds = []
        for i, idx in enumerate(indices):
            seed = cases[idx]['plan']['seed']
            if seed in self.drop_seeds:
                self.drop_seeds.discard(seed)        # world lost once (HOST_ERROR mid batch)
                continue
            raw = out / f'world-{i:03d}' / 'raw'
            raw.mkdir(parents=True)
            r = self.outcome(seed, cases[idx])
            (raw / 'result.json').write_text(json.dumps(r))
            worlds.append(dict(world=i, seed=seed, carry_success=(r.get('carry_eval') or {}).get('success'),
                               raw=str(raw), sim_s=100.))
        (out / 'summary.json').write_text(json.dumps(dict(status='complete', HOST_ERROR=0, worlds=worlds)))
        return 0


def collect(tmp, prereg, outcome, **kw):
    ep = kw.pop('episode', None) or FakeEpisode(outcome)
    stop = runner.run(tmp, prereg, 'sha', mode=kw.pop('mode', 'measurement'), noise='off',
                      batch_size=kw.pop('batch_size', 20), max_batches=kw.pop('max_batches', 1000),
                      make_cases=lambda slots: [case_for(prereg, s) for s in slots], run_episode=ep, **kw)
    return stop, pc.replay(prereg, pc.read_ledger(Path(tmp) / 'ledger.jsonl')), ep


# --------------------------------------------------------------- prereg

def test_prereg_registered_numbers(prereg):
    assert prereg['status'] == 'READY_FOR_REVIEW'
    assert [b['id'] for b in prereg['bins']['list']] == ['B0', 'B1', 'B2', 'B3', 'B4', 'B5']
    assert prereg['bins']['min_success_per_bin'] == 20
    t = prereg['targets']
    assert (t['success_target_pairs'], t['success_minimum_pairs'], t['attempt_cap']) == (200, 150, 600)
    assert prereg['dart_noise']['default'] == 'off'
    assert set(prereg['reporting']) >= {'A', 'B', 'C'}


def test_seed_ranges_disjoint_and_ordered(prereg):
    known = json.loads((ROOT / 'experiments/2026-10-21-pairact-r1/seeds.json').read_text())['known_ranges']
    pc.check_seed_ranges(prereg, known)
    pool = pc.train_pool(prereg)
    assert pool[0] == 8340000 and pool[-1] == 8340599 and pool == sorted(pool) and len(pool) == 600
    bad = json.loads(json.dumps(prereg))
    bad['seeds']['train_extension'] = {'first': 8340200, 'last': 8341005}
    with pytest.raises(ValueError, match='validation'):
        pc.check_seed_ranges(bad)


def test_training_mode_requires_frozen_prereg(tmp_path):
    with pytest.raises(ValueError, match='not allowed for training'):
        pc.load_prereg(PREREG, mode='training')
    pr, sha = pc.load_prereg(PREREG, mode='measurement')
    assert sha == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    frozen = tmp_path / 'p.json'
    frozen.write_text(json.dumps({**pr, 'status': 'FROZEN'}))
    pc.load_prereg(frozen, mode='training')


def test_draws_stay_inside_their_bin(prereg):
    for b in pc.bins(prereg):
        for seed in range(8340000, 8340050):
            for r in (0, 1):
                d, y = pc.draw_start(prereg, seed, b['id'], r)
                assert pc.bin_of(prereg, d, y) == b['id']
    assert pc.draw_start(prereg, 8340000, 'B3', 0) == pc.draw_start(prereg, 8340000, 'B3', 0)
    assert pc.yaw_class(math.pi) == 'facing' and pc.yaw_class(0.) == 'away'


# --------------------------------------------------------------- filter

def test_judge_success_and_every_failure_rule():
    assert pc.judge(result(), mode='measurement')['eligible'] is True
    assert pc.judge(result(drops=[{'kind': 'tilt'}]), mode='measurement')['success'] is False
    assert pc.judge(result(rr=3), mode='measurement')['failure_stage'] == 'carry'
    assert pc.judge(result(success=False), mode='measurement')['reason'] == 'not_in_zone'
    g = pc.judge(result(grasp=False), mode='measurement')
    assert (g['outcome'], g['failure_stage'], g['reason']) == ('failure', 'grasp', 'no_joint_hold_3s')
    assert pc.judge(dict(result(), carry_eval=None), mode='measurement')['failure_stage'] == 'carry_not_started'
    assert pc.judge(None, mode='measurement')['outcome'] == 'host_error'
    assert pc.judge(result(status='HOST_ERROR'), mode='measurement')['outcome'] == 'host_error'
    h = pc.judge(result(handoff=True), mode='measurement')
    assert h['success'] and not h['eligible'] and h['reason'] == 'success_not_admitted_handoff'
    t = pc.judge(result(admitted=False), mode='training')
    assert t['success'] and not t['eligible']
    assert pc.judge(result(admitted=False), mode='measurement')['eligible'] is True


def test_failures_stay_in_ledger_and_out_of_convert_input(tmp_path, prereg):
    outcome = lambda seed, case: result(success=seed % 3 == 0)
    _, st, _ = collect(tmp_path / 'run', prereg, outcome, mode='training', max_batches=3)
    rows = [r for r in st['attempt_rows'] if r['outcome'] != 'host_error']
    assert any(not r['success'] for r in rows) and all(Path(r['raw']).exists() for r in rows)
    proto = pc.convert_input(st, tmp_path / 'conv', teacher_sha='a' * 40)
    ok = sorted(r['seed'] for r in rows if r['eligible'] and r['split'] == 'train')
    assert proto['train_seeds'] == ok and all(s % 3 == 0 for s in ok)
    assert proto['validation_seeds'] and all(8341000 <= s <= 8341019 for s in proto['validation_seeds'])
    d = tmp_path / 'conv' / f'seed-{ok[0]}'
    assert (d / 'raw').is_symlink() and (d / 'raw' / 'result.json').exists()
    assert (d / 'EXIT').read_text().strip() == '0'


# ------------------------------------------------------------ allocation

def test_warmup_is_round_robin_and_validation_first(tmp_path, prereg):
    _, st, ep = collect(tmp_path, prereg, lambda s, c: result(), max_batches=2)
    first, second = st['batches'][0]['slots'], st['batches'][1]['slots']
    assert [s['split'] for s in first] == ['validation'] * 20
    assert [s['seed'] for s in second] == list(range(8340000, 8340020))
    assert [s['bin'] for s in second[:6]] == ['B0', 'B1', 'B2', 'B3', 'B4', 'B5']


def test_deficit_bins_get_more_attempts_and_allocation_is_deterministic(prereg):
    st = pc.replay(prereg, [])
    st['validation_done'] = True
    for b in ('B0', 'B1', 'B2', 'B3', 'B4', 'B5'):
        st['attempts'][b] = 10
    for b in ('B0', 'B1', 'B2', 'B3'):
        st['eligible'][b] = 20
    st['eligible']['B4'], st['eligible']['B5'] = 2, 8
    slots = pc.allocate(prereg, st, 20)
    assert set(slots) == {'B4', 'B5'} and slots.count('B4') > slots.count('B5')
    assert slots == pc.allocate(prereg, st, 20)


def test_hard_bin_is_filled_before_cap(tmp_path, prereg):
    # B5 succeeds 1 in 4, the others always: allocation must push B5 to 20.
    def outcome(seed, case):
        b = case['plan']['start_layers']['r1']['layer']
        return result(success=b != 'B5' or seed % 4 == 0)
    stop, st, _ = collect(tmp_path, prereg, outcome)
    assert stop == 'STOP_TARGET'
    assert all(st['eligible'][b] >= 20 for b in ('B0', 'B1', 'B2', 'B3', 'B4', 'B5'))
    assert pc.totals(st)['eligible'] >= 200 and pc.totals(st)['attempts'] <= 600


def test_attempt_cap_and_in_order_seed_consumption(tmp_path, prereg):
    stop, st, _ = collect(tmp_path, prereg, lambda s, c: result(success=False), batch_size=48)
    assert stop == 'STOP_CAP'
    assert pc.totals(st)['attempts'] == 600
    seeds = [r['seed'] for r in st['attempt_rows'] if r['split'] == 'train']
    assert seeds == list(range(8340000, 8340600))
    rep = json.loads((tmp_path / 'report.json').read_text())
    assert rep['stop'] == 'STOP_CAP' and rep['data_range_limited'] is True
    assert '성공 0 / 시도 600' in rep['A']['text'] and '학습 결과 아님' in rep['A']['text']


# --------------------------------------------------------------- restart

def test_restart_continues_and_matches_one_shot_run(tmp_path, prereg):
    outcome = lambda seed, case: result(success=seed % 2 == 0)
    collect(tmp_path / 'a', prereg, outcome, max_batches=3)
    collect(tmp_path / 'a', prereg, outcome, max_batches=3)          # second invocation resumes
    _, one, _ = collect(tmp_path / 'b', prereg, outcome, max_batches=6)
    two = pc.replay(prereg, pc.read_ledger(tmp_path / 'a' / 'ledger.jsonl'))
    key = lambda st: [(r['seed'], r['bin'], r['outcome']) for r in st['attempt_rows']]
    assert key(two) == key(one) and len(two['batches']) == 6


def test_finished_but_uningested_batch_is_ingested_not_rerun(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result())
    collect(tmp_path, prereg, None, episode=ep, max_batches=1)
    ledger = tmp_path / 'ledger.jsonl'
    lines = ledger.read_text().splitlines()
    cut = next(i for i, l in enumerate(lines) if json.loads(l)['type'] == 'attempt')
    ledger.write_text('\n'.join(lines[:cut + 3]) + '\n{"torn')     # crash during ingest
    stop, st, ep2 = collect(tmp_path, prereg, lambda s, c: result(), max_batches=0)
    assert stop == 'MAX_BATCHES' and ep2.calls == []
    assert st['batches'][0]['done'] and len(st['attempt_rows']) == 20


def test_interrupted_batch_retries_once_then_closes(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result(), crash_first=1)
    collect(tmp_path, prereg, None, episode=ep, max_batches=2)
    assert (tmp_path / 'batches/b000/try-1').exists() and (tmp_path / 'batches/b000/try-2').exists()
    st = pc.replay(prereg, pc.read_ledger(tmp_path / 'ledger.jsonl'))
    assert st['batches'][0]['done'] and all(r['outcome'] == 'success' for r in st['attempt_rows'])
    ep = FakeEpisode(lambda s, c: result(), crash_first=5)
    stop, st, _ = collect(tmp_path / 'x', prereg, None, episode=ep, max_batches=5)
    # two tries per batch, two HOST_ERROR batches in a row -> STOP_HOST
    assert stop == 'STOP_HOST' and len(ep.calls) == 4 and st['batches'][0]['done']
    assert {r['reason'] for r in st['attempt_rows']} == {'interrupted_twice'}


def test_host_error_world_is_requeued_once_with_same_seed_and_bin(tmp_path, prereg):
    ep = FakeEpisode(lambda s, c: result(success=False), drop_seeds={8340003})
    collect(tmp_path, prereg, None, episode=ep, max_batches=3)
    st = pc.replay(prereg, pc.read_ledger(tmp_path / 'ledger.jsonl'))
    rows = [r for r in st['attempt_rows'] if r['seed'] == 8340003]
    assert [r['outcome'] for r in rows] == ['host_error', 'failure']
    assert rows[0]['bin'] == rows[1]['bin'] and rows[1]['requeue'] is True
    # batch 2 = the re-queue + 19 new seeds: the re-queue consumes no new seed
    assert pc.totals(st)['attempts'] == 39 and st['host_errors'][rows[0]['bin']] == 1
    assert sorted({r['seed'] for r in st['attempt_rows'] if r['split'] == 'train'}) == list(range(8340000, 8340039))


def test_ledger_header_must_not_change(tmp_path, prereg):
    collect(tmp_path, prereg, lambda s, c: result(), max_batches=1)
    with pytest.raises(ValueError, match='header'):
        collect(tmp_path, prereg, lambda s, c: result(), max_batches=1, batch_size=10)


def test_deadline_stops_before_new_batch(tmp_path, prereg):
    import datetime as dt
    t = dt.datetime(2026, 10, 22, 0, 30, tzinfo=dt.timezone.utc)
    stop, st, ep = collect(tmp_path, prereg, lambda s, c: result(), deadline=t, now=lambda: t)
    assert stop == 'DEADLINE' and ep.calls == []


# ---------------------------------------------------------------- report

def test_ks_statistic():
    same = pc.ks_2samp([.1, .2, .3, .4], [.1, .2, .3, .4])
    assert same['D'] == 0 and same['p'] == 1
    far = pc.ks_2samp([i / 100 for i in range(50)], [1 + i / 100 for i in range(50)])
    assert far['D'] == 1 and far['p'] < 1e-6
    assert pc.ks_2samp([], [1.])['D'] is None


def test_report_separates_validation_and_bins(tmp_path, prereg):
    collect(tmp_path, prereg, lambda s, c: result(success=s % 2 == 0), max_batches=4)
    rep = json.loads((tmp_path / 'report.json').read_text())
    assert rep['validation']['attempts'] == 20 and rep['A']['attempts'] == 60
    assert sum(b['attempts'] for b in rep['A']['bins']) == 60
    assert rep['ks']['distance']['n1'] > 0 and rep['ks']['distance']['n2'] > 0
    assert '측정 모드' in rep['A']['text'] and 'C student n/20' in rep['not_pooled_with']


def test_collect_cases_geometry_respects_bins(prereg):
    """Setup-only generator (admission filter off here: frozen root is VM-only)."""
    import sys
    sys.path.insert(0, str(ROOT / 'experiments/2026-10-21-pairact-r1'))
    try:
        import collect_cases as cc
        geo = cc.Geometry(setup_validity=False)
    except ModuleNotFoundError as error:
        pytest.skip(f'geometry imports unavailable: {error}')
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
    # role must not follow the round-robin bin (seed offset % 6) or seed parity
    for k in range(6):
        roles = {cc.role_of(8340000 + k + 6 * j) for j in range(20)}
        assert roles == {'teal', 'blue'}


def test_prereg_seed_ranges_match_seeds_json(prereg):
    spec = json.loads((ROOT / 'experiments/2026-10-21-pairact-r1/seeds.json').read_text())
    pick = lambda r: (r['first'], r['last'])
    s = prereg['seeds']
    assert pick(s['train_primary']) == pick(spec['splits']['train'])
    assert pick(s['train_extension']) == pick(spec['train_extension'])
    assert pick(s['validation']) == pick(spec['splits']['validation'])
    assert pick(s['heldout']) == pick(spec['splits']['heldout'])
    import importlib.util as u
    sp = u.spec_from_file_location('seedcheck', ROOT / 'scripts/check_pairact_r1_seeds.py')
    m = u.module_from_spec(sp)
    sp.loader.exec_module(m)
    assert m.check(spec) == []
