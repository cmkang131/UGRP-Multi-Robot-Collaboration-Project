"""Hidden-event physics of the integrated zone study (PR #257 review P1-G, P1-H, P1-I).

``sim.zone_hidden_events`` realises the scenario's hidden events for the
physics owner. The actuator tests step REAL MuJoCo physics (``mj_step``) on a
toy model through the REAL ``sim.camera_robot_port.CameraRobotPort``: the toy
world mirrors ``MultiMasterPiProductionV2`` only where the fault acts (per-robot
``motor_command``/``motor_state``, gripper position actuators, the
``_physics_step_for`` entry point). The toy grip uses explicit ``<pair>``
contacts, like the study contact profile ``cargo_noslip_v1``. The scene test
builds the real world (render off, no physics step). The full-robot probe is
``scripts/probe_zone_hidden_events.py``.
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

mujoco = pytest.importorskip('mujoco')

from harness import zone_study_referee as zr  # noqa: E402
from harness.zone_study_contract import ROBOTS, ContractViolation  # noqa: E402
from sim import zone_hidden_events as zhe  # noqa: E402
from sim.camera_robot_port import CameraRobotPort  # noqa: E402
from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2  # noqa: E402

TOY = """<mujoco><option timestep=".002"/>
<worldbody><geom name="floor" type="plane" size="3 3 .1"/>
 <body name="r1__hand" pos="0 0 .2">
  <body pos="0 .03 0"><joint name="r1__left_gripper_close" type="slide" axis="0 -1 0" range="0 .02" limited="true" damping=".5"/>
   <geom name="r1__left_finger" type="box" size=".01 .005 .02" mass=".02"/></body>
  <body pos="0 -.03 0"><joint name="r1__right_gripper_close" type="slide" axis="0 1 0" range="0 .02" limited="true" damping=".5"/>
   <geom name="r1__right_finger" type="box" size=".01 .005 .02" mass=".02"/></body>
 </body>
 <body name="item_body" pos="0 0 .2"><freejoint/><geom name="item_body_geom" type="box" size=".015 .015 .015" mass=".03"/></body>
 <body name="r2__base" pos="1 0 .05"><joint name="r2__drive_x" type="slide" axis="1 0 0"/>
  <geom name="r2__chassis" type="box" size=".05 .05 .05" mass="1" contype="0" conaffinity="0"/></body>
</worldbody>
<actuator><position name="r1__servo_gripper_left" joint="r1__left_gripper_close" kp="40"/>
 <position name="r1__servo_gripper_right" joint="r1__right_gripper_close" kp="40"/></actuator>
<contact><pair geom1="item_body_geom" geom2="r1__left_finger" friction="1.5 1.5 .005 .0001 .0001"/>
 <pair geom1="item_body_geom" geom2="r1__right_finger" friction="1.5 1.5 .005 .0001 .0001"/></contact>
