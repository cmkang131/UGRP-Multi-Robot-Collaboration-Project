"""T04 synthetic/offline tests. No renderer, host, contact or model provider.

Reference masks below are analytic labelled drawings, not simulated evidence.
The positive trajectory exercises real perception, IK and command/state logic.
"""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import pytest

from harness import visual_arm_v3 as arm
from harness import wrist_can as vision
from harness.can_skill_registry import CAN, CONDITIONS, REGISTRY, create_skill, profile_record
from harness.owncam_pose_source import OwnCamPoseSource, PoseReport
from harness.zone_can_skill import CanSkill, VIEWS
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT / 'maps/zones/zone_wide_door_geometry_v3.json').read_text())
VIOLET = cv2.cvtColor(np.uint8([[[132, 190, 210]]]), cv2.COLOR_HSV2BGR)[0, 0]


def reference_frame(pulses, *, xy=(.2, 0.), held=False, hue=132, height=.05, shape='cylinder'):
    """Independent labelled projection; does not call production can perception.

    96 vertices instead of its 64. Poses/dimensions are literal fixture labels,
    so changing the production cylinder/profile changes the tests' observations.
    """
    x, y = xy
    bottom = 0.
    if held:
        x, y, pad_z = arm.forward_grip(pulses)
        bottom = pad_z - .024
    angles = np.linspace(0, 2*math.pi, 96, endpoint=False)
    if shape == 'box':
        ring = [(x+dx, y+dy) for dx in (-.019, .019) for dy in (-.019, .019)]
    else:
        ring = [(x+.019*math.cos(t), y+.019*math.sin(t)) for t in angles]
    # The held fixture labels ONLY the camera-visible lower rim, never a whole
    # cylinder placed in an impossible gripper ROI.
    points = np.array([(a, b, z) for z in ([bottom] if held else [bottom, bottom+height]) for a, b in ring])
    if shape == 'lying_can':
        points = np.column_stack((x + points[:, 2] - .025, points[:, 1],
                                  .019 + points[:, 0] - x))
    origin, axes = arm.camera_extrinsics(pulses)
    camera_points = (points-origin) @ np.linalg.inv(axes)
    assert (camera_points[:, 2] > 0).all(), 'fixture behind camera'
    pixels = cv2.fisheye.distortPoints(
        (camera_points[:, :2] / camera_points[:, 2, None]).reshape(-1, 1, 2),
        scaled_camera_matrix(640, 480), np.array(CAMERA_FISHEYE_D).reshape(4, 1)).reshape(-1, 2)
    frame = np.full((480, 640, 3), 80, np.uint8)
    colour = cv2.cvtColor(np.uint8([[[hue, 190, 210]]]), cv2.COLOR_HSV2BGR)[0, 0]
    cv2.fillConvexPoly(frame, cv2.convexHull(pixels.astype(np.float32)).astype(np.int32), colour.tolist())
    return frame


def observation(frame, fid=1, now=1., rid='r1', **extras):
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 97])
    assert ok
    raw = buf.tobytes()
    return {'robot_id': rid, 'camera': 'robot_cam', 'frame_id': fid, 'sim_time': now,
            'image': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest(), **extras}


def pose(now, *, xy=(-.4, -.85), yaw=0., **kw):
    return PoseReport(t_est=now, initialized=True, x_m=xy[0], y_m=xy[1], yaw_rad=yaw,
                      std_xy_m=.002, std_yaw_rad=.002, source='owncam_pf_v2:fake-offline', **kw)


class FakeOwnPose(OwnCamPoseSource):
    """A registered provider stand-in; records exactly the own inputs it receives."""
    def __init__(self):
        self.source = 'owncam_pf_v2:fake-offline'
        self.next_report = None
        self.commands = []
        self.frames = []

    def on_command(self, row):
        self.commands.append(copy.deepcopy(row))

    def on_frame(self, now, rgb):
        self.frames.append(rgb.copy())
        return self.next_report or pose(now)


def decide(skill, now, obs, report=None):
    skill.pose.next_report = report
    return skill.step(now, obs)


