"""Gripper-closed state read from recorded act18 issued commands (pure stdlib).

Servo mapping (`harness/research_camera_actor.py:15`):
    arm servo_id 1(gripper), 3(wrist pitch), 4(elbow), 5(shoulder), pulse 500..2500.
    Gripper 2000 opens, 1500 closes.
`sim/masterpi_production_v2.py:358-359` marks a grasp "clearly open" when the
servo-1 pulse is >= 1900, so on the recorded 500..2500 scale a closed gripper is
    pwm['1'] < 1900
and servo 5 is the shoulder, never the gripper.

The 14-dim action encoding stores servo PWM as (pulse-1500)/1000 over
SERVOS = (1, 3, 4, 5, 6) (main `harness/grasp_act_contract.py`; byte-identical
fixture `tests/fixtures/warp3/grasp_act_contract.py.txt:19,139`), so action
dim 8 is the gripper and dim 11 is the shoulder.

Diagnostic helper only: no simulator, model, measured joints or GT state.
"""
SERVOS = ('1', '3', '4', '5', '6')
GRIPPER_SERVO = '1'
GRIPPER_ACTION_DIM = 8  # SERVOS.index('1') offset inside the 14-dim action
GRIPPER_OPEN_PWM = 1900  # sim's `clearly_open` cutoff; closed is strictly below
PWM_MIN = 500
PWM_MAX = 2500


def clamp_pwm(pulse):
    """Clamp to the recorded servo pulse scale (500..2500)."""
    return min(PWM_MAX, max(PWM_MIN, float(pulse)))


def gripper_closed_pulse(pulse):
    """True iff a servo-1 pulse is below the 1900 'clearly open' cutoff."""
    return clamp_pwm(pulse) < GRIPPER_OPEN_PWM


def gripper_closed(pwm):
    """True iff the issued command closes the gripper (servo 1, not servo 5).

    pwm is the issued-command mapping {'1': pulse, ...}; a missing servo 1 is an
    error rather than a silent "open" default.
    """
    return gripper_closed_pulse(pwm[GRIPPER_SERVO])


def pwm_from_encoded(value):
    """Decode a (pulse-1500)/1000 action value back to a clamped pulse."""
    return clamp_pwm(1500.0 + 1000.0*float(value))
