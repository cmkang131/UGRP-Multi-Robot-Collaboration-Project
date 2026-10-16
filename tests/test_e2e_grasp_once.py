"""Actual approach dispatch and bundle admission; no simulation or rendering."""
import copy
import math
import numpy as np
import pytest
from harness import e2e_grasp_once as m
from harness import e2e_approach_commit as commit
from harness.e2e_carrier_approach import advance
from harness.e2e_pregrasp_gaze import fresh_gaze
from tests.test_e2e_align_progress import setup_transport


def setup(option):
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1',
        pregrasp_gaze='own_bearing_v1')
    tr.state='align';tr.approach_commit='memory60_view_v1';tr.stale_station='expire12_v1'
    m.install(tr,option);r=tr.robots['r1'];r.last_obs['sim_time']=2.
    r.goal.explorer.navigator.plan_to=lambda c,p,t:[p[:2],t]
    m.observe(r,2.)
    return tr,r


def miss(r, now, pose=None):
    r.beam=None;r.last_obs=dict(frame_id=round(now*10),sim_time=now)
    if pose is not None:r.goal.explorer.local_pose=np.asarray(pose,float)
    m.observe(r,now)


def test_missing_detection_keeps_fixed_own_anchor_and_gaze_not_rgb():
    tr,r=setup('gaze_v1');anchor=r.grasp_track['band'].copy()
    miss(r,3.,[-1.,0.,-.5])
    target=commit.gaze_target(tr,'r1',False,np.array([5.,5.]))
    assert target.tolist()==anchor and r.beam is None
    assert fresh_gaze(tr,'r1',target)==[dict(kind='look',pan_pulse=1818)]
    assert r.grasp_track['sigma_m']>.03
    assert r.grasp_track['seen']==2.
    miss(r,123.)
    assert commit.gaze_target(tr,'r1',False,[5.,5.]) is None


def test_baseline_off_and_efficiency_only_do_not_keep_gaze_or_station():
    for option in ('off','regulated_v1','gaze_v1'):
        tr,r=setup(option);advance(tr,'r1',2.);tr.queue.clear()
        miss(r,63.)
        fine,_=advance(tr,'r1',63.)
        assert not fine and 'station' not in tr.approach['r1']
        if option!='gaze_v1':assert commit.gaze_target(tr,'r1',False,[5.,5.]) is None
    assert m.compose({})==()


def test_actual_approach_retains_staging_only_and_expires_bounded_track():
    tr,r=setup('track_gaze_v1');advance(tr,'r1',2.);tr.queue.clear()
    miss(r,63.)
    fine,actions=advance(tr,'r1',63.)
    assert not fine and 'station' in tr.approach['r1'] and r.beam is None
    assert any(a['kind']=='mecanum' for a in actions)
    r.goal.explorer.local_pose=tr.approach['r1']['station'].copy()
    miss(r,64.)
    fine,_=advance(tr,'r1',64.)
    assert not fine and r.carrier_approach['status']=='reacquire_own_beam'
    miss(r,123.);fine,_=advance(tr,'r1',123.)
    assert not fine and 'station' not in tr.approach['r1']


def test_mapping_memory_can_seed_staging_but_not_fine_and_large_motion_retires():
    tr,r=setup('track_gaze_v1');miss(r,50.)
    fine,_=advance(tr,'r1',50.)
    assert not fine and tr.approach['r1']['last_seen']==2.
    assert any(e['event']=='own_track_staging_hypothesis' for e in tr.events)
    miss(r,65.,[-5.,0.,0.]);assert not m.valid(r,65.)
    fine,_=advance(tr,'r1',65.)
    assert not fine and 'station' not in tr.approach['r1']


def test_replayed_rgb_never_resets_uncertainty_or_time_and_robots_are_separate():
    tr,r=setup('track_gaze_v1');m.observe(tr.robots['r2'],2.)
    beam=copy.deepcopy(r.beam)
    r.goal.explorer.local_pose+=np.array([.1,0.,0.]);m.observe(r,2.2)
    sigma=r.grasp_track['sigma_m'];assert sigma>.03
    m.observe(r,2.3);assert r.grasp_track['sigma_m']>sigma
    miss(r,70.);r.beam=beam;m.observe(r,70.1)
    assert r.grasp_track['seen']==2. and tr.robots['r2'].grasp_track['sigma_m']==.03
    assert not m.valid(r,1.)


def test_unreachable_pan_is_clamped_and_reported_not_claimed_visible():
    tr,r=setup('gaze_v1');r.carrier_approach={}
    target=m.pan_target(tr,'r1',[-2.,0.])
    assert target==833 and not r.carrier_approach['gaze_pan_reachable']
    assert not tr.aligned


def test_registered_candidates_and_tamper_rejected(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',
        boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1',call_snapshot='prepared_v1',
        speech_context='recent4_v1',post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',
        controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',
        explore_idle='idle5_v1',admission_clock='tick_v1')
    parent=bundle(*args,**kw);assert parent['execution_bundle_id']=='e2e18-v375'
    for option,v in m.VERSIONS.items():
        b=bundle(*args,**kw,grasp_once=option);require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert m.parent_for_validation(b)['e2e_options']==parent['e2e_options']
        assert 'harness/e2e_grasp_once.py' in b['source_sha256']
        bad=copy.deepcopy(b);bad['grasp_once_parameters']['max_age_s']=9999
        with pytest.raises(ValueError):require_current(bad,ROOT)


def test_lost_band_distance_updates_existing_posture_and_keeps_final_gate():
    tr,r=setup('gaze_v1');state={'committed_camera':'search'}
    anchor=np.asarray(r.grasp_track['band'])
    miss(r,3.,[*list(anchor-[.24,0.]),0.])
    assert commit.view(tr,'r1',state,False,1.5)[0]=='inspect'
    assert r.beam is None and not tr.aligned


def test_diagnostic_dwell_clips_interval_and_does_not_count_stale_tail():
    from scripts.analyze_e2e_grasp_once import dwell,losses
    frames=[dict(t=0.,carrier_approach={'status':'acquire_scan'},own_beam={'x':1}),
            dict(t=2.,carrier_approach={'status':'navigate_pregrasp'},own_beam=None,
                 own_beam_observation={'result':{'reason':'BAND_CLIPPED'}}),
            dict(t=5.,carrier_approach={'status':'visual_servo'},own_beam=None)]
    assert dwell(frames,1.,4.)=={'acquire_scan':1.,'navigate_pregrasp':2.}
    assert len(losses(frames,1.,4.))==1