def make(condition='no_comm', *, rid='r1'):
    return create_skill('can', role='any', condition=condition, robot_id=rid,
                        static_map=MAP, destination_zone='C', pose_source=FakeOwnPose())


class FakePort:
    def __init__(self, skill=None):
        self.skill = skill or make()
        self.t, self.fid = 0., 0
        self.xy = (-.4, -.85)
        self.skill.on_command({'robot_id': self.skill.robot_id, 't': 0., 'kind': 'initial_servo_command',
                               'pulses': dict(VIEWS[0])})
        self.trace = []

    def tick(self, frame=None, **extra):
        self.t = round(self.t + .2, 3)
        self.fid += 1
        skill = self.skill
        if frame is None:
            if skill.phase == 'approach':
                # Fixed, labelled observations; no dynamics or achievement model.
                frame = reference_frame(VIEWS[skill.view_index], xy=((.30, .25, .20)[skill.view_index], 0.))
            elif skill.phase in ('lift_first', 'lift_second', 'holding'):
                frame = reference_frame(skill.servo, held=True)
            elif skill.phase == 'release_look':
                frame = reference_frame(VIEWS[2])
            else:
                frame = np.full((480, 640, 3), 80, np.uint8)
        obs = observation(frame, self.fid, self.t, skill.robot_id, **extra)
        out = decide(skill, self.t, obs, pose(self.t, xy=self.xy))
        self.trace.append(out)
        for command in out['commands']:
            skill.on_command({'t': self.t, 'robot_id': skill.robot_id, **command})
        return out

    def until(self, phase, *, frame=None):
        for _ in range(350):
            out = self.tick(frame)
            if self.skill.phase in (phase, 'failed'):
                break
        assert self.skill.phase == phase, (self.skill.phase, self.skill.reason)
        return out


def test_catalogue_kind_geometry_height_role_and_new_registry():
    from sim.zone_cargo import CATALOGUE
    cargo = CATALOGUE['can']
    assert CAN.kind == 'can' and CAN.role == cargo.grasps[0].role == 'any'
    assert CAN.diameter_m == cargo.parts[0].size[0]*2 == .038
    assert CAN.height_m == cargo.parts[0].size[1]*2 == .050
    assert CAN.mass_kg == cargo.mass_kg == .080
    assert CAN.grasp_height_m == cargo.grasps[0].grip_xyz[2] == .024
    assert CAN.grasp_forward_m == .200
    assert CAN.lift_heights_m == (.080, .100)
    with pytest.raises(ValueError, match='envelope'):
        arm.solve_grip_site_ik((.155, 0, CAN.grasp_height_m))
    assert REGISTRY['can'] is CAN and len(profile_record()['sha256']) == 64
    with pytest.raises(TypeError):
        REGISTRY['red'] = CAN


def test_pose_provider_receives_only_decoded_own_rgb_and_own_history():
    port = FakePort()
    raw = reference_frame(VIEWS[0], xy=(.4, 0.))
    port.tick(raw, actuator_state={'qpos':[999], 'servo_pulses':{'3':500}},
              peer_rgb='forbidden')
    expected = vision.decode_own(observation(raw, 1, .2), robot_id='r1', previous_frame_id=None, now=.2)
    assert np.array_equal(port.skill.pose.frames[0], expected[..., ::-1])
    assert port.skill.pose.commands[0]['pulses'] == VIEWS[0]
    assert all(row['robot_id'] == 'r1' for row in port.skill.pose.commands)
    with pytest.raises(TypeError):
        port.skill.step(.4, observation(raw, 2, .4), pose(.4))  # external pose channel absent
    class PretendOwnProvider:
        source = 'owncam_pf_v2:spoof'
    with pytest.raises(ValueError, match='registered'):
        CanSkill('r1', MAP, destination_zone='C', pose_source=PretendOwnProvider())


@pytest.mark.parametrize('kind,role,condition', [('red', 'any', 'no_comm'), ('tile', 'any', 'no_comm'),
                                                ('can', 'west', 'no_comm'), ('can', 'any', 'unknown')])
def test_factory_fails_closed(kind, role, condition):
    with pytest.raises(ValueError):
        create_skill(kind, role=role, condition=condition, robot_id='r1', static_map=MAP, destination_zone='C', pose_source=FakeOwnPose())


