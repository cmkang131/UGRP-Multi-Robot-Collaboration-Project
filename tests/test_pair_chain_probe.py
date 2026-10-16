"""Chain probe (opt-in stage ``chain``): pure logic, no MuJoCo. Stage probe, not E2E success.

Covers: chain plan generation, state carry-over across legs (one staging, pass-through recorder, no re-staging), the leg-by-leg
accumulation metrics and the verdict / first-failure attribution, and golden checks that the existing single-leg stage outputs
are byte-unchanged.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import pair_chain_probe as pcp
from harness import pair_stage_probe as sp

ROOT = Path(__file__).resolve().parents[1]
ROUTE = sp.plan_route(sp.BASE_SETUP['coarse_order_sheet'])
JAWS = {'r1': [True, True], 'r2': [True, True]}


# ------------------------------------------------------------------ synthetic records
def gt(beam_xy, yaw=0., lift=.10, tilt=1., jaws=JAWS, robots=None):
    return {'beam_xyz': [beam_xy[0], beam_xy[1], lift], 'beam_yaw': yaw, 'tilt_deg': tilt, 'lift_m': lift, 'jaws': jaws,
            'robots': robots or {'r1': [beam_xy[0] - .3, beam_xy[1], 0.], 'r2': [beam_xy[0] + .3, beam_xy[1], math.pi]}}


def own(std_xy=.03, std_yaw=.012, xyyaw=None, age=4.5):
    return {'t': 0., 'xyyaw': xyyaw or [0., 0., 0.], 'std_xy_m': std_xy, 'std_yaw_rad': std_yaw, 'fix_age_s': age,
            'fix_source': 'tags_temporary'}


def make_raw(ends, *, starts=None, sigma=lambda k: (.03, .012), yaw_of=lambda k: 0., dt=70.):
    """Raw recorders for both robots. ``ends[k]`` = GT beam xy at the end of leg k (only legs that were reached)."""
    raw = {}
    for rid in ('r1', 'r2'):
        leg_start, leg_end = {}, {}
        prev = [ROUTE[0][0], ROUTE[0][1]]
        for k, e in enumerate(ends):
            s_xy = prev if starts is None else starts[k]
            sx, sy = sigma(k)
            t0 = k * dt
            robots = {'r1': [s_xy[0] - .3, s_xy[1], 0.], 'r2': [s_xy[0] + .3, s_xy[1], math.pi]}
            leg_start[k] = {'sim_s': t0 + (.1 if rid == 'r2' else 0.), 'own': own(sx, sy),
                            'gt': gt(s_xy, yaw_of(k - 1) if k else 0., robots=robots)}
            erobots = {'r1': [e[0] - .3, e[1], 0.], 'r2': [e[0] + .3, e[1], math.pi]}
            leg_end[k] = {'sim_s': t0 + 30. + (.2 if rid == 'r2' else 0.), 'own': own(sx * 1.5, sy * 1.5, xyyaw=list(erobots[rid])),
                          'gt': gt(e, yaw_of(k), robots=erobots)}
            prev = e
        raw[rid] = {'timeline': [[0., 0, 'wait_carry'], [1., 0, 'carry'], [30., 0, 'wait_lower'], [40., 0, 'lower'],
                                 [45., 0, 'cp_open'], [50., 1, 'pregrasp_look'], [65., 1, 'wait_carry']],
                    'leg_start': leg_start, 'leg_end': leg_end, 'done': None, 'ticks': 100}
    return raw


def perfect_ends():
    return [list(p) for p in ROUTE[1:]]


def case_for_chain():
    return sp.teacher_cases('chain', subset={'nominal'}, nominal_seeds=(911,), prior_std='e2e')[0]


# ------------------------------------------------------------------ chain plan
def test_chain_plan_is_one_teacher_staging_on_the_whole_route():
    cases = sp.teacher_cases('chain')
    assert len(cases) == 19 and len({c['case_id'] for c in cases}) == 19
    c = case_for_chain()
    assert c['case_id'] == 'chain:teacher:nominal:s911:pE2E'
    assert c['stage'] == 'chain' and c['leg'] is None and c['teacher_held'] is True
    assert len(c['route']) == 9 and c['route'] == ROUTE
    assert c['beam_xyyaw'] == sp.BASE_SETUP['beam_xyyaw']     # staged at route point 0 (leg 0), the carry-stage L0 case
    assert 'ONE teacher staging' in c['route_note'] and 'legs 0..7' in c['route_note']
    # same placement / prior as the carry stage leg 0 (only the stage differs)
    carry0 = sp.teacher_cases('carry', subset={'nominal'}, nominal_seeds=(911,), prior_std='e2e', leg=0)[0]
    assert c['placement_xyyaw'] == carry0['placement_xyyaw'] and c['prior'] == carry0['prior']
    assert sp.teacher_cases('chain', subset={'nominal'}, nominal_seeds=(911,), policy='b-v6d')[0]['case_id'] == 'chain@b-v6d:teacher:nominal:s911'


def test_chain_stage_has_no_exit_hook_so_nothing_can_restage_or_stop_between_legs():
    spec = sp.STAGES['chain']
    assert spec['implemented'] and spec['exit_hook'] is None and spec['exit_state'] is None
    assert spec['entry'] == 'wait_carry' and spec['final_states'] == ('done',) and spec['order'] == 6
    with pytest.raises(ValueError, match='every leg itself'):
        sp.teacher_cases('chain', leg=3)


def test_chain_legs_of_the_dev_route():
    legs = pcp.legs_of(ROUTE)
    assert [l['axis'] for l in legs] == ['axial'] * 3 + ['lateral'] * 3 + ['axial'] * 2
    assert [round(l['length_m'], 4) for l in legs] == [.55, .85, .8, .7167, .7167, .7167, .7, .7]


def test_plan_mode_runner_chain_needs_no_simulator_and_marks_e2e_unavailable():
    program = ('import sys; import scripts.run_pair_stage_probes as r; '
               'r.main(["--stage","chain","--output","/nonexistent/never","--policies","b-v6d"]); '
               'assert "mujoco" not in sys.modules')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    plan = json.loads(out.stdout)
    assert plan['state'] == 'planned' and plan['cases'] == 19 and plan['case_ids'][0].startswith('chain@b-v6d:teacher:nominal')
    assert plan['unavailable_e2e'][0]['stage'] == 'chain' and 'teacher-staged only' in plan['unavailable_e2e'][0]['reason']


# ------------------------------------------------------------------ state carry-over (no re-staging)
def test_phase_of_maps_controller_states_to_the_leg_and_phase():
    assert pcp.phase_of(3, 'carry', 8) == ('carry', 3)
    assert pcp.phase_of(3, 'wait_lower', 8) == ('handover', 3)
    assert pcp.phase_of(3, 'cp_open', 8) == ('handover', 3)          # the counter moves on at the end of cp_open
    assert pcp.phase_of(4, 'pregrasp_look', 8) == ('regrasp', 4)
    assert pcp.phase_of(7, 'released', 8) == ('setdown', 7)
    assert pcp.phase_of(7, 'done', 8) == ('setdown', 7)
    assert pcp.phase_of(0, 'align', 8) == ('other', 0)
    tl = [[0., 0, 'carry'], [30., 0, 'wait_lower'], [50., 1, 'pregrasp_look']]
    assert pcp.phase_at(tl, 29., 8) == ('carry', 0) and pcp.phase_at(tl, 40., 8) == ('handover', 0)
    assert pcp.phase_at(tl, 60., 8) == ('regrasp', 1) and pcp.phase_at([[5., 0, 'carry']], 1., 8) is None


class FakeController:
    """Scripted stand-in for the registered controller: steps through legs; counts what the probe does to it."""
    SCRIPT = []
    for k in range(3):
        SCRIPT += [(k, 'carry'), (k, 'carry'), (k, 'wait_lower'), (k, 'lower'), (k, 'cp_open'), (k + 1, 'pregrasp_look'),
                   (k + 1, 'wait_carry')]

    def __init__(self):
        self.i = 0
        self.seg, self.state = self.SCRIPT[0]
        self.calls = 0
        self.staging_calls = 0
        self.attribute_writes = []

    def tick(self, now):
        self.calls += 1
        self.i = min(self.i + 1, len(self.SCRIPT) - 1)
        self.seg, self.state = self.SCRIPT[self.i]
        return ('tick-result', self.calls)

    def __setattr__(self, name, value):
        if name not in ('i', 'seg', 'state', 'calls', 'staging_calls', 'attribute_writes', 'tick'):
            self.attribute_writes.append(name)
        object.__setattr__(self, name, value)


def test_recorder_is_a_pass_through_that_never_restages_or_writes_the_controller():
    ctl = FakeController()
    gt_calls = []
    host = SimpleNamespace(gt_snapshot=lambda rid: gt_calls.append(rid) or gt([1., 0.]))
    probe = SimpleNamespace(host=host)
    execution = SimpleNamespace(own=SimpleNamespace(last_report=SimpleNamespace(as_dict=lambda: {
        't_est': 1., 'xyyaw': [0., 0., 0.], 'std_xy_m': .03, 'std_yaw_rad': .012, 'fix_age_s': 4.5, 'fix_source': 'tags_temporary'})))
    original = ctl.tick
    pcp.install_recorder(ctl, 'r1', probe, execution)
    assert ctl.tick is not original
    results = [ctl.tick(float(t)) for t in range(len(FakeController.SCRIPT) - 1)]
    assert results == [('tick-result', n) for n in range(1, len(results) + 1)]      # the original result, unchanged
    assert ctl.calls == len(results) and ctl.staging_calls == 0 and ctl.attribute_writes == []
    rec = probe.chain['r1']
    # timeline: every (seg, state) change is kept, in order, and the segment counter only ever grows (state carried on)
    segs = [row[1] for row in rec.timeline]
    assert segs == sorted(segs) and segs[0] == 0 and segs[-1] == 3
    assert sorted(rec.leg_start) == [0, 1, 2, 3]
    assert sorted(rec.leg_end) == [0, 1, 2]
    # eval-only GT is read only at boundaries (each leg start and leg end once), not on every tick
    assert len(gt_calls) == len(rec.leg_start) + len(rec.leg_end) < ctl.calls
    assert probe.chain['r1'] is rec and pcp.raw_of(probe)['r1']['ticks'] == ctl.calls


def test_a_second_robot_gets_its_own_recorder_on_the_shared_probe():
    probe = SimpleNamespace(host=None)
    exec_ = SimpleNamespace(own=SimpleNamespace(last_report=None))
    for rid in ('r1', 'r2'):
        c = FakeController()
        pcp.install_recorder(c, rid, probe, exec_)
        c.tick(0.)
    assert sorted(pcp.raw_of(probe)) == ['r1', 'r2']


# ------------------------------------------------------------------ accumulation metrics
def test_leg_metrics_match_the_stage_probe_formula_and_accumulate():
    from scripts import run_pair_stage_probes as runner
    ends = perfect_ends()
    ends[2] = [ends[2][0] + .03, ends[2][1] + .02]                     # leg 2 ends 3 cm along / 2 cm across
    ends[3] = [ends[3][0] + .03, ends[3][1] + .02 + .06]                # leg 3 (lateral): starts from the wrong end, adds 6 cm
    legs = pcp.chain_legs(ROUTE, make_raw(ends, yaw_of=lambda k: math.radians(.5) * (k + 1)))
    assert [l['recorded'] for l in legs][:4] == [True] * 4
    l2 = legs[2]
    ref = runner.leg_end_metrics(ROUTE[2], ROUTE[3], ends[2], 0., 0.)
    assert l2['end_error_m'] == pytest.approx(ref['end_error_m']) and l2['along_error_m'] == pytest.approx(ref['along_error_m'])
    assert l2['cross_track_m'] == pytest.approx(ref['cross_track_m'])
    assert l2['end_error_m'] == pytest.approx(math.hypot(.03, .02))
    # cumulative vs incremental: leg 3 starts at the actual end of leg 2 (error carried in), so its step error is only what
    # leg 3 itself adds while its cumulative end error still contains the carried-over error
    assert legs[3]['step_error_m'] == pytest.approx(math.hypot(.0, .06), abs=1e-9)
    assert legs[3]['end_error_m'] == pytest.approx(math.hypot(.03, .08), abs=1e-9)
    assert legs[3]['end_error_m'] > legs[3]['step_error_m']
    # yaw drift is cumulative against the chain start; the step is per leg
    assert legs[0]['yaw_drift_deg'] == pytest.approx(.5) and legs[3]['yaw_drift_deg'] == pytest.approx(2.)
    assert legs[3]['yaw_step_deg'] == pytest.approx(.5)
    assert legs[0]['leg_error_m'] == pytest.approx(0., abs=1e-9)
    assert legs[0]['handover_from_prev_end_s'] is None and legs[1]['handover_from_prev_end_s'] == pytest.approx(70. + .1 - 30.2 + 0., abs=.11)


def test_sigma_and_estimate_error_curves():
    legs = pcp.chain_legs(ROUTE, make_raw(perfect_ends(), sigma=lambda k: (.03 + .01 * k, .012 + .004 * k)))
    curves = pcp.curves(legs)
    assert curves['sigma_xy_end_m'] == pytest.approx([1.5 * (.03 + .01 * k) for k in range(8)])
    assert curves['sigma_yaw_end_rad'] == pytest.approx([1.5 * (.012 + .004 * k) for k in range(8)])
    assert all(v == pytest.approx(0., abs=1e-9) for v in curves['est_err_xy_end_m'])   # the fake own estimate equals GT
    assert legs[0]['sigma_xy_start_m'] == pytest.approx(.03) and legs[0]['fix_age_end_s'] == 4.5


def test_unreached_legs_are_not_recorded_and_have_no_metrics():
    legs = pcp.chain_legs(ROUTE, make_raw(perfect_ends()[:3]))
    assert [l['recorded'] for l in legs] == [True] * 3 + [False] * 5
    assert pcp.curves(legs)['end_error_m'][3:] == [None] * 5
    assert pcp.leg_checks(legs[5]) == {}


# ------------------------------------------------------------------ verdict and first failure
def chain_of(ends, *, gt_end=None, final=None, raw=None, case=None, **kw):
    case = case or case_for_chain()
    gt_end = gt_end or gt([ROUTE[-1][0], ROUTE[-1][1]], lift=.001, tilt=1., jaws={'r1': [False, False], 'r2': [False, False]})
    return pcp.chain_record(case, raw or make_raw(ends, **kw), gt_end, final or {'r1': 'done', 'r2': 'done'}, [])


def evaluate_chain(chain, failure=None):
    record = {'exits': {'r1': {}, 'r2': {}} if chain and not failure else {}, 'first_failure': failure, 'chain': chain}
    return sp.evaluate('chain', record), record


def test_a_clean_chain_passes_every_leg_and_the_setdown():
    chain = chain_of(perfect_ends())
    ev, record = evaluate_chain(chain)
    assert ev['passed'] and ev['category'] == 'PASS', ev['checks']
    assert chain['legs_recorded'] == 8 and chain['legs_passed_prefix'] == 8 and chain['setdown']['reached']
    assert set(ev['checks']) >= {'legs_recorded', 'lift', 'tilt', 'both_jaws_both_robots', 'end_error', 'leg_error', 'rest',
                                 'released', 'shift', 'controller_exit_both'}
    assert pcp.first_failure(chain, record) is None


def test_accumulated_drift_names_the_first_leg_over_the_limit_and_its_cause():
    ends = perfect_ends()
    for k in range(8):   # 3 cm of additional along-error every leg: cumulative 0.03 * (k + 1) -> first over 0.10 at leg 3
        ends[k] = [ends[k][0] + .03 * (k + 1), ends[k][1]]
    chain = chain_of(ends, starts=[[ROUTE[0][0], ROUTE[0][1]]] + [list(e) for e in ends[:-1]])
    ev, record = evaluate_chain(chain)
    assert not ev['passed'] and ev['category'].startswith('GT_CRITERIA') and 'end_error' in ev['category']
    ff = pcp.first_failure(chain, record)
    assert (ff['source'], ff['phase'], ff['leg'], ff['code']) == ('gt_criterion', 'carry', 3, 'MOTION_ERROR')
    assert chain['legs_passed_prefix'] == 3
    assert chain['curves']['end_error_m'][:4] == pytest.approx([.03, .06, .09, .12])
    # each leg on its own is within the per-leg criterion: it is the accumulation that fails (the reason for this probe)
    assert all(l['leg_error_m'] <= pcp.CRITERIA['max_leg_error_m'] for l in chain['legs'])
    assert all(l['step_error_m'] == pytest.approx(.03) for l in chain['legs'])


def test_controller_failure_between_legs_is_attributed_to_the_handover_and_regrasp_phase():
    raw = make_raw(perfect_ends()[:5])
    for r in raw.values():   # robot state at t=5*70-15: after leg 4's end, in the regrasp of leg 5
        r['timeline'] += [[5 * 70 - 40., 4, 'wait_lower'], [5 * 70 - 20., 4, 'cp_open'], [5 * 70 - 18., 5, 'pregrasp_look']]
    chain = chain_of(perfect_ends()[:5], raw=raw, final={'r1': 'failed', 'r2': 'failed'})
    failure = {'robot_id': 'r1', 'sim_s': 5 * 70 - 10., 'reason': 'POSE_UNCERTAIN'}
    ev, record = evaluate_chain(chain, failure)
    assert not ev['passed'] and ev['category'] == 'POSE_UNCERTAIN'
    own_at_failure = {'r1': {'std_xy_m': .02, 'std_yaw_rad': math.radians(4.)}}
    ff = pcp.first_failure(chain, record, own_at_failure)
    assert (ff['source'], ff['phase'], ff['leg'], ff['code'], ff['sub']) == ('controller', 'regrasp', 5, 'SELF_POSE_UNCERTAIN', 'yaw')
    cause = sp.classify_cause('chain', ev, record, {'own_at_failure': own_at_failure})
    assert cause['code'] == 'SELF_POSE_UNCERTAIN'
    assert chain['legs_recorded'] == 5 and not ev['checks']['legs_recorded']


def test_earliest_event_wins_between_a_gt_leg_failure_and_a_later_controller_abort():
    ends = perfect_ends()
    ends[1] = [ends[1][0] + .2, ends[1][1]]
    chain = chain_of(ends[:4], final={'r1': 'failed', 'r2': 'failed'})
    failure = {'robot_id': 'r2', 'sim_s': 3 * 70 + 40., 'reason': 'PAIR_COLLISION_GUARD'}
    _, record = evaluate_chain(chain, failure)
    ff = pcp.first_failure(chain, record)
    assert (ff['source'], ff['leg'], ff['code']) == ('gt_criterion', 1, 'MOTION_ERROR')


def test_setdown_failures_are_named_and_only_when_reached():
    dragged = gt([ROUTE[-1][0] + .08, ROUTE[-1][1]], lift=.001, tilt=1., jaws={'r1': [False, False], 'r2': [False, False]})
    chain = chain_of(perfect_ends(), gt_end=dragged)
    ev, record = evaluate_chain(chain)
    assert not ev['passed'] and ev['checks']['shift'] is False and chain['setdown']['shift_m'] == pytest.approx(.08)
    ff = pcp.first_failure(chain, record)
    assert (ff['phase'], ff['leg'], ff['code']) == ('setdown', 7, 'DRAGGED')
    unreached = chain_of(perfect_ends(), final={'r1': 'released', 'r2': 'released'})
    assert unreached['setdown']['reached'] is False
    assert pcp.first_failure(unreached, {'first_failure': None}) is None


def test_json_roundtrip_of_raw_keeps_the_leg_records_usable():
    raw = json.loads(json.dumps(make_raw(perfect_ends())))    # int keys become strings in result.json
    legs = pcp.chain_legs(ROUTE, raw)
    assert all(l['recorded'] for l in legs)


def test_summarize_chain_and_stage_summary_hook():
    good = chain_of(perfect_ends())
    ends = perfect_ends()
    ends[4] = [ends[4][0], ends[4][1] + .3]
    bad = chain_of(ends[:6])
    rows = []
    for i, ch in enumerate((good, bad)):
        ev, record = evaluate_chain(ch)
        ch['first_failure'] = pcp.first_failure(ch, record)
        rows.append({'stage': 'chain', 'source': 'teacher_grid', 'passed': ev['passed'], 'category': ev['category'],
                     'cause': 'PASS' if ev['passed'] else 'MOTION_ERROR', 'chain': ch, 'wall_s': 100., 'stage_sim_s': 500.,
                     'pair_policy': 'v5h', 'leg': None})
    summary = sp.summarize(rows)['stages']['chain']
    assert summary['cases'] == 2 and summary['passed'] == 1
    agg = summary['chain']
    assert agg['legs_recorded'] == {8: 1, 6: 1} and agg['legs_passed_prefix'] == {8: 1, 4: 1}
    assert agg['per_leg']['0']['reached'] == 2 and agg['per_leg']['7']['reached'] == 1
    assert agg['first_failure'] == [{'phase': 'carry', 'leg': 4, 'code': 'MOTION_ERROR', 'count': 1}]
    assert pcp.summarize_chain([{'stage': 'chain'}]) == {'cases': 0}


# ------------------------------------------------------------------ runner glue without a simulator
def test_finish_result_builds_the_chain_row_from_raw_recorders(tmp_path):
    from scripts import run_pair_stage_probes as runner
    case = case_for_chain()
    raw = make_raw(perfect_ends())
    result = {'case_id': case['case_id'], 'exits': {}, 'event_log': [], 'acks': {'r1': {'accepted': True}, 'r2': {'accepted': True}},
              'wall_s': 12.3, 'termination': {'sim_s': 600.}, 'final_states': {'r1': 'done', 'r2': 'done'},
              'entry': {'r1': {'sim_s': 3.}, 'r2': {'sim_s': 3.}}, 'submit_t': 3., 'chain_raw': raw,
              'gt_at_end': gt([ROUTE[-1][0], ROUTE[-1][1]], lift=.001, jaws={'r1': [False, False], 'r2': [False, False]}),
              'localizer_log': [{'t': 45., 'robot_id': 'r1', 'event': 'localizer_object_replaced'}],
              'localizer_stats': {}, 'checkpoints': []}
    row = runner.finish_result(case, result, tmp_path)
    assert row['passed'] and row['category'] == 'PASS' and row['stage'] == 'chain' and row['leg'] is None
    assert row['chain']['legs_recorded'] == 8 and row['chain']['first_failure'] is None
    assert row['chain']['localizer_replaced_events'] == [{'t': 45., 'robot_id': 'r1'}]
    assert row['chain']['restaging_between_legs'] is False
    assert json.loads((tmp_path / 'result.json').read_text())['row']['chain']['curves']['end_error_m'][0] == pytest.approx(0., abs=1e-9)
    json.dumps(row, allow_nan=False)


def test_finish_result_of_other_stages_has_no_chain_key(tmp_path):
    from scripts import run_pair_stage_probes as runner
    case = sp.teacher_cases('carry', subset={'nominal'}, nominal_seeds=(911,), leg=0)[0]
    result = {'case_id': case['case_id'], 'exits': {}, 'event_log': [], 'acks': {}, 'wall_s': 1., 'termination': {'sim_s': 5.},
              'final_states': {}, 'entry': {}, 'localizer_stats': {}, 'checkpoints': []}
    row = runner.finish_result(case, result, tmp_path)
    assert 'chain' not in row and row['stage'] == 'carry'


# ------------------------------------------------------------------ golden: existing stage outputs are unchanged
# Digests computed on origin/main 45a21b23 (before the chain stage existed).
GOLDEN_CASES = {
    ('align', ()): (19, '84c0c2ec59b6cd9399d6a95b728d608b27c9fd92400a4c470cb593d1ecfe52e9'),
    ('grasp_lift', ()): (19, '2be5291079add7849d69e738e078f9251696582cef83468ad5b01949e064821f'),
    ('carry', (('leg', 0),)): (19, '2165c8e46a0201ae80e49fbd302489789ba3cc419d0d7450511f2a25d2881faf'),
    ('carry', (('leg', 5), ('prior_std', 'e2e'))): (19, '277b28b193bd285bcf48192fe82fd3f199b343a811a86ba2893136bb62633ed5'),
    ('setdown', (('leg', 'end'), ('policy', 'b-v6d'), ('prior_std', 'e2e'))):
        (19, '50c569aade8aaa57aba8f0719b0c3f8c4f1317c729335ad224edbee9ee802237'),
    ('setdown', ()): (19, '76b6c866e95dcb38f5b4618c7a957c15988a8564ede8aba0db9a91d6829372e5'),
}


@pytest.mark.parametrize('stage,kw', list(GOLDEN_CASES))
def test_existing_stage_case_lists_are_byte_unchanged(stage, kw):
    cases = sp.teacher_cases(stage, **dict(kw))
    assert (len(cases), sp.digest(cases)) == GOLDEN_CASES[(stage, kw)]


def test_existing_stage_evaluation_criteria_and_summary_are_byte_unchanged():
    carry = {'exits': {'r1': {}, 'r2': {}}, 'first_failure': None,
             'gt_at_exit': {'lift_m': .1, 'tilt_deg': 2., 'jaws': JAWS}, 'max_tilt_deg': 3., 'min_lift_after_first_lift_m': .09,
             'beam_travel_m': .55, 'planned_leg_m': .55, 'end_error_m': .02, 'cross_track_m': .01, 'yaw_drift_deg': .2}
    assert sp.digest(sp.evaluate('carry', carry)) == '49748c50333f3d6ba909b815bba5442d47bd31fd425498367dc9ed71b7168237'
    setdown = {'exits': {'r1': {}, 'r2': {}}, 'first_failure': None, 'beam_shift_m': .01,
               'gt_at_exit': {'lift_m': .001, 'tilt_deg': 1., 'jaws': {'r1': [False, False], 'r2': [False, False]}}}
    assert sp.digest(sp.evaluate('setdown', setdown)) == 'ecc7d1958ecfa426e4b34b1c2bbf43ff6e17e40229042c917226e452169ac72c'
    assert sp.digest({k: sp.CRITERIA[k] for k in ('align', 'grasp_lift', 'carry', 'setdown')}) == \
        '97bb7955569c593327c4d28f3f70496a8388b9a616a6ff192c81c9f12bce94ef'
    assert sp.digest({k: sp.STAGES[k] for k in ('bootstrap', 'align', 'grasp_lift', 'carry', 'setdown')}) == \
        '0da861eac4656bcdfd64382b1c10df2663c857ff804b57a24901d065c22a1564'
    rows = [{'stage': 'carry', 'source': 'teacher_grid', 'passed': False, 'category': 'X', 'cause': 'MOTION_ERROR', 'wall_s': 1.,
             'stage_sim_s': 2., 'leg': 1, 'pair_policy': 'v5h'},
            {'stage': 'carry', 'source': 'teacher_grid', 'passed': True, 'category': 'PASS', 'cause': 'PASS', 'wall_s': 1.,
             'stage_sim_s': 2., 'leg': 1, 'pair_policy': 'v5h'}]
    summary = sp.summarize(rows)
    assert 'chain' not in summary['stages']['carry']
    assert sp.digest(summary) == '61e0b0dd31a17d4712f191e3f1b437b0c735843f8ca4cc92b31ed3f85746cf5e'
