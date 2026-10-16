"""D1's finite v3 carry postures, from PR #361 (command space only).

The original floor grasp and low lift stay intact. HIGH is a new carry pose;
neither an issued target nor an elapsed settle proves contact or visibility.
"""
from harness.zone_final_pair_vision import grasp_postures, required_camera_poses as old_camera_poses

HIGH = {3: 896, 4: 2035, 5: 1894, 6: 1500}
VIA_110 = {3: 891, 4: 2036, 5: 2054, 6: 1500}
VIA_130 = {3: 981, 4: 2152, 5: 1917, 6: 1500}
MOVE_S, VIA_SETTLE_S, HIGH_SETTLE_S = 1.2, 2.8, 8.
POSE_ID = 'masterpi-v3-pair-high-150mm-minus40-v1'


def at_high(servo):
    return all(servo.get(sid) == pulse for sid, pulse in HIGH.items())


def raise_path():
    return [(dict(VIA_110), MOVE_S, VIA_SETTLE_S),
            (dict(VIA_130), MOVE_S, VIA_SETTLE_S),
            (dict(HIGH), MOVE_S, HIGH_SETTLE_S)]


def lower_path():
    hover, descent = grasp_postures()
    return [(dict(VIA_130), MOVE_S, VIA_SETTLE_S),
            (dict(VIA_110), MOVE_S, VIA_SETTLE_S),
            (hover, MOVE_S, VIA_SETTLE_S), (descent[-1], MOVE_S, .4)]


def queue_path(arm, now, path):
    for pose, duration, settle in path:
        arm.queue({**pose, 1: 1500}, now, duration=duration, settle=settle)


def required_camera_poses():
    # D2: no loaded floor/low-hover extrinsics, no interpolation or fallback.
    # Transit pixels still go to grip/hold checks; absolute localization waits.
    return {'unloaded': old_camera_poses()['unloaded'], 'loaded': [dict(HIGH)]}


def record():
    hover, descent = grasp_postures()
    return {'pose_id': POSE_ID, 'floor': descent[-1], 'low_lift': hover, 'high': dict(HIGH),
            'raise': raise_path(), 'lower': lower_path(), 'gripper_closed_pwm': 1500,
            'loaded_camera_scope': 'HIGH only; command-based transit skips map observations',
            'source': 'PR #361 a9481446; D1-D2 issue #219 comment 5966171204'}
