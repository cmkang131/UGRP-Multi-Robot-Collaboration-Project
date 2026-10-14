"""Own-RGB lift confirmation: synthetic at-grip silhouettes, no simulator."""
import cv2
import numpy as np
import pytest
from harness import zone_own_perception as v1
from harness import zone_own_perception_v3 as v3
from sim.grasp_act_solo_rgb import lift_answer, SoloLiftObserver
from sim.grasp_act_solo_teacher import SoloTeacher, primitives


def geometry(kind, role='west'):
    p = primitives()
    t = SoloTeacher(kind, role, p.folded, profile='solo_visible_only_v1', held_object_hidden_v1=True, ops=p)
    station = t.spec.station_m or p.station
    low, high, _ = t._pick_geometry({'xyz': [station, 0., t.spec.grip_z_m], 'yaw': 0.})
    return low, high


def floor(seed=0):
    rng = np.random.default_rng(seed)
    base = np.zeros((480, 640, 3), np.int32)
    base[:] = (60, 70, 80)
    base += rng.integers(-12, 12, base.shape)
    base = base*np.linspace(.6, 1.4, 480)[:, None, None]
    return base.clip(0, 255).astype(np.uint8)


def paint(frame, mask, hsv):
    out = frame.copy()
    out[mask] = cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0]
    return out


HSV = {'cyan': (93, 210, 200), 'red': (0, 220, 200)}


