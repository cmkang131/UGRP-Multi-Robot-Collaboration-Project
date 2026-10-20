"""faildiag gripper/arm labels must follow the servo mapping (1=gripper, 5=shoulder)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_faildiag import PWM_KEYS, analyse_world

BASE = {'1': 2000, '3': 1500, '4': 1500, '5': 1500, '6': 1500}
STEPS = 10
CHANGE = 5


def rows(pwms):
    out = []
    for pwm in pwms:
        command = {'wheels': [0.0]*4, 'duration_s': [0.0]*4,
                   'pwm': {k: pwm[k] for k in PWM_KEYS}}
        out.append({'actions': [{'command': command, 'done': False}], 'skills': ['grasp']})
    return out


def at_change(key, after):
    return [dict(BASE, **{key: BASE[key] if i < CHANGE else after}) for i in range(STEPS)]


def test_servo5_movement_is_not_a_gripper_label():
    report = analyse_world(rows(at_change('5', 2000)), 0, [])
    assert report['gripper_close_onset_sim_s'] is None
    assert report['gripper_last_change_sim_s'] is None
    assert report['finger_last_change_sim_s'] is None  # legacy alias, same value
    assert report['gripper_pwm_distinct'] == 1 and report['gripper_pwm_range'] == 0
    # Servo 5 is the shoulder, so it belongs to the arm set.
    assert report['arm_last_change_sim_s'] == round(CHANGE*0.1+1.7, 2)


def test_servo1_close_is_the_gripper_label():
    report = analyse_world(rows(at_change('1', 1500)), 0, [])
    expected = round(CHANGE*0.1+1.7, 2)
    assert report['gripper_close_onset_sim_s'] == expected
    assert report['gripper_last_change_sim_s'] == expected
    assert report['gripper_pwm_range'] == 500
    # The gripper (servo 1) is not an arm servo.
    assert report['arm_last_change_sim_s'] is None
