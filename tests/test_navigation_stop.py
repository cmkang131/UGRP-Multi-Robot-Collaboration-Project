"""v8 final zero velocity contract; no MuJoCo or model requests."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.self_map_prob import V7CommandOdometry
from harness.public_navigation_monitor import ApproachMonitor,MonitorActor,navigation_output_v8
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_recovery import issued_twist

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'experiments/2026-10-07-mapfree-collision-monitor/code/integer_episode.py'
spec=importlib.util.spec_from_file_location('v8_integer_stop',path)
episode=importlib.util.module_from_spec(spec)
spec.loader.exec_module(episode)


def moving():
    odom=V7CommandOdometry()
    odom.command(command_from_twist(np.array([.12,.03,.2]),0.,1.))
    odom.advance(1.)
    assert np.linalg.norm(odom._predictor.vel)>.1
    return odom


@pytest.mark.parametrize('command',[dict(kind='stop'),dict(kind='hold'),
    dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1)])
def test_zero_velocity_stops_residual_and_positive_command_resumes(command):
    old,new=moving(),episode.velocity_stop(moving(),navigation='public_ros_v8')
    before=np.array(new.pose)
    original_cov=new.covariance.copy()
    for odom in (old,new):odom.command(dict(t=1.,**command))
    np.testing.assert_array_equal(new.covariance,original_cov)
    np.testing.assert_array_equal(new._predictor.vel,np.zeros(3))
    for odom in (old,new):odom.advance(3.)
    # Concrete old counterexample: command is zero, but the .3 s filter coasts.
    assert np.linalg.norm(np.array(old.pose)-before)>.02
    np.testing.assert_array_equal(new.pose,before)
    np.testing.assert_array_equal(new.covariance,original_cov)
    new.command(command_from_twist(np.array([.12,0.,0.]),3.))
    new.advance(3.1)
    assert np.linalg.norm(np.array(new.pose)-before)>1e-5


def test_timeout_collision_stop_and_safe_resume_use_same_final_zero_path():
    monitor=ApproachMonitor()
    wanted=command_from_twist(np.array([.12,0.,0.]),1.)
    for reason,points,stamp in [('invalid_source',[],None),('approach',np.zeros((6,2)),1.)]:
        odom=episode.velocity_stop(moving(),navigation='public_ros_v8')
        pose=np.array(odom.pose)
        if stamp is not None:monitor.observe(points,pose,stamp)
        stopped,info=monitor.filter(wanted,pose,1.)
        assert info['reason']==reason and np.array_equal(issued_twist(stopped),np.zeros(3))
        odom.command(stopped)
        odom.advance(1.1)
        np.testing.assert_array_equal(odom.pose,pose)
    # Fresh safe observation removes the stop; old requested velocity is not replayed.
    monitor.observe([],pose,1.1)
    fresh=command_from_twist(np.array([.1,0.,0.]),1.1)
    result,info=monitor.filter(fresh,pose,1.1)
    assert result is fresh and info['reason']=='clear'


def test_wait_does_not_run_navigation_and_expired_source_cannot_resume():
    actor=MonitorActor('own_frontier',navigation='public_ros_v8')
    def poison(*a,**kw):raise AssertionError('waiting advanced planner')
    actor.navigator.command=poison
    actor.monitor.observe([],actor.odom.pose,0.)
    for t in (0.,1.,1.1,2.):
        actor.t=t
        np.testing.assert_array_equal(issued_twist(actor.wait_command()),np.zeros(3))
    assert [x['reason'] for x in actor.monitor_log]==['clear','clear','invalid_source','invalid_source']


def test_off_is_lazy_and_nonzero_dynamics_are_unchanged():
    poison=object()
    assert episode.velocity_stop(poison) is poison
    sentinel=b'{"legacy":true}\n'
    assert navigation_output_v8(sentinel,navigator=poison) is sentinel
    with pytest.raises(ValueError):episode.velocity_stop(poison,navigation='public_ros_v7')
    old=V7CommandOdometry()
    new=episode.velocity_stop(V7CommandOdometry(),navigation='public_ros_v8')
    for i in range(10):
        cmd=command_from_twist(np.array([.12,.02,.1]),i/10)
        for x in (old,new):x.command(cmd)
        for x in (old,new):x.advance((i+1)/10)
        np.testing.assert_array_equal(old.pose,new.pose)
        np.testing.assert_array_equal(old.covariance,new.covariance)
    assert 'mujoco' not in sys.modules


def test_real_2d_world_and_oracle_pose_bridge_both_stop():
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-collision-monitor/code'))
    import monitor_common as m
    manifest=m.read(m.v7.EXP/'cohort.json')
    runner=m.configure(manifest)
    row=manifest['rows'][0]
    world=runner.RectangleOracleWorld(row['scenario'],row['pose'],row['seed'],'confirmation')
    actor=runner.PublicActor('own_frontier',None,None,navigation='public_ros_v3')
    world.motion=episode.velocity_stop(world.motion,navigation=actor.option)
    actor.odom=episode.velocity_stop(actor.odom,navigation=actor.option)
    command=command_from_twist(np.array([.04,0.,0.]),0.,.5)
    actor.odom.command(command)
    world.advance(command,.5)
    actor.odom.advance(.5)
    before=world.pose.copy()
    distance=world.distance
    stop=dict(t=.5,kind='stop')
    actor.odom.command(stop)
    world.advance(stop,2.5)
    actor.odom.advance(2.5)
    np.testing.assert_array_equal(world.pose,before)
    assert world.distance==distance and not world.collisions
    np.testing.assert_array_equal(actor.odom._predictor.vel,np.zeros(3))
    assert 'mujoco' not in sys.modules