</mujoco>"""
CLOSED = 1500


class ToyRobot:
    """Just the controller surface the port and the fault touch (``NamespacedMasterPi`` names)."""

    def __init__(self, world, rid):
        m = world.model
        self.world, self.rid = world, rid
        self.motor_command, self.motor_state = np.zeros(4), np.zeros(4)
        act = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f'{rid}__servo_gripper_{s}') for s in ('left', 'right')]
        jnt = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{rid}__{s}_gripper_close') for s in ('left', 'right')]
        self.gripper_act, self.gripper_joint = tuple(a for a in act if a >= 0), tuple(j for j in jnt if j >= 0)
        self.servo_command_pulses = {1: 2000, 3: 1500, 4: 1500, 5: 1500, 6: 1500}

    def pulse_to_joint_targets(self, pose):
        return MasterPiDynamicsV2.pulse_to_joint_targets(self, pose)        # the real PWM -> jaw closure map

    def set_motor_commands(self, commands):
        self.motor_command[:] = np.clip(np.asarray(commands, float), -1, 1)

    def set_servo_pulses(self, pose, *, forward_only=False):
        self.servo_command_pulses.update({int(k): int(v) for k, v in pose.items()})
        if 1 in pose:
            for aid in self.gripper_act:
                self.world.data.ctrl[aid] = self.pulse_to_joint_targets({1: pose[1]})['gripper']


class ToyWorld:
    def __init__(self):
        self.model = mujoco.MjModel.from_xml_string(TOY)
        self.data = mujoco.MjData(self.model)
        self.controllers = {rid: ToyRobot(self, rid) for rid in ('r1', 'r2')}
        self.inside = []                                  # what each physics step actually used
        self._base = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, 'r2__base')
        self._vx = int(self.model.jnt_dofadr[self.model.body_jntadr[self._base]])

    def robot(self, rid):
        return self.controllers[rid]

    def render_jpeg(self, robot_id, camera):
        return b'toy-frame-' + robot_id.encode()

    def _physics_step_for(self, active, commands=None):
        d = self.data
        if commands is not None:
            active.motor_command[:] = commands
        for c in self.controllers.values():
            c.motor_state += .2 * (c.motor_command - c.motor_state)
        r2, r1 = self.controllers['r2'], self.controllers['r1']
        # masterpi_dynamics_v2 drive law in miniature: force from the wheel state,
        # a much stronger damping while the wheel command is zero
        damping = 5. if r2.motor_command.any() else 50.
        d.xfrc_applied[:] = 0
        d.xfrc_applied[self._base, 0] = 20. * float(np.mean(r2.motor_state)) - damping * float(d.qvel[self._vx])
        self.inside.append({'t': float(d.time), 'r2_command': r2.motor_command.copy(), 'r2_state': r2.motor_state.copy(),
                            'r1_grip_ctrl': [float(d.ctrl[a]) for a in r1.gripper_act]})
        mujoco.mj_step(self.model, d)


def gid(world, name):
    return mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_GEOM, name)


def rig(events=(), *, grip=False):
    """Toy world + real ports (+ hidden-event physics); ``grip``: r1 holds the item under gravity."""
    world = ToyWorld()
    ports = {rid: CameraRobotPort(world, rid, allow_reverse=True, allow_mecanum=True) for rid in ('r1', 'r2')}
    fingers = {r: ({gid(world, f'{r}__left_finger')}, {gid(world, f'{r}__right_finger')}) if r == 'r1' else (set(), set())
               for r in ROBOTS}
    hidden = zr.HiddenEventSchedule({'eval': {'hidden_events': list(events)}})
    physics = zhe.HiddenEventPhysics(world, hidden, objects={'it': {'kind': 'cyan', 'body_name': 'item_body'}},
                                     item_geoms={'it': {gid(world, 'item_body_geom')}}, finger_geoms=fingers) \
        if events else None
    rows = {rid: [] for rid in ports}
    if grip:
        gravity = world.model.opt.gravity.copy()
        world.model.opt.gravity[:] = 0                     # test setup only: close the jaws before the item falls
        issue(ports, rows, 'r1', {'kind': 'arm', 'servo_id': 1, 'pulse': CLOSED}, 0.)
        advance(world, ports, physics, .3)
        world.model.opt.gravity[:] = gravity
        advance(world, ports, physics, .6)
    return world, ports, physics, rows


def issue(ports, rows, rid, action, now):
    rows[rid].append({**action, 't': float(now)})         # the robot's own issued-command history
    ports[rid].apply(action, now)


def advance(world, ports, physics, until, *, every=None, sample=None):
    """Host-order stepping: hidden events -> port ticks -> one physics step (as ``OwnCamTeamHost``).

    ``sample(t)`` runs every ``every`` physics steps, at the step's SIM time rounded to 4 digits."""
    step = 0
    while float(world.data.time) < until - 1e-9:
        now = float(world.data.time)
        if physics is not None:
            physics.tick(now)
        if every is not None and step % every == 0:
            sample(round(now, 4))
        for port in ports.values():
            port.tick(now)
        world._physics_step_for(world.controllers['r1'])
        step += 1


def item_z(world):
    return float(world.data.body('item_body').xpos[2])


def ev_row(kind, target, at, event_id=None):
    return {'event_id': event_id or kind, 'kind': kind, 'trigger': {'kind': 'sim_time', 'at_sim_s': at}, 'target': target}


