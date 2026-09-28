"""Stage-probe harness: pure logic (no MuJoCo). Stage probe, not E2E success."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from harness import pair_stage_probe as sp

ROOT = Path(__file__).resolve().parents[1]


def test_module_and_plan_mode_import_no_simulator():
    program = ('import sys; from harness import pair_stage_probe; import scripts.run_pair_stage_probes as r; '
               'r.main(["--stage","align","grasp_lift","--output","/nonexistent/never","--sources","teacher"]); '
               'assert "mujoco" not in sys.modules, sorted(m for m in sys.modules if "mujoco" in m)')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    plan = json.loads(out.stdout)
    assert plan['state'] == 'planned' and plan['cases'] == 38


def test_registry_labels_and_bootstrap_delegated():
    assert 'not_e2e_success' in sp.LABELS and 'stage_probe' in sp.LABELS
    assert sp.STAGES['bootstrap']['implemented'] is False
    assert 'zone-pair-v6-boot' in sp.STAGES['bootstrap']['owner']
    with pytest.raises(ValueError, match='not implemented'):
        sp.teacher_cases('bootstrap')
    orders = [sp.STAGES[s]['order'] for s in ('bootstrap', 'align', 'grasp_lift', 'carry', 'setdown')]
    assert orders == [1, 2, 3, 4, 5]


def test_teacher_grid_prior_is_static_plan_not_placement():
    cases = sp.teacher_cases('align')
    assert len(cases) == 19 and len({c['case_id'] for c in cases}) == 19
    plan = sp.stations(sp.BASE_SETUP['coarse_order_sheet']['beam_xyyaw'])['prestation']
    for c in cases:
        for rid in sp.PARTICIPANTS:
            prior = c['prior'][rid]
            assert prior['is_fix'] is False and prior['mean_xyyaw'] == plan[rid]
            assert 'not GT' in prior['source']
    moved = next(c for c in cases if c['cell'] == 'lat+/opp')
    r1, r2 = moved['placement_xyyaw']['r1'], moved['placement_xyyaw']['r2']
    # r1 faces +x: left is +y. r2 faces -x and gets the opposite offset -> its left (-y) negated = +y.
    assert r1[1] - plan['r1'][1] == pytest.approx(.04) and r2[1] - plan['r2'][1] == pytest.approx(.04)


def test_later_stages_start_at_true_station_with_align_tolerance_grid():
    cases = sp.teacher_cases('grasp_lift', nominal_seeds=(911,))
    true = sp.stations(sp.BASE_SETUP['beam_xyyaw'])['station']
    nominal = next(c for c in cases if c['cell'] == 'nominal')
    assert nominal['placement_xyyaw'] == {r: pytest.approx(true[r]) for r in sp.PARTICIPANTS}
    corner = next(c for c in cases if c['cell'] == 'corner++/same')
    assert corner['offsets']['r1'] == [.012, .008, .035]
    assert all(c['teacher_held'] is False for c in cases)
    assert all(c['teacher_held'] is True for c in sp.teacher_cases('carry', nominal_seeds=(911,)))


def test_offset_and_grip_errors_geometry():
    p = sp.offset_pose([1., 2., math.pi / 2], .1, .2, .05)
    assert p == pytest.approx([.8, 2.1, math.pi / 2 + .05])
    geo = sp.stations([1.0, .05, 0.])
    for rid in sp.PARTICIPANTS:
        e = sp.grip_errors(geo['station'][rid], geo['grip_xyz'][rid][:2], geo['station'][rid][2])
        # catalogue station puts the grip 0.155 m ahead; the controller targets 0.162 (7 mm, inside tolerance)
        assert abs(e['grip_x_err_m']) < sp.CRITERIA['align']['grip_x_err_m']
        assert e['grip_y_err_m'] == pytest.approx(0., abs=1e-9) and e['yaw_err_rad'] == pytest.approx(0., abs=1e-9)


class _Loc:
    def __init__(self):
        self.n, self.rng, self.params = 4000, np.random.default_rng(3), {'motion': {'scale_std': .05}}
        self.initialized, self.last_tag_t, self.t = False, None, 0.

    def predict_to(self, t):
        self.t = t

    def _map_logprior(self, px):
        return np.zeros(len(px))

    def estimate(self):
        return {'x': float(self.px[:, 0].mean()), 'y': float(self.px[:, 1].mean()),
                'yaw': float(self.px[:, 2].mean()), 'std_xy_m': float(np.sqrt(self.px[:, 0].var() + self.px[:, 1].var())),
                'std_yaw_rad': float(self.px[:, 2].std())}


def test_seeded_prior_matches_statement_and_sets_no_fix():
    loc = _Loc()
    prior = sp.gaussian_prior([.3, -.1, .2], .06, .05, 'test')
    est = sp.seed_gaussian_prior(loc, 1.25, prior)
    assert loc.initialized and loc.last_tag_t is None and loc.t == 1.25
    assert est['x'] == pytest.approx(.3, abs=.005) and est['y'] == pytest.approx(-.1, abs=.005)
    assert est['std_xy_m'] == pytest.approx(.06, rel=.05) and est['std_yaw_rad'] == pytest.approx(.05, rel=.05)
    with pytest.raises(ValueError):
        sp.seed_gaussian_prior(loc, 1., {**prior, 'is_fix': True})
    with pytest.raises(ValueError):
        sp.gaussian_prior([float('nan'), 0, 0], .1, .1, 'x')


def _fake_run(tmp_path, *, entered=('r1', 'r2')):
    run = tmp_path / 'v6-s999-v5h'
    (run / 'eval_only').mkdir(parents=True)
    ev = [{'event': 'pair_progress', 'robot_id': r, 'sim_s': 10. + i, 'detail': {'phase': 'align_start'}}
          for i, r in enumerate(entered)]
    (run / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in ev))
    corners = [[.7, .03, 0]] * 4 + [[1.3, .03, 0]] * 4
    rows = [{'t': t, 'states': {}, 'beam_xyz': [1., .05, 0.], 'beam_corners': corners,
             'robots': {'r1': [.28, 0., 0.], 'r2': [1.74, 0., math.pi], 'r3': [-.65, -2.25, 0.]}} for t in (10.95, 11.0, 11.05)]
    (run / 'eval_only/trace.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    rep = lambda x: {'xyyaw': [x, .001, 0.01], 'std_xy_m': .03, 'std_yaw_rad': .01}
    frames = {r: {'frames': [{'t': 10.9, 'frame_id': 5, 'commanded_servo': {'1': 2000}, 'report': rep(9.)},
                             {'t': 11.0, 'frame_id': 6, 'commanded_servo': {'1': 2000}, 'report': rep(.29)},
                             {'t': 11.1, 'frame_id': 7, 'commanded_servo': {'1': 2000}, 'report': rep(7.)}]}
              for r in ('r1', 'r2')}
    (run / 'robots.json').write_text(json.dumps(frames))
    sheet = sp.BASE_SETUP['coarse_order_sheet']
    (run / 'prereg.json').write_text(json.dumps({'runs': [{'id': 'v6-s999-v5h', 'coarse_order_sheet': sheet}]}))
    (run / 'manifest.json').write_text(json.dumps({'run_id': 'v6-s999-v5h', 'seed': 999}))
    return run


def test_e2e_checkpoint_uses_own_recorded_report_as_prior(tmp_path):
    run = _fake_run(tmp_path)
    [case] = sp.e2e_checkpoint(run, 'align')
    assert case['e2e_source']['entry_sim_s'] == 11.
    assert case['placement_xyyaw']['r1'] == [.28, 0., 0.]
    prior = case['prior']['r1']
    assert prior['mean_xyyaw'] == [.29, .001, .01] and prior['is_fix'] is False
    assert 'own recorded PoseReport' in prior['source'] and 'frame 6' in prior['source']
    assert case['beam_xyyaw'][2] == pytest.approx(0.)
    assert len(case['e2e_source']['trace_sha256']) == 64


def test_e2e_checkpoint_unavailable_when_one_robot_never_entered(tmp_path):
    got = sp.e2e_checkpoint(_fake_run(tmp_path, entered=('r2',)), 'align')
    assert got['unavailable'] is True and "['r2']" in got['reason']


def _align_exit(x=0., y=0., yaw=0.):
    return {'sim_s': 1., 'gt': {'grip_errors': {'grip_x_err_m': x, 'grip_y_err_m': y, 'yaw_err_rad': yaw}}}


def test_evaluate_requires_controller_exit_and_gt_criteria():
    ok = sp.evaluate('align', {'exits': {'r1': _align_exit(), 'r2': _align_exit()}})
    assert ok['passed'] and ok['category'] == 'PASS'
    off = sp.evaluate('align', {'exits': {'r1': _align_exit(y=.02), 'r2': _align_exit()}})
    assert not off['passed'] and off['category'] == 'GT_CRITERIA:r1_grip_y'
    fail = sp.evaluate('align', {'exits': {'r1': _align_exit()},
                                 'first_failure': {'reason': 'ALIGN_RELOOK_NO_FIX'}})
    assert not fail['passed'] and fail['category'] == 'ALIGN_RELOOK_NO_FIX'
    budget = sp.evaluate('align', {'exits': {'r1': _align_exit()}})
    assert budget['category'] == 'STAGE_BUDGET_EXHAUSTED'
    entry = sp.evaluate('grasp_lift', {'exits': {}, 'entry_error': 'ADMISSION_SELF_UNCERTAIN'})
    assert entry['category'] == 'ENTRY:ADMISSION_SELF_UNCERTAIN'


def test_evaluate_grasp_lift_needs_both_jaws_and_height():
    gt = {'lift_m': .06, 'tilt_deg': 2., 'jaws': {'r1': [True, True], 'r2': [True, True]}}
    exits = {'r1': {'sim_s': 1.}, 'r2': {'sim_s': 2.}}
    assert sp.evaluate('grasp_lift', {'exits': exits, 'gt_at_exit': gt})['passed']
    one_jaw = {**gt, 'jaws': {'r1': [True, False], 'r2': [True, True]}}
    got = sp.evaluate('grasp_lift', {'exits': exits, 'gt_at_exit': one_jaw})
    assert not got['passed'] and 'both_jaws_both_robots' in got['category']


def test_summarize_counts_by_stage_source_and_failure():
    rows = [{'stage': 'align', 'source': 'teacher_grid', 'passed': True, 'category': 'PASS', 'wall_s': 10, 'stage_sim_s': 5},
            {'stage': 'align', 'source': 'e2e_checkpoint', 'passed': False, 'category': 'ALIGN_RELOOK_NO_FIX',
             'wall_s': 30, 'stage_sim_s': 20},
            {'stage': 'grasp_lift', 'source': 'teacher_grid', 'passed': False, 'category': 'X', 'wall_s': 7, 'stage_sim_s': 3}]
    s = sp.summarize(rows)
    assert s['labels'] == sp.LABELS
    assert s['stages']['align']['pass_rate'] == .5 and s['stages']['align']['failures'] == {'ALIGN_RELOOK_NO_FIX': 1}
    assert s['stages']['align']['by_source']['e2e_checkpoint'] == {'cases': 1, 'passed': 0}
    assert list(s['stages']) == ['align', 'grasp_lift']


def test_runner_refuses_physical_without_lock_or_outside_outputs(tmp_path):
    from scripts import run_pair_stage_probes as r
    with pytest.raises(SystemExit):
        r.main(['--stage', 'align', '--sources', 'teacher', '--limit', '1', '--execute',
                '--output', str(tmp_path / 'out')])
    assert not (tmp_path / 'out').exists()


def test_workflow_registered():
    rows = json.loads((ROOT / 'configs/simulation_workflows.json').read_text())['workflows']
    row = next(r for r in rows if r['id'] == 'pair-stage-probes')
    assert row['entry'] == 'scripts/run_pair_stage_probes.py' and (ROOT / row['docs']).is_file()
    assert row['runner'] == 'scripts.run_pair_stage_probes' and row['output_flag'] == '--output'
