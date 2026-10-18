"""Pure-python boundary tests for the act18 gripper-closed classifier.

Servo 1 is the gripper (1500 closes, >=1900 is the sim's "clearly open" cutoff);
servo 5 is the shoulder and must never decide the gripper state.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_gripper_state import (GRIPPER_ACTION_DIM, GRIPPER_OPEN_PWM, GRIPPER_SERVO,
                                 SERVOS, clamp_pwm, gripper_closed, gripper_closed_pulse,
                                 pwm_from_encoded)


def test_servo1_1500_closed_1900_plus_open():
    assert gripper_closed({'1': 1500}) is True          # recorded close pulse
    assert gripper_closed({'1': 1899}) is True          # below the open cutoff
    assert gripper_closed({'1': 1900}) is False         # sim "clearly open" cutoff
    assert gripper_closed({'1': 2000}) is False         # recorded open pulse
    assert gripper_closed({'1': 2500}) is False


def test_servo5_shoulder_is_ignored():
    # Servo 5 is the shoulder: it must not flip either verdict.
    assert gripper_closed({'1': 1500, '5': 2500}) is True
    assert gripper_closed({'1': 2000, '5': 500}) is False
    assert gripper_closed({'1': 1500, '3': 2500, '4': 2500, '5': 2500, '6': 2500}) is True
    assert gripper_closed({'1': 2000, '3': 500, '4': 500, '5': 500, '6': 500}) is False


def test_recorded_scale_is_clamped():
    assert clamp_pwm(0) == 500 and clamp_pwm(9999) == 2500
    assert gripper_closed_pulse(0) is True              # clamped up to 500
    assert gripper_closed_pulse(9999) is False          # clamped down to 2500


def test_action_dim_matches_contract_servo_order():
    # The cited contract fixture stores servo PWM in SERVOS order at dims 8..12.
    contract = (ROOT / 'tests/fixtures/warp3/grasp_act_contract.py.txt').read_text()
    found = re.search(r'^SERVOS = \(([^)]*)\)', contract, re.M)
    assert found is not None
    servos = tuple(s.strip() for s in found.group(1).split(','))
    assert servos == SERVOS
    assert 8 + servos.index(GRIPPER_SERVO) == GRIPPER_ACTION_DIM


def test_encoded_action_uses_gripper_dim_8_not_shoulder_dim_11():
    assert GRIPPER_SERVO == '1' and GRIPPER_ACTION_DIM == 8
    assert GRIPPER_OPEN_PWM == 1900
    assert pwm_from_encoded(0.0) == 1500.0              # closed target
    assert pwm_from_encoded(0.5) == 2000.0              # open target
    assert pwm_from_encoded(2.0) == 2500.0              # clamped
    assert gripper_closed_pulse(pwm_from_encoded(0.0)) is True
    assert gripper_closed_pulse(pwm_from_encoded(0.5)) is False
