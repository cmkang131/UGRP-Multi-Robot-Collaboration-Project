"""Actual frozen predicate and diagnosis math; no simulator or provider calls."""
import math
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import beam_frame_analysis as a


def saved():
    return a.r.read(Path(__file__).parent/'dev09_10_diagnosis.json')


def test_exact_frames_refute_tag_blackout_and_clock_predicate_is_reproduced():
    d=saved()
    bots=[b for r in d['dev'] for b in r['robots'].values()]
    assert sum(b['frame_count'] for b in bots)==154
    assert sum(b['frames_with_detected_tags'] for b in bots)==154
    checks=[c for b in bots for c in b['decision_checks']]
    assert len(checks)==10
    assert all(not c['exact_frozen_predicate'] for c in checks)
    assert sum(c['clock_clause_only_variant'] for c in checks)==9
    assert all(1e-9<c['estimated_tag_time_minus_now_s']<3e-9 for c in checks)


@pytest.mark.parametrize('bad', ['none','high_sigma','stale','no_new_fix','far_future'])
def test_clock_variant_does_not_remove_other_actual_gate_requirements(bad):
    # Build a report like dev09 r1's first consumed relook frame.
    f={'report':{'t_est':177.3,'initialized':True,'xyyaw':[.29,0.,0.],
                 'std_xy_m':.04552,'std_yaw_rad':.02159,'since_tag_s':0.,
                 'last_valid_obs':None,'n_eff':2000.,'load_state':'unloaded','source':'owncam_pf_v2'}}
    obs={'sim_time':177.2999999975354}
    if bad=='high_sigma':f['report']['std_xy_m']=.051
    if bad=='stale':f['report']['t_est']=176.
    if bad=='no_new_fix':f['report']['since_tag_s']=2.
    if bad=='far_future':f['report']['t_est']=177.301
    got=a.gate_check(f,obs,175.69999999757323,True)
    assert got['exact_frozen_predicate'] is False
    assert got['clock_clause_only_variant'] is (bad=='none')


def test_real_pf_report_rounds_capture_time_even_without_saved_serialization():
    from harness.owncam_localizer import OwnCamLocalizer
    from harness.owncam_pose_source import OwnCamPoseSource
    static={'bounds_m':[-2,2,-2,2],'obstacles':[],'landmarks':{'tags':[]}}
    loc=OwnCamLocalizer(static,seed=1);loc.initialized=True
    now=177.2999999975354;loc.t=now;loc.last_tag_t=now
    loc.px[:]=[0.,0.,0.]
    report=OwnCamPoseSource.report(NS(loc=loc,source='synthetic',last_obs=None),now)
    assert report.t_est==177.3
    assert report.t_est-report.since_tag_s>now
    assert 0<report.t_est-now<.0001


def test_sigma_budget_is_inverse_of_conservative_unchanged_margin():
    d,L,y,B=.5,.9,math.radians(3),.1
    cap=a.sigma_cap(d,L,y,bias=B)
    assert cap==pytest.approx(.1353761101961531)
    assert .035+B+2*cap+2*L*y==pytest.approx(d)
    assert a.sigma_cap(d,L,y,bias=.8)<0
    assert a.sigma_cap(d,L,y,bias=B+.1)<cap
    assert a.sigma_cap(d+.1,L,y,bias=B)>cap
    assert a.sigma_cap(d,L,y+.01,bias=B)<cap


def test_static_pickup_margin_is_not_uniform_over_approach():
    rows=saved()['static_budget']['rows']
    by={r['position_basis']:r for r in rows if r['robot']=='r2' and r['posture']=='LOOK_P20'}
    assert by['prestation']['min_nominal_clearance_m']<.5
    assert by['nominal_grasp_station']['min_nominal_clearance_m']>.5


def test_signed_rectangle_distance_rejects_inside_wall():
    b={'center':[0.,0.],'half':[.1,.2],'yaw':0.}
    assert a.signed_box_distance(b,0.,0.)==pytest.approx(-.1)
    assert a.signed_box_distance(b,.3,0.)==pytest.approx(.2)


def test_history_keeps_missing_evidence_unknown():
    h=saved()['history']
    assert (h['m2_run_count'],h['m2_trace_count'],h['vo_trace_count'])==(49,98,46)
    assert h['all_m2_full_design_unknown']==49
    assert h['m2_existing_fresh_preclose_pass']==0
    assert h['m2_existing_preclose_attempts']==206
    assert all(r['new_design_verdict']=='INSUFFICIENT_EVIDENCE' for r in h['m2_runs'])


def test_import_boundary_and_no_truth_inputs():
    d=saved()
    assert not d['GT_read'] and d['physics_steps']==d['model_calls']==0
    assert d['blocked_modules_not_imported']
    assert all('/eval_only/' not in p for p in d['hashes'])
    for module in ('mujoco','torch','tensorflow','httpx','requests'):
        with pytest.raises(ImportError):a.r.Boundary().find_spec(module)