@pytest.mark.parametrize('x,y,view', [(.4, 0, 0), (.35, .04, 0), (.3, -.03, 1), (.2, 0, 2)])
def test_cylinder_center_from_own_jpeg(x, y, view):
    obs = observation(reference_frame(VIEWS[view], xy=(x, y)))
    frame = vision.decode_own(obs, robot_id='r1', previous_frame_id=None, now=1.)
    found = vision.floor_can(frame, VIEWS[view])
    assert found.answer == 'yes', found
    assert found.center_base_m == pytest.approx((x, y, .025), abs=.003)
    assert found.source.startswith('own_robot_cam_jpeg')


@pytest.mark.parametrize('fault', ['occlusion', 'floor', 'flat_disc', 'black', 'wrong_kind', 'box', 'lying_can', 'two', 'clipped'])
def test_wrong_or_ambiguous_floor_never_approaches_as_a_can(fault):
    p = VIEWS[0]
    frame = reference_frame(p, xy=(.4, 0.))
    if fault == 'occlusion':
        frame[130:155, 270:320] = 80
    elif fault == 'floor':
        frame[:] = VIOLET
    elif fault == 'flat_disc':
        frame = reference_frame(p, xy=(.4, 0.), height=0.)
    elif fault == 'black':
        frame[:] = 0
    elif fault == 'wrong_kind':
        frame = reference_frame(p, xy=(.4, 0.), hue=164)
    elif fault == 'box':
        frame = reference_frame(p, xy=(.4, 0.), shape='box')
    elif fault == 'lying_can':
        frame = reference_frame(p, xy=(.4, 0.), shape='lying_can')
    elif fault == 'two':
        other = reference_frame(p, xy=(.4, .075))
        frame[np.any(other != 80, axis=2)] = other[np.any(other != 80, axis=2)]
    else:
        frame = reference_frame(p, xy=(.20, 0.))
    assert vision.floor_can(frame, p).answer == 'unknown'
    port = FakePort()
    for _ in range(5):
        out = port.tick(frame)
    assert out['phase'] == 'approach'
    assert not any(c['kind'] == 'mecanum' for c in out['commands'])


@pytest.mark.parametrize('height', [.08, .10])
def test_holding_rim_is_can_specific_at_both_lift_heights(height):
    p = {1:1500, **arm.solve_grip_site_ik((.2, 0, height), preferred_pitch_deg=-66)}
    good = reference_frame(p, held=True)
    assert vision.attached_can(good, p).answer == 'yes'
    for bad in (np.full_like(good, 80), np.zeros_like(good),
                reference_frame(p, held=True, hue=90), reference_frame(p, xy=(.4, 0.))):
        assert vision.attached_can(bad, p).answer == 'unknown'
    assert vision.attached_can(good, {**p, 1:2000}).answer == 'unknown'
    assert vision.attached_can(good, {1:1500, 3:777, 4:2053, 5:1646, 6:1500}).answer == 'unknown'


def test_actual_state_machine_approach_grasp_two_lifts_and_release():
    port = FakePort()
    port.until('holding')
    assert [r['phase'] for r in port.skill.log] == ['lower', 'close', 'lift_first', 'lift_second', 'holding']
    arm_commands = [c for r in port.trace for c in r['commands'] if c['kind'] == 'arm']
    assert any(c['servo_id'] == 1 and c['pulse'] == 1500 for c in arm_commands)
    assert port.skill.servo == {1:1500, **arm.solve_grip_site_ik((.2, 0, .1), preferred_pitch_deg=-66)}
    # Stub own navigation estimate, explicitly outside this local skill's tests.
    port.xy = (2.8, -.85)
    port.skill.request_release()
    out = port.until('released_visual')
    assert out['release_visual'] and out['delivery_success'] is None
    assert port.skill.servo[1] == 2000
    assert port.tick()['commands'] == [{'kind':'hold'}]


