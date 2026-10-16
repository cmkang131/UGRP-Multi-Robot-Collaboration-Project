"""Candidate scheduling, safe viewpoints and unchanged RGB gate; no physics."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_boundary_views as m
from harness.e2e_rgb_gate import boundary
from harness.public_navigation_unknown import UnknownCostmap
from harness.zone_study_contract import ContractViolation
from harness.active_camera import SEARCH


def candidate(): return dict(kind='B',source='own',center_m=[1.,0.])


def fixture():
    c=UnknownCostmap(np.zeros((100,100),np.uint8),[-2.5,-2.5],.05)
    goal=SimpleNamespace(entities={'B':candidate()},e2e_gate=SimpleNamespace(references={},current=None),
        explorer=SimpleNamespace(map_to_odom=np.zeros(3)))
    n=m.CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),goal)
    return n,goal,c


def test_off_identity_and_closed_input_boundary():
    x=object();assert m.install(x) is x
    assert not m.request(candidate(),False)
    assert m.request(candidate(),False,option=m.OPTION)
    assert not m.request(candidate(),True,option=m.OPTION)
    assert not m.request(None,False,option=m.OPTION)
    for row in ({**candidate(),'source':'peer'},{**candidate(),'truth':[0,0]},
                {**candidate(),'center_m':[float('nan'),0]}):
        with pytest.raises(ContractViolation):m.request(row,False,option=m.OPTION)
    with pytest.raises(ValueError):m.install(x,'unknown')


def test_static_map_views_require_rgb_registration_before_live_install():
    n, goal, _ = fixture()
    goal.explorer.navigator = n
    # A self-map->odometry transform, even nonzero, cannot register the static map.
    goal.explorer.map_to_odom = np.array([3.9, -1.4, -np.pi/4])
    with pytest.raises(ValueError, match='STATIC_MAP_TO_OWN_RGB_REGISTRATION_REQUIRED'):
        m.install(goal, m.STANDOFF_OPTION)
    assert goal.explorer.navigator is n
    assert not n.view_active and not n.events


def test_view_is_reachable_free_faces_candidate_and_checks_swept_connectors():
    n,g,c=fixture()
    v=m.choose_view(c,np.zeros(3),[1,0],n.plan_to)
    assert v is not None and abs(v['heading'])<1e-6
    assert c.raw[c.world_to_map(v['target'])[::-1]]==0
    # NavFn accepts points, but a footprint-straddling unknown connector is unsafe.
    c.raw[:]=255;c.costs=c.inflate()
    assert m.choose_view(c,np.zeros(3),[1,0],n.plan_to) is None
    c.raw[:]=0;c.costs=c.inflate();c.sweep_clear=lambda *args:False
    assert m.choose_view(c,np.zeros(3),[1,0],n.plan_to) is None


def test_frontier_finished_is_reopened_for_confirmation_without_promoting_B():
    n,g,c=fixture();n.finished=True
    plan=n.update(c,np.zeros(3),84.)
    assert n.view_active and not n.finished
    assert n.events[-1]['reason']=='B_confirmation_view_selected'
    assert not g.e2e_gate.references
    assert n.frontier is None and (plan['path_m'] or n.phase=='B_candidate_observe')


def test_baseline_unknown_tracking_cannot_admit_a_candidate_footprint():
    n,g,c=fixture()
    # Center free, perimeter unknown: existing v8 accepts this outline, while
    # the candidate approach must require observed space across the whole body.
    c.raw[:]=255
    x,y=c.world_to_map([0,0]);c.raw[y,x]=0;c.costs=c.inflate()
    assert c.pose_clear([0,0,0])
    assert not m.observed_sweep_clear(c,[0,0,0],[0,0,0])
    assert m.choose_view(c,np.zeros(3),[1,0],n.plan_to) is None


def test_new_grid_cannot_keep_a_previously_admitted_view_without_coverage():
    n,g,c=fixture();n.core.frontiers=lambda *args:[]
    n.update(c,np.zeros(3),0.)
    assert n.view_active
    c.raw[:]=255;c.costs=c.inflate()
    n.update(c,np.zeros(3),.2)
    assert not n.view_active and g.entities['B']==candidate()
    assert any(e['reason']=='B_view_coverage_lost' for e in n.events)


def test_three_views_are_finite_and_do_not_blacklist_the_candidate():
    n,g,c=fixture();n.core.frontiers=lambda *args:[]
    for i in range(m.MAX_VIEWS):
        n.update(c,np.zeros(3),i*31.)
        assert n.view_active
        n.end_view(i*31.+30.,'fixture_timeout')
    n.update(c,np.zeros(3),95.)
    assert not n.view_active and len(n.tried_own)==m.MAX_VIEWS
    assert not n.blacklist and g.entities['B']==candidate()


def test_fresh_views_wait_for_full_boundary_and_failed_local_view_resumes():
    n,g,c=fixture();n.update(c,np.zeros(3),0.)
    pose=np.array([*n.target,n.heading]);n.update(c,pose,.2)
    assert n.phase=='B_candidate_observe'
    for i in range(3):
        t=.2+i*.2;g.e2e_gate.current=dict(ref=dict(frame_id=i,t_sim=t))
        n.command(c,pose,{},t)
        assert not g.e2e_gate.references
    assert not n.view_active and len(n.tried_own)==1
    assert n.events[-1]['reason']=='B_view_observed_still_unconfirmed'
    n.update(c,np.zeros(3),1.)
    g.e2e_gate.references['B']={'ref':'existing_verified_anchor'}
    n.update(c,np.zeros(3),1.2)
    assert not n.view_active


def test_observation_replay_cannot_reuse_a_frame_or_turn_through_unknown():
    n,g,c=fixture();n.update(c,np.zeros(3),0.)
    pose=np.array([*n.target,n.heading]);n.update(c,pose,.2)
    g.e2e_gate.current=dict(ref=dict(frame_id=1,t_sim=.2))
    for _ in range(3):n.command(c,pose,{},.2)
    assert n.view_active and len(n.observe_frames)==1
    c.sweep_clear=lambda *args:False
    cmd=n.command(c,np.array([*pose[:2],pose[2]+1.]),{},.4)
    assert not n.view_active and not any(cmd.get(k,0) for k in ('forward','left','turn'))


def test_boundary_diagnostics_preserve_baseline_and_never_make_missing_contour_complete():
    rgb=np.zeros((480,640,3),np.uint8);diag={}
    assert boundary(rgb,SEARCH,[0,0,0]) is None
    assert boundary(rgb,SEARCH,[0,0,0],diagnostics=diag) is None
    assert diag==dict(blue_pixels=0,contours=[],accepted_candidates=0)


def test_real_robot_wires_option_and_logs_diagnostics_without_promoting_coverage():
    pytest.importorskip('mujoco', exc_type=ModuleNotFoundError)
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    import base64,hashlib,cv2
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r=Robot('r1',61001,cov,Options(),exploration_progress='frontier_progress_v1',boundary_views=m.OPTION)
    image=np.zeros((480,640,3),np.uint8);ok,data=cv2.imencode('.jpg',image);data=data.tobytes()
    trace=r.receive(dict(frame_id=1,sim_time=0.,sha256=hashlib.sha256(data).hexdigest(),
                         image=base64.b64encode(data).decode()),image)
    assert trace['boundary_view']['option']==m.OPTION
    assert trace['boundary_diagnostics']['accepted_candidates']==0
    assert not r.goal.e2e_gate.references.get('B')
    with pytest.raises(ValueError):Robot('r1',61001,cov,Options(),boundary_views=m.OPTION)


def test_evaluator_clock_and_initial_frame_are_used_only_in_diagnostic(tmp_path):
    from scripts.diagnose_e2e_bboundary import pose_diagnosis
    (tmp_path/'eval_only/r1').mkdir(parents=True);(tmp_path/'robots/r1').mkdir(parents=True)
    truth=[dict(t=1.3,robot_xyz_m=[10,20,0],robot_yaw_rad=np.pi/2),
           dict(t=1.5,robot_xyz_m=[10,21,0],robot_yaw_rad=np.pi/2)]
    (tmp_path/'eval_only/r1/trajectory.jsonl').write_text('\n'.join(json.dumps(v) for v in truth))
    frames=[dict(frame_id=i+1,sim_time=t) for i,t in enumerate((1.3,1.5))]
    (tmp_path/'robots/r1/frames.jsonl').write_text('\n'.join(json.dumps(v) for v in frames))
    rows=[dict(t=t,frame_id=i+1,pose_own_m=[i,0,0],remembered_B={**candidate(),'center_m':[2,0]})
          for i,t in enumerate((0,.2))]
    measured=pose_diagnosis(tmp_path,'r1',rows,{})
    assert measured['max_position_error_m']<1e-12
    assert measured['max_candidate_rigid_reprojection_shift_m']<1e-12
    assert measured['max_capture_time_residual_s']==0
    assert rows[0]['pose_own_m']==[0,0,0] and rows[1]['pose_own_m']==[1,0,0]


def test_repeated_waypoint_preserves_heading_and_terminal_rotation_check(monkeypatch):
    seen=[]
    def sweep(costmap,start,end):
        seen.append((list(start),list(end)))
        return abs(end[2]-np.pi)<1e-12
    monkeypatch.setattr(m,'observed_sweep_clear',sweep)
    assert m.observed_path_clear(object(),[0.,0.,np.pi],[[0.,0.],[0.,0.]],np.pi)
    assert len(seen)==1 and seen[0][0][2]==np.pi
    assert not m.observed_path_clear(object(),[0.,0.,np.pi],[[0.,0.],[0.,0.]],0.)
