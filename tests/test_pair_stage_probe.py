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


def test_plan_mode_policies_and_boundary_source(tmp_path):
    program = ('from scripts import run_pair_stage_probes as r; '
               'r.main(["--stage","align","grasp_lift","--output","/nonexistent/never","--sources","teacher","boundary",'
               '"--policies","v5h","b-only","a+b"])')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    # 3 policies x (19 align + 19 grasp_lift teacher + 23 grasp_lift boundary)
    assert json.loads(out.stdout)['cases'] == 3 * (19 + 19 + 23)


def test_policy_case_ids_are_distinct_and_v5h_ids_unchanged():
    v5h = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,))[0]
    ab = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,), policy='a+b')[0]
    assert v5h['case_id'] == 'align:teacher:nominal:s911' and v5h['pair_policy'] == 'v5h'
    assert ab['case_id'] == 'align@a+b:teacher:nominal:s911' and ab['pair_policy'] == 'a+b'
    assert ab['placement_xyyaw'] == v5h['placement_xyyaw'] and ab['prior'] == v5h['prior']
    with pytest.raises(ValueError, match='unknown pair policy'):
        sp.teacher_cases('align', policy='a-only')


def test_boundary_cases_place_true_grip_exactly_at_the_align_tolerance():
    cases = sp.boundary_cases(policy='a+b')
    assert len(cases) == 23 and len({c['case_id'] for c in cases}) == 23
    assert {c['source'] for c in cases} == {'tolerance_boundary'}
    geo = sp.stations(sp.BASE_SETUP['beam_xyyaw'])
    plan = sp.stations(sp.BASE_SETUP['coarse_order_sheet']['beam_xyyaw'])
    extremes = {tuple(round(abs(v), 6) for v in c['offsets']['r1']) for c in cases if c['cell'].startswith('corner')}
    assert extremes == {(sp.ALIGN_TOL['x_m'], sp.ALIGN_TOL['y_m'], sp.ALIGN_TOL['yaw_rad'])}
    for c in cases:
        for rid in sp.PARTICIPANTS:
            ex, ey, ea = c['offsets'][rid]
            e = sp.grip_errors(c['placement_xyyaw'][rid], geo['grip_xyz'][rid][:2], geo['station'][rid][2])
            assert e['grip_x_err_m'] == pytest.approx(ex, abs=1e-9)
            assert e['grip_y_err_m'] == pytest.approx(ey, abs=1e-9)
            assert e['yaw_err_rad'] == pytest.approx(-ea, abs=1e-9)
            # prior is the static sheet station, never the GT placement
            assert c['prior'][rid]['mean_xyyaw'] == pytest.approx(plan['station'][rid])
    with pytest.raises(ValueError):
        sp.boundary_cases('align')


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


def test_workflow_registration_row_is_pending_until_v6_contract_allows_it():
    """The catalog row is kept ready but NOT in configs/simulation_workflows.json: the REGISTERED v6
    prereg hashes that whole file (see workflow_registration_pending.json)."""
    pending = json.loads((ROOT / 'experiments/2026-09-28-pair-stage-probes/workflow_registration_pending.json').read_text())
    row = pending['catalog_row']
    assert pending['status'] == 'pending_registration' and row['id'] == 'pair-stage-probes'
    assert row['entry'] == 'scripts/run_pair_stage_probes.py' and (ROOT / row['entry']).is_file() and (ROOT / row['docs']).is_file()
    assert row['runner'] == 'scripts.run_pair_stage_probes' and row['output_flag'] == '--output'
    for key in ('id', 'version', 'runner', 'entry', 'output_flag', 'output_kind', 'required_inputs', 'side_effect'):
        assert key in row
    rows = json.loads((ROOT / 'configs/simulation_workflows.json').read_text())['workflows']
    assert 'pair-stage-probes' not in {r['id'] for r in rows}


