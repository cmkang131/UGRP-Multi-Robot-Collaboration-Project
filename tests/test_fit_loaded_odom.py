"""scripts/fit_loaded_odom.py + scripts/make_hybrid_config.py: synthetic carry runs, no simulator."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from harness import hybrid_carry as hc
from harness import pair_carry_eval as ce
from harness import pair_carry_teacher_warp as ct

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json').read_text())
ROLES = {'r1': 'teal', 'r2': 'blue'}
TRUE = {'forward_m_per_pct_s': .0036, 'lateral_m_per_pct_s': .0031, 'yaw_deg_per_pct_s': .82, 'latency_ticks': 1,
        'forward_bias_m_per_s': .002, 'lateral_bias_m_per_s': -.001, 'yaw_bias_deg_per_s': .3}


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


fit = load('fit_loaded_odom')
mk = load('make_hybrid_config')


def truth(beam, robots, t):
    return {'t': t, 'beam': {'pose': list(beam), 'min_z': .03, 'tilt_deg': 1., 'xyz': [beam[0], beam[1], .05]},
            'robots': {rid: {'pose': list(p)} for rid, p in robots.items()},
            'contacts': {'r1': [2., 2.], 'r2': [2., 2.]}, 'objects': {}}


def carry_world(beam0=(.7, -1.5, .3), true=TRUE, cap=60., t0=30.):
    """GT teacher closed loop on a kinematic world that moves by the TRUE loaded model."""
    robots = {'r1': ct.compose(beam0, (-.5, 0., 0.)), 'r2': ct.compose(beam0, (.5, 0., math.pi)), 'r3': (-.8, 1.2, 0.)}
    arm = {rid: fit.DUMMY_ARM for rid in ROLES}
    pwm = {rid: {s: 1500 for s in (1, 3, 4, 5, 6)} for rid in ROLES}
    rows, t = [truth(beam0, robots, t0)], t0
    teacher = ct.PairCarryTeacherWarp(ROLES, rows[0], t0, MAP, arm, pwm, wheel_fn=fit.duty_wheels)
    odo = {rid: hc.OwnOdometry(true, sigma_xy_per_m=0, sigma_yaw_per_rad=0, pose=robots[rid]) for rid in ROLES}
    off = ct.relative(robots['r1'], beam0)
    beam = beam0
    while t < t0 + cap and not teacher.done:
        t = round(t + .1, 6)
        row = truth(beam, robots, t)
        rows.append(row)
        out = teacher.step(row, t)
        for rid, (cmd, _done) in out.items():
            robots[rid] = odo[rid].step(cmd)
        if teacher.phase in ct.PHASES[:ct.PHASES.index('lower')]:
            beam = ct.compose(robots['r1'], off)
    rows.append(truth(beam, robots, round(t + .1, 6)))
    return teacher, rows


def write_run(path, worlds):
    """worlds: [(seed, teacher, rows, extra_files)] -> run root in the runner layout."""
    entries = []
    for i, (seed, teacher, rows, extra) in enumerate(worlds):
        raw = path/f'world-{i:03d}'/'raw'; raw.mkdir(parents=True)
        if teacher is not None:
            (raw/'result.json').write_text(json.dumps({'carry': teacher.diagnostic()}))
        if teacher is not None and rows is not None:
            ev = [ce.eval_row(r) for r in rows]
            (raw/'carry-eval.json').write_text(json.dumps({'drive_response': ce.drive_response(ev, teacher.log,
                                                                                               list(ROLES))}))
        if rows is not None:
            (raw/'eval-only.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        for name, text in (extra or {}).items():
            (raw/name).write_text(text)
        entries.append({'world': i, 'seed': seed})
    path.mkdir(parents=True, exist_ok=True)
    (path/'summary.json').write_text(json.dumps({'worlds': entries}))
    return path


@pytest.fixture(scope='module')
def two_worlds():
    return carry_world(), carry_world((.6, -1.7, -.2))


def test_duty_wheels_matches_the_port_formula():
    from harness.grasp_act_contract import wheel_mix
    w, d = fit.duty_wheels((.24, 0., 0.))
    assert w == [.35]*4 and d == pytest.approx([.1*.24/.35]*4)
    w, d = fit.duty_wheels((0., 0., 0.))
    assert w == [0.]*4 and d == [0.]*4
    assert len(wheel_mix((1, 2, 3))) == 4


def test_fit_recovers_gain_latency_bias_from_teacher_replay(tmp_path, two_worlds):
    (ta, ra), (tb, rb) = two_worlds
    assert len(ta.log) > 100
    run = write_run(tmp_path/'pilot', [(8343000, ta, ra, None), (8420011, tb, rb, None)])
    rep = fit.run_fit([run])
    c = rep['calibration']
    assert c['latency_ticks'] == TRUE['latency_ticks']
    for k in hc.GAIN_KEYS:
        assert c[k] == pytest.approx(TRUE[k], rel=.02), k
    assert c['forward_bias_m_per_s'] == pytest.approx(TRUE['forward_bias_m_per_s'], abs=5e-4)
    assert c['yaw_bias_deg_per_s'] == pytest.approx(TRUE['yaw_bias_deg_per_s'], abs=.1)
    assert all(w['source'] == 'teacher_replay' and w['replay']['ok'] and w['drive_response_matches']
               for w in rep['worlds'])
    assert rep['seeds'] == [8343000, 8420011] and rep['excluded'] == []
    assert rep['sigma']['sigma_xy_per_m'] < .02                # exact model -> tiny drift
    assert rep['values_sha256'] == hc.calibration_values_sha256(c, rep['sigma'])
    best = min((x for x in rep['latency_scan'] if x['cost'] is not None), key=lambda x: x['cost'])
    assert best['latency_ticks'] == 1


def test_heldout_or_training_seed_stops_the_fit(tmp_path, two_worlds):
    (ta, ra), _ = two_worlds
    for seed in (8340005, 8341000, 8343040, 8420000):
        run = write_run(tmp_path/f's{seed}', [(8343000, ta, ra, None), (seed, ta, ra, None)])
        with pytest.raises(SystemExit, match='SEED_NOT_ALLOWED'):
            fit.run_fit([run])


def test_replay_mismatch_and_aggregate_only_worlds_are_excluded_not_fitted(tmp_path, two_worlds):
    (ta, ra), (tb, rb) = two_worlds
    bad = copy.deepcopy(ta)
    for e in bad.events:
        if e.get('event') == 'phase':
            e['t'] += .1                                         # record no longer equals the replay
            break
    agg = {'carry-eval.json': json.dumps({'drive_response': ce.drive_response([ce.eval_row(r) for r in rb], tb.log,
                                                                              list(ROLES))})}
    run = write_run(tmp_path/'mix', [(8343000, bad, ra, None), (8343001, tb, None, agg), (8343002, tb, rb, None)])
    rep = fit.run_fit([run])
    why = {w['seed']: w.get('excluded') for w in rep['worlds']}
    assert why == {8343000: 'replay_differs_from_record', 8343001: 'no_per_tick_source', 8343002: None}
    assert rep['seeds'] == [8343002]
    only_agg = write_run(tmp_path/'agg', [(8343001, tb, None, agg)])
    with pytest.raises(SystemExit, match='NO_FIT_DATA'):
        fit.run_fit([only_agg])


def test_hybrid_code_log_is_a_per_tick_source(tmp_path, two_worlds):
    (ta, ra), _ = two_worlds
    log = ''.join(json.dumps({'t': e['t'], 'segment': 'CODE_CARRY',
                              'commands': {rid: {'wheels': e['wheels'][rid], 'duration_s': e['duration_s'][rid]}
                                           for rid in ROLES}}) + '\n' for e in ta.log)
    run = write_run(tmp_path/'hyb', [(8420017, None, ra, {'hybrid-drive.jsonl': log})])
    rep = fit.run_fit([run])
    assert rep['worlds'][0]['source'] == 'hybrid_code_log'
    assert rep['calibration']['latency_ticks'] == 1
    assert rep['calibration']['forward_m_per_pct_s'] == pytest.approx(TRUE['forward_m_per_pct_s'], rel=.03)


# ------------------------------------------------------------------ config generator

TEMPLATE = ROOT/'experiments/2026-10-21-pairact-p2/HYBRID_CARRY_NAV_TEMPLATE_V2.json'
OWNER = ['limits.carry_budget_s=110', 'limits.sigma_xy_max_m=.25', 'limits.sigma_yaw_max_deg=6',
         'nav.profile=gpu_calib_v5_h112', 'nav.arm_ground_m=.9', 'nav.advance_m=.45',
         'nav.source=/home/ugrp/ugrp-sim/src/pairact-hybrid/nav']


def fit_file(tmp_path, two_worlds):
    (ta, ra), (tb, rb) = two_worlds
    run = write_run(tmp_path/'p', [(8343000, ta, ra, None), (8420011, tb, rb, None)])
    out = tmp_path/'fit'
    fit.main(['--run', str(run), '--out', str(out)])
    return out/'loaded-odom-fit.json'


def test_template_is_refused_until_the_fit_tool_fills_it(tmp_path, two_worlds):
    tmpl = json.loads(TEMPLATE.read_text())
    with pytest.raises((ValueError, TypeError)):
        hc.validate_config(tmpl)
    f = fit_file(tmp_path, two_worlds)
    cfg = mk.build(json.loads(f.read_text()), hashlib.sha256(f.read_bytes()).hexdigest(), tmpl, OWNER,
                   purpose='teacher_smoke')
    assert hc.validate_config(cfg, purpose='teacher_smoke')
    fitted = json.loads(f.read_text())
    assert cfg['calibration'] == fitted['calibration']
    assert {k: cfg['limits'][k] for k in hc.SIGMA_FIT_KEYS} == fitted['sigma']
    assert cfg['calibration_provenance']['fit_sha256'] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert cfg['shadow_predict'] is False
    out = tmp_path/'hybrid.json'
    mk.main(['--fit', str(f), '--template', str(TEMPLATE), '--purpose', 'hybrid_n', '--out', str(out),
             *sum((['--set', x] for x in OWNER), [])])
    assert hc.load_config(out)


def test_generator_refuses_fitted_keys_missing_owner_values_and_tampered_fit(tmp_path, two_worlds):
    tmpl = json.loads(TEMPLATE.read_text())
    f = fit_file(tmp_path, two_worlds)
    fitted = json.loads(f.read_text()); sha = hashlib.sha256(f.read_bytes()).hexdigest()
    for bad in ('calibration.forward_m_per_pct_s=.004', 'limits.sigma_xy_per_m=.01',
                'calibration_provenance.seeds=[1]', 'mode=x'):
        with pytest.raises(ValueError, match='owner'):
            mk.build(fitted, sha, tmpl, OWNER + [bad], purpose='teacher_smoke')
    with pytest.raises(ValueError, match='확인 필요'):
        mk.build(fitted, sha, tmpl, OWNER[:-2], purpose='teacher_smoke')       # nav.advance_m still a placeholder
    t = dict(fitted, calibration=dict(fitted['calibration'], yaw_deg_per_pct_s=1.))
    with pytest.raises(ValueError, match='values_sha256'):
        mk.build(t, sha, tmpl, OWNER, purpose='teacher_smoke')
    with pytest.raises(ValueError, match='fit_sha256'):
        mk.main(['--fit', str(f), '--template', str(TEMPLATE), '--purpose', 'teacher_smoke', '--out',
                 str(tmp_path/'x.json'), '--expect-fit-sha256', '0'*64, *sum((['--set', x] for x in OWNER), [])])


def test_values_hash_is_the_shared_canonical_form():
    # same literal in root tests/test_pairact_p2_root.py (hybrid smoke): both trees hash identically
    cal = {'forward_m_per_pct_s': .0036, 'lateral_m_per_pct_s': .0031, 'yaw_deg_per_pct_s': .82, 'latency_ticks': 1,
           'forward_bias_m_per_s': .002, 'lateral_bias_m_per_s': -.001, 'yaw_bias_deg_per_s': .3}
    lim = {'sigma_xy_per_m': .05, 'sigma_yaw_per_rad': .1}
    assert hc.calibration_values_sha256(cal, lim) == hashlib.sha256(json.dumps(
        {'calibration': cal, 'sigma': lim}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