@pytest.mark.parametrize('kind', ['cyan', 'tile'])
def test_kind_in_its_predicted_at_grip_band_is_yes_and_floor_only_is_no(kind):
    low, high = geometry(kind)
    sil = v3.held_silhouette(kind, v1._pose(high), (640, 480), grasp_pose=low)[0]
    assert sil.sum() > 5000
    from harness.zone_own_perception import APPEARANCE      # the hue band the catalogue gives this kind
    low_h, high_h = APPEARANCE[kind]['hue'][0]
    color = ((low_h+high_h)//2, 210, 200)
    answer, record = lift_answer(paint(floor(), sil, color), high, kind, low, [.2, 0.])
    assert answer == 'yes' and record['evidence'] == 'kind_in_at_grip_band'
    answer, record = lift_answer(floor(), high, kind, low, [.2, 0.])
    assert answer == 'no'


def test_other_kind_in_the_band_is_not_a_confirmation():
    low, high = geometry('cyan')
    sil = v3.held_silhouette('cyan', v1._pose(high), (640, 480), grasp_pose=low)[0]
    answer, _ = lift_answer(paint(floor(), sil, HSV['red']), high, 'cyan', low, [.2, 0.])
    assert answer == 'no'


def test_black_frame_is_unknown_not_a_confirmation():
    low, high = geometry('cyan')
    answer, record = lift_answer(np.zeros((480, 640, 3), np.uint8), high, 'cyan', low, [.2, 0.])
    assert answer == 'unknown'


def test_can_is_never_framed_at_the_grasp_so_the_floor_spot_is_the_only_evidence():
    # Cause of the fallback: a held 50 mm can's at-grip silhouette is 0 px at every reachable tool pitch.
    p = primitives()
    t = SoloTeacher('can', 'any', p.folded, profile='solo_visible_only_v1', held_object_hidden_v1=True, ops=p)
    for pref in (-90., -66., -50., -40.):
        low = p.ik((p.station, 0., .024), preferred_pitch_deg=pref)
        assert v3.held_silhouette('can', v1._pose(low), (640, 480), grasp_pose=low)[0].sum() == 0
    low, high = geometry('can', 'any')
    calls = []

    def slot(answer, observed):
        def judge(frame, pose, *, slot_base_xy, expected_kind):
            calls.append((slot_base_xy, expected_kind))
            return {'answer': answer, 'observed': observed, 'reason': 'x'}
        return judge
    frame = floor()
    answer, record = lift_answer(frame, high, 'can', low, [.2, .01], slot_judge=slot('no', 'empty'))
    assert answer == 'yes' and record['evidence'] == 'original_floor_spot'
    assert calls == [([.2, .01], 'can')]                      # the frozen pre-grasp floor spot, nothing else
    assert lift_answer(frame, high, 'can', low, [.2, 0.], slot_judge=slot('yes', 'can'))[0] == 'no'
    assert lift_answer(frame, high, 'can', low, [.2, 0.], slot_judge=slot('unknown', 'not_observed'))[0] == 'unknown'
    # A bare spot is not evidence for a kind that CAN be framed: no fallback for boxes.
    low_b, high_b = geometry('cyan')
    answer, record = lift_answer(np.zeros((480, 640, 3), np.uint8), high_b, 'cyan', low_b, [.2, 0.],
                                 slot_judge=slot('no', 'empty'))
    assert answer == 'unknown' and record['evidence'] == 'kind_in_at_grip_band'


def issued(t, arm=1200, *, grip=1500, pan=1500, wheels=None):
    return {'t': t, 'pwm': {'1': grip, '3': arm, '4': 2100, '5': 2400, '6': pan},
            'wheels': wheels or [0.]*4}


def solid_kind(kind):
    from harness.zone_own_perception import APPEARANCE
    lo, hi = APPEARANCE[kind]['hue'][0]
    return np.full((480, 640, 3), cv2.cvtColor(np.uint8([[[(lo+hi)//2, 210, 200]]]),
                   cv2.COLOR_HSV2BGR)[0, 0], np.uint8)


@pytest.mark.parametrize('kind', ['cyan', 'red', 'green', 'yellow', 'can', 'tile'])
def test_v2_confirms_textureless_colour_through_completed_lift_and_three_second_hold(kind):
    frame = solid_kind(kind)
    from harness.zone_own_perception_v3_1 import image_information
    assert not image_information(frame)['sufficient']  # real failure class, without relaxing v3.1
    o = SoloLiftObserver(kind)
    tags = []
    def save(tag, frame, now):
        tags.append(tag)
        return {'t': now, 'path': tag}
    o.start(frame, issued(0), save)
    assert o.observe(frame, issued(1.7, 750), complete=True, save=save)['answer'] == 'unknown'
    assert o.observe(frame, issued(4.6, 750), complete=True, save=save)['answer'] == 'unknown'
    row = o.observe(frame, issued(4.7, 750), complete=True, save=save)
    assert row['answer'] == 'yes' and len(row['comparisons']) == 2
    assert tags == ['before_lift', 'lift_complete', 'settled_hold']
    # A successful old sample cannot hide a new grip loss.
    row = o.observe(solid_kind('red' if kind != 'red' else 'cyan'), issued(4.8, 750), complete=True, save=save)
    assert row['answer'] == 'no'


@pytest.mark.parametrize('cmd', [issued(1.7), issued(.5, 750), issued(1.7, 750, grip=2000),
                                issued(1.7, 750, pan=1600), issued(1.7, 750, wheels=[.2]*4)])
def test_v2_pixels_alone_cannot_replace_compatible_issued_lift(cmd):
    o = SoloLiftObserver('cyan'); frame = solid_kind('cyan')
    save = lambda tag, frame, now: {'t': now}
    o.start(frame, issued(0), save)
    o.observe(frame, cmd, complete=True, save=save)
    assert o.observe(frame, {**cmd, 't': cmd['t']+3}, complete=True, save=save)['answer'] == 'unknown'


@pytest.mark.parametrize('before', [np.zeros((480, 640, 3), np.uint8), solid_kind('red')])
def test_v2_unseen_or_wrong_colour_before_lift_is_unknown(before):
    o = SoloLiftObserver('cyan'); save = lambda tag, frame, now: {'t': now}
    o.start(before, issued(0), save)
    o.observe(solid_kind('cyan'), issued(1.7, 750), complete=True, save=save)
    assert o.observe(solid_kind('cyan'), issued(4.7, 750), complete=True, save=save)['answer'] == 'unknown'


def test_shared_comparator_preserves_crate_independent_part_checks():
    from sim.rgb_lift_evidence import confirm_parts_v2
    masks = lambda f: (f[..., 0] > 0, f[..., 1] > 0)
    b = np.zeros((100, 100, 3), np.uint8); b[:, :50, 0] = 255; b[:, 50:, 1] = 255
    commands = [issued(0), issued(1.7, 750)]
    call = lambda after, settled: confirm_parts_v2(b, after, masks=masks, names=('lug', 'pink'),
                             commands=commands, settled=settled, rule='crate_rgb_lift_v2')
    assert call(b, b)['verdict'] == 'confirmed'
    assert call(b, None)['verdict'] == 'undetermined'
    lost = b.copy(); lost[..., 0] = 0
    assert call(lost, b)['verdict'] == 'not_confirmed'
    assert call(b, lost)['verdict'] == 'not_confirmed'
    assert call(np.roll(b, 20, axis=1), b)['verdict'] == 'undetermined'