def test_finish_result_root_cause_tie_break_and_out_of_stage_events(tmp_path):
    from scripts import run_pair_stage_probes as r
    case = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,))[0]
    ev = lambda rid, t, reason: {'event': 'job_failed', 'robot_id': rid, 'sim_s': t, 'detail': {'reason': reason}}
    result = {'wall_s': 1., 'exits': {}, 'entry': {'r1': {'sim_s': 2.}},
              'event_log': [ev('r1', 5., 'PARTNER_ABORT'), ev('r2', 5., 'PAIR_COLLISION_GUARD'),
                            ev('r1', 9., 'EPISODE_END:STUDY_LAYER_DONE')]}
    row = r.finish_result(case, result, tmp_path)
    assert row['category'] == 'PAIR_COLLISION_GUARD' and row['first_failure']['robot_id'] == 'r2'
    # a robot's failure AFTER its own stage exit is outside the stage
    exits = {q: {'sim_s': 4., 'gt': {'grip_errors': {'grip_x_err_m': 0., 'grip_y_err_m': 0., 'yaw_err_rad': 0.}}}
             for q in sp.PARTICIPANTS}
    after = {'wall_s': 1., 'exits': exits, 'entry': {}, 'event_log': [ev('r1', 5., 'PARTNER_ABORT_AFTER_OWN_EXIT')]}
    row = r.finish_result(case, after, tmp_path)
    assert row['passed'] and row['category'] == 'PASS'
    assert json.loads((tmp_path / 'result.json').read_text())['row']['labels'] == sp.LABELS


def test_finish_result_records_policy_relooks_and_remaining_distance(tmp_path):
    from scripts import run_pair_stage_probes as r
    case = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,), policy='b-only')[0]
    err = {'grip_x_err_m': .05, 'grip_y_err_m': -.01, 'yaw_err_rad': .02, 'grip_base_m': [.212, -.01]}
    log = [{'t': 3., 'robot_id': 'r1', 'event': 'begin_observation', 'localizer_object_replaced': False},
           {'t': 4., 'robot_id': 'r2', 'event': 'begin_relocalization', 'localizer_object_replaced': True},
           {'t': 4., 'robot_id': 'r2', 'event': 'localizer_object_replaced'}]
    result = {'wall_s': 1., 'exits': {}, 'entry': {}, 'event_log': [], 'localizer_log': log,
              'localizer_stats': {'r1': {'resets': 0}, 'r2': {'resets': 1}},
              'gt_at_stop': {'t': 9.5, 'grip_errors_all': {'r1': err, 'r2': err}}}
    row = r.finish_result(case, result, tmp_path)
    assert row['pair_policy'] == 'b-only' and row['stop_sim_s'] == 9.5
    assert row['relook_calls'] == {'r1': ['begin_observation'], 'r2': ['begin_relocalization']}
    assert row['localizer_replaced'] == {'r1': 0, 'r2': 1}
    assert row['localizer_resets_stat'] == {'r1': 0, 'r2': 1}
    assert row['remaining_at_stop']['r1'] == {'grip_x_err_m': .05, 'grip_y_err_m': -.01, 'yaw_err_rad': .02}


def test_summary_splits_by_policy():
    rows = [{'stage': 'align', 'source': 'teacher_grid', 'pair_policy': p, 'passed': ok, 'category': c}
            for p, ok, c in (('v5h', False, 'X'), ('a+b', True, 'PASS'), ('a+b', False, 'Y'))]
    s = sp.summarize(rows)['stages']['align']
    assert s['by_policy']['a+b'] == {'cases': 2, 'passed': 1, 'by_source': {'teacher_grid': {'cases': 2, 'passed': 1}},
                                     'failures': {'Y': 1}}
    assert s['by_policy']['v5h']['failures'] == {'X': 1}


def test_staged_global_anchor_is_the_stated_prior_or_own_recorded_fix(tmp_path):
    c = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,), policy='a+b')[0]
    a = sp.staged_global_anchor(c)
    for rid in sp.PARTICIPANTS:
        assert a[rid]['xyyaw'] == c['prior'][rid]['mean_xyyaw'] and a[rid]['age_s'] == 0.
        assert a[rid]['std_xy_m'] == sp.PRIOR_STD_XY_M and 'not GT' in a[rid]['source']
    e = {**c, 'source': 'e2e_checkpoint', 'e2e_source': {'own_fix_age_s': {'r1': 2.5, 'r2': 31.}}}
    a = sp.staged_global_anchor(e)
    assert a['r1']['age_s'] == 2.5 and a['r2'] is None


