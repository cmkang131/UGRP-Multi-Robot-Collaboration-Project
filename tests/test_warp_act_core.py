import numpy as np
import pytest
from scripts.warp_act_core import relay, visible_relative, control_tape


def test_vector_relay_has_independent_hysteresis_and_reversal():
    u = np.array([[.2, .35, -.2, -.35], [.2, .35, -.2, -.35]])
    state = np.array([[0, 0, 0, 0], [1, 1, -1, 1]])
    effective, out = relay(u, state, start_fraction=.325, kinetic_fraction=1/12)
    assert out.tolist() == [[0, 1, 0, -1], [1, 1, -1, -1]]
    assert effective[0, 0] == 0 and effective[1, 0] > 0
    assert np.array_equal(state, [[0,0,0,0],[1,1,-1,1]])


def test_lazy_visibility_never_reads_held_or_invisible_worlds():
    calls = []
    ids, value = visible_relative([3,7,0,2], [7,7,0,7], [False,True,False,False],
        lambda ids: calls.append(ids.tolist()) or np.ones((len(ids),4)))
    assert calls == [[0]] and ids.tolist() == [0] and value.shape == (1,4)
    visible_relative([0], [7], [True], lambda _: pytest.fail('forbidden read'))


def test_visibility_rejects_bulk_truth():
    with pytest.raises(ValueError, match='selected-world'):
        visible_relative([3,0],[7,7],[False,False],lambda _: np.zeros((2,4)))


def row(now=2.):
    return dict(ctrl=np.zeros(10), wheels=[.35]*4, deadlines=[now+.001,0,0,0],
        applied=[1500.]*5,target=[1502.,1500.,1500.,1500.,1500.],
        servo_active=[True,False,False,False,False],now=now,servo_time=now)


def test_fractional_pwm_progress_and_wheel_deadline_on_physics_ticks():
    lookup = np.tile(np.arange(500,2501),(5,1))
    tape, state = control_tape([row(),row()],np.zeros((2,4),int),dt=.00025,steps=8,
        lookup=lookup,wheel_ids=[0,1,2,3],servo_ids=[[4],[5],[6],[7],[8]],
        start_fraction=.325,kinetic_fraction=1/12,torque_cap_nm=1.)
    assert tape.shape == (8,2,10)
    assert tape[0,0,4] == 1500 and tape[3,0,4] == 1502
    assert tape[3,0,0] > 0 and tape[4,0,0] == 0
    assert tape[4,0,1] > 0
    assert state['applied'][0,0] == 1502
    assert np.array_equal(tape[:,0],tape[:,1])


def test_nonfinite_or_out_of_range_relay_denied():
    with pytest.raises(ValueError):relay([[np.nan,0,0,0]],[[0]*4],start_fraction=.325,kinetic_fraction=1/12)
    with pytest.raises(ValueError):relay([[1.1,0,0,0]],[[0]*4],start_fraction=.325,kinetic_fraction=1/12)


def test_runner_mac_and_default_off_deny_before_output_or_simulator(monkeypatch,tmp_path):
    import sys
    from scripts import run_warp_act_teacher as runner
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    for backend in ('off','mjwarp_batch_v1'):
        monkeypatch.setattr(sys,'argv',['runner','--physics-backend',backend,
            '--teacher-source',str(tmp_path),'--plan',str(tmp_path/'missing.json'),
            '--out',str(tmp_path/'out'),'--vm-hourly-usd','1.096'])
        with pytest.raises(SystemExit,match='2'):runner.main()
        assert not (tmp_path/'out').exists()


def test_pwm_tape_matches_real_camera_port_without_physics():
    from types import SimpleNamespace
    from sim.camera_robot_port import CameraRobotPort
    servos=(1,3,4,5,6)
    class Robot:
        servo_command_pulses={s:1500 for s in servos}
        def __init__(self):self.setpoint={s:1500 for s in servos}
        def set_servo_pulses(self,values):self.setpoint.update(values)
        def set_motor_commands(self,values):pass
    expected=[]
    rows=[]
    for offset in (0.,.25):
        robot=Robot();world=SimpleNamespace(data=SimpleNamespace(time=2.),robot=lambda _:robot)
        port=CameraRobotPort(world,'r1')
        port._servo_applied={s:1500.+offset for s in servos}
        port._queue_servos({1:1537,3:1461,4:1511,5:1500,6:1499},2.)
        rows.append(dict(ctrl=np.zeros(10),wheels=[0.]*4,deadlines=[0.]*4,
            applied=[port._servo_applied[s] for s in servos],
            target=[port._servo_targets[s] for s in servos],servo_active=[True]*5,
            now=2.,servo_time=port._servo_tick_time))
        samples=[]
        for tick in range(400):
            port._advance_servos(2.+tick*.00025)
            samples.append([robot.setpoint[s] for s in servos])
        expected.append(samples)
    tape,_=control_tape(rows,np.zeros((2,4),int),dt=.00025,steps=400,
        lookup=np.tile(np.arange(500,2501),(5,1)),wheel_ids=[0,1,2,3],
        servo_ids=[[4],[5],[6],[7],[8]],start_fraction=.325,kinetic_fraction=1/12,torque_cap_nm=1.)
    assert np.array_equal(tape[:,:,4:9],np.asarray(expected).transpose(1,0,2))


def test_model_grouping_allows_only_free_joint_initial_pose_changes():
    from scripts.warp_act_core import model_key
    xml='<mujoco><worldbody><body pos="1 0 0"><freejoint/><geom size=".1"/></body><geom pos="1 2 3" size=".1"/></worldbody></mujoco>'
    assert model_key(xml)==model_key(xml.replace('body pos="1 0 0"','body pos="4 5 6"'))
    assert model_key(xml)!=model_key(xml.replace('geom pos="1 2 3"','geom pos="4 5 6"'))
    assert model_key(xml)!=model_key(xml.replace('size=".1"','size=".2"'))
