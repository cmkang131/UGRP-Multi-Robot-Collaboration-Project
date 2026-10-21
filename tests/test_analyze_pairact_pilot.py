"""scripts/analyze_pairact_pilot.py on a synthetic pilot tree built from the
real teacher module (no simulator, no VM files)."""
import json
import shutil
import subprocess

import pytest

from harness import pair_carry_teacher_warp as ct
from scripts import analyze_pairact_pilot as ap
from test_pair_carry_detour import W1_BEAM, W1_OFF, w1_object
from test_pair_carry_teacher_warp import ARM, MAP, PWM, ROLES, handover, wheels


def _row(t, beam, offsets, objects, min_z=.03):
    robots = {rid: list(ct.compose(beam, off)) for rid, off in offsets.items()}
    robots['r3'] = [-.8, 1.2, 0.]
    return {'t': t, 'beam': {'pose': list(beam), 'min_z': min_z, 'tilt_deg': 1.}, 'robots': {k: {'pose': v} for k, v in
            robots.items()}, 'contacts': {'r1': [2., 2.], 'r2': [2., 2.]},
            'objects': {o['id']: {'xy': o['xy'], 'radius': o['radius']} for o in objects}}


def _world(run, i, *, result, eval_rows=None, carry_eval=None, route=None, zst=False):
    raw = run/f'world-{i:03d}'/'raw'
    raw.mkdir(parents=True)
    (raw/'result.json').write_text(json.dumps(result))
    if carry_eval is not None:
        (raw/'carry-eval.json').write_text(json.dumps(carry_eval))
    if route is not None:
        (raw/'carry-route.json').write_text(json.dumps(route))
    if eval_rows is not None:
        p = raw/'eval-only.jsonl'
        p.write_text(''.join(json.dumps(r) + '\n' for r in eval_rows))
        if zst:
            subprocess.check_call(['zstd', '-q', '--rm', str(p)])


def _blocked_teacher(mode):
    obstacles = w1_object('r2')
    row = _row(23.5, W1_BEAM, W1_OFF, obstacles)
    teacher = ct.PairCarryTeacherWarp(ROLES, row, 23.5, MAP, ARM, PWM, wheel_fn=wheels,
                                      obstacles=ct.carry_obstacles(row, ROLES), route_mode=mode)
    return teacher, row


@pytest.fixture
def pilot(tmp_path):
    run = tmp_path/'pilot-8343000'
    worlds = []
    # 0: success
    t = ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, .3)), 20., MAP, ARM, PWM, wheel_fn=wheels)
    _world(run, 0, result={'status': 'complete', 'carry': json.loads(json.dumps(t.diagnostic()))},
           carry_eval={'success': True, 'failure': None, 'funnel': {}})
    worlds.append(dict(world=0, seed=8343000, success=True, sim_s=110., cap_end=False, carry_success=True))
    # 1: grasp cap_end (root definition: not grasp success and sim >= cap_s)
    _world(run, 1, result={'status': 'complete', 'carry': {'started': False, 'reason': 'no_joint_hold_3s'},
                           'teachers': {'r1': {'outcome': 'no_stable_joint_hold_3s'}}})
    worlds.append(dict(world=1, seed=8343001, success=False, sim_s=60., cap_end=True, carry_success=False))
    # 2: literal route_blocked (straight_v1), eval-only rows zstd-compressed like compress_logs
    tb, row = _blocked_teacher('straight_v1')
    _world(run, 2, result={'status': 'complete', 'carry': json.loads(json.dumps(tb.diagnostic()))},
           carry_eval={'success': False, 'failure': 'not_through_door', 'carried_max_m': .0006},
           eval_rows=[_row(23.4, W1_BEAM, W1_OFF, w1_object('r2')), row], zst=True)
    worlds.append(dict(world=2, seed=8343002, success=True, sim_s=25., cap_end=False, carry_success=False,
                       carry_failure='not_through_door'))
    # 3: drop during door_pass
    t3 = ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, .3)), 20., MAP, ARM, PWM, wheel_fn=wheels)
    t3.events += [{'t': 30., 'event': 'phase', 'from': 'carry_hold', 'to': 'to_west_staging'},
                  {'t': 60., 'event': 'phase', 'from': 'to_door_entry', 'to': 'door_pass'}]
    t3.outcome = 'command_sequence_complete'
    _world(run, 3, result={'status': 'complete', 'carry': json.loads(json.dumps(t3.diagnostic()))},
           carry_eval={'success': False, 'failure': 'drop', 'drop_events': [{'t': 65., 'kind': 'carry_low'}]})
    worlds.append(dict(world=3, seed=8343003, success=True, sim_s=90., cap_end=False, carry_success=False,
                       carry_failure='drop'))
    (run/'summary.json').write_text(json.dumps({'worlds': worlds}))
    return run


