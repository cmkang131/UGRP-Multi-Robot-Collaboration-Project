"""Saved/synthetic own-pose decisions only. No physics or rendering."""
import math
import json
from pathlib import Path
import numpy as np
import pytest
from harness.e2e_rpp_path import carrot,command,lookahead_distance,install
from harness.self_pulse_rotation import selected_model


def action(angle, length=2., pose=(0.,0.,0.)):
    point=[pose[0]+length*math.cos(angle+pose[2]),pose[1]+length*math.sin(angle+pose[2])]
    plan=dict(coordinate_frame='r2/own_odom',status='frontier',path_m=[list(pose[:2]),point],heading_rad=pose[2])
    return command(plan,pose,selected_model('s2_pulse_v122_rotL_v1')['profiles'],robot_id='r2')


def test_first_radial_point_and_last_endpoint_not_short_grid_cell():
    path=[[0,0],[.025,.025],[.4,.4],[.6,.02],[1,0]]
    assert carrot(path,[0,0,0],.6)==[.6,.02]
    assert carrot(path[:3],[0,0,0],.6)==[.4,.4]
    assert lookahead_distance(2)==.6  # official default: scaling disabled
    assert [lookahead_distance(v,velocity_scaled=True) for v in (0,.3,2)]==pytest.approx([.3,.45,.9])


def test_rpp_rotation_threshold_sign_has_no_history_or_hysteresis():
    for angle in (.784,-.784,0.):
        a,info=action(angle)
        assert a['forward']>0 and a['turn']==0 and info['phase']=='forward_path'
    for angle in (.786,-.786,.786):
        a,info=action(angle)
        assert a['forward']==0 and a['turn']*angle>0 and info['phase']=='rotate_path'
        assert a['duration_s']==.1


def test_frame_transform_and_finite_pulses():
    a,info=action(.2)
    other,translated=action(.2,pose=(2.,-1.,1.2))
    assert other==a
    assert translated['heading_error_rad']==pytest.approx(info['heading_error_rad'])
    assert sum(a[k]!=0 for k in ('forward','left','turn'))==1
    assert action(0,length=.02)[0]==dict(kind='hold')
    assert install(object()) is not None
    with pytest.raises(ValueError):install(object(),'unknown')


def test_dev_startup_is_observational_but_legacy_still_stops():
    from scripts.run_e2e_ownmap_live import startup_decision,bundle
    args=dict(enabled=True,exploration_progress='frontier_progress_v1',pose_fix='innovation')
    legacy=bundle('a'*40,61001,'study_gemma4_31b_v1',**args)
    dev=bundle('a'*40,61001,'study_gemma4_31b_v1',path_follow='rpp_v1',dev_light=True,**args)
    p=dict(first_model_response=True,own_map_B_generated=False,wall_s=250,
           robots={r:dict(map_frames=20,translation_commands=0) for r in ('r1','r2')})
    assert startup_decision(p,legacy)==dict(passed=False,would_stop=True,stop=True)
    assert startup_decision(p,dev)==dict(passed=False,would_stop=True,stop=False)
    assert dev['execution_bundle_id']=='e2e-rpp-lookahead-v197'
    assert 'harness/e2e_rpp_path.py' in dev['source_sha256']
    from scripts.s4_proxy_relay import accepted_call_id
    assert accepted_call_id('e2e10-a-s61004:call-0001-r1:1')
    assert accepted_call_id('e2e10-b-s61002:call-0001-r2:1')
    assert accepted_call_id('e2e10-b-s61002-r2:call-0001-r2:1')
    assert not accepted_call_id('e2e10-b-s61004:call-0001-r2:1')


def test_real_host_wires_rpp_after_rep105_transform_and_keeps_coast():
    from harness.e2e_live_mapping import make_goal
    from types import SimpleNamespace
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    goal=make_goal('r2',61003,cov,pose_fix='innovation',path_follow='rpp_v1')
    host=goal.heading_host
    kw=dict(t=0.,pose=np.array([2.,3.,0.]),path=[[2.025,3.025],[3.,3.]],goal=[3.,3.],
        costmap=SimpleNamespace(pose_clear=lambda p:True),core=SimpleNamespace(collision_time=lambda *a:-1.),
        points=np.zeros((0,2)),map_pose=np.zeros(3),dev_light=True)
    a,info=host.command(**kw)
    assert a['forward']>0 and a['turn']==0
    assert info['path_follow']=='rpp_v1' and host.ready>0
    assert host.command(**kw)[0]['kind']=='hold'


def test_dev_reobservation_deadline_records_once_and_actual_go_failure_stops():
    from harness.e2e_live_transport import Transport
    from types import SimpleNamespace
    profiles=json.loads(Path('configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    transport=Transport({},SimpleNamespace(),profiles,dev_light=True)
    transport.state='relook'
    for t in (20.,21.):
        assert transport.observation_timeout('OWN_RGB_METRIC_CORRECTION_TIMEOUT',t)==[]
    assert transport.failure is None and len(transport.events)==1
    transport.fail('CURRENT_GO_ACK_TIMEOUT',22.)
    assert transport.failure=='CURRENT_GO_ACK_TIMEOUT' and transport.state=='failed'


def test_managed_workflow_does_not_require_a_value_for_store_true_flag():
    from sim.workflow_manager import _row,_validate_args
    row,_=_row(Path.cwd(),'e2e-rpp-lookahead-v197')
    argv=[]
    for flag in row['required_inputs']:
        argv.extend([flag,'off' if flag=='--path-follow' else 'fixture'])
    argv.extend(['--dev-light','--execute'])
    assert _validate_args(row,argv)=='--output'
