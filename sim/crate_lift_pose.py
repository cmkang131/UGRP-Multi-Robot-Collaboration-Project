"""Default-off, command-only elbow-margin selection for the 0.25 kg crate.

The frozen crate6 XML statics assume a level base, issued angles reached and
equal vertical pad loads (0.125 kg/arm). This is not measured torque or a
dynamic/collision guarantee. Never read world coordinates, contacts or qpos.
Candidates are exact prefixes of the existing 1.2 s joint-interpolated lift:
the pick, eight-step fixed-pitch descent, and original collision/route checks
remain intact. No new arm path, independent pitch, or retraction is invented.
"""
from __future__ import annotations

import math
from itertools import groupby

from harness import visual_arm as sdk
from harness.visual_arm_v3 import MOUNT_X_M, tool_pose
from sim.grasp_act_release_teacher import PAD_WINDOW_M
from sim.grasp_act_teacher import IssuedArm
from sim.s2_servo_stiffness import TORQUE_NM
from scripts.zone_teacher import ArmSequence

OPTION = 'crate_lift_pose_margin_v1'
CARTESIAN_OPTION = 'crate_cartesian_lift_v1'
ANTIPODAL_OPTION = 'crate_antipodal_grasp_v1'
CARTESIAN_MODES = (CARTESIAN_OPTION, ANTIPODAL_OPTION)
MODES = ('off', OPTION, *CARTESIAN_MODES)
PAYLOAD_PER_ARM_KG = .125
MIN_RISE_M = .012
LIMIT_NM = TORQUE_NM['elbow']
THRESHOLD_NM = .9 * LIMIT_NM


def angles(pwm):
    tool_pose(pwm)  # finite, complete, safe PWM validation
    p = {int(k): v for k, v in pwm.items()}
    nominal = lambda sid: (p[sid]-sdk.SERVO_DEVIATION[sid]-1500) / sdk.PULSE_PER_DEGREE
    shoulder = math.radians(90-nominal(5))
    elbow = math.radians(-nominal(4))
    wrist = math.radians(nominal(3))
    return shoulder, elbow, wrist


def elbow_torque(pwm):
    """Signed static moment from the frozen arm COMs and the issued pad FK."""
    shoulder, elbow, wrist = angles(pwm)
    forearm, pitch = shoulder+elbow, shoulder+elbow+wrist
    own = 9.81*(.00403*math.cos(forearm)+.0023435*math.cos(pitch)+.00012*math.sin(pitch))
    lever = .062*math.cos(forearm)+.08685*math.cos(pitch)
    payload = PAYLOAD_PER_ARM_KG*9.81*lever
    return {'arm_gravity_nm': own, 'payload_equal_share_nm': payload,
            'payload_per_arm_kg': PAYLOAD_PER_ARM_KG, 'elbow_to_pad_horizontal_m': lever,
            'total_equal_share_nm': own+payload, 'limit_nm': LIMIT_NM,
            'margin_fraction': 1-abs(own+payload)/LIMIT_NM}


def select_lift_prefix(closed_pwm, legacy_lift_pwm):
    """Choose maximum static margin among admissible original lift prefixes.

    Both inputs are owned PWM, including the already planned original lift.
    Every loaded issued sample must retain >=10% margin and the static joint
    ranges. Prefix endpoints stay in pad_window_v2, rise >=12 mm and retain
    the closing pitch (PWM rounding <=0.135 degrees). No candidate -> none.
    """
    closed = {int(k): int(v) for k, v in closed_pwm.items()}
    target = {int(k): int(v) for k, v in legacy_lift_pwm.items()}
    origin = tool_pose(closed)
    sink = IssuedArm(closed)
    sequence = ArmSequence(sink, closed)
    sequence.queue(target, 0., duration=1.2, settle=.5)
    prefix = []
    current = dict(closed)
    peak = abs(elbow_torque(closed)['total_equal_share_nm'])
    eligible, checked, best = 0, 0, None
    shoulder, elbow, wrist = angles(closed)
    ranges_ok = (-.15 <= shoulder <= 2.8 and abs(elbow) <= 1.8 and abs(wrist) <= 1.8)
    for at, batch in groupby(sequence.events, key=lambda row: row[0]):
        rows = list(batch)
        prefix.extend(rows)
        for _, sid, pulse in rows:
            current[sid] = pulse
        pose = tool_pose(current)
        shoulder, elbow, wrist = angles(current)
        ranges_ok &= (-.15 <= shoulder <= 2.8 and abs(elbow) <= 1.8 and abs(wrist) <= 1.8)
        torque = elbow_torque(current)
        peak = max(peak, abs(torque['total_equal_share_nm']))
        checked += 1
        radius = math.hypot(pose.x_m-MOUNT_X_M, pose.y_m)
        if not (ranges_ok and PAD_WINDOW_M[0] <= radius <= PAD_WINDOW_M[1]
                and origin.z_m+MIN_RISE_M <= pose.z_m <= .096
                and -90.135 <= pose.pitch_deg <= -39.865
                and abs(pose.pitch_deg-origin.pitch_deg) <= .135+1e-9
                and peak <= THRESHOLD_NM):
            continue
        eligible += 1
        row = {'issued_pwm': dict(current), 'arm_axis_radius_m': radius,
               'z_m': pose.z_m, 'rise_m': pose.z_m-origin.z_m,
               'pitch_deg': pose.pitch_deg, 'prefix_duration_s': at,
               'peak_prefix_torque_nm': peak, **torque, 'events': list(prefix)}
        if best is None or abs(row['total_equal_share_nm']) < abs(best['total_equal_share_nm']):
            best = row
    report = {'mode': OPTION, 'status': 'selected' if best else 'none',
              'reason': None if best else 'no original lift prefix satisfies pad/pitch/rise/joint/10% constraints',
              'threshold_nm': THRESHOLD_NM, 'payload_per_arm_kg': PAYLOAD_PER_ARM_KG,
              'required_margin_fraction': .10, 'checked_prefixes': checked,
              'qualified_prefixes': eligible, 'input_source': 'own issued PWM and own planned lift PWM only',
              'collision_scope': 'unchanged descent; exact subset of original lift command path; physical collision unverified',
              'selected': None if best is None else {k: v for k, v in best.items() if k != 'events'}}
    return best, report