# ---------------------------------------------------------------- robot_hold (P1-I)
def test_robot_hold_blocks_the_wheels_at_the_actuator_and_leaves_the_issued_commands_unchanged():
    runs = {}
    for name, events in (('free', ()), ('held', [ev_row('robot_hold', {'robot_id': 'r2', 'duration_s': .3}, .1)])):
        world, ports, physics, rows = rig(events)
        drive = {'kind': 'drive', 'forward': .1, 'turn': 0., 'duration_s': 1.}
        issue(ports, rows, 'r2', drive, 0.)
        seen, xs = [], []

        def sample(now, ports=ports, world=world, seen=seen, xs=xs):
            obs = ports['r2'].capture()
            seen.append((now, obs['actuator_state'], obs['sha256']))
            xs.append((now, float(world.data.body('r2__base').xpos[0])))
        advance(world, ports, physics, .8 + 1e-6, every=25, sample=sample)      # every 0.05 s
        runs[name] = SimpleNamespace(world=world, rows=rows, seen=seen, x=dict(xs), physics=physics)
    free, held = runs['free'], runs['held']
    # What r2 itself can read of its issued commands is identical with and without the hold.
    assert held.seen == free.seen and held.rows == free.rows
    assert all(state['motor_commands'] == [.1] * 4 for _, state, _ in held.seen)
    assert list(held.world.controllers['r2'].motor_command) == [.1] * 4          # restored after every step
    # Inside the physics step the wheels got 0 during [0.1, 0.4) only.
    window = [r for r in held.world.inside if .1 - 1e-9 <= r['t'] < .4 - 1e-9]
    outside = [r for r in held.world.inside if r['t'] >= .4 + 1e-9]
    assert window and all(not r['r2_command'].any() and not r['r2_state'].any() for r in window)
    assert outside and all(list(r['r2_command']) == [.1] * 4 for r in outside)
    assert all(list(r['r2_command']) == [.1] * 4 for r in free.world.inside)
    # It really stands still while held and drives on afterwards.
    assert held.x[.4] - held.x[.1] < .1 * (free.x[.4] - free.x[.1])
    assert abs(held.x[.4] - held.x[.2]) < 5e-4 < free.x[.4] - free.x[.2]       # stands still once it has stopped
    assert held.x[.8] - held.x[.4] > 1e-2
    assert [(r['effect'], r['t']) for r in held.physics.log] == [('wheels_held', .1), ('wheels_released', .4)]
    assert '_physics_step_for' not in vars(free.world)


# ---------------------------------------------------------------- item_dropped (P1-H)
def test_item_dropped_opens_the_holders_gripper_actuator_so_the_item_really_falls():
    control, ctl_ports, _, ctl_rows = rig(grip=True)
    drop = [ev_row('item_dropped', {'item_id': 'it'}, 1.2, 'drop_1')]
    world, ports, physics, rows = rig(drop, grip=True)
    assert item_z(world) > .18 and item_z(control) > .18                   # held under gravity by contact only
    assert physics.holders('it') == ['r1']
    seen = {'control': [], 'fault': []}
    for key, w, p, ph in (('control', control, ctl_ports, None), ('fault', world, ports, physics)):
        advance(w, p, ph, 2.6, every=50, sample=lambda now, p=p, key=key: seen[key].append(
            (now, p['r1'].capture()['actuator_state'])))
    # The fault fell the item to the floor; without it the grip holds.
    assert item_z(control) > .18 and item_z(world) < .03
    assert physics.holders('it') == []
    # The robot's own command record and its commanded servo state are unchanged.
    assert seen['fault'] == seen['control'] and rows == ctl_rows
    assert world.controllers['r1'].servo_command_pulses == control.controllers['r1'].servo_command_pulses
    issued = control.data.ctrl[list(control.controllers['r1'].gripper_act)]
    assert list(world.data.ctrl[list(world.controllers['r1'].gripper_act)]) == list(issued)    # restored
    # The open target acted inside the physics step for GRIPPER_FAULT_S only.
    opened = [r for r in world.inside if 1.2 - 1e-9 <= r['t'] < 1.2 + zhe.GRIPPER_FAULT_S - 1e-9]
    after = [r for r in world.inside if r['t'] >= 1.2 + zhe.GRIPPER_FAULT_S + 1e-9]
    assert opened and all(v == 0. for r in opened for v in r['r1_grip_ctrl'])
    assert after and all(v == pytest.approx(float(issued[0])) for r in after for v in r['r1_grip_ctrl'])
    assert [r['effect'] for r in physics.log] == ['gripper_fault_open', 'gripper_fault_cleared']
    assert physics.log[0]['holders'] == ['r1'] and physics.log[0]['pwm'] == zhe.GRIPPER_FAULT_PULSE


