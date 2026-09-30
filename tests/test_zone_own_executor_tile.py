"""T05 offline only. Synthetic image/port fixtures; no physics, rendering or LLM.

Controller assertions use a fake RGB recognizer, then recognizer assertions use
labelled geometric/color counterexamples. Neither is an accuracy measurement.
The existing test_zone_own_executor*.py CI glob includes this file unchanged.
"""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import tile_own_skill as skill
from harness import tile_own_vision as vision
from harness import visual_arm_v3 as arm
from harness.zone_study_inputs import OrderSheetSource
from harness.zone_map_schematic import map_bundle
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

ROOT = Path(__file__).resolve().parents[1]
ORDER = {'order_id': 'order-3', 'kind': 'tile', 'count': 1, 'required_robots': 1,
         'identity': 'kind_fungible', 'item_ids': [], 'destination_zone': 'C'}
LOOK = {1: 2000, 3: 510, 4: 2234, 5: 1753, 6: 1500}
MAGENTA = (148, 41, 219)


def floor_image():
    image = np.full((480, 640, 3), (150, 128, 104), np.uint8)
    image[::30, :] = (60, 60, 60)
    image[:, ::30] = (60, 60, 60)
    return image


def frame(fid, t, *, robot='r1', image=None, **extra):
    ok, buf = cv2.imencode('.jpg', floor_image() if image is None else image)
    assert ok
    jpeg = buf.tobytes()
    return {'robot_id': robot, 'camera': 'robot_cam', 'frame_id': fid, 'sim_time': t,
            'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest(), **extra}


def make(**kw):
    return skill.TileWestSkill(**{'robot_id': 'r1', 'order': ORDER, 'role': 'west',
                                 'condition_name': 'no_comm', **kw})


class Port:
    def __init__(self, monkeypatch, *, condition='no_comm', private=None, holding='yes'):
        self.s = make(condition_name=condition)
        self.t, self.fid, self.commands = 0., 0, []
        self.private, self.holding = private or {}, holding
        self.s.on_command({'robot_id': 'r1', 't': 0., 'kind': 'initial_servo_command', 'pulses': LOOK})
        self.s.step(0.)
        self.inspect = lambda *a, **k: vision.TileView((.178, 0.), 'synthetic_tile',
                    'no' if self.s.state in ('inspect_release', 'verify_release') else self.holding,
                    'synthetic_rgb_label')
        monkeypatch.setattr(vision, 'inspect', self.inspect)

    def tick(self, *, ack=True, fresh=True):
        self.t = round(self.t + .2, 6)
        if fresh:
            self.fid += 1
            self.s.on_frame(self.t, frame(self.fid, self.t, **self.private))
        out = self.s.step(self.t)
        for command in out['commands']:
            self.commands.append((self.t, command))
            if ack:
                self.s.on_command({'t': self.t, 'robot_id': 'r1', **command})
        return out

    def until(self, state, max_ticks=160):
        for _ in range(max_ticks):
            if self.s.state == state:
                return
            self.tick()
        pytest.fail(f'expected {state}, got {self.s.status(self.t)}')


def native_motion(p, **changes):
    """Issued row shape from OwnCamTeamHost._macro_timeline's mecanum branch."""
    return {'robot_id': 'r1', 't': p.t, 'kind': 'mecanum', 'forward': .05,
            'left': 0., 'turn': 0., 'duration_s': .1, **changes}


def test_native_macro_receipt_can_resume_tile_carry(monkeypatch):
    from harness.zone_own_team_host import OwnCamTeamHost
    from sim.camera_robot_port import validate_raw_action

    p = Port(monkeypatch)
    p.until('holding')
    # Exercise the real pure macro conversion with no host/world construction.
    host = SimpleNamespace(robots={'r1': SimpleNamespace(executor=None)})
    action = {'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration': .1}
    timeline = OwnCamTeamHost._macro_timeline(host, 'r1', action, p.t)
    t, (issued,) = timeline[0]
    validate_raw_action(issued, allow_mecanum=True)
    assert issued['duration_s'] == .1 and 'duration' not in issued
    # The caller binds its own port identity; this is not native dispatch wiring.
    p.s.on_command({'robot_id': 'r1', 't': t, **issued})
    assert p.s.motion_until == pytest.approx(t + .1)
    assert not p.s.carry_permitted(t)
    p.tick()
    assert p.s.carry_permitted(p.t)


@pytest.mark.parametrize('duration', [0., .1, .3])
def test_native_motion_waits_for_post_motion_capture_then_can_release(monkeypatch, duration):
    p = Port(monkeypatch)
    p.until('holding')
    issued = p.t
    # An upstream action alias must not override the actual port receipt.
    p.s.on_command(native_motion(p, duration_s=duration, duration=99.))
    assert p.s.motion_until == pytest.approx(issued + duration)
    assert not p.s.carry_permitted(issued)
    with pytest.raises(ValueError, match='RELEASE_REQUIRES'):
        p.s.request_release(now=issued, destination_zone='C')
    # Merely advancing time cannot make the old capture post-motion evidence.
    p.s.step(issued + duration)
    assert not p.s.carry_permitted(issued + duration)
    p.t = round(issued + duration, 6)
    p.tick()
    assert p.s.carry_permitted(p.t)
    p.s.request_release(now=p.t, destination_zone='C')
    p.until('done')


def test_overlapping_native_motion_keeps_latest_end_and_waits_for_rgb(monkeypatch):
    p = Port(monkeypatch)
    p.until('holding')
    issued = p.t
    p.s.on_command(native_motion(p, duration_s=.6))
    p.tick()  # fresh image during motion cannot authorize another move/release
    assert not p.s.carry_permitted(p.t)
    p.s.on_command(native_motion(p, duration_s=.1))
    assert p.s.motion_until == pytest.approx(issued + .6)
    p.tick()
    assert not p.s.carry_permitted(p.t)
    p.tick()
    assert p.s.carry_permitted(p.t)


@pytest.mark.parametrize('field', ['forward', 'left', 'turn', 'duration_s'])
@pytest.mark.parametrize('bad', [None, True, '0.1', math.nan, math.inf, -math.inf])
def test_native_motion_invalid_numbers_do_not_mutate_history(monkeypatch, field, bad):
    p = Port(monkeypatch)
    before = copy.deepcopy(vars(p.s))
    with pytest.raises(ValueError, match='MOTION_COMMAND_INVALID'):
        p.s.on_command(native_motion(p, **{field: bad}))
    assert vars(p.s) == before


@pytest.mark.parametrize('fault', ['missing', 'action_only', 'negative'])
def test_native_motion_requires_nonnegative_canonical_duration(monkeypatch, fault):
    p = Port(monkeypatch)
    row = native_motion(p)
    if fault == 'negative':
        row['duration_s'] = -.1
    else:
        row.pop('duration_s')
        if fault == 'action_only':
            row['duration'] = .1
    with pytest.raises(ValueError, match='MOTION_COMMAND_INVALID'):
        p.s.on_command(row)
    assert p.s.motion_until == -math.inf and p.s.motion_time == -math.inf


@pytest.mark.parametrize('phase', ['search', 'verify_hold', 'holding', 'verify_release'])
@pytest.mark.parametrize('reencode', [False, True])
def test_same_capture_time_with_new_id_fails_closed_in_all_confirmation_phases(monkeypatch, phase, reencode):
    p = Port(monkeypatch)
    if phase == 'search':
        p.tick(); p.tick(); p.tick()
        assert p.s.streak == 1
    else:
        p.until('holding' if phase == 'verify_release' else phase)
        if phase == 'verify_release':
            p.s.request_release(now=p.t, destination_zone='C')
            p.until(phase)
        p.tick()
        assert p.s.state == phase
        if phase == 'verify_hold':
            assert p.s.hold_streak == 1
        elif phase == 'verify_release':
            assert p.s.streak == 1
    # Equal capture time is invalid even if metadata or encoding bytes change.
    image = floor_image()
    if reencode:
        image[:30, :30] = (10, 20, 30)
    replay = frame(p.fid + 1, p.t, image=image)
    p.s.on_frame(p.t, replay)
    out = p.s.step(p.t)
    assert p.s.reason == 'OWN_IMAGE_INVALID' and p.s.state == 'failed'
    assert out['commands'] == [{'kind': 'hold'}]
    assert not p.s.carry_permitted(p.t)
    assert not p.s.status(p.t)['skill_complete']
    assert not any(e['event'] == 'skill_complete' for e in p.s.events)


def test_normal_low_grasp_hold_and_release_are_not_delivery(monkeypatch):
    p = Port(monkeypatch)
    p.until('holding')
    assert p.s.carry_permitted(p.t)
    assert not p.s.status(p.t)['skill_complete']
    # The target and height flow into actual PWM commands (not just metadata).
    commanded = [c for _, c in p.commands if c['kind'] == 'arm']
    for servo, value in p.s.grasp_pose.items():
        if servo != 6:
            assert {'kind': 'arm', 'servo_id': servo, 'pulse': value} in commanded
    assert arm.forward_grip(p.s.grasp_pose)[2] == pytest.approx(.007, abs=.001)
    assert arm.forward_grip(p.s.lift_pose)[2] == pytest.approx(.070, abs=.001)
    p.s.request_release(now=p.t, destination_zone='C')
    p.until('done')
    assert p.s.status(p.t)['release_belief'] == 'own_rgb_released'
    assert p.s.events == [{'event': 'skill_complete', 'confirmation': 'own_rgb_released',
                           'scope': 'local_manipulation_only'}]
    assert 'delivery_success' not in p.s.status(p.t)
    assert 'delivered' not in json.dumps(p.s.events)
    for _ in range(3):
        assert p.tick()['commands'] == [{'kind': 'hold'}]
    assert len(p.s.events) == 1


@pytest.mark.parametrize('role', ['east', 'any', 'north', 'end_neg', None])
def test_wrong_role_rejected(role):
    with pytest.raises(ValueError, match='ROLE_UNSUPPORTED'):
        make(role=role)


@pytest.mark.parametrize('patch', [{'kind': 'cyan'}, {'kind': 'can'}, {'count': 2}, {'count': True},
    {'required_robots': 2}, {'required_robots': True}, {'count': 1.0},
    {'identity': 'specific_item', 'item_ids': ['tile_1']}, {'destination_zone': 'A'}])
def test_unsupported_order_rejected(patch):
    with pytest.raises(ValueError, match='ORDER_UNSUPPORTED'):
        make(order={**ORDER, **patch})


def test_catalogue_public_role_and_separate_assignment_contract():
    from sim.zone_cargo import kind
    tile = kind('tile')
    assert tuple(2 * v for v in tile.parts[0].size) == vision.DIMENSIONS_M
    assert tile.mass_kg == vision.MASS_KG == .025
    assert tile.formations == (('west',), ('east',))
    assert all(g.grip_xyz[2] == vision.GRASP_HEIGHT_M == .007 for g in tile.grasps)
    first, second = make(), make(robot_id='r3')
    assert first.manifest() == second.manifest()
    assert first.role_assignment() != second.role_assignment()


@pytest.mark.parametrize('x', [.176, .178, .180])
@pytest.mark.parametrize('z', [.006, .007, .008])
def test_low_arm_command_bounds_and_round_trip(x, z):
    p = skill.low_pose((x, 0.), height_m=z)
    assert all(isinstance(v, int) and 500 <= v <= 2500 for v in p.values())
    assert arm.forward_grip(p) == pytest.approx((x, 0., z), abs=.001)


@pytest.mark.parametrize('z', [0., .00599, .00801, .024, math.nan, math.inf, True])
def test_box_height_and_invalid_height_are_refused(z):
    with pytest.raises(ValueError, match='HEIGHT_OUT_OF_RANGE'):
        skill.low_pose((.178, 0.), height_m=z)


@pytest.mark.parametrize('xy', [(.155, 0.), (.17599, 0.), (.18001, 0.), (.178, .006), (math.nan, 0.)])
def test_outside_candidate_envelope_refused(xy):
    with pytest.raises(ValueError):
        skill.low_pose(xy)


def test_missing_low_tile_never_closes_or_completes(monkeypatch):
    p = Port(monkeypatch)
    monkeypatch.setattr(vision, 'inspect', lambda *a, **k: vision.TileView())
    p.until('failed')
    assert p.s.reason == 'TILE_NOT_DETECTED'
    assert all(out == {'kind': 'hold'} for _, out in p.commands)
    assert not p.s.status(p.t)['skill_complete']


def test_detection_requires_two_fresh_stable_frames(monkeypatch):
    p = Port(monkeypatch)
    p.tick(); p.tick(); p.tick()  # only one settled frame at t=.6
    assert p.s.state == 'search'
    for _ in range(3):
        p.s.step(p.t)
    assert p.s.state == 'search'
    monkeypatch.setattr(vision, 'inspect', lambda *a, **k: vision.TileView((.30, 0.)))
    p.tick()
    assert p.s.state == 'search'
    p.tick()
    assert p.s.state == 'failed' and p.s.reason == 'TILE_TARGET_OUTSIDE_ARM_ENVELOPE'


def test_emitted_command_without_history_never_advances(monkeypatch):
    p = Port(monkeypatch)
    p.until('open')
    for _ in range(65):
        p.tick(ack=False)
    assert p.s.state == 'failed' and p.s.reason == 'STAGE_TIMEOUT_OPEN'
    assert not any(c.get('pulse') == skill.CLOSED_PWM for _, c in p.commands)


def test_hold_and_release_need_two_post_transition_frames(monkeypatch):
    p = Port(monkeypatch)
    p.until('verify_hold')
    p.tick()
    assert p.s.state == 'verify_hold'
    p.tick()
    assert p.s.state == 'holding'
    p.s.request_release(now=p.t, destination_zone='C')
    p.until('verify_release')
    p.tick()
    assert p.s.state == 'verify_release'
    p.tick()
    assert p.s.state == 'done'


def test_same_value_command_ack_still_needs_new_settled_frame(monkeypatch):
    p = Port(monkeypatch)
    p.until('open')  # open PWM already equals initial command
    p.tick()  # emits and logs another open command, frame came BEFORE it
    p.s.step(p.t)
    assert p.s.state == 'open'
    p.tick()
    assert p.s.state == 'open'
    p.until('lower')


@pytest.mark.parametrize('held', ['no', 'unknown'])
def test_miss_grasp_or_unknown_blocks_carry_and_release(monkeypatch, held):
    p = Port(monkeypatch, holding=held)
    p.until('failed')
    assert p.s.reason == ('TILE_NOT_HELD' if held == 'no' else 'STAGE_TIMEOUT_VERIFY_HOLD')
    assert not p.s.carry_permitted(p.t)
    with pytest.raises(ValueError, match='RELEASE_REQUIRES'):
        p.s.request_release(now=p.t, destination_zone='C')


def test_open_command_alone_and_absence_without_visible_floor_tile_do_not_complete(monkeypatch):
    p = Port(monkeypatch)
    p.until('holding')
    with pytest.raises(ValueError):
        p.s.request_release(now=p.t, destination_zone='B')
    p.s.request_release(now=p.t, destination_zone='C')
    p.until('verify_release')
    assert not p.s.status(p.t)['skill_complete']
    monkeypatch.setattr(vision, 'inspect', lambda *a, **k: vision.TileView(holding='no'))
    p.until('failed')
    assert p.s.reason == 'STAGE_TIMEOUT_VERIFY_RELEASE'


@pytest.mark.parametrize('fault', ['unknown', 'no', 'missing', 'stale'])
def test_hold_loss_stops_permission_and_terminates(monkeypatch, fault):
    p = Port(monkeypatch)
    p.until('holding')
    if fault in ('unknown', 'no'):
        p.holding = fault
        p.tick()
    else:
        p.tick(fresh=False); p.tick(fresh=False)
    assert not p.s.carry_permitted(p.t)
    for _ in range(70):
        p.tick(fresh=fault in ('unknown', 'no'))
        if p.s.state == 'failed':
            break
    assert p.s.state == 'failed'


@pytest.mark.parametrize('fault', ['actor', 'top', 'future', 'nan', 'stale', 'duplicate', 'hash', 'bad_jpeg'])
def test_bad_camera_input_fails_closed(monkeypatch, fault):
    p = Port(monkeypatch)
    p.tick()
    obs = frame(2, .4)
    if fault == 'actor': obs['robot_id'] = 'r2'
    if fault == 'top': obs['camera'] = 'top_cam'
    if fault == 'future': obs['sim_time'] = .5
    if fault == 'nan': obs['sim_time'] = math.nan
    if fault == 'stale': obs['sim_time'] = 0.
    if fault == 'duplicate': obs['frame_id'] = 1
    if fault == 'hash': obs['sha256'] = '0' * 64
    if fault == 'bad_jpeg': obs['image'] = '!invalid!'
    p.s.on_frame(.4, obs)
    assert p.s.state == 'failed' and p.s.reason == 'OWN_IMAGE_INVALID'
    assert p.s.step(.4)['commands'] == [{'kind': 'hold'}]


def test_private_changes_and_four_conditions_do_not_change_trace(monkeypatch):
    traces = []
    for condition in skill.CONDITIONS:
        for private in ({'eval': {'delivered': True, 'item_pose': [1, 2, 3]}, 'partner_state': 'held'},
                        {'eval': {'delivered': False, 'item_pose': [99, -2, 9]}, 'partner_state': 'lost',
                         'actuator_state': {'servo_pulses': {'3': 0}}, 'inventory': ['wrong']}):
            p = Port(monkeypatch, condition=condition, private=private)
            p.until('holding')
            p.s.request_release(now=p.t, destination_zone='C')
            p.until('done')
            traces.append((p.commands, p.s.events, p.s.status(p.t), p.s.manifest()))
    assert all(trace == traces[0] for trace in traces)


def test_public_sheet_survives_private_event_and_placement_changes():
    scenario = json.loads((ROOT / 'configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json').read_text())
    bundle = map_bundle(scenario['map_id'], landmark_detail='none')
    first = OrderSheetSource(scenario, bundle)
    changed = copy.deepcopy(scenario)
    changed['eval'] = {'hidden_events': [], 'placements': [], 'partner_pose': [200, 200, 3]}
    second = OrderSheetSource(changed, bundle)
    order1 = next(o for o in first.sheet()['orders'] if o['kind'] == 'tile')
    order2 = next(o for o in second.sheet()['orders'] if o['kind'] == 'tile')
    assert order1 == order2
    assert make(order=order1).manifest() == make(order=order2).manifest()


def test_abort_and_900_sim_cap_are_terminal(monkeypatch):
    p = Port(monkeypatch)
    p.until('holding')
    p.s.step(900.)
    assert p.s.reason == 'SIM_LIMIT'
    p.s.abort()
    assert len(p.s.events) == 1
    q = Port(monkeypatch)
    q.until('lower')
    q.s.abort()
    assert q.s.step(q.t)['commands'] == [{'kind': 'hold'}]
    assert q.s.reason == 'CANCELLED'


def test_peer_command_history_and_mid_grasp_base_motion_refused(monkeypatch):
    p = Port(monkeypatch)
    with pytest.raises(ValueError, match='OWN_COMMAND'):
        p.s.on_command({'robot_id': 'r2', 't': 1., 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    p.until('lower')
    p.s.on_command({'robot_id': 'r1', 't': p.t, 'kind': 'mecanum', 'forward': .1,
                    'left': 0., 'turn': 0., 'duration_s': .1})
    assert p.s.reason == 'BASE_MOVED_DURING_MANIPULATION'


def projected_slab(*, centre=(.178, 0.), dims=(.060, .040), yaw=0., colour=MAGENTA):
    """2-D synthetic polygon from labelled plane geometry, no renderer or physics."""
    xy = np.array([[-1, -1], [-1, 1], [1, 1], [1, -1]], float) * np.array(dims) / 2
    rot = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
    xy = xy @ rot.T + np.array(centre)
    points = np.column_stack((xy, np.full(4, .012)))
    origin, axes = (np.asarray(v, float) for v in arm.camera_extrinsics(LOOK))
    optical = (points - origin) @ axes.T
    pixels, _ = cv2.fisheye.projectPoints(optical.reshape(1, -1, 3), np.zeros(3), np.zeros(3),
                                        scaled_camera_matrix(640, 480), np.asarray(CAMERA_FISHEYE_D))
    image = floor_image()
    cv2.fillConvexPoly(image, np.rint(pixels.reshape(-1, 2)).astype(np.int32), colour)
    return image


def test_real_rgb_low_tile_detector_and_floor_box_counterexamples():
    view = vision.inspect(projected_slab(), LOOK)
    assert view.target_xy_m == pytest.approx((.178, 0.), abs=.003)
    assert view.holding == 'unknown'
    for image in (floor_image(), projected_slab(dims=(.034, .040)),
                  projected_slab(dims=(.30, .30)), projected_slab(yaw=math.pi / 2),
                  projected_slab(colour=(200, 180, 40)), projected_slab(dims=(.003, .002)),
                  np.zeros((480, 640, 3), np.uint8)):
        assert vision.inspect(image, LOOK).target_xy_m is None


def test_real_holding_requires_tile_boundary_not_background_or_box():
    grasp = skill.low_pose((.178, 0.))
    mask = vision.grip_mask(grasp, (640, 480))
    image = floor_image()
    image[mask] = MAGENTA
    # Texture makes an informative synthetic frame; not final-camera validation.
    image[150:153, 150:350] = (90, 25, 135)
    assert vision.inspect(image, LOOK, grasp_pose=grasp).holding == 'yes'
    for colour in ((200, 180, 40), (40, 190, 40), (40, 40, 220)):
        rival = floor_image(); rival[mask] = colour
        assert vision.inspect(rival, LOOK, grasp_pose=grasp).holding != 'yes'
    background = floor_image(); background[:] = MAGENTA
    for offset in range(3):
        background[offset::30, :] = (90, 25, 135)
    assert vision.image_information(background)['sufficient']
    assert vision.inspect(background, LOOK, grasp_pose=grasp).holding != 'yes'
    assert vision.inspect(floor_image(), LOOK, grasp_pose=grasp).holding == 'no'
    assert vision.inspect(np.zeros_like(image), LOOK, grasp_pose=grasp).holding == 'unknown'


def test_catalogue_station_v3_geometry_cannot_prove_holding():
    # Catalogue's .155 station has a legal mathematical pose outside the old
    # box calibration, but its entire image is hidden by the hypothetical tile.
    grasp = arm.solve_grip_site_ik((.155, 0., .007), calibrated_grasp_only=False)
    assert vision.grip_mask(grasp, (640, 480)).mean() > .95
    assert vision.holding_judgment(projected_slab(), grasp)[0] == 'unknown'


def test_runtime_imports_no_physics_or_model_sdk():
    code = '''
import sys
for name in ('mujoco', 'google.genai', 'openai', 'torch'):
    sys.modules[name] = None
from harness.tile_own_skill import TileWestSkill, low_pose
assert low_pose((.178, 0.))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
