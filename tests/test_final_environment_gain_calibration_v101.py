"""v101 unloaded gain calibration: static plan, command table, offline fitter on a known synthetic plant."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import final_environment_gain_calibration_v101 as env  # noqa: E402
from scripts import fit_unloaded_gain_calibration as fit  # noqa: E402

TRUTH = {'gain': [1.5, 1.2, 1.1], 'tau_axis_s': [.8, .8, .17], 'tau_stop_s': .08}


def test_plan_is_registered_generator_output_and_admitted():
    plan = env.protocol()
    assert plan == env.build_plan()
    report = env.validate(plan, for_execution=True)
    assert set(report) == {'fitA1', 'fitA2', 'heldA3', 'heldM1', 'heldP1', 'heldP2'}
    assert all(v['admitted'] for v in report.values())
    assert {r['role'] for r in plan['runs']} == {'fit', 'heldout'}
    assert all(r['seed'] != 911 for r in plan['runs'])
    assert [r['id'] for r in plan['runs'] if r['role'] == 'fit'] == ['fitA1', 'fitA2']


def test_changed_plan_is_rejected():
    plan = json.loads(json.dumps(env.protocol()))
    plan['runs'][0]['segments'][0]['start'][0] = .13
    with pytest.raises(ValueError, match='contract changed'):
        env.validate(plan, for_execution=False)


def test_command_table_respects_live_cadence_and_limits():
    plan = env.protocol()
    assert plan['control_period_s'] == .1 and plan['command_lease_s'] == .15
    for run in plan['runs']:
        table = env.command_table(run, plan)
        assert table.shape == (round(run['sim_cap_s'] / .1), 3)
        assert table[:round(plan['initial_hold_s'] / .1)].max() == 0 and table[:15].min() == 0
        assert table[:, 0].max() <= .15 and table[:, 0].min() >= -.05
        assert np.abs(table[:, 1]).max() <= .10 and np.abs(table[:, 2]).max() <= .15


def test_blocks_start_from_rest_and_cover_registered_levels():
    plan = env.protocol()
    for run in plan['runs'][:3]:
        table = env.command_table(run, plan)
        windows = fit.make_windows(run, plan)
        levels = {}
        for w in windows:
            levels.setdefault(w['axis'], set()).add(round(w['level'], 6))
            a_ctrl = w['a'] // 2
            assert not table[max(a_ctrl - 15, 0):a_ctrl].any()          # >= 1.5 s of zero command before every block
        want = env.FIT_LEVELS if run['role'] == 'fit' else env.HELD_LEVELS
        assert levels == {k: {round(v, 6) for v in vs} for k, vs in want.items()}


def _synthetic_raw(tmp_path, truth=TRUTH, deadband=None, noise=0.):
    plan = env.protocol()
    raw = tmp_path / 'raw'
    rng = np.random.default_rng(3)
    for run in plan['runs']:
        folder = raw / run['id'] / run['id']
        (folder / 'eval_only/r1').mkdir(parents=True)
        (folder / 'robots/r1').mkdir(parents=True)
        table = env.command_table(run, plan)
        U = np.repeat(table, 2, axis=0)
        n = len(U)
        p = np.array([*truth['gain'], *truth['tau_axis_s'], truth['tau_stop_s']])
        form = 'linear_diag'
        if deadband is not None:
            p = np.array([*p, *deadband['c0'], *deadband['u1']])
            form = 'deadband_diag'
        rel = fit.predict(U, form, p, 0, n)
        x0, y0, yaw0 = run['spawn_xy_yaw']
        c, s = math.cos(yaw0), math.sin(yaw0)
        xs = x0 + c * rel[:, 0] - s * rel[:, 1] + noise * rng.normal(size=n + 1)
        ys = y0 + s * rel[:, 0] + c * rel[:, 1] + noise * rng.normal(size=n + 1)
        yaw = yaw0 + rel[:, 2]
        with (folder / 'eval_only/r1/pose.jsonl').open('w') as f:
            for k in range(n + 1):
                R = [[math.cos(yaw[k]), -math.sin(yaw[k]), 0.], [math.sin(yaw[k]), math.cos(yaw[k]), 0.], [0., 0., 1.]]
                f.write(json.dumps({'t': 1.3 + .05 * k, 'base_position_m': [xs[k], ys[k], .03], 'base_rotation': R}) + '\n')
        with (folder / 'robots/r1/commands.jsonl').open('w') as f:
            for i, row in enumerate(table):
                f.write(json.dumps({'t': 1.3 + .1 * i, 'kind': 'mecanum', 'forward': row[0], 'left': row[1],
                                    'turn': row[2], 'duration_s': .15}) + '\n')
        (folder / 'result.json').write_text(json.dumps({'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True}))
    return raw


@pytest.fixture
def clean_tree(monkeypatch):
    monkeypatch.setattr(fit, 'git_clean_sha', lambda: ('0' * 40, True))


def _args(**kw):
    return type('A', (), kw)


@pytest.fixture(scope='module')
def fitted(tmp_path_factory):
    """One synthetic linear plant, fitted/evaluated/registered once and shared by the tests below."""
    tmp = tmp_path_factory.mktemp('gaincal')
    patch = pytest.MonkeyPatch()
    patch.setattr(fit, 'git_clean_sha', lambda: ('0' * 40, True))
    try:
        raw = _synthetic_raw(tmp)
        fit.stage_fit(_args(raw=raw, output=tmp / 'fit'))
        fit.stage_evaluate(_args(raw=raw, fit=tmp / 'fit/fit.json', output=tmp / 'held'))
        base = ROOT / 'experiments/2026-10-03-v92-dev-pilot/calibration_dev_pilot.json'
        fit.stage_product(_args(fit=tmp / 'fit/fit.json', heldout=tmp / 'held/heldout.json', base=base,
                                base_sha256=fit.sha_file(base), output=tmp / 'prod'))
    finally:
        patch.undo()
    return {'tmp': tmp, 'raw': raw, 'base': base}


def test_fit_recovers_known_linear_plant_and_reads_fit_runs_only(fitted):
    record = json.loads((fitted['tmp'] / 'fit/fit.json').read_text())
    lin = record['forms']['linear_diag']
    assert np.allclose([lin['gain'][i][i] for i in range(3)], TRUTH['gain'], rtol=1e-3)
    assert np.allclose(lin['tau_axis_s'], TRUTH['tau_axis_s'], rtol=1e-2)
    assert lin['tau_stop_s'] == pytest.approx(TRUTH['tau_stop_s'], rel=.2)
    assert [r['id'] for r in record['fit_runs']] == ['fitA1', 'fitA2']


def test_heldout_accepts_the_true_model_and_keeps_the_linear_form(fitted):
    heldout = json.loads((fitted['tmp'] / 'held/heldout.json').read_text())
    assert heldout['status'] == 'VALIDATED_DEV' and heldout['chosen_form'] == 'linear_diag'
    assert all(heldout['checks'].values())


def test_product_fills_the_ten_fields_without_touching_the_base(fitted):
    base = fitted['base']
    cal = json.loads((fitted['tmp'] / 'prod/C/calibration_dev_pilot_unloaded_v101.json').read_text())
    assert cal['missing'] == [] and cal['status'] == 'DEV_PILOT'
    motion = cal['params']['motion']
    assert set(motion) >= {'gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'noise_rel', 'noise_abs', 'scale_std',
                           'scale_walk', 'use_scale', 'rest_noise'}
    assert motion['noise_rel'] == [0.3176, 0.4438, 0.1116]             # registered r4/r5 noise (diff C)
    assert np.allclose([motion['gain'][i][i] for i in range(3)], TRUTH['gain'], rtol=1e-3)
    assert cal['field_provenance']['params.motion.gain'] == 'measured_unloaded_gain_calibration_v101'
    assert cal['field_provenance']['params.motion.noise_rel'] == 'registered_r4_r5_measured_noise'
    assert cal['params']['motion_loaded'] == json.loads(base.read_text())['params']['motion_loaded']
    other = json.loads((fitted['tmp'] / 'prod/C2/calibration_dev_pilot_unloaded_v101.json').read_text())['params']['motion']
    assert other['gain'] == motion['gain'] and other['noise_abs'] != motion['noise_abs']
    assert fit.sha_file(base) == '398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5'


def test_evaluate_refuses_to_run_on_a_modified_fit(fitted, tmp_path):
    copy = tmp_path / 'fit'
    copy.mkdir()
    (copy / 'fit.json').write_text((fitted['tmp'] / 'fit/fit.json').read_text() + ' ')
    (copy / 'fit.json.sha256').write_text((fitted['tmp'] / 'fit/fit.json.sha256').read_text())
    with pytest.raises(ValueError, match='hash mismatch'):
        fit.stage_evaluate(_args(raw=fitted['raw'], fit=copy / 'fit.json', output=tmp_path / 'held'))


def test_product_is_refused_when_heldout_fails(fitted, tmp_path, clean_tree):
    held = tmp_path / 'held'
    held.mkdir()
    value = json.loads((fitted['tmp'] / 'held/heldout.json').read_text())
    value['status'] = 'FAILED_HELDOUT'
    (held / 'heldout.json').write_text(json.dumps(value))
    (held / 'heldout.json.sha256').write_text(fit.sha_file(held / 'heldout.json') + '\n')
    with pytest.raises(ValueError, match='held-out acceptance failed'):
        fit.stage_product(_args(fit=fitted['tmp'] / 'fit/fit.json', heldout=held / 'heldout.json', base=fitted['base'],
                                base_sha256=fit.sha_file(fitted['base']), output=tmp_path / 'prod'))


def test_deadband_plant_selects_deadband_form(tmp_path, clean_tree):
    truth = {'gain': [1.5, 1.2, 1.1], 'tau_axis_s': [.8, .8, .17], 'tau_stop_s': .08}
    raw = _synthetic_raw(tmp_path, truth, deadband={'c0': [.006, .01, .01], 'u1': [.05, .06, .05]})
    out, held = tmp_path / 'fit', tmp_path / 'held'
    fit.stage_fit(_args(raw=raw, output=out))
    fit.stage_evaluate(_args(raw=raw, fit=out / 'fit.json', output=held))
    assert json.loads((held / 'heldout.json').read_text())['chosen_form'] == 'deadband_diag'
