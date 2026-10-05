"""v102 offline fitter on known synthetic plants: recovery, registered selection, held-out isolation, gate (no physics)."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import final_pair_loaded_gain_v102 as env  # noqa: E402
from scripts import fit_loaded_gain_calibration as fit  # noqa: E402

TRUTH_A = {'forward': {'g': 1.57, 'tau': .97, 'shape': {'u0': .0056}}, 'left': {'g': 1.175, 'tau': .97, 'shape': {'u0': .0072}}}
TRUTH_R0 = {'forward': {'g': 1.36, 'tau': .96, 'shape': {'u1': .0266}}, 'left': {'g': .964, 'tau': .97, 'shape': {'u1': .0282}}}
TAU_STOP = .085


def _write_run(raw, run, form, truth, noise=0., beam_z=.115, scramble_roles=()):
    folder = raw / run['id']
    (folder / run['id'] / 'eval_only').mkdir(parents=True)
    (folder / 'result.json').write_text(json.dumps({'cases': [{'protocol_complete': True, 'status': 'COLLECTED_UNQUALIFIED'}]}))
    x = fit.simulate(run, form, truth[run['axis']], TAU_STOP)
    if scramble_roles:                                   # corrupt the held-out windows of the "measured" displacement
        rng = np.random.default_rng(5)
        for w in fit.windows(run):
            if w['role'] in scramble_roles:
                x = x.copy()
                x[w['a'] + 1:w['b']] += rng.normal(size=w['b'] - w['a'] - 1) * .05     # interior only: the shared boundary sample is a fit window's reference
    rng = np.random.default_rng(1)
    x = x + rng.normal(size=len(x)) * noise
    stations = env.stations(run['beam_xy_yaw'])
    psi = run['beam_xy_yaw'][2]
    e = np.array([math.cos(psi), math.sin(psi)]) if run['axis'] == 'forward' else np.array([-math.sin(psi), math.cos(psi)])
    i0 = round(env.PREP_END_S / .05)
    n = round(run['sim_cap_s'] / .05) + 1
    s = np.zeros(n)
    s[i0:i0 + len(x)] = x
    s[i0 + len(x):] = x[-1]
    lines = []
    for k in range(n):
        q = [0.] * 40
        p1 = np.array(stations['r1'][:2]) + s[k] * e
        p2 = np.array(stations['r2'][:2]) + s[k] * e
        q[0], q[1] = p1
        y1, y2 = stations['r1'][2], stations['r2'][2]
        q[3:7] = [math.cos(y1 / 2), 0., 0., math.sin(y1 / 2)]
        q[17], q[18] = p2
        q[20:24] = [math.cos(y2 / 2), 0., 0., math.sin(y2 / 2)]
        lines.append(json.dumps({'t': 1.3 + k * .05, 'beam_xyz_m': [0., 0., beam_z], 'qpos': q}))
    # carriers stay 0.944 m apart in these stations
    (folder / run['id'] / 'eval_only' / 'trajectory.jsonl').write_text('\n'.join(lines) + '\n')


def synth(tmp_path, form, truth, **kw):
    plan = env.protocol()
    raw = tmp_path / 'raw'
    for run in plan['runs']:
        _write_run(raw, run, form, truth, **kw)
    return raw


@pytest.fixture(autouse=True)
def fast_starts(monkeypatch):
    full = fit.start_points
    monkeypatch.setattr(fit, 'start_points', lambda form, ref: full(form, ref)[1::4][:2])
    monkeypatch.setattr(fit, 'git_clean_sha', lambda: ('0' * 40, True))


def _run_stages(tmp_path, raw):
    class A:  # simple namespace
        pass
    a = A(); a.raw = raw; a.output = tmp_path / 'fit'
    fit.stage_fit(a)
    b = A(); b.raw = raw; b.fit = tmp_path / 'fit' / 'fit.json'; b.output = tmp_path / 'held'
    fit.stage_evaluate(b)
    return json.loads((tmp_path / 'fit' / 'fit.json').read_text()), json.loads((tmp_path / 'held' / 'heldout.json').read_text())


def test_affine_plant_is_recovered_and_form_A_is_chosen(tmp_path):
    raw = synth(tmp_path, 'A', TRUTH_A, noise=5e-4)
    fitj, held = _run_stages(tmp_path, raw)
    names = fitj['forms']['A']['names']
    p = dict(zip(names, fitj['forms']['A']['params']))
    assert p['left.g'] == pytest.approx(1.175, rel=.03) and p['left.u0'] == pytest.approx(.0072, rel=.15)
    assert p['forward.g'] == pytest.approx(1.57, rel=.03) and p['forward.tau'] == pytest.approx(.97, rel=.1)
    assert p['tau_stop'] == pytest.approx(TAU_STOP, rel=.5)
    assert held['status'] == 'VALIDATED_DEV' and held['chosen_form'] == {'forward': 'A', 'left': 'A'}
    left = held['per_axis']['left']
    assert not left['forms']['R0']['passes']                       # the current ramp form fails on an affine plant
    assert left['current_model']['metrics']['worst_leg_rel'] > .05   # the as-recorded loaded model misses the carry leg
    assert held['h3_fcc_leg']['new'][0]['displacement_m'] > 0.7


def test_ramp_plant_keeps_the_existing_form(tmp_path):
    raw = synth(tmp_path, 'R0', TRUTH_R0, noise=5e-4)
    _, held = _run_stages(tmp_path, raw)
    assert held['chosen_form'] == {'forward': 'R0', 'left': 'R0'}


def test_fit_never_reads_heldout_windows(tmp_path):
    raw1 = synth(tmp_path / 'a', 'A', TRUTH_A)
    raw2 = synth(tmp_path / 'b', 'A', TRUTH_A, scramble_roles=fit.HELD_ROLES)
    for t, raw in (('a', raw1), ('b', raw2)):
        class A: pass
        a = A(); a.raw = raw; a.output = tmp_path / t / 'fit'
        fit.stage_fit(a)
    j1 = json.loads((tmp_path / 'a' / 'fit' / 'fit.json').read_text())
    j2 = json.loads((tmp_path / 'b' / 'fit' / 'fit.json').read_text())
    for f in fit.FORMS:
        assert j1['forms'][f]['params'] == j2['forms'][f]['params']
    assert all(row['role'] in fit.FIT_ROLES for row in j2['steady_table'])
    assert j2['held_out_windows_used'] is False


def test_validity_gate_rejects_a_dropped_beam(tmp_path):
    raw = synth(tmp_path, 'A', TRUTH_A, beam_z=.02)
    class A: pass
    a = A(); a.raw = raw; a.output = tmp_path / 'fit'
    with pytest.raises(ValueError, match='validity gate'):
        fit.stage_fit(a)


def test_product_replaces_only_the_registered_loaded_fields_and_never_overwrites(tmp_path):
    raw = synth(tmp_path, 'A', TRUTH_A, noise=5e-4)
    fitj, held = _run_stages(tmp_path, raw)
    base = ROOT / 'experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json'
    if not base.exists():
        pytest.skip('base calibration not present in this checkout')
    class A: pass
    a = A(); a.fit = tmp_path / 'fit' / 'fit.json'; a.heldout = tmp_path / 'held' / 'heldout.json'; a.base = base
    a.base_sha256 = fit.sha_file(base); a.rule = 'DEV_PILOT_C0_ZERO_v1'; a.output = tmp_path / 'prod'
    fit.stage_product(a)
    cal = json.loads((tmp_path / 'prod' / 'calibration_dev_pilot_loaded_v102.json').read_text())
    old = json.loads(base.read_text())
    new_ml, old_ml = cal['params']['motion_loaded'], old['params']['motion_loaded']
    for key in ('noise_abs', 'noise_rel', 'load_transition', 'drift_ratio_std', 'yaw_bias_std_rad_s', 'rest_noise', 'use_scale'):
        assert new_ml[key] == old_ml[key]
    assert new_ml['gain'][2] == old_ml['gain'][2] and new_ml['tau_axis_s'][2] == old_ml['tau_axis_s'][2]
    assert new_ml['deadband']['u1'][2] == old_ml['deadband']['u1'][2]                  # turn axis unchanged
    assert new_ml['deadband']['u0'][0] > 0 and new_ml['deadband']['c0'][:2] == [0., 0.] and new_ml['deadband']['u1'][:2] == [fit.RAMP_OFF_U1] * 2
    assert cal['params']['motion'] == old['params']['motion'] and cal['camera_models'] == old['camera_models']
    assert cal['dev_rule'] == 'DEV_PILOT_C0_ZERO_v1' and cal['loaded_gain_calibration']['bundle_id'] == env.BUNDLE_ID and cal['confirmatory'] is False and cal['status'] == 'DEV_PILOT'
    with pytest.raises(FileExistsError):
        fit.stage_product(a)
    with pytest.raises(FileExistsError):
        fit.write_new(tmp_path / 'prod' / 'calibration_dev_pilot_loaded_v102.json', {})
