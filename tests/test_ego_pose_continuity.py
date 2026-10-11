import copy
import math
from types import SimpleNamespace
import numpy as np
import pytest

from harness.ego_pose_continuity import (Options, Reporter, PoseView, install,
    dominant_cluster, REP105, CLUSTER, STATIONARY, MAHALANOBIS, BOUND, CHI2_99_XY)
from harness.active_wall_mapping import compose, inverse
from harness.self_odom_grid import transform


def test_off_has_no_wrappers_or_state():
    c = SimpleNamespace(receive=object())
    before = vars(c).copy()
    assert install(c) is c and vars(c) == before
    with pytest.raises(ValueError):
        Options(correction_gate='invented')


def test_cluster_total_mass_not_highest_particle_and_yaw_seam():
    p = [[0,0,math.pi-.01],[.1,0,-math.pi+.01],[4,0,0]]
    mean, detail = dominant_cluster(p,[.3,.3,.4])
    assert detail['clusters']==2 and detail['particles']==2
    assert mean[0] == pytest.approx(.05)
    assert abs(abs(mean[2])-math.pi)<1e-9
    assert detail['mass']==pytest.approx(.6)


def test_mahalanobis_xy_99_percent_and_joseph_psd():
    o=Options(correction_gate=MAHALANOBIS)
    a=Reporter([0,0,0],np.eye(3)*.01,o)
    # Sxx=.02: a 0.7m jump has d2=24.5 and must not move the output.
    row=a.measure([.7,0,0],np.eye(3)*.01)
    assert row['mahalanobis_xy']==pytest.approx(24.5)
    assert not row['accepted'] and np.array_equal(a.pose,[0,0,0])
    row=a.measure([math.sqrt(.02*(CHI2_99_XY-1e-6)),0,0],np.eye(3)*.01)
    assert row['accepted'] and np.linalg.eigvalsh(a.covariance).min()>0


def test_process_bound_rejects_measurement_at_true_command_standstill():
    a=Reporter([0,0,0],np.eye(3)*.01,Options(correction_limit=BOUND))
    assert a.measure([.01,0,0],np.eye(3)*.01)['reason']=='motion_covariance_rejected'
    a.predict([.01,0,0],np.eye(3)*.001)
    assert a.measure([.02,0,0],np.eye(3)*.01)['accepted']


def fixture_controller():
    from harness.self_map_rbpf import RaoBlackwellizedGrid
    from harness.self_pulse_rotation import RotationPulseOdometry
    g=RaoBlackwellizedGrid('r3',correction_options={'particles':30},start_time=0.)
    driver=RotationPulseOdometry(0.);driver.step_callback=g.propagate;g.odom.driver=driver
    g.odom.command(dict(t=0.,kind='initial_servo_command',pulses={1:2000}))
    calls=[]
    def observe(rec,segments,**kw):
        calls.append(rec['t_sim'])
        # Explicit multimodal measurement; never use test evaluation truth.
        g.poses[:15,0]=.1;g.poses[15:,0]=.7
        g.weights[:15]=.04;g.weights[15:]=.4/15;g.best=15
        g.decisions.append(dict(t=rec['t_sim'],matching_attempted=True,particle_events=[{}]))
        return segments
    g._observe=observe
    e=SimpleNamespace(memory=SimpleNamespace(self_map=g))
    host_calls=[]
    def host(**kw):host_calls.append(kw);return {'kind':'hold'},{}
    c=SimpleNamespace(explorer=e,heading_host=SimpleNamespace(command=host))
    c._localize=lambda sample,t:None
    def receive(**kw):
        g.odom.advance(kw['t'])
        g._observe({'t_sim':kw['t'],'view_index':1},[[[0,0],[1,0]]],camera_xy=[0,0],robot_id='r3')
        return {'kind':'hold'},{'local_pose':list(g.odom.pose)}
    c.receive=receive
    return c,g,calls,host_calls


def test_live_receive_uses_cluster_reporter_before_control_and_skips_static_pf():
    c,g,calls,_=fixture_controller()
    install(c,Options(pose_reporting=CLUSTER,stationary_update=STATIONARY))
    _,t=c.receive(t=0.)
    assert t['local_pose'][0]==pytest.approx(.34)  # adjacent bins form one AMCL component
    c.receive(t=1.)
    assert calls==[0.] and c._pose_continuity_view.skips==1
    assert g.odom.base.pose[0]==.7 and g.odom.pose[0]==pytest.approx(.34)


def test_rep105_transforms_targets_after_reference_path_selection(monkeypatch):
    from harness.goal_route_heading import Host, shared
    c,g,_,_=fixture_controller()
    host=object.__new__(Host)
    host.robot_id='r3';host.profiles={};host.ready=-math.inf;host.rows=[]
    c.heading_host=host;install(c,Options(pose_continuity=REP105))
    calls=[]
    def select(plan,pose,*a,**kw):
        calls.append({'pose':np.asarray(pose).copy(),'plan':plan});return {'kind':'hold'}
    monkeypatch.setattr(shared,'command',select)
    local=np.array([.7,.2,.6]); goal=[1.4,-.2];path=[goal]
    kw=dict(t=0,pose=local,path=path,goal=goal,map_pose=[8,4,.6],costmap=None,core=None,points=[],dev_light=True)
    c.heading_host.command(**kw)
    actual=calls[0]
    assert np.allclose(actual['pose'],[0,0,0])
    assert np.allclose(transform([goal],inverse(local)),[actual['plan']['path_m'][-1]])
    # A new map correction changes only transform/targets, never odom pose.
    c.heading_host.command(**dict(kw,pose=local+[.7,0,0]))
    assert np.array_equal(calls[0]['pose'],calls[1]['pose'])