def test_cause_table(pilot, tmp_path):
    rep = ap.main(['--run', str(pilot), '--out', str(tmp_path/'out')])
    by = {w['world']: w for w in rep['worlds']}
    assert by[0]['category'] == 'success'
    assert by[1]['cause'] == 'grasp_cap_end'
    assert by[2]['category'] == 'route'
    assert by[2]['cause'] == 'route_blocked@to_west_staging/object'
    assert by[3]['cause'] == 'drop:carry_low@door_pass'
    s = rep['summary']
    assert s['N'] == 4 and s['carry_success_n'] == 1 and s['grasp_success_n'] == 3 and s['cap_end_n'] == 1
    assert s['teacher_outcomes']['route_blocked'] == 1
    md = (tmp_path/'out'/'pilot-analysis.md').read_text()
    assert 'route_blocked@to_west_staging/object' in md and '학습 아님' in md
    json.loads((tmp_path/'out'/'pilot-analysis.json').read_text())


@pytest.mark.skipif(shutil.which('zstd') is None, reason='zstd binary needed to decode eval-only.jsonl.zst')
def test_replay_reproduces_recorded_block_and_runs_detour(pilot, tmp_path):
    rep = ap.main(['--run', str(pilot), '--out', str(tmp_path/'out'), '--replay', '--replay-modes', 'detour_v1,bogus'])
    w = next(w for w in rep['worlds'] if w['world'] == 2)
    r = w['replay']
    assert r['replayed'] and r['handover_t'] == pytest.approx(23.5)
    assert r['straight']['blocked'] and r['straight']['matches_record'] is True
    assert r['nearest_obstacles'][0]['id'] == 'w1_object'
    assert r['modes']['detour_v1']['available'] and r['modes']['detour_v1']['outcome'] is None
    assert r['modes']['detour_v1']['variant'] == 'detour'
    assert r['modes']['bogus'] == {'available': False}
    assert rep['summary']['replay_modes'] == {'detour_v1:path': 1}
    # worlds without eval-only rows are reported as not replayed, never guessed
    assert next(w for w in rep['worlds'] if w['world'] == 3)['replay']['replayed'] is False


def test_verify_against_artifact_manifest(pilot, tmp_path):
    import hashlib
    f = pilot/'world-000'/'raw'/'result.json'
    (pilot/'artifact-sha256.json').write_text(json.dumps({
        'world-000/raw/result.json': {'sha256': hashlib.sha256(f.read_bytes()).hexdigest()},
        'world-001/raw/result.json': {'sha256': '0'*64}}))
    rep = ap.main(['--run', str(pilot), '--out', str(tmp_path/'o'), '--verify'])
    v = rep['verify']['pilot-8343000']
    assert v['checked'] == 2 and v['mismatch'] == ['world-001/raw/result.json']


def test_missing_summary_fails_closed(tmp_path):
    with pytest.raises(SystemExit, match='MISSING_SUMMARY'):
        ap.main(['--run', str(tmp_path), '--out', str(tmp_path/'o')])


def test_phase_at():
    ev = [{'t': 1., 'event': 'phase', 'to': 'a'}, {'t': 2., 'event': 'fail'}, {'t': 3., 'event': 'phase', 'to': 'b'}]
    assert ap.phase_at(ev, .5) == 'carry_hold' and ap.phase_at(ev, 2.5) == 'a' and ap.phase_at(ev, 3.) == 'b'