def test_ungrasped_and_empty_gripper_never_reach_holding_or_release():
    port = FakePort()
    port.until('lift_first')
    empty = np.full((480, 640, 3), 80, np.uint8)
    port.until('failed', frame=empty)
    assert port.skill.reason == 'phase_timeout'
    assert not any(r['holding'] == 'yes' or r['release_visual'] for r in port.trace)
    with pytest.raises(ValueError):
        port.skill.request_release()
    assert port.skill.servo[1] == 1500  # uncertain elevated load is not automatically opened


def test_bad_release_views_cannot_turn_open_gripper_into_completion():
    port = FakePort()
    port.until('holding')
    port.xy = (2.8, -.85)
    port.skill.request_release()
    port.until('release_look')
    port.until('failed', frame=np.full((480, 640, 3), 80, np.uint8))
    assert not any(r['release_visual'] for r in port.trace)


def test_release_intent_requires_fresh_own_pose_in_destination():
    port = FakePort()
    port.until('holding')
    port.skill.request_release()
    assert port.tick()['phase'] == 'failed'
    assert port.skill.reason == 'release_outside_public_zone'
    assert port.skill.servo[1] == 1500


@pytest.mark.parametrize('yaw', [0, math.pi/2, math.pi, -math.pi/2])
def test_any_role_has_no_world_west_heading_restriction(yaw):
    skill = make()
    skill.on_command({'robot_id':'r1', 't':0., 'kind':'initial_servo_command', 'pulses':dict(VIEWS[0])})
    obs = observation(reference_frame(VIEWS[0], xy=(.4, .03)))
    out = decide(skill, 1., obs, pose(1., yaw=yaw))
    command = out['commands'][0]
    assert command['kind'] == 'mecanum'
    assert command['forward'] > 0 and command['left'] > 0
    assert command['duration_s'] == .1 and command['turn'] == 0


@pytest.mark.parametrize('fault', ['other_robot', 'top', 'hash', 'future', 'stale', 'nan', 'bool_id',
                                  'bad_image', 'wrong_size', 'pose_gt', 'pose_stale', 'pose_uncertain'])
def test_input_and_pose_refusal(fault):
    skill = make()
    skill.on_command({'robot_id':'r1', 't':0., 'kind':'initial_servo_command', 'pulses':dict(VIEWS[0])})
    obs = observation(reference_frame(VIEWS[0], xy=(.4, 0.)))
    rep = pose(1.)
    if fault == 'other_robot': obs['robot_id'] = 'r2'
    elif fault == 'top': obs['camera'] = 'cctv_top'
    elif fault == 'hash': obs['sha256'] = '0'*64
    elif fault == 'future': obs['sim_time'] = 1.1
    elif fault == 'stale': obs['sim_time'] = .74
    elif fault == 'nan': obs['sim_time'] = float('nan')
    elif fault == 'bool_id': obs['frame_id'] = True
    elif fault == 'bad_image':
        obs['image'] = base64.b64encode(b'bad JPEG').decode()
        obs['sha256'] = hashlib.sha256(b'bad JPEG').hexdigest()
    elif fault == 'wrong_size': obs = observation(np.zeros((24,32,3), np.uint8))
    elif fault == 'pose_gt': rep = replace(rep, source='gt_stub_eval_only')
    elif fault == 'pose_stale': rep = replace(rep, t_est=.7)
    else: rep = replace(rep, std_xy_m=.03)
    out = decide(skill, 1., obs, rep)
    assert out['phase'] == 'failed' and out['commands'] == [{'kind':'hold'}]


def test_repeated_frame_and_unacknowledged_commands_do_not_advance():
    port = FakePort()
    port.tick()
    obs = observation(reference_frame(VIEWS[0], xy=(.4, 0)), fid=1, now=.4)
    assert decide(port.skill, .4, obs, pose(.4))['phase'] == 'failed'
    skill = make()
    out = decide(skill, 1., observation(reference_frame(VIEWS[0])), pose(1.))
    assert out['phase'] == 'failed'  # own initial PWM log required


