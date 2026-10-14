"""Command-space, constant-XY/pitch cooperative lift; default-off teacher only.

References and limitations: experiments/2026-10-14-crate-teacher/crate8.md.
Use the standard Cartesian straight-line / cubic time scaling, with static
joint-torque constraints checked BEFORE closing. No measured state is an input.
Equal vertical load sharing is a design assumption, never a feedback signal.
"""
import math

from harness.visual_arm_v3 import MOUNT_X_M, solve_grip_site_ik, tool_pose
from sim.crate_lift_pose import CARTESIAN_OPTION, angles, elbow_torque
from sim.grasp_act_release_teacher import PAD_WINDOW_M
from sim.s2_servo_stiffness import TORQUE_NM

STATION_M = MOUNT_X_M + .148
RISE_M = .026
DURATION_S = 2.4
DT_S = .1
MAX_XY_ERROR_M = .0004  # PWM quantization; not a relaxed grasp/hold criterion


def static_torques(pwm, payload_kg=.125):
    """g(q) + J(q)^T [0,0,mg], frozen arm COMs; level base, issued q.

    XML mass moments: elbow subtree .085 kg, shoulder link .050 kg at
    .0325 m. Wrist subtree moment .0023435*cos(pitch)+.00012*sin(pitch).
    """
    shoulder, elbow, wrist = angles(pwm)
    pitch = shoulder+elbow+wrist
    e = elbow_torque(pwm)
    elbow_nm = e['arm_gravity_nm']+payload_kg*9.81*e['elbow_to_pad_horizontal_m']
    wrist_nm = 9.81*(.0023435*math.cos(pitch)+.00012*math.sin(pitch)
                     + payload_kg*.08685*math.cos(pitch))
    shoulder_nm = elbow_nm+9.81*(.050*.0325+(.085+payload_kg)*.065)*math.cos(shoulder)
    return {'shoulder': shoulder_nm, 'elbow': elbow_nm, 'wrist': wrist_nm}


def plan_lift(closed_pwm):
    """One common rise/time law, same horizontal grip separation and pitch.

    Reject any PWM/IK/joint/torque/Cartesian violation. Never pick a smaller
    rise to improve margin: the 26 mm command is separate from the unchanged
    12 mm actual crate-clearance + 3 s hold evaluator.
    """
    closed = {int(k): int(v) for k, v in closed_pwm.items()}
    origin = tool_pose(closed)
    report = {'mode': CARTESIAN_OPTION, 'status': 'none', 'input_source': 'own planned/issued PWM only',
              'rise_m': RISE_M, 'duration_s': DURATION_S, 'payload_per_arm_kg': .125,
              'required_margin_fraction': .1, 'reason': None}
    samples = [(0., closed)]
    try:
        for i in range(1, round(DURATION_S/DT_S)+1):
            u = i*DT_S/DURATION_S
            z = origin.z_m+RISE_M*u*u*(3-2*u)
            pwm = {**closed, **solve_grip_site_ik((origin.x_m, origin.y_m, z),
                                                preferred_pitch_deg=origin.pitch_deg)}
            # Integer IK rounds three joints separately. Preserve the exact
            # issued pitch sum, instead of relaxing the pitch constraint.
            pwm[3] = closed[3]+(pwm[4]-closed[4])+(pwm[5]-closed[5])
            pwm[6] = closed[6]
            samples.append((i*DT_S, pwm))
    except ValueError as exc:
        report['reason'] = 'ik: '+str(exc)
        return None, report
    peak = {j: 0. for j in TORQUE_NM if j != 'arm_yaw'}
    xy_error = pitch_error = 0.
    for at, pwm in samples:
        p = tool_pose(pwm)
        r = math.hypot(p.x_m-MOUNT_X_M, p.y_m)
        q = angles(pwm)
        xy_error = max(xy_error, math.hypot(p.x_m-origin.x_m, p.y_m-origin.y_m))
        pitch_error = max(pitch_error, abs(p.pitch_deg-origin.pitch_deg))
        for name, value in static_torques(pwm).items():
            peak[name] = max(peak[name], abs(value))
        if not (PAD_WINDOW_M[0] <= r <= PAD_WINDOW_M[1] and
                -.15 <= q[0] <= 2.8 and abs(q[1]) <= 1.8 and abs(q[2]) <= 1.8 and
                -.0003 <= p.z_m-origin.z_m <= RISE_M+.0003 and p.z_m <= .096 and
                -90.135 <= p.pitch_deg <= -39.865 and pitch_error <= .135+1e-9 and
                xy_error <= MAX_XY_ERROR_M and
                all(peak[j] <= .9*TORQUE_NM[j] for j in peak)):
            report.update(reason='path violates pad/joint/height/pitch/XY/10% static margin', rejected_at_s=at,
                          peak_torque_nm=peak, max_xy_error_m=xy_error, max_pitch_error_deg=pitch_error)
            return None, report
    events = [(at, sid, pwm[sid]) for at, pwm in samples[1:] for sid in (3, 4, 5, 6)]
    best = {'events': events, 'issued_pwm': samples[-1][1], 'prefix_duration_s': DURATION_S}
    report.update(status='selected', samples=len(samples), peak_torque_nm=peak,
                  margin_fraction={j: 1-peak[j]/TORQUE_NM[j] for j in peak},
                  max_xy_error_m=xy_error, max_pitch_error_deg=pitch_error,
                  selected={k: v for k, v in best.items() if k != 'events'},
                  scope='static equal-share feasibility; no measured load/collision/success guarantee')
    return best, report
