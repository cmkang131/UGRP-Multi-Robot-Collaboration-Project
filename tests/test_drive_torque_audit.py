"""Force decomposition sanity on known independent hinges, no integration."""
from types import SimpleNamespace
import numpy as np
import pytest
mujoco=pytest.importorskip('mujoco')
from scripts.drive_torque_audit import snapshot


def test_friction_projection_and_motor_units():
    bodies=''.join(f'<body pos="{i} 0 0"><joint name="r1__wheel_{w}_joint" type="hinge" frictionloss=".04"/><geom type="sphere" size=".1" contype="0" conaffinity="0"/></body>' for i,w in enumerate(('fl','fr','rl','rr')))
    acts=''.join(f'<motor joint="r1__wheel_{w}_joint" gear="1"/>' for w in ('fl','fr','rl','rr'))
    m=mujoco.MjModel.from_xml_string(f'<mujoco><worldbody>{bodies}</worldbody><actuator>{acts}</actuator></mujoco>')
    d=mujoco.MjData(m); d.ctrl[:]=[.02,-.03,.035,-.05]
    mujoco.mj_forward(m,d)
    r=snapshot(m,d,SimpleNamespace(robot_id='r1',wheel_act=np.arange(4)),d.qvel.copy(),0.)
    assert r['actuator_generalized_nm']==pytest.approx(d.ctrl)
    friction=np.array(r['constraint_terms_nm']['mjCNSTR_FRICTION_DOF'])
    assert np.all(friction*d.ctrl<=0)
    assert len(r['friction_rows'])==4
    assert r['constraint_projection_error'] < 1e-12
    assert r['wheel_balance_error_nm'] < 1e-12
