from contextlib import nullcontext
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pytest

mujoco = pytest.importorskip('mujoco')
from sim import masterpi_drive_friction_v7 as v7
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform


@pytest.fixture(scope='module')
def base_xml():
    return v3_robot_xml_transform({})(build_multi_robot_xml({}))


def test_off_is_the_default_and_leaves_xml_unchanged(base_xml):
    p = v7.DriveParameters()
    assert v7.transform_xml(base_xml, p) == v7.transform_xml(base_xml, p, 'mesh', 'off')
    assert 'sleep' not in v7.transform_xml(base_xml, p)
    assert v7.HysteresisWorld.idle_robot_contacts == 'off'
    assert v7.option_record('mesh', 'off') == {}
    with pytest.raises(ValueError):
        v7.transform_xml(base_xml, p, 'mesh', 'always')


def test_freeze_xml_enables_sleeping_for_robots_only(base_xml):
    xml = v7.transform_xml(base_xml, v7.DriveParameters(), 'mesh', 'freeze_v1')
    root = ET.fromstring(xml)
    assert root.find('option/flag').get('sleep') == 'enable'
    assert root.find("custom/text[@name='idle_robot_contacts']").get('data') == 'freeze_v1'
    robots = [b for b in root.findall('worldbody/body') if b.get('name').endswith('__robot')]
    others = [b for b in root.findall('worldbody/body')
              if b.get('name') and not b.get('name').endswith('__robot')
              and (b.find('freejoint') is not None or any(j.get('type') == 'free' for j in b.findall('joint')))]
    assert len(robots) == 3 and all(b.get('sleep') == 'allowed' for b in robots)
    assert others and all(b.get('sleep') == 'never' for b in others)
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.opt.enableflags & mujoco.mjtEnableBit.mjENBL_SLEEP
    def policy(body):
        return int(model.tree_sleep_policy[model.body_treeid[model.body(body.get('name')).id]])
    assert all(policy(b) == mujoco.mjtSleepPolicy.mjSLEEP_ALLOWED for b in robots)
    assert all(policy(b) == mujoco.mjtSleepPolicy.mjSLEEP_NEVER for b in others)


def test_freeze_composes_with_sphere6(base_xml):
    xml = v7.transform_xml(base_xml, v7.DriveParameters(), 'sphere6_v1', 'freeze_v1')
    root = ET.fromstring(xml)
    assert root.find("custom/text[@name='roller_collision']") is not None
    assert root.find("custom/text[@name='idle_robot_contacts']") is not None
    mujoco.MjModel.from_xml_string(xml)


def test_option_record_documents_method_and_caveat():
    r = v7.option_record('mesh', 'freeze_v1')
    assert r['idle_robot_contacts'] == 'freeze_v1'
    assert 'sleeping-islands' in r['idle_robot_contacts_source']
    assert 'contact-based readouts are empty' in r['idle_robot_contacts_caveat']
    assert 'roller_collision' not in r


def make_world(tree_asleep, ctrl, mode='freeze_v1'):
    model = SimpleNamespace(
        body_treeid=np.array([0, 1, 1, 1]), jnt_bodyid=np.array([2, 3]),
        actuator_trnid=np.array([[0, 0], [1, 0]]), actuator_trntype=np.array([mujoco.mjtTrn.mjTRN_JOINT]*2))
    data = SimpleNamespace(ctrl=np.array(ctrl, dtype=float), tree_asleep=np.array(tree_asleep),
                           qfrc_applied=np.zeros(8))
    world = v7.HysteresisWorld.__new__(v7.HysteresisWorld)
    world.drive_parameters = SimpleNamespace(
        torque_cap_nm=1., command_step=lambda command, previous: (np.asarray(command, dtype=float), np.zeros(1, dtype=int)))
    world.physics_lock = nullcontext()
    world.model, world.data = model, data
    world.idle_robot_contacts = mode
    wheel = np.array([0])
    controller = SimpleNamespace(wheel_act=wheel, motor_state=np.zeros(1), motor_command=np.zeros(1),
                                 robot_bid=1, base_dadr=4, _presentation_dirty=False)
    controller.set_motor_commands = lambda value: controller.motor_command.__setitem__(slice(None), value)
    world.controllers = {'r1': controller}
    return world, controller


def test_sleeping_robot_is_woken_on_a_command_and_the_wake_mark_is_cleared(monkeypatch):
    world, c = make_world([-1, 7], [0., 0.])
    seen = []
    monkeypatch.setattr(mujoco, 'mj_step', lambda m, d: seen.append(d.qfrc_applied[4].copy()))
    world._physics_step_for(c, np.array([0.]))   # first call records ctrl; sleeping robot, no command: it may wake once
    seen.clear(); world.data.qfrc_applied[:] = 0.
    world._physics_step_for(c, np.array([0.]))   # unchanged ctrl, zero command: stays asleep
    assert seen == [0.] and not np.signbit(seen[0])
    seen.clear()
    world._physics_step_for(c, np.array([.5]))   # command: wake mark is -0.0 during the step
    assert len(seen) == 1 and seen[0] == 0. and np.signbit(seen[0])
    assert not np.signbit(world.data.qfrc_applied[4])   # restored to +0.0 afterwards


def test_arm_ctrl_change_wakes_and_awake_robot_is_untouched(monkeypatch):
    world, c = make_world([7, 7], [0., 0.])
    marks = []
    monkeypatch.setattr(mujoco, 'mj_step', lambda m, d: marks.append(bool(np.signbit(d.qfrc_applied[4]))))
    world._physics_step_for(c, np.array([0.]))
    marks.clear()
    world.data.ctrl[1] = .3                       # servo target changed
    world._physics_step_for(c, np.array([0.]))
    assert marks == [True]
    world.data.tree_asleep[1] = -1                # already awake: nothing is written
    world.data.ctrl[1] = .4
    marks.clear()
    world._physics_step_for(c, np.array([0.]))
    assert marks == [False]


def test_off_mode_never_touches_sleep_state(monkeypatch):
    world, c = make_world([7, 7], [0., 0.], mode='off')
    marks = []
    monkeypatch.setattr(mujoco, 'mj_step', lambda m, d: marks.append(bool(np.signbit(d.qfrc_applied[4]))))
    world._physics_step_for(c, np.array([.5]))
    assert marks == [False] and not hasattr(world, '_freeze_state')