def test_prior_std_variant_is_tagged_and_default_unchanged():
    base = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,))[0]
    e2e = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,), prior_std='e2e')[0]
    assert base['case_id'] == 'align:teacher:nominal:s911' and base['prior']['r1']['std_xy_m'] == sp.PRIOR_STD_XY_M
    assert e2e['case_id'] == 'align:teacher:nominal:s911:pE2E'
    assert e2e['prior']['r1']['std_xy_m'] == .03 and e2e['prior']['r1']['std_yaw_rad'] == .012
    assert e2e['prior']['r1']['mean_xyyaw'] == base['prior']['r1']['mean_xyyaw']
    bd = sp.boundary_cases(prior_std='e2e')[0]
    assert bd['case_id'].endswith(':pE2E') and bd['prior']['r2']['std_xy_m'] == .03


def test_diag_patch_is_labelled_and_off_by_default():
    base = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,), policy='b-only')
    assert 'diag_patch' not in base[0] and sp.apply_diag_patch(base, None) == base
    d = sp.apply_diag_patch(base, 'fix_age_round')[0]
    assert d['case_id'] == 'align@b-only:teacher:nominal:s911:diag-fix_age_round' and d['diag_patch'] == 'fix_age_round'
    with pytest.raises(ValueError):
        sp.apply_diag_patch(base, 'nope')


