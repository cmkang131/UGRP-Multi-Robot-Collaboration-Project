import numpy as np
from scripts.analyze_own_route_error_budget import between,compose,interval_audit,motion_poses,kind,recorded_B


def test_se2_and_posterior_error_budget_distinguish_motion_from_jump():
    origin=np.array([2.,-1.,1.2]);delta=np.array([.1,.02,.2])
    np.testing.assert_allclose(between(origin,compose(origin,delta)),delta)
    truth=np.array([origin,compose(origin,delta)])
    own=truth.copy();own[1,0]+=.4
    dr=np.array([[0.,0.,0.],delta])
    pred,actual,innov,before,after=interval_audit(own,truth,dr)
    np.testing.assert_allclose(pred,actual,atol=1e-12)
    assert before[0]<1e-12 and abs(after[0]-.4)<1e-12
    assert abs(np.linalg.norm(innov[0,:2])-.4)<1e-12


def test_command_at_image_time_is_not_integrated_into_current_pose():
    commands=[dict(t=0.,kind='initial_servo_command',pulses={1:2000}),
              dict(t=.2,kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)]
    poses=motion_poses(commands,[0.,.2,.4])
    np.testing.assert_array_equal(poses[:2],np.zeros((2,3)))
    assert poses[2,0]>.01
    assert kind(commands[1])=='forward' and kind(dict(kind='hold'))=='hold'


def test_wall_failure_is_scored_from_events_not_excluded():
    assert not recorded_B(dict(status='WALL_CONTACT'),[])
    assert recorded_B(dict(status='WALL_CONTACT'),[dict(reason='goal_reached',entity='B')])
    assert not recorded_B(dict(declared_B=False),[])


def test_oracle_lateral_diagnosis_does_not_change_yaw_or_forward():
    from scripts.analyze_own_route_forensics import counterfactual
    gt=np.array([[0.,0.,0.],[0.,0.,.1],[.1*np.cos(.1),.1*np.sin(.1),.1]])
    dr=np.array([[0.,0.,0.],[0.,-.03,.1],[.1*np.cos(.1),-.03+.1*np.sin(.1),.1]])
    assert counterfactual(dr,gt,['left_turn','forward'],'turn_xy')['end_m']<1e-10