def test_item_events_do_nothing_when_they_do_not_apply():
    world, ports, physics, _ = rig([ev_row('item_dropped', {'item_id': 'it'}, 0.)])
    # not held: no fault is armed
    assert physics.apply(ev_row('item_dropped', {'item_id': 'it'}, 0.), 0.)['effect'] == 'none_item_not_held'
    assert not physics.faults.grippers
    world, ports, physics, _ = rig([ev_row('item_dropped', {'item_id': 'it'}, 5.)], grip=True)
    out = physics.apply(ev_row('item_moved', {'item_id': 'it', 'to_pose_m': [1., 1., 0.]}, 5.), 5.)
    assert out == {'event_id': 'item_moved', 'kind': 'item_moved', 'at_sim_s': 5., 'effect': 'none_item_held',
                   'holders': ['r1']}


@pytest.mark.parametrize('duration', [0, -1., math.nan, math.inf, None, '2', True])
def test_robot_hold_refuses_a_bad_duration(duration):
    event = ev_row('robot_hold', {'robot_id': 'r2', 'duration_s': duration}, 0.)
    world, ports, physics, _ = rig([ev_row('robot_hold', {'robot_id': 'r2', 'duration_s': 1.}, 9.)])
    with pytest.raises(ContractViolation, match='robot_hold'):
        physics.apply(event, 0.)
    with pytest.raises(ContractViolation, match='robot_hold'):
        physics.apply(ev_row('robot_hold', {'robot_id': 'r9', 'duration_s': 1.}, 0.), 0.)
    assert not physics.faults.wheels


def test_a_world_step_is_wrapped_once_and_unknown_kinds_are_refused():
    world, _, physics, _ = rig([ev_row('robot_hold', {'robot_id': 'r2', 'duration_s': 1.}, 9.)])
    with pytest.raises(ContractViolation, match='already'):
        zhe.ActuatorFaults(world, [])
    with pytest.raises(ContractViolation, match='unsupported'):
        physics.apply({'event_id': 'x', 'kind': 'teleport', 'trigger': {'at_sim_s': 0.}, 'target': {'item_id': 'it'}}, 0.)
    with pytest.raises(ContractViolation, match='at least one'):
        zhe.obstacle_xml([])


# ---------------------------------------------------------------- scene (P1-G a)
OBSTACLE = {'obstacle_id': 'p1', 'center_m': [1., 1.], 'half_extents_m': [.1, .2], 'height_m': .12}


def study_spec():
    from scripts import run_zone_study_integration as runner
    pre = runner.load_prereg(ROOT / 'experiments/2026-09-26-zone-study-integration/prereg.json')
    _, scenario, map_bundle, _ = runner.run_bundle(pre, pre['episodes'][0])
    return runner.host_spec(scenario, pre['episodes'][0], map_bundle)


def world_for(scene, profile):
    """The world exactly as ``OwnCamTeamHost`` builds it (render off, no physics step)."""
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_cargo_contact import apply
    return MultiMasterPiProductionV2(seed=scene.scene['seed'], width=64, height=48, render=False,
                                     warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None,
                                     xml_transform=lambda xml: apply(scene.transform(xml), profile))


def canonical(xml, *, drop_hidden):
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    for body in list(world):
        if drop_hidden and body.tag == 'body' and body.get('name', '').startswith(zhe.HIDDEN_BODY_PREFIX):
            world.remove(body)
    return ET.canonicalize(ET.tostring(root, encoding='unicode'))