def test_diag_fix_age_round_matches_base_rounding_in_a_subprocess():
    program = ('import types, numpy as np\n'
               'from scripts import run_pair_stage_probes as r\n'
               'from harness.owncam_recovery_v6 import RecoveryLocalizer\n'
               'from harness.owncam_localizer import OwnCamLocalizer\n'
               'OwnCamLocalizer.estimate = lambda self: {}\n'
               'loc = RecoveryLocalizer.__new__(RecoveryLocalizer)\n'
               'loc.t, loc.last_informative_t = 4.4 - 5e-13, 4.4\n'
               'assert RecoveryLocalizer.estimate(loc)["fix_age_s"] < 0\n'
               'r.install_diag_patch("fix_age_round")\n'
               'e = RecoveryLocalizer.estimate(loc)\n'
               'assert e["fix_age_s"] >= 0 and e["since_tag_s"] == e["fix_age_s"] and e["last_fix_t"] == 4.4, e\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


# ------------------------------------------------------------------ 0.4.0: route legs, cause codes, diag patches
def _carry(**kw):
    return sp.teacher_cases('carry', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c', prior_std='e2e', **kw)[0]


def test_route_legs_leg0_is_the_030_case_and_other_legs_translate_beam_and_prior():
    legacy, leg0, leg3 = _carry(), _carry(leg=0), _carry(leg=3)
    assert legacy['case_id'] == leg0['case_id'] == 'carry@b-v6c:teacher:nominal:s911:pE2E'   # ids of 0.3.0 unchanged
    same = lambda c: {k: v for k, v in c.items() if k not in ('leg', 'route', 'route_note')}
    assert same(leg0) == same(legacy)
    assert leg3['case_id'] == leg0['case_id'] + ':L3' and leg3['leg'] == 3
    dx, dy = (leg3['route'][3][i] - leg3['route'][0][i] for i in (0, 1))
    for rid in sp.PARTICIPANTS:
        assert leg3['placement_xyyaw'][rid][:2] == pytest.approx([leg0['placement_xyyaw'][rid][0] + dx,
                                                                  leg0['placement_xyyaw'][rid][1] + dy])
        assert leg3['prior'][rid]['mean_xyyaw'][:2] == pytest.approx([leg0['prior'][rid]['mean_xyyaw'][0] + dx,
                                                                      leg0['prior'][rid]['mean_xyyaw'][1] + dy])
        assert leg3['prior'][rid]['std_xy_m'] == leg0['prior'][rid]['std_xy_m']
    # the true-beam vs static-sheet offset of BASE_SETUP is kept on every leg (prior is the plan, not the placement)
    assert (leg3['beam_xyyaw'][1] - leg3['coarse_order_sheet']['beam_xyyaw'][1]
            == pytest.approx(leg0['beam_xyyaw'][1] - leg0['coarse_order_sheet']['beam_xyyaw'][1]))


def test_route_is_the_controller_static_plan_and_matches_the_runner_map():
    from harness.zone_pair_executor import make_plan
    from scripts import run_pair_stage_probes as r
    assert r.MAP_ID == sp.MAP_ID
    route = _carry()['route']
    assert route == sp.plan_route(sp.BASE_SETUP['coarse_order_sheet'])
    assert len(route) == 9 and route[0] == [1.0, .05] and route[-1] == [4.6, -2.1]
    static_map = json.loads((ROOT / 'maps/zones' / f'{sp.MAP_ID}.json').read_text())
    assert make_plan(static_map, sp.BASE_SETUP['coarse_order_sheet'], 'B')['route'] == route


def test_leg_index_and_setdown_end_case():
    assert sp.leg_index('carry', None, 9) == 0 and sp.leg_index('carry', 7, 9) == 7
    for bad in (8, -1):
        with pytest.raises(ValueError):
            sp.leg_index('carry', bad, 9)
    assert sp.leg_index('setdown', None, 9) is None and sp.leg_index('setdown', 'end', 9) == 8
    with pytest.raises(ValueError):
        sp.leg_index('setdown', 3, 9)
    end = sp.teacher_cases('setdown', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c', prior_std='e2e', leg='end')[0]
    legacy = sp.teacher_cases('setdown', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c', prior_std='e2e')[0]
    assert end['case_id'] == legacy['case_id'] + ':Lend' and end['beam_xyyaw'][:2] == [4.6, -2.1]
    assert 'leg' not in legacy or legacy['leg'] is None
    assert len(sp.teacher_cases('carry', policy='b-v6c', prior_std='e2e', leg=6)) == 19


def test_carry_end_error_check_only_when_the_runner_measured_it():
    def exit_(gt):
        return {'sim_s': 9., 'gt': gt}
    gt = {'lift_m': .06, 'tilt_deg': 0., 'jaws': {'r1': [True, True], 'r2': [True, True]}}
    rec = {'exits': {r: exit_(gt) for r in sp.PARTICIPANTS}, 'gt_at_exit': gt, 'beam_travel_m': .55, 'planned_leg_m': .55,
           'min_lift_after_first_lift_m': .058, 'max_tilt_deg': 1.}
    base = sp.evaluate('carry', dict(rec))
    assert 'end_error' not in base['checks']                               # 0.3.0 records are judged as before
    good = sp.evaluate('carry', {**rec, 'end_error_m': .03, 'cross_track_m': .01, 'yaw_drift_deg': 1.})
    assert good['checks']['end_error'] and good['metrics']['end_error_m'] == .03
    bad = sp.evaluate('carry', {**rec, 'end_error_m': .12})
    assert not bad['checks']['end_error'] and not bad['passed']


def _ev(**checks):
    ok = all(checks.values()) if checks else True
    return {'passed': ok, 'category': 'PASS' if ok else 'GT_CRITERIA', 'checks': checks}


def test_classify_cause_codes_and_pose_uncertainty_sub():
    own = {'r1': {'std_xy_m': .03, 'std_yaw_rad': .0728}}
    fail = {'first_failure': {'robot_id': 'r1', 'sim_s': 8.7, 'reason': 'POSE_UNCERTAIN_PROGRESS'}}
    c = sp.classify_cause('carry', {'passed': False, 'category': 'POSE_UNCERTAIN_PROGRESS', 'checks': {}}, fail,
                          {'own_at_failure': own, 'contacts': {'box': 2}})
    assert c['code'] == 'SELF_POSE_UNCERTAIN' and c['sub'] == 'yaw' and c['contacts_in_stage'] == {}
    assert sp.pose_uncertainty_sub({'std_xy_m': .09, 'std_yaw_rad': .09}) == 'yaw+xy'
    assert sp.pose_uncertainty_sub({'std_xy_m': .03, 'std_yaw_rad': .02}) == 'gate_not_ok_dwell_or_hysteresis'
    assert sp.pose_uncertainty_sub(None) == 'no_report'
    assert sp.classify_cause('carry', {'passed': True, 'category': 'PASS', 'checks': {}}, {})['code'] == 'PASS'
    # no controller failure: the first GT check that failed names the cause; contacts are reported, not assumed
    lift = sp.classify_cause('carry', _ev(controller_exit_both=True, lift=False, end_error=False), {},
                             {'contacts': {'wall': 3, 'box': 9}})
    assert lift['code'] == 'LOAD_DROP' and lift['contacts_in_stage'] == {'wall': 3}
    assert sp.classify_cause('carry', _ev(controller_exit_both=True, end_error=False), {})['code'] == 'MOTION_ERROR'
    assert sp.classify_cause('setdown', _ev(controller_exit_both=True, released=False), {})['code'] == 'NOT_RELEASED'
    assert sp.classify_cause('carry', _ev(controller_exit_both=False), {})['code'] == 'STAGE_TIMEOUT_NO_EXIT'
    partner = {'first_failure': {'robot_id': 'r2', 'sim_s': 4., 'reason': 'PARTNER_ABORT_X'}}
    assert sp.classify_cause('carry', {'passed': False, 'category': 'PARTNER_ABORT_X', 'checks': {}}, partner)['code'] \
        == 'PARTNER_ABORT'
    assert sp.classify_cause('carry', {'passed': False, 'category': 'HOST_ERROR:x', 'checks': {}}, {})['code'] == 'HOST_ERROR'
    assert set(sp.FAILURE_TO_CAUSE.values()) <= set(sp.CAUSES) and set(sp.CHECK_TO_CAUSE.values()) <= set(sp.CAUSES)


def test_diag_patches_040_are_labelled_and_components_exist():
    for name in ('loaded_yaw_gate_wide', 'pf_rest_no_abs_noise', 'rest_noise_off_and_gate_wide'):
        assert name in sp.DIAG_PATCHES
        d = sp.apply_diag_patch([_carry()], name)[0]
        assert d['case_id'].endswith(':diag-' + name) and d['diag_patch'] == name
    assert set(sp.DIAG_COMPONENTS['rest_noise_off_and_gate_wide']) <= set(sp.DIAG_PATCHES)
    assert sp.LOADED_YAW_GATE_DIAG_DEG == (12., 10.)


def test_diag_loaded_yaw_gate_and_rest_noise_patches_in_a_subprocess():
    program = ('import math, numpy as np\n'
               'from scripts import run_pair_stage_probes as r\n'
               'from harness import zone_own_guards as g, zone_own_driver as d, zone_own_sweep as s, zone_pair_guards as p\n'
               'from harness.owncam_localizer import OwnCamLocalizer\n'
               'assert g.GATE_LOADED.high_yaw_rad == math.radians(3.)\n'
               'reg = OwnCamLocalizer._motion_params\n'
               'loc = OwnCamLocalizer.__new__(OwnCamLocalizer)\n'
               'loc.motion_profile, loc.params = None, {"motion_loaded": {"noise_abs": [.01, .004, .098]}, "motion": {"noise_abs": [1, 1, 1]}}\n'
               'loc.load = type("L", (), {"loaded": True})()\n'
               'loc.vel, loc.t, loc.cmd_expires = np.zeros(3), 5., -1.\n'
               'assert reg(loc)["noise_abs"] == [.01, .004, .098]\n'
               'r.install_diag_patch("rest_noise_off_and_gate_wide")\n'
               'assert loc._motion_params()["noise_abs"] == [0., 0., 0.]                    # at rest\n'
               'loc.cmd_expires = 6.\n'
               'assert loc._motion_params()["noise_abs"] == [.01, .004, .098]               # live command\n'
               'loc.cmd_expires, loc.vel = -1., np.array([.1, 0., 0.])\n'
               'assert loc._motion_params()["noise_abs"] == [.01, .004, .098]               # still moving\n'
               'for m in (g, d, s, p):\n'
               '    assert m.GATE_LOADED.high_yaw_rad == math.radians(12.) and m.GATE_LOADED.low_yaw_rad == math.radians(10.)\n'
               '    assert m.GATE_LOADED.high_xy_m == .07 and m.GATE_LOADED.enter_dwell_s == .6\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_finish_result_carry_leg_metrics_cause_and_command_counts(tmp_path):
    from scripts import run_pair_stage_probes as r
    case = _carry(leg=3)
    p1 = case['route'][4]                                                     # leg 3 ends at route[4]
    gt0 = {'beam_xyz': [3.2, .05, .06], 'beam_yaw': 0., 'lift_m': .06}
    gt1 = {'beam_xyz': [p1[0] + .02, p1[1] - .03, .06], 'beam_yaw': math.radians(2.), 'lift_m': .059, 'tilt_deg': 0.,
           'jaws': {q: [True, True] for q in sp.PARTICIPANTS}}
    exits = {q: {'sim_s': 30., 'gt': gt1} for q in sp.PARTICIPANTS}
    (tmp_path / 'commands.json').write_text(json.dumps({'r1': [{'kind': 'mecanum', 't': 12.}, {'kind': 'mecanum', 't': 13.},
                                                                 {'kind': 'look', 't': 13.}, {'kind': 'mecanum', 't': 1.}],
                                                        'r2': []}))
    result = {'wall_s': 1., 'exits': exits, 'entry': {'r1': {'sim_s': 10., 'own_report': {'std_yaw_rad': .03}}},
              'event_log': [], 'gt_at_entry': gt0, 'submit_t': 10., 'termination': {'sim_s': 30.},
              'loadavg_case_start': [20., 20., 20.], 'loadavg_case_end': [21., 21., 21.],
              'max_tilt_deg': 1., 'min_lift_after_first_lift_m': .058}
    row = r.finish_result(case, result, tmp_path)
    m = row['metrics']
    assert row['leg'] == 3 and m['end_error_m'] == pytest.approx(math.hypot(.02, .03))
    assert m['cross_track_m'] == pytest.approx(.02) and m['yaw_drift_deg'] == pytest.approx(2.)   # leg 3 is along -y
    assert row['commands_after_submit']['r1'] == {'mecanum': 2, 'look': 1} and row['base_motion_commands']['r1'] == 2
    assert row['loadavg_case'] == [[20., 20., 20.], [21., 21., 21.]] and row['cause'] in sp.CAUSES
    assert row['passed'] and row['cause'] == 'PASS'


def test_staging_bypass_only_on_setdown_at_the_destination_and_new_image_cause():
    end = sp.teacher_cases('setdown', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c', prior_std='e2e', leg='end')[0]
    assert end['staging_bypass'] == ['admission_image_valid'] and 'image_valid' in end['staging_bypass_note']
    legacy = sp.teacher_cases('setdown', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c', prior_std='e2e')[0]
    assert 'staging_bypass' not in legacy
    for leg in (0, 3):
        assert 'staging_bypass' not in sp.teacher_cases('carry', nominal_seeds=(911,), subset={'nominal'}, policy='b-v6c',
                                                        prior_std='e2e', leg=leg)[0]
    fail = {'first_failure': {'robot_id': 'r1', 'sim_s': 3., 'reason': 'INVALID_OWN_IMAGE'}}
    c = sp.classify_cause('setdown', {'passed': False, 'category': 'INVALID_OWN_IMAGE', 'checks': {}}, fail)
    assert c['code'] == 'OWN_IMAGE_INVALID' and 'OWN_IMAGE_INVALID' in sp.CAUSES
    e = sp.classify_cause('setdown', {'passed': False, 'category': 'ENTRY:ADMISSION_SELF_INVALID_IMAGE', 'checks': {}}, {})
    assert e['code'] == 'ENTRY_ERROR' and e['sub'] == 'ADMISSION_SELF_INVALID_IMAGE'


def test_staging_bypass_forces_only_the_admission_predicate_and_records_the_real_verdict():
    program = ('from scripts import run_pair_stage_probes as r\n'
               'import harness.zone_pair_admission as adm, harness.zone_pair_vision as vis\n'
               'real = vis.valid_frame\n'
               'seen = []\n'
               'adm.readiness_snapshot = lambda ex, now, *a, **k: seen.append(vis.valid_frame(None, "r1", now)) or {"state": "READY"}\n'
               'ex = type("E", (), {"robot_id": "r1", "last_obs": None})()\n'
               'vis.valid_frame = lambda obs, rid, now: False                                 # the real verdict: invalid\n'
               'verdicts = {}\n'
               'r.install_staging_bypass(["admission_image_valid"], verdicts)\n'
               'assert adm.readiness_snapshot(ex, 1.)["state"] == "READY" and seen == [True]  # forced during the call\n'
               'assert verdicts == {"r1": [False]} and vis.valid_frame(None, "r1", 2.) is False  # restored afterwards\n'
               'try:\n'
               '    r.install_staging_bypass(["nope"], {})\n'
               '    raise SystemExit(1)\n'
               'except ValueError:\n'
               '    pass\n'
               'r.install_staging_bypass(None, {})\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_staging_ik_envelope_is_its_own_cause_and_leaves_the_staged_denominator():
    msg = 'target radius is outside the calibrated 14.5..18.0 cm grasp envelope'
    ev = {'passed': False, 'category': 'HOST_ERROR', 'checks': {}}
    c = sp.classify_cause('carry', ev, {'first_failure': {'robot_id': None, 'sim_s': None, 'reason': 'HOST_ERROR'}},
                          {'host_error_message': msg})
    assert c['code'] == 'STAGING_IK_ENVELOPE' and 'STAGING_IK_ENVELOPE' in sp.CAUSES
    assert sp.classify_cause('carry', ev, {}, {'host_error_message': 'MuJoCo exploded'})['code'] == 'HOST_ERROR'
    assert sp.classify_cause('carry', ev, {})['code'] == 'HOST_ERROR'
    rows = [{'stage': 'carry', 'source': 'teacher_grid', 'passed': False, 'category': 'HOST_ERROR', 'cause': 'STAGING_IK_ENVELOPE',
             'wall_s': 8, 'stage_sim_s': None},
            {'stage': 'carry', 'source': 'teacher_grid', 'passed': True, 'category': 'PASS', 'cause': 'PASS', 'wall_s': 60,
             'stage_sim_s': 20.},
            {'stage': 'carry', 'source': 'teacher_grid', 'passed': False, 'category': 'POSE_UNCERTAIN', 'cause': 'SELF_POSE_UNCERTAIN',
             'wall_s': 60, 'stage_sim_s': 3.}]
    st = sp.summarize(rows)['stages']['carry']
    assert (st['cases'], st['passed'], st['staging_infeasible'], st['staged_cases']) == (3, 1, 1, 2)
    assert st['pass_rate'] == round(1 / 3, 4) and st['staged_pass_rate'] == .5


def test_diag_image_valid_off_forces_every_check_and_keeps_the_real_verdict_in_a_subprocess():
    assert 'image_valid_off' in sp.DIAG_PATCHES
    d = sp.apply_diag_patch([_carry()], 'image_valid_off')[0]
    assert d['case_id'].endswith(':diag-image_valid_off') and d['diag_patch'] == 'image_valid_off'
    program = ('from scripts import run_pair_stage_probes as r\n'
               'import harness.zone_pair_admission as adm, harness.zone_pair_grasp as gr, harness.zone_pair_vision as vis\n'
               'real = vis.valid_frame\n'
               'vis.valid_frame = lambda obs, rid, now: rid == "r2"                         # r1 invalid, r2 valid\n'
               'r.IMAGE_VALID_REAL.clear()\n'
               'r.install_diag_patch("image_valid_off")\n'
               'assert vis.valid_frame(None, "r1", 1.) is True and gr.valid_frame(None, "r1", 1.) is True\n'
               'assert vis.valid_frame(None, "r2", 1.) is True\n'
               'assert r.IMAGE_VALID_REAL == {"r1": [0, 2], "r2": [1, 0]}                    # real verdicts counted\n'
               'seen = []\n'
               'adm.readiness_snapshot = lambda ex, now, *a, **k: seen.append(vis.valid_frame(None, "r1", now)) or {"state": "READY"}\n'
               'ex = type("E", (), {"robot_id": "r1", "last_obs": None})()\n'
               'verdicts = {}\n'
               'r.install_staging_bypass(["admission_image_valid"], verdicts)\n'
               'adm.readiness_snapshot(ex, 2.)\n'
               'assert seen == [True] and verdicts == {"r1": [False]}                       # real verdict, not the forced one\n'
               'assert vis.valid_frame.__wrapped__("x", "r1", 3.) is False\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_clamp_estimate_sigma_is_pure_and_leaves_uninitialised_or_non_finite_alone():
    est = {'initialized': True, 'x': 1., 'y': 2., 'yaw': .1, 'std_xy_m': .09, 'std_yaw_rad': .02, 'cov': [[1]]}
    out = sp.clamp_estimate_sigma(est, .03, .012)
    assert (out['std_xy_m'], out['std_yaw_rad']) == (.03, .012) and out['x'] == 1. and out['cov'] == [[1]]
    assert est['std_xy_m'] == .09                                                      # input untouched
    small = sp.clamp_estimate_sigma({'initialized': True, 'std_xy_m': .01, 'std_yaw_rad': .005}, .03, .012)
    assert (small['std_xy_m'], small['std_yaw_rad']) == (.01, .005)                    # never raised
    bad = {'initialized': True, 'std_xy_m': float('inf'), 'std_yaw_rad': None}
    assert sp.clamp_estimate_sigma(bad, .03, .012) == bad
    assert sp.clamp_estimate_sigma({'initialized': False}, .03, .012) == {'initialized': False}


def test_diag_sigma_held_at_prior_caps_the_reported_sigma_in_a_subprocess():
    assert 'sigma_held_at_prior' in sp.DIAG_PATCHES
    d = sp.apply_diag_patch([_carry()], 'sigma_held_at_prior')[0]
    assert d['case_id'].endswith(':diag-sigma_held_at_prior') and d['diag_patch'] == 'sigma_held_at_prior'
    program = ('from scripts import run_pair_stage_probes as r\n'
               'from harness.owncam_localizer import OwnCamLocalizer as L\n'
               'from harness.owncam_recovery_v6 import RecoveryLocalizer as R\n'
               'L.estimate = lambda self: {"initialized": True, "x": 1., "std_xy_m": .2, "std_yaw_rad": .3}\n'
               'r.install_diag_patch("sigma_held_at_prior")\n'
               'e = L.estimate(object())\n'
               'assert (e["std_xy_m"], e["std_yaw_rad"], e["x"]) == (.03, .012, 1.), e\n'
               'assert issubclass(R, L) and R.estimate is not L.estimate      # subclass keeps super().estimate()\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_diag_carry_all_three_is_the_composite_of_the_three_single_patches():
    assert sp.DIAG_COMPONENTS['carry_all_three'] == ('sigma_held_at_prior', 'carry_lateral_scale_measured', 'image_valid_off')
    assert all(part in sp.DIAG_PATCHES for part in sp.DIAG_COMPONENTS['carry_all_three']) and 'carry_all_three' in sp.DIAG_PATCHES
    d = sp.apply_diag_patch([_carry()], 'carry_all_three')[0]
    assert d['case_id'].endswith(':diag-carry_all_three') and d['diag_patch'] == 'carry_all_three'
    assert sp.CARRY_LATERAL_SCALE_DIAG == 0.806 and abs(0.697 * 0.829084 / 0.716667 - 0.806) < 1e-3


def test_diag_carry_lateral_scale_measured_changes_only_the_lateral_scale_in_a_subprocess():
    program = ('from scripts import run_pair_stage_probes as r\n'
               'from scripts import study_owncam_pair_beam as s\n'
               'before = dict(s.CARRY_ODOM_SCALE)\n'
               'r.install_diag_patch("carry_lateral_scale_measured")\n'
               'assert s.CARRY_ODOM_SCALE == {"axial": before["axial"], "lateral": .806}, s.CARRY_ODOM_SCALE\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_diag_setdown_sigma_tiny_image_off_is_the_composite_and_caps_sigma_at_the_floor_in_a_subprocess():
    assert sp.DIAG_COMPONENTS['setdown_sigma_tiny_image_off'] == ('sigma_held_tiny', 'image_valid_off')
    assert all(part in sp.DIAG_PATCHES for part in sp.DIAG_COMPONENTS['setdown_sigma_tiny_image_off'])
    assert 'setdown_sigma_tiny_image_off' in sp.DIAG_PATCHES
    d = sp.apply_diag_patch([_carry()], 'setdown_sigma_tiny_image_off')[0]
    assert d['case_id'].endswith(':diag-setdown_sigma_tiny_image_off') and d['diag_patch'] == 'setdown_sigma_tiny_image_off'
    assert sp.SIGMA_TINY_DIAG == {'std_xy_m': .001, 'std_yaw_rad': .0005}
    program = ('from scripts import run_pair_stage_probes as r\n'
               'from harness.owncam_localizer import OwnCamLocalizer as L\n'
               'L.estimate = lambda self: {"initialized": True, "x": 1., "std_xy_m": .2, "std_yaw_rad": .3}\n'
               'r.install_diag_patch("sigma_held_tiny")\n'
               'e = L.estimate(object())\n'
               'assert (e["std_xy_m"], e["std_yaw_rad"], e["x"]) == (.001, .0005, 1.), e\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_probe_view_name_collision_between_raws_keeps_both_views():
    import importlib.util
    spec = importlib.util.spec_from_file_location('views', ROOT / 'scripts/build_pair_stage_probe_views.py')
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    first, again = Path('/x/pair-stage-probes-aaaa-carryL0'), Path('/x/pair-stage-probes-bbbb-postBaseL0')
    assert views.unique_name('C-ca-t-nominal-s911-pE-L0', [], first) == 'C-ca-t-nominal-s911-pE-L0'
    assert views.unique_name('C-ca-t-nominal-s911-pE-L0', ['C-ca-t-nominal-s911-pE-L0'], again) == \
        'C-ca-t-nominal-s911-pE-L0-postBaseL0'
