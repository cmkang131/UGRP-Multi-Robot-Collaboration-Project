import xml.etree.ElementTree as ET
from types import SimpleNamespace
from contextlib import nullcontext
import numpy as np
import pytest
mujoco=pytest.importorskip('mujoco')
from sim.masterpi_drive_friction_v7 import DriveParameters, HysteresisWorld, transform_xml
from sim.masterpi_drive_friction_v6 import transform_xml as v6_xml
from sim.masterpi_drive_friction import FrictionWorld
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


def test_signed_input_hysteresis_start_hold_release_reverse():
    p=DriveParameters(); state=np.zeros(4,dtype=int)
    torque,state=p.command_step([.2,.3,.325,-.325],state)
    assert np.array_equal(state,[0,0,0,0]);assert not torque.any()
    torque,state=p.command_step([.35,-.35,.5,-1],state)
    assert state.tolist()==[1,-1,1,-1]
    assert torque==pytest.approx(np.array([.35,-.35,.5,-1])-state/12)
    torque,state=p.command_step([.3,-.3,-.2,0],state)
    assert state.tolist()==[1,-1,0,0]  # lower command holds only in same direction
    torque,state=p.command_step([1/12,-1/12,-.35,0],state)
    assert state.tolist()==[0,0,-1,0]
    with pytest.raises(ValueError):p.command_step([np.nan],np.zeros(1))


def test_source_derived_motor_curve_and_geometry():
    p=DriveParameters();assert p.kinetic_fraction==pytest.approx(1/12)
    assert p.kinetic_torque_nm==pytest.approx(.00980665)
    xml=v3_robot_xml_transform({})(build_multi_robot_xml({}))
    a,b=ET.fromstring(v6_xml(xml,p)),ET.fromstring(transform_xml(xml,p))
    b.find("custom/text[@name='drive_profile']").set('data','masterpi_drive_friction_v6')
    assert ET.tostring(a)==ET.tostring(b)
    m=mujoco.MjModel.from_xml_string(transform_xml(xml,p));d=mujoco.MjData(m)
    aid=m.actuator('r1__wheel_fl_drive').id;dof=m.jnt_dofadr[m.joint('r1__wheel_fl_joint').id]
    u,state=p.command_step(np.array([1.]),np.zeros(1,dtype=int))
    d.ctrl[aid]=p.torque_cap_nm*u[0];d.qvel[dof]=p.omega;mujoco.mj_forward(m,d)
    assert d.qfrc_actuator[dof]+d.qfrc_passive[dof]==pytest.approx(0.,abs=1e-12)
    assert m.dof_frictionloss[dof]==0


def test_runtime_state_is_input_only_and_reset_clears(monkeypatch):
    p=DriveParameters();world=HysteresisWorld.__new__(HysteresisWorld)
    world.drive_parameters=p;world.physics_lock=nullcontext();world.model=None
    world.data=SimpleNamespace(ctrl=np.zeros(4))  # no qvel/contact/ground-truth input exists
    c=SimpleNamespace(wheel_act=np.arange(4),motor_state=np.zeros(4),motor_command=np.array([.35,-.35,.3,0]))
    world.controllers={'r1':c};monkeypatch.setattr(mujoco,'mj_step',lambda *_:None)
    world._physics_step_for(c)
    assert world.drive_input_state['r1'].tolist()==[1,-1,0,0]
    assert world.data.ctrl==pytest.approx(p.torque_cap_nm*np.array([.35-1/12,-.35+1/12,0,0]))
    monkeypatch.setattr(FrictionWorld,'reset',lambda *_a,**_k:'reset')
    assert world.reset()=='reset';assert world.drive_input_state=={}


def test_diagnostic_failure_gate_uses_predeclared_limits():
    from scripts.probe_masterpi_drive_friction import evaluate_criterion
    r={'status':'MEASURED_DEV','case':'forward','wheel_input':30,'peak_command_com_xy_m':.002}
    assert evaluate_criterion(r)['passed'] is False
    r.update(wheel_input=35,tail_forward_min_mps=.002)
    assert evaluate_criterion(r)['passed'] is True
    r.update(case='left',tail_lateral_min_mps=.1,yaw_change_rad=np.deg2rad(2))
    assert evaluate_criterion(r)['passed'] is False