def test_hidden_obstacles_add_parked_bodies_and_change_nothing_else_in_the_scene():
    from sim.zone_own_scene_provider import own_scene
    spec = study_spec()
    profile = spec['contact_profile']
    base = own_scene(spec, profile, None)
    scene = zhe.hidden_event_scene(spec, profile, [OBSTACLE])
    assert type(base).__name__ == 'TaggedZoneScene' and type(scene).__name__ == 'TaggedCargoZoneScene'
    assert own_scene(spec, profile, scene) is scene                        # the host accepts it unchanged
    plain, hidden = world_for(base, profile), world_for(scene, profile)
    try:
        assert canonical(hidden.scene_xml, drop_hidden=True) == canonical(plain.scene_xml, drop_hidden=False)
        assert hidden.model.nbody == plain.model.nbody + 1 and hidden.model.ngeom == plain.model.ngeom + 1
        schedule = zr.HiddenEventSchedule({'eval': {'hidden_events': [
            ev_row('passage_blocked', {'passage': 'door_x', 'obstacle': OBSTACLE}, 1.),
            ev_row('passage_cleared', {'passage': 'door_x'}, 2.)]}})
        physics = zhe.HiddenEventPhysics(hidden, schedule, objects={}, item_geoms={},
                                         finger_geoms={r: (set(), set()) for r in ROBOTS})
        assert physics.faults is None and '_physics_step_for' not in vars(hidden)
        body = hidden.data.body(zhe.HIDDEN_BODY_PREFIX + 'p1')
        assert float(body.xpos[2]) == zhe.PARK_Z_M
        physics.tick(1.)
        assert list(hidden.data.body(zhe.HIDDEN_BODY_PREFIX + 'p1').xpos) == pytest.approx([1., 1., .06])
        physics.tick(2.)
        assert float(hidden.data.body(zhe.HIDDEN_BODY_PREFIX + 'p1').xpos[2]) == zhe.PARK_Z_M
        assert [r['effect'] for r in physics.log] == ['obstacle_moved', 'obstacle_moved']
        with pytest.raises(ContractViolation, match='not in the scene'):
            physics.apply(ev_row('obstruction_added', {'obstacle': {**OBSTACLE, 'obstacle_id': 'nope'}}, 3.), 3.)
    finally:
        plain.close()
        hidden.close()


def test_final_geometry_scene_is_wrapped_in_place_and_other_classes_are_refused():
    from sim.zone_geometry_scene import GeometryCargoZoneScene
    from sim.zone_own_scene_provider import own_scene
    spec = {**study_spec(), 'map': 'zone_wide_door_geometry_v2'}
    original = GeometryCargoZoneScene.transform
    scene = zhe.hidden_event_scene(spec, spec['contact_profile'], [OBSTACLE])
    assert type(scene) is GeometryCargoZoneScene and own_scene(spec, spec['contact_profile'], scene) is scene
    assert 'transform' in vars(scene) and GeometryCargoZoneScene.transform is original    # this instance only
    with pytest.raises(ContractViolation, match='unsupported scene class'):
        zhe._cargo_free_twin(SimpleNamespace())


def test_study_host_builds_no_hidden_physics_and_passes_the_same_scene_without_events(monkeypatch):
    from harness import zone_own_executor as zox
    from scripts import run_zone_study_integration as runner
    seen = []

    def init_host(host, spec, student, **kwargs):
        seen.append(kwargs['scene'])
        host.static, host.eval_only, host.world = {}, {}, SimpleNamespace()
        host.robots = {rid: SimpleNamespace(port=SimpleNamespace(capture=lambda camera: None)) for rid in ROBOTS}
    monkeypatch.setattr(zox.OwnCamTeamHost, '__init__', init_host)
    monkeypatch.setattr(runner, 'evaluation_top_config', lambda static: {'profile': {'id': 'x'}})
    monkeypatch.setattr(runner.zone_eval_top, 'eval_static_map', lambda *a: {})
    monkeypatch.setattr(runner.zone_eval_top, 'apply_to_world', lambda *a: {})
    host = runner.StudyTeamHost({'pair_order_sheets': {}}, {}, root=ROOT, provider_spec={})
    assert seen == [None] and host.hidden_physics is None and host.hidden_log == []
    host.hidden_tick(5.)                                                    # a no-op without events