def test_pose_or_own_base_command_change_invalidates_pending_grasp():
    port = FakePort()
    port.until('lower')
    port.xy = (-.37, -.85)
    assert port.tick()['reason'] == 'own_pose_shifted_during_manipulation'
    port = FakePort()
    port.until('lower')
    with pytest.raises(ValueError, match='base_moved'):
        port.skill.on_command({'robot_id':'r1', 't':port.t, 'kind':'mecanum',
                               'forward':.02, 'left':0., 'turn':0., 'duration_s':.1})
    assert port.skill.phase == 'failed'


def test_bad_own_command_stops_the_controller():
    port = FakePort()
    with pytest.raises(ValueError):
        port.skill.on_command({'robot_id':'r1', 't':1., 'kind':'arm', 'servo_id':3, 'pulse':True})
    assert port.skill.phase == 'failed'


def test_release_floor_zone_margin_and_refusal_are_geometry_not_heading():
    skill = make()
    from harness.zone_own_guards import OwnPose
    # All headings can release into C when the own estimated pad is inside it.
    for yaw in (0., math.pi/2, math.pi, -math.pi/2):
        own = OwnPose(3.-.2*math.cos(yaw), -.85-.2*math.sin(yaw), yaw, .002, .002)
        assert skill._zone_contains(own, (.2, 0.))
    assert not skill._zone_contains(OwnPose(2.51, -.85, 0., .002, .002), (.2, 0.))


def test_private_changes_and_all_four_conditions_leave_commands_equal():
    traces = []
    for condition in CONDITIONS:
        port = FakePort(make(condition))
        for _ in range(8):
            port.tick(reference_frame(VIEWS[0], xy=(.4, 0.)),
                      eval_only={'qpos':[len(traces),999], 'held':bool(len(traces)%2)},
                      setup_manifest={'item_id':'secret-'+condition},
                      peer={'x_m':999*len(traces)}, event_time=-500*len(traces))
        traces.append(port.trace)
    assert all(t == traces[0] for t in traces)
    assert all(type(make(c)) is CanSkill for c in CONDITIONS)


def test_ci_collects_can_tests_without_ci_configuration_changes():
    from scripts.run_ci_tests import TEST_PATTERNS
    import fnmatch
    assert any(fnmatch.fnmatch('tests/test_zone_own_executor_can.py', p) for p in TEST_PATTERNS)


def test_static_collision_and_sim_cap_stop_commands():
    skill = make()
    skill.on_command({'robot_id':'r1', 't':0., 'kind':'initial_servo_command', 'pulses':dict(VIEWS[0])})
    obs = observation(reference_frame(VIEWS[0], xy=(.4, 0)))
    assert decide(skill, 1., obs, pose(1., xy=(2.15, -.85)))['phase'] == 'failed'
    port = FakePort()
    port.tick()
    out = port.skill.step(900.2, {})
    assert out['reason'] == 'local_sim_cap' and out['commands'] == [{'kind':'hold'}]


def test_legacy_box_api_unchanged_and_can_not_silently_dispatched_as_box():
    from harness.zone_color_boxes import KINDS, detect_own
    from harness.m1_owncam_delivery import M1OwnCamDelivery
    assert KINDS == ('cyan', 'green', 'red', 'yellow')
    for kind in KINDS:
        assert detect_own(np.zeros((480,640,3), np.uint8), VIEWS[0], kinds=(kind,))['detections'] == []
    with pytest.raises(ValueError, match='unknown box kind'):
        detect_own(np.zeros((480,640,3), np.uint8), VIEWS[0], kinds=('can',))
    with pytest.raises(ValueError, match='cyan'):
        M1OwnCamDelivery(MAP, {}, box_kind='can', slot_id='C2', slot_xy=(3.,-.85),
                         skill_factory=None, pose_estimate_cls=None, search_rows_y=())


def test_runtime_does_not_import_a_simulator_or_t03():
    code = """
import sys
sys.modules['mujoco'] = None
from harness.can_skill_registry import create_skill
from harness.zone_can_skill import CanSkill
from tests.test_zone_own_executor_can import FakePort
port = FakePort()
port.tick()
assert 'harness.m1_color_delivery' not in sys.modules
assert 'sim.zone_cargo' not in sys.modules
assert 'sim.zone_arena' not in sys.modules
assert 'harness.zone_own_team_host' not in sys.modules
"""
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
