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
